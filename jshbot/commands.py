import json

from enum import Enum
from pprint import pformat
from collections import OrderedDict
from discord.abc import PrivateChannel

class ArgTypes(Enum):
    SINGLE, OPTIONAL, SPLIT, SPLIT_OPTIONAL, MERGED, MERGED_OPTIONAL = range(6)

class MessageTypes(Enum):
    NORMAL, PERMANENT, REPLACE, ACTIVE, INTERACTIVE = range(5)

from jshbot import parser, utilities, data
from jshbot.exceptions import BotException, ConfiguredBotException, ErrorTypes

CBException = ConfiguredBotException('Commands')


class Response():
    def __init__(
            self, content=None, tts=False, message_type=MessageTypes.NORMAL, extra=None,
            embed=None, file=None, files=None, reason=None, delete_after=None, nonce=None,
            extra_function=None, destination=None):
        '''
        Keyword arguments:
        message_type -- One of the MessageTypes available. See core for more.
        extra -- Used depending on the given message_type
        extra_function -- Used depending on the given message_type
        destination -- If set, the bot sends to the destination instead of replying
        '''
        self.content = content
        self.tts = tts
        self.message_type = message_type
        self.extra = extra
        self.embed = embed
        self.file = file
        self.files = files
        self.reason = reason
        self.delete_after = delete_after
        self.nonce = nonce
        self.extra_function = extra_function
        self.destination = destination

        self.message = None  # Set by the core

    def __repr__(self):
        result = ''
        if self.content:
            result = self.content
        if self.embed:
            if result:
                result += '\n\nEmbed:\n'
            result += pformat(self.embed.to_dict())
        return result

    def get_send_kwargs(self, use_edit_kwargs):
        if use_edit_kwargs:
            keywords = ['content', 'embed']
        else:
            keywords = [
                'content', 'tts', 'embed', 'file', 'files', 'reason', 'delete_after', 'nonce']
        return dict((it, getattr(self, it)) for it in keywords)

    def is_empty(self):
        return not (self.content or self.embed)


class SubCommand():
    def __init__(self, *optargs, doc=None, function=None, elevated_level=None,
            allow_direct=None, strict_syntax=None, no_selfbot=None, id=None):
        """
        Arguments:
        optargs -- Composed of a sequence of Opt and Arg objects.
            The last element can be an Attachment.

        Keyword arguments:
        doc -- The help string used whenever detailed help is requested.

        Override keyword arguments: (function, elevated_level, ...)
            These arguments will override the behavior of the base command's
            properties. If left at None, they will be replaced with the base command's
            specified properties. See Command documentation for more.
        """
        self.opts = OrderedDict()
        self.args = []
        self.optargs = optargs
        self.attaches = None
        self.doc = doc
        self.function = function
        self.elevated_level = elevated_level
        self.allow_direct = allow_direct
        self.strict_syntax = strict_syntax
        self.no_selfbot = no_selfbot
        self.help_embed_fields = []
        self.keywords = []
        self.command = None  # Set by Command in init
        self.index = None  # Set by Command in init
        self.id = id  # Used as an alternative to index
        for index, optarg in enumerate(optargs):
            if isinstance(optarg, Arg):
                self.args.append(optarg)
            elif isinstance(optarg, Opt):
                if self.args:
                    raise CBException("Cannot have opts after args.")
                if optarg.name in self.opts:
                    raise CBException("Duplicate argument found: {}".format(optarg.name))
                self.opts[optarg.name] = optarg
            elif isinstance(optarg, Attachment):
                if not optargs.index(optarg) == len(optargs) - 1:
                    raise CBException("Attachment must be the last optarg.")
                self.attaches = optarg
            else:
                raise CBException("SubCommand must contain only Opt, Arg, or Attachment objects.")
            optarg.index = index
            optarg.subcommand = self
            if optarg.name not in self.keywords:
                self.keywords.append(optarg.name)

    def _build_help_string(self):  # Add base to help lines
        help_lines = []
        clean_help_lines = []
        parameter_lines = []
        clean_parameter_lines = []

        for index, optarg in enumerate(self.optargs):
            help_lines.append(optarg.help_string)
            clean_help_lines.append(optarg.clean_help_string)
            if optarg.doc_string:
                parameter_lines.append(optarg.doc_string)
                clean_parameter_lines.append(optarg.clean_doc_string)

        # TODO: Consider switching help_string and quick_help? Consistency issue
        self.help_string = '**`{base}`**　{help_string}'.format(
            base=self.command.base, help_string='　'.join(help_lines))
        self.clean_help_string = '{base}    {help_string}'.format(
            base=self.command.base, help_string='    '.join(clean_help_lines))
        self.parameter_string = '\n'.join(parameter_lines)
        self.clean_parameter_string = '\n'.join(clean_parameter_lines)
        self.quick_help = self.help_string
        self.clean_quick_help = self.clean_help_string
        self.help_embed_fields.append(('Usage:', self.help_string))
        if self.parameter_string:
            self.quick_help += '\n' + self.parameter_string
            self.clean_quick_help += '\n' + self.clean_parameter_string
            self.help_embed_fields.append(('Parameter details:', self.parameter_string))
        if self.doc:
            self.quick_help += '\n\n' + self.doc
            self.clean_quick_help += '\n\n' + self.doc
            self.help_embed_fields.append(('Description:', self.doc))

    def __repr__(self):
        return "<'{}' SubCommand>".format(self.clean_help_string)


