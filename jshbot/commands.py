import json
import inspect

from enum import Enum, IntEnum
from pprint import pformat
from collections import OrderedDict
from discord.abc import PrivateChannel

from jshbot import logger

class ArgTypes(Enum):
    """
    These specify argument behavior for commands.

    SINGLE -- Required single argument, separated by spaces, and grouped with quotes.
        Template: SINGLE, SINGLE, SINGLE
        Example: foo "bar biz" baz
        Result: ['foo', 'bar biz', 'baz']
    OPTIONAL -- Like SINGLE, but not required. Must be last.
        Template: SINGLE, OPTIONAL
        Example: foo
        Result: ['foo', '']
    SPLIT -- Required variable number of SINGLE arguments. At least one is required. Must be last.
        Template: SINGLE, SPLIT
        Example: foo "bar biz" baz flub
        Result: ['foo', 'bar biz', 'baz', 'flub']
    SPLIT_OPTIONAL -- Like SPLIT, but not required. Must be last.
        Template: SINGLE, SPLIT_OPTIONAL
        Example: foo
        Result: ['foo', '']
    MERGED -- Required argument that merges all text to the end of the message. Must be last.
        Template: SINGLE, MERGED
        Example: foo bar "biz baz"
        Result: ['foo', 'bar "biz baz"']
    MERGED_OPTIONAL -- Like MERGED, but not required. Must be last.
        Template: MERGED_OPTIONAL
        Example:
        Result: ['']
    """
    SINGLE, OPTIONAL, SPLIT, SPLIT_OPTIONAL, MERGED, MERGED_OPTIONAL = range(6)

class MessageTypes(Enum):
    """
    These specify message behavior in the core whenever a command is issued,
        or when a plugin uses the bot.handle_response method.

    NORMAL -- Normal. The only message type where the issuing command can be edited.
    PERMANENT -- Message is not added to the edit dictionary.
    REPLACE -- Deletes the issuing command, effectively replacing it with the bot's response.
        Configuration:
            extra -- Number of seconds before issuing command is deleted. Defaults to 0.
    ACTIVE -- The message reference is passed back to the plugin for processing.
        Configuration:
            extra_function -- The function to be called after the message is sent.
                The function signature must be: (bot, context, response)
                Arguments:
                    bot -- Bot instance
                    context -- bot.Context object
                    response -- commands.Response object
    INTERACTIVE -- Creates a message with clickable reaction buttons.
        Configuration:
            extra -- Dictionary containing fields for additional configuration:
                kwargs -- Keyword arguments used in wait_for:
                    timeout -- Number of seconds until the menu times out. Defaults to 300.
                    check -- Function used to check whether or not a reaction is read.
                buttons -- List of emojis to add as buttons (in order).
                reactionlock -- Reads provided reactions only (no new reactions can be added).
                    Defaults to True.
                userlock -- Whether or not the menu only responds to the command author.
                    Bot moderators bypass this. Defaults to True.
                elevation -- commands.Elevation value. Defaults to subcommand elevation.
            extra_function -- The function to be called on reaction button press.
                The function signature must be: (bot, context, response, result, timed_out)
                Arguments:
                    bot -- Bot instance
                    context -- bot.Context object
                    response -- commands.Response object
                    result -- (emoji, user) tuple
                    timed_out -- Whether or not the menu timed out
    WAIT -- Waits for events to happen.
        Configuration:
            extra -- Dictionary containing fields for additional configuration:
                kwargs -- Keyword arguments used in wait_for. These two should be defined:
                    timeout -- Number of seconds until the response times out. Defaults to 300.
                    check -- Function that checks the validity of the event.
                event -- Event to wait for.
            extra_function -- The function to be called when the event is triggered.
                The function signature must be: (bot, context, response, result)
                Arguments:
                    bot -- Bot instance
                    context -- bot.Context object
                    response -- commands.Response object
                    result -- The result of wait_for
    """
    NORMAL, PERMANENT, REPLACE, ACTIVE, INTERACTIVE, WAIT = range(6)

class Elevation(IntEnum):
    """Basic permission elevation levels."""
    ALL, BOT_MODERATORS, GUILD_OWNERS, BOT_OWNERS = range(4)

