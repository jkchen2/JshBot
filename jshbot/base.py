import asyncio
import random
import socket
import time
import logging
import inspect
import traceback

from jshbot import data, utilities, commands
from jshbot.commands import Command, SubCommands, Shortcuts
from jshbot.exceptions import BotException

__version__ = '0.1.6'
EXCEPTION = 'Base'
uses_configuration = False
local_dictionary = {}


def get_commands():
    """Sets up new commands and shortcuts in the proper syntax.

    See dummy.py for a complete sample reference.
    """
    new_commands = []

    new_commands.append(Command(
        'ping', SubCommands(('&', '(message)', '')),
        description='Pings the bot for a response'))

    new_commands.append(Command(
        'base', SubCommands(
            ('version', 'version', 'Gets the version of the bot.'),
            ('source', 'source', 'Gets the source of the bot.'),
            ('uptime', 'uptime', 'Gets the uptime of the bot.'),
            ('help: &', '<command> (<topic>)', 'Gets the help of the given '
             'command. If a topic index is provided, it will get specific '
             'help regarding that command.'),
            ('help', 'help', 'Gets the general help text. This will list all '
             'available help commands to you.'),
            ('announcement', 'announcement', 'Gets the current announcement '
             'set by the bot owners.'),
            ('join', 'join', 'Joins the voice channel you are in.'),
            ('leave', 'leave', 'Leaves the voice channel you are in.')),
        shortcuts=Shortcuts(
            ('help', 'help {}', '&', 'help <arguments>', '<arguments>'),
            ('announcement', 'announcement', '', 'announcement', ''),
            ('join', 'join', '', 'join', ''),
            ('leave', 'leave', '', 'leave', ''),
            ('stfu', 'leave', '', 'leave', '')),
        description='Essential bot commands that anybody can use.'))

    new_commands.append(Command(
        'mod', SubCommands(
            ('info', 'info', 'Gets server information.'),
            ('block ^', 'block <user>', 'Blocks the user from interacting '
             'with the bot.'),
            ('unblock ^', 'unblock <user>', 'Unblocks the user from '
             'interacting with the bot.'),
            ('clear', 'clear', 'Pushes chat upwards.'),
            ('add ^', 'add <user>', 'Adds the user to the moderators list. '
             'This command is for server owners only.'),
            ('remove ^', 'remove <user>', 'Removes the user from the '
             'moderators list. This command is for server owners only.'),
            ('mute &', 'mute (<channel>)', 'Mutes the given channel. If no '
             'channel is specified, this mutes the bot for the server.'),
            ('unmute ^', 'unmute (<channel>)', 'Unmutes the given channel. If '
             'no channel is specified, this unmutes the bot for the server.'),
            ('invoker &', 'invoker (<custom invoker>)', 'Sets the custom '
             'invoker for the server. If no invoker is specified, this clears '
             'the custom invoker.'),
            ('mention', 'mention', 'Toggles mention mode. If enabled, the '
             'bot will only respond to its name or mention as an invoker.')),
        shortcuts=Shortcuts(('clear', 'clear', '', 'clear', '')),
        description='Commands for server bot moderators.',
        elevated_level=1))

    new_commands.append(Command(
        'owner', SubCommands(
            ('halt', 'halt', 'Shuts down the bot.'),
            ('restart', 'restart', 'Restarts the bot.'),
            ('ip', 'ip', 'Gets the local IP address of the bot.'),
            ('backup', 'backup', 'Gets the data folder as a zip file.'),
            ('announcement &', 'announcement (<text>)', 'Sets or clears the '
             'announcement text.')),
        shortcuts=Shortcuts(('restart', 'restart', '', 'restart', '')),
        description='Commands for the bot owner.',
        elevated_level=3))

    new_commands.append(Command(
        'debug', SubCommands(
            ('plugin list', 'plugin list', 'Lists added plugins.'),
            ('plugin:', 'plugin <plugin name>', 'Gets some basic information '
             'about the given plugin.'),
            ('latency', 'latency', 'Calculates the ping time.'),
            ('resetlocals', 'resetlocals', 'Resets the debug locals.'),
            ('^', '<python>', 'Evaluates or executes the given code.')),
        description='Commands to help the bot owner debug stuff.',
        other='Be careful with these commands! They can break the bot.',
        elevated_level=3))

    return new_commands