class Command():
    def __init__(
            self, base, subcommands=[SubCommand()], description='', other='',
            category='miscellaneous', shortcuts=[], function=None, hidden=False, elevated_level=0,
            allow_direct=True, strict_syntax=False, no_selfbot=False):
        """
        Arguments:
        base -- The base command name. Acts as a secondary invoker of sorts.

        Keyword arguments:
        subcommands -- A list of SubCommand objects.
        description -- Small description of the command. Shows up in the general help menu.
        other -- Extra description. Shows up in the command help menu.
        group -- Categorizes the command with other commands of the same group.
        shortcuts -- A list of Shortcut objects.
        function -- A custom function to call instead of get_response.
        hidden -- Prevents the command from showing up in the help menu.
        elevated_level -- Limits usage to a certain permission level. 0 is
            everybody, 1 is bot moderators, 2 is guild owners, and 3 is bot
            owners. This is a hierarchy model.
        allow_direct -- Allows the command to be used in direct messages.
        strict_syntax -- Parameter order is strictly maintained.
        no_selfbot -- Disallows the command to be used in selfbot mode.
        """
        self.base = base.lower().strip()
        self.subcommands = subcommands
        self.description = description if description else '[Description not provided]'
        self.other = other
        self.category = category.strip().title()
        self.function = function
        self.hidden = hidden
        self.allow_direct = allow_direct
        self.shortcuts = shortcuts
        self.strict_syntax = strict_syntax
        self.no_selfbot = no_selfbot
        self.help_embed_fields = []
        self.plugin = None  # Assigned later on

        # 1 - bot moderators, 2 - guild owners, 3 - bot owners
        self.elevated_level = elevated_level

        # Generate help string and keywords and
        #   replace subcommand properties with configured values
        replacements = [
            'function', 'elevated_level', 'allow_direct', 'strict_syntax', 'no_selfbot']
        self.help_lines = []
        self.clean_help_lines = []
        self.keywords = []
        for index, subcommand in enumerate(subcommands):
            subcommand.index = index
            subcommand.command = self
            for replacement in replacements:
                if getattr(subcommand, replacement) is None:
                    setattr(subcommand, replacement, getattr(self, replacement))
            subcommand._build_help_string()
            self.help_lines.append(subcommand.help_string)
            self.clean_help_lines.append(subcommand.clean_help_string)
            for keyword in subcommand.keywords:
                if keyword not in self.keywords:
                    self.keywords.append(keyword)
        self.quick_help = '\n'.join(self.help_lines)  # TODO: Consider no help_lines
        self.clean_quick_help = '\n'.join(self.clean_help_lines)
        self.help_embed_fields.append(('Usage:', self.quick_help))  # Can be edited later
        self.usage_embed_index = 0

        shortcut_help_lines = []
        clean_shortcut_help_lines = []
        for shortcut in shortcuts:
            shortcut.command = self
            shortcut._build_help_string()
            shortcut_help_lines.append(shortcut.help_string)
            clean_shortcut_help_lines.append(shortcut.clean_help_string)
        self.shortcut_help_string = '\n'.join(shortcut_help_lines)
        self.clean_shortcut_help_string = '\n'.join(clean_shortcut_help_lines)

        self.help_string = '**Usage**:\n' + self.quick_help
        self.clean_help_string = 'Usage:\n' + self.clean_quick_help
        if self.description:
            self.help_string = '**Description**:\n{description}\n\n{help_string}'.format(
                description=self.description, help_string=self.help_string)
            self.clean_help_string = 'Description:\n{description}\n\n{help_string}'.format(
                description=self.description, help_string=self.clean_help_string)
            self.help_embed_fields.insert(0, ('Description:', self.description))
            self.usage_embed_index = 1
        if self.shortcut_help_string:
            self.help_string += '\n\n**Shortcuts**:\n{shortcut_help_string}'.format(
                shortcut_help_string=self.shortcut_help_string)
            self.clean_help_string += '\n\nShortcuts:\n{shortcut_help_string}'.format(
                shortcut_help_string=self.clean_shortcut_help_string)
            self.help_embed_fields.append(('Shortcuts:', self.shortcut_help_string))
        if self.other:
            self.help_string += '\n\n**Other information**:\n{other_string}'.format(
                other_string = self.other)
            self.clean_help_string += '\n\nOther information:\n{other_string}'.format(
                other_string = self.other)
            self.help_embed_fields.append(('Other information:', self.other))

    def __repr__(self):
        return "<'{}' Command>".format(self.base)

    def __lt__(self, other):
        return self.base < other.base


