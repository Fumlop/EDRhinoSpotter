"""What another program may read out of RhinoSpotter, and the promise about it.

Two people asked in the same week: one writing an EDMC plugin, one writing a
separate application. Both were reading the plugin's own storage, which is how
they found out the hard way that it moved from JSON files to a database between
4.4.3 and 5.0. This module is the thing that does not move.

    import sys; sys.path.append(r"%LOCALAPPDATA%\\EDMarketConnector\\plugins\\RhinoSpotter")
    import rs_api

    rs_api.bookmarks()                    # every bookmark the commander made
    rs_api.bookmarks(system="Aramo")      # one system
    rs_api.bodies()                       # the bodies that carry any
    rs_api.explored("Aramo A 1")          # how much of that body has been driven

Inside EDMC or outside it, same call: nothing here imports EDMC, tkinter or
PIL, and the database is opened **read-only**, so a reader can neither lock the
plugin out nor change what it reads.

The promise: keys are added, never removed or repurposed, for as long as
`SCHEMA` reads 1. A key that has to change meaning gets a new name and the old
one keeps answering. If that ever becomes impossible, SCHEMA goes to 2 and this
docstring says what moved.

See docs/API.md for the fields, and rs_tests/test_api.py for what is checked.
"""

import json
import os
import sqlite3

from rs_core import database, paths
from rs_core.update import VERSION

# The shape of what comes back. Additive changes leave it alone.
SCHEMA = 1

# The keys a bookmark answers with. Everything the plugin recorded is in
# `raw` beside them - the readings the game gave that day, whatever they were.
FIELDS = ("system", "body", "location", "material", "rigs", "latitude", "longitude",
          "heading", "amount", "density", "depleted", "depleted_at", "marked_at",
          "commander", "id")


def version():
    """The plugin's version, so a reader can say what it read."""
    return VERSION


def database_path():
    """Where the storage is, in case a reader wants to watch it for changes."""
    return database.PATH


def data_dir():
    """The plugin's folder: the database, the map pictures, the backups."""
    return paths.data_root()


def bookmarks(system=None, body=None, path=None):
    """Every bookmark, or those of one system or one body, oldest first.

    A bookmark is a place a commander stood with the rigs down: where it is,
    what it was mining, how big the deposit read, and whether it has since been
    worked out. `depleted` is the flag to draw on; `depleted_at` is when it was
    marked, which is what any research into deposits reforming needs.

    Returns a list of dicts. Unreadable rows are skipped rather than raised on:
    one broken row is not a reason to hand back nothing.
    """
    where, values = [], []
    if system:
        where.append("system = ?")
        values.append(system)
    if body:
        where.append("planet_name = ?")
        values.append(body)
    query = "SELECT id, data FROM bookmarks"
    if where:
        query += " WHERE " + " AND ".join(where)
    found = []
    for id, data in _rows(query + " ORDER BY id", values, path):
        record = _record(data)
        if record is None:
            continue
        found.append(_bookmark(id, record))
    return found


def bodies(system=None, path=None):
    """The bodies that carry bookmarks: name, system, how many, and how many of
    those are worked out. The cheap question - "is there anything of mine on
    this body" - without reading every bookmark on it."""
    query = ("SELECT system, planet_name, count(*), "
             "       sum(CASE WHEN depleted_at IS NOT NULL THEN 1 ELSE 0 END) "
             "FROM bookmarks")
    values = []
    if system:
        query += " WHERE system = ?"
        values.append(system)
    query += " GROUP BY system, planet_name ORDER BY system, planet_name"
    return [{"system": row[0], "body": row[1], "bookmarks": row[2],
             "depleted": row[3] or 0}
            for row in _rows(query, values, path)]


def explored(body, path=None):
    """How much of one body has been driven, or None when no map was saved.

    This is the part of the plugin that no radar has: the ground inside scanner
    range of the SRV's track, as square kilometres, per saved map. A reader that
    wants the picture itself can take `maps` and open the PNGs beside the
    database - see docs/API.md.

    Needs Pillow, because the painted area is a mask. Without it, the counts
    come back and `km2` is None rather than the call failing.
    """
    maps = [name for name, _ in _maps(body, path)]
    if not maps:
        return None
    summary = {"body": body, "maps": maps, "km2": None, "locations": None}
    try:
        from rs_core import coverage                # Pillow lives down here
    except ImportError:
        return summary
    painted, locations = 0.0, set()
    for name, data in _maps(body, path):
        try:
            cover = coverage.Coverage.from_dict(body, data, name=name)
        except (TypeError, ValueError, KeyError):
            continue
        if cover is None:
            continue
        painted += cover.painted_km2()
        if cover.location is not None:
            locations.add(cover.location)
    summary["km2"] = round(painted, 1)
    summary["locations"] = sorted(locations)
    return summary


# ------------------------------------------------------------------ the parts


def _bookmark(id, record):
    """One row, as the documented fields plus everything it actually holds."""
    return {
        "system": record.get("system"),
        "body": record.get("planet_name"),
        "location": record.get("location_index"),
        "material": record.get("commodity"),
        "rigs": record.get("rigs"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "heading": record.get("heading"),
        "amount": record.get("amount"),
        "density": record.get("density"),
        "depleted": bool(record.get("depleted_at")),
        "depleted_at": record.get("depleted_at"),
        "marked_at": record.get("marked_at"),
        "commander": record.get("commander"),
        "id": id,
        "raw": record,
    }


def _record(data):
    try:
        record = json.loads(data)
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("planet_name") else None


def _maps(body, path=None):
    """(name, dict) of every saved map on that body, newest name last."""
    import gzip
    found = []
    for name, blob in _rows("SELECT name, data FROM maps WHERE body = ? ORDER BY name",
                            [body], path):
        try:
            found.append((name, json.loads(gzip.decompress(blob).decode("utf-8"))))
        except (OSError, ValueError, TypeError):
            continue
    return found


def _rows(query, values, path=None):
    """Read-only, and quiet about a database that is not there yet.

    mode=ro rather than a plain connect: a reader must not be able to create an
    empty database beside the real one, lock the plugin out of its own writes,
    or upgrade a schema it does not own.
    """
    file = path or database.PATH
    if not os.path.isfile(file):
        return []
    try:
        with sqlite3.connect(f"file:{file}?mode=ro", uri=True, timeout=5.0) as conn:
            return conn.execute(query, values).fetchall()
    except sqlite3.Error:
        return []
