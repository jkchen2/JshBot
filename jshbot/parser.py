import logging
import re

from jshbot import commands
from jshbot.commands import ArgTypes
from jshbot.exceptions import ConfiguredBotException

CBException = ConfiguredBotException('Parser')


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
        logging.warn("Detected an unclosed quote: " + split[add_start])
        joined_split.append(''.join(split[add_start:index + 1]))
    if quote_list:
        return (joined_split, quoted_indices)
    else:
        return joined_split


def match_subcommand(bot, command, parameters, message, match_closest=False):
    """Matches the given parameters to a valid subcommand from the command.
    Returns a tuple of the subcommand, options, and arguments.

    If match_closest is True, returns the closest matching subcommand or None.
    No processing (conversion, checking) is done, and returns only the subcommand or None.
    """

    parameters, quoted_indices = split_parameters(parameters, quote_list=True)
    closest_index = -1
    closest_index_matches = 0
    closest_index_error = None
    stripped_parameters = parameters[::2]
    for subcommand in command.subcommands:

        print("\n===In subcommand:", subcommand.index)
        print("Subcommand args:", subcommand.args)
        current_index = 0
        matches = 0
        options = {}
        arguments = []
        last_opt_index = -1
        arg_index = -1
        used_opts = []
        exhausted_opts = False
        not_found = False
        not_found_error = None

        while current_index < len(stripped_parameters):
            current = stripped_parameters[current_index]
            print("On index:", current_index)
            print("Checking:", current)

            if current_index * 2 in quoted_indices:  # Quoted elements are always arguments
                print("Quoted element found. Skipping to args.")
                exhausted_opts = True

            if not exhausted_opts:  # Check opts
                print("Checking opts.")
                found_opt = subcommand.opts.get(current.lower(), None)
                if found_opt:

                    if not exhausted_opts and subcommand.strict_syntax:  # Check strict syntax
                        if found_opt.index < last_opt_index:  # Syntax out of order
                            print("Syntax out of order detected. Exhausted opts.")
                            exhausted_opts = True
                        else:
                            last_opt_index = found_opt.index

                    if not exhausted_opts:
                        if found_opt.name in options:  # Duplicate. Skip to args
                            print("Duplicate opt found. Skipping to args.")
                            exhausted_opts = True
                        else:  # Check for attached argument
                            if found_opt.attached:  # Required attached argument
                                if current_index + 1 >= len(stripped_parameters):
                                    print("Required attachment not found. not_found set to True.")
                                    not_found_error = (
                                        'Option \'{opt.name}\' requires an attached '
                                        'parameter, \'{opt.attached}\'.'.format(opt=found_opt))
                                    not_found = True
                                    matches += 3
                                else:
                                    print("Opt with attached parameter found:", found_opt.name)
                                    current_index += 1
                                    options[found_opt.name] = stripped_parameters[current_index]
                                    matches += 6
                            else:  # No attached argument
                                print("Opt found:", found_opt.name)
                                options[found_opt.name] = None
                                matches += 5
                            used_opts.append(found_opt)

                else:  # Option not found. Skip to args
                    print("Opt not found. Opts exhausted.")
                    exhausted_opts = True

                if exhausted_opts:  # No more matching opts - check for optional opts
                    print("Opts exhausted.")
                    current_index -= 1  # Search args where we left off
                    remaining_opts = [o for o in subcommand.opts.values() if o not in used_opts]
                    for opt in remaining_opts:
                        if opt.optional:
                            matches += 1
                        else:  # Not optional. Unfit subcommand
                            print("A mandatory option remains. not_found set to True.", opt.name)
                            not_found_error = (
                                'Option \'{}\' is required and must be included'.format(opt.name))
                            not_found = True
                            break

            else:  # Check args
                arg_index += 1
                print("Checking args. arg_index:", arg_index)
                if arg_index >= len(subcommand.args):  # Too many arguments
                    print("Detecting that there are too many arguments. not_found = True")
                    not_found_error = 'Too many arguments.'
                    not_found = True
                else:
                    matches += 1
                    arg = subcommand.args[arg_index]
                    if arg.argtype in (ArgTypes.SINGLE, ArgTypes.OPTIONAL):
                        print("Matched SINGLE/OPTIONAL arg.")
                        arguments.append(current)
                    else:  # Instant finish grouped arguments
                        print("Matched GROUPED arg.")
                        if arg.argtype in (ArgTypes.SPLIT, ArgTypes.SPLIT_OPTIONAL):
                            arguments += stripped_parameters[current_index:]
                        else:  # Merged
                            arguments += [''.join(parameters[current_index * 2:])]
                        break

            if not_found_error:  # Skip rest of loop and evaluate matches
                print("Not found: Breaking out of the loop early.")
                break

            current_index += 1

        # Finished opt/arg while loop
        print("Finished opt/arg while loop.")
        if not not_found_error and not exhausted_opts:  # Opts remain
            print("Checking for remaining mandatory opts.")
            remaining_opts = [o for o in subcommand.opts.values() if o not in used_opts]
            # for opt in subcommand.opts.values():
            for opt in remaining_opts:
                if opt.optional:
                    matches += 1
                else:  # Not optional. Unfit subcommand
                    print("A mandatory option was required, but not supplied. not_found = True")
                    not_found_error = (
                        'Option \'{}\' is required and must be included.'.format(opt.name))
                    break
        print("arg_index value:", arg_index)
        print("subcommand args length:", len(subcommand.args))
        if not not_found_error and arg_index < len(subcommand.args) - 1:  # Optional arguments
            print("Checking for optional arguments.")
            arg = subcommand.args[arg_index + 1]
            if arg.argtype is ArgTypes.OPTIONAL:
                matches += 1
                while (arg and arg.argtype is ArgTypes.OPTIONAL and
                        arg_index < len(subcommand.args)):
                    arguments.append(arg.default)
                    arg_index += 1
                    try:
                        arg = subcommand.args[arg_index]
                    except:
                        arg = None
            if arg and arg.argtype in (ArgTypes.SPLIT_OPTIONAL, ArgTypes.MERGED_OPTIONAL):
                matches += 1
                arguments.append(arg.default)
            elif arg:
                print("A mandatory argument was required, but not supplied. not_found = True")
                not_found_error = 'No value given for argment \'{}\'.'.format(arg.name)

        if not not_found_error and subcommand.attaches:  # Check for message attachment
            if not message.attachments and not subcommand.attaches.optional:
                print("Not found triggered. C")
                not_found_error = 'Missing attachment \'{name}\''.format(
                    name=subcommand.attaches.name)
            elif message.attachments:  # No attachment argument, but attachment was provided
                not_found_error = 'No attachment required, but one was given.'

        if not_found_error:  # Find closest subcommand
            if matches > closest_index_matches:
                closest_index = subcommand.index
                closest_index_matches = matches
                closest_index_error = not_found_error
        else:  # Subcommand found. Convert and check
            if match_closest:  # No additional processing
                return subcommand
            else:

                for option_name, value in options.items():  # Check options
                    print("Converting and checking 1")
                    new_value = subcommand.opts[option_name].convert_and_check(bot, message, value)
                    if new_value is not None:
                        options[option_name] = new_value
                for index, pair in enumerate(zip(subcommand.args, arguments)):  # Check arguments
                    arg, value = pair
                    if value:
                        if arg.argtype not in (ArgTypes.SINGLE, ArgTypes.OPTIONAL):
                            print("Converting and checking 2")
                            new_values = arg.convert_and_check(bot, message, arguments[index:])
                            arguments = arguments[:index] + new_values
                            break
                        else:
                            print("Converting and checking 3")
                            new_value = arg.convert_and_check(bot, message, value)
                            arguments[index] = new_value

                print("Returning found subcommand:", subcommand)
                return subcommand, options, arguments

    # Looped through all subcommands. Not found
    if closest_index == -1 or closest_index_matches <= 1:  # Low confidence
        guess = command
    else:
        guess = command.subcommands[closest_index]
    print("No subcommand found. Best guess:", guess)
    if match_closest:
        print("Returnning closest subcommand:", subcommand)
        return guess
    else:
        if isinstance(guess, commands.SubCommand):
            syntax_error = 'Invalid syntax: {}'.format(closest_index_error)
        else:
            guess = command
            syntax_error = 'Invalid syntax.'
        raise CBException(syntax_error, embed_fields=guess.help_embed_fields)