class Opt():
    def __init__(
            self, name, optional=False, attached=None, doc=None, quotes_recommended=True,
            convert=None, check=None, convert_error=None, check_error=None, default=''):
        """
        Keyword arguments:
        optional -- Whether or not this option is optional.
        attached -- The name of the required user value as the attached parameter.
        doc -- Additional help string for the given option.
        convert -- Function or class to use to convert the value.
        check -- Function to check the (converted) value. Passed in: context, value
        convert_error -- Error message upon conversion failure.
        check_error -- Error message upon check failure.
        """
        self.name = name.strip()
        self.optional = optional
        self.attached = attached
        self.check = check
        self.doc = doc
        self.quotes_recommended = quotes_recommended
        self.default = default
        self.subcommand = None  # Set by Subcommand in init

        # Invalid value type for {name}:
        if convert is int:
            convert = lambda b, m, v, *a: int(v)
            if not convert_error:
                convert_error = 'Value must be an integer number.'
        elif convert is float:
            convert = lambda b, m, v, *a: float(v)
            if not convert_error:
                convert_error = 'Value must be a decimal number.'
        if not convert_error:
            convert_error = 'Unknown specification.'
        self.convert = convert
        self.convert_error = 'Invalid value type for \'{name}\': {error}'.format(
            name=self.name, error=convert_error)

        # Invalid value for {name}:
        if not check_error:
            check_error = 'Unknown specification.'
        self.check_error = 'Invalid value for \'{name}\': {error}'.format(
            name=self.attached if self.attached else self.name, error=check_error)

        self._build_help_string()

    def _build_help_string(self):
        quotes = '"' if self.quotes_recommended else ''
        wrap = '_' if self.optional else '**'
        clean_wrap = ['[', ']'] if self.optional else ['', '']
        current = '{wrap}`{name}`'.format(wrap=wrap, name=self.name)
        clean_current = '{wrap[0]}{name}'.format(wrap=clean_wrap, name=self.name)
        if self.attached:
            current += '__`{quotes}{attached}{quotes}`__'.format(
                quotes=quotes, attached=self.attached)
            clean_current += ' <{quotes}{attached}{quotes}>'.format(
                quotes=quotes, attached=self.attached)
        current += '{wrap}'.format(wrap=wrap)
        clean_current += '{wrap[1]}'.format(wrap=clean_wrap)
        self.help_string = current
        self.clean_help_string = clean_current
        if self.doc:
            self.doc_string = '{name}: {doc}'.format(name=current.strip(), doc=self.doc)
            self.clean_doc_string = '{name}: {doc}'.format(
                name=clean_current.strip(), doc=self.doc)
        else:
            self.doc_string = self.clean_doc_string = None

    def convert_and_check(self, bot, message, value):
        if self.convert:
            try:
                if isinstance(value, list):
                    new_values = []
                    for entry in value:
                        new_values.append(self.convert(bot, message, entry))
                    value = new_values
                else:
                    value = self.convert(bot, message, value)
            except:
                if hasattr(self.convert, 'get_convert_error'):
                    convert_error = self.convert.get_convert_error(bot, message, value)
                else:
                    convert_error = self.convert_error
                raise BotException(
                    'Parser', convert_error, embed_fields=self.subcommand.help_embed_fields)
        if self.check:
            try:
                if isinstance(value, list):
                    for entry in value:
                        assert self.check(bot, message, entry)
                else:
                    assert self.check(bot, message, value)
            except:
                if hasattr(self.check, 'get_check_error'):
                    check_error = self.check.get_check_error(bot, message, value)
                else:
                    check_error = self.check_error
                raise BotException(
                    'Parser', check_error, embed_fields=self.subcommand.help_embed_fields)
        return value


