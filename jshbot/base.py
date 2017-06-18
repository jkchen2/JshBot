import asyncio
import discord
import random
import socket
import time
import logging
import inspect
import traceback
import re

from discord.abc import PrivateChannel

from jshbot import parser, data, utilities, commands, plugins, configurations
from jshbot.exceptions import BotException, ConfiguredBotException
from jshbot.commands import (
    Command, SubCommand, Shortcut, ArgTypes, Arg, Opt, Attachment,
    MessageTypes, Response)

__version__ = '0.2.0'
uses_configuration = False
CBException = ConfiguredBotException('Base')
global_dictionary = {}


@plugins.command_spawner
def get_commands():
    """Sets up new commands and shortcuts in the proper syntax.

    See dummy.py for a complete sample reference.
    """
    new_commands = []

    new_commands.append(Command(
        'ping', subcommands=[
            SubCommand(
                Arg('message', argtype=ArgTypes.MERGED_OPTIONAL),
                doc='The bot will respond with "Pong!" and the given message if it is included.')],
        description='Pings the bot for a response.', category='core'))

    new_commands.append(Command(
        'base', subcommands=[
            SubCommand(Opt('version'), doc='Gets the version of the bot.'),
            SubCommand(Opt('source'), doc='Gets the source of the bot.'),
            SubCommand(Opt('uptime'), doc='Gets the uptime of the bot.'),
            SubCommand(Opt('announcement'), doc='Gets the current announceent.'),
            SubCommand(
                Opt('invite'),
                Opt('details', optional=True,
                    doc='Shows a breakdown of what each permission is used for'),
                doc='Generates an invite for the bot.'),
            SubCommand(
                Opt('join'), doc='Have the bot join the voice channel you are in.',
                allow_direct=False),
            SubCommand(
                Opt('leave'), doc='Have the bot leave the voice channel you are in.',
                allow_direct=False)],
        shortcuts = [
            Shortcut('announcement', 'announcement'),
            Shortcut('invite', 'invite details'),
            Shortcut('join', 'join'),
            Shortcut('leave', 'leave'),
            Shortcut('stfu', 'leave')],
        description='Essential bot commands that anybody can use.',
        category='core', function=base_wrapper))

    new_commands.append(Command(
        'mod', subcommands=[
            SubCommand(Opt('info'), doc='Gets server information'),
            SubCommand(
                Opt('toggle'),
                Arg('command', argtype=ArgTypes.MERGED,
                    doc='The command to toggle. If a specific subcommand needs to be '
                        'toggled, the index of the subcomand can be supplied after '
                        'the base.'),
                doc='Enables or disables a command.'),
            SubCommand(
                Opt('block'), Arg('user', argtype=ArgTypes.MERGED,
                    convert=utilities.MemberConverter()),
                doc='Blocks the user from interacting with the bot.'),
            SubCommand(
                Opt('unblock'), Arg('user', argtype=ArgTypes.MERGED,
                    convert=utilities.MemberConverter()),
                doc='Unlocks the user from interacting with the bot.'),
            SubCommand(Opt('clear'), doc='Pushes chat upwards.'),
            SubCommand(
                Opt('mute'), Arg('channel', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=utilities.ChannelConverter()),
                doc='Stops the bot from responding to messages sent in the given '
                    'channel, or the entire server if the channel is not given.'),
            SubCommand(
                Opt('unmute'), Arg('channel', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=utilities.ChannelConverter()),
                doc='Allows the bot to respond to messages sent in the given '
                    'channel, or the entire server if the channel is not given.'),
            SubCommand(
                Opt('invoker'), Arg('custom invoker', argtype=ArgTypes.MERGED_OPTIONAL),
                doc='Sets or clears the custom invoker.'),
            SubCommand(
                Opt('mention'), doc='Toggles mention mode. If enabled, the bot '
                    'will only respond to its name or mention as an invoker.'),
            SubCommand(
                Opt('cooldown'),
                Arg('number of commands', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=int, check=lambda b, m, v, *a: 0 < v <= b.spam_limit,
                    check_error='Must be between 1 and {b.spam_limit} inclusive.'),
                doc='Limits the number of commands per default time interval to the '
                    'value specified. Bot moderators are not subject to this limit. If '
                    'no value is given, the default cooldown is used (maximum value).')],
        shortcuts=[Shortcut('clear', 'clear')],
        description='Commands for bot moderators.', elevated_level=1,
        no_selfbot=True, category='core', function=mod_wrapper))

    new_commands.append(Command(
        'owner', subcommands=[
            SubCommand(
                Opt('modrole'),
                Arg('role', argtype=ArgTypes.MERGED_OPTIONAL, convert=utilities.RoleConverter()),
                doc='Sets or clears the bot moderator role.'),
            SubCommand(
                Opt('feedback'), Arg('message', argtype=ArgTypes.MERGED),
                doc='Sends a message to the bot owners. NOTE: Your user ID will be sent '
                    'as well. Please use reasonably.'),
            SubCommand(
                Opt('notifications'),
                doc='Toggles notifications from the bot regarding moderation events '
                    '(such as muting channels and blocking users from bot interaction).')],
        description='Commands for server owners.',
        elevated_level=2, no_selfbot=True, category='core', function=owner_wrapper))

    new_commands.append(Command(
        'botowner', subcommands=[
            SubCommand(Opt('halt'), doc='Shuts down the bot.'),
            SubCommand(Opt('restart'), doc='Restarts the bot.'),
            SubCommand(
                Opt('reload'),
                Arg('plugin', argtype=ArgTypes.SPLIT_OPTIONAL, additional='additional plugins'),
                doc='Reloads the specified plugin(s), or all external plugins.'),
            SubCommand(Opt('ip'), doc='Gets the local IP address of the bot.'),
            SubCommand(Opt('backup'), doc='Gets the data folder as a zip file.'),
            SubCommand(
                Opt('restore'), Attachment('restore zip file'),
                doc='Gets the data folder as a zip file.'),
            SubCommand(
                Opt('blacklist'),
                Arg('user', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=utilities.MemberConverter(server_only=False)),
                doc='Blacklist or unblacklist a user from sending feedback. If no '
                    'user is specified, this lists all blacklisted entries.'),
            SubCommand(Opt('togglefeedback'), doc='Toggles the feedback command.'),
            SubCommand(
                Opt('announcement'), Arg('text', argtype=ArgTypes.MERGED_OPTIONAL),
                doc='Sets or clears the announcement text.')],
        shortcuts=[Shortcut('reload', 'reload')],
        description='Commands for the bot owner(s).',
        elevated_level=3, category='core', function=botowner_wrapper))

    new_commands.append(Command(
        'debug', subcommands=[
            SubCommand(Opt('plugin'), Opt('list'), doc='Lists loaded plugins.'),
            SubCommand(
                Opt('plugin', attached='plugin name'),
                doc='Gets basic information about the given plugin.'),
            SubCommand(Opt('latency'), doc='Calculates the ping time.'),
            SubCommand(Opt('resetlocals'), doc='Resets the debug local variables.'),
            SubCommand(
                Arg('python', argtype=ArgTypes.MERGED),
                doc='Evaluates or executes the given code.')],
        description='Commands to help the bot owner debug stuff.',
        other='Be careful with these commands! They can break the bot.',
        elevated_level=3, category='core', function=debug_wrapper))

    new_commands.append(Command(
        'help', subcommands=[
            SubCommand(
                Opt('manual'), Opt('here', optional=True),
                Arg('subject', argtype=ArgTypes.OPTIONAL),
                Arg('topic number', argtype=ArgTypes.OPTIONAL, convert=int, default=None,
                    check=lambda b, m, v, *a: v > 0, check_error='Must be a positive number.',
                    quotes_recommended=False),
                Arg('page number', argtype=ArgTypes.OPTIONAL, convert=int, default=None,
                    check=lambda b, m, v, *a: v > 0, check_error='Must be a positive number.',
                    quotes_recommended=False),
                doc='Gets the specified manual. If no subject is specified, this '
                    'brings up the general manual menu.'),
            SubCommand(
                Opt('all'), Opt('here', optional=True),
                doc='Shows all of the commands and related help.'),
            SubCommand(
                Opt('here', optional=True),
                Arg('base', argtype=ArgTypes.OPTIONAL),
                Arg('topic', argtype=ArgTypes.MERGED_OPTIONAL,
                    doc='Either the subcommand index, or standard subcommand syntax.'),
                doc='Gets the specified help entry. If no base is specified, this '
                    'brings up the general help menu.')],
        shortcuts=[
            Shortcut(
                'manual', 'manual {arguments}',
                Arg('arguments', argtype=ArgTypes.MERGED_OPTIONAL))],
        description='Command help and usage manuals.',
        other=('For all of these commands, if the \'here\' option is specified, a '
               'direct message will not be sent.'),
        category='core', function=help_wrapper))

    return new_commands