def fill_shortcut(bot, shortcut, parameters, message):
    parameters = split_parameters(parameters, include_quotes=True)
    stripped_parameters = parameters[::2]
    arguments_dictionary = {}
    current_index = -1
    for current_index, current in enumerate(stripped_parameters):
        if current_index >= len(shortcut.args):
            raise CBException('Too many arguments.', embed_fields=shortcut.help_embed_fields)
        else:
            arg = shortcut.args[current_index]
            if arg.argtype in (ArgTypes.SINGLE, ArgTypes.OPTIONAL):
                arguments_dictionary[arg.name] = current
            else:  # Instant finish grouped arguments
                if arg.argtype in (ArgTypes.SPLIT, ArgTypes.SPLIT_OPTIONAL):
                    arguments_dictionary[arg.name] = ''.join(stripped_parameters[current_index:])
                else:  # Merged
                    arguments_dictionary[arg.name] = ''.join(parameters[current_index * 2:])
                break
    # TODO: TEST THIS!
    print("Finished shortcut loop.", arguments_dictionary)
    if current_index < len(shortcut.args) - 1:  # Check for optional arguments
        arg = shortcut.args[current_index + 1]
        if arg.argtype is ArgTypes.OPTIONAL:
            while (arg and arg.argtype is ArgTypes.OPTIONAL and
                    current_index < len(shortcut.args)):
                arguments.append(arg.default)
                current_index += 1
                try:
                    arg = shortcut.args[current_index]
                except:
                    arg = None
        if arg and arg.argtype in (ArgTypes.SPLIT_OPTIONAL, ArgTypes.MERGED_OPTIONAL):
            arguments_dictionary[arg.name] = arg.default
        elif arg:
            raise CBException('Not enough arguments.', embed_fields=shortcut.help_embed_fields)
    print("Finished checking for optional arguments.", arguments_dictionary)
    for arg in shortcut.args:
        value = arguments_dictionary[arg.name]
        if value:
            print("Converting and checking 4")
            new_value = arg.convert_and_check(bot, message, value)
            arguments_dictionary[arg.name] = new_value
    return shortcut.replacement.format(**arguments_dictionary)


