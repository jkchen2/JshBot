import json

from jshbot.exceptions import BotException, ErrorTypes

EXCEPTION = 'Configurations'


def get_configurations(bot):
    configurations_list = {}
    directory = bot.path + '/config'
    try:
        with open(directory + '/config.json', 'r') as config_file:
            configurations_list['core'] = json.load(config_file)
    except Exception as e:
        raise BotException(
            EXCEPTION,
            "Could not open the core configuration file", e=e,
            error_type=ErrorTypes.STARTUP)

    directory += '/'
    for plugin in bot.plugins:
        try:
            with open(directory + plugin + '.json', 'r') as config_file:
                configurations_list[plugin] = json.load(config_file)
        except FileNotFoundError:
            module = bot.plugins[plugin][0]
            if (getattr(module, 'uses_configuration', False) and
                    module.uses_configuration):
                raise BotException(
                    EXCEPTION, "Plugin {} requires a configuration file, "
                    "but it was not found.".format(plugin),
                    error_type=ErrorTypes.STARTUP)
        except Exception as e:
            raise BotException(
                EXCEPTION, "Could not open the {} configuration file.".format(
                    plugin), e=e, error_type=ErrorTypes.STARTUP)

    return configurations_list


def get(bot, plugin_name, extra=None, extension='json'):
    """Gets the configuration file for the given plugin.

    Keyword arguments:
    extra -- Looks for <plugin_name>-<extra>.<extension>
    extension -- If 'json', reads the file as json, otherwise reads it as text.
    """
    if extra:
        filename = '{0}/config/{1}-{2}.{3}'.format(
            bot.path, plugin_name, extra, extension)
    else:
        return bot.configurations[plugin_name]
    try:
        with open(filename, 'r') as config_file:
            if extension.lower() != 'json':
                return config_file.read()
            else:
                return json.load(config_file)
    except FileNotFoundError:
        raise BotException(EXCEPTION, "File {} not found.".format(filename))
    except Exception as e:
        raise BotException(
            EXCEPTION, "Failed to read {} properly.".format(filename), e=e)