@plugins.db_template_spawner
def get_templates():
    """Gets the timer database template."""
    return {
        'schedule': ("time          bigint NOT NULL,"
                     "plugin        text NOT NULL,"
                     "function      text NOT NULL,"
                     "payload       text,"
                     "search        text,"
                     "destination   text")
    }

#async def schedule(bot, plugin_name, function, payload, time, search=None):

@plugins.on_load
def setup_schedule_table(bot):
    if not data.db_exists(bot, 'schedule'):  # Create schedule table
        data.db_create_table(bot, 'schedule', template='schedule')
    if not data.db_exists(bot, 'IX_schedule_time'):  # Create time index
        data.db_execute(bot, 'CREATE INDEX IX_schedule_time ON schedule (time ASC)')


async def base_wrapper(bot, context):
    message, _, subcommand, options = context[:4]

    if subcommand.index == 0:  # version
        response = '`{}`\n{}'.format(bot.version, bot.date)

    elif subcommand.index == 1:  # source
        response = random.choice([
            "It's shit. I'm sorry.",
            "You want to see what the Matrix is like?",
            "Script kiddie level stuff in here.",
            "Beware the lack of PEP 8 guidelines inside!",
            "Snarky comments inside and out.",
            "Years down the road, this will all just be a really "
            "embarrassing but funny joke.",
            "Made with ~~love~~ pure hatred.",
            "At least he's using version control.",
            "Yes, I know I'm not very good. Sorry...",
            "Take it easy on me, okay?",
            "You're going to groan. A lot.",
            "You might be better off *not* looking inside."])
        response += ("\nhttps://github.com/jkchen2/JshBot\n"
                     "https://github.com/jkchen2/JshBot-plugins")

    elif subcommand.index == 2:  # uptime
        uptime_total_seconds = int(time.time()) - bot.time
        uptime_struct = time.gmtime(uptime_total_seconds)
        days = int(uptime_total_seconds / 86400)
        hours = uptime_struct.tm_hour
        minutes = uptime_struct.tm_min
        seconds = uptime_struct.tm_sec
        response = (
            "The bot has been on since **{0}**\n{1} days, {2} hours, "
            "{3} minutes, and {4} seconds").format(
                bot.readable_time, days, hours, minutes, seconds)

    elif subcommand.index == 3:  # Announcement
        announcement = data.get(bot, 'base', 'announcement')
        if not announcement:
            response = "No announcement right now!"
        else:
            response = announcement

    elif subcommand.index == 4:  # Invite
        if bot.selfbot:
            raise CBException("Nope.")
        response_list = []

        if 'details' in options:
            for plugin in bot.plugins.keys():
                permission_items = data.get(
                    bot, plugin, 'permissions', volatile=True, default={}).items()
                if permission_items:
                    response_list.append('***`{}`***'.format(plugin))
                    response_list.append('\t' + '\n\t'.join(
                        ['**`{0[0]}`** -- {0[1]}'.format(item)
                            for item in permission_items]) + '\n')

        permissions_number = utilities.get_permission_bits(bot)
        app_id = (await bot.application_info()).id
        response_list.append(
            'https://discordapp.com/oauth2/authorize?&client_id={0}'
            '&scope=bot&permissions={1}\n**Remember: you must have the '
            '"Administrator" role on the server you are trying to add the '
            'bot to.**'.format(app_id, permissions_number))
        response = '\n'.join(response_list)

    elif subcommand.index in (5, 6):  # Join/leave voice channel
        if not message.author.voice:
            raise CBException("You are not in a voice channel.")
        try:
            voice_channel = message.author.voice.channel
            if subcommand.index == 5:
                await utilities.join_and_ready(
                    bot, voice_channel, reconnect=True, is_mod=data.is_mod(
                        bot, message.guild, message.author.id))
                response = "Joined {}.".format(voice_channel.name)
            else:
                await utilities.leave_and_stop(
                    bot, message.guild, member=message.author, safe=False)
                response = "Left {}.".format(voice_channel.name)
        except BotException as e:
            raise e  # Pass up
        except Exception as e:
            action = 'join' if subcommand.index == 5 else 'leave'
            raise CBException("Failed to {} the voice channel.".format(action), e=e)

    return Response(content=response)


