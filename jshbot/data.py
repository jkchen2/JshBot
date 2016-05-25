import discord
import asyncio
import logging
import os
import json

from jshbot.exceptions import ErrorTypes, BotException

EXCEPTION = 'Data'

def check_all(bot):
    '''
    Refreshes the server listing in the global data dictionary.
    '''
    for server in bot.servers:
        if server.id not in bot.data: # Mirrored with volatile data
            bot.data[server.id] = {}
            bot.volatile_data[server.id] = {}
        elif server.id not in bot.volatile_data: # Just volatile data
            bot.volatile_data[server.id] = {}

def get_location(bot, server_id, channel_id, user_id, volatile, create=True):
    '''
    Gets the location given the server_id, channel_id, and user_id. If the
    create flag is False, no elements will be created when getting the location.
    This also returns the key used to get to the data. It will be a server ID,
    'global_users' or 'global_plugins'.
    '''

    data = bot.volatile_data if volatile else bot.data

    if server_id: # Look in the specific server
        if server_id in data:
            current = data[server_id]
            key = server_id
        else: # Server not found - refresh listing
            check_all(bot)
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Server {} not found.".format(server_id))
        if channel_id:
            if channel_id not in current:
                if not create:
                    return {}
                current[channel_id] = {}
            current = current[channel_id]
        if user_id:
            if user_id not in current:
                if not create:
                    return {}
                current[user_id] = {}
            current = current[user_id]

    elif user_id: # Check for global user data
        key = 'global_users'
        if user_id not in data[key]:
            if not create:
                return {}
            data[key][user_id] = {}
        current = data[key][user_id]

    else: # Check for global plugin data
        key = 'global_plugins'
        current = data[key]

    return (current, key)

def get(bot, plugin_name, key, server_id=None, channel_id=None,
        user_id=None, default=None, volatile=False, create=False):
    '''
    Gets the data with the given key from the given plugin and specified
    location. If no specified location is given, the global component is
    searched. If only the user is given, it will search the global users
    component. Otherwise it will follow the specifiers to retireve the data if
    it exists. If it does not exist, returns default.

    If the key is None, it returns all of the data for the given plugin in that
    specific location.
    '''

    current, location_key = get_location(bot, server_id, channel_id, user_id,
            volatile, create=create)

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
    '''
    Adds the given information to the specified location. Location is specified
    in the same way as get(). If the value exists, this will overwrite it.
    '''

    current, location_key = get_location(bot, server_id, channel_id, user_id,
            volatile)

    if plugin_name not in current:
        current[plugin_name] = {}
    current[plugin_name][key] = value

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)

def remove(bot, plugin_name, key, server_id=None, channel_id=None,
        user_id=None, default=None, safe=False, volatile=False):
    '''
    Removes the given key from the specified location. If the key does not
    exist and the safe flag is not set, this will throw an exception. If the
    safe flag is set, it will return default. Otherwise, this will return the
    found value, and remove it from the dictionary.

    If the key is None, it removes all of the data associated with that plugin
    for the given location. Use with caution.
    '''

    current, location_key = get_location(bot, server_id, channel_id, user_id,
            volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Key '{}' not found.".format(key))

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)

    elif key:
        return current[plugin_name].pop(key)
    else: # Remove all data associated with that plugin for the given location
        return current.pop(plugin_name)

def list_data_append(bot, plugin_name, key, value, server_id=None,
        channel_id=None, user_id=None, volatile=False, duplicates=True):
    '''
    Works like add, but manipulates the list at the location instead to append
    the given key. It creates the list if it doesn't exist. If the duplicates
    flag is set to false, this will not append the data if it is already found
    inside the list.
    '''

    current, location_key = get_location(bot, server_id, channel_id, user_id,
            volatile)
    if plugin_name not in current:
        current[plugin_name] = {}
    if key not in current[plugin_name]: # List doesn't exist
        current[plugin_name][key] = [value]
    else: # List already exists
        current = current[plugin_name][key]
        if type(current) is not list:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Data is not a list.")
        elif duplicates or value not in current:
            current.append(value)
        if not volatile and location_key not in bot.data_changed:
            bot.data_changed.append(location_key)

def list_data_remove(bot, plugin_name, key, value=None, server_id=None,
        channel_id=None, user_id=None, default=None, safe=False,
        volatile=False):
    '''
    Works like remove, but manipulates the list at the location. If the value
    is not specified, it will pop the first element.
    '''

    current, location_key = get_location(bot, server_id, channel_id, user_id,
            volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Key '{}' not found.".format(key))
    current = current[plugin_name][key]
    if type(current) is not list:
        if safe:
            return default
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Data is not a list.")
    elif not current: # Empty, can't pop
        if safe:
            return default
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "List is empty.")

    if not volatile and location_key not in bot.data_changed:
        bot.data_changed.append(location_key)
    if value is None:
        return current.pop()
    else: # Pop value
        if value not in current:
            if safe:
                return default
            else:
                raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                        "Value '{}' not found in list.".format(value))
        else:
            current.remove(value)
            return value

