import json

from jshbot import parser, utilities, data
from jshbot.exceptions import BotException, ErrorTypes

EXCEPTION = 'Commands'


class Command():
    def __init__(
            self, base, sub_commands, description='', other='', shortcuts=None,
            function=None, hidden=False, elevated_level=0, allow_direct=True,
            strict_syntax=False):
        self.base = base
        self.description = description
        self.other = other
        self.function = function
        self.hidden = hidden
        self.allow_direct = allow_direct
        self.shortcut = shortcuts
        self.strict = strict_syntax
        self.plugin = None  # Added later

        # 1 - mods, 2 - server owners, 3 - bot owners
        self.elevated_level = elevated_level

        # Convenience
        self.blueprints = sub_commands.blueprints
        self.keywords = sub_commands.keywords
        self.help = sub_commands.help


class SubCommands():
    def __init__(self, *args):
        user_blueprints, syntax, details = zip(*args)
        self.blueprints, self.keywords = convert_blueprints(user_blueprints)
        self.help = list(zip(syntax, details))


class Shortcuts():
    def __init__(self, *args):
        self.bases, syntaxes, templates, results, syntaxes_help = zip(*args)
        self.format_pairs = list(zip(syntaxes, templates))
        self.help = list(zip(syntaxes_help, results))


def get_general_manual(bot, server=None):
    """Lists available manual entries and assigns each one an index."""
    response = "Here is a list of manual entries by plugin:\n"
    invoker = utilities.get_invoker(bot, server=server)
    counter = 1
    for manual in bot.manuals:
        response += '\n***`{}`***\n'.format(manual[0])
        for entry in manual[1]['order']:
            response += '\t**`[{0: <2}]`** {1}\n'.format(counter, entry)
            counter += 1
    response += (
        '\nRead an entry with `{}manual <entry number>`\nNew? It is '
        'recommended that you read manual entries 1, 2, and 3.').format(
             invoker)
    return response


def get_manual(bot, entry, server=None):
    """Gets the given manual entry."""
    invoker = utilities.get_invoker(bot, server=server)
    base_invoker = utilities.get_invoker(bot)
    if entry == 0:
        raise BotException(EXCEPTION, "Invalid manual entry.")
    for manual in bot.manuals:
        manual_length = len(manual[1]['order'])
        if manual_length >= entry:
            entry_title = manual[1]['order'][entry - 1]
            found_entry = manual[1]['entries'][entry_title]
            response = '***`{0}`*** -- {1}\n\n'.format(manual[0], entry_title)
            return response + found_entry.format(
                invoker=invoker, base_invoker=base_invoker)
        else:
            entry -= manual_length
    raise BotException(EXCEPTION, "Invalid manual entry.")


def get_general_help(bot, server=None, is_owner=False):
    """Gets the general help. Lists all base commands that aren't shortcuts."""
    response = "Here is a list of commands by plugin:\n"
    invoker = utilities.get_invoker(bot, server=server)
    plugin_pairs = []
    for plugin_name, plugin in bot.plugins.items():
        plugin_pairs.append((plugin_name, plugin[1]))
    plugin_pairs.sort()

    for plugin_pair in plugin_pairs:
        visible_commands = []
        for command in plugin_pair[1]:
            level = command.elevated_level
            hidden = command.hidden
            if (((level < 3 and not hidden) or is_owner) and
                    command not in visible_commands):
                visible_commands.append(command)
        listing = []
        for command in visible_commands:
            if command.description:
                description = command.description
            else:
                description = '[Description not provided]'
            listing.append('\t**`{0}`** -- {1}'.format(
                command.base, description))
        if listing:
            response += '\n***`{}`***\n'.format(plugin_pair[0])
            response += '\n'.join(sorted(listing)) + '\n'

    response += ("\nGet help on a command with `{0}help <command>`\n"
                 "Confused by the syntax? See `{0}manual 3`").format(invoker)
    return response


