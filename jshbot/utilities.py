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
        bot, 'base', 'voice_client', server_id=server_id, volatile=True)


def set_player(bot, server_id, player):
    """Sets the voice player of the given server."""
    # TODO: Type check player
    data.add(
        bot, 'base', 'voice_client', player,
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
        player = get_player(bot, server.id)
        if player is not None and player.is_playing():
            player.stop()

    if include_player:
        return (voice_client, player)
    else:
        return voice_client
