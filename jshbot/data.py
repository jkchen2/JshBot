import discord
import os
import io
import json
import psycopg2
import psycopg2.extras

from types import GeneratorType

from jshbot import core, utilities, logger, configurations
from jshbot.exceptions import BotException, ConfiguredBotException, ErrorTypes

CBException = ConfiguredBotException('Data')


def check_folders(bot):
    """Checks that all of the folders are present at startup."""
    directories = ['audio', 'audio_cache', 'data', 'plugins', 'temp']
    for directory in directories:
        full_path = '{0}/{1}/'.format(bot.path, directory)
        if not os.path.exists(full_path):
            logger.warn("Directory {} does not exist. Creating...".format(directory))
            os.makedirs(full_path)


def check_all(bot):
    """Refreshes the guild listing in the global data dictionary."""
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id not in bot.data:  # Mirrored with volatile data
            bot.data[guild_id] = {}
            bot.volatile_data[guild_id] = {}
        elif guild_id not in bot.volatile_data:  # Just volatile data
            bot.volatile_data[guild_id] = {}


def get_location(bot, guild_id, channel_id, user_id, volatile, create=True):
    """Gets the location given the arguments.

    If the create flag is False, no elements will be created when getting the
    location. This also returns the key used to get to the data. It will be a
    guild ID, 'global_users' or 'global_plugins'.
    """
    data = bot.volatile_data if volatile else bot.data

    # Comply with rewrite giving ints instead of strings
    if guild_id:
        guild_id = str(guild_id)
    if channel_id:
        channel_id = str(channel_id)
    if user_id:
        user_id = str(user_id)

    if guild_id:  # Look in the specific guild
        if guild_id in data:
            current = data[guild_id]
            key = guild_id
        else:  # Server not found - refresh listing
            check_all(bot)
            raise CBException("Server {} not found.".format(guild_id))
        if channel_id:
            if channel_id not in current:
                if not create:
                    return ({}, key)
                current[channel_id] = {}
            current = current[channel_id]
        if user_id:
            if user_id not in current:
                if not create:
                    return ({}, key)
                current[user_id] = {}
            current = current[user_id]

    elif user_id:  # Check for global user data
        key = 'global_users'
        current = data[key]
        if user_id not in current:
            if not create:
                return ({}, key)
            current[user_id] = {}
        current = current[user_id]

    else:  # Check for global plugin data
        key = 'global_plugins'
        current = data[key]

    return (current, key)


def get(bot, plugin_name, key, guild_id=None, channel_id=None, user_id=None,
        default=None, volatile=False, create=False, save=False):
    """Gets the data with the given key.

    The keyword arguments specify the location of the key.
    If no specified location is given, the global component is searched.
    If only the user is given, it will search the global users component.
    Otherwise it will follow the specifiers to retireve the data if it exists.
    If it does not exist, returns default.

    If the key is None, it returns all of the data for the given plugin in that
    specific location.

    If save is True, this marks the given location to be saved. Used if the
    internal data structure you are trying to access needs to be modified in
    a way that these given functions cannot.
    """
    current, location_key = get_location(
        bot, guild_id, channel_id, user_id, volatile, create=create)

    if save and not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)

    current_plugin = current.get(plugin_name, None)
    if create and current_plugin is None:
        current[plugin_name] = {}
        current_plugin = current[plugin_name]
        if not volatile and location_key not in bot.data_changed:
            bot.data_changed.append(location_key)

    if key:
        if create and key not in current_plugin:
            current_plugin[key] = default
            if not volatile and location_key not in bot.data_changed:
                bot.data_changed.append(location_key)
        if current_plugin is None:
            return default
        else:
            return current_plugin.get(key, default)
    else:
        return current.get(plugin_name, default)


def add(bot, plugin_name, key, value, guild_id=None, channel_id=None,
        user_id=None, volatile=False):
    """Adds the given information to the specified location.

    Location is specified in the same way as get(). If the value exists,
    this will overwrite it.
    """
    current, location_key = get_location(bot, guild_id, channel_id, user_id, volatile)

    if plugin_name not in current:
        current[plugin_name] = {}
    current[plugin_name][key] = value

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)


