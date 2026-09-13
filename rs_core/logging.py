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

# Debug lines only on a machine that asks for them. EDMC's plugin logger passes
# DEBUG by default, so without this every scan-window fit lands in a player's log.
logger.setLevel(logging.DEBUG if os.environ.get("RHINOSPOTTER_DEBUG") else logging.INFO)
