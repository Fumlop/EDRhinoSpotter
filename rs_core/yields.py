"""Tons refined at a bookmarked deposit, counted into that bookmark.

One `MiningRefined` event is 1 t: on journals 2026-09-21T211951 and
2026-09-22T113404 the SRV `Cargo.Count` tracks the running event count, +/-1
from Cargo being written up to a second late. The event carries `Type` and
nothing else - no position, no body - so the ton is placed by the Status.json
reading at that moment.

Tons are kept as cycles: a run from the first ton to the Depleted mark, or to
REGEN_DAYS after its first ton ("expired"). A cycle that opened at Amount High
and ended depleted is the deposit's capacity; any other cycle bounds it from
below. A Depleted mark older than REGEN_DAYS is taken off by regrow().

No tkinter and no PIL. `python -m rs_core.yields` prints what the closed cycles
imply for deposit.TONS_PER_RIG.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from rs_core import cards, database, guide, spotmark, store
from rs_core.logging import logger

# Radius around a bookmark a ton is still counted into it - a 350 m circle.
# cards.SAME_SPOT_M is 100 m, the patch itself; the 75 m on top is for chunks
# collected off it. How far they scatter is unmeasured.
ATTRIBUTE_M = 175.0

# Days before a depleted deposit is assumed to carry material again, and after
# which an open cycle expires. Assumed, not measured: Amount was not back at
# High immediately after a depletion.
REGEN_DAYS = 14

# Seconds a delta waits before it reaches the row. 171 t in a 90-minute session
# is 3 writes rather than 171.
FLUSH_S = 30.0


def nearest(records, body, lat, lon, radius, material=None, within=ATTRIBUTE_M):
    """(record, metres) for the bookmark a ton belongs to, or None.

    On `body`, within `within` metres, nearest first. With `material`, only
    bookmarks whose `commodity` is that material.
    """
    if not radius or lat is None or lon is None:
        return None
    wanted = (material or "").lower()
    best = None
    for record in records:
        if not cards.same_body(record, body):
            continue
        if record.get("latitude") is None or record.get("longitude") is None:
            continue
        try:
            metres = guide.distance(float(lat), float(lon), float(record["latitude"]),
                                    float(record["longitude"]), float(radius))
        except (TypeError, ValueError):
            continue
        if metres > within:
            continue
        if wanted and (record.get("commodity") or "").lower() != wanted:
            continue
        if best is None or metres < best[1]:
            best = (record, metres)
    return best


def _stamp(when):
    """datetime -> the journal's shape, '2026-09-24T10:00:00Z'."""
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    """The journal's shape - `cycle["from"]` is a journal timestamp and the two
    are compared as strings in add()."""
    return _stamp(datetime.now(timezone.utc))


def cycles(record):
    """The bookmark's cycles, oldest first. [] when it has none."""
    held = (record.get("yield") or {}).get("cycles")
    return held if isinstance(held, list) else []


def _parse(stamp):
    """A datetime, journal or ISO timestamp -> aware datetime, or None."""
    if isinstance(stamp, datetime):
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def open_cycle(record):
    """The last cycle with no `ended`, or None. May be past REGEN_DAYS; see current()."""
    found = cycles(record)
    if found and isinstance(found[-1], dict) and not found[-1].get("ended"):
        return found[-1]
    return None


def _expired(cycle, when):
    """Whether open `cycle` is REGEN_DAYS or more past its first ton at `when`."""
    start, now = _parse(cycle.get("from")), _parse(when)
    return bool(start and now and now - start >= timedelta(days=REGEN_DAYS))


def current(record, now=None):
    """The open cycle while it is under REGEN_DAYS old, else None."""
    cycle = open_cycle(record)
    if cycle is None or _expired(cycle, now or _now()):
        return None
    return cycle