from jshbot import parser, utilities, data
from jshbot.exceptions import BotException, ConfiguredBotException, ErrorTypes

CBException = ConfiguredBotException('Commands')

ELEVATION = [
    "all users",
    "bot moderators",
    "the server owner",
    "the bot owners"
]


class Response():
    def __init__(
            self, content=None, tts=False, message_type=MessageTypes.NORMAL, extra=None,
            embed=None, file=None, files=None, delete_after=None, nonce=None,
            extra_function=None, destination=None, **kwargs):
        """
        Keyword arguments:
        message_type -- One of the MessageTypes available. See core for more.
        extra -- Used depending on the given message_type
        extra_function -- Used depending on the given message_type
        destination -- If set, the bot sends to the destination instead of replying
        """
        # The following may be overwritten after the response object is passed
        #   back to a plugin via a special message type.
        self.content = content
        self.tts = tts
        self.message_type = message_type
        self.extra = extra
        self.embed = embed
        self.file = file
        self.files = files
        self.delete_after = delete_after
        self.nonce = nonce
        self.extra_function = extra_function
        self.destination = destination

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.message = None  # Set by the core

    def __repr__(self):
        result = ''
        if self.content:
            result = self.content
        if self.embed:
            if self.content:
                result += '\n\nEmbed:\n'
            result += pformat(self.embed.to_dict())
        return result

    def __bool__(self):
        return not self.is_empty()

    def get_send_kwargs(self, use_edit_kwargs):
        if use_edit_kwargs:
            keywords = ['content', 'embed']
        else:
            keywords = ['content', 'tts', 'embed', 'file', 'files', 'delete_after', 'nonce']
        return dict((it, getattr(self, it)) for it in keywords)

    def is_empty(self):
        return not (self.content or self.embed)