def save_data(bot, force=False):
    '''
    Saves all of the current data in the data dictionary. Does not save
    volatile_data, though.
    '''

    # TODO: Add backup before save

    if bot.data_changed or force: # Only save if something changed or forced
        # Loop through keys
        keys = []
        directory = bot.path + '/data/'

        if force: # Save all data
            for key, value in bot.data.items():
                keys.append(key)
                with open(directory + key + '.json', 'w') as current_file:
                    json.dump(value, current_file, indent=4)
            # Check to see if any server was removed
            files = os.listdir(directory)
            for check_file in files:
                if check_file.endswith('.json') and check_file[:-5] not in keys:
                    logging.debug("Removing file {}".format(check_file))
                    os.remove(directory + check_file)

        else: # Save data that has changed
            for key in bot.data_changed:
                with open(directory + key + '.json', 'w') as current_file:
                    json.dump(bot.data[key], current_file, indent=4)

        bot.data_changed = []

def load_data(bot):
    '''
    Loads the data from the data directory.
    '''

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
    '''
    Recursively cleans out the given location. Removes users, servers, and
    plugin data that can no longer be used. The location must be a server or
    global data dictionary.
    '''

    location_items = list(location.items())
    for key, value in location_items:
        if key.isdigit(): # Channel or user
            if key not in channels and key not in users: # Missing
                del location[key]
            else: # Recurse
                clean_location(bot, plugins, channels, users, location[key])
                if not location[key]: # Remove entirely
                    del location[key]
        else: # Plugin
            if key not in plugins: # Unreachable data
                del location[key]

def clean_data(bot):
    '''
    Removes data that is no longer needed, as either a server or plugin was
    removed.
    '''

    plugins = list(bot.plugins.keys())
    servers = list(server.id for server in bot.servers)

    data_items = list(bot.data.items())
    for key, value in data_items:

        if key[0].isdigit(): # Server
            if key not in servers: # Server cannot be found, remove it
                logging.warn("Removing server {}".format(key))
                del bot.data[key]
            else: # Recursively clean the data
                server = bot.get_server(key)
                channels = [channel.id for channel in server.channels]
                users = [member.id for member in server.members]
                clean_location(bot, plugins, channels, users, bot.data[key])

        else: # Global plugins or users
            clean_location(bot, plugins, [], [], bot.data[key])

    save_data(bot, force=True)

def is_mod(bot, server, user_id, strict=False):
    '''
    Returns true if the given user is a moderator of the given server.
    The server owner and bot owners count as moderators. If strict is True,
    this will only look in the moderators list and nothing above that.
    '''
    moderators = get(bot, 'base', 'moderators', server.id, default=[])
    if strict: # Only look for the user in the moderators list
        return user_id in moderators
    else: # Check higher privileges too
        return user_id in moderators or is_admin(bot, server, user_id)

def is_admin(bot, server, user_id, strict=False):
    '''
    Returns true if the given user is either the owner of the server or is a
    bot owner.
    '''
    if strict:
        return user_id == server.owner.id
    else:
        return user_id == server.owner.id or is_owner(bot, user_id)

def is_owner(bot, user_id):
    '''
    Returns true if the given user is one of the bot owners
    '''
    return user_id in bot.configurations['core']['owners']

def is_blocked(bot, server, user_id, strict=False):
    '''
    Returns true if the given user is blocked by the bot (no interaction
    allowed).
    '''
    blocked_list = get(bot, 'base', 'blocked', server_id=server.id, default=[])
    if strict:
        return user_id in blocked_list
    else:
        return user_id in blocked_list and not is_mod(bot, server, user_id)

def get_member(bot, identity, server=None, attribute=None, safe=False,
        strict=False):
    '''
    Gets the ID number, name, nick, mention, or member of the given identity.
    Looks through the server if it is specified, otherwise it looks through
    all members the bot can see. If the strict parameter is True, it will only
    look in the defined server.
    '''
    if identity.startswith('<@') and identity.endswith('>'):
        identity = identity.strip('<@!>')
    if server:
        members = server.members
    elif not strict:
        members = bot.get_all_members()
    else:
        raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                "No server specified for strict user search.")
    result = discord.utils.get(members, id=identity) # No conflict
    if result is None: # Potential conflict
        result = discord.utils.get(members, name=identity)
    if result is None: # Potentially a lot of conflict
        result = discord.utils.get(members, nick=identity)

    if result:
        if attribute:
            if hasattr(result, attribute):
                return getattr(result, attribute)
            elif safe:
                return None
            else:
                raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                        "Invalid attribute, '{}'.".format(attribute))
        else:
            return result
    else:
        if safe:
            return None
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "{} not found.".format(identity))

def add_server(bot, server):
    '''
    Adds the server to the data dictionary.
    '''
    bot.data[server.id] = {}
    bot.data_changed = True

