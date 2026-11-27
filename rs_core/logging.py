"""The plugin's logger, named f"{appname}.RhinoSpotter" as EDMC expects.

EDMC installs a handler per plugin under that name. Outside EDMC the logger
gets a NullHandler so test runs stay clean.
"""

import logging
import os
import re

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
DEBUG = bool(os.environ.get("RHINOSPOTTER_DEBUG"))     # also gates trace files (press.py)
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# The home folder names the OS account: written as ~ in every record.
# Case-insensitive, three forms: C:\Users\x, C:/Users/x, and C:\\Users\\x from an OSError repr.
_HOME = os.path.expanduser("~")
_FORMS = {_HOME, _HOME.replace("\\", "/"), _HOME.replace("\\", "\\\\")}
_HOME_RE = (re.compile("|".join(re.escape(h) for h in sorted(_FORMS, key=len, reverse=True)), re.IGNORECASE)
            if len(_HOME) > 3 else None)          # "~" unresolved, or "/" as home: nothing to hide


def _scrub(text):
    return _HOME_RE.sub("~", text) if _HOME_RE else text


class _NoHome(logging.Filter):
    """Replace the home folder with ~ in the message and the traceback."""

    def filter(self, record):
        try:
            text = record.getMessage()
        except (TypeError, ValueError):             # msg/args mismatch: raised here, in the caller
            text = f"{record.msg} {record.args}"
        record.msg, record.args = _scrub(text), ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = _scrub(record.exc_text)
        return True


logger.addFilter(_NoHome())
