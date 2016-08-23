import asyncio
import aiohttp
import functools
import urllib
import shutil
import logging
import os

from jshbot import data
from jshbot.exceptions import BotException

EXCEPTION = 'Utilities'


async def download_url(bot, url, include_name=False, extension=None):
    """Asynchronously downloads the given file to the temp folder.

    Returns the path of the downloaded file. If include_name is True, returns
    a tuple of the file location and the file name.
    """
    cleaned_name = get_cleaned_filename(url, extension=extension)
    file_location = '{0}/temp/{1}'.format(bot.path, cleaned_name)
    try:
        await future(urllib.request.urlretrieve, url, file_location)
        if include_name:
            return (file_location, cleaned_name)
        else:
            return file_location
    except Exception as e:
        raise BotException(EXCEPTION, "Failed to download the file.", e=e)


async def get_url(bot, url):
    """Uses aiohttp to asynchronously get a url response"""
    try:
        with aiohttp.ClientSession(loop=bot.loop) as session:
            # return session.get(url)
            async with session.get(url) as response:
                return (response.status, await response.text())
    except Exception as e:
        raise BotException(EXCEPTION, "Failed to retrieve URL.", e)


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
        if player.is_playing():
            player.stop()
        elif not player.is_done():  # Can this even happen?
            raise BotException(
                EXCEPTION, "Audio is pending, please try again later.")

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


async def delayed_leave(bot, server, player, delay=60):
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
            "at {0.timestamp}{1}{2}:\n\t{0.content}\n").format(
                message, edited, attached)


async def get_log_text(bot, channel, **log_arguments):
    """Wrapper function for Carter's time machine."""
    messages = []
    large_text = ''
    async for message in bot.logs_from(channel, **log_arguments):
        messages.append(message)
    for message in reversed(messages):
        large_text += get_formatted_message(message)
    return large_text


async def send_text_as_file(bot, channel, text, filename, extra=None):
    """Sends the given text as a text file."""
    file_location = '{0}/temp/{1}.txt'.format(bot.path, filename)
    with open(file_location, 'w') as text_file:
        text_file.write(text)
    reference = await bot.send_file(channel, file_location, content=extra)
    asyncio.ensure_future(future(os.remove, file_location))
    return reference


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
