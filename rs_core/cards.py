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
# patch assumed on flat ground: eight rigs, seven round one in the middle at
# the 76 m rig spacing, is a circle of 76 / (2 sin(pi/7)) = 87.6 m; with 10 %
# on top that is 96 m, set to a round 100 m.
SAME_SPOT_M = 100.0

# Bookmarks already reported as unreadable. The minimap reads them again on
# every change, and one broken row is one line in the log, not one a change.
_warned = set()


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
    """
    if record.get("id") is None:
        return False
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
            else:
                data.pop("depleted_at", None)
            database.write_bookmark(conn, data, record["id"])
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning(f"could not mark bookmark {record['id']} depleted: {err}")
        return False
    database.changed()
    if depleted:
        record["depleted_at"] = data["depleted_at"]
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
# location: a location is up to about 5 km in radius, so two points in it are
# up to 10 km apart. The nearest bookmark wins. Bookmarks of two different
# locations have sat 2.7 km apart, so at a location not bookmarked yet a
# neighbour's number can come up - the panel says which bookmark it used.
SAME_LOCATION_M = 10000.0


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


def updated(old, spot):
    """The old bookmark with the new mark's Amount and Density, nothing else.

    The first mark is where the deposit is: its position, heading, location,
    rigs and time stay. Only the readings that change as it is mined are taken
    from the new one, and only the ones picked - a picker left at "-" does not
    wipe what was there. `updated_at` says when. An Amount other than Depleted
    takes the Depleted mark off: the deposit reads live again.
    """
    record = {key: value for key, value in old.items()
              if key not in ("path", "id", "distance_m")}
    for key in ("amount", "density"):
        if spot.get(key) is not None:
            record[key] = spot[key]
    # A bookmark made before the IDs were kept takes them from the new mark.
    for key in ("system_address", "body_id"):
        if record.get(key) is None and spot.get(key) is not None:
            record[key] = spot[key]
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    amount = spot.get("amount")
    if amount is not None and amount != "Depleted":
        record.pop("depleted_at", None)
    return record


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
