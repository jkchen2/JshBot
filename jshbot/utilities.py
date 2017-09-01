import discord
import asyncio
import aiohttp
import functools
import zipfile
import shutil
import socket
import datetime
import json
import time
import os
import io

from jshbot import data, configurations, core, logger
from jshbot.exceptions import BotException, ConfiguredBotException

CBException = ConfiguredBotException('Utilities')


# Voice region time offsets (no DST)
voice_regions = {
    'us-west': -8,
    'us-east': -5,
    'us-south': -6,
    'us-central': -6,
    'eu-west': 1,  # West European Summer Time
    'eu-central': 2,  # Central European Summer Time
    'singapore': 8,
    'london': 0,
    'sydney': 10,
    'amsterdam': 2,  # CEST
    'frankfurt': 2,  # CEST
    'brazil': -3,
    'vip-us-east': -5,
    'vip-us-west': -8,
    'vip-amsterdam': 2  # CEST
}


class BaseConverter():
    def __init__(self):
        self.error_reason = None
    def get_convert_error(self, *args):
        return self.error_reason


class MemberConverter(BaseConverter):
    def __init__(self, server_only=True, live_check=None):
        self.server_only = server_only
        self.live_check = live_check
        super().__init__()
    def __call__(self, bot, message, value, *a):
        if self.live_check:
            self.server_only = live_check(bot, message, value, *a)
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


class ChannelConverter(MemberConverter):
    def __init__(self, server_only=True, live_check=None, constraint=None):
        self.server_only = server_only
        self.live_check = live_check
        self.constraint = constraint
        super().__init__()
    def __call__(self, bot, message, value, *a):
        if self.live_check:
            guild = live_check(bot, message, value, *a)
        else:
            guild = message.guild if self.server_only else None
        try:
            return data.get_channel(
                bot, value, guild=guild, strict=self.server_only, constraint=self.constraint)
        except BotException as e:
            self.set_error_reason(e, 'channel')


class RoleConverter(MemberConverter):
    def __init__(self):
        super().__init__()
    def __call__(self, bot, message, value, *a):
        try:
            return data.get_role(bot, value, message.guild)
        except BotException as e:
            self.set_error_reason(e, 'role')


class PercentageConverter(BaseConverter):
    def __init__(self, accuracy=3):
        self.accuracy = int(accuracy)
        super().__init__()
    def __call__(self, bot, message, value, *a):
        cleaned = value.strip('%')
        try:
            converted = float(cleaned)
        except:
            raise CBException("Must be a percentage.")
            #self.error_reason = "Must be a percentage."
        else:
            if self.accuracy is not None:
                converted = round(converted, self.accuracy)
            return converted/100


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


async def download_url(bot, url, include_name=False, extension=None, filename=None, use_fp=False):
    """Asynchronously downloads the given file to the temp folder.

    Returns the path of the downloaded file. If include_name is True, returns
    a tuple of the file location and the file name.

    If use_fp, this will use a BytesIO object instead of downloading to a file.
    """
    if use_fp:
        fp = io.BytesIO()
    else:
        if not filename:
            filename = get_cleaned_filename(url, extension=extension)
        file_location = '{0}/temp/{1}'.format(bot.path, filename)
    try:
        response_code, downloaded_bytes = await get_url(
            bot, url, get_bytes=True, headers={'User-Agent': 'Mozilla/5.0'})
        if response_code != 200:
            raise CBException("Failed to download file.", response_code)
        if use_fp:
            fp.write(downloaded_bytes)
            fp.seek(0)
            return fp
        else:
            with open(file_location, 'wb') as download:
                download.write(downloaded_bytes)
            if include_name:
                return (file_location, filename)
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


def get_temporary_file(bot, filename, safe=True):
    """Gets the filename from the temp folder."""
    test_path = '{0}/temp/{1}'.format(bot.path, filename)
    if os.path.isfile(test_path):
        return test_path
    elif safe:
        return None
    else:
        raise CBException("Temporary file not found.")


