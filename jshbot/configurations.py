import json

from jshbot.exceptions import ConfiguredBotException, ErrorTypes

CBException = ConfiguredBotException('Configurations')


'''
def add_configurations(bot):
    configurations_list = {}
    directory = bot.path + '/config/'
    try:  # Load core config file
        with open(bot.path + '/config/config.json', 'r') as config_file:
            configurations_list['core'] = json.load(config_file)
    except Exception as e:
        raise CBException(
            "Could not open the core configuration file", e=e, error_type=ErrorTypes.STARTUP)

    for plugin in bot.plugins:  # Load all other config files
        if plugin == 'base':
            continue
        try:
            with open(directory + plugin + '.json', 'r') as config_file:
                configurations_list[plugin] = json.load(config_file)
        except FileNotFoundError:
            module = bot.plugins[plugin]
            if getattr(module, 'uses_configuration', False):
                raise CBException(
                    "Plugin {} requires a configuration file, "
                    "but it was not found.".format(plugin), error_type=ErrorTypes.STARTUP)
        except Exception as e:
            raise CBException(
                "Could not open the {} configuration file.".format(plugin),
                e=e, error_type=ErrorTypes.STARTUP)

    bot.configurations = configurations_list
    return configurations_list
'''


def get(bot, plugin_name, key=None, extra=None, extension='json'):
    """Gets the configuration file for the given plugin.

    Keyword arguments:
    key -- Gets the specified key from the config file, otherwise everything.
    extra -- Looks for <plugin_name>-<extra>.<extension>
    extension -- If 'json', reads the file as json, otherwise reads it as text.
    """
    if extra:  # Open from external configuration file
        filename = '{0}/config/{1}-{2}.{3}'.format(
            bot.path, plugin_name, extra, extension)
    else:  # Open from configuration dictionary
        try:
            config = bot.configurations[plugin_name]
        except KeyError:
            raise CBException(
                "Plugin {} not found in the configurations dictionary.".format(plugin_name))
        try:
            if key:
                return config[key]
            else:
                return config
        except KeyError:
            raise CBException("Key {} not found in the configuration file.".format(key))
    try:
        with open(filename, 'r') as config_file:
            if extension.lower() == 'json':
                return json.load(config_file)
            else:
                return config_file.read()
    except FileNotFoundError:
        raise CBException("File {} not found.".format(filename))
    except Exception as e:
        raise CBException("Failed to read {} properly.".format(filename), e=e)