def set_save_flag(bot, plugin_name, guild_id=None, channel_id=None, user_id=None):
    """Flags the given location for unsaved changes."""
    _, location_key = get_location(bot, guild_id, channel_id, user_id, False)
    if location_key not in bot.data_changed:
        bot.data_changed.append(location_key)


def remove(bot, plugin_name, key, guild_id=None, channel_id=None,
           user_id=None, default=None, safe=False, volatile=False):
    """Removes the given key from the specified location.

    If the key does not exist and the safe flag is not set, this will throw an
    exception. If the safe flag is set, it will return default. Otherwise, this
    will return the found value, and remove it from the dictionary.

    If the key is None, it removes all of the data associated with that plugin
    for the given location. Use with caution.
    """
    current, location_key = get_location(bot, guild_id, channel_id, user_id, volatile)

    if (not current or
            plugin_name not in current or
            (key and key not in current[plugin_name])):
        if safe:
            return default
        else:
            raise CBException("Key '{}' not found.".format(key))

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)

    if key:
        return current[plugin_name].pop(key)
    else:  # Remove all data associated with that plugin for the given location
        return current.pop(plugin_name)


def list_data_append(
        bot, plugin_name, key, value, guild_id=None, channel_id=None,
        user_id=None, volatile=False, duplicates=True):
    """Add data to list at location.

    Works like add, but manipulates the list at the location instead to append
    the given key. It creates the list if it doesn't exist. If the duplicates
    flag is set to false, this will not append the data if it is already found
    inside the list.
    """
    current, location_key = get_location(bot, guild_id, channel_id, user_id, volatile)
    if plugin_name not in current:
        current[plugin_name] = {}
    if key not in current[plugin_name]:  # List doesn't exist
        current[plugin_name][key] = [value]
    else:  # List already exists
        current = current[plugin_name][key]
        if not isinstance(current, list):
            raise CBException("Data is not a list.")
        elif duplicates or value not in current:
            current.append(value)
        if not volatile and location_key not in bot.data_changed:
            bot.data_changed.append(location_key)


def list_data_remove(
        bot, plugin_name, key, value=None, guild_id=None, channel_id=None,
        user_id=None, default=None, safe=False, volatile=False):
    """Remove data from list at location.

    Works like remove, but manipulates the list at the location. If the value
    is not specified, it will pop the first element.
    """
    current, location_key = get_location(bot, guild_id, channel_id, user_id, volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise CBException("Key '{}' not found.".format(key))
    current = current[plugin_name][key]
    if not isinstance(current, list):
        if safe:
            return default
        else:
            raise CBException("Data is not a list.")
    elif not current:  # Empty, can't pop
        if safe:
            return default
        else:
            raise CBException("List is empty.")

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)
    if value is None:
        return current.pop()
    else:  # Pop value
        if value not in current:
            if safe:
                return default
            else:
                raise CBException("Value '{}' not found in list.".format(value))
        else:
            current.remove(value)
            return value


def list_data_toggle(
        bot, plugin_name, key, value, guild_id=None, channel_id=None,
        user_id=None, volatile=False):
    """Toggles the value from the list at the location.

    If the value exists in the list, it will be removed (one instance).
    Otherwise, it will be added.
    Returns whether or not the value was appended to the list.
    """
    current, location_key = get_location(bot, guild_id, channel_id, user_id, volatile)
    if plugin_name not in current:
        current[plugin_name] = {}
    if key not in current[plugin_name]:  # List doesn't exist
        current[plugin_name][key] = [value]
        return True
    else:  # List already exists
        current = current[plugin_name][key]
        if not isinstance(current, list):
            raise CBException("Data is not a list.")
        appended = value not in current
        current.append(value) if appended else current.remove(value)
        return appended


