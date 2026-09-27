r"""The minimap's painted ground, kept, so an EDMC restart does not wipe it.

    %LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db      the points, table maps
    %LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map 1.png

A row per map, keyed by body and name. A body can hold several maps - two
mining locations more than 10 km apart are two - and one row each means a save
never has to read and merge the others.

Not a picture: the points the SRV painted new ground at, as latitude and
longitude. Loading repaints the mask from them - 270 points from an hour's
drive, 11 ms. A point is still right if SCAN_RADIUS_M or the mask resolution
changes; a picture would not be.

Gzipped: 270 points are 7.2 KB of JSON and 2.4 KB compressed.

The PNG is for the commander to look at, so it stays a file. Nothing reads it
back. The .json.gz files older versions wrote beside it are read in once by
rs_core/migrate.py.

No tkinter. See rs_tests/test_coverstore.py.
"""

import gzip
import io
import json
import os
import sqlite3
import time

from rs_core import atomic, database, names
from rs_core.logging import logger

# The pictures. The points are in the database.
ROOT = os.path.join(database.ROOT, "coverage")
VERSION = 1


def folder(body, root=None):
    return os.path.join(root or ROOT, names.safe(body))


def maps(body, db=None, system_address=None):
    """[(name, data), ...] for every map saved on that body.

    A map that cannot be read, or is from another version, is skipped and
    logged - one broken map must not cost the others.

    A name is only unique inside its system. With `system_address` given, a
    map that names a different one is a body of the same name elsewhere and is
    left out; a map from before the address was kept names none and stays in.
    """
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT name, data FROM maps WHERE body = ? ORDER BY name",
                                (body,)).fetchall()
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"minimap: could not read the maps of {body}: {err}")
        return []
    found = []
    for name, raw in rows:
        try:
            data = json.loads(gzip.decompress(raw).decode("utf-8"))
        except Exception as err:        # zlib.error and RecursionError too
            logger.warning(f"minimap: skipping {name} on {body}: {err}")
            continue
        if not isinstance(data, dict) or data.get("version") != VERSION:
            logger.warning(f"minimap: skipping {name} on {body}: not version {VERSION}")
            continue
        theirs = data.get("system_address")
        if system_address is not None and theirs is not None and theirs != system_address:
            logger.debug(f"minimap: {name} on {body} is in system {theirs}, not {system_address}")
            continue
        found.append((name, data))
    return found


def next_name(body, db=None, root=None):
    """'map N', one past the highest number on that body - in the database or
    as a picture, so a new map never overwrites an old one's PNG."""
    stems = []
    try:
        with database.connect(db) as conn:
            stems = [row[0] for row in conn.execute("SELECT name FROM maps WHERE body = ?",
                                                    (body,))]
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"minimap: could not read the map names of {body}: {err}")
    try:
        stems += [file.split(".", 1)[0] for file in os.listdir(folder(body, root))]
    except OSError:
        pass
    taken = [0] + [int(stem[4:]) for stem in stems
                   if stem.startswith("map ") and stem[4:].isdigit()]
    return f"map {max(taken) + 1}"


def save(body, name, data, db=None):
    """Write one map, gzipped, replacing one of that name. The database path,
    or None."""
    # `saved` picks between two maps that both reach a launch - see
    # coverage._pick_saved.
    payload = dict(data, version=VERSION, body=body, saved=round(time.time(), 3))
    raw = gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    try:
        with database.connect(db) as conn:
            conn.execute("INSERT OR REPLACE INTO maps "
                         "(body, name, system_address, body_id, saved, data) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (body, name, payload.get("system_address"), payload.get("body_id"),
                          payload["saved"], raw))
        return db or database.PATH
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"minimap: could not save {name} on {body}: {err}")
        return None


def save_png(body, name, image, root=None):
    """The map as a picture. The path, or None."""
    try:
        where = folder(body, root)
        os.makedirs(where, exist_ok=True)
        target = os.path.join(where, name + ".png")
        # Through a temp file: EDMC closing mid-save or two
        # docks close together must not leave half a picture.
        picture = io.BytesIO()
        image.save(picture, "PNG")
        atomic.write_bytes(target, picture.getvalue())
        return target
    except (OSError, ValueError) as err:
        logger.warning(f"minimap: could not save the picture of {name} on {body}: {err}")
        return None


def latest_png(body, root=None):
    """The path of the map picture on that body written last, or None."""
    where = folder(body, root)
    try:
        pictures = [os.path.join(where, f) for f in os.listdir(where) if f.endswith(".png")]
        return max(pictures, key=os.path.getmtime) if pictures else None
    except OSError:
        return None


def usage(db=None, root=None):
    """(maps, bytes) over everything saved - points and pictures - for the
    settings tab."""
    count = size = 0
    try:
        with database.connect(db) as conn:
            count, size = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(data)), 0) FROM maps").fetchone()
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"minimap: could not count the saved maps: {err}")
    for where, _, files in os.walk(root or ROOT):
        for file in files:
            if file.endswith(".png"):
                try:
                    size += os.path.getsize(os.path.join(where, file))
                except OSError:
                    pass
    return count, size
