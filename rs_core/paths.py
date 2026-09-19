r"""Where the plugin's files live and where the game writes, on either system.

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
import pathlib
import subprocess
import sys
import webbrowser

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


def data_root():
    r"""The plugin's own folder: bookmarks, maps and their backups.

    %LOCALAPPDATA%\RhinoSpotter on Windows, $XDG_DATA_HOME/RhinoSpotter on
    Linux - ~/.local/share/RhinoSpotter unless the commander says otherwise.
    Outside the plugin folder either way: a reinstall replaces the plugin, and
    nobody expects it to take their bookmarks with it.
    """
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return os.path.join(local, "RhinoSpotter")
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                          ".local", "share")
    return os.path.join(xdg, "RhinoSpotter")


def open_path(path):
    """A file or folder, in whatever the desktop opens it with.

    Three systems, three calls: os.startfile exists only on Windows, macOS has
    `open`, a Linux desktop has xdg-open. A picture that will not open is a log
    line, never a raise - it is a convenience button on a window that has work
    to do.
    """
    try:
        if hasattr(os, "startfile"):               # Windows
            os.startfile(path)                     # noqa: S606
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return True
        subprocess.Popen(["xdg-open", str(path)])
        return True
    except (OSError, ValueError) as err:
        logger.warning(f"could not open {path}: {err}")
    try:
        return bool(webbrowser.open(pathlib.Path(path).as_uri()))
    except (ValueError, webbrowser.Error) as err:
        logger.warning(f"could not open {path} in a browser either: {err}")
        return False


def on_windows():
    """Whether the Win32 calls the overlay and the hotkeys need are there.

    Asked rather than sys.platform: what the callers depend on is ctypes.windll,
    and an interpreter that has the platform but not the library is the case
    that used to raise in the middle of a draw.
    """
    try:
        import ctypes
        ctypes.windll.user32                       # noqa: B018  the attribute is the test
        return True
    except (ImportError, AttributeError, OSError):
        return False
