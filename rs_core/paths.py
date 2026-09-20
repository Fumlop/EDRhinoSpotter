r"""Resolves the Elite Dangerous journal folder.

The default path is only a fallback: a moved folder, a synced profile, a Steam
library elsewhere or an install under Proton is already resolved by EDMC, so
EDMC is asked first. See journal_dir().

EDMC is imported inside the function, not at module level, so the module
imports in a bare interpreter.

No tkinter. Tests in rs_tests/test_paths.py.
"""

import os

from rs_core.logging import logger

# Default install path, expanded only as the last fallback.
WINDOWS_JOURNAL = r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous"


def journal_dir():
    """Path to the folder holding Status.json and the journal files.

    Tried in order:

    1. monitor.currentdir - the folder EDMC is watching; already resolved for
       platform, default and override.
    2. the journaldir setting - set only when the commander typed a path.
    3. WINDOWS_JOURNAL, expandvars'd. The only source outside EDMC.
    """
    try:
        from monitor import monitor                # EDMC
        current = getattr(monitor, "currentdir", None)
        if current:
            return os.path.expanduser(str(current))
    except (ImportError, AttributeError, OSError):
        pass
    try:
        from config import config                  # EDMC
        setting = config.get_str("journaldir")
        if setting:
            return os.path.expanduser(setting)
    except (ImportError, AttributeError, OSError):
        pass
    fallback = os.path.expandvars(WINDOWS_JOURNAL)
    logger.debug(f"paths: no journal folder from EDMC, falling back to {fallback}")
    return fallback
