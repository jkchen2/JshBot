import json
import yaml

from jshbot.exceptions import ConfiguredBotException, ErrorTypes

CBException = ConfiguredBotException('Configurations')


def get(bot, plugin_name, key=None, extra=None, extension='yaml'):
    """Gets the configuration file for the given plugin.

    Keyword arguments:
    key -- Gets the specified key from the config file, otherwise everything.
    extra -- Looks for <plugin_name>-<extra>.<extension>
    extension -- If 'json', reads the file as json. Same for yaml. Otherwise reads it as text.
    """
    if extra:  # Open from external configuration file
        filename = '{0}/config/{1}-{2}.{3}'.format(bot.path, plugin_name[:-3], extra, extension)
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
        with open(filename, 'r', encoding='utf-8') as config_file:
            if extension.lower() == 'json':
                return json.load(config_file)
            elif extension.lower() == 'yaml':
                return yaml.load(config_file)
            else:
                return config_file.read()
    except FileNotFoundError:
        raise CBException("File {} not found.".format(filename))
    except Exception as e:
        raise CBException("Failed to read {} properly.".format(filename), e=e)


def redact(bot, plugin_name, key):
    """Overwrites the configuration entry to avoid accidentally leaking sensitive data."""
    try:
        config = bot.configurations[plugin_name]
    except KeyError:
        raise CBException(
            "Plugin {} not found in the configurations dictionary.".format(plugin_name))
    config[key] = '(redacted)'