async def mod_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    response = ''
    mod_action = ''

    if subcommand.index == 0:  # info
        guild_data = data.get(
            bot, 'base', None, guild_id=message.guild.id, default={})
        guild_volatile_data = data.get(
            bot, 'base', None, guild_id=message.guild.id, default={}, volatile=True)
        disabled_commands = guild_data.get('disabled', [])
        display_list = []
        for disabled_command in disabled_commands:
            display_list.append('{0} ({1})'.format(
                disabled_command[0],
                'all' if disabled_command[1] == -1 else disabled_command[1]+1))
        cooldown_message = (
            "{} command(s) per {} seconds(s)".format(
                guild_data.get('spam_limit', bot.spam_limit),
                bot.spam_timeout))
        response = (
            '```\n'
            'Information for server {0}\n'
            'ID: {0.id}\n'
            'Owner: {0.owner.id}\n'
            'Bot moderator role: {1}\n'
            'Blocked users: {2}\n'
            'Muted: {3}\n'
            'Muted channels: {4}\n'
            'Command invoker: {5}\n'
            'Mention mode: {6}\n'
            'Disabled commands: {7}\n'
            'Cooldown: {8}```').format(
                message.guild,
                guild_volatile_data.get('modrole', None),
                guild_data.get('blocked', []),
                guild_data.get('muted', []),
                guild_data.get('muted_channels', []),
                guild_data.get('command_invoker', None),
                guild_data.get('mention_mode', False),
                display_list, cooldown_message)

    elif subcommand.index == 1:  # Toggle command  (TODO: Fix for rewrite)
        try:  # Explicit index
            split_arguments = arguments[0].split()
            command = bot.commands[split_arguments[0]]
            if isinstance(command, commands.Shortcut):
                command = command.command
            disable_pair = [command.base, int(split_arguments[1]) - 1]
            assert -1 < guess[1] < len(command.blueprints)
        except IndexError:  # No index
            disable_pair = [command.base, -1]
        except:  # Guess the help index
            guess = parser.guess_index(bot, arguments[0], message, safe=False)

        command = bot.commands[guess[0]]
        if command.category == 'core':
            raise CBException("The core commands cannot be disabled.")
        pass_in = (bot, 'base', 'disabled', guess)
        pass_in_keywords = {'guild_id': message.guild.id}
        disabled_commands = data.get(
            *pass_in[:-1], **pass_in_keywords, default=[])
        if guess in disabled_commands:
            data.list_data_remove(*pass_in, **pass_in_keywords)
            response = "Enabled"
        else:
            data.list_data_append(*pass_in, **pass_in_keywords)
            response = "Disabled"
        response += " the `{0}` command {1}.".format(
            guess[0], "and all associated subcommands"
            if guess[1] == -1 else "(subcommand {})".format(guess[1] + 1))
        mod_action = response

    elif subcommand.index in (2, 3):  # Block or unblock
        user = data.get_member(bot, arguments[0], message.guild)
        block = subcommand.index == 2
        mod_action = 'Blocked {}' if block else 'Unblocked {}'
        mod_action = mod_action.format('{0} ({0.id})'.format(user))
        blocked = data.is_blocked(
            bot, message.guild, user.id, strict=True)
        mod = data.is_mod(bot, message.guild, user.id)
        if mod:
            raise CBException("Cannot block or unblock a moderator.")
        elif block:
            if blocked:
                raise CBException("User is already blocked.")
            else:
                data.list_data_append(
                    bot, 'base', 'blocked', user.id,
                    guild_id=message.guild.id)
                response = "User is now blocked."
        else:
            if not blocked:
                raise CBException("User is already unblocked.")
            else:
                data.list_data_remove(
                    bot, 'base', 'blocked', user.id,
                    guild_id=message.guild.id)
                response = "User is now unblocked."

    elif subcommand.index == 4:  # Clear
        response = (
            '\u200b' + '\n'*80 + "The chat was pushed up by a bot moderator.")

    elif subcommand.index in (5, 6):  # Mute or unmute
        guild_id = message.guild.id
        mute = subcommand.index == 5
        mod_action = 'Muted {}' if mute else 'Unmuted {}'

        if arguments[0]:
            channel = arguments[0]
            muted = channel.id in data.get(
                bot, 'base', 'muted_channels', guild_id=guild_id, default=[])
            mod_action = mod_action.format(channel.name)
            if mute:
                if muted:
                    raise CBException("Channel is already muted.")
                else:
                    data.list_data_append(
                        bot, 'base', 'muted_channels', channel.id, guild_id=guild_id)
                    if isinstance(channel, discord.VoiceChannel):  # disconnect
                        await utilities.leave_and_stop(bot, message.guild)
                    response = "Channel muted."
            else:  # unmute
                if not muted:
                    raise CBException("Channel is already unmuted.")
                else:
                    data.list_data_remove(
                        bot, 'base', 'muted_channels', channel.id, guild_id=guild_id)
                    response = "Channel unmuted."

        else:  # guild
            mod_action = mod_action.format('the server')
            muted = data.get(bot, 'base', 'muted', guild_id=guild_id, default=False)
            if not (muted ^ mute):
                response = "Server is already {}muted.".format('' if muted else 'un')
                raise CBException(response)
            else:
                data.add(bot, 'base', 'muted', mute, guild_id=guild_id)
                response = "Server {}muted.".format('' if mute else 'un')

    elif subcommand.index == 7:  # Invoker
        if len(arguments[0]) > 10:
            raise CBException("The invoker can be a maximum of 10 characters long.")
        data.add(
            bot, 'base', 'command_invoker',
            arguments[0] if arguments[0] else None,
            guild_id=message.guild.id)
        response = "Custom command invoker {}.".format('set' if arguments[0] else 'cleared')
        if arguments[0]:
            response = "Custom command invoker set."
            mod_action = "Set the server command invoker to '{}'.".format(arguments[0])
        else:
            response = "Custom command invoker cleared."
            mod_action = "Removed the custom command invoker."

    elif subcommand.index == 8:  # Mention
        current_mode = data.get(
            bot, 'base', 'mention_mode', guild_id=message.guild.id, default=False)
        data.add(bot, 'base', 'mention_mode', not current_mode, guild_id=message.guild.id)
        response = "Mention mode {}activated.".format('de' if current_mode else '')
        mod_action = "{}activated mention mode.".format('de' if current_mode else '').capitalize()

    elif subcommand.index == 9:  # Cooldown
        if arguments[0]:
            try:
                cooldown = int(arguments[0])
                if not 1 <= cooldown <= bot.spam_limit:
                    raise ValueError
            except ValueError:
                raise CBException(
                    "Cooldown value must be between 1 and {} inclusive.".format(bot.spam_limit))
            data.add(bot, 'base', 'spam_limit', cooldown, guild_id=message.guild.id)
            cooldown_message = (
                "{} command(s) per {} seconds(s)".format(cooldown, bot.spam_timeout))
            response = "Cooldown set to {}.".format(cooldown_message)
            mod_action = "set the cooldown to {}.".format(cooldown_message)
        else:
            data.remove(
                bot, 'base', 'spam_limit', guild_id=message.guild.id)
            cooldown_message = (
                "{} command(s) per {} seconds(s)".format(bot.spam_limit, bot.spam_timeout))
            response = "Cooldown reset to the default {}.".format(cooldown_message)
            mod_action = "reset the cooldown to the default {}.".format(cooldown_message)

    # Send notification if configured
    send_notifications = data.get(
        bot, 'base', 'notifications', guild_id=message.guild.id, default=True)
    if mod_action and send_notifications:
        if message.edited_at:
            timestamp = message.edited_at
        else:
            timestamp = message.created_at
        notification = ('Moderator {0} ({0.id}) from {0.guild} on {1}:\n\t'
                        '{2}').format(message.author, timestamp, mod_action)
        logs = await utilities.get_log_text(bot, message.channel, limit=20, before=message)
        logs += '\n{}'.format(utilities.get_formatted_message(message))
        await message.guild.owner.send(notification)
        await utilities.send_text_as_file(message.guild.owner, logs, 'context')

    return Response(content=response)


