import asyncio
import copy
import yaml
import importlib.util
import os.path
import sys

# Debug
import traceback

from collections import OrderedDict

from jshbot import commands, utilities, data, logger
from jshbot.exceptions import ErrorTypes, BotException, ConfiguredBotException

CBException = ConfiguredBotException('Plugins')
command_spawner_functions = []
db_template_functions = []
command_load_functions = []

numeric_words = [
    ':zero:', ':one:', ':two:', ':three:', ':four:',
    ':five:', ':six:', ':seven:', ':eight:', ':nine:', ':ten:']


def command_spawner(function):
    command_spawner_functions.append(function)
    return function


def db_template_spawner(function):
    db_template_functions.append(function)
    return function


def on_load(function):
    command_load_functions.append(function)
    return function


def load_plugin(bot, plugin_name):
    directory = '{}/plugins'.format(bot.path)
    if plugin_name == 'base':
        raise CBException("Cannot (re)load base plugin.")

    if plugin_name in bot.plugins:
        logger.debug("Reloading plugin {}...".format(plugin_name))
        module = bot.plugins.pop(plugin_name)
        # importlib.reload(module)
        to_remove = []
        for base, command in bot.commands.items():
            if command.plugin is module:
                to_remove.append(base)
        for base in to_remove:
            del bot.commands[base]
        del module
    else:
        logger.debug("Loading plugin {}...".format(plugin_name))

    try:
        spec = importlib.util.spec_from_file_location(
            plugin_name, '{}/{}'.format(directory, plugin_name))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        raise CBException("Failed to import external plugin.", plugin_name, e=e)
    else:
        bot.plugins[plugin_name] = module

    if plugin_name.lower().endswith('.py'):
        clean_name = plugin_name[:-3]
    else:
        clean_name = plugin_name

    add_configuration(bot, clean_name, plugin_name, module)
    add_manual(bot, clean_name, plugin_name)

    try:
        while command_spawner_functions:
            function = command_spawner_functions.pop()
            add_commands(bot, function(bot), module)
        while db_template_functions:
            function = db_template_functions.pop()
            template = function(bot)
            for name, value in template.items():
                data.db_add_template(bot, name, value)
        while command_load_functions:
            function = command_load_functions.pop()
            function(bot)
    except Exception as e:
        raise CBException("Failed to initialize external plugin.", plugin_name, e=e)
    logger.debug("Plugin {} loaded.".format(plugin_name))


def add_plugins(bot):
    """
    Gets a list of all of the plugins and stores them as a key/value pair of
    the plugin name and the module itself (renamed to plugin for the user).
    In addition, this also sets the commands given by each plugin.
    """
    directory = '{}/plugins'.format(bot.path)
    data_directory = '{}/plugins/plugin_data'.format(bot.path)
    if os.path.isdir(data_directory):
        logger.debug("Setting plugin_data as plugin import path.")
        sys.path.append(data_directory)
    try:
        plugins_list = os.listdir(directory)
    except FileNotFoundError:
        raise CBException("Plugins directory not found", error_type=ErrorTypes.STARTUP)

    # Add base plugin
    # Order is always add: plugin, configuration, manual, commands
    from jshbot import base
    bot.plugins['core'] = base
    add_manual(bot, 'core', 'core')
    while command_spawner_functions:
        function = command_spawner_functions.pop()
        add_commands(bot, function(bot), base)
    while db_template_functions:
        function = db_template_functions.pop()
        template = function(bot)
        for name, value in template.items():
            data.db_add_template(bot, name, value)
    while command_load_functions:
        function = command_load_functions.pop()
        function(bot)

    # Add plugins in plugin folder
    for plugin_name in plugins_list:
        if (plugin_name[0] in ('.', '_') or
                plugin_name == 'base' or
                not plugin_name.endswith('.py')):
            continue
        try:
            load_plugin(bot, plugin_name)
        except Exception as e:
            raise CBException(
                "Failed to import external plugin on startup.", e=e, error_type=ErrorTypes.STARTUP)

    if len(bot.plugins) - 1:
        logger.debug("Loaded {} plugin(s)".format(len(bot.plugins) - 1))


def add_commands(bot, new_commands, plugin):
    """Adds the given commands the bot's command dictionary.

    Checks that all keys in the new dictionary are unique from those in the old
    dictionary. If all keys are good, add them to the bot commands dictionary.
    """

    # Just a quick duplicate checker
    def check_and_add(dictionary, key, value):
        if key in dictionary:
            raise CBException(
                "Attempting to add a command that already exists.",
                key, error_type=ErrorTypes.FATAL)
        dictionary[key] = value

    for command in new_commands:
        command.plugin = plugin
        if command.shortcuts:
            for shortcut in command.shortcuts:
                shortcut.plugin = plugin
                check_and_add(bot.commands, shortcut.base, shortcut)
        check_and_add(bot.commands, command.base, command)


