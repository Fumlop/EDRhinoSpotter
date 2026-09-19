r"""Where the game writes, asked rather than assumed.

The journal folder was spelled out in two places as

    %USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous

which is the default and not the answer. A commander who moved the folder - a
second drive, a synced profile, a Steam library somewhere else, an install
under Proton - has told EDMC where it is, and EDMC is already reading it. So
ask EDMC first and keep the default as the last resort.

Nothing here imports EDMC at module level: the plugin has to import in a bare
interpreter for the tests.

No tkinter. See rs_tests/test_paths.py.
"""

import os

from rs_core.logging import logger

# The default install, and the fallback when nothing better answers.
WINDOWS_JOURNAL = r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous"


def journal_dir():
    """The folder Status.json and the journals are in.

    Three sources, in the order of how much they know:

    1. `monitor.currentdir` - the folder EDMC is watching right now. It is the
       one that has already resolved the default, the commander's override and
       whatever the platform does, because it is the folder EDMC's own journal
       reading comes out of.
    2. The `journaldir` setting - what the commander typed, when they typed
       anything. Empty on a default install, which is why it cannot be the
       only source.
    3. The Windows default, expanded. Outside EDMC - the tests, the replay
       tool - this is all there is.
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
