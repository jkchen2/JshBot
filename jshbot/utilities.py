import discord
import asyncio
import aiohttp
import functools
import shutil
import logging
import os
import io

from jshbot import data, configurations, core
from jshbot.exceptions import BotException, ConfiguredBotException

CBException = ConfiguredBotException('Utilities')


class BaseConverter():
    def __init__(self):
        self.error_reason = None
    def get_convert_error(self, *args):
        return self.error_reason


class MemberConverter(BaseConverter):
    def __init__(self, server_only=True):
        self.server_only = server_only
        super().__init__()
    def __call__(self, bot, message, value, *a):
        guild = message.guild if self.server_only else None
        try:
            return data.get_member(bot, value, guild=guild, strict=self.server_only)
        except BotException as e:
            self.set_error_reason(e, 'member')
    def set_error_reason(self, error, convert_type):
        if error.error_subject.startswith('Duplicate'):
            pre_format = "Duplicate {}s found.".format(convert_type)
        else:
            pre_format = "{} not found.".format(convert_type.title())
        self.error_reason = pre_format + ' Please use a mention.'
        assert False  # To trigger the conversion error
    def get_convert_error(self, *args):
        return self.error_reason


class ChannelConverter(MemberConverter):
    def __call__(self, bot, message, value, *a):
        guild = message.guild if self.server_only else None
        try:
            return data.get_channel(bot, value, guild=guild, strict=self.server_only)
        except BotException as e:
            self.set_error_reason(e, 'channel')


class RoleConverter(MemberConverter):
    def __init__(self):
        super().__init__()
    def __call__(self, bot, message, value, *a):
        try:
            bot.extra = (bot, message, value, *a)
            return data.get_role(bot, value, message.guild)
        except BotException as e:
            self.set_error_reason(e, 'role')


def add_bot_permissions(bot, plugin_name, **permissions):
    """Adds the given permissions to the bot for authentication generation."""
    dummy = discord.Permissions()
    for permission in permissions:
        try:
            getattr(dummy, permission.lower())
        except:  # Permission not found
            raise CBException("Permission '{}' does not exist", permission)
    current = data.get(
        bot, plugin_name, 'permissions', create=True, volatile=True)
    if current is None:
        data.add(bot, plugin_name, 'permissions', permissions, volatile=True)


def get_permission_bits(bot):
    """Calculates all of the permissions for each plugin."""
    dummy = discord.Permissions()
    for plugin in bot.plugins.keys():
        for permission in data.get(
                bot, plugin, 'permissions', volatile=True, default={}):
            setattr(dummy, permission.lower(), True)
    return dummy.value


async def download_url(bot, url, include_name=False, extension=None):
    """Asynchronously downloads the given file to the temp folder.

    Returns the path of the downloaded file. If include_name is True, returns
    a tuple of the file location and the file name.
    """
    cleaned_name = get_cleaned_filename(url, extension=extension)
    file_location = '{0}/temp/{1}'.format(bot.path, cleaned_name)
    try:
        response_code, downloaded_bytes = await get_url(
            bot, url, get_bytes=True, headers={'User-Agent': 'Mozilla/5.0'})
        if response_code != 200:
            raise CBException("Failed to download file.", response_code)
        with open(file_location, 'wb') as download:
            download.write(downloaded_bytes)
        if include_name:
            return (file_location, cleaned_name)
        else:
            return file_location
    except Exception as e:
        raise CBException("Failed to download the file.", e=e)


def delete_temporary_file(bot, filename, safe=True):
    """Deletes the given file from the temp folder."""
    try:
        os.remove('{0}/temp/{1}'.format(bot.path, filename))
    except Exception as e:
        if not safe:
            raise CBException("File could not be deleted.", e=e)


async def get_url(bot, urls, headers={}, get_bytes=False):
    """Uses aiohttp to asynchronously get a url response, or multiple."""
    read_method = 'read' if get_bytes else 'text'
    try:
        with aiohttp.ClientSession(headers=headers, loop=bot.loop) as session:

            async def fetch(url, read_method='text'):
                if not url:  # Why
                    return (None, None)
                async with session.get(url) as response:
                    return (
                        response.status,
                        await getattr(response, read_method)())

            if isinstance(urls, list) or isinstance(urls, tuple):
                coroutines = [fetch(url, read_method) for url in urls]
                result = await parallelize(coroutines)
            else:
                result = await fetch(urls, read_method)
            return result
    except Exception as e:
        raise CBException("Failed to retrieve a URL.", e)