def save_data(bot, force=False):
    """Saves all of the current data in the data dictionary.

    Does not save volatile_data, though. Backups data if forced.
    """
    if bot.data_changed or force:  # Only save if something changed or forced
        # Loop through keys
        directory = bot.path + '/data/'

        if force:  # Save all data
            for key, value in bot.data.items():
                with open(directory + key + '.json', 'w') as current_file:
                    try:
                        json.dump(value, current_file, indent=4)
                    except TypeError as e:
                        logger.error('Failed to save data for %s: (TypeError) %s', key, e)
            # Check to see if any guild was removed
            files = os.listdir(directory)
            for check_file in files:
                if check_file.endswith('.json') and check_file[:-5] not in bot.data:
                    logger.debug("Removing file {}".format(check_file))
                    os.remove(directory + check_file)

        else:  # Save data that has changed
            for key in bot.data_changed:
                with open(directory + key + '.json', 'w') as current_file:
                    json.dump(bot.data[key], current_file, indent=4)
                logger.debug("Saved {}".format(directory + key + '.json'))

        bot.data_changed = []

    if force:
        utilities.make_backup(bot)


def load_data(bot):
    """Loads the data from the data directory."""

    logger.debug("Loading data...")
    directory = bot.path + '/data/'
    for guild in bot.guilds:
        guild_id = str(guild.id)
        try:
            with open(directory + guild_id + '.json', 'r') as guild_file:
                bot.data[guild_id] = json.load(guild_file)
        except:
            logger.warn("Data for guild {} not found.".format(guild_id))
            bot.data[guild_id] = {}

    try:
        with open(directory + 'global_plugins.json', 'r') as plugins_file:
            bot.data['global_plugins'] = json.load(plugins_file)
    except:
        logger.warn("Global data for plugins not found.")
    try:
        with open(directory + 'global_users.json', 'r') as users_file:
            bot.data['global_users'] = json.load(users_file)
    except:
        logger.warn("Global data for users not found.")
    logger.debug("Data loaded.")


def clean_location(bot, plugins, channels, users, location):
    """Recursively cleans out the given location.

    Removes users, guilds, and plugin data that can no longer be used.
    The location must be a guild or global data dictionary.
    """

    location_items = list(location.items())
    for key, value in location_items:
        if key.isdigit():  # Channel or user
            if key not in channels and key not in users:  # Missing
                del location[key]
            else:  # Recurse
                clean_location(bot, plugins, channels, users, location[key])
                if not location[key]:  # Remove entirely
                    del location[key]
        else:  # Plugin
            if key not in plugins:  # Unreachable data
                del location[key]


def clean_data(bot):
    """Removes data that is no longer needed removed."""

    plugins = list(bot.plugins.keys())
    guilds = list(str(guild.id) for guild in bot.guilds)

    data_items = list(bot.data.items())
    for key, value in data_items:

        if key[0].isdigit():  # Server
            if key not in guilds:  # Server cannot be found, remove it
                logger.warn("Removing guild {}".format(key))
                del bot.data[key]
            else:  # Recursively clean the data
                guild = bot.get_guild(key)
                channels = [str(channel.id) for channel in guild.channels]
                users = [str(member.id) for member in guild.members]
                clean_location(bot, plugins, channels, users, bot.data[key])

        else:  # Global plugins or users
            clean_location(bot, plugins, [], [], bot.data[key])

    save_data(bot, force=True)


def add_custom_role(bot, plugin_name, role_name, role):
    """Adds the given role as a custom internal role used by the bot."""
    roles = get(bot, plugin_name, 'custom_roles', guild_id=role.guild.id, create=True, default={})
    roles[role_name] = role.id


def remove_custom_role(bot, plugin_name, role_name, guild, safe=True):
    roles = get(bot, plugin_name, 'custom_roles', guild_id=guild.id, default={})
    try:
        return roles.pop(role_name)
    except KeyError:
        if not safe:
            raise CBException("Custom role not found.")


