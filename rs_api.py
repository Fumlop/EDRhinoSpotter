r"""What another program may read out of RhinoSpotter, and the promise about it.

Two people asked in the same week: one writing an EDMC plugin, one writing a
separate application. Both were reading the plugin's own storage, which is how
they found out the hard way that it moved from JSON files to a database. This
module is the thing that does not move.

    import sys
    sys.path.append(r"%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter")
    import rs_api

    rs_api.bookmarks()                    # every bookmark the commander made
    rs_api.bookmarks(system="Aramo")      # one system
    rs_api.bodies()                       # the bodies that carry any
    rs_api.revision()                     # changes when the bookmarks do

Inside EDMC or outside it, same call. Nothing here imports EDMC, tkinter or
Pillow, and every call is read-only: a reader cannot lock the plugin out, change
anything, or create a database by reading before the commander has flown.

Four calls, because that is what was asked for. There is no permission system in
here: the file sits in the commander's own folder and anything that can run this
can read it, so a flag saying otherwise would be a lie in code. What a tool does
with somebody's mining coordinates is the tool's to declare and the commander's
to judge.

See docs/API.md for the fields.
"""

import json
import os
import sqlite3
import zlib

from rs_core import database
from rs_core.update import VERSION

# The shape of what comes back. While this reads 1, keys are added, never
# removed and never repurposed.
SCHEMA = 1


def version():
    """The plugin's version, so a reader can say what it read."""
    return VERSION


def bookmarks(system=None, body=None, path=None):
    """Every bookmark, or those of one system or one body, oldest first.

    A bookmark is a place a commander stood with the rigs down: where it is,
    what it was mining, how big the deposit read, and whether it has since been
    worked out. `depleted` is the flag to draw on; `depleted_at` is when it was
    marked, which is what any research into deposits reforming needs.

    Unreadable rows are skipped rather than raised on: one broken row is not a
    reason to hand back nothing.
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
        if record is not None:
            found.append(_bookmark(id, record))
    return found


def bodies(system=None, path=None):
    """The bodies that carry bookmarks: name, system, how many, and how many of
    those are worked out. The cheap question - is there anything of mine on this
    body - without reading every bookmark on it."""
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


def revision(path=None):
    """A number that changes when the bookmarks do. Poll it to know when to read
    again.

    Read from the database, not from a counter in memory: a counter belongs to
    the process that did the writing, so a separate application polling one gets
    the same value for ever and never refreshes. This counts the rows and takes
    the highest id and the latest stored record, so an insert, a delete, a
    depleted flip and an edit each move it.
    """
    rows = _rows("SELECT count(*), coalesce(max(id), 0), "
                 "       coalesce(max(coalesce(depleted_at, '')), ''), "
                 "       coalesce(max(data), '') FROM bookmarks", [], path)
    if not rows:
        return 0
    return zlib.crc32("|".join(str(value) for value in rows[0]).encode("utf-8"))


# ------------------------------------------------------------------ the parts


def _bookmark(id, record):
    """One row, as the documented fields. Whatever the plugin stores beside them
    is its own business, and it has changed twice already."""
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
    }


def _record(data):
    try:
        record = json.loads(data)
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("planet_name") else None


def _rows(query, values, path=None):
    """Read-only, and quiet about a database that is not there yet.

    mode=ro rather than a plain connect: rs_core.database.connect makes the
    folder, the file and the schema, which is right for the plugin and wrong for
    a reader - a tool that looks before the commander has ever flown would leave
    an empty database behind for the plugin to find.
    """
    file = path or database.PATH
    if not os.path.isfile(file):
        return []
    try:
        with sqlite3.connect(f"file:{file}?mode=ro", uri=True, timeout=5.0) as conn:
            return conn.execute(query, values).fetchall()
    except sqlite3.Error:
        return []
