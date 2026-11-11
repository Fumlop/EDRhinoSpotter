"""E2E harness: still depleted vs depleted again (issue 21). Checks and blind spots: recheck.md.

Run from the plugin folder:  python rs_e2etest/recheck_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
JOURNALS = os.path.join(OUT, "journals")
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.makedirs(JOURNALS)
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk                                                # noqa: E402

from rs_core import bodies, cards, coverage, database, paths, spotcard, yields  # noqa: E402
from rs_ui import main, scan                                        # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E Recheck", "E2E Recheck 1 a"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0
DAY = 86400

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def stamp(offset_s=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def east(metres):
    return LON + math.degrees(metres / (RADIUS * math.cos(math.radians(LAT))))


def status(lon):
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": 0x200000 | 0x10, "BodyName": BODY, "Latitude": LAT,
                   "Longitude": lon, "Altitude": 0, "PlanetRadius": RADIUS, "Heading": 0}, handle)


def seed(material, lon, depleted_days, rechecks_days=()):
    """A bookmark mined out `depleted_days` ago: one closed 50 t cycle."""
    depleted = stamp(-depleted_days * DAY)
    looks = {"rechecks": [stamp(-d * DAY) for d in rechecks_days]} if rechecks_days else {}
    return spotcard.save({**looks,
        "system": SYSTEM, "planet_name": BODY, "latitude": LAT, "longitude": lon,
        "planet_radius": RADIUS, "commodity": material, "rigs": 4, "amount": "High",
        "density": "Medium", "location_index": 1, "marked_at": stamp(-(depleted_days + 2) * DAY),
        "depleted_at": depleted,
        "yield": {"cycles": [{"from": stamp(-(depleted_days + 1) * DAY), "to": depleted,
                              "tons": {material: 50}, "rigs": 4, "density": "Medium",
                              "amount_at_start": "High", "ended": "depleted",
                              "ended_at": depleted}]}})


def row(id):
    with database.connect() as conn:
        return dict(json.loads(conn.execute("SELECT data FROM bookmarks WHERE id = ?",
                                            (id,)).fetchone()[0]), id=id)


def widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from widgets(child)


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def pump_until(until, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.05)
    return False


def show(id):
    """Select bookmark `id` in the scan window and draw its card."""
    record = next(r for r in cards.for_system(SYSTEM) if r.get("id") == id)
    scan._state["selected"] = scan._key(record)
    scan._draw()
    pump()


def press(id, text):
    """The card's own button labelled `text`, pressed. False when not on the card."""
    show(id)
    button = next((w for w in widgets(window)
                   if isinstance(w, tk.Button) and w.cget("text") == text), None)
    if button is None:
        return False
    button.invoke()
    pump()
    return True


def card_line(prefix):
    """(text, fits) of the card label starting with `prefix`, or (None, None)."""
    for w in widgets(window):
        if isinstance(w, tk.Label) and str(w.cget("text")).startswith(prefix):
            room = w.master.winfo_width() - 2 * 13
            return w.cget("text"), w.winfo_reqwidth() <= room
    return None, None


def refine(material, lon, tons):
    status(lon)
    for _ in range(tons):
        main.journal_entry("E2E", False, SYSTEM, None,
                           {"event": "MiningRefined", "timestamp": stamp(),
                            "Type": f"${material.lower()}_name;", "Type_Localised": material}, {})
    yields.TALLY.flush()


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
yields.TALLY._writes.delay = 0.05
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.withdraw()
window = None