async def base_wrapper(
        bot, message, direct, blueprint_index, options, arguments):
    response = ''
    message_type = 0

    if blueprint_index == 0:  # version
        response = '`{}`\n{}'.format(bot.version, bot.date)

    elif blueprint_index == 1:  # source
        response += random.choice([
            "It's shit. I'm sorry.",
            "You want to see what the Matrix is like?",
            "Script kiddie level stuff in here.",
            "Beware the lack of PEP 8 guidelines inside!",
            "Snarky comments inside and out.",
            "Years down the road, this will all just be a really "
            "embarrassing but funny joke.",
            "Made with ~~love~~ pure hatred.",
            "At least he's using version control."])
        response += ("\nhttps://github.com/jkchen2/JshBot\n"
                     "https://github.com/jkchen2/JshBot-plugins")

    elif blueprint_index == 2:  # uptime
        uptime_total_seconds = int(time.time()) - bot.time
        uptime_struct = time.gmtime(uptime_total_seconds)
        days = int(uptime_total_seconds / 86400)
        hours = uptime_struct.tm_hour
        minutes = uptime_struct.tm_min
        seconds = uptime_struct.tm_sec
        response = (
            "The bot has been on since **{0}**\n{1} days\n{2} hours\n"
            "{3} minutes\n{4} seconds").format(
                bot.readable_time, days, hours, minutes, seconds)

    elif blueprint_index in (3, 4):  # help, detailed or general
        is_owner = data.is_owner(bot, message.author.id)
        if blueprint_index == 3:  # Detailed
            response = commands.get_help(
                bot, options['help'],
                topic=arguments[0] if arguments[0] else None,
                is_owner=is_owner)
        else:  # General
            response = commands.get_general_help(bot, is_owner=is_owner)
        if not direct:  # Terminal reminder message
            await bot.send_message(message.author, response)
            response = "Check your direct messages!"
            message_type = 2  # Default 10 seconds

    elif blueprint_index == 5:  # Announcement
        announcement = data.get(bot, 'base', 'announcement')
        if not announcement:
            response = "No announcement right now!"
        else:
            response = announcement

    elif blueprint_index in (6, 7):  # Join/leave voice channel
        voice_channel = message.author.voice_channel
        if not voice_channel:
            raise BotException(EXCEPTION, "You are not in a voice channel.")
        try:
            if blueprint_index == 6:
                await utilities.join_and_ready(
                    bot, voice_channel, message.server)
                response = "Joined {}.".format(voice_channel.name)
            else:
                voice_client = bot.voice_client_in(message.server)
                if not voice_client:
                    raise BotException(
                        EXCEPTION, "Bot not connected to a voice channel.")
                elif voice_client.channel != message.author.voice_channel:
                    raise BotException(
                        EXCEPTION, "Bot not connected to your voice channel.")
                else:
                    await voice_client.disconnect()
                    response = "Left {}.".format(voice_channel.name)
        except BotException as e:
            raise e  # Pass up
        except Exception as e:
            action = 'join' if blueprint_index == 6 else 'leave'
            raise BotException(
                EXCEPTION, "Failed to {} the voice channel.".format(action),
                e=e)

    return (response, message_type)


