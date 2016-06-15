import discord
import logging
import os
import json

from jshbot import utilities
from jshbot.exceptions import BotException

EXCEPTION = 'Data'


def check_folders(bot):
    """Checks that all of the folders are present at startup."""
    directories = ['audio', 'audio_cache', 'data', 'plugins', 'temp']
    for directory in directories:
        full_path = '{0}/{1}/'.format(bot.path, directory)
        if not os.path.exists(full_path):
            logging.warn("Directory {} is empty.".format(directory))
            os.makedirs(full_path)


def check_all(bot):
    """Refreshes the server listing in the global data dictionary."""
    for server in bot.servers:
        if server.id not in bot.data:  # Mirrored with volatile data
            bot.data[server.id] = {}
            bot.volatile_data[server.id] = {}
        elif server.id not in bot.volatile_data:  # Just volatile data
            bot.volatile_data[server.id] = {}


def get_location(bot, server_id, channel_id, user_id, volatile, create=True):
    """Gets the location given the arguments.

    If the create flag is False, no elements will be created when getting the
    location. This also returns the key used to get to the data. It will be a
    server ID, 'global_users' or 'global_plugins'.
    """
    data = bot.volatile_data if volatile else bot.data

    if server_id:  # Look in the specific server
        if server_id in data:
            current = data[server_id]
            key = server_id
        else:  # Server not found - refresh listing
            check_all(bot)
            raise BotException(
                EXCEPTION, "Server {} not found.".format(server_id))
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


def get(bot, plugin_name, key, server_id=None, channel_id=None, user_id=None,
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
        bot, server_id, channel_id, user_id, volatile, create=create)

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


def add(bot, plugin_name, key, value, server_id=None, channel_id=None,
        user_id=None, volatile=False):
    """Adds the given information to the specified location.

    Location is specified in the same way as get(). If the value exists,
    this will overwrite it.
    """
    current, location_key = get_location(
        bot, server_id, channel_id, user_id, volatile)

    if plugin_name not in current:
        current[plugin_name] = {}
    current[plugin_name][key] = value

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)


def remove(bot, plugin_name, key, server_id=None, channel_id=None,
           user_id=None, default=None, safe=False, volatile=False):
    """Removes the given key from the specified location.

    If the key does not exist and the safe flag is not set, this will throw an
    exception. If the safe flag is set, it will return default. Otherwise, this
    will return the found value, and remove it from the dictionary.

    If the key is None, it removes all of the data associated with that plugin
    for the given location. Use with caution.
    """
    current, location_key = get_location(
        bot, server_id, channel_id, user_id, volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise BotException(EXCEPTION, "Key '{}' not found.".format(key))

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)

    elif key:
        return current[plugin_name].pop(key)
    else:  # Remove all data associated with that plugin for the given location
        return current.pop(plugin_name)


def list_data_append(
        bot, plugin_name, key, value, server_id=None, channel_id=None,
        user_id=None, volatile=False, duplicates=True):
    """Add data to list at location.

    Works like add, but manipulates the list at the location instead to append
    the given key. It creates the list if it doesn't exist. If the duplicates
    flag is set to false, this will not append the data if it is already found
    inside the list.
    """
    current, location_key = get_location(
        bot, server_id, channel_id, user_id, volatile)
    if plugin_name not in current:
        current[plugin_name] = {}
    if key not in current[plugin_name]:  # List doesn't exist
        current[plugin_name][key] = [value]
    else:  # List already exists
        current = current[plugin_name][key]
        if type(current) is not list:
            raise BotException(EXCEPTION, "Data is not a list.")
        elif duplicates or value not in current:
            current.append(value)
        if not volatile and location_key not in bot.data_changed:
            bot.data_changed.append(location_key)


def list_data_remove(
        bot, plugin_name, key, value=None, server_id=None, channel_id=None,
        user_id=None, default=None, safe=False, volatile=False):
    """Remove data from list at location.

    Works like remove, but manipulates the list at the location. If the value
    is not specified, it will pop the first element.
    """
    current, location_key = get_location(
        bot, server_id, channel_id, user_id, volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise BotException(EXCEPTION, "Key '{}' not found.".format(key))
    current = current[plugin_name][key]
    if type(current) is not list:
        if safe:
            return default
        else:
            raise BotException(EXCEPTION, "Data is not a list.")
    elif not current:  # Empty, can't pop
        if safe:
            return default
        else:
            raise BotException(EXCEPTION, "List is empty.")

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)
    if value is None:
        return current.pop()
    else:  # Pop value
        if value not in current:
            if safe:
                return default
            else:
                raise BotException(
                    EXCEPTION, "Value '{}' not found in list.".format(value))
        else:
            current.remove(value)
            return value


def save_data(bot, force=False):
    """Saves all of the current data in the data dictionary.

    Does not save volatile_data, though. Backups data if forced.
    """
    if force:
        utilities.make_backup(bot)

    if bot.data_changed or force:  # Only save if something changed or forced
        # Loop through keys
        keys = []
        directory = bot.path + '/data/'

        if force:  # Save all data
            for key, value in bot.data.items():
                keys.append(key)
                with open(directory + key + '.json', 'w') as current_file:
                    json.dump(value, current_file, indent=4)
            # Check to see if any server was removed
            files = os.listdir(directory)
            for check_file in files:
                if (check_file.endswith('.json') and
                        check_file[:-5] not in keys):
                    logging.debug("Removing file {}".format(check_file))
                    os.remove(directory + check_file)

        else:  # Save data that has changed
            for key in bot.data_changed:
                with open(directory + key + '.json', 'w') as current_file:
                    json.dump(bot.data[key], current_file, indent=4)

        bot.data_changed = []


