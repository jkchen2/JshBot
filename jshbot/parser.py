import discord
import re

from discord.abc import PrivateChannel

from jshbot import commands, utilities, logger
from jshbot.commands import ArgTypes
from jshbot.exceptions import ConfiguredBotException, BotException

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
        logger.warn("Detected an unclosed quote: " + split[add_start])
        joined_split.append(''.join(split[add_start:index + 1]))
    if quote_list:
        return (joined_split, quoted_indices)
    else:
        return joined_split


async def match_subcommand(bot, command, parameters, message, match_closest=False):
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

        current_index = 0
        matches = 0
        options = {}
        arguments = []
        last_opt_index = -1
        arg_index = -1
        used_opts = []
        exhausted_opts = len(subcommand.opts) == 0
        not_found_error = None

        while current_index < len(stripped_parameters):
            current = stripped_parameters[current_index]

            if not exhausted_opts:  # Check opts
                if current_index * 2 in quoted_indices:  # Quoted elements are always arguments
                    exhausted_opts = True

                found_opt = subcommand.opts.get(current.lower(), None)
                if not exhausted_opts and found_opt:

                    if subcommand.strict_syntax:  # Check strict syntax
                        if found_opt.index < last_opt_index:  # Syntax out of order
                            exhausted_opts = True
                        else:
                            last_opt_index = found_opt.index

                    if not exhausted_opts:
                        if found_opt.name in options:  # Duplicate. Skip to args
                            exhausted_opts = True
                        else:  # Check for attached argument
                            if found_opt.attached:  # Required attached argument
                                if current_index + 1 >= len(stripped_parameters):
                                    not_found_error = (
                                        'Option {opt.name_string} requires an attached parameter, '
                                        '{opt.attached_string}.'.format(opt=found_opt))
                                    matches += 3
                                else:
                                    current_index += 1
                                    options[found_opt.name] = stripped_parameters[current_index]
                                    matches += 6
                            else:  # No attached argument required
                                options[found_opt.name] = None
                                matches += 5
                            used_opts.append(found_opt)

                else:  # Option not found. Skip to args
                    exhausted_opts = True

                if exhausted_opts:  # No more matching opts - check for optional opts
                    current_index -= 1  # Search args where we left off
                    remaining_opts = [o for o in subcommand.opts.values() if o not in used_opts]
                    for opt in remaining_opts:
                        if opt.optional:
                            matches += 1
                            if opt.always_include:
                                options[opt.name] = opt.default
                        else:  # Not optional. Unfit subcommand
                            not_found_error = 'Option {} is required.'.format(opt.name_string)
                            break

            else:  # Check args
                arg_index += 1
                if arg_index >= len(subcommand.args):  # Too many arguments
                    not_found_error = 'Too many arguments.'
                else:
                    matches += 1
                    arg = subcommand.args[arg_index]
                    if arg.argtype in (ArgTypes.SINGLE, ArgTypes.OPTIONAL):
                        arguments.append(current)
                    else:  # Instant finish grouped arguments
                        if arg.argtype in (ArgTypes.SPLIT, ArgTypes.SPLIT_OPTIONAL):
                            arguments += stripped_parameters[current_index:]
                        else:  # Merged
                            split_arguments = []
                            quote_index = current_index * 2
                            for segment in parameters[current_index * 2:]:
                                if quote_index in quoted_indices:  # Add quotes back in
                                    split_arguments.append('"{}"'.format(segment))
                                else:
                                    split_arguments.append(segment)
                                quote_index += 1
                            arguments += [''.join(split_arguments)]
                        break

            if not_found_error:  # Skip rest of loop and evaluate matches
                break

            current_index += 1

        # Finished opt/arg while loop
        if not not_found_error and not exhausted_opts:  # Opts remain
            remaining_opts = [o for o in subcommand.opts.values() if o not in used_opts]
            for opt in remaining_opts:
                if opt.optional:
                    matches += 1
                    if opt.always_include:
                        options[opt.name] = opt.default
                else:  # Not optional. Unfit subcommand
                    not_found_error = 'Option {} is required.'.format(opt.name_string)
                    break
        if not not_found_error and arg_index < len(subcommand.args) - 1:  # Optional arguments
            arg_index += 1
            arg = subcommand.args[arg_index]
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
                not_found_error = 'No value given for argument {}.'.format(arg.help_string)

        if not not_found_error:  # Check for message attachment
            if subcommand.attaches:
                if message.attachments or subcommand.attaches.optional:
                    matches += 6
                else:
                    not_found_error = 'Missing attachment **__`{name}`__**'.format(
                        name=subcommand.attaches.name)
            elif message.attachments:  # No attachment argument, but attachment was provided
                not_found_error = 'No attachment required, but one was given.'

        if not_found_error:  # Find closest subcommand
            if matches > closest_index_matches:
                closest_index = subcommand.index
                closest_index_matches = matches
                closest_index_error = not_found_error
        else:  # Subcommand found. Convert and check
            if subcommand.confidence_threshold is not None:  # Confidence threshold
                if closest_index_matches >= subcommand.confidence_threshold:
                    continue  # Skip valid match due to low confidence

            # No additional processing
            if match_closest:
                if matches <= 1 and matches < closest_index_matches:  # No confidence
                    continue
                else:
                    return subcommand

            # Cannot match parameters in a direct message if disabled
            elif not subcommand.allow_direct and isinstance(message.channel, PrivateChannel):
                return subcommand, {}, []

            # Fill in options and arguments
            else:
                for option_name, value in options.items():  # Check options
                    current_opt = subcommand.opts[option_name]
                    new_value = await current_opt.convert_and_check(bot, message, value)
                    if new_value is not None:
                        options[option_name] = new_value
                for index, pair in enumerate(zip(subcommand.args, arguments)):  # Check arguments
                    arg, value = pair
                    if (value is not None
                            or arg.argtype in (ArgTypes.SINGLE, ArgTypes.SPLIT, ArgTypes.MERGED)):
                        if arg.argtype not in (ArgTypes.SINGLE, ArgTypes.OPTIONAL):
                            new_values = await arg.convert_and_check(
                                bot, message, arguments[index:])
                            arguments = arguments[:index] + new_values
                            break
                        else:
                            new_value = await arg.convert_and_check(bot, message, value)
                            arguments[index] = new_value

                return subcommand, options, arguments

    # Looped through all subcommands. Not found
    if closest_index == -1 or closest_index_matches <= 1:  # Low confidence
        guess = command
    else:
        guess = command.subcommands[closest_index]
    if match_closest:
        return guess
    else:
        if isinstance(guess, commands.SubCommand):
            syntax_error = 'Invalid syntax: {}'.format(closest_index_error)
        else:
            guess = command
            syntax_error = 'Invalid syntax.'
        invoker = utilities.get_invoker(bot, guild=message.guild)
        raise CBException(
            syntax_error, embed_fields=guess.help_embed_fields, embed_format={'invoker': invoker})