def add_configuration(bot, clean_name, plugin_name, plugin):
    directory = '{}/config/'.format(bot.path)
    try:
        with open(directory + clean_name + '-config.yaml', 'rb') as config_file:
            bot.configurations[plugin_name] = yaml.load(config_file)
    except FileNotFoundError:
        if getattr(plugin, 'uses_configuration', False):
            raise CBException(
                "{} requires a configuration file, but it was not found.".format(plugin_name),
                error_type=ErrorTypes.FATAL)
    except Exception as e:
        raise CBException(
            "Could not open the {} configuration file.".format(plugin_name), e=e,
            error_type=ErrorTypes.FATAL)


def add_manual(bot, clean_name, plugin_name):
    """Reads all manuals in the config folder and adds them to the bot."""
    directory = bot.path + '/config/'
    try:
        with open(directory + clean_name + '-manual.yaml', 'rb') as manual_file:
            raw_manual = yaml.load(manual_file)
    except FileNotFoundError:
        logger.debug("No manual found for {}.".format(plugin_name))
        return
    except yaml.YAMLError as e:  # TODO: Change
        raise CBException("Failed to parse the manual for {}.".format(plugin_name), e=e)
    try:
        for subject, topics in raw_manual.items():
            assert len(topics)
            for topic_group in topics:
                assert len(topic_group) >= 2
            bot.manuals.update({subject.lower(): {'subject': subject, 'topics': topics}})
    except:
        raise CBException("Manual for {} is improperly structured.".format(plugin_name))


def get_help(
        bot, category_id=None, command_index=None, subcommand_index=None,
        page=None, guild=None, safe=True, using_menu=True, elevation=0):
    """
    Gets the help entry depending on depth. Help me.
    """
    MAX_E = 5
    invoker = utilities.get_invoker(bot, guild=guild)
    base_invoker = utilities.get_invoker(bot)
    crumbs = 'Help menu'
    if page is None:
        page = 0

    categories = OrderedDict([('Core', [])])
    for command in bot.commands.values():
        if isinstance(command, commands.Command):
            if not command.hidden or elevation >= 3:
                if command.category in categories:
                    categories[command.category].append(command)
                else:
                    categories[command.category] = [command]
    categories = OrderedDict(sorted(list(categories.items())))

    if category_id is not None:  # Category selected; browsing commands listing
        try:
            category_index = int(category_id)
            assert category_index >= 0  # TODO: Better checking
        except ValueError:  # Category text given
            category_name = subject_id.title()
            if category_name not in categories:
                if safe:
                    return
                raise CBException("Invalid category")
            commands_listing = sorted(categories[category_name])
        else:
            categories_listing = list(categories.values())
            try:
                commands_listing = sorted(categories_listing[category_index])
            except:
                if safe:
                    return
                raise CBException(
                    "Invalid category index. Must be between 1 and {}".format(
                        len(categories_listing)))
            category_name = list(categories)[category_index]
        crumbs += '\t→\t{}'.format(category_name)

        if command_index is not None:  # Command selected; browsing subcommands
            try:
                command = commands_listing[command_index]
            except:
                if safe:
                    return
                raise CBException(
                    "Invalid command index. Must be between 1 and {}.".format(
                        len(commands_listing)))
            crumbs += '\t→\t{}'.format(command.base)
            subcommands = command.subcommands

            if subcommand_index is not None:  # Subcommand selected; browsing detailed help
                try:
                    subcommand = subcommands[subcommand_index]
                except:
                    if safe:
                        return
                    raise CBException(
                        "Invalid subcommand index. Must be between 1 and {}.".format(
                            len(subcommands)))
                crumbs += '\t→\tSubcommand {}'.format(subcommand.index + 1)
                if using_menu:  # Add crumbs
                    embed_fields = [(crumbs, '\u200b')] + subcommand.help_embed_fields
                else:
                    embed_fields = subcommand.help_embed_fields
                return embed_fields, 0, 0

            else:  # No subcommand selected; browsing command still
                total_pages = int((len(command.help_lines)-1) / MAX_E)
                if not 0 <= page <= total_pages:
                    if safe:
                        return
                    raise CBException(
                            "Invalid subcommand page. Must be between 1 and {}".format(
                                total_pages+1))
                if using_menu:  # Add numbers
                    help_lines = command.help_lines[page*MAX_E:(page + 1)*MAX_E]
                    raw_list = []
                    for index, entry in enumerate(help_lines):
                        raw_list.append('{} {}'.format(numeric_words[index + 1], entry))
                    embed_fields = [(crumbs, '\u200b')] + command.help_embed_fields
                    embed_fields[command.usage_embed_index + 1] = ('Usage:', '\n'.join(raw_list))
                else:
                    embed_fields = command.help_embed_fields
                return embed_fields, page, total_pages

        else:  # No command selected; browsing commands listing still
            total_pages = int((len(commands_listing)-1) / MAX_E)
            if not 0 <= page <= total_pages:
                if safe:
                    return
                raise CBException(
                    "Invalid command page. Must be between 1 and {}".format(total_pages+1))
            commands_listing = commands_listing[page*MAX_E:(page + 1)*MAX_E]
            raw_list = []
            for index, command in enumerate(commands_listing):
                raw_list.append('{} **`{}`** -- {}'.format(
                    numeric_words[index + 1], command.base, command.description))
            embed_fields = [(crumbs, '\n'.join(raw_list))]
            return embed_fields, page, total_pages

    else:  # Nothing selected. Get category listing
        total_pages = int((len(categories)-1) / MAX_E)
        if not 0 <= page <= total_pages:
            if safe:
                return
            raise CBException(
                "Invalid category page. Must be between 1 and {}".format(total_pages+1))
        category_pairs = list(categories.items())[page*MAX_E:(page + 1)*MAX_E]
        raw_list = []
        for index, category_pair in enumerate(category_pairs):
            category_name, category_commands = category_pair
            peek_commands = [command.base for command in category_commands[:3]]
            if len(category_commands) > 3:
                peek_commands.append('...')
            peek = '[`{}`]'.format('`, `'.join(peek_commands))
            raw_list.append('{} **{}**\n\t\t{}'.format(
                numeric_words[index + 1], category_name, peek))
        embed_fields = [(crumbs, '\n'.join(raw_list))]
        return embed_fields, page, total_pages

    pass


