r"""The JSON files of 4.1 and before, read into the database once.

    %LOCALAPPDATA%\RhinoSpotter\data\<System>.json               bodies
    %LOCALAPPDATA%\RhinoSpotter\cards\<System>\*.json            bookmarks
    %LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map N.json[.gz]  map points

Run at every start. The first run imports everything it can read and writes
db\migrate.done; every run after sees that file and returns before looking at
a single folder.

Nothing is deleted or moved: the files stay where they are.

A file that cannot be read is logged, listed in migrate.done, and does not stop
the rest. Only a database that cannot be written leaves no migrate.done - the
whole import is one transaction, and the next start tries again.

A row already in the database wins over its file: INSERT OR IGNORE, bookmarks
recognised by the file they came from. So a second run after a failed one
never duplicates or overwrites.

No tkinter. See rs_tests/test_migrate.py.
"""

import gzip
import json
import os
import sqlite3
from datetime import datetime, timezone

from rs_core import atomic, coverstore, database
from rs_core.logging import logger

DONE = "migrate.done"
STORE_VERSION = 1           # the only version store.py and coverstore.py ever wrote

# A value SQLite will not store - a list where a number goes, a missing body
# name. It skips that file. Anything else, a disk error, fails the import.
BAD_VALUE = (sqlite3.InterfaceError, sqlite3.ProgrammingError, sqlite3.IntegrityError,
             OverflowError, TypeError, ValueError)


def done_path(db=None):
    return os.path.join(os.path.dirname(db or database.PATH), DONE)


def run(root=None, db=None):
    """Import the JSON under `root` into `db`. {"imported": {...}, "kept": {...},
    "failed": [(path, reason), ...]}, or None when migrate.done is there."""
    marker = done_path(db)
    if os.path.exists(marker):
        return None
    root = root or database.ROOT
    result = {"imported": {"bodies": 0, "bookmarks": 0, "maps": 0},
              "kept": {"bodies": 0, "bookmarks": 0, "maps": 0},
              "failed": []}
    with database.connect(db) as conn:
        # The report is kept in the database too, committed with the import: a
        # migrate.done that failed to write after the commit is written again
        # from it, instead of a second import bringing deleted bookmarks back.
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (DONE,)).fetchone()
        if row is None:
            # Explicit, so the per-file savepoints nest inside one transaction
            # rather than each committing on release.
            conn.execute("BEGIN")
            _bodies(conn, os.path.join(root, "data"), result)
            _bookmarks(conn, os.path.join(root, "cards"), result)
            _maps(conn, os.path.join(root, "coverage"), result)
            when = datetime.now(timezone.utc).isoformat(timespec="seconds")
            lines = [f"migrated {when} from {root}"]
            lines += [f"{kind}: {count} imported, {result['kept'][kind]} already in the database"
                      for kind, count in result["imported"].items()]
            lines += [f"skipped {path}: {reason}" for path, reason in result["failed"]]
            report = "\n".join(lines) + "\n"
            conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (DONE, report))
    if row is not None:
        atomic.write_text(marker, row[0])
        return None
    database.changed()
    atomic.write_text(marker, report)
    for path, reason in result["failed"]:
        logger.warning(f"migrate: skipped {path}: {reason}")
    logger.info("migrate: " + "; ".join(lines[1:4]))
    return result


def _count(result, kind, inserted):
    result["imported" if inserted else "kept"][kind] += 1


def _one_file(conn, result, kind, path, write):
    """Run one file's inserts, all or none. `write()` returns a rowcount per
    row. A value SQLite will not store skips the file, not the import."""
    conn.execute("SAVEPOINT one_file")
    try:
        counts = write()
    except BAD_VALUE as err:
        conn.execute("ROLLBACK TO one_file")
        result["failed"].append((path, f"cannot be stored: {err}"))
        counts = []
    conn.execute("RELEASE one_file")
    for inserted in counts:
        _count(result, kind, inserted)


# A folder that is not there is nothing to import. One that is there and cannot
# be listed raises: the import fails, no migrate.done, and the next start tries
# again rather than calling it done without those files.
def _files(folder, suffix):
    try:
        return sorted(name for name in os.listdir(folder) if name.endswith(suffix))
    except FileNotFoundError:
        return []


def _folders(folder):
    try:
        return sorted(name for name in os.listdir(folder)
                      if os.path.isdir(os.path.join(folder, name)))
    except FileNotFoundError:
        return []


def _read(path):
    """A JSON file, gzipped or not. Raises on anything unreadable."""
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _bodies(conn, folder, result):
    for file in _files(folder, ".json"):
        path = os.path.join(folder, file)
        try:
            data = _read(path)
        except Exception as err:            # zlib.error and RecursionError too
            result["failed"].append((path, str(err)))
            continue
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            version = data.get("version") if isinstance(data, dict) else None
            result["failed"].append((path, f"version {version!r}, expected {STORE_VERSION}"))
            continue
        bodies = data.get("bodies")
        if not isinstance(bodies, list):
            result["failed"].append((path, "no list of bodies"))
            continue
        system = data.get("system") or file[:-5]
        address = data.get("system_address")
        good = []
        for body in bodies:
            if not isinstance(body, dict) or not body.get("name"):
                result["failed"].append((path, f"a body without a name: {body!r:.80}"))
                continue
            if address is not None:
                body = dict(body, system_address=body.get("system_address", address))
            good.append(body)

        def write():
            return [conn.execute(
                "INSERT OR IGNORE INTO bodies (system, name, system_address, body_id, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (system, body["name"], body.get("system_address"), body.get("body_id"),
                 json.dumps(body))).rowcount for body in good]
        _one_file(conn, result, "bodies", path, write)


