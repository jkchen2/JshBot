import asyncio
import logging
import sys
import traceback

from random import random
from discord import Embed, Colour
from enum import Enum


# Rudimentary enumerated error types
class ErrorTypes(Enum):
    USER, RECOVERABLE, INTERNAL, STARTUP, FATAL = range(5)


class BotException(Exception):

    def __init__(
            self, error_subject, error_details, *args, e=None,
            error_type=ErrorTypes.RECOVERABLE, edit_pair=None, autodelete=0,
            use_embed=True, embed_fields=[], serious=False):
        self.error_type = error_type
        self.error_subject = str(error_subject)
        self.error_details = str(error_details)
        self.error_other = args
        self.provided_exception = e
        self.autodelete = autodelete
        self.use_embed = use_embed
        self.traceback = ''
        other_details = '\n'.join([str(arg) for arg in args])
        self.error_message = "`{subject} error: {details}`\n{others}".format(
            subject=self.error_subject,
            details=self.error_details,
            others=other_details)
        emoji = ':warning:' if serious or random() > 0.01 else ':thinking:'
        self.embed = Embed(
            title='{} {} error'.format(emoji, self.error_subject),
            description='{}\n{}'.format(self.error_details, other_details),
            colour=Colour(0xffcc4d))

        if e:
            given_error = '`{}: {}`'.format(type(e).__name__, e)
            self.error_message += '\nGiven error:\n{}'.format(given_error)
            embed_fields.insert(0, ('Given error:', given_error))
            if e.__traceback__:
                self.traceback = traceback.format_tb(e.__traceback__)
            else:
                self.traceback = traceback.format_exc()

        for name, value in embed_fields:
            self.embed.add_field(name=name, value=value, inline=False)

        logging.error(self.error_message)

        # If non-recoverable, quit
        if error_type in (ErrorTypes.STARTUP, ErrorTypes.FATAL, ErrorTypes.INTERNAL):
            traceback.print_exc()
            sys.exit()

        if edit_pair:
            bot, message_reference = edit_pair
            asyncio.ensure_future(bot.edit_message(message_reference, self.error_message))

    def __str__(self):
        return self.error_message


class ConfiguredBotException(BotException):

    def __init__(self, error_subject):
        self.error_subject = error_subject

    def __call__(self, *args, **kwargs):
        return BotException(self.error_subject, *args, **kwargs)