async def upload_to_discord(bot, fp, filename=None, rewind=True, close=False):
    """Uploads the given file-like object to the upload channel.

    If the upload channel is specified in the configuration files, files
    will be uploaded there. Otherwise, a new guild will be created, and
    used as the upload channel."""
    channel_id = configurations.get(bot, 'core', 'upload_channel')
    if not channel_id:  # Check to see if a guild was already created
        channel_id = data.get(bot, 'core', 'upload_channel')
    for instance in bot.all_instances:
        channel = instance.get_channel(channel_id)
        if channel:
            break

    if channel is None:  # Create guild
        logging.debug("Creating guild for upload channel...")
        try:
            guild = await bot.create_guild('uploads')
        except Exception as e:
            raise CBException(
                "Failed to create upload guild. This bot is not whitelisted "
                "to create guilds.", e=e)
        data.add(bot, 'core', 'upload_channel', guild.id)
        channel = bot.get_channel(guild.id)

    if channel is None:  # Shouldn't happen
        raise CBException("Failed to get upload channel.")

    try:
        message = await bot.send_file(channel, fp, filename=filename)
        upload_url = message.attachments[0]['url']
    except Exception as e:
        raise CBException("Failed to upload file.", e=e)

    if close:
        try:
            fp.close()
        except:
            pass
    elif rewind:
        try:
            fp.seek(0)
        except:
            pass

    return upload_url


async def parallelize(coroutines, return_exceptions=False):
    """Uses asyncio.gather to "parallelize" the coroutines (not really)."""
    try:
        return await asyncio.gather(
            *coroutines, return_exceptions=return_exceptions)
    except Exception as e:
        raise CBException("Failed to await coroutines.", e=e)


def future(function, *args, **kwargs):
    """Returns the given function as a future."""
    loop = asyncio.get_event_loop()
    function = functools.partial(function, *args, **kwargs)
    return loop.run_in_executor(None, function)


def get_cleaned_filename(name, cleaner=False, limit=200, extension=None):
    """Cleans up the filename to a limited set of ASCII characters."""
    if extension:
        extension = '.{}'.format(extension)
        limit -= len(extension)
    else:
        extension = ''
    cleaned_list = []
    for char in name:
        if cleaner:  # Does not include underscores or dashes
            if char.isalnum():
                cleaned_list.append(char)
        else:
            if char.isalnum() or ord(char) in (95, 45):
                cleaned_list.append(char)
    if len(cleaned_list) > limit:  # Because Windows file limitations
        cleaned_list = cleaned_list[:limit]
    return ''.join(cleaned_list).lower() + extension


def get_player(bot, guild_id):
    """Gets the voice player on the given guild. None otherwise."""
    return data.get(
        bot, 'base', 'voice_player', guild_id=guild_id, volatile=True)


def set_player(bot, guild_id, player):
    """Sets the voice player of the given guild."""
    data.add(
        bot, 'base', 'voice_player', player,
        guild_id=guild_id, volatile=True)


# TODO: Convert muted channels into ints
# TODO: Check code for missing 'include_player' parameter
async def join_and_ready(bot, voice_channel, is_mod=False, reconnect=False):
    """Joins the voice channel and stops any player if it exists.

    Returns the voice_client object from bot.join_voice_channel.
    If include_player is True, this will return a tuple of both the voice
    client and the player (None if not found).
    """
    guild = voice_channel.guild
    muted = voice_channel.id in data.get(
        bot, 'base', 'muted_channels', guild_id=guild.id, default=[])
    if voice_channel == guild.afk_channel:
        raise CBException("This is the AFK channel.")
    if muted and not is_mod:
        raise CBException("The bot is muted in this voice channel.")
    if reconnect:
        await leave_and_stop(bot, guild)

    voice_client = guild.voice_client
    if not voice_client:
        try:
            voice_client = await voice_channel.connect()
        except Exception as e:
            raise CBException("Failed to join the voice channel.", e=e)
    else:
        if voice_client.channel != voice_channel:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                raise CBException("Failed to move to the voice channel.", e=e)

    if voice_client.is_playing():
        voice_client.stop()
    return voice_client


async def leave_and_stop(bot, guild, member=None, safe=True):
    """Leaves any voice channel in the given guild and stops any players.

    Keyword arguments:
    member -- Checks that the the bot is connected to the member's
        voice channel. The safe option overrides this.
    safe -- Prevents exceptions from being thrown. Can be seen as 'silent'.
    """
    voice_client = guild.voice_client
    if not voice_client:
        if safe:
            return
        else:
            raise CBException("Bot not connected to a voice channel.")
    voice_client.stop()
    member_voice = member.voice.channel if member and member.voice else None
    if member and voice_client.channel != member_voice:
        if not safe:
            raise CBException("Bot not connected to your voice channel.")
    else:
        await voice_client.disconnect()


async def delayed_leave(bot, guild_id, player, delay=60):
    """Leaves the voice channel associated with the given guild.

    This command does nothing if the current player of the guild is not the
    same as the one given.
    """
    # TODO: Implement


