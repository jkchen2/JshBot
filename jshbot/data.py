import discord
import asyncio
import logging
import os
import json

from jshbot.exceptions import ErrorTypes, BotException

EXCEPTION = 'Data'
data_changed = True

def check_all(bot):
    '''
    Refreshes the server listing in the global data dictionary.
    '''
    for server in bot.servers:
        if server.id not in bot.data: # Mirrored with volatile data
            bot.data[server.id] = {}
            bot.volatile_data[server.id] = {}

def get_location(bot, server_id, channel_id, user_id, volatile):
    '''
    Gets the location given the server_id, channel_id, and user_id.
    '''

    data = bot.volatile_data if volatile else bot.data

    if server_id: # Look in the specific server
        if server_id in data:
            current = data[server_id]
        else: # Server not found - refresh listing
            check_all(bot)
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Server {} not found.".format(server_id))
        if channel_id:
            if channel_id not in current:
                current[channel_id] = {}
            current = current[channel_id]
        if user_id:
            if user_id not in current:
                current[user_id] = {}
            current = current[user_id]

    elif user_id: # Check for global user data
        current = data['global_users'].get(str(user_id), {})

    else: # Check for global plugin data
        current = data['global_plugins']

    return current

def get(bot, plugin_name, key, server_id=None, channel_id=None,
        user_id=None, default=None, volatile=False):
    '''
    Gets the data with the given key from the given plugin and specified
    location. If no specified location is given, the global component is
    searched. If only the user is given, it will search the global users
    component. Otherwise it will follow the specifiers to retireve the data if
    it exists. If it does not exist, returns default.

    If the key is None, it returns all of the data for the given plugin in that
    specific location.
    '''

    current = get_location(bot, server_id, channel_id, user_id, volatile)

    if key:
        return current.get(plugin_name, {}).get(str(key), default)
    else:
        return current.get(plugin_name, default)

def add(bot, plugin_name, key, value, server_id=None, channel_id=None,
        user_id=None, volatile=False):
    '''
    Adds the given information to the specified location. Location is specified
    in the same way as get(). If the value exists, this will overwrite it.
    '''

    current = get_location(bot, server_id, channel_id, user_id, volatile)

    if plugin_name not in current:
        current[plugin_name] = {}
    current[plugin_name][key] = value

    if not volatile:
        data_changed = True

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

    current = get_location(bot, server_id, channel_id, user_id, volatile)
    if (not current or
            plugin_name not in current or
            key not in current[plugin_name]):
        if safe:
            return default
        else:
            raise BotException(ErrorTypes.RECOVERABLE, EXCEPTION,
                    "Key '{}' not found.".format(key))

    if not volatile:
        data_changed = True

    elif key:
        return current[plugin_name].pop(key)
    else: # Remove all data associated with that plugin for the given location
        return current.pop(plugin_name)

def save_data(bot, force=False):
    '''
    Saves all of the current data in the data dictionary. Does not save
    volatile_data, though.
    '''

    global data_changed
    if data_changed or force: # Only save if something changed or forced
        # Loop through keys
        keys = []
        directory = bot.path + '/data/'
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

        data_changed = False

def get_data(bot):
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
