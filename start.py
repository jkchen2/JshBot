import jshbot
import sys

if 'debug' in sys.argv:
    print("Saving debug prints to logs.txt")
    use_debug = True
else:
    use_debug = False

if 'shards' in sys.argv:
    try:
        total_shards = int(sys.argv[sys.argv.index('shards') + 1])
        assert total_shards > 1
        print("Using {} shards".format(total_shards))
    except:
        print("Invalid shard number - must be greater than 1.")
        sys.exit(1)
else:
    total_shards = 1

jshbot.core.initialize(__file__, debug=use_debug, shards=total_shards)
