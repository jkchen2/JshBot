import asyncio
import discord
import logging
import os.path
import random
import shutil
import time
import sys
import os

# Debug
import traceback
import logging.handlers

from jshbot import configurations, plugins, commands, parser, data, utilities
from jshbot.exceptions import BotException, ErrorTypes

EXCEPTION = 'Core'
why = None

exception_insults = [
    'Ow.',
    'Ah, shucks.',
    'Wow, nice one.',
    'That wasn\'t supposed to happen.',
    'Tell Jsh to fix his bot.',
    'I was really hoping that wouldn\'t happen, but it did.',
    'segmentation fault (core dumped)',
    '0xABADBABE 0xFEE1DEAD',
    ':bomb: Sorry, a system error occured.',
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
    'Existence is pain.'
]


class Bot(discord.Client):

    def __init__(self, start_file, debug):
        self.version = '0.3.0-alpha'
        self.date = 'September 27th, 2016'
        self.time = int(time.time())
        self.readable_time = time.strftime('%c')
        self.debug = debug

        if self.debug:
            logging.debug("=== {0: ^40} ===".format(
                "Starting up JshBot " + self.version))
            logging.debug("=== {0: ^40} ===".format(self.readable_time))
        else:
            print("=== {0: ^40} ===".format(
                "Starting up JshBot " + self.version))
            print("=== {0: ^40} ===".format(self.readable_time))

        super().__init__()

        self.path = os.path.split(os.path.realpath(start_file))[0]
        logging.debug("Setting directory to {}".format(self.path))
        data.check_folders(self)

        logging.debug("Loading plugins and commands...")
        self.commands = {}
        self.plugins = {}
        plugins.add_plugins(self)

        logging.debug("Setting up data...")
        self.data = {'global_users': {}, 'global_plugins': {}}
        self.volatile_data = {'global_users': {}, 'global_plugins': {}}
        self.data_changed = []

        logging.debug("Loading manuals...")
        self.manuals = []
        commands.add_manuals(self)

        logging.debug("Loading configurations...")
        self.configurations = {}
        configurations.add_configurations(self)

        # Extras
        config = self.configurations['core']
        self.edit_dictionary = {}
        self.spam_dictionary = {}
        self.spam_limit = config['command_limit']
        self.spam_timeout = config['command_limit_timeout']
        self.command_invokers = config['command_invokers']
        self.locked_commands = config['locked_commands']
        self.edit_timeout = config['edit_timeout']
        self.selfbot = config['selfbot_mode']
        self.owners = config['owners']
        self.last_exception = None
        self.last_traceback = None
        self.last_response = None
        self.fresh_boot = None
        self.extra = None

    def get_token(self):
        return self.configurations['core']['token']

    def can_respond(self, message):
        """Determines whether or not the bot can respond.

        Checks that the message has text, matches an invoker, and that the
        server/channel/user is not muted or blocked. Admins and mods
        override this.
        """
        if self.fresh_boot is None:  # Ignore until bot is ready
            return
        # Ignore empty messages and messages by bots
        if (not message.content or message.author.bot or
                message.author.id == self.user.id) and not self.selfbot:
            return None

        # Check that the message starts with a valid invoker
        content = message.content
        has_regular_invoker = False
        has_mention_invoker = False
        has_name_invoker = False
        has_nick_invoker = False
        if message.channel.is_private:  # No custom invoker or data
            server_data = {}
            invokers = self.command_invokers
        else:
            server_data = data.get(
                self, 'base', None, message.server.id, default={})
            invokers = [server_data.get('command_invoker', None)]
            if not invokers[0]:
                invokers = self.command_invokers
        for invoker in invokers:
            if content.startswith(invoker):
                has_regular_invoker = True
                break
        if not has_regular_invoker:
            has_mention_invoker = content.startswith(
                ('<@' + self.user.id + '>', '<@!' + self.user.id + '>'))
            if not has_mention_invoker:
                clean_content = content.lower()
                has_name_invoker = clean_content.startswith(
                    self.user.name.lower())
                if (not has_name_invoker and not message.channel.is_private and
                        message.server.me.nick):
                    has_nick_invoker = clean_content.startswith(
                        message.server.me.nick.lower())
                    if has_nick_invoker:  # Clean up content (nickname)
                        content = content[len(message.server.me.nick):].strip()
                else:  # Clean up content (name)
                    content = content[len(self.user.name):].strip()
            else:  # Clean up content (mention)
                content = content.partition(' ')[2].strip()
        else:  # Clean up content (invoker)
            content = content.partition(invoker)[2].strip()

        if server_data.get('mention_mode', False):  # Mention mode enabled
            if not (has_mention_invoker or has_name_invoker or
                    has_nick_invoker):
                return None
        else:  # Any invoker will do
            if not (has_regular_invoker or has_mention_invoker or
                    has_name_invoker or has_nick_invoker):
                return None

        if self.selfbot:  # Selfbot check
            if message.author.id == self.owners[0]:
                return (content, False, False, True)
            else:
                return None

        # Respond to direct messages
        author_id = message.author.id
        is_owner = author_id in self.owners
        if message.channel.is_private:
            return (content, False, False, is_owner)

        is_mod = author_id in server_data.get('moderators', [])
        is_admin = author_id == message.server.owner.id
        result = (content, is_mod, is_admin, is_owner)

        try:
            # Owners/moderators override everything
            # This is faster than calling the function in jshbot.data
            channel_id = message.channel.id
            if is_mod or is_admin or is_owner:
                return result
            # Server/channel muted, or user is blocked
            if (server_data.get('muted', False) or
                    (channel_id in server_data.get('muted_channels', [])) or
                    (author_id in server_data.get('blocked', []))):
                return None
        except KeyError as e:  # Bot may not have updated fast enough
            logging.warn("Failed to find server in can_respond(): " + str(e))
            data.check_all(self)
            return None  # Don't recurse for safety

        return result  # Clear to respond

    async def on_message(self, message, replacement_message=None):
        # Ensure bot can respond properly
        try:
            initial_data = self.can_respond(message)
        except Exception as e:  # General error
            logging.error(e)
            traceback.print_exc()
            self.last_exception = e
            return
        if not initial_data:
            return

        # Ensure command is valid
        content = initial_data[0]
        split_content = content.split(' ', 1)
        if len(split_content) == 1:  # No spaces
            split_content.append('')
        base, parameters = split_content
        base = base.lower()
        try:
            command = self.commands[base]
        except KeyError:
            logging.debug("Suitable command not found: " + base)
            return

        # Check that user is not spamming
        spam_value = self.spam_dictionary.get(message.author.id, 0)
        if spam_value >= self.spam_limit:
            if spam_value == self.spam_limit:
                self.spam_dictionary[message.author.id] = self.spam_limit + 1
                plugins.broadcast_event(
                    self, 'bot_on_user_ratelimit', message.author)
                await self.send_message(
                    message.channel, "{0}, you appear to be issuing/editing "
                    "commands too quickly. Please wait {1} seconds.".format(
                        message.author.mention, self.spam_timeout))
            return

        # Bot is clear to get response. Send typing to signify
        if not replacement_message:
            typing_task = asyncio.ensure_future(
                self.send_typing(message.channel))
            edit = None
        else:
            typing_task = None
            edit = replacement_message

        # Parse command and reply
        try:
            logging.debug(message.author.name + ': ' + message.content)
            parsed_input = None
            parsed_input = parser.parse(
                self, command, base, parameters, server=message.server)
            plugins.broadcast_event(
                self, 'bot_on_command', command, parsed_input, message.author)
            logging.debug('\t' + str(parsed_input))
            print(parsed_input[:-1])  # Temp
            response = await (commands.execute(
                self, message, command, parsed_input, initial_data))
            if self.selfbot and response[2] != 5:
                response = ('\u200b' + response[0], *response[1:])
        except Exception as e:  # General error
            response = ('', False, 0, None)
            message_reference = await self.handle_error(
                e, message, parsed_input, response, edit=edit)

        else:  # Attempt to respond
            if typing_task:
                typing_task.cancel()
            try:
                message_reference = None
                if response[2] != 5:  # Handle file sending separately
                    if replacement_message:
                        try:
                            message_reference = await self.edit_message(
                                replacement_message, response[0])
                        except discord.NotFound:  # Message deleted
                            response = ('', False, 0, None)
                            message_reference = None
                    elif (response[0] and
                            not (self.selfbot and response[2] == 4)):
                        message_reference = await self.send_message(
                            message.channel, response[0], tts=response[1])
                    elif not response[0]:  # Empty message
                        response = (None, None, 1, None)
                    plugins.broadcast_event(
                        self, 'bot_on_response', response,
                        message_reference, message)
            except Exception as e:
                message_reference = await self.handle_error(
                    e, message, parsed_input, response, edit=edit)

        # Incremement the spam dictionary entry
        if message.author.id in self.spam_dictionary:
            self.spam_dictionary[message.author.id] += 1
        else:
            self.spam_dictionary[message.author.id] = 1

        # A response looks like this:
        # (text, tts, message_type, extra)
        # message_type can be:
        # 0 - normal
        # 1 - permanent
        # 2 - terminal (deletes itself after 'extra' seconds)
        #   If 'extra' is a tuple of (seconds, message), it will delete
        #   both the bot response and the given message reference.
        # 3 - active (pass the reference back to the plugin to edit)
        # 4 - replace (deletes command message)
        # 5 - send file (response[0] should be a file pointer)
        #   If 'extra' is provided, it will be the file name.
        # If message_type is >= 1, do not add to the edit dictionary

        self.last_response = message_reference

        if response[2] == 0:  # Normal
            # Edited commands are handled in base.py
            if message_reference is None:  # Forbidden exception
                return
            wait_time = self.edit_timeout
            if wait_time:
                self.edit_dictionary[message.id] = message_reference
                await asyncio.sleep(wait_time)
                if message.id in self.edit_dictionary:
                    del self.edit_dictionary[message.id]

        elif response[2] == 2:  # Terminal
            delay, extra_message = 10, None
            if response[3]:
                if type(response[3]) is tuple:
                    delay, extra_message = response[3]
                else:
                    delay = int(response[3])
            await asyncio.sleep(delay)
            await self.delete_message(message_reference)
            if extra_message:
                try:
                    await self.delete_message(extra_message)
                except:  # Ignore permissions errors
                    pass

        elif response[2] == 3:  # Active
            if message_reference is None:  # Forbidden exception
                return
            try:
                await commands.handle_active_message(
                    self, message_reference, command, response[3])
            except Exception as e:  # General error
                message_reference = await self.handle_error(
                    e, message, parsed_input, response, edit=message_reference)
                self.last_response = message_reference

        elif response[2] == 4:  # Replace
            try:
                if self.selfbot and not replacement_message:  # Edit instead
                    await self.edit_message(message, response[0])
                else:
                    try:
                        await self.delete_message(message)
                    except:  # Ignore permissions errors
                        pass
            except Exception as e:
                message_reference = await self.handle_error(
                    e, message, parsed_input, response, edit=message_reference)
                self.last_response = message_reference

        elif response[2] == 5:  # Send file
            try:
                if type(response[3]) is str and response[3]:
                    filename = response[3]
                    content = None
                elif (type(response[3]) is tuple and
                        len(response[3]) == 2 and response[3][1]):
                    filename, content = response[3]
                else:
                    filename, content = None, None
                await self.send_file(
                    message.channel, response[0],
                    filename=filename, content=content)
                try:
                    response[0].close()
                except:  # Ignore closing exceptions
                    pass
                plugins.broadcast_event(
                    self, 'bot_on_response', response,
                    message_reference, message)
            except Exception as e:
                message_reference = await self.handle_error(
                    e, message, parsed_input, response, edit=message_reference)
                self.last_response = message_reference

    async def handle_error(
            self, error, message, parsed_input, response, edit=None):
        """Common error handler for sending responses."""
        send_function = self.edit_message if edit else self.send_message
        location = edit if edit else message.channel
        self.last_traceback = traceback.format_exc()
        self.last_exception = error

        if type(error) is BotException:
            plugins.broadcast_event(self, 'bot_on_error', error, message)
            message_reference = await send_function(location, str(error))

        elif type(error) is discord.HTTPException and message and response:
            plugins.broadcast_event(
                self, 'bot_on_discord_error', error, message)
            self.last_exception = error
            if len(response[0]) > 1998:
                message_reference = await utilities.send_text_as_file(
                    self, message.channel, response[0], 'response',
                    extra="The response is too long. Here is a text file of "
                    "the contents.")
            else:
                message_reference = await send_function(
                    location, "Huh, I couldn't deliver the message "
                    "for some reason.\n{}".format(error))

        elif type(error) is discord.Forbidden:
            plugins.broadcast_event(
                self, 'bot_on_discord_error', error, message)
            message_reference = None
            try:
                await self.send_message(
                    message.author, "Sorry, I don't have permission to carry "
                    "out that command in that channel. The bot may have had "
                    "its `Send Messages` permission revoked (or any other "
                    "necessary permissions, like `Manage Messages` or "
                    "`Speak`).\nIf you are a bot moderator or server owner, "
                    "you can mute channels with `{}mod mute <channel>` "
                    "instead of using permissions directly. If that's not the "
                    "issue, be sure to check that the bot has the proper "
                    "permissions on the server and each channel!".format(
                        self.command_invokers[0]))
            except:  # User has blocked the bot
                pass

        else:
            plugins.broadcast_event(
                self, 'bot_on_general_error', error, message)
            logging.error(self.last_traceback)
            logging.error(self.last_exception)
            await utilities.notify_owners(
                self, '```\n{0}\n{1}\n{2}\n{3}```'.format(
                    message.content, parsed_input,
                    self.last_exception, self.last_traceback))
            insult = random.choice(exception_insults)
            error = '{0}\n`{1}: {2}`'.format(
                insult,  type(error).__name__, error)
            message_reference = await send_function(location, error)

        return message_reference

    async def on_ready(self):
        if self.fresh_boot is None:
            if self.selfbot:  # Selfbot safety checks
                if len(self.owners) != 1:
                    raise BotException(
                        EXCEPTION, "There can be only one owner for "
                        "a selfbot.", error_type=ErrorTypes.STARTUP)
                elif self.owners[0] != self.user.id:
                    raise BotException(
                        EXCEPTION, "Token does not match the owner.",
                        error_type=ErrorTypes.STARTUP)
            # Make sure server data is ready
            data.check_all(self)
            data.load_data(self)
            self.fresh_boot = True
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
                    await self.send_message(debug_channel, "Started up fresh.")
                else:
                    await self.send_file(
                        debug_channel, log_file, content="Logs:")
                if not os.path.isfile(error_file):
                    await self.send_message(debug_channel, "No error log.")
                else:
                    await self.send_file(
                        debug_channel, error_file, content="Last error:")
            elif debug_channel is not None:
                await self.send_message(debug_channel, "Reconnected.")

        if self.debug:
            logging.debug("=== {0: ^40} ===".format(
                self.user.name + ' online'))
        else:
            print("=== {0: ^40} ===".format(self.user.name + ' online'))

        if self.fresh_boot:
            if self.selfbot:
                asyncio.ensure_future(self.selfbot_away_loop())
            asyncio.ensure_future(self.spam_clear_loop())
            asyncio.ensure_future(self.save_loop())

    # Take advantage of dispatch to intercept all events
    def dispatch(self, event, *args, **kwargs):
        super().dispatch(event, *args, **kwargs)
        plugins.broadcast_event(self, 'on_' + event, *args, **kwargs)

    async def selfbot_away_loop(self):
        """Sets the status to 'away' every 5 minutes."""
        while True:
            await asyncio.sleep(300)
            self_member = next(iter(self.servers)).me
            self_status, self_game = self_member.status, self_member.game
            if not isinstance(self_status, discord.Status.idle):
                await self.change_presence(game=self_game, afk=True)

    async def spam_clear_loop(self):
        """Loop to clear the spam dictionary periodically."""
        try:
            interval = self.configurations['core']['command_limit_timeout']
            interval = 0 if interval <= 0 else int(interval)
        except:
            logging.warn("Command limit timeout not configured.")
            interval = 0
        while interval:
            await asyncio.sleep(interval)
            if self.spam_dictionary:
                self.spam_dictionary = {}

    async def save_loop(self):
        """Runs the loop that periodically saves data."""
        try:
            interval = int(self.configurations['core']['save_interval'])
            interval = 0 if interval <= 0 else interval
        except:
            logging.warn("Saving interval not configured.")
            interval = 0
        while interval:
            await asyncio.sleep(interval)
            self.save_data()

    def save_data(self, force=False):
        logging.debug("Saving data...")
        data.save_data(self, force=force)
        logging.debug("Saving data complete.")

    def restart(self):
        logging.debug("Attempting to restart the bot...")
        self.save_data(force=True)
        asyncio.ensure_future(self.logout())
        os.system('python3.5 ' + self.path + '/start.py')

    def shutdown(self):
        logging.debug("Writing data on shutdown...")
        if self.fresh_boot is not None:  # Don't write blank data
            self.save_data(force=True)
        logging.debug("Closing down!")
        try:
            asyncio.ensure_future(self.logout())
        except:
            pass
        sys.exit()


def initialize(start_file, debug=False):
    if debug:
        path = os.path.split(os.path.realpath(start_file))[0]
        log_file = '{}/temp/logs.txt'.format(path)
        if os.path.isfile(log_file):
            shutil.copy2(log_file, '{}/temp/last_logs.txt'.format(path))
        logging.basicConfig(
                level=logging.DEBUG,
                handlers=[logging.handlers.RotatingFileHandler(
                    log_file, maxBytes=1000000, backupCount=3)])
    try:
        bot = Bot(start_file, debug)
        bot.run(bot.get_token(), bot=not bot.selfbot)
    except Exception as e:
        logging.error("An uncaught exception occurred.\n{}".format(e))
        traceback.print_exc()
        error_message = '{0}\n{1}'.format(e, traceback.format_exc())
        with open('{}/temp/error.txt'.format(path), 'w') as error_file:
            error_file.write(error_message)
        logging.error("Error file written.")
    logging.warn("Bot disconnected. Shutting down...")
    bot.shutdown()
