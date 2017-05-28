import discord
import asyncio
import aiohttp
import functools
import shutil
import logging
import os
import io

from jshbot import data, configurations, core
from jshbot.exceptions import BotException

EXCEPTION = 'Utilities'


def add_bot_permissions(bot, plugin_name, **permissions):
    """Adds the given permissions to the bot for authentication generation."""
    dummy = discord.Permissions()
    for permission in permissions:
        try:
            getattr(dummy, permission.lower())
        except:  # Permission not found
            raise BotException(
                EXCEPTION, "Permission '{}' does not exist", permission)
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
            raise BotException(
                EXCEPTION, "Failed to download file.", response_code)
        with open(file_location, 'wb') as download:
            download.write(downloaded_bytes)
        if include_name:
            return (file_location, cleaned_name)
        else:
            return file_location
    except Exception as e:
        raise BotException(EXCEPTION, "Failed to download the file.", e=e)


def delete_temporary_file(bot, filename, safe=True):
    """Deletes the given file from the temp folder."""
    try:
        os.remove('{0}/temp/{1}'.format(bot.path, filename))
    except Exception as e:
        if not safe:
            raise BotException(EXCEPTION, "File could not be deleted.", e=e)


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
        raise BotException(EXCEPTION, "Failed to retrieve a URL.", e)


async def upload_to_discord(bot, fp, filename=None, rewind=True, close=False):
    """Uploads the given file-like object to the upload channel.

    If the upload channel is specified in the configuration files, files
    will be uploaded there. Otherwise, a new server will be created, and
    used as the upload channel."""
    channel_id = configurations.get(bot, 'core', 'upload_channel')
    if not channel_id:  # Check to see if a server was already created
        channel_id = data.get(bot, 'core', 'upload_channel')
    for instance in bot.all_instances:
        channel = instance.get_channel(channel_id)
        if channel:
            break

    if channel is None:  # Create server
        logging.debug("Creating server for upload channel...")
        try:
            server = await bot.create_server('uploads')
        except Exception as e:
            raise BotException(
                EXCEPTION,
                "Failed to create upload server. This bot is not whitelisted "
                "to create servers.", e=e)
        data.add(bot, 'core', 'upload_channel', server.id)
        channel = bot.get_channel(server.id)

    if channel is None:  # Shouldn't happen
        raise BotException(EXCEPTION, "Failed to get upload channel.")

    try:
        message = await bot.send_file(channel, fp, filename=filename)
        upload_url = message.attachments[0]['url']
    except Exception as e:
        raise BotException(EXCEPTION, "Failed to upload file.", e=e)

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
        raise BotException(EXCEPTION, "Failed to await coroutines.", e=e)


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


def get_player(bot, server_id):
    """Gets the voice player on the given server. None otherwise."""
    return data.get(
        bot, 'base', 'voice_player', server_id=server_id, volatile=True)


def set_player(bot, server_id, player):
    """Sets the voice player of the given server."""
    data.add(
        bot, 'base', 'voice_player', player,
        server_id=server_id, volatile=True)


async def join_and_ready(
        bot, voice_channel, include_player=False,
        is_mod=False, reconnect=False):
    """Joins the voice channel and stops any player if it exists.

    Returns the voice_client object from bot.join_voice_channel.
    If include_player is True, this will return a tuple of both the voice
    client and the player (None if not found).
    """
    server = voice_channel.server
    muted = voice_channel.id in data.get(
        bot, 'base', 'muted_channels', server_id=server.id, default=[])
    if voice_channel == server.afk_channel:
        raise BotException(EXCEPTION, "This is the AFK channel.")
    if muted and not is_mod:
        raise BotException(
            EXCEPTION, "The bot is muted in this voice channel.")
    if reconnect:
        await leave_and_stop(bot, server)
    if not bot.is_voice_connected(server):
        try:
            voice_client = await bot.join_voice_channel(voice_channel)
        except Exception as e:
            raise BotException(
                EXCEPTION, "Failed to join the voice channel.", e=e)
    else:
        voice_client = bot.voice_client_in(server)
        if voice_client.channel != voice_channel:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                raise BotException(
                    EXCEPTION, "Failed to move to the voice channel.", e=e)

    player = get_player(bot, server.id)
    if player is not None:
        if player.is_playing() or not player.is_done():
            player.stop()
        '''
        elif not player.is_done():  # Can this even happen?
            raise BotException(
                EXCEPTION, "Audio is pending, please try again later.")
        '''

    if include_player:
        return (voice_client, player)
    else:
        return voice_client