def add_temporary_file(bot, bytes_io, filename, seek=True, overwrite=True, safe=False):
    """Dumps the binary file into the temp folder."""
    test_path = '{0}/temp/{1}'.format(bot.path, filename)
    if os.path.isfile(test_path) and not overwrite and not safe:
        raise CBException("Temporary file already exists.")
    else:
        try:
            if seek and bytes_io.seekable():
                bytes_io.seek(0)
            write_type = 'w' if isinstance(bytes_io, io.StringIO) else 'wb'
            with open(test_path, write_type) as temp_file:
                temp_file.write(bytes_io.read())
        except Exception as e:
            if not safe:
                raise CBException("Failed to write temporary file.", e=e)


def get_plugin_file(bot, filename, safe=True):
    """Gets the plugin file in the plugin_data directory."""
    test_path = '{0}/plugins/plugin_data/{1}'.format(bot.path, filename)
    if os.path.isfile(test_path):
        return test_path
    elif safe:
        return None
    else:
        raise CBException("Plugin file '{}' not found.".format(filename))


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

            if isinstance(urls, (list, tuple)):
                coroutines = [fetch(url, read_method) for url in urls]
                result = await parallelize(coroutines)
            else:
                result = await fetch(urls, read_method)
            return result
    except Exception as e:
        raise CBException("Failed to retrieve a URL.", e=e)


async def upload_to_discord(bot, fp, filename=None, rewind=True, close=False):
    """Uploads the given file-like object to the upload channel.

    If the upload channel is specified in the configuration files, files
    will be uploaded there. Otherwise, a new guild will be created, and
    used as the upload channel."""
    channel_id = configurations.get(bot, 'core', 'upload_channel')
    if not channel_id:  # Check to see if a guild was already created
        channel_id = data.get(bot, 'core', 'upload_channel')
    channel = data.get_channel(bot, channel_id, safe=True)

    if channel is None:  # Create guild
        logger.debug("Creating guild for upload channel...")
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
        discord_file = discord.File(fp, filename=filename)
        message = await channel.send(file=discord_file)
        upload_url = message.attachments[0].url
    except Exception as e:
        raise CBException("Failed to upload file.", e=e)

    try:
        if close:
            fp.close()
        elif rewind:
            fp.seek(0)
    except:
        pass

    return upload_url


async def upload_logs(bot):
    """Uploads any log files to the debug channel."""
    log_zip_location = '{0}/temp/log_files.zip'.format(bot.path)
    log_zip_file = zipfile.ZipFile(log_zip_location, mode='w')
    log_location = '{0}/temp/logs.txt'.format(bot.path)
    if os.path.exists(log_location):
        log_zip_file.write(log_location, arcname=os.path.basename(log_location))
    for log_number in range(5):
        next_location = log_location + '.{}'.format(log_number + 1)
        if os.path.exists(next_location):
            log_zip_file.write(next_location, arcname=os.path.basename(next_location))
    log_zip_file.close()

    debug_channel = bot.get_channel(configurations.get(bot, 'core', 'debug_channel'))
    discord_file = discord.File(log_zip_location, filename='all_logs.zip')
    await debug_channel.send(content='All logs:', file=discord_file)


async def parallelize(coroutines, return_exceptions=False):
    """Uses asyncio.gather to "parallelize" the coroutines (not really)."""
    try:
        return await asyncio.gather(*coroutines, return_exceptions=return_exceptions)
    except Exception as e:
        raise CBException("Failed to await coroutines.", e=e)


def future(function, *args, **kwargs):
    """Returns the given function as a future."""
    loop = asyncio.get_event_loop()
    function = functools.partial(function, *args, **kwargs)
    return loop.run_in_executor(None, function)


# TODO: Deprecate in favor of clean_text
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


