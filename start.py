import jshbot, sys
if len(sys.argv) == 2 and sys.argv[1] == 'debug':
    print("Showing debug prints.")
    use_debug = True
else:
    use_debug = False
jshbot.core.initialize(__file__, debug=use_debug)