def load_data(bot):
    """Loads the data from the data directory."""

    directory = bot.path + '/data/'
    for server in bot.servers:
        try:
            with open(directory + server.id + '.json', 'r') as server_file:
                bot.data[server.id] = json.load(server_file)
        except:
            logging.warn("Data for server {} not found.".format(server.id))
            bot.data[server.id] = {}

    try:
        with open(directory + 'global_plugins.json', 'r') as plugins_file:
            bot.data['global_plugins'] = json.load(plugins_file)
    except:
        logging.warn("Global data for plugins not found.")
    try:
        with open(directory + 'global_users.json', 'r') as users_file:
            bot.data['global_users'] = json.load(users_file)
    except:
        logging.warn("Global data for users not found.")


def clean_location(bot, plugins, channels, users, location):
    """Recursively cleans out the given location.

    Removes users, servers, and plugin data that can no longer be used.
    The location must be a server or global data dictionary.
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
    servers = list(server.id for server in bot.servers)

    data_items = list(bot.data.items())
    for key, value in data_items:

        if key[0].isdigit():  # Server
            if key not in servers:  # Server cannot be found, remove it
                logging.warn("Removing server {}".format(key))
                del bot.data[key]
            else:  # Recursively clean the data
                server = bot.get_server(key)
                channels = [channel.id for channel in server.channels]
                users = [member.id for member in server.members]
                clean_location(bot, plugins, channels, users, bot.data[key])

        else:  # Global plugins or users
            clean_location(bot, plugins, [], [], bot.data[key])

    save_data(bot, force=True)


def is_mod(bot, server, user_id, strict=False):
    """Returns true if the given user is a moderator of the given server.

    The server owner and bot owners count as moderators. If strict is True,
    this will only look in the moderators list and nothing above that.
    """
    moderators = get(bot, 'base', 'moderators', server.id, default=[])
    if strict:  # Only look for the user in the moderators list
        return user_id in moderators
    else:  # Check higher privileges too
        return user_id in moderators or is_admin(bot, server, user_id)


def is_admin(bot, server, user_id, strict=False):
    """Checks that the user is an admin or higher."""
    if strict:
        return user_id == server.owner.id
    else:
        return user_id == server.owner.id or is_owner(bot, user_id)


def is_owner(bot, user_id):
    """Returns true if the given user is one of the bot owners."""
    return user_id in bot.configurations['core']['owners']


def is_blocked(bot, server, user_id, strict=False):
    """Checks that the user is blocked in the given server."""
    blocked_list = get(bot, 'base', 'blocked', server_id=server.id, default=[])
    if strict:
        return user_id in blocked_list
    else:
        return user_id in blocked_list and not is_mod(bot, server, user_id)


def get_member(
        bot, identity, server=None, attribute=None, safe=False, strict=False):
    """Gets a member given the identity.

    Keyword arguments:
    server -- if specified, will look here for identity first
    attribute -- gets the found member's attribute instead of the member istelf
    safe -- returns None if not found instead of raising an exception
    strict -- will look only in the specified server
    """
    if identity.startswith('<@') and identity.endswith('>'):
        identity = identity.strip('<@!>')
    if server:
        members = server.members
    elif not strict:
        members = bot.get_all_members()
    else:
        raise BotException(
            EXCEPTION, "No server specified for strict user search.")
    result = discord.utils.get(members, id=identity)  # No conflict
    if result is None:  # Potential conflict
        result = discord.utils.get(members, name=identity)
    if result is None:  # Potentially a lot of conflict
        result = discord.utils.get(members, nick=identity)

    if result:
        if attribute:
            if hasattr(result, attribute):
                return getattr(result, attribute)
            elif safe:
                return None
            else:
                raise BotException(
                    EXCEPTION, "Invalid attribute, '{}'.".format(attribute))
        else:
            return result
    else:
        if safe:
            return None
        else:
            raise BotException(EXCEPTION, "{} not found.".format(identity))


def get_channel(
        bot, identity, server, attribute=None, safe=False):
    """Like get_member(), but gets the channel instead. Always strict."""
    if identity.startswith('<#') and identity.endswith('>'):
        identity = identity.strip('<#>')
    channels = server.channels
    result = discord.utils.get(channels, id=identity)
    if result is None:
        result = discord.utils.get(channels, name=identity)

    if result:
        if attribute:
            if hasattr(result, attribute):
                return getattr(result, attribute)
            elif safe:
                return None
            else:
                raise BotException(
                    EXCEPTION, "Invalid attribute, '{}'.".format(attribute))
        else:
            return result
    else:
        if safe:
            return None
        else:
            raise BotException(EXCEPTION, "{} not found.".format(identity))


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
        file_location, cleaned_name = await utilities.download_url(
            bot, url, include_name=True)
    if name:
        cleaned_name = utilities.get_cleaned_filename(name)
    download_stat = os.stat(file_location)
    cache_limit = bot.configurations['core']['cache_size_limit'] * 1000 * 1000
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

        # TODO: Check complexity of list entry removal
        while total_size > cache_limit:
            entry = cache_entries.pop()
            os.remove(entry[2])
            total_size -= entry[1]

    return cached_location


def add_server(bot, server):
    """Adds the server to the data dictionary."""
    bot.data[server.id] = {}
    bot.data_changed.append(server.id)