class SubCommand():
    def __init__(
            self, *optargs, doc=None, confidence_threshold=None,
            function=None, elevated_level=None, allow_direct=None,
            strict_syntax=None, no_selfbot=None, pre_check=None, id=None):
        """
        Arguments:
        optargs -- Composed of a sequence of Opt and Arg objects.
            The last element can be an Attachment.

        Keyword arguments:
        doc -- The help string used whenever detailed help is requested.
        confidence_threshold -- Matching threshold for command match.
            If the best candidate match out of all subcommands has a match value equal
            to or greater than the confidence threshold, then this subcommand will be
            skipped, even if this subcommand is a valid match.

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
        self.confidence_threshold = confidence_threshold
        self.function = function
        self.elevated_level = elevated_level
        self.allow_direct = allow_direct
        self.strict_syntax = strict_syntax
        self.no_selfbot = no_selfbot
        self.pre_check = pre_check
        self.help_embed_fields = []
        self.short_help_embed_fields = []
        self.keywords = []
        self.command = None  # Set by Command in init
        self.index = None  # Set by Command in init
        self.id = id  # Used as an internal alternative to index
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
        short_help_lines = []
        clean_help_lines = []
        parameter_lines = []
        clean_parameter_lines = []
        groups = {}

        for index, optarg in enumerate(self.optargs):
            help_lines.append(optarg.help_string)
            clean_help_lines.append(optarg.clean_help_string)
            if optarg.doc_string:
                parameter_lines.append(optarg.doc_string)
                clean_parameter_lines.append(optarg.clean_doc_string)
            if optarg.group is None:
                short_help_lines.append(optarg.help_string)
            else:  # Group together options/arguments
                if optarg.group not in groups:
                    groups[optarg.group] = [optarg.optional, len(short_help_lines)]
                    wrap = '_' if optarg.optional else '**'
                    short_help_lines.append('{0}`[{1}]`{0}'.format(wrap, optarg.group))
                elif not optarg.optional and groups[optarg.group][0]:
                    group_data = groups[optarg.group]
                    group_data[0] = False
                    short_help_lines[group_data[1]] = '**`[{}]`**'.format(optarg.group)

        # TODO: Consider switching help_string and quick_help? Consistency issue
        if help_lines:
            self.help_string = '**`{base}`**`\u200b　\u200b`{help_string}'.format(
                base=self.command.base, help_string='`\u200b　\u200b`'.join(help_lines))
            self.short_help_string = '**`{base}`**`\u200b　\u200b`{help_string}'.format(
                base=self.command.base, help_string='`\u200b　\u200b`'.join(short_help_lines))
            self.clean_help_string = '{base}    {help_string}'.format(
                base=self.command.base, help_string='    '.join(clean_help_lines))
        else:
            self.help_string = '**`{base}`**'.format(base=self.command.base)
            self.short_help_string = '**`{base}`**'.format(base=self.command.base)
            self.clean_help_string = '{base}'.format(base=self.command.base)
        self.parameter_string = '\n'.join(parameter_lines)
        self.clean_parameter_string = '\n'.join(clean_parameter_lines)

        self.quick_help = ''
        self.clean_quick_help = ''
        if self.doc:
            self.quick_help += self.doc + '\n\n'
            self.clean_quick_help += self.doc + '\n\n'
            self.help_embed_fields.append(('Description:', self.doc))
            self.short_help_embed_fields.append(('Description:', self.doc))
        self.quick_help += self.help_string
        self.clean_quick_help += self.clean_help_string
        self.help_embed_fields.append(('Usage:', self.help_string))
        self.short_help_embed_fields.append(('Usage:', self.short_help_string))
        if self.parameter_string:
            self.quick_help += '\n' + self.parameter_string
            self.clean_quick_help += '\n' + self.clean_parameter_string
            self.help_embed_fields.append(('Parameter details:', self.parameter_string))
            self.short_help_embed_fields.append(('Parameter details:', self.parameter_string))

        # Privilege warning
        if self.elevated_level != Elevation.ALL:
            elevation_string = 'This subcommand can only be used by {}.'.format(
                ELEVATION[self.elevated_level])
            self.quick_help += '\n\n**Privilege**:\n{}'.format(elevation_string)
            self.clean_quick_help += '\n\nPrivilege:\n{}'.format(elevation_string)
            self.help_embed_fields.append(('Privilege:', elevation_string))
            self.short_help_embed_fields.append(('Privilege:', elevation_string))

    def __repr__(self):
        if hasattr(self, 'clean_help_string'):
            return "<SubCommand '{}'>".format(self.clean_help_string)
        else:
            return "<Uninitialized SubCommand {}>".format(id(self))


class Command():
    def __init__(
            self, base, subcommands=[], description='', other='',
            category='miscellaneous', shortcuts=[], function=None, hidden=False, elevated_level=0,
            allow_direct=True, strict_syntax=False, no_selfbot=False, pre_check=None):
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
        elevated_level -- commands.Elevation value. Limits usage to a certain permission level.
        allow_direct -- Allows the command to be used in direct messages.
        strict_syntax -- Parameter order is strictly maintained.
        no_selfbot -- Disallows the command to be used in selfbot mode.
        pre_check -- An async function called with (bot, context) params before the execution.
        """
        self.base = base.lower().strip()
        if not subcommands:
            self.subcommands = [SubCommand()]
        else:
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
        self.pre_check = pre_check
        self.help_embed_fields = []
        self.plugin = None  # Assigned later on

        # 1 - bot moderators, 2 - guild owners, 3 - bot owners
        self.elevated_level = elevated_level

        # Generate help string and keywords and
        #   replace subcommand properties with configured values
        replacements = [
            'function', 'elevated_level', 'allow_direct',
            'strict_syntax', 'no_selfbot', 'pre_check']
        self.help_lines = []
        self.clean_help_lines = []
        self.keywords = []
        for index, subcommand in enumerate(self.subcommands):
            subcommand.index = index
            subcommand.command = self
            for replacement in replacements:
                if getattr(subcommand, replacement) is None:
                    setattr(subcommand, replacement, getattr(self, replacement))
            subcommand._build_help_string()
            self.help_lines.append(subcommand.short_help_string)
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

        # Privilege warning
        if self.elevated_level != Elevation.ALL:
            elevation_string = 'These commands can only be used by {}.'.format(
                ELEVATION[self.elevated_level])
            self.help_string += '\n\n**Privilege**:\n{}'.format(elevation_string)
            self.clean_help_string += '\n\nPrivilege:\n{}'.format(elevation_string)
            self.help_embed_fields.append(('Privilege:', elevation_string))

    def __repr__(self):
        return "<Command '{}'>".format(self.base)

    def __lt__(self, other):
        return self.base < other.base


