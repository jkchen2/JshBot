import asyncio
import random
import socket
import time
import logging
import inspect
import traceback

from jshbot import data, utilities
from jshbot.exceptions import BotException

__version__ = '0.1.6'
EXCEPTION = 'Base'
uses_configuration = False
local_dictionary = {}


def get_commands():
    """Sets up new commands and shortcuts in the proper syntax.

    See command_reference.txt for more information and examples.
    See dummy.py for a complete sample reference.
    """
    commands = {}
    shortcuts = {}
    manual = {}

    commands['ping'] = (['&'], [])
    commands['debug'] = ([
        'plugin:', 'plugin list', 'latency', 'resetlocals', '^'], [
        ('plugin', 'p'), ('list', 'l'), ('latency', 'ping')])
    commands['owner'] = ([
        'halt', 'restart', 'ip', 'backup', 'announcement &'], [])
    commands['mod'] = ([
        'info', 'block ^', 'unblock ^', 'clear', 'add ^', 'remove ^', 'mute :',
        'unmute :', 'invoker &', 'mention'], [
        ('info', 'i'), ('clear', 'c')])
    commands['base'] = ([
        'version', 'source', 'uptime', 'help: &', 'help', 'announcement',
        'join', 'leave'], [
        ('version', 'ver', 'v'), ('source', 'src', 'git'), ('help', 'h')])

    shortcuts['clear'] = ('mod -clear', '')
    shortcuts['help'] = ('base -help {}', '&')
    shortcuts['restart'] = ('owner -restart', '')
    shortcuts['announcement'] = ('base -announcement', '')
    shortcuts['join'] = ('base -join', '')
    shortcuts['leave'] = ('base -leave', '')

    manual['ping'] = {
        'description': 'Command to ping the bot for a response.',
        'usage': [
            ('(argument)', 'Optional argument.')]}
    manual['debug'] = {
        'description': 'Debug commands.',
        'usage': [
            ('-plugin <plugin>', 'Show information about the plugin.'),
            ('-plugin -list', 'Lists all active plugins.'),
            ('-latency', 'Gets ping time to current server.'),
            ('-resetlocals', 'Resets the local dictionary environment.'),
            ('<expression>', 'Executes or evalulates the given expression.')],
        'other': 'Be careful with these commands! They can break the bot.'}
    manual['owner'] = {
        'description': 'Commands for the owner only.',
        'usage': [
            ('-halt', 'Stops the bot.'),
            ('-restart', 'Restarts the bot.'),
            ('-ip', 'Gets the internal IP address of the bot.'),
            ('-backup', 'Sends each owner a copy of the bot data files.'),
            ('-announcement <text>', 'Sets the announcement text.')],
        'shortcuts': [('restart', '-restart')]}
    manual['mod'] = {
        'description': 'Commands for server bot moderators.',
        'usage': [
            ('-info', 'Gets server information.'),
            ('-block <user>', 'Blocks the user from bot interaction.'),
            ('-unblock <user>', 'Unblocks the user from bot interaction.'),
            ('-clear', 'Pushes chat upwards.'),
            ('-add <user>', 'Adds the user to the moderators list.'),
            ('-remove <user>', 'Removes the user from the moderators list.'),
            ('-mute <type>', 'Mutes the given type.'),
            ('-unmute <type>', 'Unmutes the given type.'),
            ('-invoker <invoker>', 'Sets or clears the custom command invoker '
                'for the server.'),
            ('-mention', 'Toggles mention mode for the server.')],
        'shorcuts': [('clear', '-clear')],
        'other': 'The type for mute and unmute must either be "server" or '
                 '"channel"'}
    manual['base'] = {
        'description': 'Base commands.',
        'usage': [
            ('-version', 'Gets the bot version and date.'),
            ('-source', 'Gets the github link to the source of JshBot.'),
            ('-uptime', 'Gets how long the bot has been up.'),
            ('-help <command> (topic index)', 'Gets the help about the '
                'given command, with extra information on a specific option '
                'if a valid topic index is provided.'),
            ('-help', 'Gets the general help page.'),
            ('-announcement', 'Gets the current announcement from the owners '
                'about the bot.'),
            ('-join', 'Joins the voice channel of the command author.'),
            ('-leave', 'Leaves the voice channel of the command author.')],
        'shortcuts': [
            ('help <arguments>', '-help <arguments>'),
            ('announcement', '-announcement')]}

    return (commands, shortcuts, manual)


