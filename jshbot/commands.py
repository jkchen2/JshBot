from jshbot import parser
from jshbot.exceptions import BotException, ErrorTypes

EXCEPTION = 'Commands'


class Command():
    def __init__(
            self, base, sub_commands, description='', other='', shortcuts=None,
            function=None, hidden=False, elevated_level=0, allow_direct=True):
        self.base = base
        self.description = description
        self.other = other
        self.function = function
        self.hidden = hidden
        self.allow_direct = allow_direct
        self.shortcut = shortcuts
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


def get_general_help(bot, server=None, is_owner=False):
    """Gets the general help. Lists all base commands that aren't shortcuts."""
    response = "Here is a list of commands by plugin:\n"
    invoker = bot.get_invoker(server=server)
    plugin_pairs = []
    for plugin_name, plugin in bot.plugins.items():
        plugin_pairs.append((plugin_name, plugin[1]))
    plugin_pairs.sort()

    for plugin_pair in plugin_pairs:
        visible_commands = []
        response += '\n***`{}`***\n'.format(plugin_pair[0])
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
        response += '\n'.join(sorted(listing)) + '\n'

    response += "\nGet help on a command with `{}help <command>`".format(
        invoker)
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
            bot, base, index=shortcut_index, shortcut=True, is_owner=is_owner)

    # Handle specific topic help
    if topic is not None:
        try:
            topic_index = int(topic)
        except:
            guess = parser.guess_index(bot, '{0} {1}'.format(base, topic))
            topic_index = None if guess[1] == -1 else guess[1] + 1
            return get_help(bot, base, topic=topic_index, is_owner=is_owner)
        return usage_reminder(bot, base, index=topic_index)

    response = ''
    if command.description:
        response += 'Description:\n\t{}\n\n'.format(command.description)
    response += usage_reminder(
        bot, base, monospace=False, is_owner=is_owner, server=server) + '\n'
    if command.shortcut:
        response += usage_reminder(
            bot, base, monospace=False, shortcut=True,
            is_owner=is_owner, server=server) + '\n'
    if command.other:
        response += 'Other information:\n\t{}'.format(command.other)

    return '```\n{}```'.format(response)


def usage_reminder(
        bot, base, index=None, monospace=True, shortcut=False,
        server=None, is_owner=False):
    """Returns the usage syntax for the base command (simple format).

    Keyword arguments:
    index -- gets that specific index's help entry
    monospace -- returns the result wrapped in '```' or '`' if found
    server_id -- used to check the invoker
    is_mod -- used to check for private command visibility
    """
    command = bot.commands[base]
    if command.hidden and not is_owner:
        return "```\nCommand is hidden.```"
    if shortcut:
        if base in command.shortcut.bases:
            base = command.base
        command = command.shortcut
    invoker = bot.get_invoker(server=server)

    if index is None:
        if shortcut:
            response = 'Shortcuts:\n'
        else:
            response = 'Usage: {0}{1} (syntax)\n'.format(invoker, base)
        spacing = 2 if len(command.help) >= 10 else 1
        for topic_index, (syntax, details) in enumerate(command.help):
            details = details if details else '[Details not provided]'
            if shortcut:
                response += '\t{0}{1} {2}\n\t\t{0}{3} {4}\n'.format(
                    invoker, command.bases[topic_index], syntax, base, details)
            else:
                syntax = syntax if syntax else '[Syntax not provided]'
                response += '\t[{1: <{0}}] {2}\n'.format(
                    spacing, topic_index + 1, syntax)
    else:
        if shortcut:
            syntax, result = command.help[index]
            response = '{0}{1} {2}\n\t{0}{3} {4}'.format(
                invoker, command.bases[index], syntax, base, result)
        elif 0 < index <= len(command.help):
            syntax, details = command.help[index - 1]
            syntax = syntax if syntax else '[Syntax not provided]'
            details = details if details else '[Details not provided]'
            response = '{0}{1} {2}\n\t{3}'.format(
                invoker, base, syntax, details)
        else:
            raise BotException(EXCEPTION, "Invalid help index.")

    if monospace:
        response = '{0}\n{1}{0}'.format('```', response)
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
        # new_blueprints = convert_blueprints(command.blueprints)
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


async def execute(bot, message, command, parsed_input, initial_data):
    """Calls get_response of the given plugin associated with the base."""
    if message.channel.is_private:
        if not command.allow_direct:
            raise BotException(
                EXCEPTION, "Cannot use this command in a direct message.")
        elif command.elevated_level > 0 and not any(initial_data[3:]):
            raise BotException(
                EXCEPTION, "Special permissions commands cannot be used in "
                "direct messages.")

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

    if command.function:
        given_function = command.function
    else:
        given_function = command.plugin.get_response
    return await (given_function(bot, message, *parsed_input, initial_data[0]))


async def handle_active_message(bot, message_reference, command, extra):
    """Calls handle_active_message of the given base."""
    await command.plugin.handle_active_message(bot, message_reference, extra)