def _bookmarks(conn, folder, result):
    for system_folder in _folders(folder):
        where = os.path.join(folder, system_folder)
        for file in _files(where, ".json"):
            path = os.path.join(where, file)
            try:
                record = _read(path)
            except Exception as err:
                result["failed"].append((path, str(err)))
                continue
            if not isinstance(record, dict) or not record.get("planet_name"):
                result["failed"].append((path, "not a bookmark: no planet_name"))
                continue
            if not record.get("system"):
                record["system"] = system_folder
            # The old reader found a card's PNG by the JSON's own name when the
            # record did not say; the database has no file name to go by.
            png = file[:-5] + ".png"
            if not record.get("card") and os.path.isfile(os.path.join(where, png)):
                record["card"] = png
            _one_file(conn, result, "bookmarks", path, lambda: [
                database.write_bookmark(conn, record, source=os.path.abspath(path))])


def _maps(conn, folder, result):
    for body_folder in _folders(folder):
        where = os.path.join(folder, body_folder)
        gzipped = _files(where, ".json.gz")
        # A plain .json beside a .json.gz of the same name: the gzipped one is newer.
        plain = [file for file in _files(where, ".json") if file + ".gz" not in gzipped]
        for file in gzipped + plain:
            path = os.path.join(where, file)
            name = file[:-len(".json.gz")] if file.endswith(".gz") else file[:-5]
            try:
                data = _read(path)
            except Exception as err:
                result["failed"].append((path, str(err)))
                continue
            if not isinstance(data, dict) or data.get("version") != coverstore.VERSION:
                version = data.get("version") if isinstance(data, dict) else None
                result["failed"].append((path, f"version {version!r}, "
                                               f"expected {coverstore.VERSION}"))
                continue
            data["body"] = data.get("body") or body_folder
            raw = gzip.compress(json.dumps(data, separators=(",", ":")).encode("utf-8"))
            _one_file(conn, result, "maps", path, lambda: [conn.execute(
                "INSERT OR IGNORE INTO maps (body, name, system_address, body_id, saved, data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (data["body"], name, data.get("system_address"), data.get("body_id"),
                 data.get("saved"), raw)).rowcount])


def leftovers(root=None, db=None):
    """[path, ...] of the old JSON files the database holds, and the stray .tmp
    files of the old writer - safe to delete. Empty until migrate.done is there.

    A file counts only when the database has what it holds, checked row by row:
    every body of a system file, the bookmark imported from that very file, the
    map of that body and name. So a database that was lost or replaced after
    the import deletes nothing.

    Kept out as well: a file migrate.done lists as skipped, one newer than
    migrate.done (written by an older plugin since), and every PNG (map
    pictures are still read; old card pictures were never imported).

    Raises OSError or sqlite3.Error when the folders or the database cannot be
    read.
    """
    marker = done_path(db)
    try:
        with open(marker, encoding="utf-8") as handle:
            report = handle.read()
        done_at = os.path.getmtime(marker)
    except FileNotFoundError:
        return []
    root = root or database.ROOT
    with database.connect(db) as conn:
        bodies = set(conn.execute("SELECT system, name FROM bodies"))
        sources = {row[0] for row in conn.execute(
            "SELECT source FROM bookmarks WHERE source IS NOT NULL")}
        maps = set(conn.execute("SELECT body, name FROM maps"))

    def held(path, kind, folder):
        if path.endswith(".tmp"):
            return True
        if kind == "cards":
            return os.path.abspath(path) in sources
        try:
            data = _read(path)
        except Exception:                    # unreadable never came in
            return False
        if not isinstance(data, dict):
            return False
        if kind == "data":
            system = data.get("system") or os.path.basename(path)[:-5]
            names = [body.get("name") for body in data.get("bodies") or []
                     if isinstance(body, dict)]
            return all((system, name) in bodies for name in names)
        name = os.path.basename(path).split(".json", 1)[0]
        return (data.get("body") or folder, name) in maps

    candidates = [(os.path.join(root, "data", file), "data", None)
                  for file in _files(os.path.join(root, "data"), ".json")]
    for kind in ("cards", "coverage"):
        top = os.path.join(root, kind)
        for sub in _folders(top):
            candidates += [(os.path.join(top, sub, file), kind, sub)
                           for file in _files(os.path.join(top, sub),
                                              (".json", ".json.gz", ".tmp"))]
    return [path for path, kind, folder in candidates
            if f"skipped {path}: " not in report and os.path.getmtime(path) <= done_at
            and held(path, kind, folder)]


def delete_leftovers(root=None, db=None):
    """Delete what leftovers() names, and the folders that leaves empty.
    (deleted, failed) path lists; a failure is logged."""
    deleted, failed = [], []
    for path in leftovers(root, db):
        try:
            os.remove(path)
            deleted.append(path)
        except OSError as err:
            logger.warning(f"migrate: could not delete {path}: {err}")
            failed.append(path)
    for folder in sorted({os.path.dirname(path) for path in deleted}, reverse=True):
        try:
            os.rmdir(folder)                # only when empty
        except OSError:
            pass
    return deleted, failed
