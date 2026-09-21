"""Replay recent journals, and stand in the best system they contain.

Two jobs.

  As a tool:   python -m rs_core.replay        ranks what you have flown
               through lately, so the scoring can be argued with before it
               ends up on a panel.

  As repair:   python -m rs_core.replay --rebuild writes every system it
               finds into the cache. EDMC replays the journal file it is
               watching and nothing older, so a body scanned in an earlier
               session is in a file EDMC will never read - this is how it gets
               back.

  As a test:   python -m rs_core.replay --testmode writes the best of those
               systems into the cache, so the next EDMC start stands in it
               without anyone flying anywhere.

It reads the commander's own journal files and nothing else - the same files
EDMC reads, just more of them than the one it is watching.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_replay.py.
"""

import argparse
import json
import os
import sqlite3
import sys
import time

from rs_core import bodies, grounds, migrate, paths, store
from rs_core.logging import logger

JOURNAL_DIR = paths.journal_dir()
JOURNAL_GLOB = "Journal."
DAYS = 3


def journal_files(root=JOURNAL_DIR, days=DAYS, now=None):
    """Journal files touched in the last `days`, oldest first.

    Modification time rather than the timestamp in the filename: a session
    that ran past midnight keeps writing to yesterday's file, and sorting by
    name would replay it before things that happened earlier.
    """
    cutoff = (now if now is not None else time.time()) - days * 86400
    try:
        names = os.listdir(root)
    except OSError as err:
        logger.debug(f"no journals at {root}: {err}")
        return []
    found = []
    for name in names:
        if not name.startswith(JOURNAL_GLOB) or not name.endswith(".log"):
            continue
        path = os.path.join(root, name)
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            continue
        if stamp >= cutoff:
            found.append((stamp, path))
    return [path for _, path in sorted(found)]


def replay(paths):
    """Every system in those files -> {system: [body, ...]}.

    Run through the same Register the live plugin uses, so what comes out is
    what the panel would have shown at the time.

    A system visited twice ends up with the union of both visits. Replacing
    instead of merging looked equivalent and was not: two sessions describe
    different parts of one system - the first honk resolved A 1 to A 7, the
    second only the AB bodies - and the later visit silently threw the earlier
    one away.
    """
    found = {}

    def keep(system, seen):
        merged = {body["name"]: body for body in found.get(system, [])}
        for body in seen:
            merged[body["name"]] = body
        found[system] = sorted(merged.values(),
                               key=lambda body: (body["distance"] is None,
                                                 body["distance"] or 0.0,
                                                 body["name"]))

    register = bodies.Register(on_change=keep)
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    register.track(entry, system=entry.get("StarSystem"))
        except OSError as err:
            logger.debug(f"skipping {path}: {err}")
    return {system: seen for system, seen in found.items() if seen}


def score(seen, sheet):
    """How much good ground a system has -> a number, higher is better.

    Every landable body is worth the best rate its ground has ever shown, and
    the system is worth the sum. That rewards a system with five magma bodies
    over one with a single magma body and four icy ones, which is the question
    the panel exists to answer: not "is there something here" but "is there
    enough here to be worth the trip".

    A body on ground the sheet has never measured is worth nothing rather than
    being guessed at.
    """
    total = 0.0
    for body in seen:
        rows = sheet.materials(body.get("ground"))
        if rows:
            total += rows[0]["pct"]
    return round(total, 1)


def rank(systems, sheet):
    """[(system, bodies, score), ...], best first.

    Ties break on how many mining locations have actually been counted there:
    two systems of equal ground are separated by how much someone has already
    probed, and a probed body is one you can fly straight to.
    """
    rows = []
    for system, seen in systems.items():
        counted = sum(body.get("locations") or 0 for body in seen)
        rows.append((score(seen, sheet), counted, system, seen))
    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [(system, seen, value) for value, _, system, seen in rows]


def best(root=JOURNAL_DIR, days=DAYS, sheet=None):
    """The best system in the recent journals -> (system, bodies), or None."""
    sheet = sheet or grounds.Sheet()
    systems = replay(journal_files(root, days))
    if not systems:
        return None
    ordered = rank(systems, sheet)
    system, seen, _ = ordered[0]
    return system, seen


