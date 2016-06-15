import asyncio
import discord
import logging
import os.path
import random
import time
import sys
import os

# Debug
import traceback

from jshbot import configurations, plugins, commands, parser, data
from jshbot.exceptions import BotException

EXCEPTION = 'Core'

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
    'Of *course*. Nothing ever works out, does it?'
]


class Bot(discord.Client):

    def __init__(self, start_file, debug):
        self.version = '0.3.0-alpha'
        self.date = 'June 14th, 2016'
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
        self.owners = config['owners']
        self.edit_timeout = config['edit_timeout']
        self.last_exception = None
        self.last_traceback = None
        self.extra = None

    def get_token(self):
        return self.configurations['core']['token']

    def can_respond(self, message):
        """Determines whether or not the bot can respond.

        Checks that the message has text, matches an invoker, and that the
        server/channel/user is not muted or blocked. Admins and mods
        override this.
        """
        # Ignore empty messages and messages by bots
        if (not message.content or message.author.bot or
                message.author.id == self.user.id):
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
        plugins.broadcast_event(self, 2, message)

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
                await self.send_message(
                    message.channel, "{}, you appear to be issuing/editing "
                    "commands too quickly. Please wait {} seconds.".format(
                        message.author.mention, self.spam_timeout))
            return

        # Bot is clear to get response. Send typing to signify
        if not replacement_message:
            typing_task = asyncio.ensure_future(
                    self.send_typing(message.channel))
        else:
            typing_task = None

        # Parse command and reply
        try:
            logging.debug(message.author.name + ': ' + message.content)
            parsed_input = parser.parse(
                self, command, base, parameters, server=message.server)
            logging.debug('\t' + str(parsed_input))
            print(parsed_input[:-1])  # Temp
            response = await (commands.execute(
                self, message, command, parsed_input, initial_data))
        except BotException as e:  # Respond with error message
            response = (str(e), False, 0, None)
        except Exception as e:  # General error
            self.last_traceback = traceback.format_exc()
            self.last_exception = e
            logging.error(e)
            logging.error(self.last_traceback)
            insult = random.choice(exception_insults)
            error = '{0}\n`{1}: {2}`'.format(insult,  type(e).__name__, e)
            response = (error, False, 0, None)

        # If a replacement message is given, edit it
        if typing_task:
            typing_task.cancel()
        try:
            if replacement_message:
                self.extra = replacement_message
                message_reference = await self.edit_message(
                    replacement_message, response[0])
            elif response[0]:
                message_reference = await self.send_message(
                    message.channel, response[0], tts=response[1])
            else:  # Empty message
                response = (None, None, 1, None)
        except discord.HTTPException as e:
            self.last_exception = e
            if 'too long' in e.args[0]:
                message_reference = await self.send_message(
                    message.channel, "The response is too long.")
            else:
                message_reference = await self.send_message(
                    message.channel, "Huh, I couldn't deliver the message "
                    "for some reason.\n{}".format(e))
        except Exception as e:
            self.last_traceback = traceback.format_exc()
            self.last_exception = e
            logging.error(e)
            logging.error(self.last_exception)
            return

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
        # If message_type is >= 1, do not add to the edit dictionary

        if response[2] == 0:  # Normal
            # Edited commands are handled in base.py
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
                except:  # Ignore for permissions errors
                    pass

        elif response[2] == 3:  # Active
            try:
                await commands.handle_active_message(
                    self, message_reference, command, response[3])
            except BotException as e:  # Respond with error message
                await self.edit_message(message_reference, str(e))
            except Exception as e:  # General error
                self.last_traceback = traceback.format_exc()
                self.last_exception = e
                logging.error(e)
                logging.error(self.last_traceback)
                insult = random.choice(exception_insults)
                error = '{0}\n`{1}: {2}`'.format(insult,  type(e).__name__, e)
                await self.edit_message(message_reference, error)

    async def on_ready(self):
        # Make sure server data is ready
        data.check_all(self)
        data.load_data(self)

        plugins.broadcast_event(self, 0)

        if self.debug:
            logging.debug("=== {0: ^40} ===".format(
                self.user.name + ' online'))
        else:
            print("=== {0: ^40} ===".format(self.user.name + ' online'))

        asyncio.ensure_future(self.spam_clear_loop())
        await self.save_loop()

    async def on_error(self, event, *args, **kwargs):
        plugins.broadcast_event(self, 1, event, *args, **kwargs)
    async def on_socket_raw_receive(self, msg):
        plugins.broadcast_event(self, 3, msg)
    async def on_socket_raw_send(self, payload):
        plugins.broadcast_event(self, 4, payload)
    async def on_message_delete(self, message):
        plugins.broadcast_event(self, 5, message)
    async def on_message_edit(self, before, after):
        plugins.broadcast_event(self, 6, before, after)
    async def on_channel_delete(self, channel):
        plugins.broadcast_event(self, 7, channel)
    async def on_channel_create(self, channel):
        plugins.broadcast_event(self, 8, channel)
    async def on_channel_update(self, before, after):
        plugins.broadcast_event(self, 9, before, after)
    async def on_member_join(self, member):
        plugins.broadcast_event(self, 10, member)
    async def on_member_update(self, before, after):
        plugins.broadcast_event(self, 11, before, after)
    async def on_server_join(self, server):
        plugins.broadcast_event(self, 12, server)
    async def on_server_remove(self, server):
        plugins.broadcast_event(self, 13, server)
    async def on_server_update(self, before, after):
        plugins.broadcast_event(self, 14, before, after)
    async def on_server_role_create(self, server, role):
        plugins.broadcast_event(self, 15, server, role)
    async def on_server_role_delete(self, server, role):
        plugins.broadcast_event(self, 16, server, role)
    async def on_server_role_update(self, before, after):
        plugins.broadcast_event(self, 17, before, after)
    async def on_server_available(self, server):
        plugins.broadcast_event(self, 18, server)
    async def on_server_unavailable(self, server):
        plugins.broadcast_event(self, 19, server)
    async def on_voice_state_update(self, before, after):
        plugins.broadcast_event(self, 20, before, after)
    async def on_member_ban(self, member):
        plugins.broadcast_event(self, 21, member)
    async def on_member_unban(self, server, user):
        plugins.broadcast_event(self, 22, server, user)
    async def on_typing(self, channel, user, when):
        plugins.broadcast_event(self, 23, channel, user, when)

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
        self.save_data(force=True)
        logging.debug("Closing down!")
        try:
            asyncio.ensure_future(self.logout())
        except:
            pass
        sys.exit()


def initialize(start_file, debug=False):
    if debug:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    bot = Bot(start_file, debug)
    bot.run(bot.get_token())
    logging.error("Bot disconnected. Shutting down...")
    bot.shutdown()