def clean_text(text, level=2, limit=200, custom=None, lowercase=True):
    """Cleans up the text to a limited set of ASCII characters.

    level 0: Standard ASCII characters or alphanumeric unicode
    level 1: Alphanumeric (unicode) or dash, underscore, space
    level 2: Alphanumeric (unicode) or dash, underscore (default)
    level 3: Alphanumeric (unicode) only
    level 4: Alphanumeric (ASCII) only
    """
    if custom:
        sifter = custom
    else:
        sifter = (
            lambda x: x if (x.isalnum() or 32 <= ord(x) <= 126) else '',
            lambda x: x if (x.isalnum() or ord(x) in (95, 45, 32)) else '',
            lambda x: x if (x.isalnum() or ord(x) in (95, 45)) else '',
            lambda x: x if x.isalnum() else '',
            lambda x: x if (x.isalnum() and ord(x) < 127) else ''
        )[level]
    cleaned = ''.join(sifter(char) for char in text[:limit])
    return cleaned.lower() if lowercase else cleaned


def get_player(bot, guild_id):
    """Gets the voice player on the given guild. None otherwise."""
    return data.get(bot, 'core', 'voice_player', guild_id=guild_id, volatile=True)


def set_player(bot, guild_id, player):
    """Sets the voice player of the given guild."""
    data.add(bot, 'core', 'voice_player', player, guild_id=guild_id, volatile=True)


async def join_and_ready(bot, voice_channel, is_mod=False, reconnect=False):
    """Joins the voice channel and stops any audio playing.

    Returns the voice_client object from voice_channel.connect()
    """
    guild = voice_channel.guild
    muted = voice_channel.id in data.get(
        bot, 'core', 'muted_channels', guild_id=guild.id, default=[])
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
            try:
                await leave_and_stop(bot, guild)
            except:
                pass
            raise CBException("Failed to join the voice channel.", e=e)
        if voice_client.is_playing():
            voice_client.stop()
    else:
        if voice_client.is_playing():
            voice_client.stop()
        if voice_client.channel != voice_channel:
            try:
                await voice_client.move_to(voice_channel)
            except Exception as e:
                try:
                    await leave_and_stop(bot, guild)
                except:
                    pass
                raise CBException("Failed to move to the voice channel.", e=e)

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
        #('weeks', int(total_seconds / 604800)),  # Weeks are more confusing than days
        ('days', int(total_seconds / 86400)),
        ('hours', int((total_seconds % 86400) / 3600)),
        ('minutes', int((total_seconds % 3600) / 60)),
        ('seconds', int(total_seconds % 60))
    ]
    result = []

    if text:
        for scale, value in values:
            if value > 0:
                if not full and len(result) == 1 and values[0][1] >= 7:
                    break  # Lower resolution if there are several days already
                result.append('{} {}{}'.format(
                    value, scale[:-1], '' if value == 1 else 's'))
                if not full and len(result) > 1:
                    break
            elif not full and len(result) == 1:
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
        urls = [attachment.url for attachment in message.attachments]
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
            bot, 'core', None, guild_id=guild.id, default={})
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
        logger.info("Notification:\n{}".format(message))
    else:
        if user_id:
            blacklist = data.get(bot, 'core', 'blacklist', default=[])
            if user_id in blacklist:
                await asyncio.sleep(0.5)
                return
        for owner in bot.owners:
            member = data.get_member(bot, owner)
            if len(message) > 1998:
                await send_text_as_file(member, message, 'notification')
            else:
                await member.send(message)


# TODO: Add specific table dumping
def db_backup(bot, safe=True):
    """Use the Docker setup to backup the database."""
    if not bot.docker_mode:
        return
    try:
        logger.debug("Attemping to connect to the database container...")
        if bot.dump_exclusions:
            exclusions = '-T "' + '" -T "'.join(bot.dump_exclusions) + '"'
        else:
            exclusions = ''
        command = (
            'pg_dump -U postgres -F t {} postgres > '
            '/external/data/db_dump.tar'.format(exclusions))
        host = 'db'
        port = 2345
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.connect((host, port))
        s.send(bytes(command, 'ascii'))
        s.close()
        time.sleep(1)
        logger.debug("Told database container to backup")
    except Exception as e:
        logger.warn("Failed to communicate with the database container: %s", e)
        if safe:
            return
        raise CBException("Failed to communicate with the database container.", e=e)


