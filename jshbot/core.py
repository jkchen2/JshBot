import asyncio
import discord
import traceback
import logging
import os.path
import random
import shutil
import yaml
import time
import sys
import os

from logging.handlers import RotatingFileHandler
from concurrent.futures import FIRST_COMPLETED
from collections import namedtuple, OrderedDict
from discord.abc import PrivateChannel

from jshbot import (
        configurations, plugins, commands, parser, data, utilities,
        base, logger, core_version, core_date)
from jshbot.exceptions import BotException, ConfiguredBotException, ErrorTypes
from jshbot.commands import Response, MessageTypes

CBException = ConfiguredBotException('Core')


exception_insults = [
    'Ow.',
    'Ah, shucks.',
    'Wow, nice one.',
    'That wasn\'t supposed to happen.',
    'Tell Jsh to fix his bot.',
    'I was really hoping that wouldn\'t happen, but it did.',
    'segmentation fault (core dumped)',
    '0xABADBABE 0xFEE1DEAD',
    ':bomb: Sorry, a system error occurred.',
    ':bomb: :bomb: :bomb: :bomb:',
    'But... the future refused to be awaited.',
    'So... cold...',
    'Yup. Jsh is still awful at Python.',
    'Yeah, I was a mistake.',
    'Maybe it won\'t happen next time! *Right...?*',
    'Darn.',
    'I... have failed...',
    'Well, it was worth a shot.',
    'That one stung a bit.',
    'Of *course*. Nothing ever works out, does it?',
    'I yelled at Jsh for you.',
    'Minsoo is bad at osu!. He wanted me to tell you that.',
    'Existence is pain.',
    'The Brass is impressed. Good work.',
    'And the award for worst coded bot goes to...',
    'Oh man. Oh god. Oh man. Oh god, oh man! Oh god, oh man, oh god oh man oh god!'
]


