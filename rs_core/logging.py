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

# Quiet unless asked. EDMC's plugin logger passes everything, so without this
# every map build and guide start lands in a player's log. Warnings and errors
# still go through - a map that could not be saved has to say so somewhere.
# Set RHINOSPOTTER_DEBUG=1 before starting EDMC for all of it.
logger.setLevel(logging.DEBUG if os.environ.get("RHINOSPOTTER_DEBUG") else logging.WARNING)
