r"""The one database: bodies, bookmarks and minimap maps.

    %LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db

Three stores of JSON files, each with its own layout, became one file. A
question across systems - every monazite with six rigs - is one query rather
than a walk over every folder.

A connection per piece of work, opened and closed around it: 1.3 ms measured
with WAL, and three threads write (the bookmark worker, the debounce timer and
the panel), so no connection is ever shared between them.

Each row keeps the whole record as JSON beside the columns a lookup needs, so
a record comes back exactly as it went in.

No tkinter. See rs_tests/test_database.py.
"""

import contextlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from rs_core.logging import logger

ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                    or os.path.expanduser("~"), "RhinoSpotter")
DIR = os.path.join(ROOT, "db")
PATH = os.path.join(DIR, "rhinospotter.db")

# PRAGMA user_version. A later schema change reads it and upgrades.
SCHEMA_VERSION = 1
TIMEOUT_S = 5.0
BACKUPS_KEPT = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS bodies (
    system TEXT NOT NULL,
    name TEXT NOT NULL,
    system_address INTEGER,
    body_id INTEGER,
    data TEXT NOT NULL,
    PRIMARY KEY (system, name));
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    system TEXT,
    planet_name TEXT NOT NULL,
    system_address INTEGER,
    body_id INTEGER,
    commodity TEXT,
    location_index INTEGER,
    rigs INTEGER,
    depleted_at TEXT,
    data TEXT NOT NULL,
    source TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS bookmarks_system ON bookmarks (system);
CREATE TABLE IF NOT EXISTS maps (
    body TEXT NOT NULL,
    name TEXT NOT NULL,
    system_address INTEGER,
    body_id INTEGER,
    saved REAL,
    data BLOB NOT NULL,
    PRIMARY KEY (body, name));
"""

# Bumped after every committed bookmark change, so the minimap knows when to
# read them again. In-process only: nothing else writes bookmarks.
_revision = 0


@contextlib.contextmanager
def connect(path=None):
    """A connection for one piece of work: committed when the block ends,
    rolled back when it raises, closed either way."""
    path = path or PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=TIMEOUT_S)
    try:
        _prepare(conn, path)
        with conn:
            yield conn
    finally:
        conn.close()


def _prepare(conn, path):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version > SCHEMA_VERSION:
        logger.warning(f"{path} is schema {version}, this plugin knows {SCHEMA_VERSION}")


def changed():
    global _revision
    _revision += 1


def revision():
    return _revision


BOOKMARK_COLUMNS = ("system", "planet_name", "system_address", "body_id", "commodity",
                    "location_index", "rigs", "depleted_at")


def write_bookmark(conn, record, id=None, source=None):
    """Insert a bookmark, or replace row `id`. The row id, or None when
    `source` was imported already. A row that was deleted meanwhile is
    inserted again, as its file used to be. Call changed() after the
    commit."""
    values = [record.get(column) for column in BOOKMARK_COLUMNS] + [json.dumps(record)]
    if id is not None:
        sets = ", ".join(f"{column} = ?" for column in BOOKMARK_COLUMNS)
        if conn.execute(f"UPDATE bookmarks SET {sets}, data = ? WHERE id = ?",
                        values + [id]).rowcount:
            return id
    columns = ", ".join(BOOKMARK_COLUMNS)
    marks = ", ".join("?" * (len(BOOKMARK_COLUMNS) + 2))
    cursor = conn.execute(f"INSERT OR IGNORE INTO bookmarks ({columns}, data, source) "
                          f"VALUES ({marks})", values + [source])
    return cursor.lastrowid if cursor.rowcount else None


def backup(path=None, keep=BACKUPS_KEPT):
    r"""A copy of the database in db\backups\, the newest `keep` kept. The
    copy's path, or None. Through a temp file, so a failed copy never pushes
    a good one out."""
    path = path or PATH
    if not os.path.isfile(path):
        return None
    folder = os.path.join(os.path.dirname(path), "backups")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = os.path.join(folder, f"rhinospotter-{stamp}.db")
    try:
        os.makedirs(folder, exist_ok=True)
        with contextlib.closing(sqlite3.connect(path, timeout=TIMEOUT_S)) as source, \
                contextlib.closing(sqlite3.connect(target + ".tmp")) as copy:
            # Only a copy worth keeping may push an older one out: an emptied or
            # broken database backed up twice would leave nothing to go back to.
            check = source.execute("PRAGMA quick_check").fetchone()[0]
            rows = sum(source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                       for table in ("bodies", "bookmarks", "maps"))
            if check != "ok" or not rows:
                raise sqlite3.DatabaseError(f"not backed up: quick_check {check}, {rows} rows")
            source.backup(copy)
        os.replace(target + ".tmp", target)
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not back up {path}: {err}")
        with contextlib.suppress(OSError):
            os.remove(target + ".tmp")
        return None
    copies = sorted(name for name in os.listdir(folder)
                    if name.startswith("rhinospotter-") and name.endswith(".db"))
    for name in copies[:-keep]:
        try:
            os.remove(os.path.join(folder, name))
        except OSError as err:
            logger.warning(f"could not remove old backup {name}: {err}")
    return target
