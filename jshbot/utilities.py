import asyncio
import functools
import urllib

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


def future(function, *args, **kwargs):
    """Returns the given function as a future."""
    loop = asyncio.get_event_loop()
    function = functools.partial(function, *args, **kwargs)
    return loop.run_in_executor(None, function)


def get_cleaned_filename(name, limit=200, extension=None):
    """Cleans up the filename to a limited set of ASCII characters."""
    if extension:
        extension = '.{}'.format(extension)
        limit -= len(extension)
    else:
        extension = ''
    cleaned_list = []
    for char in name:
        num = ord(char)
        if (48 <= num <= 57 or  # [0-9]
                65 <= num <= 90 or  # [A-Z]
                97 <= num <= 122 or  # [a-z]
                num in (95, 45)):  # Underscore and dash
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
    # TODO: Type check player
    data.add(
        bot, 'base', 'voice_player', player,
        server_id=server_id, volatile=True)


async def join_and_ready(bot, voice_channel, server, include_player=False):
    """Joins the voice channel and stops any player if it exists.

    Returns the voice_client object from bot.join_voice_channel.
    If include_player is True, this will return a tuple of both the voice
    client and the player (None if not found).
    """
    if not bot.is_voice_connected(server):
        try:
            voice_client = await bot.join_voice_channel(voice_channel)
        except Exception as e:
            raise BotException(
                EXCEPTION, "Failed to join the voice channel.", e=e)
        player = None
    else:
        voice_client = bot.voice_client_in(server)
        if voice_client.channel != voice_channel:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                raise BotException(
                    EXCEPTION, "Failed to move to the voice channel.", e=e)
        player = get_player(bot, server.id)
        if player is not None and player.is_playing():
            player.stop()

    if include_player:
        return (voice_client, player)
    else:
        return voice_client


def get_formatted_message(message):
    """Gets a log-friendly format of the given message."""
    if message.edited_timestamp:
        edited = ' (edited {})'.format(message.edited_timestamp)
    else:
        edited = ''
    if message.attachments:
        urls = []
        for attachment in message.attachments:
            urls.append(attachment['url'])
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


async def send_text_as_file(bot, channel, text, filename):
    """Sends the given text as a text file."""
    file_location = '{0}/temp/{1}.txt'.format(bot.path, filename)
    with open(file_location, 'w') as text_file:
        text_file.write(text)
    await bot.send_file(channel, file_location)


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


async def notify_owners(bot, message):
    """Sends all owners a direct message with the given text."""
    for owner in bot.owners:
        member = data.get_member(bot, owner)
        await bot.send_message(member, message)
