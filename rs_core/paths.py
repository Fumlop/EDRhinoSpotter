r"""Resolves the Elite Dangerous journal folder.

The default path is only a fallback: a moved folder, a synced profile, a Steam
library elsewhere or an install under Proton is already resolved by EDMC, so
EDMC is asked first. See journal_dir().

EDMC's `monitor` and `config` are read from sys.modules, where EDMC put
them, so the module imports in a bare interpreter.

No tkinter. Tests in rs_tests/test_paths.py and rs_e2etest/paths_e2e.py.
"""

import os
import sys

# Default install path, expanded only as the last fallback.
WINDOWS_JOURNAL = r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous"
# Below the Saved Games known folder, wherever Windows has it.
GAME_SUBDIR = os.path.join("Frontier Developments", "Elite Dangerous")
# FOLDERID_SavedGames.
SAVED_GAMES_ID = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"


def _saved_games():
    """The Saved Games known folder (SHGetKnownFolderPath), or None off
    Windows. Follows a folder moved in Explorer's Location tab, which
    %USERPROFILE%\\Saved Games does not."""
    try:
        import ctypes
        from ctypes import wintypes
        guid = (ctypes.c_byte * 16)()
        ctypes.oledll.ole32.CLSIDFromString(SAVED_GAMES_ID, ctypes.byref(guid))
        found = wintypes.LPWSTR()
        shell32 = ctypes.WinDLL("shell32")
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                                 ctypes.POINTER(wintypes.LPWSTR)]
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(found)):
            return None
        try:
            return found.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(found)
    except (ImportError, AttributeError, OSError):
        return None


def journal_dir():
    """Path to the folder holding Status.json and the journal files.

    Looked up once a start. Inside EDMC the answer is kept only once the
    monitor has one: the plugin loads ~1.4 s before the monitor starts, and
    what steps 2-5 say before then is kept by nobody.
    """
    global _found
    if _found is None:
        path, final = _lookup()
        if not final:
            return path
        _found = path
    return _found


_found = None


def _lookup():
    """(path, final). Tried in order:

    1. monitor.currentdir - the folder EDMC is watching; already resolved for
       platform, default and override. Final.
    2. the journaldir setting - set only when the commander typed a path.
    3. config.default_journal_dir - EDMC's own default, the known folder.
    4. the Saved Games known folder.
    5. WINDOWS_JOURNAL, expandvars'd.

    2-5 are final outside EDMC (no `monitor` module), where nothing changes.
    EDMC's modules are read from sys.modules, where EDMC put them.
    """
    edmc = sys.modules.get("monitor")
    try:
        current = getattr(getattr(edmc, "monitor", None), "currentdir", None)
        if current:
            return os.path.expanduser(str(current)), True
    except (AttributeError, OSError):
        pass
    return _fallback(), edmc is None


def _fallback():
    """Steps 2-5 of _lookup()."""
    try:
        config = getattr(sys.modules.get("config"), "config", None)
        setting = config.get_str("journaldir") if config is not None else None
        if setting:
            return os.path.expanduser(setting)
        default = getattr(config, "default_journal_dir", None)
        if default:
            return os.path.expanduser(str(default))
    except (AttributeError, OSError):
        pass
    saved = _saved_games()
    if saved:
        return os.path.join(saved, GAME_SUBDIR)
    return os.path.expandvars(WINDOWS_JOURNAL)