def get_help(bot, base, topic=None, is_owner=False, server=None):
    """Gets the help of the base command, or the topic of a help command."""
    # Check for shortcut first
    try:
        base = base.lower()
        command = bot.commands[base]
    except KeyError:
        raise BotException(
            EXCEPTION, "Invalid command base. Ensure sure you are not "
            "including the command invoker.")

    if command.hidden and not is_owner:
        return '```\nCommand is hidden.```'
    if command.shortcut and base in command.shortcut.bases:
        shortcut_index = command.shortcut.bases.index(base)
        return usage_reminder(
            bot, base, index=shortcut_index, shortcut=True,
            is_owner=is_owner, server=server)

    # Handle specific topic help
    if topic is not None:
        try:
            topic_index = int(topic)
        except:
            guess = parser.guess_index(bot, '{0} {1}'.format(base, topic))
            topic_index = None if guess[1] == -1 else guess[1] + 1
            return get_help(
                bot, base, topic=topic_index, is_owner=is_owner, server=server)
        return usage_reminder(bot, base, index=topic_index, server=server)

    response = ''
    invoker = utilities.get_invoker(bot, server=server)
    if command.description:
        response += '**Description**:\n{}\n\n'.format(
            command.description.format(invoker=invoker))
    response += usage_reminder(
        bot, base, is_owner=is_owner, server=server) + '\n'
    if command.shortcut:
        response += usage_reminder(
            bot, base, shortcut=True, is_owner=is_owner, server=server) + '\n'
    if command.other:
        response += '**Other information**:\n{}'.format(
            command.other.format(invoker=invoker))

    return response.rstrip()


def usage_reminder(
        bot, base, index=None, shortcut=False, server=None, is_owner=False):
    """Returns the usage syntax for the base command (simple format).

    Keyword arguments:
    index -- gets that specific index's help entry
    server_id -- used to check the invoker
    is_mod -- used to check for private command visibility
    """
    command = bot.commands[base]
    if command.hidden and not is_owner:
        return "`\nCommand is hidden.`"
    if shortcut:
        if base in command.shortcut.bases:
            base = command.base
        command = command.shortcut
    invoker = utilities.get_invoker(bot, server=server)

    if index is None:
        if shortcut:
            response = '**Shortcuts**:\n'
        else:
            response = '**Usage**:\n'
        for topic_index, (syntax, details) in enumerate(command.help):
            details = details if details else '[Details not provided]'
            if shortcut:
                response += '`{0}{1} {2}`\t→\t`{0}{3} {4}`\n'.format(
                    invoker, command.bases[topic_index], syntax, base, details)
            else:
                syntax = syntax if syntax else '[Syntax not provided]'
                response += '`{0}{1} {2}`\n'.format(invoker, base, syntax)
    else:
        if shortcut:
            syntax, result = command.help[index]
            response = '`{0}{1} {2}`\t→\t`{0}{3} {4}`'.format(
                invoker, command.bases[index], syntax, base, result)
        elif 0 < index <= len(command.help):
            syntax, details = command.help[index - 1]
            syntax = syntax if syntax else '[Syntax not provided]'
            details = details if details else '[Details not provided]'
            response = '`{0}{1} {2}`\n{3}'.format(
                invoker, base, syntax, details)
        else:
            raise BotException(EXCEPTION, "Invalid help index.")

    return response


def convert_blueprints(blueprints):
    """
    Converts user-friendly(ish) blueprints into the system-friendly version.
    Also returns a list of keywords given by the blueprints.
    Converts: "?opt1 opt2: ::+" To:
    [(T, "opt1", F), (F, "opt2", T), (F, ":", F), (F, ":", F), (F, "+", F)]
    Converts: "^" To: [(F, "^", F)]
    """
    new_blueprints = []
    keywords = []
    for blueprint in blueprints:
        user_plans = blueprint.split()
        new_blueprint = []
        for plan in user_plans:  # Parse each individual plan
            if plan[0] in (':', '^', '&', '+', '#'):
                for argument_type in plan:
                    new_blueprint.append((False, argument_type, False))
            else:
                required = plan[0] == '?'
                argument = plan[-1] == ':'
                option_key = plan.strip('?:')
                if option_key not in keywords:
                    keywords.append(option_key)
                new_blueprint.append((required, option_key, argument))
        new_blueprints.append(new_blueprint)
    return new_blueprints, keywords