def get_new_bot(client_type, path, debug, docker_mode):

    class Bot(client_type):

        # Shamelessly similar to d.py context for command usage
        Context = namedtuple(
            'Context',
            [
                'message', 'base', 'subcommand', 'options', 'arguments', 'keywords',
                'cleaned_content', 'elevation', 'guild', 'channel', 'author',
                'direct', 'index', 'id', 'bot'
            ]
        )

        def __init__(self, path, debug, docker_mode):
            self.version = core_version
            self.date = core_date
            self.time = int(time.time())
            self.readable_time = time.strftime('%c')
            self.path = path
            self.debug = debug
            self.docker_mode = docker_mode

            logger.info("=== {0: ^40} ===".format("Starting up JshBot " + self.version))
            logger.info("=== {0: ^40} ===".format(self.readable_time))

            super().__init__()

            self.configurations = {}
            plugins.add_configuration(self, 'core', 'core', base)
            data.check_folders(self)

            logger.debug("Connecting to database...")
            self.db_templates = {}
            self.db_connection = None
            data.db_connect(self)

            logger.debug("Loading plugins...")
            self.data = {'global_users': {}, 'global_plugins': {}}
            self.volatile_data = {'global_users': {}, 'global_plugins': {}}
            self.data_changed = []
            self.tables_changed = []
            self.dump_exclusions = []
            self.plugins = OrderedDict()
            self.manuals = OrderedDict()
            self.commands = {}
            plugins.add_plugins(self)

            config = self.configurations['core']
            self.edit_dictionary = {}
            self.spam_dictionary = {}
            self.spam_limit = config['command_limit']
            self.spam_timeout = config['command_limit_timeout']
            self.command_invokers = config['command_invokers']
            self.locked_commands = config['locked_commands']
            self.single_command = config['single_command']
            self.edit_timeout = config['edit_timeout']
            self.selfbot = config['selfbot_mode']
            self.owners = config['owners']
            self.schedule_timer = None
            self.last_exception = None
            self.last_traceback = None
            self.last_response = None
            self.fresh_boot = None
            self.ready = False
            self.extra = None

            # Extras
            config['token'] = '(redacted)'
            config['database_credentials'] = '(redacted)'

        def can_respond(self, message):
            """Determines whether or not the bot can respond.

            Checks that the message has text, matches an invoker, and that the
            guild/channel/user is not muted or blocked. Admins and mods
            override this.
            """
            if self.fresh_boot is None:  # Ignore until bot is ready
                return False
            # Ignore empty messages and messages by bots
            if (not message.content or message.author.bot or
                    message.author.id == self.user.id) and not self.selfbot:
                return False

            # Check that the message starts with a valid invoker
            content = message.content
            if isinstance(message.channel, PrivateChannel):  # No custom invoker or data
                guild_data = {}
                invokers = self.command_invokers
            else:
                guild_data = data.get(self, 'core', None, message.guild.id, default={})
                invokers = [guild_data.get('command_invoker')]
                if not invokers[0]:
                    invokers = self.command_invokers
            has_mention_invoker = False
            has_name_invoker = False
            has_nick_invoker = False
            has_regular_invoker = False
            is_direct = isinstance(message.channel, PrivateChannel)
            for invoker in invokers:  # Need to pick a single invoker
                if content.startswith(invoker):
                    has_regular_invoker = True
                    break
            if not has_regular_invoker:
                has_mention_invoker = content.startswith(
                    ('<@' + str(self.user.id) + '>', '<@!' + str(self.user.id) + '>'))
                if not has_mention_invoker:
                    clean_content = content.lower()
                    has_name_invoker = clean_content.startswith(self.user.name.lower())
                    if not has_name_invoker and not is_direct and message.guild.me.nick:
                        has_nick_invoker = clean_content.startswith(message.guild.me.nick.lower())
                        if has_nick_invoker:  # Clean up content (nickname)
                            content = content[len(message.guild.me.nick):].strip()
                    elif has_name_invoker:  # Clean up content (name)
                        content = content[len(self.user.name):].strip()
                else:  # Clean up content (mention)
                    content = content.partition(' ')[2].strip()
            else:  # Clean up content (invoker)
                content = content.partition(invoker)[2].strip()

            if guild_data.get('mention_mode', False):  # Mention mode enabled
                if not (has_mention_invoker or has_name_invoker or has_nick_invoker):
                    return False
            else:  # Any invoker will do
                if not (has_regular_invoker or has_mention_invoker or
                        has_name_invoker or has_nick_invoker or is_direct):
                    return False

            if self.selfbot:  # Selfbot check
                if message.author.id == self.owners[0]:
                    return [content, False, False, True]
                else:
                    return False

            # Respond to direct messages
            author = message.author
            is_owner = author.id in self.owners
            if is_direct:
                return [content, False, False, is_owner]

            modrole_id = data.get(self, 'core', 'modrole', guild_id=message.guild.id)
            is_mod = (
                author.guild_permissions.administrator or
                modrole_id in [it.id for it in author.roles])
            is_admin = author == message.guild.owner
            result = [content, is_mod, is_admin, is_owner]

            # Owners/moderators override everything
            # This is faster than calling the function in jshbot.data
            channel_id = message.channel.id
            if is_mod or is_admin or is_owner:
                return result
            # Server/channel muted, or user is blocked
            if (guild_data.get('muted', False) or
                    (channel_id in guild_data.get('muted_channels', [])) or
                    (author.id in guild_data.get('blocked', []))):
                return False
            else:
                return result  # Clear to respond

        async def on_message(self, message, replacement_message=None):
            # Ensure bot can respond properly
            try:
                initial_data = self.can_respond(message)
            except Exception as e:  # General error
                logger.error(e)
                logger.error(traceback.format_exc())
                self.last_exception = e
                return
            if not initial_data:
                return

            # Ensure command is valid
            content = initial_data[0]
            elevation = 3 - (initial_data[4:0:-1] + [True]).index(True)
            split_content = content.split(' ', 1)
            if len(split_content) == 1:  # No spaces
                split_content.append('')
            base, parameters = split_content
            base = base.lower()
            try:
                command = self.commands[base]
            except KeyError:
                if self.single_command:
                    try:
                        parameters = content
                        base = self.single_command
                        command = self.commands[base]
                    except KeyError:
                        logger.error("Single command fill not found!")
                        return
                else:
                    logger.debug("Suitable command not found: %s", base)
                    return

            # Check that user is not spamming
            author_id = message.author.id
            direct = isinstance(message.channel, PrivateChannel)
            spam_value = self.spam_dictionary.get(author_id, 0)
            if elevation > 0 or direct:  # Moderators ignore custom limit
                spam_limit = self.spam_limit
            else:
                spam_limit = min(
                    self.spam_limit, data.get(
                        self, 'core', 'spam_limit',
                        guild_id=message.guild.id, default=self.spam_limit))
            if spam_value >= spam_limit:
                if spam_value == spam_limit:
                    self.spam_dictionary[author_id] = spam_limit + 1
                    plugins.broadcast_event(self, 'bot_on_user_ratelimit', message.author)
                    await message.channel.send(content=(
                        "{0}, you appear to be issuing/editing "
                        "commands too quickly. Please wait {1} seconds.".format(
                            message.author.mention, self.spam_timeout)))
                return

            # Parse command and reply
            try:
                context = None
                with message.channel.typing():
                    logger.debug(message.author.name + ': ' + message.content)
                    subcommand, options, arguments = await parser.parse(
                        self, command, parameters, message)
                    context = self.Context(
                        message, base, subcommand, options, arguments,
                        subcommand.command.keywords, initial_data[0], elevation,
                        message.guild, message.channel, message.author, direct,
                        subcommand.index, subcommand.id, self)
                    plugins.broadcast_event(self, 'bot_on_command', context)
                    logger.info([subcommand, options, arguments])
                    response = await commands.execute(self, context)
                    if response is None:
                        response = Response()
                    if self.selfbot and response.content:
                        response.content = '\u200b' + response.content
            except Exception as e:  # General error
                response = Response()
                destination = message.channel
                message_reference = await self.handle_error(
                    e, message, context, response, edit=replacement_message, command_editable=True)

            else:  # Attempt to respond
                send_arguments = response.get_send_kwargs(replacement_message)
                try:
                    destination = response.destination if response.destination else message.channel
                    message_reference = None
                    if replacement_message:
                        try:
                            await replacement_message.edit(**send_arguments)
                            message_reference = replacement_message
                        except discord.NotFound:  # Message deleted
                            response = Response()
                            message_reference = None
                    elif (not response.is_empty() and not (self.selfbot and
                            response.message_type is MessageTypes.REPLACE)):
                        message_reference = await destination.send(**send_arguments)
                    response.message = message_reference
                    plugins.broadcast_event(self, 'bot_on_response', response, context)
                except Exception as e:
                    message_reference = await self.handle_error(
                        e, message, context, response,
                        edit=replacement_message, command_editable=True)

            # Incremement the spam dictionary entry
            if author_id in self.spam_dictionary:
                self.spam_dictionary[author_id] += 1
            else:
                self.spam_dictionary[author_id] = 1

            # MessageTypes:
            # NORMAL - Normal. The issuing command can be edited.
            # PERMANENT - Message is not added to the edit dictionary.
            # REPLACE - Deletes the issuing command after 'extra' seconds. Defaults
            #   to 0 seconds if 'extra' is not given.
            # ACTIVE - The message reference is passed back to the function defined
            #   with 'extra_function'. If 'extra_function' is not defined, it will call
            #   plugin.handle_active_message.
            # INTERACTIVE - Assembles reaction buttons given by extra['buttons'] and
            #   calls 'extra_function' whenever one is pressed.
            # WAIT - Wait for event. Calls 'extra_function' with the result, or None
            #   if the wait timed out.
            #
            # Only the NORMAL message type can be edited.

            response.message = message_reference
            if message_reference and isinstance(message_reference.channel, PrivateChannel):
                permissions = self.user.permissions_in(message_reference.channel)
            elif message_reference:
                permissions = message_reference.guild.me.permissions_in(message_reference.channel)
            else:
                permissions = None
            self.last_response = message_reference

            if response.message_type is MessageTypes.NORMAL and message_reference:
                # Edited commands are handled in base.py
                wait_time = self.edit_timeout
                if wait_time:
                    self.edit_dictionary[str(message.id)] = message_reference
                    await asyncio.sleep(wait_time)
                    if str(message.id) in self.edit_dictionary:
                        del self.edit_dictionary[str(message.id)]
                        if message_reference.embeds:
                            embed = message_reference.embeds[0]
                            if embed.footer.text and embed.footer.text.startswith('\u200b'*3):
                                embed.set_footer()
                                try:
                                    await message_reference.edit(embed=embed)
                                except:
                                    pass

            elif response.message_type is MessageTypes.REPLACE:
                try:
                    if self.selfbot and not replacement_message:  # Edit instead
                        await message.edit(**send_arguments)
                    else:
                        if response.extra:
                            await asyncio.sleep(response.extra)
                        try:
                            await message.delete()
                        except:  # Ignore permissions errors
                            pass
                except Exception as e:
                    message_reference = await self.handle_error(
                        e, message, context, response, edit=message_reference)
                    self.last_response = message_reference

            elif response.message_type is MessageTypes.ACTIVE and message_reference:
                try:
                    await response.extra_function(self, context, response)
                except Exception as e:  # General error
                    message_reference = await self.handle_error(
                        e, message, context, response, edit=message_reference)
                    self.last_response = message_reference

            elif response.message_type is MessageTypes.INTERACTIVE and message_reference:
                # There are two additional options for the extra object to change menu behavior:
                # reactionlock -- Whether or not non-menu reactions can be used for responses
                # userlock -- Whether or not the menu only responds to the command author
                try:
                    buttons = response.extra['buttons']
                    kwargs = response.extra.get('kwargs', {})
                    if 'timeout' not in kwargs:
                        kwargs['timeout'] = 300
                    if 'check' not in kwargs:
                        kwargs['check'] = (
                            lambda r, u: r.message.id == message_reference.id and not u.bot)
                    for button in buttons:
                        await message_reference.add_reaction(button)
                    reaction_check = await destination.get_message(message_reference.id)
                    for reaction in reaction_check.reactions:
                        if not reaction.me or reaction.count > 1:
                            async for user in reaction.users():
                                if user != self.user and permissions.manage_messages:
                                    asyncio.ensure_future(
                                        message_reference.remove_reaction(reaction, user))
                    await response.extra_function(self, context, response, None, False)
                    process_result = True
                    while process_result is not False:
                        try:
                            if not permissions.manage_messages:
                                add_task = self.wait_for('reaction_add', **kwargs)
                                remove_task = self.wait_for('reaction_remove', **kwargs)
                                done, pending = await asyncio.wait(
                                    [add_task, remove_task], return_when=FIRST_COMPLETED)
                                result = next(iter(done)).result()
                                for future in pending:
                                    future.cancel()
                            else:  # Can remove reactions
                                result = await self.wait_for('reaction_add', **kwargs)
                                if result[1] != self.user:
                                    asyncio.ensure_future(
                                        message_reference.remove_reaction(*result))
                                else:
                                    continue
                            is_mod = data.is_mod(self, message.guild, result[1].id)
                            if (response.extra.get('reactionlock', True) and not result[0].me or
                                    data.is_blocked(self, message.guild, result[1].id) or
                                    (response.extra.get('userlock', True) and not
                                        (result[1] == message.author or is_mod))):
                                continue
                        except (asyncio.futures.TimeoutError, asyncio.TimeoutError):
                            await response.extra_function(self, context, response, None, True)
                            process_result = False
                        else:
                            process_result = await response.extra_function(
                                self, context, response, result, False)
                    try:
                        await response.message.clear_reactions()
                    except:
                        pass
                except Exception as e:
                    message_reference = await self.handle_error(
                        e, message, context, response, edit=message_reference)
                    self.last_response = message_reference

            elif response.message_type is MessageTypes.WAIT:
                try:
                    kwargs = response.extra.get('kwargs', {})
                    if 'timeout' not in kwargs:
                        kwargs['timeout'] = 300
                    process_result = True
                    while process_result is not False:
                        try:
                            result = await self.wait_for(response.extra['event'], **kwargs)
                        except asyncio.TimeoutError:
                            await response.extra_function(self, context, response, None)
                            process_result = False
                        else:
                            process_result = await response.extra_function(
                                self, context, response, result)
                        if not response.extra.get('loop', False):
                            process_result = False

                except Exception as e:
                    message_reference = await self.handle_error(
                        e, message, context, response, edit=message_reference)
                    self.last_response = message_reference

            elif message_reference:
                logger.error("Unknown message type: {}".format(response.message_type))

            '''
            # TODO: Fix for rewrite
            elif response[2] == 6:  # Wait for response
                assert False
                try:
                    reply = await self.wait_for_message(**response[3][1])
                    await response[3][0](
                        self, message_reference, reply, response[3][2])
                except Exception as e:
                    message_reference = await self.handle_error(
                        e, message, parsed_input, response,
                        edit=message_reference, command_editable=False)
                    self.last_response = message_reference
            '''

        async def handle_error(
                self, error, message, context, response, edit=None, command_editable=False):
            """Common error handler for sending responses."""
            send_function = edit.edit if edit else message.channel.send
            self.last_exception = error
            if response.message:
                try:
                    await response.message.clear_reactions()
                except:
                    pass

            if isinstance(error, BotException):
                self.last_traceback = error.traceback
                plugins.broadcast_event(self, 'bot_on_error', error, message)
                if error.use_embed:
                    content, embed = '', error.embed
                else:
                    content, embed = str(error), None
                if command_editable and error.autodelete == 0:
                    if content:
                        content += '\n\n(Note: The issuing command can be edited)'
                    elif embed:
                        embed.set_footer(
                            text="\u200b\u200b\u200bThe issuing command can be edited",
                            icon_url="http://i.imgur.com/fM9yGzI.png")
                # TODO: Handle long messages
                message_reference = await send_function(content=content, embed=embed)

                if error.autodelete > 0:
                    await asyncio.sleep(error.autodelete)
                    try:  # Avoid delete_messages for selfbot mode
                        message_reference = edit if edit else message_reference
                        await message_reference.delete()
                        await message.delete()
                    except:
                        pass
                    return

            elif isinstance(error, discord.Forbidden):
                plugins.broadcast_event(self, 'bot_on_discord_error', error, message)
                message_reference = None
                try:
                    await message.author.send(
                        content="Sorry, I don't have permission to carry "
                        "out that command in that channel. The bot may have had "
                        "its `Send Messages` permission revoked (or any other "
                        "necessary permissions, like `Embed Links`, `Manage Messages`, or "
                        "`Speak`).\nIf you are a bot moderator or server owner, "
                        "you can mute channels with `{}mod mute <channel>` "
                        "instead of using permissions directly. If that's not the "
                        "issue, be sure to check that the bot has the proper "
                        "permissions on the server and each channel!".format(
                            self.command_invokers[0]))
                except:  # User has blocked the bot
                    pass
                # TODO: Consider sending a general permissions error

            else:
                if isinstance(error, discord.HTTPException) and len(str(response)) > 1998:
                    plugins.broadcast_event(self, 'bot_on_discord_error', error, message)
                    message_reference = await utilities.send_text_as_file(
                        message.channel, str(response), 'response',
                        extra="The response is too long. Here is a text file of the contents.")
                else:
                    insult = random.choice(exception_insults)
                    error = '**`{0}:`**`{1}`'.format(type(error).__name__, error)
                    embed = discord.Embed(
                        title=':x: Internal error',
                        description=insult, colour=discord.Colour(0xdd2e44))
                    embed.add_field(name='Details:', value=error)
                    embed.set_footer(text="The bot owners have been notified of this error.")
                    message_reference = await send_function(content='', embed=embed)
                self.last_traceback = traceback.format_exc()
                plugins.broadcast_event(self, 'bot_on_general_error', error, message)
                logger.error(self.last_traceback)
                logger.error(self.last_exception)
                if context:
                    parsed_input = '[{0.subcommand}, {0.options}, {0.arguments}]'.format(context)
                else:
                    parsed_input = '!Context is missing!'
                await utilities.notify_owners(
                    self, '```\n{0}\n{1}\n{2}\n{3}```'.format(
                        message.content, parsed_input, self.last_exception, self.last_traceback))

            return edit if edit else message_reference

        async def on_ready(self):
            if self.fresh_boot is None:
                if self.selfbot:  # Selfbot safety checks
                    self.owners = [self.user.id]
                else:
                    app_info = await self.application_info()
                    if app_info.owner.id not in self.owners:
                        self.owners.append(app_info.owner.id)
                # Start scheduler
                asyncio.ensure_future(utilities._start_scheduler(self))
                # Make sure guild data is ready
                data.check_all(self)
                data.load_data(self)
                # Set single command notification
                if self.single_command:
                    try:
                        command = self.commands[self.single_command]
                    except KeyError:
                        raise CBException(
                            "Invalid single command base.", error_type=ErrorTypes.STARTUP)
                    command.help_embed_fields.append((
                        '[Single command mode]',
                        'The base `{}` can be omitted when invoking these commands.'.format(
                            self.single_command)))
                    
                self.fresh_boot = True
                self.ready = True
                plugins.broadcast_event(self, 'bot_on_ready_boot')

            elif self.fresh_boot:
                self.fresh_boot = False

            if self.debug:
                debug_channel = self.get_channel(
                    self.configurations['core']['debug_channel'])
                if self.fresh_boot and debug_channel is not None:
                    log_file = '{}/temp/last_logs.txt'.format(self.path)
                    error_file = '{}/temp/error.txt'.format(self.path)
                    if not os.path.isfile(log_file):
                        await debug_channel.send(content="Started up fresh.")
                    else:
                        discord_file = discord.File(log_file, filename='last_logs.txt')
                        await debug_channel.send(content="Logs:", file=discord_file)
                    if not os.path.isfile(error_file):
                        await debug_channel.send(content="No error log.")
                    else:
                        discord_file = discord.File(error_file)
                        await debug_channel.send(content="Last error:", file=discord_file)
                elif debug_channel is not None:
                    await debug_channel.send("Reconnected.")

            logger.info("=== {0: ^40} ===".format(self.user.name + ' online'))

            if self.fresh_boot:
                asyncio.ensure_future(self.spam_clear_loop())
                asyncio.ensure_future(self.save_loop())
                asyncio.ensure_future(self.backup_loop())

                if self.selfbot:
                    asyncio.ensure_future(self.selfbot_away_loop())
                elif len(self.guilds) == 0:
                    link = (
                        'https://discordapp.com/oauth2/authorize?&client_id={}'
                        '&scope=bot&permissions=8').format(app_info.id)
                    first_start_note = (
                        "It appears that this is the first time you are starting up the bot. "
                        "In order to have it function properly, you must add the bot to the "
                        "server with the specified debug channel. Invite link:\n{}\n\nIt is "
                        "highly recommended that you update the core using [{}botowner update] "
                        "to not only update the bot, but also add the core manual.").format(
                            link, self.command_invokers[0])
                    logger.info(first_start_note)

        # Take advantage of dispatch to intercept all events
        def dispatch(self, event, *args, **kwargs):
            super().dispatch(event, *args, **kwargs)
            plugins.broadcast_event(self, 'on_' + event, *args, **kwargs)

        async def selfbot_away_loop(self):
            """Sets the status to 'away' every 5 minutes."""
            while True:
                await asyncio.sleep(300)
                self_member = next(iter(self.guilds)).me
                self_status, self_game = self_member.status, self_member.game
                if not isinstance(self_status, discord.Status.idle):
                    await self.change_presence(game=self_game, afk=True)

        async def spam_clear_loop(self):
            """Loop to clear the spam dictionary periodically."""
            try:
                interval = self.configurations['core']['command_limit_timeout']
                interval = 0 if interval <= 0 else int(interval)
            except:
                logger.warn("Command limit timeout not configured.")
                interval = 0
            while interval:
                await asyncio.sleep(interval)
                self.spam_dictionary.clear()

        async def save_loop(self):
            """Runs the loop that periodically saves data (minutes)."""
            try:
                interval = int(self.configurations['core']['save_interval'])
                interval = 0 if interval <= 0 else interval
            except:
                logger.warn("Saving interval not configured.")
                interval = 0
            while interval:
                await asyncio.sleep(interval * 60)
                self.save_data()

        async def backup_loop(self):
            """Runs the loop that periodically backs up data (hours)."""
            try:
                interval = int(self.configurations['core']['backup_interval'])
                interval = 0 if interval <= 0 else interval * 3600
            except:
                logger.warn("Backup interval not configured - backup loop stopped.")
                return
            channel_id = self.configurations['core']['debug_channel']
            debug_channel = self.get_channel(channel_id)
            while not debug_channel:
                logger.warn("Debug channel not found. Trying again in 60 seconds...")
                await asyncio.sleep(60)
                debug_channel = self.get_channel(channel_id)
            while interval:
                utilities.make_backup(self)
                discord_file = discord.File('{}/temp/backup1.zip'.format(self.path))
                try:
                    await debug_channel.send(file=discord_file)
                except Exception as e:
                    logger.error("Failed to upload backup file! %s", e)
                await asyncio.sleep(interval)

        def save_data(self, force=False):
            if force:
                logger.info("Forcing data save...")
            else:
                logger.info("Saving data...")
            data.save_data(self, force=force)
            logger.info("Save complete.")

        def restart(self):
            logger.info("Attempting to restart the bot...")
            self.save_data(force=True)
            asyncio.ensure_future(self.logout())
            os.system('python3.5 ' + self.path + '/start.py')

        def shutdown(self):
            logger.debug("Writing data on shutdown...")
            if self.fresh_boot is not None:  # Don't write blank data
                self.save_data(force=True)
            logger.info("Closing down!")
            try:
                self.loop.close()
            except:
                pass
            sys.exit()

    return Bot(path, debug, docker_mode)


