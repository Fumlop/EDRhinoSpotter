"""Which bodies in a system you have already marked.

Read from the bookmarks spotcard writes into the database - rs_core/database.py.

No tkinter and no PIL, so it can be checked without EDMC or a display. See
rs_tests/test_cards.py.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

from rs_core import database, guide
from rs_core.logging import logger
from rs_core.spotcard import card_dir

# A new bookmark this close to one for the same material on the same body is
# the same deposit read again - on leaving, say, with Amount gone from High to
# Low - and updates it instead of adding a second. The distance is the largest
# patch assumed on flat ground: deposit.MAX_RIGS positions, six round one in
# the middle at the 76 m rig spacing, is a circle of 76 / (2 sin(pi/6)) = 76.0 m;
# with 10 % on top that is 83.6 m. Kept at a round 100 m: it was derived for
# eight positions and the slack costs nothing.
SAME_SPOT_M = 100.0

# Bookmarks already reported as unreadable. The minimap reads them again on
# every change, and one broken row is one line in the log, not one a change.
_warned = set()


def materials_marked(db=None):
    """Every material the commander has a bookmark for, lowercased.

    One indexed column, no JSON to parse. The panel asks this when it fills its
    dropdown: a material somebody has already stood on stays pickable whatever
    it pays, because nearby() matches a second mark to the first one on the
    name. Drop the name from the dropdown and that bookmark can never be marked
    again - the re-mark lands beside it as a duplicate instead of updating it.

    A database that cannot be read is logged and empty: the filter then does
    what it would have done on its own.
    """
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT DISTINCT commodity FROM bookmarks "
                                "WHERE commodity IS NOT NULL").fetchall()
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not read which materials are bookmarked: {err}")
        return set()
    return {name.lower() for name, in rows if name}


def for_system(system, db=None, quiet=True):
    """Every bookmark marked in that system, in the order they were made.

    Each record carries its row as `id`. Older versions wrote a PNG card beside
    the bookmark; that card's path is kept in `path` when it is still there,
    so Delete takes it too, and None otherwise.

    A database that cannot be read is logged and [] - or, with quiet=False,
    raised, for a caller that must not take it for "no bookmarks".
    """
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT id, data FROM bookmarks WHERE system = ? ORDER BY id",
                                (system,)).fetchall()
    except (sqlite3.Error, OSError) as err:
        if not quiet:
            raise
        logger.warning(f"could not read the bookmarks of {system}: {err}")
        return []

    found = []
    for id, data in rows:
        try:
            record = json.loads(data)
        except ValueError as err:
            if id not in _warned:
                _warned.add(id)
                logger.warning(f"skipping unreadable bookmark {id} in {system}: {err}")
            continue
        if not isinstance(record, dict) or not record.get("planet_name"):
            continue
        card = os.path.join(card_dir(system), record["card"]) if record.get("card") else None
        record["path"] = card if card and os.path.isfile(card) else None
        record["id"] = id
        found.append(record)
    return found


def delete(record, db=None):
    """Remove a bookmark: its row, and an old card's PNG if it has one.

    True when something was removed. A PNG that is already gone is the state
    the caller asked for and not a failure; one that will not go - open in a
    viewer, on a read-only folder - is, says so, and leaves the bookmark in
    place rather than the list claiming it is deleted.
    """
    removed = False
    if record.get("path"):
        try:
            os.remove(record["path"])
            removed = True
        except FileNotFoundError:
            pass
        except OSError as err:
            logger.warning(f"could not delete {record['path']}: {err}")
            return False
    if record.get("id") is not None:
        try:
            with database.connect(db) as conn:
                removed = conn.execute("DELETE FROM bookmarks WHERE id = ?",
                                       (record["id"],)).rowcount > 0 or removed
        except (sqlite3.Error, OSError) as err:
            logger.warning(f"could not delete bookmark {record['id']}: {err}")
            return False
        database.changed()
    return removed


def set_depleted(record, depleted, when=None, db=None):
    """Mark a bookmark as mined out, or take the mark off. True when written.

    Written into the bookmark as `depleted_at` - when it was marked, not a
    yes/no - so the day the community knows how long a patch takes to come
    back, the time is already there to count from. No mark, no key.
    The record in hand is updated to match.

    Depleted also closes the open yield cycle; the next ton refined there opens
    the next one.
    """
    # Imported here: rs_core.yields reads bookmarks through this module.
    from rs_core import yields
    if record.get("id") is None:
        return False
    if depleted and db is None:
        yields.TALLY.flush()    # pending tons belong in the cycle being closed
    try:
        with database.connect(db) as conn:
            row = conn.execute("SELECT data FROM bookmarks WHERE id = ?",
                               (record["id"],)).fetchone()
            if row is None:
                logger.warning(f"could not mark bookmark {record['id']} depleted: it is gone")
                return False
            data = json.loads(row[0])
            if depleted:
                data["depleted_at"] = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
                yields.close(data, data["depleted_at"])
            else:
                data.pop("depleted_at", None)
            database.write_bookmark(conn, data, record["id"])
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning(f"could not mark bookmark {record['id']} depleted: {err}")
        return False
    database.changed()
    if depleted:
        record["depleted_at"] = data["depleted_at"]
        record["yield"] = data.get("yield")
    else:
        record.pop("depleted_at", None)
    return True


def same_body(record, name, system_address=None, body_id=None):
    """Whether a bookmark is on that body. By the game's IDs when both sides
    have them - a name is only unique inside its system - by name otherwise:
    bookmarks from before the IDs were kept have none."""
    theirs = record.get("system_address")
    if system_address is not None and theirs is not None:
        if theirs != system_address:
            return False
        if body_id is not None and record.get("body_id") is not None:
            return record["body_id"] == body_id
    return record.get("planet_name") == name


def nearby(spot, db=None, within=SAME_SPOT_M):
    """The bookmark a new mark updates, or None: same body, same material,
    within `within` metres, the nearest one. None too when the mark carries no
    planet radius, since without it there is no distance to measure."""
    radius = spot.get("planet_radius")
    lat, lon = spot.get("latitude"), spot.get("longitude")
    material = (spot.get("commodity") or "").lower()
    if not radius or lat is None or lon is None or not material:
        return None
    best = None
    for record in for_system(spot.get("system"), db):
        if not same_body(record, spot.get("planet_name"), spot.get("system_address"),
                         spot.get("body_id")):
            continue
        if (record.get("commodity") or "").lower() != material:
            continue
        if record.get("latitude") is None or record.get("longitude") is None:
            continue
        try:
            metres = guide.distance(float(lat), float(lon), float(record["latitude"]),
                                    float(record["longitude"]), float(radius))
        except (TypeError, ValueError):
            continue
        if metres <= within and (best is None or metres < best[0]):
            best = (metres, record)
    if best is None:
        return None
    best[1]["distance_m"] = best[0]
    return best[1]


# A drop this close to a bookmark is taken to be at that bookmark's mining
# location. The nearest bookmark wins. Bookmarks of different locations on one
# body sit 14 km apart at the closest (measured 2026-09-18), so 3 km never
# reaches a neighbour. The panel says which bookmark it used.
SAME_LOCATION_M = 3000.0


def location_at(system, body, lat, lon, radius, db=None, within=SAME_LOCATION_M,
                system_address=None, body_id=None):
    """(location index, metres) of the nearest bookmark on `body` that knows its
    location and lies within `within` metres, or None. The IDs, when known,
    decide which bookmarks are on `body` - see same_body."""
    if not radius or lat is None or lon is None:
        return None
    best = None
    for record in for_system(system, db):
        index = record.get("location_index")
        if not same_body(record, body, system_address, body_id) or not isinstance(index, int):
            continue
        if record.get("latitude") is None or record.get("longitude") is None:
            continue
        try:
            metres = guide.distance(float(lat), float(lon), float(record["latitude"]),
                                    float(record["longitude"]), float(radius))
        except (TypeError, ValueError):
            continue
        if metres <= within and (best is None or metres < best[1]):
            best = (index, metres)
    return best


# What the Edit dialog may change. Coordinates, heading, commander and
# marked_at are excluded: they are readings taken at the press, and the
# coordinates identify the deposit.
EDITABLE = ("commodity", "rigs", "amount", "density", "location_index")


def edited(old, fields, db=None):
    """`old` with the EDITABLE keys of `fields` applied.

    Values of None clear the field, unlike updated(), where None means the
    commander left the control alone. Keys outside EDITABLE are ignored.

    Sets updated_at. An `amount` other than 'Depleted' clears depleted_at.
    """
    record = _refreshed(old, db)
    for key in EDITABLE:
        if key in fields:
            record[key] = fields[key]
    return _touched(record, fields.get("amount"))


def _without_row_keys(old):
    """`old` minus the columns for_system() adds, which are not record data."""
    return {key: value for key, value in old.items()
            if key not in ("path", "id", "distance_m")}


def _refreshed(old, db=None):
    """`old` minus the row keys, with `yield` taken off the row.

    The tally writes the row every yields.FLUSH_S and the Edit dialog is modal,
    so the copy in hand can be minutes behind. Pending tons are flushed first.
    """
    from rs_core import yields
    if db is None:
        yields.TALLY.flush()
    record = _without_row_keys(old)
    if old.get("id") is None:
        return record
    try:
        with database.connect(db) as conn:
            row = conn.execute("SELECT data FROM bookmarks WHERE id = ?",
                               (old["id"],)).fetchone()
        fresh = json.loads(row[0]).get("yield") if row else None
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning(f"could not re-read the tons of bookmark {old['id']}: {err}")
        return record
    if fresh is not None:
        record["yield"] = fresh
    return record


def _touched(record, amount):
    """Stamp updated_at. Amount Depleted marks and closes the cycle, any other
    Amount clears the mark. Set here as well as in set_depleted: the Edit
    dialog and a re-mark write `amount` straight to the row."""
    from rs_core import yields
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if amount == "Depleted":
        record.setdefault("depleted_at", record["updated_at"])
        yields.close(record, record["depleted_at"])
    elif amount is not None:
        record.pop("depleted_at", None)
    return record


def updated(old, spot, db=None):
    """`old` with Rigs, Amount and Density taken from `spot`.

    Position, heading, location, commander and marked_at stay as first marked;
    coordinates are what identifies the deposit. Only the three fields a
    commander re-reads off the HUD are copied, and only when set - a picker
    left at "-" or an empty Rigs box leaves the old value.

    Sets updated_at. An `amount` other than 'Depleted' clears depleted_at.
    Fills system_address and body_id when `old` predates them.
    """
    record = _refreshed(old, db)
    for key in ("rigs", "amount", "density"):
        if spot.get(key) is not None:
            record[key] = spot[key]
    # Bookmarks written before these columns existed take them from the mark.
    for key in ("system_address", "body_id"):
        if record.get(key) is None and spot.get(key) is not None:
            record[key] = spot[key]
    return _touched(record, spot.get("amount"))


def by_body(system, db=None):
    """{body name: [card, ...]} for one system.

    Keyed by the body exactly as the journal names it, which is what the scan
    window has in hand - no normalising on either side, so a match is a match.
    """
    grouped = {}
    for record in for_system(system, db):
        grouped.setdefault(record["planet_name"], []).append(record)
    return grouped


def newest(records):
    """The card most recently marked, for a link that has to pick one."""
    if not records:
        return None
    return max(records, key=lambda record: str(record.get("marked_at") or ""))


def ordered(records):
    """The bookmarks of one body, most rigs first, then by location.

    Rigs first because that is the question a list of them answers: of the
    patches you marked on this body, which one was worth the most. Location is
    the order you worked the body in, which is history rather than a decision.

    A bookmark with no rig count sorts last rather than as zero - it was not
    counted, which is not the same as having been counted at none.
    """
    def key(record):
        rigs = record.get("rigs")
        index = record.get("location_index")
        return (rigs is None, -(rigs or 0), index is None, index or 0)

    return sorted(records, key=key)