async def mod_wrapper(bot, message, blueprint_index, options, arguments):
    response = ''

    if blueprint_index == 0:  # info
        server_data = data.get(
            bot, 'base', None, server_id=message.server.id, default={})
        response = (
            '```\n'
            'Information for server {0}\n'
            'ID: {0.id}\n'
            'Owner: {0.owner.id}\n'
            'Moderators: {1}\n'
            'Blocked users: {2}\n'
            'Muted: {3}\n'
            'Muted channels: {4}\n'
            'Command invoker: {5}\n'
            'Mention mode: {6}\n```').format(
                message.server,
                server_data.get('moderators', []),
                server_data.get('blocked', []),
                server_data.get('muted', []),
                server_data.get('muted_channels', []),
                server_data.get('command_invoker', None),
                server_data.get('mention_mode', False))

    elif blueprint_index in (1, 2):  # block or unblock
        user = data.get_member(bot, arguments[0], message.server)
        block = blueprint_index == 1
        blocked = data.is_blocked(
            bot, message.server, user.id, strict=True)
        mod = data.is_mod(bot, message.server, user.id)
        if mod:
            raise BotException(
                EXCEPTION, "Cannot block or unblock a moderator.")
        elif block:
            if blocked:
                raise BotException(EXCEPTION, "User is already blocked.")
            else:
                data.list_data_append(
                    bot, 'base', 'blocked', user.id,
                    server_id=message.server.id)
                response = "User is now blocked."
        else:
            if not blocked:
                raise BotException(EXCEPTION, "User is already unblocked.")
            else:
                data.list_data_remove(
                    bot, 'base', 'blocked', user.id,
                    server_id=message.server.id)
                response = "User is now unblocked."

    elif blueprint_index == 3:  # clear
        response = '```\n'
        for i in range(0, 80):
            response += '.\n'
        response += random.choice([
            "Think twice before scrolling up.",
            "clear ver {}".format(bot.version),
            "Can you find the one comma?",
            "Are people watching? If so, best not to scroll up.",
            "Don't worry, just censorship doing its thing.",
            "This is why we can't have nice things.",
            "The only one who can spam is ME.",
            "That made me feel a bit queasy...",
            "We need a better content filter. 18+ checks, maybe?",
            "You ANIMALS. At least I'm not one.",
            "Scroll up if you want to be on a list.",
            "I'll bet the NSA will have a fun time scrolling up.",
            "So much wasted space...",
            "This is pretty annoying, huh? Well TOO BAD.",
            "No time to delete!"])
        response += '```\n'

    elif blueprint_index in (4, 5):  # add or remove moderator
        if not data.is_admin(bot, message.server, message.author.id):
            raise BotException(
                EXCEPTION, "You must be an admin to use these commands.")
        else:
            user_id = data.get_member(
                bot, arguments[0], server=message.server, attribute='id')
            user_is_mod = data.is_mod(
                bot, message.server, user_id, strict=True)
            blocked = data.is_blocked(
                bot, message.server, user_id, strict=True)
            if blocked:
                response = "User is blocked."
            elif blueprint_index == 4:  # add
                if user_is_mod:
                    raise BotException(
                        EXCEPTION, "User is already a moderator.")
                else:
                    data.list_data_append(
                        bot, 'base', 'moderators',
                        user_id, server_id=message.server.id)
                    response = "User is now a moderator."
            else:  # remove
                if not user_is_mod:
                    raise BotException(
                        EXCEPTION, "User is not in the moderators list.")
                else:
                    data.list_data_remove(
                        bot, 'base', 'moderators',
                        user_id, server_id=message.server.id)
                    response = "User is no longer a moderator."

    elif blueprint_index in (6, 7):  # mute or unmute
        server_id = message.server.id
        mute = blueprint_index == 6

        if arguments[0]:
            channel_id = data.get_channel(
                bot, arguments[0], message.server, attribute='id')
            muted = message.channel.id in data.get(
                bot, 'base', 'muted_channels', server_id=server_id, default=[])
            if mute:
                if muted:
                    raise BotException(
                        EXCEPTION, "Channel is already muted.")
                else:
                    data.list_data_append(
                        bot, 'base', 'muted_channels',
                        channel_id, server_id=server_id)
                    response = "Channel muted."
            else:  # unmute
                if not muted:
                    raise BotException(
                        EXCEPTION, "Channel is already unmuted.")
                else:
                    data.list_data_remove(
                        bot, 'base', 'muted_channels',
                        channel_id, server_id=server_id)
                    response = "Channel unmuted."

        else:  # server
            muted = data.get(
                bot, 'base', 'muted',
                server_id=server_id, default=False)
            if not (muted ^ mute):
                response = "Server is already {}muted.".format(
                    '' if muted else 'un')
                raise BotException(EXCEPTION, response)
            else:
                data.add(bot, 'base', 'muted', mute, server_id=server_id)
                response = "Server {}muted.".format('' if mute else 'un')

    elif blueprint_index == 8:  # invoker
        data.add(
            bot, 'base', 'command_invoker',
            arguments[0] if arguments[0] else None,
            server_id=message.server.id)
        response = "Custom command invoker {}.".format(
                'set' if arguments[0] else 'cleared')

    elif blueprint_index == 9:  # mention
        current_mode = data.get(
            bot, 'base', 'mention_mode',
            server_id=message.server.id, default=False)
        data.add(
            bot, 'base', 'mention_mode', not current_mode,
            server_id=message.server.id)
        response = "Mention mode {}activated.".format(
            'de' if current_mode else '')

    return response