async def leave_and_stop(bot, server, member=None, safe=True):
    """Leaves any voice channel in the given server and stops any players.

    Keyword arguments:
    member -- Checks that the the bot is connected to the member's
        voice channel. The safe option overrides this.
    safe -- Prevents exceptions from being thrown. Can be seen as 'silent'.
    """
    player = get_player(bot, server.id)
    if player is not None and player.is_playing():
        player.stop()

    voice_client = bot.voice_client_in(server)
    if not voice_client:
        if not safe:
            raise BotException(
                EXCEPTION, "Bot not connected to a voice channel.")
    elif member and voice_client.channel != member.voice_channel:
        if not safe:
            raise BotException(
                EXCEPTION, "Bot not connected to your voice channel.")
    else:
        await voice_client.disconnect()


async def delayed_leave(bot, server_id, player, delay=60):
    """Leaves the voice channel associated with the given server.

    This command does nothing if the current player of the server is not the
    same as the one given.
    """
    # TODO: Implement


def get_formatted_message(message):
    """Gets a log-friendly format of the given message."""
    if message.edited_timestamp:
        edited = ' (edited {})'.format(message.edited_timestamp)
    else:
        edited = ''
    if message.attachments:
        urls = [attachment['url'] for attachment in message.attachments]
        attached = ' (attached {})'.format(urls)
    else:
        attached = ''
    return ("{0.author.name}#{0.author.discriminator} ({0.author.id}) "
            "at {0.timestamp}{1}{2}:\r\n\t{0.content}").format(
                message, edited, attached)


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


async def get_log_text(bot, channel, **log_arguments):
    """Wrapper function for Carter's time machine."""
    messages = []
    async for message in bot.logs_from(channel, **log_arguments):
        messages.append(message)
    return '\r\n\r\n'.join(
        get_formatted_message(message) for message in reversed(messages))


async def send_text_as_file(bot, channel, text, filename, extra=None):
    """Sends the given text as a text file."""
    file_location = '{0}/temp/{1}.txt'.format(bot.path, filename)
    with open(file_location, 'w') as text_file:
        text_file.write(text)
    reference = await bot.send_file(channel, file_location, content=extra)
    asyncio.ensure_future(future(os.remove, file_location))
    return reference


def get_text_as_file(bot, text):
    """Converts the text into a bytes object using BytesIO."""
    try:
        # return io.BytesIO(bytes(str(text)), str.encode)
        return io.BytesIO(bytes(str(text), 'utf-8'))
    except Exception as e:
        raise BotException(EXCEPTION, "Failed to convert text to a file.", e=e)


def get_invoker(bot, server=None):
    """Gets a suitable command invoker for the bot.

    If a server is specified, this will check for a custom invoker and
    whether or not mention mode is enabled.
    """
    if server is not None:
        server_data = data.get(
            bot, 'base', None, server_id=server.id, default={})
        if server_data.get('mention_mode', False):
            invoker = '{} '.format(server.me.display_name)
        else:
            invoker = server_data.get('command_invoker', None)
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
                await bot.send_message(member, message)


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
    shutil.make_archive(
        backup_indices.format(1)[:-4], 'zip', '{}/data'.format(bot.path))
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
        raise BotException(
            EXCEPTION, "Failed to extract backup.", e=e)
    logging.debug("Finished data restore.")