def get_custom_role(bot, plugin_name, role_name, guild, safe=True):
    """Gets the role associated with the guild and the role name."""
    if not guild:
        if safe:
            return None
        raise CBException("Cannot check custom roles in a direct message.")
    roles = get(bot, plugin_name, 'custom_roles', guild_id=guild.id, default={})
    role_id = roles.get(role_name, None)
    role = discord.utils.get(guild.roles, id=role_id)
    if not role:
        remove_custom_role(bot, plugin_name, role_name, guild)
        if safe:
            return None
        else:
            raise CBException("Custom role '{}' not found.".format(role_name))
    return role


def has_custom_role(
        bot, plugin_name, role_name, guild=None, user_id=None, member=None, strict=False):
    """Checks if the given user has the given role."""
    if member:
        guild = getattr(member, 'guild', None)
    elif guild:
        member = guild.get_member(user_id)
    role = get_custom_role(bot, plugin_name, role_name, guild)  # Checks for no guild

    if member is None:
        raise CBException('Member not found.')
    member_roles = getattr(member, 'roles', [])
    return role in member_roles or not strict and is_mod(bot, member=member)


def is_mod(bot, guild=None, user_id=None, strict=False, member=None):
    """Returns true if the given user is a moderator of the given guild.

    The guild owner and bot owners count as moderators. If strict is True,
    this will only look in the moderators list and nothing above that.

    Member is given as a discord.Member or discord.User. If given, will
    bypass guild and user_id.
    """
    if member:
        user_id = member.id
        guild = getattr(member, 'guild', None)

    if guild is None:  # Private channel
        return is_owner(bot, user_id)
    if member is None:
        member = guild.get_member(user_id)
    if member is None:
        raise CBException('Member not found.')
    modrole_id = get(bot, 'core', 'modrole', guild_id=guild.id)
    mod_check = bool(
        member.guild_permissions.administrator or modrole_id in [it.id for it in member.roles])
    if strict:  # Only look for the user in the moderators list
        return mod_check
    else:  # Check higher privileges too
        return mod_check or is_admin(bot, guild, user_id)


def is_admin(bot, guild, user_id, strict=False):
    """Checks that the user is an admin or higher."""
    if strict:
        return guild and user_id == guild.owner.id
    else:
        return (guild and user_id == guild.owner.id) or is_owner(bot, user_id)


def is_owner(bot, user_id):
    """Checks that the user is one of the bot owners."""
    return user_id in bot.owners


def is_blocked(bot, guild, user_id, strict=False):
    """Checks that the user is blocked in the given guild."""
    if guild:
        blocked_list = get(bot, 'core', 'blocked', guild_id=guild.id, default=[])
    else:
        blocked_list = []
    if strict:
        return user_id in blocked_list
    else:
        return user_id in blocked_list and not is_mod(bot, guild, user_id)


def _get_attribute(result, attribute, safe):
    """Helper function that pulls the attribute out of the result (if given)."""
    if attribute:
        if hasattr(result, attribute):
            return getattr(result, attribute)
        elif safe:
            return None
        else:
            raise CBException("Invalid attribute, '{}'.".format(attribute))
    else:
        return result