async def owner_wrapper(bot, message, blueprint_index, options, arguments):
    response = ''

    if blueprint_index == 0:  # halt
        await bot.send_message(message.channel, "Going down...")
        bot.shutdown()
    elif blueprint_index == 1:  # restart
        await bot.send_message(message.channel, "Restarting...")
        bot.restart()
    elif blueprint_index == 2:  # ip
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # Thanks Google
        ip = s.getsockname()[0]
        s.close()
        response = "Local IP: " + ip
    elif blueprint_index == 3:  # backup
        bot.make_backup()
        await bot.send_file(
            message.channel, '{}/temp/backup.zip'.format(bot.path))
    elif blueprint_index == 4:  # Announcement
        if arguments[0]:
            text = '{0}:\n{1}'.format(time.strftime('%c'), arguments[0])
            data.add(bot, 'base', 'announcement', text)
            response = "Announcement set!"
        else:
            data.add(bot, 'base', 'announcement', '')
            response = "Announcement cleared!"

    return response


async def debug_wrapper(bot, message, blueprint_index, options, arguments):
    response = ''
    message_type = 0
    extra = None
    global local_dictionary

    if blueprint_index == 0:  # List plugins
        plugins = list(bot.plugins.keys())
        plugins.sort()
        response = '```\n{}```'.format(plugins)

    elif blueprint_index == 1:  # Plugin information
        if options['plugin'] not in bot.plugins:
            response = options['plugin'] + " not found."
        else:
            plugin = bot.plugins[options['plugin']][0]
            version = getattr(plugin, '__version__', 'Unknown')
            has_flag = getattr(plugin, 'uses_configuration', False)
            response = ("```\nPlugin information for: {0}\n"
                        "Version: {1}\n"
                        "Config: {2}\n"
                        "Dir: {3}\n```").format(
                            options['plugin'],
                            version, has_flag, dir(plugin))

    elif blueprint_index == 2:  # Latency
        message_type = 3
        response = "Testing latency time..."
        extra = ('ping', time.time() * 1000)

    elif blueprint_index == 3:  # Reset local dictionary
        setup_debug_environment(bot)
        response = "Debug environment local dictionary reset."

    elif blueprint_index == 4:  # Exec
        local_dictionary['message'] = message

        # Sanitize input
        arguments = arguments[0]
        if arguments.startswith('```py\n') and arguments.endswith('```'):
            arguments = arguments[6:-3]
        else:
            arguments = arguments.strip('`')
        pass_in = [arguments, {}, local_dictionary]

        # Check if the previous result should be sent as a file
        if arguments in ('saf', 'file'):
            await bot.send_text_as_file(
                message.channel, str(local_dictionary['result']), 'result')
        else:
            used_exec = False

            try:  # Try to execute arguments
                if '\n' in arguments:
                    exec(*pass_in)
                    used_exec = True
                else:
                    try:
                        if arguments.startswith('await '):
                            pass_in[0] = arguments[6:]
                            local_dictionary['result'] = await eval(*pass_in)
                        else:
                            local_dictionary['result'] = eval(*pass_in)
                    except SyntaxError:  # May need to use exec
                        exec(*pass_in)
                        used_exec = True

            except Exception as e:
                local_dictionary['last_traceback'] = traceback.format_exc()
                response = '`{0}: {1}`'.format(type(e).__name__, e)

            else:  # Get response if it exists
                if used_exec:
                    result = 'Executed.'
                elif local_dictionary['result'] is None:
                    result = 'Evaluated. (returned None)'
                else:
                    result = str(local_dictionary['result'])
                if len(result) >= 1998:
                    raise BotException(
                        EXCEPTION, "Exec result is too long. (try 'file')")
                if '\n' in result:  # Better formatting
                    response = '```python\n{}\n```'.format(result)
                else:  # One line response
                    response = '`{}`'.format(result)

    return (response, message_type, extra)


