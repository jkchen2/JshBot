import asyncio
import discord
import random
import socket
import logging
import datetime
import time
import inspect
import traceback
import yaml
import shutil
import pip
import os
import re

from logging.handlers import RotatingFileHandler

from distutils.dir_util import copy_tree
from discord.abc import PrivateChannel

from jshbot import parser, data, utilities, commands, plugins, configurations, logger
from jshbot.exceptions import BotException, ConfiguredBotException
from jshbot.commands import (
    Command, SubCommand, Shortcut, ArgTypes, Arg, Opt, Attachment,
    MessageTypes, Response)

__version__ = '0.2.6'
uses_configuration = False
CBException = ConfiguredBotException('Base')
global_dictionary = {}

# Debugging
DEV_BOT_ID = 171672297017573376


@plugins.command_spawner
def get_commands(bot):
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
            SubCommand(
                Opt('announcement'), doc='Gets the current announceent set by the bot owners.'),
            SubCommand(
                Opt('invite'),
                Opt('details', optional=True,
                    doc='Shows a breakdown of what each permission is used for'),
                doc='Generates an invite for the bot.'),
            SubCommand(
                Opt('notifications'),
                doc='If this command is used in a server, this will list the pending '
                    'notifications for the channel you are in. If it is used in a '
                    'direct message, this will list the pending notifications for you.'),
            SubCommand(
                Opt('join'), doc='Have the bot join the voice channel you are in.',
                allow_direct=False),
            SubCommand(
                Opt('leave'), doc='Have the bot leave the voice channel you are in.',
                allow_direct=False)],
        shortcuts = [
            Shortcut('announcement', 'announcement'),
            Shortcut('invite', 'invite'),
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
                Arg('command', quotes_recommended=False),
                Arg('specifier', argtype=ArgTypes.MERGED_OPTIONAL,
                    doc='The index of the subcomand, or subcommand arguments.'),
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
                Opt('invoker'),
                Arg('custom invoker', argtype=ArgTypes.MERGED_OPTIONAL,
                    check=lambda b, m, v, *a: len(v) <= 10,
                    check_error='The invoker can be a maximum of 10 characters long.'),
                doc='Sets or clears the custom invoker.'),
            SubCommand(
                Opt('mention'), doc='Toggles mention mode. If enabled, the bot '
                    'will only respond to its name or mention as an invoker.'),
            SubCommand(
                Opt('cooldown'),
                Arg('number of commands', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=int, check=lambda b, m, v, *a: 1 <= v <= b.spam_limit,
                    check_error='Must be between 1 and {b.spam_limit} inclusive.'),
                doc='Limits the number of commands per default time interval to the '
                    'value specified. Bot moderators are not subject to this limit. If '
                    'no value is given, the default cooldown is used (maximum value).'),
            SubCommand(
                Opt('timezone'),
                Arg('offset', quotes_recommended=False, argtype=ArgTypes.OPTIONAL,
                    convert=int, check=lambda b, m, v, *a: -12 <= v <= 12,
                    check_error='Must be between -12 and +12',
                    doc='A UTC hours offset (-12 to +12).'),
                doc='Sets or clears the bot\'s timezone interpretation for the server.')],
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
            SubCommand(
                Opt('reload'),
                Arg('plugin', argtype=ArgTypes.SPLIT_OPTIONAL, additional='additional plugins'),
                doc='Reloads the specified plugin(s), or all external plugins.'),
            SubCommand(Opt('ip'), doc='Gets the local IP address of the bot.'),
            SubCommand(Opt('backup'), doc='Gets the data folder as a zip file.'),
            SubCommand(
                Opt('restore'), Attachment('restore zip file'),
                doc='Downloads the restore zip file and replaces current data files with '
                    'the contents of the backup.'),
            SubCommand(
                Opt('restoredb'),
                Arg('table', argtype=ArgTypes.SPLIT_OPTIONAL, additional='additional tables',
                    doc='Restores the given specific tables.'),
                Attachment('db_dump file'),
                doc='Loads the database dump and restores either the entire database, or the '
                    'specified tables.'),
            SubCommand(
                Opt('blacklist'),
                Arg('user', argtype=ArgTypes.MERGED_OPTIONAL,
                    convert=utilities.MemberConverter(server_only=False)),
                doc='Blacklist or unblacklist a user from sending feedback. If no '
                    'user is specified, this lists all blacklisted entries.'),
            SubCommand(Opt('togglefeedback'), doc='Toggles the feedback command.'),
            SubCommand(
                Opt('announcement'), Arg('text', argtype=ArgTypes.MERGED_OPTIONAL),
                doc='Sets or clears the announcement text.'),
            SubCommand(Opt('update'), doc='Opens the bot update menu.')],
        shortcuts=[
            Shortcut(
                'reload', 'reload {arguments}',
                Arg('arguments', argtype=ArgTypes.MERGED_OPTIONAL))],
        description='Commands for the bot owner(s).',
        hidden=True, elevated_level=3, category='core', function=botowner_wrapper))

    new_commands.append(Command(
        'debug', subcommands=[
            SubCommand(Opt('plugin'), Opt('list'), doc='Lists loaded plugins.'),
            SubCommand(
                Opt('plugin', attached='plugin name'),
                doc='Gets basic information about the given plugin.'),
            SubCommand(Opt('latency'), doc='Calculates the ping time.'),
            SubCommand(Opt('logs'), doc='Uploads logs to the debug channel.'),
            SubCommand(Opt('toggle'), doc='Toggles the debug mode.'),
            SubCommand(Opt('resetlocals'), doc='Resets the debug local variables.'),
            SubCommand(
                Arg('python', argtype=ArgTypes.MERGED),
                doc='Evaluates or executes the given code.')],
        description='Commands to help the bot owner debug stuff.',
        other='Be careful with these commands! They can break the bot.',
        hidden=True, elevated_level=3, category='core', function=debug_wrapper))

    new_commands.append(Command(
        'help', subcommands=[
            SubCommand(
                Opt('manual'), Opt('here', optional=True),
                Arg('subject', argtype=ArgTypes.OPTIONAL, default=''),
                Arg('topic number', argtype=ArgTypes.OPTIONAL, convert=int,
                    check=lambda b, m, v, *a: v > 0, check_error='Must be a positive number.',
                    quotes_recommended=False),
                Arg('page number', argtype=ArgTypes.OPTIONAL, convert=int,
                    check=lambda b, m, v, *a: v > 0, check_error='Must be a positive number.',
                    quotes_recommended=False),
                doc='Gets the specified manual. If no subject is specified, this '
                    'brings up the general manual menu.'),
            SubCommand(
                Opt('all'), Opt('here', optional=True),
                doc='Shows all of the commands and related help.'),
            SubCommand(
                Opt('here', optional=True),
                Arg('base', argtype=ArgTypes.OPTIONAL, quotes_recommended=False),
                Arg('topic', argtype=ArgTypes.MERGED_OPTIONAL, default='',
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
def get_templates(bot):
    """Gets the timer database template."""
    return {
        'schedule': ("time          bigint NOT NULL,"
                     "plugin        text NOT NULL,"
                     "function      text NOT NULL,"
                     "payload       text,"
                     "search        text,"
                     "destination   text,"
                     "info          text")
    }

@plugins.on_load
def setup_schedule_table(bot):
    data.db_create_table(bot, 'schedule', template='schedule')
    if not data.db_exists(bot, 'IX_schedule_time'):  # Create time index
        data.db_execute(bot, 'CREATE INDEX IX_schedule_time ON schedule (time ASC)')


async def base_wrapper(bot, context):
    message, _, subcommand, options = context[:4]
    response = Response()

    if subcommand.index == 0:  # version
        response.content = '`{}`\n{}'.format(bot.version, bot.date)

    elif subcommand.index == 1:  # source
        response.content = random.choice([
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
        response.content += ("\nhttps://github.com/jkchen2/JshBot\n"
                     "https://github.com/jkchen2/JshBot-plugins")

    elif subcommand.index == 2:  # uptime
        uptime = int(time.time()) - bot.time
        response.content = "The bot has been on since **{}**\n{}".format(
            bot.readable_time, utilities.get_time_string(uptime, text=True, full=True))

    elif subcommand.index == 3:  # Announcement
        announcement = data.get(bot, 'core', 'announcement')
        if not announcement:
            response.content = "No announcement right now!"
        else:
            response.embed = discord.Embed(
                title=":mega: Announcement", description=announcement[0],
                timestamp=datetime.datetime.utcfromtimestamp(announcement[1]),
                colour=discord.Colour(0x55acee))

    elif subcommand.index == 4:  # Invite
        if bot.selfbot:
            raise CBException("Nope.")

        permissions_number = utilities.get_permission_bits(bot)
        app_id = (await bot.application_info()).id
        authorization_link = (
            '**[`Authorization link`](https://discordapp.com/oauth2/authorize?'
            '&client_id={0}&scope=bot&permissions={1})\nRemember: you must have the '
            '`Administrator` role on the server you are trying to add the '
            'bot to.**'.format(app_id, permissions_number))
        response.embed = discord.Embed(
            title=':inbox_tray: Invite', colour=discord.Colour(0x77b255),
            description=authorization_link)

        if 'details' in options:
            for plugin in bot.plugins.keys():
                permission_items = data.get(
                    bot, plugin, 'permissions', volatile=True, default={}).items()
                if permission_items:
                    plugin_permissions = '\n'.join(
                        ['**`{0[0]}`** -- {0[1]}'.format(item)
                            for item in permission_items])
                    response.embed.add_field(name=plugin, value=plugin_permissions)

    elif subcommand.index == 5:  # Notifications
        if context.direct:  # List user notifications
            destination = 'u' + str(context.author.id)
            specifier = 'you'
            guild_id = None
        else:  # List channel notifications:
            destination = 'c' + str(context.channel.id)
            specifier = 'this channel'
            guild_id = context.guild.id
        notifications = utilities.get_schedule_entries(
            bot, None, custom_match='destination=%s', custom_args=[destination])
        if notifications:
            results = ['Here is a list of pending notifications for {}:\n'.format(specifier)]
            for entry in notifications:
                time_seconds, plugin, info = entry[0], entry[1], entry[6]
                delta = utilities.get_time_string(time_seconds - time.time(), text=True)
                offset, scheduled = utilities.get_timezone_offset(
                    bot, guild_id=guild_id, as_string=True,
                    utc_dt=datetime.datetime.utcfromtimestamp(time_seconds))
                results.append('{} [{}] ({}) from plugin `{}`: {}'.format(
                    scheduled, offset, delta, plugin,
                    info if info else '(No description available)'))
            response.content = '\n'.join(results)
        else:
            response.content = "No pending notifications for {}.".format(specifier)

    elif subcommand.index in (6, 7):  # Join/leave voice channel
        if not message.author.voice:
            raise CBException("You are not in a voice channel.")
        try:
            voice_channel = message.author.voice.channel
            if subcommand.index == 6:
                await utilities.join_and_ready(
                    bot, voice_channel, reconnect=True, is_mod=data.is_mod(
                        bot, message.guild, message.author.id))
                response.content = "Joined {}.".format(voice_channel.name)
            else:
                await utilities.leave_and_stop(
                    bot, message.guild, member=message.author, safe=False)
                response.content = "Left {}.".format(voice_channel.name)
        except BotException as e:
            raise e  # Pass up
        except Exception as e:
            action = 'join' if subcommand.index == 6 else 'leave'
            raise CBException("Failed to {} the voice channel.".format(action), e=e)

    return response


async def mod_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    response = ''
    mod_action = ''

    if subcommand.index == 0:  # info
        guild_data = data.get(
            bot, 'core', None, guild_id=message.guild.id, default={})
        guild_volatile_data = data.get(
            bot, 'core', None, guild_id=message.guild.id, default={}, volatile=True)
        disabled_commands = guild_data.get('disabled', [])
        display_list = []
        for disabled_command in disabled_commands:
            display_list.append('{0} ({1})'.format(
                disabled_command[0],
                'all' if disabled_command[1] == -1 else disabled_command[1]+1))
        cooldown_message = "{} command(s) per {} seconds(s)".format(
            guild_data.get('spam_limit', bot.spam_limit), bot.spam_timeout)
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

    elif subcommand.index == 1:  # Toggle command
        index_guess = -1  # All
        guess_text = '{} '.format(arguments[0])
        if arguments[1]:  # Given the index or subcommand
            if arguments[1].isdigit():
                index_guess = int(arguments[1]) - 1
            else:
                guess_text += arguments[1]
            pass
        guess = await parser.guess_command(bot, guess_text, message, safe=False)
        if isinstance(guess, Command):  # No subcommand found
            if not -1 <= index_guess < len(guess.subcommands):
                raise CBException(
                    "Invalid subcommand index. Must be between 1 and {} inclusive, "
                    "or 0 to toggle all subcommands.".format(len(guess.subcommands)))
        else:  # Subcommand
            index_guess = guess.index
            guess = guess.command

        # Display disabled command and potentially subcommand
        if guess.category == 'core':
            raise CBException("The core commands cannot be disabled.")
        subcommand = guess.subcommands[index_guess] if index_guess != -1 else None
        toggle = [guess.base, index_guess]
        pass_in = (bot, 'core', 'disabled', toggle)
        pass_in_keywords = {'guild_id': message.guild.id}
        disabled_commands = data.get(*pass_in[:-1], **pass_in_keywords, default=[])
        if toggle in disabled_commands:
            function = data.list_data_remove
            response = "Enabled"
        else:
            function = data.list_data_append
            response = "Disabled"
        function(*pass_in, **pass_in_keywords)
        if index_guess == -1:
            response += " all `{}` subcommands.".format(guess.base)
        else:
            response += " the \t{}\t subcommand.".format(subcommand.help_string)
        mod_action = response

    elif subcommand.index in (2, 3):  # Block or unblock
        user = arguments[0]
        block = subcommand.index == 2
        mod_action = 'Blocked {}' if block else 'Unblocked {}'
        mod_action = mod_action.format('{0} ({0.id})'.format(user))
        blocked = data.is_blocked(bot, message.guild, user.id, strict=True)
        mod = data.is_mod(bot, message.guild, user.id)
        if mod:
            raise CBException("Cannot block or unblock a moderator.")
        elif block:
            if blocked:
                raise CBException("User is already blocked.")
            else:
                data.list_data_append(bot, 'core', 'blocked', user.id, guild_id=message.guild.id)
                response = "User is now blocked."
        else:
            if not blocked:
                raise CBException("User is already unblocked.")
            else:
                data.list_data_remove(bot, 'core', 'blocked', user.id, guild_id=message.guild.id)
                response = "User is now unblocked."

    elif subcommand.index == 4:  # Clear
        response = '\u200b' + '\n'*80 + "The chat was pushed up by a bot moderator."

    elif subcommand.index in (5, 6):  # Mute or unmute
        guild_id = message.guild.id
        mute = subcommand.index == 5
        mod_action = 'Muted {}' if mute else 'Unmuted {}'

        if arguments[0]:
            channel = arguments[0]
            muted = channel.id in data.get(
                bot, 'core', 'muted_channels', guild_id=guild_id, default=[])
            mod_action = mod_action.format(channel.name)
            if mute:
                if muted:
                    raise CBException("Channel is already muted.")
                else:
                    data.list_data_append(
                        bot, 'core', 'muted_channels', channel.id, guild_id=guild_id)
                    if isinstance(channel, discord.VoiceChannel):  # disconnect
                        await utilities.leave_and_stop(bot, message.guild)
                    response = "Channel muted."
            else:  # unmute
                if not muted:
                    raise CBException("Channel is already unmuted.")
                else:
                    data.list_data_remove(
                        bot, 'core', 'muted_channels', channel.id, guild_id=guild_id)
                    response = "Channel unmuted."

        else:  # guild
            mod_action = mod_action.format('the server')
            muted = data.get(bot, 'core', 'muted', guild_id=guild_id, default=False)
            if not (muted ^ mute):
                response = "Server is already {}muted.".format('' if muted else 'un')
                raise CBException(response)
            else:
                data.add(bot, 'core', 'muted', mute, guild_id=guild_id)
                response = "Server {}muted.".format('' if mute else 'un')

    elif subcommand.index == 7:  # Invoker
        data.add(
            bot, 'core', 'command_invoker',
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
            bot, 'core', 'mention_mode', guild_id=message.guild.id, default=False)
        data.add(bot, 'core', 'mention_mode', not current_mode, guild_id=message.guild.id)
        response = "Mention mode {}activated.".format('de' if current_mode else '')
        mod_action = "{}activated mention mode.".format('de' if current_mode else '').capitalize()

    elif subcommand.index == 9:  # Cooldown
        cooldown = arguments[0]
        if cooldown:
            data.add(bot, 'core', 'spam_limit', cooldown, guild_id=message.guild.id)
            cooldown_message = (
                "{} command(s) per {} seconds(s)".format(cooldown, bot.spam_timeout))
            response = "Cooldown set to {}.".format(cooldown_message)
            mod_action = "set the cooldown to {}.".format(cooldown_message)
        else:
            data.remove(bot, 'core', 'spam_limit', guild_id=message.guild.id, safe=True)
            cooldown_message = (
                "{} command(s) per {} seconds(s)".format(bot.spam_limit, bot.spam_timeout))
            response = "Cooldown reset to the default {}.".format(cooldown_message)
            mod_action = "reset the cooldown to the default {}.".format(cooldown_message)

    elif subcommand.index == 10:  # Set timezone
        if isinstance(arguments[0], int):  # Set timezone
            data.add(bot, 'core', 'timezone', arguments[0], guild_id=context.guild.id)
            response = "Timezone set to UTC{}.".format(
                ('+' + str(arguments[0])) if arguments[0] >= 0 else arguments[0])
            mod_action = "set the timezone: {}".format(response)
        else:  # Clear timezone
            data.remove(bot, 'core', 'timezone', guild_id=context.guild.id, safe=True)
            guess = utilities.get_timezone_offset(bot, context.guild.id, as_string=True)
            response = (
                "Timezone cleared. Time will be interpreted based off of voice "
                "server location instead. Current guess: ({})".format(guess))
            mod_action = "cleared the custom timezone offset."

    # Send notification if configured
    send_notifications = data.get(
        bot, 'core', 'notifications', guild_id=message.guild.id, default=True)
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


async def owner_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    mod_action = ''

    send_notifications = data.get(
        bot, 'core', 'notifications', guild_id=message.guild.id, default=True)

    if subcommand.index == 0:  # Change moderator role
        role = arguments[0]
        if role:
            response = mod_action = 'Set the bot moderator role to {}.'.format(role)
            data.add(bot, 'core', 'modrole', role.id, guild_id=message.guild.id)
            data.add(bot, 'core', 'modrole', role, guild_id=message.guild.id, volatile=True)
        else:
            response = mod_action = 'Removed the bot moderator role.'
            data.remove(bot, 'core', 'modrole', guild_id=message.guild.id, safe=True)
            data.remove(
                bot, 'core', 'modrole', guild_id=message.guild.id, volatile=True, safe=True)

    elif subcommand.index == 1:  # Send feedback
        if data.get(bot, 'core', 'feedbackdisabled', default=False):
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
            bot, 'core', 'notifications', not send_notifications, guild_id=message.guild.id)

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


# Update related
def _compare_config(bot, plugin, file_path):
    try:
        comparison = bot.configurations[plugin]
    except:
        logger.warn("Configuration file for plugin %s exists, but is not loaded.", plugin)
        with open('{}/config/{}-config.yaml'.format(bot.path, plugin[:-3]), 'rb') as config_file:
            comparison = yaml.load(config_file)
    with open(file_path, 'rb') as config_file:
        test_config = yaml.load(config_file)
    changes = []
    for key, value in test_config.items():
        if key not in comparison:
            changes.append("Missing entry: " + key)
        elif type(value) is not type(comparison[key]):
            changes.append("Type mismatch for entry: " + key)
    return changes

async def _update_core(bot, progress_function):
    if bot.user.id == DEV_BOT_ID:
        raise CBException("Dev bot - cancelled core update")
    await progress_function('Downloading core package...')
    core_repo = 'https://github.com/jkchen2/JshBot/archive/master.zip'
    archive_path = await utilities.download_url(bot, core_repo, filename='core.zip')
    update_directory = bot.path + '/temp/update/'
    try:
        shutil.rmtree(update_directory)
    except Exception as e:
        logger.warn("Failed to clear the update directory: %s", e)
    await progress_function('Installing core...')
    shutil.unpack_archive(archive_path, update_directory)
    update_directory += 'JshBot-master/config/'
    config_directory = bot.path + '/config/'
    shutil.copy2(update_directory + 'core-manual.yaml', config_directory + 'core-manual.yaml')
    changes = _compare_config(bot, 'core', update_directory + 'core-config.yaml')
    if changes:
        return changes
    pip.main([
        'install',
        '--upgrade',
        '--force-reinstall',
        '--process-dependency-links',
        archive_path])
    await asyncio.sleep(1)
    await progress_function('Core updated.')


async def _download_plugins(bot, progress_function):
    await progress_function("Downloading plugins...")
    plugins_repo = 'https://github.com/jkchen2/JshBot-plugins/archive/master.zip'
    archive_path = await utilities.download_url(bot, plugins_repo, filename='plugins.zip')
    await progress_function("Unpacking plugins...")

    # Extract and return plugins list
    update_directory = bot.path + '/temp/update/'
    try:
        shutil.rmtree(update_directory)
    except Exception as e:
        logger.warn("Failed to clear the update directory: %s", e)
    shutil.unpack_archive(archive_path, update_directory)
    update_directory += 'JshBot-plugins-master'
    available_updates = []
    for entry in os.listdir(update_directory):
        if os.path.isdir('{}/{}'.format(update_directory, entry)):
            available_updates.append(entry + '.py')
    await asyncio.sleep(1)
    await progress_function("Plugins unpacked.")
    return sorted(available_updates)


async def _update_plugins(bot, plugin_list, progress_function):
    if bot.user.id == DEV_BOT_ID:
        raise CBException("Dev bot - cancelled core update")
    await progress_function('Updating plugins...')
    config_changed = {}
    update_directory = bot.path + '/temp/update/JshBot-plugins-master/'
    plugins_directory = bot.path + '/plugins/'
    config_directory = bot.path + '/config/'
    for plugin in plugin_list:
        directory = update_directory + plugin[:-3]
        for entry in os.listdir(directory):
            entry_path = directory + '/' + entry

            if entry.lower() == 'requirements.txt':  # Install plugin requirements
                await progress_function('Installing requirements for {}...'.format(plugin))
                pip.main(['install', '--upgrade', '-r', entry_path])
                await asyncio.sleep(1)
                continue

            if entry in (plugin, 'plugin_data'):  # plugin_data or plugin itself
                if entry == 'plugin_data':
                    copy_tree(entry_path, plugins_directory + 'plugin_data')
                else:
                    shutil.copy2(entry_path, plugins_directory)

            elif entry.startswith(plugin[:-3] + '-'):
                if entry in os.listdir(config_directory):  # Check existing config
                    if entry.endswith('-config.yaml'):
                        changes = _compare_config(bot, plugin, entry_path)
                        if changes:
                            config_changed[plugin] = changes
                else:  # Copy config over
                    shutil.copy2(entry_path, config_directory)

            else:
                logger.debug("Ignoring entry: %s", entry_path)

        logger.debug('Updated ' + plugin)

    await asyncio.sleep(1)
    await progress_function('Plugins updated.')
    return config_changed


async def update_menu(bot, context, response, result, timed_out):
    if timed_out or (result and result[0].emoji == '❌'):
        response.embed.clear_fields()
        response.embed.add_field(name='Update cancelled', value='\u200b')
        response.embed.set_footer(text='---')
        await response.message.edit(embed=response.embed)
        return False
    elif not result:
        return

    async def _progress_function(status_message):
        response.embed.set_footer(text=status_message)
        try:
            await response.message.edit(embed=response.embed)
        except Exception as e:
            logger.warn("Failed to update the update embed: %s", e)

    selection = ['⬆', '⬇', '🇦', '🇧'].index(result[0].emoji)
    if selection in (0, 1):  # Navigation
        if response.stage != 1:  # Ignore selection
            return
        offset = 1 if selection else -1
        response.selection_index = max(
            min(response.selection_index + offset, len(response.updates)), 0)

    else:  # Action
        if response.stage == 0:  # First choice
            if selection == 2:  # Update core
                response.stage = 10
                changed = await _update_core(bot, _progress_function)
            else:  # Download plugins
                response.stage = 1
                response.updates = await _download_plugins(bot, _progress_function)
                for index, update in enumerate(response.updates):
                    if update in response.plugin_list:
                        response.selected.append(index)
                await asyncio.sleep(1)

        elif response.stage == 1:  # Plugins selected
            if selection == 2:  # Toggle selection
                if response.selection_index in response.selected:
                    response.selected.remove(response.selection_index)
                else:
                    response.selected.append(response.selection_index)

            else:  # Start update
                if not response.selected:  # None selected
                    return
                response.stage = 2
                update_list = [response.updates[it] for it in response.selected]
                changed = await _update_plugins(bot, update_list, _progress_function)
                await asyncio.sleep(1)

    tooltip = None
    if response.stage == 10:  # Core finished updating
        if changed:
            title = 'Core config file issue(s) detected'
            result = '\n'.join(changed)
            response.embed.set_footer(text='Core update interrupted.')
        else:
            title = 'Core updated'
            result = 'No issues detected. Restart to complete update.'

    elif response.stage == 1:  # Select plugins
        title = 'Select plugins'
        result_list = []
        for index, plugin in enumerate(response.updates):
            arrow = '→ ' if index == response.selection_index else '\u200b\u3000 '
            wrap, tick = ('**', '> ') if index in response.selected else ('', '')
            result_list.append('{0}{1}`{2}{3}`{1}'.format(arrow, wrap, tick, plugin))
        result = '\n'.join(result_list)
        tooltip = ['Toggle selection', 'Update selected']

    elif response.stage == 2:  # Finished updating plugins
        if changed:
            title = 'Config file issue(s) detected'
            result_list = []
            for plugin, issues in changed.items():
                result_list.append('{}:\n\t{}'.format(plugin, '\t\n'.join(issues)))
            result = '\n'.join(result_list)
        else:
            title = 'Plugins updated'
            result = 'No issues detected. Restart to complete update.'

    if title:
        response.embed.set_field_at(0, name=title, value=result, inline=False)
    if tooltip:
        tooltip = ':regional_indicator_a: : {}\n:regional_indicator_b: : {}'.format(*tooltip)
    else:
        tooltip = '\u200b'
    response.embed.set_field_at(1, name='\u200b', value=tooltip, inline=False)

    await response.message.edit(embed=response.embed)
    if response.stage in (10, 2):  # Finish update
        return False


async def botowner_wrapper(bot, context):
    message, _, subcommand, _, arguments = context[:5]
    response = Response()

    if subcommand.index == 0:  # Halt
        await message.channel.send("Going down...")
        bot.shutdown()

    elif subcommand.index == 1:  # Reload
        response.content = "Reloading..."
        response.message_type = MessageTypes.ACTIVE
        response.extra_function = handle_active_message
        response.extra = ('reload', arguments)

    elif subcommand.index == 2:  # IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # Thanks Google
        ip = s.getsockname()[0]
        s.close()
        response.content = "Local IP: " + ip

    elif subcommand.index == 3:  # Backup
        utilities.make_backup(bot)
        response.content = "Manual backup file:"
        if not bot.docker_mode:
            response.content = (
                "**NOTE:** Database dumps are only available "
                "in Docker mode.\n{}".format(response.content))
        response.file = discord.File('{}/temp/backup1.zip'.format(bot.path))

    elif subcommand.index == 4:  # Restore
        try:
            location = await utilities.download_url(
                bot, message.attachments[0].url, extension='zip')
        except Exception as e:
            raise CBException("Failed to download the file.", e=e)
        utilities.restore_backup(bot, location)
        response.content = "Restored backup file."

    elif subcommand.index == 5:  # DB Restore
        if not bot.docker_mode:
            raise CBException("Database restores can only be made in Docker mode.")
        try:
            location = await utilities.download_url(
                bot, message.attachments[0].url, filename='db_dump')
        except Exception as e:
            raise CBException("Failed to download the file.", e=e)
        exit_code = utilities.restore_db_backup(bot, tables=context.arguments)
        response.content = "Restore exit code: `{}`".format(exit_code)

    elif subcommand.index == 6:  # Blacklist
        blacklist = data.get(bot, 'core', 'blacklist', default=[])
        if not arguments[0]:
            response.content = "Blacklisted entries: {}".format(blacklist)
        else:
            user_id = arguments[0]
            if user_id in blacklist:
                data.list_data_remove(bot, 'core', 'blacklist', user_id)
                response.content = "User removed from blacklist."
            else:
                data.list_data_append(bot, 'core', 'blacklist', user_id)
                response.content = "User added to blacklist."

    elif subcommand.index == 7:  # Toggle feedback
        status = data.get(bot, 'core', 'feedbackdisabled', default=False)
        action = "enabled" if status else "disabled"
        data.add(bot, 'core', 'feedbackdisabled', not status)
        response.content = "Feedback has been {}.".format(action)

    elif subcommand.index == 8:  # Announcement
        if arguments[0]:
            data.add(bot, 'core', 'announcement', [arguments[0], int(time.time())])
            response.content = "Announcement set!"
        else:
            data.remove(bot, 'core', 'announcement')
            response.content = "Announcement cleared!"

    elif subcommand.index == 9:  # Update
        response.embed = discord.Embed(
            title=':arrow_up: Update', description='', colour=discord.Color(0x3b88c3))
        tooltip = ':regional_indicator_a: : Update core\n:regional_indicator_b: : Update plugins'
        response.embed.add_field(name='Update Wizard 95 ready', value='\u200b', inline=False)
        response.embed.add_field(name='\u200b', value=tooltip, inline=False)
        response.embed.set_footer(text='---')
        response.message_type = MessageTypes.INTERACTIVE
        response.extra_function = update_menu
        response.extra = {'buttons': ['❌', '⬆', '⬇', '🇦', '🇧']}
        response.selection_index = 0
        response.plugin_list = list(bot.plugins)[1:]
        response.updates = []
        response.selected = []
        response.stage = 0

    return response


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

    elif subcommand.index == 3:  # Upload logs
        await utilities.upload_logs(bot)
        response = "Logs uploaded to the debug channel."

    elif subcommand.index == 4:  # Toggle debug mode
        if bot.debug:  # Remove handlers
            to_remove = []
            for handler in logging.root.handlers:
                if handler.get_name() == 'jb_debug':
                    to_remove.append(handler)
            for handler in to_remove:
                logging.root.removeHandler(handler)
            logging.root.setLevel(logging.WARN)
            bot.debug = False
            response = 'Debug mode is now off.'
        else:  # Add handlers
            log_file = '{}/temp/logs.txt'.format(bot.path)
            if os.path.isfile(log_file):
                shutil.copy2(log_file, '{}/temp/last_logs.txt'.format(bot.path))
            file_handler = RotatingFileHandler(log_file, maxBytes=5000000, backupCount=5)
            file_handler.set_name('jb_debug')
            stream_handler = logging.StreamHandler()
            stream_handler.set_name('jb_debug')
            logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, stream_handler])
            bot.debug = True
            response = 'Debug mode is now on.'

    elif subcommand.index == 5:  # Reset local dictionary
        _setup_debug_environment(bot)
        response = "Debug environment local dictionary reset."

    elif subcommand.index == 6:  # Repl thingy
        global_dictionary['message'] = message
        global_dictionary['bot'] = bot
        global_dictionary['channel'] = message.channel
        global_dictionary['guild'] = message.guild

        # Cleaning up input
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

    return Response(
        content=response, message_type=message_type,
        extra=extra, extra_function=handle_active_message)


async def help_menu(bot, context, response, result, timed_out):
    invoker = utilities.get_invoker(bot, guild=None if response.destination else context.guild)
    if timed_out:
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
        response.embed.add_field(name=name, value=value.format(invoker=invoker), inline=False)
    response.embed.add_field(
        value='Page [ {} / {} ]'.format(page+1, total_pages+1), name='\u200b', inline=False)
    await response.message.edit(embed=response.embed)


async def manual_menu(bot, context, response, result, timed_out):
    invoker_guild = None if response.destination else context.guild
    invoker = utilities.get_invoker(bot, guild=invoker_guild)
    if timed_out:
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
        embed_details = plugins.get_manual(bot, *previous_entry, guild=invoker_guild)

    elif selection in (1, 2):  # Page navigation
        new_page = response.current_state[2] + (1 if selection == 2 else -1)
        test_state = response.current_state[:2] + [new_page]
        embed_details = plugins.get_manual(bot, *test_state, guild=invoker_guild)
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
        embed_details = plugins.get_manual(bot, *test_state, guild=invoker_guild)
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


async def help_wrapper(bot, context):
    message, _, subcommand, options, arguments = context[:5]
    response = Response()
    is_owner = data.is_owner(bot, message.author.id)
    help_here = 'here' in options
    invoker_guild = context.guild if (context.direct or help_here or bot.selfbot) else None
    invoker = utilities.get_invoker(bot, guild=invoker_guild)

    if subcommand.index == 0:  # Manual
        if arguments[0]:  # Load from given state
            try:
                subject_test = int(arguments[0]) - 1
            except:
                subject_test = arguments[0]
            if arguments[1] is not None:
                arguments[1] -= 1
            if arguments[2] is not None:
                arguments[2] -= 1
            state = [subject_test, arguments[1], arguments[2]]
            embed_details = plugins.get_manual(bot, *state, safe=False, guild=invoker_guild)
        else:  # Load menu from scratch
            embed_details = plugins.get_manual(bot, guild=invoker_guild)
            state = [None]*3
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
                guess = await parser.guess_command(
                    bot, text, message, safe=False, substitue_shortcuts=False)
            for name, value in guess.help_embed_fields:
                response.embed.add_field(
                    name=name, value=value.format(invoker=invoker), inline=False)
            help_here = True
        else:  # Help menu
            state = [None]*3 + [0]
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

    if not (context.direct or help_here or bot.selfbot):
        try:
            await message.add_reaction('📨')  # Envelope reaction
        except:
            pass
        response.destination = context.author

    return response


async def get_response(bot, context):
    if context.base == 'ping':
        if context.arguments[0]:
            response = 'Pong!\n{}'.format(context.arguments[0])
        else:
            response = 'Pong!'
    else:
        response = "This should not be seen. Your command was: " + base
    return Response(content=response)


async def handle_active_message(bot, context, response):
    """
    This function is called if the given message was marked as active
    (message_type of 3).
    """
    if response.extra[0] == 'ping':
        latency_time = "Latency time: {:.2f} ms".format((time.time() * 1000) - response.extra[1])
        await response.reference.edit(content=latency_time)

    elif response.extra[0] == 'reload':

        # Preliminary check
        plugins_to_reload = []
        if response.extra[1][0]:
            for plugin_name in response.extra[1]:
                if plugin_name in bot.plugins:
                    plugins_to_reload.append(plugin_name)
                else:
                    raise CBException("Invalid plugin.", plugin_name)
        else:
            plugins_to_reload = list(bot.plugins.keys())
            plugins_to_reload.remove('core')

        data.save_data(bot)  # Safety save
        logger.info("Reloading plugins and commands...")

        # Cancel running tasks associated with plugins
        tasks = asyncio.Task.all_tasks()
        pattern = re.compile('([^/(:\d>$)])+(?!.*\/)')
        for plugin_name in plugins_to_reload:
            for task in tasks:
                callback_info = task._repr_info()[1]
                plugin_name_test = pattern.search(callback_info).group(0)
                if plugin_name_test == plugin_name:
                    logger.debug("Canceling task: {}".format(task))
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
        await response.message.edit(content='Reloaded {} plugin{}.'.format(
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
    if bot.user.id == DEV_BOT_ID:  # Set debugging mode only for the dev bot
        logger.setLevel(logging.DEBUG)
    permissions = {
        'read_messages': "Standard.",
        'send_messages': "Standard.",
        'manage_messages': "Deletes messages and reactions of certain commands. (Framework)",
        'attach_files': "Uploads responses longer than 2000 characters long as a text file.",
        'read_message_history': "Gets chat context when bot moderators change settings.",
        'connect': "Allows the bot to connect to voice channels. (Framework)",
        'speak': "Allows the bot to speak. (Framework)",
        'add_reactions': "Allows for interactive menus. (Framework)",
        'embed_links': "Allows for embedded messages. (Framework)",
    }
    utilities.add_bot_permissions(bot, 'core', **permissions)


async def on_guild_join(bot, guild):
    # Add guild to the list
    logger.info("Joining guild")
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
        "read `{1}manual core 5` and `{1}manual core 4` for moderating and "
        "configuring the bot.**\n\nThat's all for now. If you have any questions, "
        "please refer to the manual, or send the bot owners a message using "
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
    logger.error(
        "An exception was thrown that wasn't handled by the core. \n"
        "Event: {0}\nargs: {1}\nkwargs: {2}".format(event, args, kwargs))
    logger.error(traceback.format_exc())
