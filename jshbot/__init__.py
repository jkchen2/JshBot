core_version = '0.4.0-rewrite'
core_date = 'June 20th, 2018'

# Create logger
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(filename)s] %(asctime)s %(levelname)s: %(message)s'))
handler.setLevel(logging.DEBUG)
handler.set_name('jb_log_stream')
logger.addHandler(handler)
logger.propagate = False

import jshbot.core as core
import jshbot.exceptions as exceptions
import jshbot.parser as parser
import jshbot.plugins as plugins
import jshbot.commands as commands
import jshbot.configurations as configurations
import jshbot.data as data
import jshbot.utilities as utilities

# Base is imported through the plugins module
# Other plugins are imported in a similar fashion
