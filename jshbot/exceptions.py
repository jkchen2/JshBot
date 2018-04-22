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
            error_type=ErrorTypes.RECOVERABLE, edit_message=None, autodelete=0,
            use_embed=True, embed_fields=[], embed_format={}, serious=False, editable=True):
        """
        Arguments:
        error_subject -- The error title. Generally the plugin name.
        error_details -- Primary error message.
        args -- A list of additional errors that get appended after the details.

        Keyword arguments:
        e -- The provided exception object itself.
        error_type -- Determines if the bot can recover from the exception.
        edit_message -- Edits the given message with the exception text or embed.
        autodelete -- Deletes after the given number of seconds, unless it is 0.
        use_embed -- The error should be displayed as an embed.
        embed_fields -- Additional fields used for providing titled descriptions of the error.
        embed_format -- Used to format the strings of the values in the embed fields.
        serious -- If True, always uses the :warning: emoji.
        editable -- Whether or not the error displays an "issuing command is editable" note.
        """
        self.error_type = error_type
        self.error_subject = str(error_subject)
        self.error_details = str(error_details)
        self.error_other = args
        self.provided_exception = e
        self.autodelete = 0 if autodelete is None else autodelete
        self.use_embed = use_embed
        self.editable = editable
        self.traceback = ''
        self.other_details = '\n'.join([str(arg) for arg in self.error_other])
        self.error_message = "`{subject} error: {details}`\n{others}".format(
            subject=self.error_subject,
            details=self.error_details,
            others=self.other_details)
        emoji = ':warning:' if serious or random() > 0.01 else ':thinking:'
        self.embed = Embed(
            title='{} {} error'.format(emoji, self.error_subject),
            description='{}\n{}'.format(self.error_details, self.other_details),
            colour=Colour(0xffcc4d))

        if self.provided_exception:
            if isinstance(self.provided_exception, BotException):
                given_error = '{}'.format(self.provided_exception.error_details)
                embed_fields = self.provided_exception.embed_fields
            else:
                given_error = '`{}: {}`'.format(
                    type(self.provided_exception).__name__, self.provided_exception)
            self.error_message += '\nGiven error:\n{}'.format(given_error)
            embed_fields = [('Given error:', given_error)] + embed_fields
            if self.provided_exception.__traceback__:
                self.traceback = traceback.format_tb(self.provided_exception.__traceback__)
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

        # Edit the given message with the error
        if edit_message:
            content, embed = ('', self.embed) if self.use_embed else (str(self), None)
            asyncio.ensure_future(edit_message.edit(content=content, embed=embed))

    def __str__(self):
        return self.error_message


class ConfiguredBotException():

    def __init__(self, error_subject):
        self.error_subject = error_subject

    def __call__(self, *args, **kwargs):
        return BotException(self.error_subject, *args, **kwargs)
