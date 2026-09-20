"""The plugin's logger, named f"{appname}.RhinoSpotter" as EDMC expects.

EDMC installs a handler per plugin under that name. Outside EDMC the logger
gets a NullHandler so test runs stay clean.
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

# INFO by default, DEBUG with RHINOSPOTTER_DEBUG set. The 9 info-level lines
# are once-per-event (map shown/hidden, guide start/stop, migration) and are
# what post-hoc questions need. Per-tick lines are debug.
logger.setLevel(logging.DEBUG if os.environ.get("RHINOSPOTTER_DEBUG") else logging.INFO)