def get_time_string(total_seconds, text=False, full=False):
    """Gets either digital-clock-like time or time in plain English."""
    total_seconds = int(total_seconds)
    values = [
        ('weeks', int(total_seconds / 604800)),
        ('days', int((total_seconds % 604800) / 86400)),
        ('hours', int((total_seconds % 86400) / 3600)),
        ('minutes', int((total_seconds % 3600) / 60)),
        ('seconds', int(total_seconds % 60))
    ]
    result = []

    if text:
        for scale, value in values:
            if value > 0:
                result.append('{} {}{}'.format(
                    value, scale[:-1], '' if value == 1 else 's'))
                if not full:
                    break
        for it in range(len(result) - 2):
            result.insert((it * 2) + 1, ', ')
        if len(result) > 1:
            result.insert(-1, ' and ')

    else:
        for scale, value in values:
            if value > 0 or full or scale == 'minutes':
                if scale in ('hours', 'minutes', 'seconds') and full:
                    format_string = '{:0>2}'
                else:
                    format_string = '{}'
                result.append(format_string.format(value))
                full = True

    return '{}'.format('' if text else ':').join(result)


def get_formatted_message(message):
    """Gets a log-friendly format of the given message."""
    if message.edited_at:
        edited = ' (edited {})'.format(message.edited_at)
    else:
        edited = ''
    if message.attachments:
        urls = [attachment['url'] for attachment in message.attachments]
        attached = ' (attached {})'.format(urls)
    else:
        attached = ''
    return ("{0.author.name}#{0.author.discriminator} ({0.author.id}) "
            "at {0.created_at}{1}{2}:\r\n\t{0.content}").format(
                message, edited, attached)


async def get_log_text(bot, channel, **log_arguments):
    """Wrapper function for Carter's time machine."""
    messages = []
    async for message in channel.history(**log_arguments):
        messages.append(message)
    return '\r\n\r\n'.join(get_formatted_message(message) for message in reversed(messages))


# TODO: Look through experiments and tags for changes
async def send_text_as_file(channel, text, filename, extra=None):
    """Sends the given text as a text file."""
    discord_file = discord.File(get_text_as_file(text), filename=filename + '.txt')
    reference = await channel.send(content=extra, file=discord_file)
    return reference


# TODO: Look through tags and playlist for changes
def get_text_as_file(text):
    """Converts the text into a bytes object using BytesIO."""
    try:
        return io.BytesIO(bytes(str(text), 'utf-8'))
    except Exception as e:
        raise CBException("Failed to convert text to a file.", e=e)


def get_invoker(bot, guild=None):
    """Gets a suitable command invoker for the bot.

    If a guild is specified, this will check for a custom invoker and
    whether or not mention mode is enabled.
    """
    if guild is not None:
        guild_data = data.get(
            bot, 'base', None, guild_id=guild.id, default={})
        if guild_data.get('mention_mode', False):
            invoker = '{} '.format(guild.me.display_name)
        else:
            invoker = guild_data.get('command_invoker', None)
    else:
        invoker = None
    if invoker is None:
        invoker = bot.command_invokers[0]
    return invoker


async def notify_owners(bot, message, user_id=None):
    """Sends all owners a direct message with the given text.

    If user_id is specified, this will check that the user is not in the
    blacklist.
    """
    if bot.selfbot:
        print("Notification:\n{}".format(message))
    else:
        if user_id:
            blacklist = data.get(bot, 'base', 'blacklist', default=[])
            if user_id in blacklist:
                await asyncio.sleep(0.5)
                return
        for owner in bot.owners:
            member = data.get_member(bot, owner)
            if len(message) > 1998:
                await send_text_as_file(bot, member, message, 'notification')
            else:
                await member.send(message)


def make_backup(bot):
    """Makes a backup of the data directory."""
    logging.debug("Making backup...")
    backup_indices = '{0}/temp/backup{{}}.zip'.format(bot.path)
    if os.path.isfile(backup_indices.format(5)):
        os.remove(backup_indices.format(5))
    for it in range(1, 5):
        backup_file_from = backup_indices.format(5-it)
        backup_file_to = backup_indices.format(6-it)
        if os.path.isfile(backup_file_from):
            os.rename(backup_file_from, backup_file_to)
    shutil.make_archive(backup_indices.format(1)[:-4], 'zip', '{}/data'.format(bot.path))
    logging.debug("Finished making backup.")


def restore_backup(bot, backup_file):
    """Restores a backup file given the backup filename."""
    logging.debug("Restoring from a backup file...")
    try:
        core.bot_data = {'global_users': {}, 'global_plugins': {}}
        core.volatile_data = {'global_users': {}, 'global_plugins': {}}
        shutil.unpack_archive(backup_file, '{}/data'.format(bot.path))
        for instance in bot.all_instances:
            data.check_all(instance)
            data.load_data(instance)
    except Exception as e:
        raise CBException("Failed to extract backup.", e=e)
    logging.debug("Finished data restore.")