def add_commands(bot, new_commands, plugin):
    """Adds the given commands the bot's command dictionary.

    Checks that all keys in the new dictionary are unique from those in the old
    dictionary. If all keys are good, add them to the bot commands dictionary.
    """

    # Just a quick duplicate checker
    def check_and_add(dictionary, key, value):
        if key in dictionary:
            raise BotException(
                EXCEPTION, "Attempting to add a command that already exists.",
                key, error_type=ErrorTypes.FATAL)
        dictionary[key] = value

    for command in new_commands:
        command.plugin = plugin
        if command.shortcut:
            for shortcut_base in command.shortcut.bases:
                check_and_add(bot.commands, shortcut_base, command)
        check_and_add(bot.commands, command.base, command)


def get_blueprints(bot, base):
    """Gets the blueprints associated with the given base.

    Also returns whether or not the command is a shortcut. If the base is not
    found in the commands dictionary, returns (None, None)
    """
    try:
        command = bot.commands[base]
        is_shortcut = base in command.shortcut.bases
        return (command.blueprints, is_shortcut)
    except KeyError:
        return (None, None)


def add_manuals(bot):
    """Reads all manuals in the config folder and adds them to the bot."""
    manual_order = []
    directory = bot.path + '/config/'
    for plugin in bot.plugins:
        try:
            with open(directory + plugin + '-manual.json', 'r') as manual_file:
                loaded_manual = (plugin, json.load(manual_file))
                if 'entries' not in loaded_manual[1]:
                    raise BotException(
                        EXCEPTION,
                        "The manual for plugin {} has no entries.".format(
                            plugin))
                if 'order' not in loaded_manual[1]:
                    raise BotException(
                        EXCEPTION,
                        "The manual for plugin {} has no order.".format(
                            plugin))
                for entry in loaded_manual[1]['order']:
                    if entry not in loaded_manual[1]['entries']:
                        raise BotException(
                            EXCEPTION, "The manual for plugin {0} is missing "
                            "the entry {1}.".format(plugin, entry))
                if plugin == 'base':
                    bot.manuals.append(loaded_manual)
                else:
                    manual_order.append(loaded_manual)
        except FileNotFoundError:
            if plugin == 'base':
                raise BotException(
                    EXCEPTION, "The base manual was not found.",
                    error_type=ErrorTypes.STARTUP)
            else:
                pass
    bot.manuals += sorted(manual_order)


async def execute(bot, message, command, parsed_input, initial_data):
    """Calls get_response of the given plugin associated with the base."""
    if message.channel.is_private:
        if not command.allow_direct:
            raise BotException(
                EXCEPTION, "Cannot use this command in a direct message.")
        elif 0 < command.elevated_level < 3:
            raise BotException(
                EXCEPTION, "Special permissions commands cannot be used in "
                "direct messages.")
        disabled_commands = []
    else:
        disabled_commands = data.get(
            bot, 'base', 'disabled', server_id=message.server.id, default=[])

    if command.elevated_level > 0:
        if command.elevated_level == 1 and not any(initial_data[1:]):
            raise BotException(
                EXCEPTION, "Only server moderators can use this command.")
        elif command.elevated_level == 2 and not any(initial_data[2:]):
            raise BotException(
                EXCEPTION, "Only server owners can use this command.")
        elif command.elevated_level >= 3 and not initial_data[3]:
            raise BotException(
                EXCEPTION, "Only the bot owners can use this command.")

    if command.base in disabled_commands and not any(initial_data[1:]):
        raise BotException(
            EXCEPTION, "This command is disabled on this server.")

    if command.function:
        given_function = command.function
    else:
        given_function = command.plugin.get_response
    return await (given_function(bot, message, *parsed_input, initial_data[0]))


async def handle_active_message(bot, message_reference, command, extra):
    """Calls handle_active_message of the given base."""
    await command.plugin.handle_active_message(bot, message_reference, extra)