async def fill_shortcut(bot, shortcut, parameters, message):
    parameters = split_parameters(parameters, include_quotes=True)
    stripped_parameters = parameters[::2]
    arguments_dictionary = {}
    current_index = -1
    for current_index, current in enumerate(stripped_parameters):
        if current_index >= len(shortcut.args):
            invoker = utilities.get_invoker(bot, guild=message.guild)
            raise CBException(
                "Too many arguments.", embed_fields=shortcut.help_embed_fields,
                embed_format={'invoker': invoker})
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
    logger.debug("Finished shortcut loop. %s", arguments_dictionary)
    if current_index < len(shortcut.args) - 1:  # Check for optional arguments
        arg = shortcut.args[current_index + 1]
        if arg.argtype is ArgTypes.OPTIONAL:
            while (arg and arg.argtype is ArgTypes.OPTIONAL and
                    current_index < len(shortcut.args)):
                arguments.append('' if arg.default is None else arg.default)
                current_index += 1
                try:
                    arg = shortcut.args[current_index]
                except:
                    arg = None
        if arg and arg.argtype in (ArgTypes.SPLIT_OPTIONAL, ArgTypes.MERGED_OPTIONAL):
            arguments_dictionary[arg.name] = '' if arg.default is None else arg.default
        elif arg:
            invoker = utilities.get_invoker(bot, guild=message.guild)
            raise CBException(
                "Not enough arguments.", embed_fields=shortcut.help_embed_fields,
                embed_format={'invoker': invoker})
    logger.debug("Finished checking for optional arguments. %s", arguments_dictionary)
    for arg in shortcut.args:
        value = arguments_dictionary[arg.name]
        if value is not None:
            logger.debug("Converting and checking 4")
            new_value = await arg.convert_and_check(bot, message, value)
            arguments_dictionary[arg.name] = new_value
    return shortcut.replacement.format(**arguments_dictionary).strip()


async def parse(bot, command, parameters, message):
    """Parses the parameters and returns a tuple.

    This matches the parameters to a subcommand.
    The tuple is (base, subcommand_index, options, arguments).
    """
    parameters = parameters.strip()  # Safety strip

    if isinstance(command, commands.Shortcut):  # Fill replacement string
        logger.debug("Filling shortcut...")
        parameters = await fill_shortcut(bot, command, parameters, message)
        command = command.command  # command is actually a Shortcut. Not confusing at all
        logger.debug("Shortcut filled to: [%s]", parameters)

    subcommand, options, arguments = await match_subcommand(bot, command, parameters, message)

    return (subcommand, options, arguments)
    #  return (command, subcommand.index, options, arguments, command.keywords)


async def guess_command(
        bot, text, message, safe=True, substitute_shortcuts=True, suggest_help=True):
    """Guesses the closest command or subcommand.
    
    Keyword arguments:
    safe -- Returns None if no command was guessed
    substitute_shortcuts -- Fills in the shortcut (if found) and guesses a command from that
    suggest_help -- Suggests that the user run the regular help command
    """
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
            if suggest_help:
                invoker = utilities.get_invoker(bot, message=message)
                additional = ' To see the menu, type `{}help`'.format(invoker)
            else:
                additional = ''
            raise CBException("Invalid base.{}".format(additional))
    if isinstance(command, commands.Shortcut) and substitute_shortcuts:
        try:
            parameters = await fill_shortcut(bot, command, parameters, message)
            command = command.command
        except BotException:
            return command.command
    if not parameters or isinstance(command, commands.Shortcut):
        return command
    else:
        return await match_subcommand(bot, command, parameters, message, match_closest=True)