async def get_response(
        bot, message, base, blueprint_index, options, arguments,
        keywords, cleaned_content):
    response, tts, message_type, extra = ('', False, 0, None)

    if base == 'ping':
        if arguments:
            response = 'Pong!\n{}'.format(arguments[0])
        else:
            response = 'Pong!'

    elif base == 'base':
        response, message_type = await base_wrapper(
            bot, message, message.channel.is_private,
            blueprint_index, options, arguments)

    elif base == 'mod':
        response = await mod_wrapper(
            bot, message, blueprint_index, options, arguments)

    elif base == 'owner':
        response = await owner_wrapper(
            bot, message, blueprint_index, options, arguments)

    elif base == 'debug':
        response, message_type, extra = await debug_wrapper(
            bot, message, blueprint_index, options, arguments)

    else:
        response = "This should not be seen. Your command was: " + base

    return (response, tts, message_type, extra)


async def handle_active_message(bot, message_reference, extra):
    """
    This function is called if the given message was marked as active
    (message_type of 3).
    """
    if extra[0] == 'ping':
        latency_time = "Latency time: {:.2f} ms".format(
                (time.time() * 1000) - extra[1])
        await bot.edit_message(message_reference, latency_time)


def setup_debug_environment(bot):
    """Resets the local dictionary for the debug command."""
    global local_dictionary
    local_dictionary = {}
    import pprint

    def say(text):
        calling_locals = inspect.currentframe().f_back.f_locals
        asyncio.ensure_future(bot.send_message(
                calling_locals['message'].channel, str(text)))
    local_dictionary.update({
        'bot': bot,
        'inspect': inspect,
        'traceback': traceback,
        'last_traceback': '',
        'result': '',
        'say': say,
        'pformat': pprint.pformat
    })


# Standard discord.py event functions

async def on_ready(bot):
    setup_debug_environment(bot)

async def on_server_join(bot, server):
    # Add server to the list
    logging.debug("Joining server")
    data.add_server(bot, server)

async def on_message_edit(bot, before, after):
    """Integrates with the core to handle edited messages."""
    if before.id in bot.edit_dictionary:
        message_reference = bot.edit_dictionary.pop(before.id)
        await bot.on_message(after, replacement_message=message_reference)

async def on_error(bot, event, *args, **kwargs):
    """Gets uncaught exceptions."""
    logging.error(
        "An exception was thrown that wasn't handled by the core. \n"
        "Event: {0}\nargs: {1}\nkwargs: {2}".format(event, args, kwargs))
    traceback.print_exc()
