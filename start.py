import jshbot
import sys

use_debug = 'debug' in sys.argv
if use_debug:
    print("Saving debug prints to logs.txt")

jshbot.core.start(__file__, debug=use_debug)
