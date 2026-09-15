r"""A system you have already seen, kept, so you do not have to honk it twice.

EDMC replays the journal file it is watching and nothing older. Every game
restart opens a new file, so a system honked last week is gone from the
plugin's view even though the commander scanned it properly at the time.

So each system's bodies go into the database and are read back when you
arrive there again. No network, no EDSM: this is the commander's own scan data
going to disk and coming back. A row per body, the body itself as JSON.

    %LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db    - rs_core/database.py

Outside the plugin folder: a reinstall replaces the plugin, and nobody expects
it to take their scans with it. The JSON files older versions wrote under
data\ are read in once by rs_core/migrate.py.

Written on every change rather than when you leave. A system you never leave -
because the game crashed, or EDMC was closed on the pad - is exactly the one
you would rather not scan twice.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_store.py.
"""

import json
import sqlite3
import threading

from rs_core import database
from rs_core.logging import logger


def save(system, bodies, db=None):
    """Write one system, replacing what was there. Returns the database path,
    or None if it could not be written.

    One transaction: EDMC can be closed at any moment, and half a system that
    still reads would be worse than none - it would look like a system with
    three bodies in it.
    """
    if not system or not bodies:
        return None
    rows = [(system, body["name"], body.get("system_address"), body.get("body_id"),
             json.dumps(body)) for body in bodies]
    try:
        with database.connect(db) as conn:
            conn.execute("DELETE FROM bodies WHERE system = ?", (system,))
            conn.executemany("INSERT OR REPLACE INTO bodies "
                             "(system, name, system_address, body_id, data) "
                             "VALUES (?, ?, ?, ?, ?)", rows)
        return db or database.PATH
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not cache {system}: {err}")
        return None


def load(system, db=None):
    """The bodies cached for that system, or [].

    Every failure is the same empty answer. A cache that cannot be read is a
    cache that is not there, and the panel says "honk the system" either way.
    """
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT system_address, data FROM bodies WHERE system = ? "
                                "ORDER BY rowid", (system,)).fetchall()
        bodies = [json.loads(data) for _, data in rows]
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning(f"could not read the cache of {system}: {err}")
        return []
    # The address belongs to the system: a body scanned before it was known
    # takes it from the others, which is how the register takes it in.
    address = next((row[0] for row in rows if row[0] is not None), None)
    if address is not None:
        bodies = [dict(body, system_address=body.get("system_address", address))
                  if isinstance(body, dict) else body for body in bodies]
    return bodies


def systems(db=None):
    """Every system name in the cache, for a count in the panel."""
    try:
        with database.connect(db) as conn:
            return [row[0] for row in conn.execute(
                "SELECT DISTINCT system FROM bodies ORDER BY system")]
    except (sqlite3.Error, OSError):
        return []


# How long a burst of changes is allowed to run before it is written. An FSS
# sweep emits a scan every few tenths of a second, so two seconds is past the
# end of a quick one and short enough that a crash costs the tail of a honk
# rather than the honk.
DEBOUNCE_S = 2.0


class Debounced:
    """`save`, with a burst of them written once.

    A honk is one change per body, and every one of them rewrites the whole
    system: 45 landable bodies in Col 285 Sector LM-V d2-73 meant 45
    writes to end up with one system. At 1.1 ms a write that is 50 ms, so
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