def add(record, tons, when=None):
    """Add {material: tons} into `record`'s open cycle, opening one if needed.

    `record` is the bookmark's stored data, not the row. `rigs`, `density` and
    `amount_at_start` are copied off it at the open and never again - a later
    edit must not rewrite the conditions the tons were mined under.
    """
    when = when or _now()
    cycle = open_cycle(record)
    if cycle is not None and _expired(cycle, when):
        _expire(cycle)
        cycle = None
    if cycle is None:
        cycle = {"from": when, "tons": {}, "rigs": record.get("rigs"),
                 "density": record.get("density"),
                 "amount_at_start": record.get("amount")}
        record.setdefault("yield", {}).setdefault("cycles", []).append(cycle)
    for material, amount in tons.items():
        cycle["tons"][material] = cycle["tons"].get(material, 0) + amount
    cycle["to"] = max(when, cycle.get("to") or "")
    return cycle


def _expire(cycle):
    cycle["ended"] = "expired"
    cycle["ended_at"] = _stamp(_parse(cycle["from"]) + timedelta(days=REGEN_DAYS))


def close(record, when=None):
    """Mark the open cycle depleted. True when there was one under REGEN_DAYS old.

    One past REGEN_DAYS is ended 'expired' instead: it never measures the deposit.
    """
    when = when or _now()
    cycle = open_cycle(record)
    if cycle is None:
        return False
    if _expired(cycle, when):
        _expire(cycle)
        return False
    cycle["ended"] = "depleted"
    cycle["ended_at"] = when
    return True


def totals(record):
    """{material: tons} over every cycle."""
    summed = {}
    for cycle in cycles(record):
        for material, amount in (cycle.get("tons") or {}).items():
            summed[material] = summed.get(material, 0) + amount
    return summed


def cycle_tons(cycle):
    return sum((cycle.get("tons") or {}).values())


def measured(record):
    """The cycles that measure the deposit: opened at Amount High, closed
    depleted. A cycle that started lower, or is still open, only bounds it from
    below."""
    return [cycle for cycle in cycles(record)
            if cycle.get("ended") == "depleted" and cycle.get("amount_at_start") == "High"]


def capacity(record):
    """(low, high, measured cycles) tons the deposit has held, or None.

    With no measured cycle, the largest cycle is the low bound and the high is
    None - the deposit held at least that much.
    """
    full = [cycle_tons(cycle) for cycle in measured(record)]
    if full:
        return (min(full), max(full), len(full))
    largest = max((cycle_tons(cycle) for cycle in cycles(record)), default=0)
    return None if not largest else (largest, None, 0)


def short(record, now=None):
    """The Mined column: tons in the current cycle, '123 t', or ''."""
    cycle = current(record, now)
    tons = cycle_tons(cycle) if cycle else 0
    return f"{tons:,} t" if tons else ""


def describe(record, now=None):
    """The card line: '40 t this cycle · held 1,150-1,190 t (2 cycles)', or ''."""
    parts = []
    cycle = current(record, now)
    if cycle and cycle_tons(cycle):
        parts.append(f"{cycle_tons(cycle):,} t this cycle")
    span = capacity(record)
    if span and not (span[2] == 0 and cycle and span[0] == cycle_tons(cycle)):
        low, high, samples = span
        parts.append(f"held ≥{low:,} t" if samples == 0 else
                     f"held {low:,} t" if samples == 1 else
                     f"held {low:,}-{high:,} t ({samples} cycles)")
    return "  ·  ".join(parts)


def days_since_depleted(record, now=None):
    """Days since the Depleted mark, or None. Fractional. `now`: datetime or timestamp."""
    when = _parse(record.get("depleted_at"))
    if when is None:
        return None
    return ((_parse(now) or datetime.now(timezone.utc)) - when).total_seconds() / 86400.0


def regenerated(record, now=None, after=REGEN_DAYS):
    """Whether a depleted deposit is past the assumed regen time. None when it
    carries no Depleted mark."""
    days = days_since_depleted(record, now)
    return None if days is None else days >= after