def start(start_file=None):
    if start_file:
        path = os.path.split(os.path.realpath(start_file))[0]
        logger.debug("Setting directory to " + path)
        docker_mode = False
    else:  # Use Docker setup
        path = '/external'
        logger.info("Bot running in Docker mode.")
        logger.debug("Using Docker setup path, " + path)
        docker_mode = True

    try:
        config_file_location = path + '/config/core-config.yaml'
        with open(config_file_location, 'rb') as config_file:
            config = yaml.load(config_file)
            selfbot_mode, token, debug = config['selfbot_mode'], config['token'], config['debug']
    except Exception as e:
        logger.error("Could not determine token /or selfbot mode.")
        raise e

    if selfbot_mode is True:  # Explicit, for YAML 1.2 vs 1.1
        client_type = discord.Client
        logger.debug("Using standard client (selfbot enabled).")
    else:
        client_type = discord.AutoShardedClient
        logger.debug("Using autosharded client (selfbot disabled).")

    if debug is True:
        log_file = '{}/temp/logs.txt'.format(path)
        if os.path.isfile(log_file):
            shutil.copy2(log_file, '{}/temp/last_logs.txt'.format(path))
        file_handler = RotatingFileHandler(log_file, maxBytes=5000000, backupCount=5)
        file_handler.set_name('jb_debug')
        stream_handler = logging.StreamHandler()
        stream_handler.set_name('jb_debug')
        logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, stream_handler])

    def safe_exit():
        loop = asyncio.get_event_loop()
        try:  # From discord.py client.run
            loop.run_until_complete(bot.logout())
            pending = asyncio.Task.all_tasks()
            gathered = asyncio.gather(*pending)
        except Exception as e:
            logger.error("Failed to log out. %s", e)
        try:
            gathered.cancel()
            loop.run_until_complete(gathered)
            gathered.exception()
        except:
            pass
        logger.warn("Bot disconnected. Shutting down...")
        bot.shutdown()  # Calls sys.exit

    def exception_handler(loop, context):
        e = context.get('exception')
        if e and e.__traceback__:
            traceback_text = ''.join(traceback.format_tb(e.__traceback__))
        else:
            traceback_text = traceback.format_exc()
            if not traceback_text:
                traceback_text = '(No traceback available)'
        error_message = '{}\n{}'.format(e, traceback_text)
        logger.error("An uncaught exception occurred.\n" + error_message)
        with open(path + '/temp/error.txt', 'w') as error_file:
            error_file.write(error_message)
        logger.error("Error file written.")
        if bot.is_closed():
            safe_exit()

    loop = asyncio.get_event_loop()
    bot = get_new_bot(client_type, path, debug, docker_mode)
    start_task = bot.start(token, bot=not selfbot_mode)
    loop.set_exception_handler(exception_handler)
    try:
        loop.run_until_complete(start_task)
    except KeyboardInterrupt:
        logger.warn("Interrupted!")
        safe_exit()