def get_member(bot, identity, guild=None, attribute=None, safe=False, strict=False):
    """Gets a member given the identity.

    Keyword arguments:
    guild -- if specified, will look here for identity first.
    attribute -- gets the member's attribute instead of the member itself.
    safe -- returns None if not found instead of raising an exception.
    strict -- will look only in the specified guild.
    """
    if strict and guild is None:
        raise CBException("No guild specified for strict member search.")

    if isinstance(identity, int):
        used_id = True
    identity = str(identity)
    if identity.startswith('<@') and identity.endswith('>'):
        identity = identity.strip('<@!>')
        used_id = True
    else:
        used_id = False

    # Check for name + discriminator first if we're not using an ID
    split = identity.split('#')
    if not used_id and len(split) >= 2 and len(split[-1]) == 4 and split[-1].isnumeric():
        guilds = [guild] if guild else bot.guilds
        for it in guilds:
            result = it.get_member_named(identity)
            if result:
                return result

    tests = []
    try:  # Double check used_id in case we're given "<@123foo456>"
        tests.append({'id': int(identity)})
    except:
        used_id = False
    tests.extend([{'name': identity}, {'nick': identity}])
    for test in tests:
        members = guild.members if guild else bot.get_all_members()
        result = discord.utils.get(members, **test)
        if result:  # Check for duplicates
            if used_id:
                break
            elif isinstance(members, GeneratorType):
                duplicate = result
                while duplicate:
                    duplicate = discord.utils.get(members, **test)
                    if duplicate and duplicate != result:
                        raise CBException("Duplicate user found. Use a mention.")
            elif list(members).count(result) > 1:
                raise CBException("Duplicate user found. Use a mention.")
            break

    if result:
        return _get_attribute(result, attribute, safe)
    elif not strict and guild:  # Search again using all members
        return get_member(
            bot, identity, guild=None, attribute=attribute, safe=safe, strict=False)
    elif safe:
        return None
    else:
        raise CBException("User '{}' not found.".format(identity), identity)


def get_channel(
        bot, identity, guild=None, attribute=None, safe=False, strict=False, constraint=None):
    """Like get_member(), but gets the channel instead.

    If a constraint is given, this will filter the channel by the constraint using isinstance.
    """
    if strict and guild is None:
        raise CBException("No guild specified for strict channel search.")

    # Convert
    used_id = False
    if isinstance(identity, int):
        used_id = True
    identity_string = str(identity)
    if identity_string.startswith('<#') and identity_string.endswith('>'):
        identity = identity_string.strip('<#>')
        used_id = True

    tests = []
    try:  # Double check used_id in case we're given "<#123foo456>"
        tests.append({'id': int(identity)})
    except:
        used_id = False
    tests.append({'name': identity})
    for test in tests:
        channels = guild.channels if guild else bot.get_all_channels()
        result = discord.utils.get(channels, **test)
        if constraint and not isinstance(result, constraint):
            continue
        elif result:  # Check for duplicates
            if used_id:
                break
            elif isinstance(channels, GeneratorType):
                duplicate = result
                while duplicate:
                    duplicate = discord.utils.get(channels, **test)
                    if not used_id and duplicate and duplicate != result:
                        raise CBException("Duplicate channel found; use a mention.")
            elif not used_id and list(it.name for it in channels).count(result.name) > 1:
                raise CBException("Duplicate channel found; use a mention.")
            break

    if result:
        return _get_attribute(result, attribute, safe)
    elif safe:
        return None
    else:
        raise CBException("Channel '{}' not found.".format(identity), identity)


# TODO: Add lowercase role list checking
def get_role(bot, identity, guild, attribute=None, safe=False):
    """Gets a role given the identity and guild."""
    used_id, used_name = False, False
    if isinstance(identity, int):
        used_id = True
    identity_string = str(identity)
    if identity_string.startswith('<@&') and identity_string.endswith('>'):
        identity = identity_string.strip('<@&>')
        used_id = True
    else:
        used_name = True

    tests = []
    try:  # Double check id in case we're given "<@&123foo456>"
        tests.append({'id': int(identity)})
    except:
        used_id = False
        used_name = True
    tests.append({'name': identity})
    # Attempted mention, but the role is unmentionable
    if identity_string.startswith('@') and len(identity_string) > 1:
        tests.append({'name': identity_string[1:]})

    for test in tests:
        result = discord.utils.get(guild.roles, **test)
        if result:  # Check for duplicates
            if used_id:
                break
            elif list(it.name for it in guild.roles).count(result.name) > 1:
                raise CBException("Duplicate role found; use a mention.")
            break

    if result:
        return _get_attribute(result, attribute, safe)
    elif used_name:  # Search through lowercased role names
        clean_roles = {}
        for it in guild.roles:
            clean_name = it.name.lower()
            if clean_name in clean_roles:
                clean_roles[clean_name][1] = True  # Duplicate found
            else:
                clean_roles[clean_name] = [it, False]
        result = clean_roles.get(identity_string.lower())
        if result:
            if result[1]:
                raise CBException("Duplicate role found; use a mention.")
            else:
                return _get_attribute(result[0], attribute, safe)

    if safe:
        return None
    else:
        raise CBException("Role '{}' not found.".format(identity), identity)


