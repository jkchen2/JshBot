import asyncio
import logging
import sys

from enum import Enum


# Rudimentary enumerated error types
class ErrorTypes(Enum):
    USER, RECOVERABLE, INTERNAL, STARTUP, FATAL = range(5)


class BotException(Exception):

    def __init__(
            self, error_subject, error_details, *args, e=None,
            error_type=ErrorTypes.RECOVERABLE, edit_pair=None):
        self.error_type = error_type
        self.error_subject = str(error_subject)
        self.error_details = str(error_details)
        self.error_other = args
        other_details = '\n'.join(args)
        self.error_message = "`{subject} error: {details}`\n{others}".format(
            subject=self.error_subject,
            details=self.error_details,
            others=other_details)
        if e:
            self.error_message += '\nGiven error:\n`{0}: {1}`'.format(
                type(e).__name__, e)

        logging.error(self.error_message)

        # If non-recoverable, quit
        if error_type in (
                ErrorTypes.STARTUP,
                ErrorTypes.FATAL,
                ErrorTypes.INTERNAL):
            sys.exit()

        if edit_pair:
            bot = edit_pair[0]
            message_reference = edit_pair[1]
            asyncio.ensure_future(
                bot.edit_message(message_reference, self.error_message))

    def __str__(self):
        return self.error_message