class Opt():
    def __init__(
            self, name, optional=False, attached=None, doc=None, quotes_recommended=True,
            convert=None, check=None, convert_error=None, check_error=None, default=None,
            always_include=False, group=None):
        """
        Keyword arguments:
        optional -- Whether or not this option is optional.
        attached -- The name of the required user value as the attached parameter.
        doc -- Additional help string for the given option.
        convert -- Function or class to use to convert the value.
        check -- Function to check the (converted) value. Passed in: context, value
        convert_error -- Error message upon conversion failure.
        check_error -- Error message upon check failure.
        always_include -- Always add to options dictionary, even if not given.
        default -- Default value to use if always_include is used.
        group -- Groups common options together to simplify the help entry.
        """
        self.name = name.strip()
        self.optional = optional
        self.attached = attached
        self.check = check
        self.doc = doc
        self.quotes_recommended = quotes_recommended
        self.default = default
        self.always_include = always_include if always_include else default is not None
        self.group = group
        self.subcommand = None  # Set by Subcommand in init

        self._build_help_string()

        if convert is int:
            convert = lambda b, m, v, *a: int(v)
            if not convert_error:
                convert_error = 'Must be an integer number.'
        elif convert is float:
            convert = lambda b, m, v, *a: float(v)
            if not convert_error:
                convert_error = 'Must be a decimal number.'
        self.convert = convert
        self.set_convert_error = convert_error or ''
        self.convert_error = 'Invalid value type for {name}: {error}'.format(
            name=self.help_string, error=self.set_convert_error)
        self.set_check_error = check_error or ''
        self.check_error = 'Invalid value for {name}: {error}'.format(
            name=self.attached_string if self.attached else self.help_string,
            error=self.set_check_error)

    def _build_help_string(self):
        quotes = '"' if self.quotes_recommended else ''
        wrap = '_' if self.optional else '**'
        clean_wrap = ['[', ']'] if self.optional else ['', '']
        current = '{wrap}`{name}'.format(wrap=wrap, name=self.name)
        clean_current = '{wrap[0]}{name}'.format(wrap=clean_wrap, name=self.name)
        self.name_string = current + '`{}'.format(wrap)
        if self.attached:
            attached_current = '__`{quotes}{attached}{quotes}`__'.format(
                quotes=quotes, attached=self.attached)
            current += '\u2009\u200b`{}'.format(attached_current)
            clean_current += '  <{quotes}{attached}{quotes}>'.format(
                quotes=quotes, attached=self.attached)
            self.attached_string = '{wrap}{current}{wrap}'.format(
                wrap=wrap, current=attached_current)
        else:
            current += '`'
            self.attached_string = ''
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

    async def convert_and_check(self, bot, message, value):
        if self.convert:
            use_await = inspect.iscoroutinefunction(self.convert.__call__)
            try:
                if isinstance(value, list):  # for split arguments
                    new_values = []
                    if use_await:
                        for entry in value:
                            new_values.append(await self.convert(bot, message, entry))
                    else:
                        for entry in value:
                            new_values.append(self.convert(bot, message, entry))
                    value = new_values
                else:
                    if use_await:
                        value = await self.convert(bot, message, value)
                    else:
                        value = self.convert(bot, message, value)
            except Exception as e:
                if isinstance(e, BotException):
                    if getattr(self.convert, 'propagate_error', False):
                        raise e
                    convert_error = 'Invalid value type for {name}: {error}'.format(
                        name=self.help_string, error=e.error_details)
                elif hasattr(self.convert, 'get_convert_error'):
                    convert_error = self.convert.get_convert_error(bot, message, value)
                elif not self.set_convert_error:
                    raise e
                else:
                    convert_error = self.convert_error
                raise BotException(
                    'Parser', convert_error, embed_fields=self.subcommand.help_embed_fields)
        if self.check:
            use_await = inspect.iscoroutinefunction(self.check.__call__)
            try:
                if isinstance(value, list):
                    if use_await:
                        for entry in value:
                            assert await self.check(bot, message, entry)
                    else:
                        for entry in value:
                            assert self.check(bot, message, entry)
                else:
                    if use_await:
                        assert await self.check(bot, message, value)
                    else:
                        assert self.check(bot, message, value)
            except Exception as e:
                if isinstance(e, BotException):
                    if getattr(self.check, 'propagate_error', False):
                        raise e
                    check_error = 'Invalid value for {name}: {error}'.format(
                        name=self.attached_string if self.attached else self.help_string,
                        error=e.error_details)
                elif hasattr(self.check, 'get_check_error'):
                    check_error = self.check.get_check_error(bot, message, value)
                elif not self.set_check_error:
                    raise e
                else:
                    check_error = self.check_error
                raise BotException(
                    'Parser', check_error, embed_fields=self.subcommand.help_embed_fields)
        return value