def get_from_cache(bot, name, url=None):
    """Gets the filename from the audio_cache. Returns None otherwise.

    If url is specified, it will clean it up and look for that instead. This
    also sets the found file's access time.
    """
    if url:
        name = utilities.get_cleaned_filename(url)
    file_path = '{0}/audio_cache/{1}'.format(bot.path, name)
    if os.path.isfile(file_path):
        os.utime(file_path, None)
        return file_path
    else:
        return None


async def add_to_cache(bot, url, name=None, file_location=None):
    """Downloads the URL and saves to the audio cache folder.

    If the cache folder has surpassed the cache size, this will continually
    remove the least used file (by date) until there is enough space. If the
    downloaded file is more than half the size of the total cache, it will not
    be stored. Returns the final location of the downloaded file.

    If name is specified, it will be stored under that name instead of the url.
    If file_location is specified, it will move that file instead of
    downloading the URL.
    """
    if file_location:
        cleaned_name = utilities.get_cleaned_filename(file_location)
    else:
        file_location, cleaned_name = await utilities.download_url(bot, url, include_name=True)
    if name:
        cleaned_name = utilities.get_cleaned_filename(name)
    try:
        download_stat = os.stat(file_location)
    except FileNotFoundError:
        raise CBException("The audio could not be saved. Please try again later.")
    cache_limit = configurations.get(bot, 'core', 'cache_size_limit') * 1000 * 1000
    store = cache_limit > 0 and download_stat.st_size < cache_limit / 2

    if store:
        cached_location = '{0}/audio_cache/{1}'.format(bot.path, cleaned_name)
    else:
        cached_location = '{}/temp/tempsound'.format(bot.path)
    try:
        os.remove(cached_location)
    except:  # Doesn't matter if file doesn't exist
        pass
    os.rename(file_location, cached_location)

    if store:
        cache_entries = []
        total_size = 0
        for entry in os.scandir('{}/audio_cache'.format(bot.path)):
            stat = entry.stat()
            cache_entries.append((stat.st_atime, stat.st_size, entry.path))
            total_size += stat.st_size
        cache_entries.sort(reverse=True)

        while total_size > cache_limit:
            _, size, path = cache_entries.pop()
            os.remove(path)
            total_size -= size

    return cached_location


async def add_to_cache_ydl(bot, downloader, url):
    """Downloads the given URL using YoutubeDL and stores it in the cache.

    The downloader must be provided as a YoutubeDL downloader object.
    """
    file_location = '{}/temp/tempsound_{}'.format(bot.path, utilities.get_cleaned_filename(url))
    downloader.params.update({'outtmpl': file_location})
    await utilities.future(downloader.download, [url])
    return await add_to_cache(bot, None, name=url, file_location=file_location)


def add_guild(bot, guild):
    """Adds the guild to the data dictionary."""
    guild_id = str(guild.id)
    if guild_id not in bot.data:
        bot.data[guild_id] = {}
        bot.volatile_data[guild_id] = {}
        bot.data_changed.append(guild_id)


def db_connect(bot):
    """Attempts to connect to the database."""
    try:
        connection_parameters = bot.configurations['core']['database_credentials']
        if not connection_parameters:  # Default for docker-compose setup
            connection_parameters = "dbname='postgres' user='postgres' host='db'"
        bot.db_connection = psycopg2.connect(connection_parameters)
    except Exception as e:
        raise CBException("Failed to connect to the database.", e=e, error_type=ErrorTypes.STARTUP)


