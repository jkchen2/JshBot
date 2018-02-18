import asyncio
import sys
import traceback

from random import random
from discord import Embed, Colour
from enum import Enum

from jshbot import logger


# Rudimentary enumerated error types
class ErrorTypes(Enum):
    USER, RECOVERABLE, INTERNAL, STARTUP, FATAL = range(5)


class BotException(Exception):

    def __init__(
            self, error_subject, error_details, *args, e=None,
            error_type=ErrorTypes.RECOVERABLE, edit_pair=None, autodelete=0,
            use_embed=True, embed_fields=[], embed_format={}, serious=False):
        self.error_type = error_type
        self.error_subject = str(error_subject)
        self.error_details = str(error_details)
        self.error_other = args
        self.provided_exception = e
        self.autodelete = 0 if autodelete is None else autodelete
        self.use_embed = use_embed
        self.traceback = ''
        self.other_details = '\n'.join([str(arg) for arg in args])
        self.error_message = "`{subject} error: {details}`\n{others}".format(
            subject=self.error_subject,
            details=self.error_details,
            others=self.other_details)
        emoji = ':warning:' if serious or random() > 0.01 else ':thinking:'
        self.embed = Embed(
            title='{} {} error'.format(emoji, self.error_subject),
            description='{}\n{}'.format(self.error_details, self.other_details),
            colour=Colour(0xffcc4d))

        if e:
            if isinstance(e, BotException):
                given_error = '{}'.format(e.error_details)
                embed_fields = e.embed_fields
            else:
                given_error = '`{}: {}`'.format(type(e).__name__, e)
            self.error_message += '\nGiven error:\n{}'.format(given_error)
            embed_fields = [('Given error:', given_error)] + embed_fields
            if e.__traceback__:
                self.traceback = traceback.format_tb(e.__traceback__)
            else:
                self.traceback = traceback.format_exc()

        self.embed_fields = embed_fields
        for name, value in embed_fields:
            self.embed.add_field(name=name, value=value.format(**embed_format), inline=False)

        logger.error(self.error_message)

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
