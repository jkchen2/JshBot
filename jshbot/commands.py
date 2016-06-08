from jshbot import data
from jshbot.exceptions import BotException, ErrorTypes

EXCEPTION = 'Commands'


class Command():
    def __init__(
            self, base, sub_commands, description='', other='',
            shortcuts=None, function=None, private=False, elevated=0):
        self.base = base
        self.description = description
        self.other = other
        self.function = function
        self.elevated = elevated  # 1 - mods, 2 - server owners, 3 - bot owners
        self.shortcut = shortcuts
        self.plugin = None  # Added later

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
        self.bases, syntaxes, templates, syntaxes_help, results = zip(*args)
        self.format_pairs = list(zip(syntaxes, templates))
        self.help = list(zip(syntaxes_help, results))


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
    for blueprint in blueprints:  # Convert each individual plan
        user_plans = blueprint.split()
        new_blueprint = []
        for plan in user_plans:  # Parse each option
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
        if command.shortcuts:
            for shortcut_base in command.shortcuts.bases:
                check_and_add(bot.commands, shortcut_base, command)
        new_blueprints = convert_blueprints(command.blueprints)
        check_and_add(bot.commands, command.base, new_blueprints)


def get_blueprints(bot, base):
    """Gets the blueprints associated with the given base.

    Also returns whether or not the command is a shortcut. If the base is not
    found in the commands dictionary, returns (None, None)
    """
    try:
        command = bot.commands[base]
        is_shortcut = base in command.shortcuts.bases
        return (command.blueprints, is_shortcut)
    except KeyError:
        return (None, None)


async def execute(bot, message, command, parsed_input):
    """Calls get_response of the given plugin associated with the base."""
    command = bot.commands[parsed_input[0]]

    if message.channel.is_private and not command.allow_direct:
        raise BotException(
            EXCEPTION, "Cannot use this command in a direct message.")
    if command.elevated > 0:
        if (command.elevated == 1 and message.server and not
                data.is_mod(bot, message.server, message.author.id)):
            raise BotException(
                EXCEPTION, "Only server moderators can use this command.")
        elif (command.elevated == 2 and message.server and not
                data.is_admin(bot, message.server, message.author.id)):
            raise BotException(
                EXCEPTION, "Only server owners can use this command.")
        elif not data.is_owner(bot, message.author.id):
            raise BotException(
                EXCEPTION, "Only the bot owners can use this command.")

    return await (command.plugin.get_response(bot, message, *parsed_input))


async def handle_active_message(bot, message_reference, command, extra):
    """Calls handle_active_message of the given base."""
    await command.plugin.handle_active_message(bot, message_reference, extra)
