r"""A system you have already seen, kept, so you do not have to honk it twice.

EDMC replays the journal file it is watching and nothing older. Every game
restart opens a new file, so a system honked last week is gone from the
plugin's view even though the commander scanned it properly at the time.

So each system is written out as one small JSON file and read back when you
arrive there again. No network, no EDSM, no database: this is the commander's
own scan data going to disk and coming back.

    %LOCALAPPDATA%\RhinoSpotter\data\<System>.json

Beside the cards, and outside the plugin folder for the same reason they are:
a reinstall replaces the plugin, and nobody expects it to take their scans
with it.

One file per system rather than a folder per body. A body is a handful of
fields; a folder holding four of them costs four directory reads to answer one
question about the system.

Written on every change rather than when you leave. A system you never leave -
because the game crashed, or EDMC was closed on the pad - is exactly the one
you would rather not scan twice.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_store.py.
"""

import json
import os
import threading

from rs_core import atomic, names
from rs_core.logging import logger

# Beside the cards, and outside the plugin folder for the same reason: scans
# outlive a plugin reinstall, and %LOCALAPPDATA% is somewhere Explorer opens
# without hunting for it.
STORE_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "data")
VERSION = 1


def safe_name(system):
    r"""A system name Windows will accept as a filename.

    The same rule the cards folder uses - rs_core/names.py. It has to be the
    same one: a system that is safe here and not there is a cache that cannot
    be matched to the cards beside it.
    """
    return names.safe(system)


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
        atomic.write_text(target, json.dumps(payload, indent=1))
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


# How long a burst of changes is allowed to run before it is written. An FSS
# sweep emits a scan every few tenths of a second, so two seconds is past the
# end of a quick one and short enough that a crash costs the tail of a honk
# rather than the honk.
DEBOUNCE_S = 2.0


class Debounced:
    """`save`, with a burst of them written once.

    A honk is one change per body, and every one of them rewrote the whole
    system file: 45 landable bodies in Col 285 Sector LM-V d2-73 meant 45
    writes to end up with one 5 KB file. At 1.1 ms a write that is 50 ms, so
    this is not about the clock - it is about not rewriting a file forty-five
    times to say the same thing.

    The timer starts on the first change and is **not** restarted by the ones
    after it. A burst longer than the delay is written every `delay` seconds
    rather than held back until it stops: the point of writing during a honk
    is that the honk is exactly what you do not want to do twice, and a
    debounce that keeps resetting would hold the whole sweep in memory until
    it ended.

    What a hard crash costs is the last `delay` seconds of scanning. EDMC
    closing normally costs nothing - `flush()` is called at plugin_stop.

    No tkinter: a daemon timer thread rather than Tk's `after`, so this can be
    checked without a display and used by anything holding a Register. See
    rs_tests/test_store.py.
    """

    def __init__(self, delay=DEBOUNCE_S, write=save):
        self.delay = delay
        self._write = write
        self._lock = threading.Lock()
        self._timer = None
        self._pending = None

    def __call__(self, *args, **kwargs):
        """Take a change. Drops in wherever `save` did."""
        with self._lock:
            self._pending = (args, kwargs)
            if self._timer is None:
                self._timer = threading.Timer(self.delay, self.flush)
                self._timer.daemon = True
                self._timer.start()

    def flush(self):
        """Write what is waiting, now. Returns what `save` returned, or None.

        Safe to call with nothing pending, and safe to call from the timer it
        cancels - cancelling a timer that is already running does nothing.
        """
        with self._lock:
            timer, self._timer = self._timer, None
            pending, self._pending = self._pending, None
        if timer is not None:
            timer.cancel()
        if pending is None:
            return None
        args, kwargs = pending
        return self._write(*args, **kwargs)
