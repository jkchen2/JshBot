import asyncio
import logging
import os.path
import importlib.util

# Debug
import traceback

from jshbot import commands
from jshbot.exceptions import ErrorTypes, BotException

EXCEPTION = 'Plugins'


def add_plugins(bot, purge_commands=False):
    """
    Gets a list of all of the plugins and stores them as a key/value pair of
    the plugin name and the module itself (renamed to plugin for the user).
    In addition, this also sets the commands given by each plugin.
    If purge_commands is set to True, this wipes the existing commands.
    """
    if purge_commands:
        bot.commands = {}
        bot.manual = {}
    directory = '{}/plugins'.format(bot.path)
    try:
        plugins_list = os.listdir(directory)
    except FileNotFoundError:
        raise BotException(
            EXCEPTION, "Plugins directory not found",
            error_type=ErrorTypes.STARTUP)
    valid_plugins = {}

    # Add base plugin
    from jshbot import base
    plugin_commands = base.get_commands()
    commands.add_commands(bot, plugin_commands, base)
    valid_plugins['base'] = [base, plugin_commands]

    # Get plugin commands
    for plugin in plugins_list:
        if (plugin[0] in ('.', '_') or
                plugin == 'base' or
                not plugin.endswith('.py')):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                plugin, '{}/{}'.format(directory, plugin))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin_commands = module.get_commands()
            commands.add_commands(bot, plugin_commands, module)
        except Exception as e:
            traceback.print_exc()
            raise BotException(
                EXCEPTION, "Failed to import external plugin",
                plugin, e=e, error_type=ErrorTypes.STARTUP)
        else:
            logging.debug("Adding plugin {}".format(plugin))
            valid_plugins[plugin] = [module, plugin_commands]

    # Get functions to broadcast
    events = [
        'on_ready', 'on_error', 'on_message', 'on_socket_raw_receive',
        'on_socket_raw_send', 'on_message_delete', 'on_message_edit',
        'on_channel_delete', 'on_channel_create', 'on_channel_update',
        'on_member_join', 'on_member_update', 'on_server_join',
        'on_server_remove', 'on_server_update', 'on_server_role_create',
        'on_server_role_delete', 'on_server_role_update',
        'on_server_available', 'on_server_unavailable',
        'on_voice_state_update', 'on_member_ban', 'on_member_unban',
        'on_typing'
    ]
    for plugin_name, plugin in valid_plugins.items():
        functions = []
        for event in events:
            functions.append(getattr(plugin[0], event, None))
        valid_plugins[plugin_name].append(functions)

    if len(valid_plugins):
        logging.debug("Loaded {} plugin(s)".format(len(valid_plugins)))

    bot.plugins = valid_plugins


def broadcast_event(bot, event_index, *args):
    """
    Loops through all of the plugins and looks to see if the event index
    specified is associated it. If it is, call that function with args.
    """
    for plugin in bot.plugins.values():
        function = plugin[2][event_index]
        if function:
            asyncio.ensure_future(function(bot, *args))