def _merged(system, seen):
    """`seen` over what the cache holds for that system, sorted by name.

    Bodies: the union; two journals of one system describe different parts.
    Fields: the journal's win, except a None over a value the cache holds, so
    cache-only ones such as Spansh's `locations` are kept. A journal
    `locations` brings its own `locations_from`: Register.bodies() leaves the
    key out for the commander's own count.
    Raises sqlite3.Error, OSError, ValueError when the cache cannot be read.
    """
    known = {body["name"]: body for body in store.load(system, strict=True)}
    for body in seen:
        held = known.get(body["name"], {})
        fresh = {key: value for key, value in body.items()
                 if value is not None or held.get(key) is None}
        if fresh.get("locations") is not None:
            held = {key: value for key, value in held.items() if key != "locations_from"}
        known[body["name"]] = {**held, **fresh}
    return sorted(known.values(), key=lambda b: b["name"])


def rebuild(systems):
    """Write every system found into the cache, merged over it. Returns
    (written, failed): how many, and [(system, reason), ...] not written.

    For bodies scanned in journal files EDMC never replays - before the plugin
    was installed, or while it was not running.
    """
    written, failed = 0, []
    for system, seen in systems.items():
        try:
            bodies_now = _merged(system, seen)
        except (sqlite3.Error, OSError, ValueError) as err:
            failed.append((system, f"cache not read, left as it was: {err}"))
            continue
        if store.save(system, bodies_now):
            written += 1
        else:
            failed.append((system, "not written, see the log"))
    return written, failed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank the systems in recent journals")
    parser.add_argument("--days", type=int, default=DAYS)
    parser.add_argument("--root", default=JOURNAL_DIR)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--testmode", action="store_true",
                        help="write the best system to the cache, so the next "
                             "EDMC start stands in it")
    parser.add_argument("--rebuild", action="store_true",
                        help="write every system in the window to the cache")
    args = parser.parse_args(argv)
    # The cache is the database now; the JSON of 4.1 goes in before it is merged into.
    migrate.run()

    sheet = grounds.Sheet()
    paths = journal_files(args.root, args.days)
    print(f"{len(paths)} journal file(s) in the last {args.days} day(s)")
    systems = replay(paths)
    if not systems:
        print("no landable bodies scanned in that window")
        return 1

    ordered = rank(systems, sheet)
    failures = 0
    if args.rebuild:
        written, failed = rebuild(systems)
        print(f"\nrebuilt {written} system(s) in the cache")
        for system, reason in failed:
            print(f"  FAILED {system}: {reason}")
        failures += len(failed)
        if not failed:
            print("  start EDMC and they are all there, no re-scanning")

    if args.testmode:
        system, seen, value = ordered[0]
        try:
            path = store.save(system, _merged(system, seen))
            reason = "not written, see the log"
        except (sqlite3.Error, OSError, ValueError) as err:
            path = None
            reason = f"cache not read, left as it was: {err}"
        print(f"\ntest mode: {system} (score {value}, {len(seen)} landable)")
        if path is None:
            failures += 1
            print(f"  FAILED: {reason}")
        else:
            print(f"  -> {path}")
            print("  start EDMC and jump nowhere - RhinoData shows it")

    for system, seen, value in ordered[:args.top]:
        counted = sum(body.get("locations") or 0 for body in seen)
        print(f"\n{system}   score {value}, {len(seen)} landable, {counted} locations counted")
        for ground, found in _by_ground(seen):
            rows = sheet.best(ground, limit=3, minimum=2.0)
            best_of = "  ".join(f"{row['material']} {row['pct']}%" for row in rows) or "-"
            print(f"   {grounds.label(ground):<28} {len(found):>2} body(s)   {best_of}")
    return 1 if failures else 0


def _by_ground(seen):
    buckets = {}
    for body in seen:
        buckets.setdefault(grounds.canonical(body["ground"]), []).append(body)
    order = {ground: index for index, ground in enumerate(grounds.GROUND_ORDER)}
    return sorted(buckets.items(), key=lambda item: order.get(item[0], len(order)))


if __name__ == "__main__":
    sys.exit(main())
