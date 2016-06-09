import logging
import re

from jshbot import commands
from jshbot.exceptions import BotException

EXCEPTION = "Parser"


def split_parameters(parameters, include_quotes=False):

    if not parameters:
        return []
    split = re.split('( +)', parameters)
    joined_split = []
    add_start = add_end = -1

    for index, entry in enumerate(split):
        if entry.startswith('"'):
            add_start = index
        if (entry.endswith('"') and not entry.endswith('\\"') and
                len(entry) > 1 and add_start != -1):
            add_end = index + 1 if add_start == index else 0
        if add_start == -1:  # Add entry normally
            joined_split.append(entry)
        elif add_end != -1:  # Join entries in quotes
            if include_quotes:
                joined_split.append(''.join(split[add_start:add_end]))
            else:
                joined_split.append(''.join(split[add_start:add_end])[1:-1])
            add_start = add_end = -1

    if add_start != -1:  # Unclosed quote
        logging.warn("Detected an unclsed quote: " + split[add_start])
        joined_split.append(''.join(split[add_start:index + 1]))
    return joined_split


def match_blueprint(bot, base, parameters, blueprints, find_index=False):
    """Matches the given parameters to a valid blueprint.

    Returns a tuple of the blueprint index, the dictionary representing the
    options and the positional arguments, and the list of arguments.
    If find_index is set to True, this finds the closest match index instead.
    """
    closest_index = -1
    closest_index_matches = 0
    parameters_length = len(parameters)
    for blueprint_index, blueprint in enumerate(blueprints):

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
                if current >= parameters_length:
                    not_found = True
                    break
                elif parameters[current].lower() == plan[1]:
                    if plan[2] and current + 2 < parameters_length:
                        current_options[plan[1]] = parameters[current + 2]
                        current += 3
                        matches += 4
                    elif plan[2]:  # Positional argument not found
                        matches += 2
                        not_found = True
                        break
                    else:
                        current_options[plan[1]] = {}
                        current += 1
                        matches += 3
                elif plan[0]:  # Optional option
                    matches += 1
                else:  # Option not found
                    not_found = True
                    break

            elif current < parameters_length:  # Regular argument
                if plan[1] == ':':
                    current_arguments.append(parameters[current])
                    current += 1
                    matches += 1
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
            if matches > closest_index_matches:
                closest_index = blueprint_index
                closest_index_matches = matches
        else:
            if find_index:
                return blueprint_index
            return (blueprint_index, current_options, current_arguments)

    if find_index:
        return closest_index
    if closest_index == -1:
        quick_help = commands.usage_reminder(bot, base)
    else:
        closest_index += 1
        quick_help = commands.usage_reminder(bot, base, index=closest_index)
    raise BotException(EXCEPTION, "Invalid syntax.", quick_help)


def fill_shortcut(bot, shortcut, base, parameters):
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
                    bot, base, index=base_index, shortcut=True))
        return syntax

    try:
        current = 0
        for argument_type in template:
            while (current < parameters_length and
                    parameters[current].isspace()):
                current += 1

            if argument_type == ':':
                syntax = syntax.format(parameters[current])

            elif argument_type in ('&', '#'):
                syntax = syntax.format(''.join(parameters[current:]))

            elif argument_type in ('^', '+'):
                if len(parameters[current:]) == 1 and argument_type == '^':
                    combined = parameters[current]
                    if (combined.startswith('"') and
                            combined.endswith('"') and not
                            combined.endswith('\\"')):
                        combined = combined[1:-1]
                else:
                    combined = ''.join(parameters[current:])
                assert combined
                syntax = syntax.format(combined)

            current += 1

    except:
        reminder = commands.usage_reminder(
            bot, base, index=base_index, shortcut=True)
        raise BotException(EXCEPTION, "Invalid shortcut syntax.", reminder)

    return syntax


def parse(bot, command, base, parameters):
    """Parses the parameters and returns a tuple.

    This matches the parameters to a blueprint given by the command.
    The tuple is (base, blueprint_index, options, arguments).
    """
    parameters = parameters.strip()  # Safety strip

    # Substitute shortcuts
    if command.shortcut and base in command.shortcut.bases:
        filled = fill_shortcut(bot, command.shortcut, base, parameters)
        return parse(bot, command, command.base, filled)

    parameters = split_parameters(parameters)
    blueprint_index, options, arguments = match_blueprint(
        bot, base, parameters, command.blueprints)

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
    parameters = split_parameters(parameters)
    return (base, match_blueprint(
        bot, base, parameters, command.blueprints, find_index=True))
