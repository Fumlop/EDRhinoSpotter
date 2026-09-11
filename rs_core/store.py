"""A system you have already seen, kept, so you do not have to honk it twice.

EDMC replays the journal file it is watching and nothing older. Every game
restart opens a new file, so a system honked last week is gone from the
plugin's view even though the commander scanned it properly at the time.

So each system is written out as one small JSON file and read back when you
arrive there again. No network, no EDSM, no database: this is the commander's
own scan data going to disk and coming back.

    <plugin>/data/systems/<System>.json

One file per system rather than a folder per body. A body is a handful of
fields; a folder holding four of them costs four inode reads to answer one
question about the system.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_store.py.
"""

import json
import os
import tempfile

from rs_core.logging import logger

STORE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "systems")
BAD = r'<>:"/\|?*'
VERSION = 1


def safe_name(system):
    r"""A system name Windows will accept as a filename.

    Real names carry characters Explorer refuses - "Col 285 Sector KM-V d2-36"
    is fine, but a name with a colon in it is not, and one bad system must not
    take the whole cache down.
    """
    cleaned = "".join("_" if ch in BAD else ch for ch in (system or "")).strip()
    return cleaned or "unknown"


def path_for(system, root=STORE_ROOT):
    return os.path.join(root, safe_name(system) + ".json")


def save(system, bodies, root=STORE_ROOT):
    """Write one system. Returns the path, or None if it could not be written.

    Written to a temporary file and moved into place: EDMC can be closed at any
    moment, and a half-written cache file that still parses would be worse than
    none - it would look like a system with three bodies in it.
    """
    if not system or not bodies:
        return None
    try:
        os.makedirs(root, exist_ok=True)
        target = path_for(system, root)
        payload = {"version": VERSION, "system": system, "bodies": bodies}
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root,
                                             suffix=".tmp", delete=False)
        try:
            json.dump(payload, handle, indent=1)
        finally:
            handle.close()
        os.replace(handle.name, target)
        return target
    except OSError as err:
        logger.debug(f"could not cache {system}: {err}")
        return None


def load(system, root=STORE_ROOT):
    """The bodies cached for that system, or [].

    Every failure is the same empty answer. A cache that cannot be read is a
    cache that is not there, and the panel says "honk the system" either way.
    """
    try:
        with open(path_for(system, root), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if data.get("version") != VERSION:
        # A shape from an older plugin. Dropping it costs one honk; guessing at
        # it costs a wrong answer that looks right.
        return []
    bodies = data.get("bodies")
    return bodies if isinstance(bodies, list) else []


def systems(root=STORE_ROOT):
    """Every system name in the cache, for a count in the panel."""
    try:
        return sorted(name[:-5] for name in os.listdir(root) if name.endswith(".json"))
    except OSError:
        return []