# TODO: FIX FIX FIX
async def owner_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    mod_action = ''

    send_notifications = data.get(
        bot, 'base', 'notifications',
        guild_id=message.guild.id, default=True)

    if subcommand.index == 0:  # Change moderator role
        role = arguments[0]
        if role:
            response = mod_action = 'Set the bot moderator role to {}.'.format(role)
            data.add(bot, 'base', 'modrole', role.id, guild_id=message.guild.id)
            data.add(bot, 'base', 'modrole', role, guild_id=message.guild.id, volatile=True)
        else:
            response = mod_action = 'Removed the bot moderator role.'
            data.remove(bot, 'base', 'modrole', guild_id=message.guild.id)
            data.remove(bot, 'base', 'modrole', guild_id=message.guild.id, volatile=True)

    elif subcommand.index == 1:  # Send feedback
        if data.get(bot, 'base', 'feedbackdisabled', default=False):
            response = ("Feedback has been temporarily disabled, probably "
                        "due to some troll spammers.")
        else:
            text = arguments[0]
            if len(text) > 1500:
                raise CBException(
                    "Whoa! That's a lot of feedback. 1500 characters or fewer, please.")
            text = '{0} ({0.id}) on {1.created_at}:\n\t{2}'.format(message.author, message, text)
            await utilities.notify_owners(bot, text, user_id=message.author.id)
            response = "Message sent to bot owners."

    elif subcommand.index == 2:  # Toggle notifications
        response = ("Bot moderator activity notifications are now turned "
                    "{}").format("OFF." if send_notifications else "ON.")
        data.add(
            bot, 'base', 'notifications', not send_notifications, guild_id=message.guild.id)

    # Send notification if configured
    if mod_action and send_notifications:
        if message.edited_at:
            timestamp = message.edited_at
        else:
            timestamp = message.created_at
        notification = 'From {0.guild} on {1}, you:\n\t{2}'.format(
            message.author, timestamp, mod_action)
        logs = await utilities.get_log_text(bot, message.channel, limit=20, before=message)
        logs += '\n{}'.format(utilities.get_formatted_message(message))
        await message.guild.owner.send(content=notification)
        await utilities.send_text_as_file(message.guild.owner, logs, 'context')

    return Response(content=response)