class Arg(Opt):
    def __init__(
            self, name, argtype=ArgTypes.SINGLE, additional=None, doc=None,
            convert=None, check=None, convert_error=None, check_error=None,
            quotes_recommended=True, default=''):
        self.argtype = argtype
        self.additional = additional
        super().__init__(
            name, convert=convert, check=check, doc=doc, quotes_recommended=quotes_recommended,
            convert_error=convert_error, check_error=check_error, default=default)

    def _build_help_string(self):
        if self.argtype in (ArgTypes.SPLIT, ArgTypes.MERGED):
            wrap = '**'
            clean_wrap = ['', '']
        else:
            wrap = '_'
            clean_wrap = ['[', ']']
        if (self.argtype in (ArgTypes.MERGED, ArgTypes.MERGED_OPTIONAL) or
                not self.quotes_recommended):
            quotes = ''
        else:
            quotes = '"'
        current = '{wrap}__`{quotes}{name}{quotes}`__{wrap}'.format(
            wrap=wrap, quotes=quotes, name=self.name)
        clean_current = '{wrap[0]}<{quotes}{name}{quotes}>{wrap[1]}'.format(
            wrap=clean_wrap, quotes=quotes, name=self.name)
        if self.additional:
            current += '　{wrap}__`{additional}`__{wrap}'.format(
                wrap=wrap, additional=self.additional)
            clean_current += '    {wrap[0]}<{additional}>{wrap[1]}'.format(
                wrap=clean_wrap, additional=self.additional)
        self.help_string = current
        self.clean_help_string = clean_current
        if self.doc:
            self.doc_string = '{name}: {doc}'.format(name=current.strip(), doc=self.doc)
            self.clean_doc_string = '{name}: {doc}'.format(
                name=clean_current.strip(), doc=self.doc)
        else:
            self.doc_string = self.clean_doc_string = None


class Attachment():
    def __init__(self, name, optional=False, doc=None):
        self.name = name.strip()
        self.optional = optional
        self.doc = doc
        wrap = '_' if optional else '**'
        clean_wrap = ['[', ']'] if optional else ['', '']
        current = '{wrap}`[Attachment: `__`{name}`__`]`{wrap}'.format(wrap=wrap, name=name)
        clean_current = '{wrap[0]}|Attachment: <{name}>|{wrap[1]}'.format(
            wrap=clean_wrap, name=name)
        self.help_string = current
        self.clean_help_string = clean_current
        if doc:
            self.doc_string = '{name}: {doc}'.format(name=current.strip(), doc=doc)
            self.clean_doc_string = '{name}: {doc}'.format(name=clean_current.strip(), doc=doc)
        else:
            self.doc_string = self.clean_doc_string = None