def regrow(db=None, now=None):
    """Take the Depleted mark off every bookmark depleted REGEN_DAYS or more ago.

    Depleted = `depleted_at`, or Amount 'Depleted' read off the HUD (dated by
    `marked_at`). The mark moves to `regrown` [{depleted_at, regrown_at}], so the
    date survives; Amount 'Depleted' becomes None (unread). Returns the count.
    """
    moment = _parse(now) or datetime.now(timezone.utc)
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT id, data FROM bookmarks WHERE depleted_at IS NOT NULL "
                                "OR data LIKE '%\"amount\": \"Depleted\"%'").fetchall()
            names = []
            for id, data in rows:
                try:
                    record = json.loads(data)
                except ValueError as err:
                    logger.warning(f"regrow: skipping unreadable bookmark {id}: {err}")
                    continue
                since = record.get("depleted_at") or (
                    record.get("marked_at") if record.get("amount") == "Depleted" else None)
                start = _parse(since)
                if start is None or moment - start < timedelta(days=REGEN_DAYS):
                    continue
                record.setdefault("regrown", []).append(
                    {"depleted_at": since, "regrown_at": _stamp(moment)})
                record.pop("depleted_at", None)
                if record.get("amount") == "Depleted":
                    record["amount"] = None
                database.write_bookmark(conn, record, id)
                names.append(f"{record.get('planet_name')} {record.get('commodity')}")
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not take regrown deposits off Depleted: {err}")
        return 0
    if names:
        database.changed()
        logger.info(f"past the {REGEN_DAYS} d regen, active again: {', '.join(names)}")
    return len(names)


class Tally:
    """Tons waiting to reach their bookmark rows.

    Deltas per row, not records: a flush re-reads the row, adds the delta into
    its open cycle and writes that, so an Edit made meanwhile is not lost.

    `unplaced` counts tons with no bookmark within ATTRIBUTE_M, `byproduct`
    tons with a bookmark in range but none of that material, `unread` tons
    whose Status.json read landed mid-write. main.stop() logs all three.
    """

    def __init__(self, delay=FLUSH_S, db=None):
        self._db = db
        self._lock = threading.Lock()   # _pending is written on the journal
        self._pending = {}              # thread and read on the timer thread
        self._writes = store.Debounced(delay=delay, write=self._write)
        self.unplaced = 0
        self.byproduct = 0
        self.unread = 0
        self._cache = None       # (system, revision) -> the bookmarks read

    def refined(self, status, system, material, when=None):
        """Count 1 t of `material` at the Status.json reading `status`.

        The bookmark it was counted into, or None when no bookmark of
        `material` is within ATTRIBUTE_M, the reading has no position, or it
        was not refined on the ground. By-products are not counted.
        """
        if not material:
            return None
        if not status:
            # read_status() gives {} for a read that landed mid-write.
            self.unread += 1
            return None
        if not spotmark.on_ground(status):
            return None         # asteroid mining refines the same materials
        body = status.get("BodyName")
        if not body:
            self.unread += 1
            return None
        records = self._bookmarks(system)
        at = (body, status.get("Latitude"), status.get("Longitude"), status.get("PlanetRadius"))
        found = nearest(records, *at, material)
        if found is None:
            if nearest(records, *at) is None:
                self.unplaced += 1
            else:
                self.byproduct += 1
            return None
        record, _ = found
        with self._lock:
            delta = self._pending.setdefault(record["id"], {"tons": {}})
            delta["tons"][material] = delta["tons"].get(material, 0) + 1
            delta["when"] = when or _now()
            # Inside the lock: a flush between the two writes nothing for this id.
            # Debounced carries no data - _pending is the one copy.
            self._writes(record["id"], None)
        return record

    def _bookmarks(self, system):
        """The system's bookmarks, re-read when a write moved the revision.

        A read that failed is not cached: revision() only moves on a write, so
        one locked database would make every ton of the session unplaced.
        """
        key = (system, database.revision())
        if self._cache is None or self._cache[0] != key:
            try:
                found = cards.for_system(system, self._db, quiet=False)
            except (sqlite3.Error, OSError) as err:
                logger.warning(f"could not read the bookmarks of {system}: {err}")
                return []
            self._cache = (key, found)
        return self._cache[1]

    def _write(self, id, _):
        """One row: read, add what has piled up into its open cycle, write.

        Only the tons counted before the read are taken off `_pending`, so ones
        refined while the write runs are kept for the next one.
        """
        with self._lock:
            delta = self._pending.get(id)
            if delta is None:
                return
            taken = {material: amount for material, amount in delta["tons"].items() if amount}
            when = delta["when"]
        if not taken:
            return
        try:
            with database.connect(self._db) as conn:
                row = conn.execute("SELECT data FROM bookmarks WHERE id = ?", (id,)).fetchone()
                if row is None:
                    logger.warning(f"dropping {sum(taken.values())} t: bookmark {id} is gone")
                    with self._lock:
                        self._pending.pop(id, None)
                    return
                record = json.loads(row[0])
                add(record, taken, when)
                database.write_bookmark(conn, record, id)
        except (sqlite3.Error, OSError, ValueError) as err:
            logger.warning(f"could not write {sum(taken.values())} t to bookmark {id}: {err} - "
                           f"retrying in {self._writes.delay:.0f} s")
            self._writes(id, None)      # flush() took the key with it
            return
        with self._lock:
            for material, amount in taken.items():
                delta["tons"][material] -= amount
        database.changed()

    def flush(self):
        """Write everything pending. Called on DockSRV, Liftoff and
        plugin_stop."""
        self._writes.flush()