async def botowner_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    response, tts, message_type, extra = ('', False, 0, None)

    if subcommand.index == 0:  # Halt
        await message.chanel.send("Going down...")
        bot.shutdown()
    elif subcommand.index == 1:  # Restart
        await message.chanel.send("Restarting...")
        bot.restart()
    elif subcommand.index == 2:  # Reload
        response = "Reloading..."
        message_type = MessageTypes.ACTIVE
        extra = ('reload', arguments)
    elif subcommand.index == 3:  # IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # Thanks Google
        ip = s.getsockname()[0]
        s.close()
        response = "Local IP: " + ip
    elif subcommand.index == 4:  # Backup
        utilities.make_backup(bot)
        await bot.send_file(message.channel, '{}/temp/backup1.zip'.format(bot.path))
    elif subcommand.index == 5:  # Restore
        try:
            location = await utilities.download_url(
                bot, message.attachments[0]['url'], extension='zip')
        except Exception as e:
            raise CBException("Failed to download the file.", e=e)
        utilities.restore_backup(bot, location)
        response = "Restored backup file."

    elif subcommand.index == 6:  # Blacklist
        blacklist = data.get(bot, 'base', 'blacklist', default=[])
        if not arguments[0]:
            response = "Blacklisted entries: {}".format(blacklist)
        else:
            user_id = arguments[0]
            if user_id in blacklist:
                data.list_data_remove(bot, 'base', 'blacklist', user_id)
                response = "User removed from blacklist."
            else:
                data.list_data_append(bot, 'base', 'blacklist', user_id)
                response = "User added to blacklist."
    elif subcommand.index == 7:  # Toggle feedback
        status = data.get(bot, 'base', 'feedbackdisabled', default=False)
        action = "enabled" if status else "disabled"
        data.add(bot, 'base', 'feedbackdisabled', not status)
        response = "Feedback has been {}.".format(action)
    elif subcommand.index == 8:  # Announcement
        if arguments[0]:
            text = '{0}:\n{1}'.format(time.strftime('%c'), arguments[0])
            data.add(bot, 'base', 'announcement', text)
            response = "Announcement set!"
        else:
            data.add(bot, 'base', 'announcement', '')
            response = "Announcement cleared!"

    return Response(content=response, message_type=message_type, extra=extra)