class Shortcut():
    def __init__(self, base, replacement, *args):
        """
        Arguments:
        base -- The base invoker. Similar to a normal command.
        replacement -- Replacement string. Filled out and re-parsed.
        args -- Argument objects.
        """
        self.base = base
        self.replacement = replacement
        self.args = args
        self.command = None  # Set by Command in init
        self.plugin = None  # Used to identify shortcuts to reload (set in plugins.py)

    def __repr__(self):
        return "<'{}' Shortcut>".format(self.base)

    def _build_help_string(self):
        command_base = self.command.base
        presub_help = '`\u200b`'.join([it.help_string for it in self.args])
        clean_presub_help = '  '.join([it.clean_help_string for it in self.args])

        arg_dict = dict([(it.name, '\u200b`' + it.help_string + '`') for it in self.args])
        clean_arg_dict = dict([(it.name, it.clean_help_string) for it in self.args])
        clean_postsub_help = self.replacement.format(**clean_arg_dict)
        new_replacement = self.replacement + '`'
        postsub_help = new_replacement.format(**arg_dict).replace('``', '')

        help_base = '`{base}`\u200b`\u200b`'.format(base=self.base)
        self.help_string = '{base}{presub}\t→\t`{command_base} {postsub}'.format(
            base=help_base, presub=presub_help, postsub=postsub_help, command_base=command_base)
        self.clean_help_string = '{base} {presub}\t→\t{command_base} {postsub}'.format(
            base=self.base, presub=clean_presub_help,
            postsub=clean_postsub_help, command_base=command_base)
        self.help_embed_fields = [('Shortcut usage:', self.help_string)]


def get_general_manual(bot, guild=None):
    """Lists available manual entries and assigns each one an index."""
    response = "Here is a list of manual entries by plugin:\n"
    invoker = utilities.get_invoker(bot, guild=guild)
    counter = 1
    for manual in bot.manuals:
        response += '\n***`{}`***\n'.format(manual[0])
        for entry in manual[1]['order']:
            response += '\t**`[{0: <2}]`** {1}\n'.format(counter, entry)
            counter += 1
    response += (
        '\nRead an entry with `{}manual <entry number>`\nNew? It is '
        'recommended that you read manual entries 1, 2, and 3.').format(invoker)
    return response


def get_manual(bot, subject, entry, guild=None):
    """Gets the given manual entry as a tuple: (topic, [text, text2])."""
    invoker = utilities.get_invoker(bot, guild=guild)
    base_invoker = utilities.get_invoker(bot)
    if entry <= 0:
        raise CBException("Invalid manual entry.")
    for manual in bot.manuals:
        manual_length = len(manual[1]['order'])
        if manual_length >= entry:
            entry_title = manual[1]['order'][entry - 1]
            found_entry = manual[1]['entries'][entry_title]
            response = '***`{0}`*** -- {1}\n\n'.format(manual[0], entry_title)
            return response + found_entry.format(invoker=invoker, base_invoker=base_invoker)
        else:
            entry -= manual_length
    raise CBException("Invalid manual entry.")


def get_general_help(bot, guild=None, is_owner=False):
    """Gets the general help. Lists all base commands that aren't shortcuts."""
    response = "Here is a list of commands by group:\n"
    invoker = utilities.get_invoker(bot, guild=guild)

    '''
    plugin_pairs = []
    for plugin_name, plugin in bot.plugins.items():
        plugin_pairs.append((plugin_name, plugin[1]))
    plugin_pairs.sort()
    '''
    group_dictionary = {}

    for plugin_name, plugin in bot.plugins.items():
        visible_commands = []
        for command in plugin[1]:
            level = command.elevated_level
            hidden = command.hidden
            group = command.group
            if (((level < 3 and not hidden) or is_owner) and
                    command not in visible_commands):
                if command.description:
                    description = command.description
                else:
                    description = '[Description not provided]'
                if group_dictionary.get(group) is None:
                    group_dictionary[group] = []
                group_dictionary[group].append('**`{0}`** -- {1}'.format(
                    command.base, description))

    listing = []
    for group, entries in sorted(list(group_dictionary.items())):
        listing.append('\n***`{0}`***\n\t{1}'.format(
            group, '\n\t'.join(sorted(entries))))
    response += '\n'.join(listing) + '\n'

    response += ("\nGet help on a command with `{0}help <command>`\n"
                 "Confused by the syntax? See `{0}manual 3`").format(invoker)
    return response