# cards.set_depleted and cards._refreshed flush this before they read the row,
# so pending tons land in the cycle they were mined in.
TALLY = Tally()


def samples(db=None):
    """Every measured cycle in the database, as
    (bookmark, cycle, tons per rig position). Density and rigs are the cycle's,
    not the bookmark's current values."""
    found = []
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT id, data FROM bookmarks").fetchall()
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not read the bookmarks: {err}")
        return found
    for id, data in rows:
        try:
            record = json.loads(data)
        except ValueError:
            continue
        record["id"] = id
        for cycle in measured(record):
            rigs = cycle.get("rigs")
            if not isinstance(rigs, int) or isinstance(rigs, bool) or rigs <= 0:
                continue
            found.append((record, cycle, cycle_tons(cycle) / rigs))
    return found


def _report(db=None):
    """What the measured cycles imply for deposit.TONS_PER_RIG, per Density."""
    from rs_core import deposit

    found = samples(db)
    if not found:
        print("no measured cycle yet: a cycle counts when it opened at Amount "
              "High and was marked Depleted")
        return 0
    print(f"{len(found)} measured cycle(s)\n")
    print(f"{'body':28} {'material':16} {'rigs':>4} {'density':8} {'tons':>7} {'t/rig':>7}")
    bands = {}
    for record, cycle, per_rig in found:
        density = cycle.get("density") or "-"
        print(f"{str(record.get('planet_name'))[:28]:28} "
              f"{str(record.get('commodity'))[:16]:16} {cycle['rigs']:>4} {density:8} "
              f"{cycle_tons(cycle):>7,} {per_rig:>7.1f}")
        bands.setdefault(density, []).append(per_rig)
    print()
    for density in sorted(bands):
        rates = bands[density]
        current = deposit.TONS_PER_RIG.get(density)
        shipped = f"  shipped {current[0]}-{current[1]}" if current else ""
        print(f"{density:8} n={len(rates):<3} {min(rates):.0f}-{max(rates):.0f} t/rig"
              f"{shipped}")
    print("\nConstants are edited by hand: a cycle whose deposit was mined before "
          "it was bookmarked, or with EDMC off for part of it, reads low.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_report())