def make_backup(bot):
    """Makes a backup of the data directory."""
    logger.info("Making backup...")
    db_backup(bot)
    backup_indices = '{0}/temp/backup{{}}.zip'.format(bot.path)
    if os.path.isfile(backup_indices.format(5)):
        os.remove(backup_indices.format(5))
    for it in range(1, 5):
        backup_file_from = backup_indices.format(5-it)
        backup_file_to = backup_indices.format(6-it)
        if os.path.isfile(backup_file_from):
            os.rename(backup_file_from, backup_file_to)
    shutil.make_archive(backup_indices.format(1)[:-4], 'zip', '{}/data'.format(bot.path))
    logger.info("Finished making backup.")


def restore_backup(bot, backup_file):
    """Restores a backup file given the backup filename."""
    logger.info("Restoring from a backup file...")
    try:
        core.bot_data = {'global_users': {}, 'global_plugins': {}}
        core.volatile_data = {'global_users': {}, 'global_plugins': {}}
        shutil.unpack_archive(backup_file, '{}/data'.format(bot.path))
        data.check_all(bot)
        data.load_data(bot)
    except Exception as e:
        raise CBException("Failed to extract backup.", e=e)
    logger.info("Finished data restore.")


def get_timezone_offset(bot, guild_id=None, utc_dt=None, utc_seconds=None, as_string=False):
    if guild_id is None:
        offset = 0
    else:
        offset = data.get(bot, 'core', 'timezone', guild_id=guild_id)
    if offset is None:
        guild = bot.get_guild(guild_id)
        offset = voice_regions.get(str(guild.region), 0)
        if 'us-' in str(guild.region):  # Apply DST offset
            if utc_dt and utc_dt.dst():
                in_dst = utc_dt.timetuple().tm_isdst > 0
            else:
                in_dst = time.localtime(time.time()).tm_isdst > 0
            if in_dst:
                offset += 1
    if as_string:
        result = 'UTC{}'.format(('+' + str(offset)) if offset >= 0 else offset)
    else:
        result = offset
    if utc_dt:  # Convert UTC datetime object to "local" time
        return (result, utc_dt + datetime.timedelta(hours=offset))
    if utc_seconds is not None:  # Convert UTC seconds to offset
        return (result, utc_seconds + (3600 * offset))
    else:
        return result


def get_schedule_entries(
        bot, plugin_name, search=None, destination=None, custom_match=None, custom_args=[]):
    """Gets the entries given the search or match arguments."""
    if custom_match:
        where_arg = custom_match
        input_args = custom_args
    else:
        where_arg = 'plugin = %s'
        input_args = [plugin_name]
        if search is not None:
            where_arg += ' AND search = %s'
            input_args.append(search)
        if destination is not None:
            where_arg += ' AND destination = %s'
            input_args.append(destination)

    cursor = data.db_select(
        bot, from_arg='schedule', where_arg=where_arg,
        additional='ORDER BY time ASC', input_args=input_args, safe=False)
    entries = cursor.fetchall()
    converted = []
    for entry in entries:
        if entry[3]:
            payload = json.loads(entry[3])
        else:
            payload = entry[3]
        converted.append(entry[:3] + (payload,) + entry[4:])
    return converted


def remove_schedule_entries(
        bot, plugin_name, search=None, destination=None, custom_match=None, custom_args=[]):
    """Removes the entries given the search or match arguments."""
    if custom_match:
        where_arg = custom_match
        input_args = custom_args
    else:
        where_arg = 'plugin = %s'
        input_args = [plugin_name]
        if search is not None:
            where_arg += ' AND search = %s'
            input_args.append(search)
        if destination is not None:
            where_arg += ' AND destination = %s'
            input_args.append(destination)
    data.db_delete(bot, 'schedule', where_arg=where_arg, input_args=input_args)