def get_manual(bot, subject_id=None, topic_index=None, page=None, guild=None, safe=True):
    """
    Gets the given manual entry depending on depth.

    If subject is not provided: returns a tuple: ('Manual menu', subject_listing)
    If subject is provided: return a tuple: (subject_name, topic_listing)
    If topic is provivded: return a tuple: (topic_name, text)
    All return values also include (1 indexed): (page_number, total_pages, crumbs)
    These return values are to be used as embed fields.
    """
    MAX_E = 5
    invoker = utilities.get_invoker(bot, guild=guild)
    base_invoker = utilities.get_invoker(bot)
    crumbs = 'Manual menu'
    if page is None:
        page = 0

    subjects = list(bot.manuals.values())

    if subject_id is not None:  # Subject selected; browsing topics
        try:
            subject_index = int(subject_id)
            assert subject_index >= 0  # TODO: Better checking
        except ValueError:  # Subject text given
            subject_name = subject_id.lower()
            if subject_name not in bot.manuals:
                if safe:
                    return
                raise CBException("Invalid subject.")
            subject = bot.manuals[subject_name]
        else:  # Subject index given
            try:
                subject = subjects[subject_index]
            except IndexError:
                if safe:
                    return
                raise CBException(
                    "Invalid subject index. Must be between 1 and {}.".format(len(bot.manuals)))
        topics = subject['topics']
        crumbs += '\t→\t{}'.format(subject['subject'])

        if topic_index is not None:  # Topic selected; browsing text pages
            try:
                topic = topics[topic_index]
            except:
                if safe:
                    return
                raise CBException(
                    "Invalid topic index. Must be between 1 and {}.".format(len(topics)))
            if not 0 <= page < len(topic[1]):
                if safe:
                    return
                raise CBException(
                    "Invalid page number. Must be between 1 and {}.".format(len(topic[1])))
            text = topic[1][page].format(invoker=invoker, base_invoker=base_invoker)
            crumbs += '\t→\t{}'.format(topic[0])
            return crumbs, text, page, len(topic[1]) - 1

        else:  # Subject selected; browsing topics
            total_topic_pages = int((len(topics)-1) / MAX_E)
            if not 0 <= page <= total_topic_pages:
                if safe:
                    return
                raise CBException(
                    "Invalid topic page number. Must be between 1 and {}.".format(total_topic_pages+1))
            topics = topics[page*MAX_E:(page + 1)*MAX_E]
            raw_list = []
            for index, topic in enumerate(topics):
                raw_list.append('{} {}'.format(numeric_words[index + 1], topic[0]))
            topic_listing = '\n'.join(raw_list)
            return crumbs, topic_listing, page, total_topic_pages

    else:  # No subject_id given; get general subject listing
        total_subject_pages = int((len(subjects)-1) / MAX_E)
        if not 0 <= page <= total_subject_pages:
            if safe:
                return
            raise CBException(
                "Invalid subject page. Must be between 1 and {}.".format(total_subject_pages+1))
        subjects = subjects[page*MAX_E:(page + 1)*MAX_E]
        raw_list = []
        for index, subject_pair in enumerate(subjects):
            raw_list.append('{} {}'.format(numeric_words[index + 1], subject_pair['subject']))
        subject_listing = '\n'.join(raw_list)
        return crumbs, subject_listing, page, total_subject_pages


def broadcast_event(bot, event, *args, **kwargs):
    """
    Loops through all of the plugins and looks to see if the event index
    specified is associated it. If it is, call that function with args.
    """
    for plugin in bot.plugins.values():
        function = getattr(plugin, event, None)
        if function:
            try:
                asyncio.ensure_future(function(bot, *args, **kwargs))
            except TypeError as e:
                logger.error("Bypassing event error: %s", e)
                logger.error(traceback.format_exc())