def get_help(bot, base, topic=None, is_owner=False, guild=None):
    """Gets the help of the base command, or the topic of a help command."""
    try:
        base = base.lower()
        command = bot.commands[base]
    except KeyError:
        raise CBException(
            "Invalid command base. Ensure sure you are not including the command invoker.")

    if command.hidden and not is_owner:
        return '```\nCommand is hidden.```'
    if command.shortcut and base in command.shortcut.bases:
        shortcut_index = command.shortcut.bases.index(base)
        return usage_reminder(
            bot, base, index=shortcut_index, shortcut=True,
            is_owner=is_owner, guild=guild)

    # Handle specific topic help
    if topic is not None:
        try:
            topic_index = int(topic)
        except:  # Guess the help index
            guess = parser.guess_index(bot, '{0} {1}'.format(base, topic))
            topic_index = None if guess[1] == -1 else guess[1] + 1
            return get_help(
                bot, base, topic=topic_index, is_owner=is_owner, guild=guild)
        else:  # Proper index given
            return usage_reminder(bot, base, index=topic_index, guild=guild)

    response = ''
    invoker = utilities.get_invoker(bot, guild=guild)
    if command.description:
        response += '**Description**:\n{}\n\n'.format(
            command.description.format(invoker=invoker))
    response += usage_reminder(
        bot, base, is_owner=is_owner, guild=guild) + '\n'
    if command.shortcut:
        response += usage_reminder(
            bot, base, shortcut=True, is_owner=is_owner, guild=guild) + '\n'
    if command.other:
        response += '**Other information**:\n{}'.format(
            command.other.format(invoker=invoker))

    return response.rstrip()


def usage_reminder(
        bot, base, index=None, shortcut=False, guild=None, is_owner=False):
    """Returns the usage syntax for the base command (simple format).

    Keyword arguments:
    index -- gets that specific index's help entry
    guild_id -- used to check the invoker
    is_mod -- used to check for private command visibility
    """
    command = bot.commands[base]
    if command.hidden and not is_owner:
        return "`\nCommand is hidden.`"
    if shortcut:
        if base in command.shortcut.bases:
            base = command.base
        command = command.shortcut
    invoker = utilities.get_invoker(bot, guild=guild)

    if index is None:  # List all commands or shortcuts
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
    else:  # Help on a specific command
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
            raise CBException("Invalid help index.")

    return response


#async def execute(bot, message, subcommand, parsed_input, initial_data):
async def execute(bot, context):
    """Calls get_response of the given plugin associated with the base."""
    subcommand = context.subcommand
    elevation = context.elevation

    if bot.selfbot and subcommand.no_selfbot:
        raise CBException("This command cannot be used in selfbot mode.")

    if elevation < 3 and subcommand.command.base in bot.locked_commands:
        raise CBException("This command is locked by the bot owner.")

    if isinstance(context.message.channel, PrivateChannel):
        if not subcommand.allow_direct:
            raise CBException("Cannot use this command in a direct message.")
        elif 0 < subcommand.elevated_level < 3:
            raise CBException("Special permissions commands cannot be used in direct messages.")
        disabled_commands = []
    else:
        disabled_commands = data.get(
            bot, 'base', 'disabled', guild_id=context.guild.id, default=[])

    if subcommand.elevated_level > 0:
        if subcommand.elevated_level == 1 and elevation < 1:
            raise CBException("Only bot moderators can use this command.")
        elif subcommand.elevated_level == 2 and elevation < 2:
            raise CBException("Only the server owner can use this command.")
        elif subcommand.elevated_level >= 3 and elevation < 3:
            raise CBException("Only the bot owner(s) can use this command.")

    for disabled_base, disabled_index in disabled_commands:
        if (subcommand.command.base == disabled_base and
                disabled_index in (-1, subcommand.index) and elevation < 1):
            raise CBException("This command is disabled on this server.")

    if subcommand.function:
        given_function = subcommand.function
    else:
        given_function = subcommand.command.plugin.get_response
    return await given_function(bot, context)