def update_schedule_entries(
        bot, plugin_name, search=None, destination=None, function=None,
        payload=None, new_search=None, time=None, new_destination=None,
        info=None, custom_match=None, custom_args=[]):
    """Updates the schedule entry with the given fields.

    If any field is left as None, it will not be changed.
    If custom_match is given, it must be a proper WHERE SQL clause. Otherwise
        it will look for a direct match with search.

    Returns the number of entries modified.
    """
    if custom_match:
        where_arg = custom_match
        input_args = custom_args
    else:
        where_arg = 'plugin = %s'
        input_args = [plugin_name]
        if search is not None:
            where_arg += ' AND search = %s'
            input_args.append(search)
        if destination is not None:
            where_arg += ' AND destination = %s'
            input_args.append(destination)

    set_args = []
    set_input_args = []
    if function:
        set_args.append('function=%s')
        set_input_args.append(function.__name__)
    if payload:
        set_args.append('payload=%s')
        set_input_args.append(json.dumps(payload))
    if time:
        set_args.append('time=%s')
        set_input_args.append(int(time))
    if new_search:
        set_args.append('search=%s')
        set_input_args.append(new_search)
    if new_destination:
        set_args.append('destination=%s')
        set_input_args.append(new_destination)
    if info:
        set_args.append('info=%s')
        set_input_args.append(info)
    set_arg = ', '.join(set_args)
    input_args = set_input_args + input_args
    data.db_update(bot, 'schedule', set_arg=set_arg, where_arg=where_arg, input_args=input_args)
    asyncio.ensure_future(_start_scheduler(bot))


def schedule(
        bot, plugin_name, time, function, payload=None,
        search=None, destination=None, info=None):
    """Adds the entry to the schedule table and starts the timer.

    It should be noted that the function CANNOT be a lambda function. It must
        be a function residing in the plugin.
    The payload should be a standard dictionary.
    The search keyword argument is to assist in later deletion or modification.
    Time should be a number in seconds from the epoch.
    """
    input_args = [
        int(time),
        plugin_name,
        function.__name__,
        json.dumps(payload) if payload else None,
        search,
        destination,
        info
    ]
    data.db_insert(bot, 'schedule', input_args=input_args, safe=False)
    asyncio.ensure_future(_start_scheduler(bot))


def get_messageable(bot, destination):
    """Takes a destination in the schedule table format and returns a messageable."""
    try:
        if destination[0] == 'u':  # User
            get = bot.get_user
        elif destination[0] == 'c':  # Channel
            get = bot.get_channel
        else:
            assert False
        return get(int(destination[1:]))
    except Exception as e:
        raise CBException("Invalid destination format.", e=e)


async def _schedule_timer(bot, raw_entry, delay):
    task_comparison = bot.schedule_timer
    await asyncio.sleep(0.5)
    logger.debug("_schedule_timer sleeping for %s seconds...", delay)
    await asyncio.sleep(delay)
    if task_comparison is not bot.schedule_timer:
        logger.debug("_schedule_timer was not cancelled! Cancelling this scheduler...")
        return
    try:
        cursor = data.db_select(bot, select_arg='min(time)', from_arg='schedule')
        minimum_time = cursor.fetchone()[0]
        data.db_delete(
            bot, 'schedule', where_arg='time=%s', input_args=[minimum_time], safe=False)
    except Exception as e:
        logger.warn("_schedule_timer failed to delete schedule entry. %s", e)
        raise e
    try:
        logger.debug("_schedule_timer done sleeping for %s seconds!", delay)
        scheduled_time, plugin, function, payload, search, destination, info = raw_entry
        if payload:
            payload = json.loads(payload)
        plugin = bot.plugins[plugin]
        function = getattr(plugin, function)
        late = delay < -60
        asyncio.ensure_future(function(bot, scheduled_time, payload, search, destination, late))
    except Exception as e:
        logger.warn("Failed to execute scheduled function: %s", e)
        raise e
    asyncio.ensure_future(_start_scheduler(bot))


async def _start_scheduler(bot):
    """Starts the interal scheduler."""
    if bot.schedule_timer:  # Scheduler already running
        bot.schedule_timer.cancel()
        bot.schedule_timer = None
    cursor = data.db_select(
        bot, from_arg='schedule', additional='ORDER BY time ASC', limit=1, safe=False)
    result = cursor.fetchone()
    if result:
        delta = result[0] - time.time()
        logger.debug("_start_scheduler is starting a scheduled event.")
        bot.schedule_timer = asyncio.ensure_future(_schedule_timer(bot, result, delta))
    else:
        logger.debug("_start_scheduler could not find a pending scheduled event.")