def parse(bot, command, parameters, message):
    """Parses the parameters and returns a tuple.

    This matches the parameters to a subcommand.
    The tuple is (base, subcommand_index, options, arguments).
    """
    parameters = parameters.strip()  # Safety strip

    if isinstance(command, commands.Shortcut):  # Fill replacement string
        print("Filling shortcut...")
        parameters = fill_shortcut(bot, command, parameters, message)
        command = command.command  # command is actually a Shortcut. Not confusing at all
        print("Shortcut filled to:", parameters)

    print("Attempting to match for a subcommand")
    subcommand, options, arguments = match_subcommand(bot, command, parameters, message)
    print("Parser finished.")

    return (subcommand, options, arguments)
    #  return (command, subcommand.index, options, arguments, command.keywords)


def guess_command(bot, text, message, safe=True, substitue_shortcuts=True):
    """Guesses the closest command or subcommand."""
    if not text:
        if safe:
            return None
        else:
            raise CBException("No guess text.")
    text = text.strip()
    split_content = text.split(' ', 1)
    if len(split_content) == 1:
        split_content.append('')
    base, parameters = split_content
    base = base.lower()
    try:
        command = bot.commands[base]
    except KeyError:
        if safe:
            return None
        else:
            raise CBException("Invalid base.")
    if isinstance(command, commands.Shortcut) and substitue_shortcuts:
        try:
            parameters = fill_shortcut(bot, command, parameters, message)
            command = command.command
        except BotException:
            return command.command
    if not parameters or isinstance(command, commands.Shortcut):
        return command
    else:
        return match_subcommand(bot, command, parameters, message, match_closest=True)