async def debug_wrapper(bot, context):
    message, _, subcommand, options, arguments, _, cleaned_content = context[:7]
    response, message_type, extra = ('', MessageTypes.NORMAL, None)
    global global_dictionary

    if subcommand.index == 0:  # List plugins
        plugins = list(bot.plugins.keys())
        plugins.sort()
        response = '```\n{}```'.format(plugins)

    elif subcommand.index == 1:  # Plugin information
        if options['plugin'] not in bot.plugins:
            raise CBException(options['plugin'] + " not found.")
        else:
            plugin = bot.plugins[options['plugin']]
            version = getattr(plugin, '__version__', 'Unknown')
            has_flag = getattr(plugin, 'uses_configuration', False)
            response = ("```\nPlugin information for: {0}\n"
                        "Version: {1}\nConfig: {2}\n"
                        "Dir: {3}\n```").format(
                            options['plugin'], version, has_flag, dir(plugin))

    elif subcommand.index == 2:  # Latency
        message_type = MessageTypes.ACTIVE
        response = "Testing latency time..."
        extra = ('ping', time.time() * 1000)

    elif subcommand.index == 3:  # Reset local dictionary
        _setup_debug_environment(bot)
        response = "Debug environment local dictionary reset."

    elif subcommand.index == 4:  # Repl thingy
        global_dictionary['message'] = message
        global_dictionary['bot'] = bot
        global_dictionary['channel'] = message.channel
        global_dictionary['guild'] = message.guild

        # Cleaning up input
        print("DEBUG: REPL cleaned content:", cleaned_content)
        arguments = cleaned_content[6:]
        if arguments.startswith('```py\n') and arguments.endswith('```'):
            arguments = arguments[6:-3]
        else:
            arguments = arguments.strip('`')
        pass_in = [arguments, global_dictionary]

        # Check if the previous result should be sent as a file
        if arguments in ('saf', 'file'):
            await utilities.send_text_as_file(
                message.channel, str(global_dictionary['_']), 'result')
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
                            global_dictionary['_'] = await eval(*pass_in)
                        else:
                            global_dictionary['_'] = eval(*pass_in)
                    except SyntaxError:  # May need to use exec
                        exec(*pass_in)
                        used_exec = True

            except BotException as e:
                response = str(e)
            except Exception as e:
                global_dictionary['last_exception'] = e
                global_dictionary['last_traceback'] = traceback.format_exc()
                response = '`{0}: {1}`'.format(type(e).__name__, e)

            else:  # Get response if it exists
                if used_exec:
                    result = 'Executed.'
                elif global_dictionary['_'] is None:
                    result = 'Evaluated. (returned None)'
                else:
                    result = str(global_dictionary['_'])
                if len(result) >= 1980:
                    raise CBException("Exec result is too long. (try 'file')")
                if '\n' in result:  # Better formatting
                    response = '```py\n{}```'.format(result)
                else:  # One line response
                    response = '`{}`'.format(result)

    return Response(content=response, message_type=message_type, extra=extra)


