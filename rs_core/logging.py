"""One logger, named the way EDMC names plugin loggers.

EDMC installs a handler per plugin under this name, so a message here lands in
EDMC's own log rather than in a file nobody opens. Outside EDMC the fallback
keeps prints off stdout, which would otherwise mix into a test run.
"""

import logging
import os

PLUGIN_NAME = "RhinoSpotter"

try:
    from config import appname                       # EDMC
    logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")
except ImportError:                                  # bare interpreter, tests
    logger = logging.getLogger(PLUGIN_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

# Info and up. The nine info lines in the plugin are all once-per-event - the
# map going down and coming back, a guide starting and closing, a migration -
# and they are exactly what gets asked about after the fact: "the map vanished
# and I do not know why". At WARNING that answer cost a RHINOSPOTTER_DEBUG=1
# and an EDMC restart, by which time the state that hid it was gone. Per-tick
# lines are debug and stay behind the variable.
logger.setLevel(logging.DEBUG if os.environ.get("RHINOSPOTTER_DEBUG") else logging.INFO)
