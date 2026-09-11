"""Replay recent journals, and stand in the best system they contain.

Two jobs.

  As a tool:   python -m rs_core.replay        ranks what you have flown
               through lately, so the scoring can be argued with before it
               ends up on a panel.

  As a test:   set RHINOSPOTTER_TESTMODE=1 and the plugin starts in the best
               of those systems. RhinoScan then has something real to draw
               without anyone flying anywhere, which is the only way to look
               at the window over a system with four grounds in it.

It reads the commander's own journal files and nothing else - the same files
EDMC reads, just more of them than the one it is watching.

No tkinter, so it can be checked without EDMC in the way. See
rs_tests/test_replay.py.
"""

import argparse
import json
import os
import sys
import time

from rs_core import bodies, grounds
from rs_core.logging import logger

JOURNAL_DIR = os.path.expandvars(
    r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous")
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
    what the panel would have shown at the time. A system visited twice ends
    up with the union of both visits, because leaving hands the list over
    before it is cleared.
    """
    found = {}

    def keep(system, seen):
        found[system] = seen

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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rank the systems in recent journals")
    parser.add_argument("--days", type=int, default=DAYS)
    parser.add_argument("--root", default=JOURNAL_DIR)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    sheet = grounds.Sheet()
    paths = journal_files(args.root, args.days)
    print(f"{len(paths)} journal file(s) in the last {args.days} day(s)")
    systems = replay(paths)
    if not systems:
        print("no landable bodies scanned in that window")
        return 1

    for system, seen, value in rank(systems, sheet)[:args.top]:
        counted = sum(body.get("locations") or 0 for body in seen)
        print(f"\n{system}   score {value}, {len(seen)} landable, {counted} locations counted")
        for ground, found in _by_ground(seen):
            rows = sheet.materials(ground, limit=3, minimum=2.0)
            best_of = "  ".join(f"{row['material']} {row['pct']}%" for row in rows) or "-"
            print(f"   {grounds.label(ground):<28} {len(found):>2} body(s)   {best_of}")
    return 0


def _by_ground(seen):
    buckets = {}
    for body in seen:
        buckets.setdefault(body["ground"], []).append(body)
    order = {ground: index for index, ground in enumerate(grounds.GROUND_ORDER)}
    return sorted(buckets.items(), key=lambda item: order.get(item[0], len(order)))


if __name__ == "__main__":
    sys.exit(main())
