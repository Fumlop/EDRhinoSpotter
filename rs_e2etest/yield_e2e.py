"""E2E harness for the yield tally. Checks and blind spots: yield.md.

Run from the plugin folder:  python rs_e2etest/yield_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and one folder per scenario.
Exit code 1 on a failure.

The child runs the real load.journal_entry over the real MiningRefined lines of
a copied journal, against a Status.json it writes itself - the game's own file
is live-only and the coordinates have to be put where the bookmarks are. Its
LOCALAPPDATA is the scenario folder, set before the interpreter starts, so the
live database is never opened.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)

# The 171-ton Diamond session. Copied, never read in place.
JOURNAL = "Journal.2026-09-21T211951.01.log"

BODY = "Aramo A 1"
SYSTEM = "Aramo"
RADIUS = 1_500_000.0        # m, a small rocky body
LAT, LON = 12.345678, -45.678901


def _metres_east(lat, lon, metres, radius):
    """`lon` moved east by `metres` at latitude `lat`."""
    import math
    return lon + math.degrees(metres / (radius * math.cos(math.radians(lat))))


# ----------------------------------------------------------------- the child


def child():
    import logging
    sys.path.insert(0, PLUGIN)
    logging.getLogger("RhinoSpotter").addHandler(
        logging.FileHandler(os.environ["E2E_LOG"], encoding="utf-8"))

    from rs_core import cards, coverage, database, paths, spotcard, yields
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH

    scratch = os.environ["LOCALAPPDATA"]
    paths.journal_dir = lambda: scratch
    coverage.clear_old_textures = lambda: None
    # TALLY was built at import with delay=FLUSH_S, so the live value is the
    # one on the debounce, not the constant.
    yields.TALLY._writes.delay = 0.05

    import load
    load.plugin_start3(PLUGIN)

    results = []

    def check(name, got, want):
        results.append((name, got == want, f"{got!r} != {want!r}"))

    def status(lat, lon, body=BODY, altitude=0.0):
        with open(os.path.join(scratch, "Status.json"), "w", encoding="utf-8") as handle:
            json.dump({"BodyName": body, "Latitude": lat, "Longitude": lon,
                       "Altitude": altitude, "PlanetRadius": RADIUS, "Heading": 0}, handle)

    def bookmark(material, lat, lon, rigs=4, amount="High", density="Medium"):
        return spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": lat,
                              "longitude": lon, "planet_radius": RADIUS,
                              "commodity": material, "rigs": rigs, "amount": amount,
                              "density": density, "location_index": 1,
                              "marked_at": _stamp(0)})

    def row(id):
        with database.connect() as conn:
            return json.loads(conn.execute("SELECT data FROM bookmarks WHERE id = ?",
                                           (id,)).fetchone()[0])

    def feed(lines):
        for entry in lines:
            load.journal_entry("E2E", False, SYSTEM, None, entry, {})
        yields.TALLY.flush()

    refined = _refined_lines(os.path.join(scratch, JOURNAL))
    check("journal carries the 171 refined lines", len(refined), 171)

    # 1. The real session, all of it at the bookmark.
    diamond = bookmark("Diamond", LAT, LON)
    status(LAT, LON)
    feed(_restamp(refined))
    cycles = yields.cycles(row(diamond))
    check("one open cycle", len(cycles), 1)
    # The session's 171 t are 127 Diamond + 44 Ruby: the third CargoTransfer of
    # that journal is ruby 44. The by-product is not counted into the bookmark.
    check("127 t of the bookmark's material counted",
          cycles[0]["tons"], {"Diamond": 127})
    check("44 t by-product counted as by-product", yields.TALLY.byproduct, 44)
    check("cycle carries the conditions it was mined under",
          (cycles[0]["rigs"], cycles[0]["density"], cycles[0]["amount_at_start"]),
          (4, "Medium", "High"))
    check("nothing unplaced", yields.TALLY.unplaced, 0)

    # 2. A ton refined 5 km off every bookmark is counted as unplaced, not onto
    #    the nearest one.
    status(LAT, _metres_east(LAT, LON, 5000.0, RADIUS))
    feed(_restamp(refined[:3]))
    check("3 t off the bookmarks are unplaced", yields.TALLY.unplaced, 3)
    check("and did not reach the bookmark",
          yields.cycles(row(diamond))[0]["tons"], {"Diamond": 127})

    # 2b. A read that lands mid-write costs the ton, and is counted.
    with open(os.path.join(scratch, "Status.json"), "w", encoding="utf-8") as handle:
        handle.write('{"BodyName": "Ara')
    feed(_restamp(refined[:2]))
    check("2 t with an unreadable Status.json", yields.TALLY.unread, 2)

    # 2c. Refined 2 km up is asteroid mining, not this deposit: not counted and
    #     not a loss.
    status(LAT, LON, altitude=2000.0)
    feed(_restamp(refined[:7]))
    check("7 t refined off the ground are neither placed nor counted lost",
          (yields.TALLY.unplaced, yields.TALLY.unread), (3, 2))

    # 3. Only a bookmark of the material refined takes the ton: the Ruby one
    #    is 120 m further away than the Alexandrite one and still gets the ruby. The Diamond bookmark
    #    at 0 m takes neither.
    alex = bookmark("Alexandrite", LAT, LON)
    ruby = bookmark("Ruby", LAT, _metres_east(LAT, LON, 120.0, RADIUS))
    status(LAT, LON)
    feed(_restamp([{"event": "MiningRefined", "Type": "$ruby_name;"}] * 11
                  + [{"event": "MiningRefined", "Type": "$alexandrite_name;"}] * 46))
    check("11 t of ruby to the Ruby bookmark",
          yields.totals(row(ruby)), {"Ruby": 11})
    check("46 t of alexandrite to the Alexandrite bookmark",
          yields.totals(row(alex)), {"Alexandrite": 46})
    check("and none to the Diamond bookmark",
          yields.totals(row(diamond)), {"Diamond": 127})

    # 4. EDMC replaying the journal at startup: lines older than the plugin
    #    start are skipped.
    from rs_ui import main
    before = main._replayed
    feed([{"event": "MiningRefined", "Type": "$diamond_name;",
           "timestamp": "2020-01-01T00:00:00Z"}] * 5)
    check("5 replayed lines skipped", main._replayed - before, 5)
    check("and no tons added", yields.totals(row(diamond)), {"Diamond": 127})

    # 5. Depleted closes the cycle, including tons still pending at the press.
    yields.TALLY._writes.delay = 3600.0        # nothing reaches the row on its own
    status(LAT, LON)
    for entry in _restamp([{"event": "MiningRefined", "Type": "$diamond_name;"}] * 9):
        load.journal_entry("E2E", False, SYSTEM, None, entry, {})
    record = dict(row(diamond), id=diamond)
    check("depleted written", cards.set_depleted(record, True), True)
    closed = yields.cycles(row(diamond))
    check("still one cycle", len(closed), 1)
    check("closed depleted", closed[0].get("ended"), "depleted")
    check("the 9 pending tons landed in the closed cycle",
          closed[0]["tons"], {"Diamond": 136})
    check("the deposit measures 136 t", yields.capacity(row(diamond)), (136, 136, 1))
    yields.TALLY._writes.delay = 0.05

    # 6. Mining it again after the regen opens a second cycle rather than
    #    reopening the closed one.
    feed(_restamp([{"event": "MiningRefined", "Type": "$diamond_name;"}] * 4))
    again = yields.cycles(row(diamond))
    check("a second cycle", len(again), 2)
    check("the closed one untouched", again[0]["tons"], {"Diamond": 136})
    check("the new one has the 4 t", again[1]["tons"], {"Diamond": 4})

    # 6b. The Mined column is the current cycle; the card keeps the measured
    #     capacity beside it.
    from rs_ui import scan
    check("Mined column reads the current cycle", yields.short(row(diamond)), "4 t")
    check("card: this cycle and what the deposit held",
          yields.describe(row(diamond)), "4 t this cycle  ·  held 136 t")
    check("card before any measured cycle: the floor is the cycle, said once",
          yields.describe(row(alex)), "46 t this cycle")
    check("header and row line up",
          len(scan._columns("Material", "Rigs", "Brg", "Dist", "Mined", "Est. left")),
          len(scan._columns("Alexandrite", "4", "359°", "5.7 km", "≥46 t",
                            "≈ 620-1,200 t left")))

    # 6b'. Bearing and distance from the location's centre: due east 120 m of a
    #      set centre is 90° / 120 m; a map with no centre set gives '-'.
    ruby_row = dict(row(ruby), id=ruby)
    centred = [("loc1", {"origin": [LAT, LON], "center": [LAT, LON], "radius": RADIUS,
                         "stamps": []})]
    check("east of the centre reads 90° 120 m",
          scan._from_centre(centred, BODY, ruby_row), ("90°", "120 m"))
    uncentred = [("loc1", {"origin": [LAT, LON], "radius": RADIUS, "stamps": []})]
    check("no centre set reads '-'",
          scan._from_centre(uncentred, BODY, ruby_row), ("-", "-"))
    check("no map reads '-'", scan._from_centre([], BODY, ruby_row), ("-", "-"))

    # 6c. Edit and re-mark write the whole record back through spotcard.save.
    #     The cycles must survive both as a dict, with the tons the tally wrote
    #     while the dialog was open.
    edited = cards.edited(dict(row(alex), id=alex), {"rigs": 6})
    spotcard.save(edited, id=alex)
    check("edit keeps the cycles a dict", type(row(alex).get("yield")).__name__, "dict")
    check("edit keeps the tons", yields.totals(row(alex)), {"Alexandrite": 46})
    check("edit still wrote the field it was for", row(alex).get("rigs"), 6)

    status(LAT, LON)
    for entry in _restamp([{"event": "MiningRefined", "Type": "$alexandrite_name;"}] * 3):
        load.journal_entry("E2E", False, SYSTEM, None, entry, {})
    spotcard.save(cards.updated(dict(row(alex), id=alex), {"amount": "Medium"}), id=alex)
    check("a re-mark takes the tons pending at the time with it",
          yields.totals(row(alex)), {"Alexandrite": 49})

    # 6d. Amount Depleted through the Edit dialog closes the cycle, as the
    #     Depleted button does.
    spotcard.save(cards.edited(dict(row(alex), id=alex), {"amount": "Depleted"}), id=alex)
    check("edited to Depleted closes the cycle",
          [cycle.get("ended") for cycle in yields.cycles(row(alex))], ["depleted"])
    check("and stamps depleted_at", bool(row(alex).get("depleted_at")), True)

    # 6e. The location map's cache key: a tally write must not throw the
    #     70-160 ms repaint away, an edit to what it draws must.
    body = {"name": BODY, "marks": [row(alex)]}
    was = scan._marks_key(body)
    yields.add(body["marks"][0], {"Alexandrite": 7})
    check("tons do not move the map picture key", scan._marks_key(body), was)
    body["marks"][0]["rigs"] = 7
    check("rigs do", scan._marks_key(body) != was, True)

    # 7. The regen assumption, on the mark just written and on an old one.
    fresh = row(diamond)
    check("fresh depletion is not regrown", yields.regenerated(fresh), False)
    old = dict(fresh, depleted_at=_stamp(-15 * 86400))
    check("15 days past is regrown", yields.regenerated(old), True)

    # 8. An open cycle expires REGEN_DAYS after its first ton: the Mined column
    #    empties, and the next ton opens a new cycle; the expired one never
    #    counts as a measurement.
    later = datetime.now(timezone.utc) + timedelta(days=15)
    check("8 open cycle past 14 d: Mined column empty",
          yields.short(row(diamond), now=later.strftime("%Y-%m-%dT%H:%M:%SZ")), "")
    record = row(diamond)
    yields.add(record, {"Diamond": 2}, later.strftime("%Y-%m-%dT%H:%M:%SZ"))
    check("8 next ton after 14 d: the old cycle ended expired",
          [cycle.get("ended") for cycle in yields.cycles(record)],
          ["depleted", "expired", None])
    check("8 new cycle holds only the new tons", yields.cycles(record)[-1]["tons"],
          {"Diamond": 2})
    check("8 expired cycle is not a measurement", len(yields.measured(record)), 1)
    stale = {"amount": "High", "yield": {"cycles": [
        {"from": _stamp(-20 * 86400), "tons": {"Diamond": 50}, "amount_at_start": "High"}]}}
    check("8 Depleted on a cycle past 14 d: not closed as depleted",
          yields.close(stale), False)
    check("8 it ended expired, not a measurement",
          (yields.cycles(stale)[0]["ended"], yields.measured(stale)), ("expired", []))

    # 9. regrow(): a Depleted mark 15 days old comes off, Amount 'Depleted'
    #    becomes unread, the cycles stay; a fresh mark stays.
    spotcard.save(dict(row(alex), depleted_at=_stamp(-15 * 86400), amount="Depleted"), id=alex)
    check("9 regrow takes off the old mark only", yields.regrow(), 1)
    check("9 old mark gone", row(alex).get("depleted_at"), None)
    check("9 Amount Depleted -> unread", row(alex).get("amount"), None)
    check("9 cycles kept", len(yields.cycles(row(alex))), 1)
    check("9 fresh mark stays", bool(row(diamond).get("depleted_at")), True)
    check("9 the old date is kept in regrown",
          [entry["depleted_at"][:10] for entry in row(alex).get("regrown", [])],
          [_stamp(-15 * 86400)[:10]])
    hud = spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT,
                         "longitude": LON, "planet_radius": RADIUS, "commodity": "Opal",
                         "amount": "Depleted", "marked_at": _stamp(-16 * 86400)})
    check("9 Amount Depleted off the HUD, 16 d old, regrows too", yields.regrow(), 1)
    check("9 and reads unread", row(hud).get("amount"), None)

    # 10. RhinoData open while mining: Mined set in place once the tons stop.
    import time
    import tkinter as tk
    from rs_core import bodies, spotmark
    from rs_ui import main, scan
    main.QUIET_S = 0.3
    root = tk.Tk()
    root.withdraw()
    main.build(root)
    main._cancel_landed()
    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "metal-rich", "distance": 10.0,
                             "locations": 7, "volcanism": "", "planet_class": "Metal rich body"}])
    fresh = bookmark("Diamond", LAT, _metres_east(LAT, LON, 3000.0, RADIUS))
    folded = spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT,
                            "longitude": _metres_east(LAT, LON, 6000.0, RADIUS),
                            "planet_radius": RADIUS, "commodity": "Diamond", "rigs": 2,
                            "location_index": 2, "marked_at": _stamp(0)})
    status(LAT, _metres_east(LAT, LON, 3000.0, RADIUS))
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=1)
    window.geometry("+-4000+-4000")
    scan._state["selected"] = scan._key(row(fresh))
    scan._draw()
    draws = []
    real_draw = scan._draw

    def counted():
        start = time.perf_counter()
        real_draw()
        draws.append(time.perf_counter() - start)
    scan._draw = counted

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            time.sleep(0.01)

    def burst(tons):
        for _ in range(tons):
            load.journal_entry("E2E", False, SYSTEM, None,
                               dict(diamond_line, timestamp=_stamp(0)), {})
            pump(0.1)

    diamond_line = next(e for e in refined if spotmark.refined_material(e) == "Diamond")
    key = scan._key(row(fresh))
    check("10 the fresh bookmark's row is drawn", key in scan._mined, True)
    check("10 a folded location's row is not drawn", scan._key(row(folded)) in scan._mined, False)
    label = scan._mined.get(key)
    pump(0.2)
    draws.clear()
    burst(3)
    check("10 nothing while tons keep coming", len(draws), 0)
    pump(0.6)
    check("10 first burst: card had no tons line, one _draw", len(draws), 1)
    check("10 the tons are in the row by then",
          yields.cycles(row(fresh))[-1]["tons"], {"Diamond": 3})
    label = scan._mined[key]
    card = scan._card_tons["label"]
    draws.clear()
    real = scan.refresh_mined
    spent = []

    def timed():
        start = time.perf_counter()
        real()
        spent.append(time.perf_counter() - start)
    scan.refresh_mined = timed
    main.scan.refresh_mined = timed
    burst(2)
    pump(0.6)
    check("10 second burst: no _draw", len(draws), 0)
    check("10 same Mined widget, new tons", (scan._mined[key] is label,
                                             label.cget("text").strip()), (True, "5 t"))
    check("10 same card tons widget, new text", (scan._card_tons["label"] is card,
                                                 card.cget("text").split(" t")[0]), (True, "5"))
    scan._draw()
    print(f"     _draw {draws[-1] * 1000:.1f} ms, in place {spent[-1] * 1000:.1f} ms")
    load.journal_entry("E2E", False, SYSTEM, None,
                       dict(diamond_line, timestamp="2020-01-01T00:00:00Z"), {})
    check("10 a replayed ton schedules nothing", main._quiet, None)
    window.destroy()
    burst(1)
    try:
        pump(0.6)
        raised = None
    except Exception as err:                 # noqa: BLE001 - any raise is the failure
        raised = repr(err)
    check("10 window closed: timer flushes, no raise",
          (raised, main._quiet, yields.cycles(row(fresh))[-1]["tons"]),
          (None, None, {"Diamond": 6}))
    root.destroy()

    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]"))
    return 0 if all(ok for _, ok, _ in results) else 1


def _stamp(offset_s):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _restamp(entries):
    """The same lines, stamped now: main._refined drops anything older than the
    plugin start, which scenario 4 tests."""
    return [dict(entry, timestamp=_stamp(0)) for entry in entries]


def _refined_lines(path):
    found = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("event") == "MiningRefined":
                found.append(entry)
    return found


# ---------------------------------------------------------------- the parent


def main():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(HERE, "out", stamp)
    os.makedirs(out, exist_ok=True)

    source = _find_journal()
    if source is None:
        print(f"{JOURNAL} not found under the journal folder - nothing to replay")
        return 1
    shutil.copy2(source, os.path.join(out, JOURNAL))

    env = dict(os.environ, LOCALAPPDATA=out, E2E_LOG=os.path.join(out, "plugin.log"),
               PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"],
                         cwd=PLUGIN, env=env, capture_output=True, text=True,
                         encoding="utf-8")
    report = run.stdout + (f"\n--- stderr ---\n{run.stderr}" if run.stderr else "")

    cli = subprocess.run([sys.executable, "-m", "rs_core.yields"], cwd=PLUGIN, env=env,
                         capture_output=True, text=True, encoding="utf-8")
    report += f"\n--- python -m rs_core.yields ---\n{cli.stdout}{cli.stderr}"
    ok = run.returncode == 0 and "t/rig" in cli.stdout
    report += f"\nresult: {'PASS' if ok else 'FAIL'}\n"

    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    print(out)
    return 0 if ok else 1


def _find_journal():
    sys.path.insert(0, PLUGIN)
    from rs_core import paths
    candidate = os.path.join(paths.journal_dir(), JOURNAL)
    return candidate if os.path.isfile(candidate) else None


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    raise SystemExit(main())