def db_copy(
        bot, table='', table_suffix='', query='', input_args=[],
        include_headers=True, safe=False, cursor_kwargs={}, pass_error=False):
    string_file = io.StringIO()
    if query:
        sql = cursor.mogrify("COPY ({}) TO STDOUT WITH CSV".format(query), input_args)
    else:
        if table_suffix:
            table_suffix = '_{}'.format(table_suffix)
        sql = "COPY {} TO STDOUT WITH CSV".format(table + table_suffix)
    if include_headers:
        sql += " HEADER"

    try:
        cursor = bot.db_connection.cursor(**cursor_kwargs)
        cursor.copy_expert(sql, string_file)
    except Exception as e:
        bot.extra = e
        bot.db_connection.rollback()
        if pass_error:
            raise e
        elif safe:
            return
        raise CBException("Failed to execute copy.", e=e)
    bot.db_connection.commit()
    string_file.seek(0)
    return string_file


def db_execute(
        bot, query, input_args=[], safe=False, cursor_kwargs={}, pass_error=False, mark=None):
    """Executes the given query."""
    try:
        cursor = bot.db_connection.cursor(**cursor_kwargs)
        cursor.execute(query, input_args)
    except Exception as e:
        bot.db_connection.rollback()
        if pass_error:
            raise e
        elif safe:
            return
        raise CBException("Failed to execute query.", e=e)
    bot.db_connection.commit()
    if mark and mark not in bot.tables_changed:
        bot.tables_changed.append(mark)
    return cursor


def db_select(
        bot, select_arg=['*'], from_arg=[], where_arg='', additional='', limit=None,
        input_args=[], table_suffix='', safe=True, pass_error=False, cursor_kwargs={},
        use_tuple_cursor=True):
    """Makes a selection query. Returns a cursor.

    Keyword arguments:
    select_arg -- List of columns to select. (unsanitized)
    from_arg -- List of tables to select from. (unsanitized)
    where_arg -- Conditionals for the selection. (unsanitized)
    additional -- Additional parameters following the WHERE clause (unsanitized)
    limit -- Limits the number of results
    input_args -- Arguments passed into the query via old pyformat. (sanitized)
    table_suffix -- Suffix appended to each entry in from_arg. (unsanitized)
    safe -- Will not throw an exception.
    use_tuple_cursor -- Changes the cursor factory to the namedtuple variant
    """
    if use_tuple_cursor:
        cursor_kwargs.update({'cursor_factory': psycopg2.extras.NamedTupleCursor})
    if not isinstance(select_arg, (list, tuple)):
        select_arg = [select_arg]
    query = "SELECT {} ".format(', '.join(select_arg))
    if not from_arg:
        if safe:
            return
        raise CBException("No table specified for selection.")
    elif not isinstance(from_arg, (list, tuple)):
        from_arg = [from_arg]
    if table_suffix:
        table_suffix = '_{}'.format(table_suffix)
    query += "FROM {}".format(', '.join((it + table_suffix) for it in from_arg))
    if where_arg:
        query += ' WHERE {}'.format(where_arg)
    if additional:
        query += ' {}'.format(additional)
    if limit:
        query += ' LIMIT {}'.format(limit)

    try:
        return db_execute(
            bot, query, input_args=input_args, cursor_kwargs=cursor_kwargs,
            pass_error=pass_error, safe=safe)
    except Exception as e:
        if safe:
            return
        elif pass_error or isinstance(e, BotException):
            raise e
        else:
            raise CBException("Database selection failed.", e=e)


