import logging
import re

from jshbot import commands
from jshbot.exceptions import BotException

EXCEPTION = "Parser"


def split_parameters(parameters, include_quotes=False, quote_list=False):
    """Splits up the given parameters by spaces and quotes.

    Keyword arguments:
    include_quotes -- The quotes attached to the parameters will be included.
    quote_list -- Gets a list of indices that represent parameters that were
        grouped because of quotes.
    """

    if not parameters:
        if quote_list:
            return ([], [])
        else:
            return []
    split = re.split('( +)', parameters)
    quoted_indices = []
    joined_split = []
    add_start = -1
    add_end = -1

    for index, entry in enumerate(split):
        if entry.startswith('"'):
            add_start = index
        if (entry.endswith('"') and not entry.endswith('\\"') and
                len(entry) > 1 and add_start != -1):
            add_end = index + 1
        if add_start == -1:  # Add entry normally
            joined_split.append(entry)
        elif add_end != -1:  # Join entries in quotes
            quoted_indices.append(len(joined_split))
            combined = ''.join(split[add_start:add_end])
            if include_quotes:
                joined_split.append(combined)
            else:
                joined_split.append(combined[1:-1])
            add_start = -1
            add_end = -1

    if add_start != -1:  # Unclosed quote
        logging.warn("Detected an unclsed quote: " + split[add_start])
        joined_split.append(''.join(split[add_start:index + 1]))
    if quote_list:
        return (joined_split, quoted_indices)
    else:
        return joined_split


def match_blueprint(
        bot, base, parameters, quoted_indices, command,
        find_index=False, server=None):
    """Matches the given parameters to a valid blueprint from the command.

    Returns a tuple of the blueprint index, the dictionary representing the
    options and the positional arguments, and the list of arguments.
    If find_index is set to True, this finds the closest match index instead.
    """
    closest_index = -1
    closest_index_matches = 0
    parameters_length = len(parameters)
    for blueprint_index, blueprint in enumerate(command.blueprints):

        current = 0
        matches = 0
        current_options = {}
        current_arguments = []
        not_found = False

        for plan in blueprint:
            while (current < parameters_length and
                    parameters[current].isspace()):
                current += 1  # Skip to content

            if plan[1].isalpha():  # Option
                if (current < parameters_length and
                        parameters[current].lower() == plan[1] and
                        current not in quoted_indices):
                    if plan[2] and current + 2 < parameters_length:
                        current_options[plan[1]] = parameters[current + 2]
                        current += 3
                        matches += 6
                    elif plan[2]:  # Positional argument not found
                        matches += 3
                        not_found = True
                        break
                    else:
                        current_options[plan[1]] = {}
                        current += 1
                        matches += 5
                elif plan[0]:  # Optional option
                    matches += 1
                else:  # Option not found
                    not_found = True
                    break

            elif current < parameters_length:  # Regular argument
                matches += 1
                if plan[1] == ':':
                    current_arguments.append(parameters[current])
                    current += 1
                elif plan[1] in ('+', '#'):  # Instant finish
                    current_arguments += filter(
                        lambda c: not c.isspace(), parameters[current:])
                    current = parameters_length
                elif plan[1] in ('^', '&'):  # Instant finish
                    current_arguments += [''.join(parameters[current:])]
                    current = parameters_length
            elif plan[1] in ('#', '&'):  # No required arguments instant finish
                current_arguments.append('')
                current = parameters_length
                matches += 1
            else:  # No arguments, more required
                not_found = True
                break

        if not_found or current < parameters_length:
            if matches >= 1 and command.strict and find_index:
                closest_index = blueprint_index
                closest_index_matches = 2  # Always get detailed help
                break
            elif matches >= closest_index_matches:
                closest_index = blueprint_index
                closest_index_matches = matches
        else:
            if find_index:
                if matches > closest_index_matches:
                    return blueprint_index
                else:
                    return closest_index
            return (blueprint_index, current_options, current_arguments)

    if find_index:
        return closest_index
    if ((closest_index == -1 or closest_index_matches <= 1) and
            len(command.blueprints) > 1):  # Low confidence
        quick_help = commands.usage_reminder(bot, base, server=server)
    else:
        closest_index = 1 if closest_index == -1 else closest_index + 1
        quick_help = commands.usage_reminder(
            bot, base, index=closest_index, server=server)
    raise BotException(EXCEPTION, "Invalid syntax.", quick_help)


def fill_shortcut(bot, shortcut, base, parameters, server=None):
    """
    Replaces elements in the syntax using the template with the parameters.
    Example:
        (<('create {} {}', ':^')>, 'tag', '"my tag" tag text'])
    Returns:
        'create "my tag" tag text'
    """
    parameters = split_parameters(parameters, include_quotes=True)
    parameters_length = len(parameters)
    base_index = shortcut.bases.index(base)
    syntax, template = shortcut.format_pairs[base_index]

    if not template:
        if parameters:
            raise BotException(
                EXCEPTION,
                "Shortcut requires no arguments, but some were given.",
                commands.usage_reminder(
                    bot, base, index=base_index, shortcut=True, server=server))
        return syntax

    try:
        current = 0
        to_add = []
        for argument_type in template:
            while (current < parameters_length and
                    parameters[current].isspace()):
                current += 1

            if argument_type == ':':
                to_add.append(parameters[current])

            elif argument_type in ('&', '#'):
                to_add.append(''.join(parameters[current:]))

            elif argument_type in ('^', '+'):
                if len(parameters[current:]) == 1 and argument_type == '^':
                    combined = parameters[current]
                else:
                    combined = ''.join(parameters[current:])
                assert combined
                to_add.append(combined)

            current += 1

        syntax = syntax.format(*to_add)
    except:
        reminder = commands.usage_reminder(
            bot, base, index=base_index, shortcut=True, server=server)
        raise BotException(EXCEPTION, "Invalid shortcut syntax.", reminder)

    return syntax


def parse(bot, command, base, parameters, server=None):
    """Parses the parameters and returns a tuple.

    This matches the parameters to a blueprint given by the command.
    The tuple is (base, blueprint_index, options, arguments).
    """
    parameters = parameters.strip()  # Safety strip

    # Substitute shortcuts
    if command.shortcut and base in command.shortcut.bases:
        filled = fill_shortcut(
            bot, command.shortcut, base, parameters, server=server)
        return parse(bot, command, command.base, filled)

    parameters, quoted_indices = split_parameters(parameters, quote_list=True)
    blueprint_index, options, arguments = match_blueprint(
        bot, base, parameters, quoted_indices, command, server=server)

    return (base, blueprint_index, options, arguments, command.keywords)


def guess_index(bot, text):
    """Guesses the closest command and returns the base and index."""
    text = text.strip()
    split_content = text.split(' ', 1)
    if len(split_content) == 1:
        split_content.append('')
    base, parameters = split_content
    base = base.lower()
    command = bot.commands[base]
    parameters, quoted_indices = split_parameters(parameters, quote_list=True)
    return (base, match_blueprint(
        bot, base, parameters, quoted_indices, command, find_index=True))