async def base_wrapper(bot, message, direct, plan_index, options, arguments):
    response = ''
    message_type = 0
    if plan_index == 0:  # version
        response = '`{}`\n{}'.format(bot.version, bot.date)
    elif plan_index == 1:  # source
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
    elif plan_index == 2:  # uptime
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
    elif plan_index in (3, 4):  # help, detailed or general
        if plan_index == 3:  # Detailed
            response = get_help(
                bot, options['help'],
                topic=arguments if arguments else None)
        else:  # General
            response = get_general_help(bot)
        if not direct:  # Terminal reminder message
            await bot.send_message(message.author, response)
            response = "Check your direct messages!"
            message_type = 2  # Default 10 seconds
    elif plan_index == 5:  # Announcement
        announcement = data.get(bot, 'base', 'announcement')
        if not announcement:
            response = "No announcement right now!"
        else:
            response = announcement
    elif plan_index in (6, 7):  # Join/leave voice channel
        voice_channel = message.author.voice_channel
        if not voice_channel:
            raise BotException(EXCEPTION, "You are not in a voice channel.")
        try:
            if plan_index == 6:
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
            action = 'join' if plan_index == 6 else 'leave'
            raise BotException(
                EXCEPTION, "Failed to {} the voice channel.".format(action),
                e=e)

    return (response, message_type)


async def mod_wrapper(bot, message, direct, plan_index, options, arguments):
    response = ''
    if direct:
        raise BotException(
            EXCEPTION, "You cannot use these commands in a direct message.")

    elif not data.is_mod(bot, message.server, message.author.id):
        raise BotException(
            EXCEPTION, "You must be a moderator to use these commands.")

    else:

        if plan_index == 0:  # info
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

        elif plan_index in (1, 2):  # block or unblock
            user = data.get_member(bot, arguments, message.server)
            block = plan_index == 1
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

        elif plan_index == 3:  # clear
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

        elif plan_index in (4, 5):  # add or remove moderator
            if not data.is_admin(bot, message.server, message.author.id):
                raise BotException(
                    EXCEPTION, "You must be an admin to use these commands.")
            else:
                user_id = data.get_member(
                    bot, arguments, server=message.server, attribute='id')
                user_is_mod = data.is_mod(
                    bot, message.server, user_id, strict=True)
                blocked = data.is_blocked(
                    bot, message.server, user_id, strict=True)
                if blocked:
                    response = "User is blocked."
                elif plan_index == 4:  # add
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

        elif plan_index in (6, 7):  # mute or unmute
            try:
                type_index = ('channel', 'server').index(arguments[0])
            except ValueError:
                raise BotException(
                    EXCEPTION, "The type must be \"channel\" or \"server\".")
            else:
                mute_key = ('muted_channels', 'muted')[type_index]
                server_id = message.server.id
                mute = plan_index == 6

                if type_index == 0:  # channel
                    muted = message.channel.id in data.get(
                        bot, 'base', mute_key,
                        server_id=server_id, default=[])
                    if mute:
                        if muted:
                            raise BotException(
                                EXCEPTION, "Channel is already muted.")
                        else:
                            data.list_data_append(
                                bot, 'base', mute_key,
                                message.server.id, server_id=server_id)
                            response = "Channel muted."
                    else:  # unmute
                        if not muted:
                            raise BotException(
                                EXCEPTION, "Channel is already unmuted.")
                        else:
                            data.list_data_remove(
                                bot, 'base', mute_key,
                                message.server.id, server_id=server_id)
                            response = "Channel unmuted."

                else:  # server
                    muted = data.get(
                        bot, 'base', mute_key,
                        server_id=server_id, default=False)
                    if not (muted ^ mute):
                        response = "Server is already {}muted.".format(
                            '' if muted else 'un')
                        raise BotException(EXCEPTION, response)
                    else:
                        data.add(
                            bot, 'base', mute_key, mute,
                            server_id=server_id)
                        response = "Server {}muted.".format(
                                '' if mute else 'un')

        elif plan_index == 8:  # invoker
            data.add(
                bot, 'base', 'command_invoker',
                arguments if arguments else None,
                server_id=message.server.id)
            response = "Custom command invoker {}.".format(
                    'set' if arguments else 'cleared')

        elif plan_index == 9:  # mention
            current_mode = data.get(
                bot, 'base', 'mention_mode',
                server_id=message.server.id, default=False)
            data.add(
                bot, 'base', 'mention_mode', not current_mode,
                server_id=message.server.id)
            response = "Mention mode {}activated.".format(
                'de' if current_mode else '')
    return response


async def owner_wrapper(bot, message, direct, plan_index, options, arguments):
    response = ''
    if not data.is_owner(bot, message.author.id):
        raise BotException(
            EXCEPTION, "You must be the bot owner to use these commands.")

    else:

        if plan_index == 0:  # halt
            bot.interrupt_say(
                None, "Going down...", channel=message.channel)
            await asyncio.sleep(1)
            bot.shutdown()
        elif plan_index == 1:  # restart
            bot.interrupt_say(
                None, "Restarting...", channel=message.channel)
            await asyncio.sleep(1)
            bot.restart()
        elif plan_index == 2:  # ip
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))  # Thanks Google
            ip = s.getsockname()[0]
            s.close()
            response = "Local IP: " + ip
        elif plan_index == 3:  # backup
            bot.make_backup()
            await bot.send_file(
                message.channel, '{}/temp/backup.zip'.format(bot.path))
        elif plan_index == 4:  # Announcement
            arguments = '{0}:\n{1}'.format(time.strftime('%c'), arguments)
            data.add(bot, 'base', 'announcement', arguments)
            response = "Announcement set!"

    return response