try:
    main.build(root)
    main._cancel_landed()
    hud_material = main._materials()[0]

    one = seed("Opal", east(0), 41)
    two = seed("Diamond", east(300), 41)
    three_a = seed("Opal", east(600), 50, rechecks_days=(8,))
    three_b = seed("Painite", east(900), 50, rechecks_days=(6,))
    four = seed(hud_material, east(1200), 41)
    five = seed("Ruby", east(1500), 41)
    six = seed("Opal", east(1800), 20)
    seven = seed("Painite", east(2100), 3)
    eight = seed("Ruby", east(2400), 30, rechecks_days=(8,))
    edge13, edge14 = seed("Opal", east(2700), 13.9), seed("Opal", east(3000), 14.01)
    edge39, edge40 = seed("Diamond", east(3300), 39.9), seed("Diamond", east(3600), 40.01)
    original = {id: row(id)["depleted_at"]
                for id in (one, two, three_a, three_b, four, five, six, seven, eight,
                           edge13, edge14, edge39, edge40)}

    lifted = yields.regrow()
    check("0 regrow lifts 41 d / 40.01 d marks and the 8 d look on 50 d, nothing else",
          lifted == 6, f"{lifted} lifted")
    check("8 30 d mark, 8 d look: stays until 40 d",
          row(eight).get("depleted_at") == original[eight], row(eight).get("depleted_at"))
    check("edge 39.9 d stays, 40.01 d lifted",
          (row(edge39).get("depleted_at") == original[edge39], row(edge40).get("depleted_at"))
          == (True, None), (row(edge39).get("depleted_at"), row(edge40).get("depleted_at")))
    check("6 20 d mark stays", row(six).get("depleted_at") == original[six],
          row(six).get("depleted_at"))
    check("3 6 d look: mark stays", row(three_b).get("depleted_at") == original[three_b],
          row(three_b).get("depleted_at"))
    check("3 8 d look: lifted, regrown keeps the original date",
          [e["depleted_at"] for e in row(three_a).get("regrown") or []] == [original[three_a]],
          row(three_a).get("regrown"))

    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "metal-rich", "distance": 10.0,
                             "locations": 7, "volcanism": "", "planet_class": "Metal rich body"}])
    status(east(0))
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=1)
    window.geometry("+-4000+-4000")
    pump()

    # 1. no tons since the lift
    check("1 card offers Mark depleted", press(one, "Mark depleted"))
    r = row(one)
    check("1 original depleted_at back", r.get("depleted_at") == original[one],
          f"{r.get('depleted_at')} vs {original[one]}")
    check("1 one look logged", len(r.get("rechecks") or []) == 1, r.get("rechecks"))
    check("1 regrown entry kept", [e["depleted_at"] for e in r.get("regrown") or []]
          == [original[one]], r.get("regrown"))
    check("1 status line", scan._state["status"].endswith("still depleted, look again in 7 d."),
          scan._state["status"])
    text, fits = card_line("still depleted")
    check("1 card line", text == "still depleted at 41 d, look again in 7 d", text)
    check("1 card line fits the card", fits, text)
    check("1 card button now Set active", any(isinstance(w, tk.Button) and w.cget("text") == "Set active"
                                              for w in widgets(window)))
    check("1 a jump right after does not lift it", yields.regrow() == 0)

    # 3. the 6 d look on the card, the 8 d one pressed again
    show(three_b)
    text, _ = card_line("still depleted")
    check("3 6 d look card line", text == "still depleted at 44 d, look again in 1 d", text)
    press(three_a, "Mark depleted")
    r = row(three_a)
    check("3 second round: original date back", r.get("depleted_at") == original[three_a],
          r.get("depleted_at"))
    check("3 second round: two looks logged", len(r.get("rechecks") or []) == 2, r.get("rechecks"))

    # 2. tons since the lift: depleted again
    refine("Diamond", east(300), 3)
    check("2 3 t in a new open cycle",
          (yields.open_cycle(row(two)) or {}).get("tons") == {"Diamond": 3},
          yields.cycles(row(two)))
    press(two, "Mark depleted")
    r = row(two)
    check("2 new depleted_at today", (r.get("depleted_at") or "")[:10] == stamp()[:10],
          r.get("depleted_at"))
    check("2 no look logged", not r.get("rechecks"), r.get("rechecks"))
    check("2 status says marked depleted", scan._state["status"].endswith("marked depleted."),
          scan._state["status"])
    check("2 card shows the plain countdown", card_line("0 d since")[0] is not None
          and card_line("still depleted")[0] is None, card_line("still depleted")[0])

    # 4. HUD path: Amount Depleted re-marked from the panel
    main._material.set(hud_material)
    main._amount.set("Depleted")
    main._loc.set("1")
    status(east(1200))
    main.make_card()
    check("4 re-mark written", pump_until(lambda: row(four).get("depleted_at") is not None),
          row(four))
    r = row(four)
    check("4 original depleted_at back", r.get("depleted_at") == original[four],
          f"{r.get('depleted_at')} vs {original[four]}")
    check("4 one look logged", len(r.get("rechecks") or []) == 1, r.get("rechecks"))

    # 1c. undo of a look: Set active, Mark depleted keeps the original date
    press(one, "Mark depleted")
    press(one, "Set active")
    press(one, "Mark depleted")
    r = row(one)
    check("1c undo of a look: original date back", r.get("depleted_at") == original[one],
          r.get("depleted_at"))

    # 5. undo on a fresh depletion after a lift
    refine("Ruby", east(1500), 3)
    press(five, "Mark depleted")
    press(five, "Set active")
    check("5 Set active clears the mark", row(five).get("depleted_at") is None,
          row(five).get("depleted_at"))
    press(five, "Mark depleted")
    r = row(five)
    check("5 undo: depleted_at today", (r.get("depleted_at") or "")[:10] == stamp()[:10],
          r.get("depleted_at"))
    check("5 undo: no look logged", not r.get("rechecks"), r.get("rechecks"))

    # 6. 14-40 d: still depleted, card says it may be back at Low; under 14 d: countdown
    show(six)
    text, fits = card_line("20 d")
    check("6 card line", text == "20 d: may be Low (unlikely), back at 40 d", text)
    check("6 card line fits the card", fits, text)
    check("6 card button Set active", any(isinstance(w, tk.Button) and w.cget("text") == "Set active"
                                          for w in widgets(window)))
    show(seven)
    text, fits = card_line("3 d")
    check("7 card line", text == "3 d since, back after 40 d (assumed)", text)
    check("7 card line fits the card", fits, text)

    show(eight)
    text, fits = card_line("still depleted")
    check("8 card line: count to day 40, not look + 7",
          text == "still depleted at 22 d, look again in 10 d", text)
    check("8 card line fits the card", fits, text)
    show(edge13)
    check("edge 13.9 d: countdown, not the hint",
          (card_line("14 d since")[0], card_line("14 d:")[0])
          == ("14 d since, back after 40 d (assumed)", None), card_line("14 d")[0])
    show(edge14)
    check("edge 14.01 d: hint", card_line("14 d:")[0] == "14 d: may be Low (unlikely), back at 40 d",
          card_line("14 d")[0])
    show(edge39)
    text, fits = card_line("40 d:")
    check("edge 39.9 d: hint, fits", text == "40 d: may be Low (unlikely), back at 40 d" and fits, text)

    # 10. a ton at a still-marked bookmark: from REGEN_DAYS it lifts the mark, under it is leftover
    late = seed("Monazite", east(5000), 20)
    early = seed("Bromellite", east(5300), 10)
    was = {id: row(id)["depleted_at"] for id in (late, early)}
    refine("Monazite", east(5000), 3)
    r = row(late)
    check("10 20 d mark, 3 t: mark lifted", r.get("depleted_at") is None, r.get("depleted_at"))
    check("10 regrown keeps the original date",
          [e.get("depleted_at") for e in r.get("regrown") or []] == [was[late]], r.get("regrown"))
    check("10 3 t in a new open cycle, the closed one untouched",
          [(c.get("ended"), sum(c["tons"].values())) for c in yields.cycles(r)]
          == [("depleted", 50), (None, 3)], yields.cycles(r))
    press(late, "Mark depleted")
    r = row(late)
    check("10 Depleted press after: new depleted_at today, no look",
          ((r.get("depleted_at") or "")[:10], r.get("rechecks")) == (stamp()[:10], None),
          (r.get("depleted_at"), r.get("rechecks")))
    check("10 status says marked depleted", scan._state["status"].endswith("marked depleted."),
          scan._state["status"])
    refine("Bromellite", east(5300), 3)
    r = row(early)
    check("11 10 d mark, 3 t: mark stays, tons are leftovers in the closed cycle",
          (r.get("depleted_at"), [(c.get("ended"), sum(c["tons"].values())) for c in yields.cycles(r)])
          == (was[early], [("depleted", 53)]), (r.get("depleted_at"), yields.cycles(r)))

    # 1b. the look pressed in 1, 6 d and 8 d on
    yields.regrow(now=stamp(6 * DAY))
    check("1b 6 d after the look: mark stays", row(one).get("depleted_at") == original[one],
          row(one).get("depleted_at"))
    yields.regrow(now=stamp(8 * DAY))
    check("1b 8 d after the look: lifted, original date in regrown",
          row(one).get("depleted_at") is None
          and [e["depleted_at"] for e in row(one).get("regrown") or []] == [original[one]] * 2,
          row(one))
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    main.stop()
    if window is not None:
        window.destroy()
    root.destroy()

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
report = "\n".join(lines)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(OUT)
sys.exit(1 if failed else 0)