async def help_menu(bot, context, response, result, timed_out):
    if timed_out:
        invoker = utilities.get_invoker(bot, guild=context.guild)
        response.embed.add_field(
            name=":information_source: The menu timed out",
            value="Type `{}help` to start again.".format(invoker), inline=False)
        await response.message.edit(embed=response.embed)
        return
    elif not result:
        return
    selection = ['↩', '⬅', '➡', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣'].index(result[0].emoji)

    if selection == 0:  # Back
        if response.backtrack:
            previous_entry = response.backtrack.pop()
        else:
            previous_entry = [None]*3 + [0]
        response.current_state = previous_entry
        embed_details = plugins.get_help(
            bot, *previous_entry, guild=context.guild, elevation=context.elevation)

    elif selection in (1, 2):  # Page navigation
        new_page = response.current_state[3] + (1 if selection == 2 else -1)
        test_state = response.current_state[:3] + [new_page]
        embed_details = plugins.get_help(
            bot, *test_state, guild=context.guild, elevation=context.elevation)

    else:  # Entry selection
        if response.current_state[2] is not None:  # Subcommand index given
            return  # No more things to select
        elif response.current_state[1] is not None:  # Command index given
            selection_type_index = 2  # Choose subcommand
        elif response.current_state[0] is not None:  # Category ID given
            selection_type_index = 1
        else:  # Nothing given
            selection_type_index = 0  # Choose category
        page_compensation = response.current_state[3] * 5
        test_state = response.current_state[:3] + [0]
        test_state[selection_type_index] = page_compensation + selection - 3
        embed_details = plugins.get_help(
            bot, *test_state, guild=context.guild, elevation=context.elevation)
        if embed_details:  # Successful selection
            response.backtrack.append(response.current_state)
            response.current_state = test_state

    if not embed_details:
        return
    embed_fields, page, total_pages = embed_details
    response.current_state[3] = page
    response.embed.clear_fields()
    for name, value in embed_fields:
        response.embed.add_field(name=name, value=value, inline=False)
    response.embed.add_field(
        value='Page [ {} / {} ]'.format(page+1, total_pages+1), name='\u200b', inline=False)
    await response.message.edit(embed=response.embed)


async def manual_menu(bot, context, response, result, timed_out):
    if timed_out:
        invoker = utilities.get_invoker(bot, guild=context.guild)
        response.embed.add_field(
            name=":information_source: The menu timed out",
            value="Type `{}manual` to start again.".format(invoker), inline=False)
        await response.message.edit(embed=response.embed)
        return
    elif not result:
        return
    selection = ['↩', '⬅', '➡', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣'].index(result[0].emoji)

    if selection == 0:  # Back
        if response.backtrack:
            previous_entry = response.backtrack.pop()
        else:
            previous_entry = [None]*3
        response.current_state = previous_entry
        embed_details = plugins.get_manual(bot, *previous_entry)
        assert embed_details  # TODO: Remove debug

    elif selection in (1, 2):  # Page navigation
        new_page = response.current_state[2] + (1 if selection == 2 else -1)
        test_state = response.current_state[:2] + [new_page]
        embed_details = plugins.get_manual(bot, *test_state)
        if not embed_details:  # Ignore page change failure
            return

    else:  # Entry selection
        if response.current_state[1] is not None:  # Topic given
            return  # No more things to select
        elif response.current_state[0] is not None:  # Subject given
            selection_type_index = 1  # Choose topic
        else:  # Nothing given
            selection_type_index = 0  # Choose subject
        page_compensation = response.current_state[2] * 5
        test_state = response.current_state[:2] + [0]
        test_state[selection_type_index] = page_compensation + selection - 3
        embed_details = plugins.get_manual(bot, *test_state)
        if embed_details:  # Successful selection
            response.backtrack.append(response.current_state)
            response.current_state = test_state
        else:  # Ignore selection failure
            return

    crumbs, text, page, total_pages = embed_details
    response.current_state[2] = page
    response.embed.set_field_at(0, name=crumbs, value=text, inline=False)
    response.embed.set_field_at(
        1, value='Page [ {} / {} ]'.format(page+1, total_pages+1), name='\u200b', inline=False)
    await response.message.edit(embed=response.embed)


# TODO: FIX FIX FIX
async def help_wrapper(bot, context):
    message, _, subcommand, options, arguments = context[:5]
    response = Response()
    # response, tts, message_type, extra = ('', False, 0, None)
    is_owner = data.is_owner(bot, message.author.id)
    help_here = 'here' in options

    if subcommand.index == 0:  # Manual
        if arguments[0]:  # Load from given state
            # TODO: detect if subject is an int
            try:
                subject_test = int(arguments[0]) - 1
            except:
                subject_test = arguments[0]
            if arguments[1] is not None:
                arguments[1] -= 1
            if arguments[2] is not None:
                arguments[2] -= 1
            state = [subject_test, arguments[1], arguments[2]]
            embed_details = plugins.get_manual(bot, *state, safe=False)
        else:  # Load menu from scratch
            embed_details = plugins.get_manual(bot)
            state = [None]*3
        assert embed_details  # TODO: Remove debug
        crumbs, text, page, total_pages = embed_details
        state[2] = page
        response.backtrack = []
        response.current_state = state
        embed = discord.Embed(title=':page_facing_up: Manual', colour=discord.Colour(0xccd6dd))
        embed.add_field(name=crumbs, value=text, inline=False)
        embed.add_field(
            value='Page [ {} / {} ]'.format(page+1, total_pages+1), name='\u200b', inline=False)
        response.message_type = MessageTypes.INTERACTIVE
        response.extra_function = manual_menu
        response.extra = {'buttons': ['↩', '⬅', '➡', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣']}
        response.embed = embed

    elif subcommand.index == 1:  # All help
        response.content = "Serving up all the help:"
        base_list = []
        for command in bot.commands.values():
            if isinstance(command, Command):
                if not command.hidden or context.elevation >= 3:
                    base_list.append(command)
        base_list.sort()
        help_list = ["### Command quick-reference ###\r\n"]
        for command in base_list:
            help_list.append(command.clean_quick_help.replace('\n', '\r\n'))
        help_list.append("\r\n\r\n### Individual command reference ###")
        for command in base_list:
            help_list.append("\r\n# {} #".format(command.base))
            help_list.append(
                "\t" + command.clean_help_string.replace('\n', '\r\n\t'))
        help_text = '\r\n'.join(help_list)
        help_file = discord.File(utilities.get_text_as_file(help_text), filename='help.txt')
        response.content = "Here is all of the help as a file:"
        response.file = help_file

    elif subcommand.index == 2:  # Help
        response.embed = discord.Embed(
            title=':grey_question: Help', colour=discord.Colour(0xccd6dd))
        if arguments[0]:  # Specified help
            guess = None
            if arguments[1]:
                try:
                    command = bot.commands[arguments[0].lower()]
                    index = int(arguments[1]) - 1
                    assert 0 <= index < len(command.subcommands)
                    guess = command.subcommands[index]
                except:  # Ignore invalid index or shortcut
                    pass
            if guess is None:
                text = arguments[0] + ' ' + arguments[1]
                guess = parser.guess_command(
                    bot, text, message, safe=False, substitue_shortcuts=False)
            for name, value in guess.help_embed_fields:
                response.embed.add_field(name=name, value=value, inline=False)
            help_here = True
        else:  # Help menu
            state = [None]*3 + [0]
            invoker = utilities.get_invoker(bot, guild=context.guild)
            embed_fields, page, total_pages = plugins.get_help(
                bot, *state, guild=message.guild, elevation=context.elevation)
            for name, value in embed_fields:
                response.embed.add_field(name=name, value=value, inline=False)
            response.embed.add_field(
                value='Page [ {} / {} ]'.format(page+1, total_pages+1),
                name='\u200b', inline=False)
            response.embed.set_footer(
                text='Confused about the syntax? Read {}manual core 3'.format(invoker))
            response.backtrack = []
            response.current_state = state
            response.message_type = MessageTypes.INTERACTIVE
            response.extra_function = help_menu
            response.extra = {'buttons': ['↩', '⬅', '➡', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣']}

    # TODO: Fix with response.destination later
    if not (context.direct or help_here or bot.selfbot):
        try:
            await message.add_reaction('📨')  # Envelope reaction
        except:
            pass
        response.destination = context.author

    return response


async def get_response(bot, context):
    if context.base == 'ping':
        if context.arguments:
            response = 'Pong!\n{}'.format(context.arguments[0])
        else:
            response = 'Pong!'
    else:
        response = "This should not be seen. Your command was: " + base
    return Response(content=response)


async def handle_active_message(bot, context, response, message_reference):
    """
    This function is called if the given message was marked as active
    (message_type of 3).
    """
    if response.extra[0] == 'ping':
        latency_time = "Latency time: {:.2f} ms".format((time.time() * 1000) - response.extra[1])
        await message_reference.edit(content=latency_time)

    elif response.extra[0] == 'reload':

        # Preliminary check
        plugins_to_reload = []
        if extra[1]:
            for plugin_name in extra[1]:
                if plugin_name in bot.plugins:
                    plugins_to_reload.append(plugin_name)
                else:
                    raise CBException("Invalid plugin.", plugin_name)
        else:
            plugins_to_reload = bot.plugins.keys()

        data.save_data(bot)  # Safety save
        logging.debug("Reloading plugins and commands...")

        # Cancel running tasks associated with plugins
        tasks = asyncio.Task.all_tasks()
        pattern = re.compile('([^/(:\d>$)])+(?!.*\/)')
        for plugin_name in plugins_to_reload:
            for task in tasks:
                callback_info = task._repr_info()[1]
                plugin_name_test = pattern.search(callback_info).group(0)
                if plugin_name_test == plugin_name:
                    logging.debug("Canceling task: {}".format(task))
                    task.cancel()
            plugins.load_plugin(bot, plugin_name)

        bot.volatile_data = {'global_users': {}, 'global_plugins': {}}
        data.check_all(bot)

        for plugin_name in plugins_to_reload:
            plugin = bot.plugins[plugin_name]
            if hasattr(plugin, 'bot_on_ready_boot'):
                asyncio.ensure_future(plugin.bot_on_ready_boot(bot))
            if hasattr(plugin, 'on_ready'):
                asyncio.ensure_future(plugin.on_ready(bot))
        await message_reference.edit(content='Reloaded {} plugin{}.'.format(
            len(plugins_to_reload), '' if len(plugins_to_reload) == 1 else 's'))


def _setup_debug_environment(bot):
    """Resets the local dictionary for the debug command."""
    global global_dictionary
    import pprint
    import jshbot

    def say(*args, **kwargs):
        message = global_dictionary.get('message')
        task = asyncio.ensure_future(message.channel.send(*args, **kwargs))
        def f(future):
            global_dictionary['_'] = future.result()
        task.add_done_callback(f)
    async def asay(*args, **kwargs):
        message = global_dictionary.get('message')
        return await message.channel.send(*args, **kwargs)

    global_dictionary = {
        'bot': bot,
        'inspect': inspect,
        'traceback': traceback,
        'last_traceback': None,
        'last_exception': None,
        '_': None,
        'say': say,
        'asay': asay,
        'pformat': pprint.pformat,
        'random': random,
        'time': time,
        're': re,
        'discord': discord,
        'jbu': utilities,
        'jbd': data,
        'jb': jshbot
    }


# Standard discord.py event functions

async def bot_on_ready_boot(bot):
    """Sets up permissions and the debug environment."""
    _setup_debug_environment(bot)
    permissions = {
        'read_messages': "Standard.",
        'send_messages': "Standard.",
        'manage_messages': "Deletes messages of certain commands (like `help`).",
        'attach_files': "Uploads responses longer than 2000 characters long as a text file.",
        'read_message_history': "Gets chat context when bot moderators change settings.",
        'connect': "Allows the bot to connect to voice channels. (Framework)",
        'speak': "Allows the bot to speak. (Framework)"
    }
    utilities.add_bot_permissions(bot, 'base', **permissions)


async def on_guild_join(bot, guild):
    # Add guild to the list
    logging.debug("Joining guild")
    data.add_guild(bot, guild)
    if bot.selfbot:  # Don't send DMs if in selfbot mode
        return
    invoker = utilities.get_invoker(bot)
    text = (
        "Hello! You are receiving this notification because this bot was "
        "added to one of your servers, specifically '{0.name}' (ID: {0.id}). "
        "If you are aware of this and approve of the addition, feel free to "
        "continue and use the bot. However, if you did not approve of this "
        "addition, it is highly recommended you kick or ban this bot as there "
        "may be potential for users to use the bot to spam. Only users that "
        "have the administrator permission can add bots to servers. "
        "Unfortunately, there is no way to track who added the bot.\n\n"
        "To read more about the functionality and usage of the bot, type "
        "`{1}manual` to see a list of topics, and `{1}help` to see a list of "
        "commands. **As a server owner, it is highly recommended that you "
        "read `{1}manual 5` and `{1}manual 4` for moderating and configuring "
        "the bot.**\n\nThat's all for now. If you have any questions, please "
        "refer to the manual, or send the bot owners a message using "
        "`{1}owner feedback <message>`.\n\nCheck out the Wiki for more: "
        "https://github.com/jkchen2/JshBot/wiki").format(guild, invoker)
    await guild.owner.send(text)


async def on_message_edit(bot, before, after):
    """Integrates with the core to handle edited messages."""
    if before.content != after.content and str(before.id) in bot.edit_dictionary:
        message_reference = bot.edit_dictionary.pop(str(before.id))
        await bot.on_message(after, replacement_message=message_reference)


async def on_error(bot, event, *args, **kwargs):
    """Gets uncaught exceptions."""
    logging.error(
        "An exception was thrown that wasn't handled by the core. \n"
        "Event: {0}\nargs: {1}\nkwargs: {2}".format(event, args, kwargs))
    traceback.print_exc()