class Arg(Opt):
    def __init__(
            self, name, argtype=ArgTypes.SINGLE, additional=None, doc=None,
            convert=None, check=None, convert_error=None, check_error=None,
            quotes_recommended=True, default=None, group=None):
        """
        Keyword Arguments:
        additional -- Used for split arguments. Name of the extra component.
        quotes_recommended -- Whether or not to wrap the argument in quotes in the help menu.
        """
        self.argtype = argtype
        self.additional = additional
        super().__init__(
            name, convert=convert, check=check, doc=doc, quotes_recommended=quotes_recommended,
            convert_error=convert_error, check_error=check_error, default=default, group=group)

    def _build_help_string(self):
        if self.argtype in (ArgTypes.SPLIT, ArgTypes.MERGED, ArgTypes.SINGLE):
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
        if self.argtype in (ArgTypes.SPLIT, ArgTypes.SPLIT_OPTIONAL):
            if self.additional:
                current += '`\u200b　\u200b`___`{quotes}{additional}{quotes} ...`___'.format(
                    quotes=quotes, wrap=wrap, additional=self.additional)
                clean_current += (
                    '    {wrap[0]}<{additional}>{wrap[1]} {wrap[0]}...{wrap[1]}'.format(
                        wrap=clean_wrap, additional=self.additional))
            else:
                current += '`\u200b　\u200b`___`{quotes}...{quotes}`___'.format(
                    quotes=quotes, wrap=wrap)
                clean_current += '    {wrap[0]}...{wrap[1]}'.format(
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
        self.group = None
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
        return "<Shortcut '{}'>".format(self.base)

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


async def execute(bot, context):
    """Calls get_response of the given plugin associated with the base."""
    subcommand = context.subcommand
    elevation, level = context.elevation, subcommand.elevated_level

    # TODO: Move preliminary checks to the core

    if bot.selfbot and subcommand.no_selfbot:
        raise CBException("This command cannot be used in selfbot mode.")

    if elevation < Elevation.BOT_OWNERS and subcommand.command.base in bot.locked_commands:
        raise CBException("This command is locked by the bot owner.")

    if isinstance(context.message.channel, PrivateChannel):
        if not subcommand.allow_direct:
            raise CBException("This command cannot be used in a direct message.")
        elif Elevation.ALL < level < Elevation.BOT_OWNERS:
            raise CBException("Special permissions commands cannot be used in direct messages.")
        disabled_commands = []
    else:
        disabled_commands = data.get(
            bot, 'core', 'disabled', guild_id=context.guild.id, default=[])

    if level > Elevation.ALL:
        if level == Elevation.BOT_MODERATORS and elevation < Elevation.BOT_MODERATORS:
            raise CBException("Only bot moderators can use this command.")
        elif level == Elevation.GUILD_OWNERS and elevation < Elevation.GUILD_OWNERS:
            raise CBException("Only the server owner can use this command.")
        elif level >= Elevation.BOT_OWNERS and elevation < Elevation.BOT_OWNERS:
            raise CBException("Only the bot owner(s) can use this command.")

    for disabled_base, disabled_index in disabled_commands:
        if (subcommand.command.base == disabled_base and
                disabled_index in (-1, subcommand.index) and
                elevation < Elevation.BOT_MODERATORS):
            raise CBException("This command is disabled on this server.")

    if subcommand.pre_check:
        await subcommand.pre_check(bot, context)

    if subcommand.function:
        given_function = subcommand.function
    else:
        if hasattr(subcommand.command.plugin, 'get_response'):
            given_function = subcommand.command.plugin.get_response
        else:
            return
    return await given_function(bot, context)