async def debug_wrapper(bot, message, direct, plan_index, options, arguments):
    response = ''
    message_type = 0
    extra = None
    global local_dictionary

    if not data.is_owner(bot, message.author.id):
        raise BotException(
            EXCEPTION, "You must be a bot owner to use these commands.")

    elif plan_index == 0:  # Plugin information
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

    elif plan_index == 1:  # List plugins
        plugins = list(bot.plugins.keys())
        plugins.sort()
        response = '```\n{}```'.format(plugins)

    elif plan_index == 2:  # Latency
        message_type = 3
        response = "Testing latency time..."
        extra = ('ping', time.time() * 1000)

    elif plan_index == 3:  # Reset local dictionary
        setup_debug_environment(bot)
        response = "Debug environment local dictionary reset."

    elif plan_index == 4:  # Exec
        local_dictionary['message'] = message

        # Sanitize input
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


async def get_response(bot, message, parsed_command, direct):

    tts = False
    message_type = 0
    extra = None
    base, plan_index, options, arguments = parsed_command

    if base == 'ping':
        response = 'Pong!\n' + arguments

    elif base == 'base':
        response, message_type = await base_wrapper(
            bot, message, direct, plan_index, options, arguments)

    elif base == 'mod':
        response = await mod_wrapper(
            bot, message, direct, plan_index, options, arguments)

    elif base == 'owner':
        response = await owner_wrapper(
            bot, message, direct, plan_index, options, arguments)

    elif base == 'debug':
        response, message_type, extra = await debug_wrapper(
            bot, message, direct, plan_index, options, arguments)

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


def get_general_help(bot):
    """Gets the general help. Lists all base commands that aren't shortcuts."""
    response = "Here is a list of base commands:\n```\n"
    for base in bot.commands:
        if type(bot.commands[base][0]) is not str:  # Skip shortcuts
            response += base + '\n'
    response += "```\nGet help on a command with `{}help <command>`".format(
            bot.configurations['core']['command_invokers'][0])
    return response


def get_help(bot, base, topic=None):
    """Gets the help of the base command, or the topic of a help command."""
    # Check for shortcut first
    if base in bot.commands and type(bot.commands[base][0]) is str:
        return get_help(bot, bot.commands[base][0].split(' ', 1)[0], topic)

    if base not in bot.manual:
        return "No help entry for this command. Sorry!"
    manual_entry = bot.manual[base]
    invoker = bot.configurations['core']['command_invokers'][0]

    # Handle specific topic help
    if topic:
        try:
            topic_index = int(topic)
        except:
            return "Topic number is not a valid integer.\n"
        if 'usage' not in manual_entry:
            return "No usage entry for this command."
        elif topic_index < 1 or topic_index > len(manual_entry['usage']):
            return "Invalid topic index.\n" + get_usage_reminder(bot, base)
        else:
            topic_pair = manual_entry['usage'][topic_index - 1]
            return '```\n{}{} {}\n\t{}```'.format(
                    invoker, base, topic_pair[0], topic_pair[1])

    # Handle regular help
    # Description, usage, aliases, shortcuts, other
    aliases = bot.commands[base][0][1]
    response = '```\n'
    if 'description' in manual_entry:
        response += 'Description:\n\t{0[description]}\n\n'.format(manual_entry)
    if 'usage' in manual_entry:
        response += 'Usage: {}{} (syntax)\n'.format(invoker, base)
        for topic_index, topic in enumerate(manual_entry['usage']):
            response += '\t({}) {}\n'.format(topic_index + 1, topic[0])
        response += '\n'
    if aliases:
        response += 'Aliases:\n'
        for alias in aliases:
            response += '\t{}:'.format(alias[0])
            for name in alias[1:]:
                response += ' {},'.format(name)
            response = response[:-1] + '\n'
        response += '\n'
    if 'shortcuts' in manual_entry:
        response += 'Shortcuts:\n'
        for shortcut in manual_entry['shortcuts']:
            response += '\t{}{}\n\t\t{}{} {}\n'.format(
                    invoker, shortcut[0], invoker, base, shortcut[1])
        response += '\n'
    if 'other' in manual_entry:
        response += 'Other information:\n\t{}\n'.format(manual_entry['other'])

    return response + '```'


def get_usage_reminder(bot, base):
    """Returns the usage syntax for the base command (simple format)."""
    # Check for shortcut first
    if base in bot.commands and type(bot.commands[base][0]) is str:
        return get_usage_reminder(
            bot, bot.commands[base][0].split(' ', 1)[0])

    if base not in bot.manual or 'usage' not in bot.manual[base]:
        return "No usage entry for this command."

    response = '```\n'
    invoker = bot.configurations['core']['command_invokers'][0]
    response += 'Usage: {}{} (syntax)\n'.format(invoker, base)
    for topic_index, topic in enumerate(bot.manual[base]['usage']):
        response += '\t({}) {}\n'.format(topic_index + 1, topic[0])
    response += '```'

    return response


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
