"""Tons refined at a bookmarked deposit, counted into that bookmark.

One `MiningRefined` event is 1 t: on journals 2026-09-21T211951 and
2026-09-22T113404 the SRV `Cargo.Count` tracks the running event count, +/-1
from Cargo being written up to a second late. The event carries `Type` and
nothing else - no position, no body - so the ton is placed by the Status.json
reading at that moment.

Tons are kept as cycles: a run from the first ton to the Depleted mark. A
cycle that opened at Amount High and ended depleted is the deposit's capacity;
any other cycle bounds it from below.

No tkinter and no PIL. `python -m rs_core.yields` prints what the closed cycles
imply for deposit.TONS_PER_RIG.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone

from rs_core import cards, database, guide, spotmark, store
from rs_core.logging import logger

# Radius around a bookmark a ton is still counted into it - a 350 m circle.
# cards.SAME_SPOT_M is 100 m, the patch itself; the 75 m on top is for chunks
# collected off it. How far they scatter is unmeasured.
ATTRIBUTE_M = 175.0

# Days before a depleted deposit is assumed to carry material again. Assumed,
# not measured: Amount was not back at High immediately after a depletion.
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


def _now():
    """The journal's shape - `cycle["from"]` is a journal timestamp and the two
    are compared as strings in add()."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cycles(record):
    """The bookmark's cycles, oldest first. [] when it has none."""
    held = (record.get("yield") or {}).get("cycles")
    return held if isinstance(held, list) else []


def open_cycle(record):
    """The cycle tons are being added to, or None. The last one with no
    `ended`."""
    found = cycles(record)
    if found and isinstance(found[-1], dict) and not found[-1].get("ended"):
        return found[-1]
    return None


def add(record, tons, when=None):
    """Add {material: tons} into `record`'s open cycle, opening one if needed.

    `record` is the bookmark's stored data, not the row. `rigs`, `density` and
    `amount_at_start` are copied off it at the open and never again - a later
    edit must not rewrite the conditions the tons were mined under.
    """
    when = when or _now()
    cycle = open_cycle(record)
    if cycle is None:
        cycle = {"from": when, "tons": {}, "rigs": record.get("rigs"),
                 "density": record.get("density"),
                 "amount_at_start": record.get("amount")}
        record.setdefault("yield", {}).setdefault("cycles", []).append(cycle)
    for material, amount in tons.items():
        cycle["tons"][material] = cycle["tons"].get(material, 0) + amount
    cycle["to"] = max(when, cycle.get("to") or "")
    return cycle


def close(record, when=None):
    """Mark the open cycle depleted. True when there was one."""
    cycle = open_cycle(record)
    if cycle is None:
        return False
    cycle["ended"] = "depleted"
    cycle["ended_at"] = when or _now()
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

    With no measured cycle, the tons collected so far are the low bound and the
    high is None - the deposit held at least that much.
    """
    full = [cycle_tons(cycle) for cycle in measured(record)]
    if full:
        return (min(full), max(full), len(full))
    collected = sum(totals(record).values())
    return None if not collected else (collected, None, 0)


def short(record):
    """Tons in one line: '190 t' from the best cycle that measured the deposit,
    '≥171 t' when none has, '' when nothing was collected."""
    span = capacity(record)
    if span is None:
        return ""
    low, high, samples = span
    return f"{high:,} t" if samples else f"≥{low:,} t"


def describe(record):
    """'1,150 t collected, 2 cycles: 1,150-1,190 t', or ''."""
    span = capacity(record)
    if span is None:
        return ""
    collected = sum(totals(record).values())
    low, high, samples = span
    if samples == 0:
        return f"{collected:,} t collected, deposit held at least that"
    if samples == 1:
        return f"{collected:,} t collected, deposit held {low:,} t"
    return f"{collected:,} t collected, {samples} cycles: {low:,}-{high:,} t"


def days_since_depleted(record, now=None):
    """Days since the Depleted mark, or None. Fractional."""
    marked = record.get("depleted_at")
    if not marked:
        return None
    try:
        when = datetime.fromisoformat(str(marked).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - when).total_seconds() / 86400.0


def regenerated(record, now=None, after=REGEN_DAYS):
    """Whether a depleted deposit is past the assumed regen time. None when it
    carries no Depleted mark."""
    days = days_since_depleted(record, now)
    return None if days is None else days >= after


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