def db_insert(
        bot, table, specifiers=[], input_args=[], table_suffix='',
        safe=True, create=False, mark=True):
    """Inserts the input arguments into the given table."""
    if not isinstance(specifiers, (list, tuple)):
        specifiers = [specifiers]
    if not isinstance(input_args, (list, tuple)):
        input_args = [input_args]
    full_table = table + ('_{}'.format(table_suffix) if table_suffix else '')
    query = "INSERT INTO {} ".format(full_table)
    if specifiers:
        query += "({}) ".format(', '.join(specifiers))
    query += "VALUES ({})".format(', '.join('%s' for it in range(len(input_args))))
    try:
        db_execute(bot, query, input_args=input_args, pass_error=True)
    except psycopg2.ProgrammingError as e:
        stripped = str(e).split('\n')[0]
        if stripped.startswith('relation') and stripped.endswith('does not exist'):
            if create:
                db_create_table(
                    bot, table, table_suffix=table_suffix, template=create, mark=mark)
                db_insert(
                    bot, table, specifiers=specifiers, input_args=input_args,
                    table_suffix=table_suffix, safe=safe, create=False, mark=mark)
                return
        if safe:
            return
        raise CBException("Invalid insert syntax.", e=e)
    except BotException as e:
        raise e
    except Exception as e:
        raise CBException("Failed to insert into database.", e=e)


def db_update(bot, table, table_suffix='', set_arg='', where_arg='', input_args=[], mark=True):
    """Updates the given table, specified by SET and WHERE if given."""
    full_table = table + ('_{}'.format(table_suffix) if table_suffix else '')
    query = "UPDATE {} SET {}".format(full_table, set_arg)
    if where_arg:
        query += " WHERE {}".format(where_arg)
    db_execute(bot, query, input_args=input_args, mark=full_table if mark else None)


def db_delete(bot, table, table_suffix='', where_arg='', input_args=[], safe=True, mark=True):
    """Deletes entries from the given table. Returns the number of entries deleted."""
    full_table = table + ('_{}'.format(table_suffix) if table_suffix else '')
    query = "DELETE FROM {} WHERE {}".format(full_table, where_arg)
    try:
        cursor = db_execute(
            bot, query, input_args=input_args, pass_error=True,
            mark=full_table if mark else None)
        return cursor.rowcount
    except Exception as e:
        if safe:
            return
        elif isinstance(e, BotException):
            raise e
        else:
            raise CBException("Invalid delete syntax", e=e)


def db_create_table(
        bot, table, table_suffix='', template=None, specification='', mark=True):
    """Creates the table with the given template."""
    if specification:
        table_specification = specification
    else:
        table_specification = bot.db_templates.get(template)
        if not table_specification:
            raise CBException("No template specified for table creation.")
    full_table = table + ('_{}'.format(table_suffix) if table_suffix else '')
    query = "CREATE TABLE IF NOT EXISTS {} ({})".format(full_table, table_specification)
    db_execute(bot, query, mark=full_table if mark else None)


def db_drop_table(bot, table, table_suffix='', safe=False):
    """Drops the specified table."""
    full_table = table + ('_{}'.format(table_suffix) if table_suffix else '')
    if_exists = 'IF EXISTS ' if safe else ''
    query = "DROP TABLE {}{}".format(if_exists, full_table)
    try:
        db_execute(bot, query, pass_error=True)
    except Exception as e:
        if not safe:
            raise e


def db_exists(bot, entry='', table='', table_suffix='', check_type=False):
    """Checks the existence of the given entry (table, index, etc.)"""
    if check_type:
        query = "SELECT True FROM pg_type WHERE typname=%s"
    else:
        query = "SELECT to_regclass(%s)"
    if not any((entry, table, table_suffix)):
        raise CBException("No DB check name provided.")
    if table:
        entry = table + ('_{}'.format(table_suffix) if table_suffix else '')
    result = db_execute(bot, query, input_args=[entry]).fetchone()
    if isinstance(result, tuple):
        result = result[0]
    return result


def db_dump_exclude(bot, table_name):
    """Adds the given table name to the dump exclusion list."""
    if table_name not in bot.dump_exclusions:
        bot.dump_exclusions.append(table_name)


# TODO: Potentially revise templates so that they are per-plugin
def db_add_template(bot, name, specification):
    bot.db_templates[name] = specification
