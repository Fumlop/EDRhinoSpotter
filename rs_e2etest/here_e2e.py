"""E2E harness: RhinoData marks and picks the bookmark the ship is at.

Run from the plugin folder:  python rs_e2etest/here_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA and the journal folder are the run folder; Status.json is written
by the harness. The window is drawn off-screen (-4000, -4000).

Ways it can fail end to end:
1. At a bookmark on open: its row is not marked, the card is on another one,
   or its folded location stays folded.
2. 200 m off every bookmark (over yields.ATTRIBUTE_M, 175 m): something is marked.
3. Two bookmarks in range: the farther one is picked.
4. Moved to another bookmark, window brought to the front (<Activate>): the
   pick does not follow.
5. Brought to the front at the same spot: the window redraws anyway, or a
   bookmark picked by hand meanwhile is taken away.
6. A system browsed from the search box: the pick jumps back to the ship's.
7. Status.json torn mid-write: an exception, or the mark dropped for one bad read.
8. In the ship or on foot at a bookmark: it is marked (SRV only).
9. Out of the SRV and back in at the same spot: a hand pick is taken away.
10. Opened with the panel's Location at 22, not at a bookmark: a location
    other than 22 unfolded, or 22 folded.
11. Opened with no Location and no bookmark in range: any location unfolded.
12. A location unfolded by hand folds again on the next draw.
"""

import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(OUT, exist_ok=True)
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)

import tkinter as tk                                            # noqa: E402

from rs_core import bodies, cards, coverage, database, paths, spotcard  # noqa: E402

IN_SRV = coverage.IN_SRV
from rs_ui import main, scan                                    # noqa: E402

assert database.PATH.startswith(OUT), database.PATH
paths.journal_dir = lambda: OUT
coverage.clear_old_textures = lambda: None

SYSTEM = "Hyperion Reach AB-C d1-42"
BODY = f"{SYSTEM} 4 a"
RADIUS = 1352744.5
LAT, LON = 12.4, -98.7


def east(metres):
    return LON + math.degrees(metres / (RADIUS * math.cos(math.radians(LAT))))


def status(lat, lon, body=BODY, flags=IN_SRV):
    with open(os.path.join(OUT, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"BodyName": body, "Latitude": lat, "Longitude": lon, "Altitude": 0,
                   "PlanetRadius": RADIUS, "Flags": flags}, handle)


def mark(material, lon, location):
    spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT, "longitude": lon,
                   "planet_radius": RADIUS, "commodity": material, "rigs": 3,
                   "amount": "High", "density": "Low", "location_index": location,
                   "marked_at": f"2026-09-24T10:00:0{location}+00:00"})


results = []


def check(name, got, want):
    results.append((name, got == want, f"{got!r} != {want!r}"))


def marked_rows(window):
    """Material names of the rows drawn with scan.HERE_MARK."""
    found, stack = [], [window]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if isinstance(widget, tk.Label) and str(widget.cget("text")).startswith(scan.HERE_MARK):
            found.append(str(widget.cget("text"))[len(scan.HERE_MARK):].split()[0])
    return found


def picked():
    selected = scan._state["selected"]
    return selected[2] if selected else None


main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
register = bodies.Register()
register.adopt(SYSTEM, [{"name": BODY, "ground": "rock 80%+ [silicate vapour geysers]",
                         "distance": 1284.0, "locations": 22, "volcanism": "",
                         "planet_class": "Rocky body"}])
draws = []
real_draw = scan._draw


def counted_draw():
    draws.append(1)
    real_draw()


scan._draw = counted_draw


def front(window):
    window.event_generate("<Activate>")
    for _ in range(10):
        root.update()


try:
    mark("Monazite", LON, 9)                 # 0 m
    mark("Jadeite", east(120.0), 22)          # 120 m
    mark("Olivine", east(1000.0), 15)         # 1 km

    # 1 + 3: at the Monazite (0 m); the Jadeite is also in range at 120 m.
    status(LAT, LON)
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",))
    window.geometry("+-4000+-4000")
    for _ in range(20):
        root.update()
    check("1 row marked on open", marked_rows(window), ["Monazite"])
    check("1+3 card on the nearest bookmark", picked(), "Monazite")
    check("1 its location unfolded, no other", scan._state["opened"], {(BODY, 9)})

    # 4: drove to the Olivine, window to the front.
    status(LAT, east(1000.0))
    front(window)
    check("4 pick follows to the Olivine", (picked(), marked_rows(window)),
          ("Olivine", ["Olivine"]))

    # 5: same spot, picked the Jadeite by hand, window to the front again.
    scan._state["selected"] = scan._key(
        next(r for r in cards.for_system(SYSTEM) if r["commodity"] == "Jadeite"))
    before = len(draws)
    front(window)
    check("5 same spot: no redraw", len(draws) - before, 0)
    check("5 a hand pick is kept", picked(), "Jadeite")

    # 2: 200 m past the Olivine - nothing in range.
    status(LAT, east(1200.0))
    front(window)
    check("2 200 m off: nothing marked", marked_rows(window), [])

    # 8: same spot, in the ship (Flags without InSRV): nothing marked.
    status(LAT, LON, flags=0)
    front(window)
    check("8 in the ship at a bookmark: nothing marked", marked_rows(window), [])

    # 9: at the Monazite in the SRV, pick the Jadeite by hand, leave the SRV and
    #    get back in at the same spot: the hand pick stays.
    status(LAT, LON)
    front(window)
    scan._state["selected"] = scan._key(
        next(r for r in cards.for_system(SYSTEM) if r["commodity"] == "Jadeite"))
    status(LAT, LON, flags=0)
    front(window)
    status(LAT, LON)
    front(window)
    check("9 back in the SRV at the same spot: hand pick kept", picked(), "Jadeite")
    check("9 and the row is marked again", marked_rows(window), ["Monazite"])

    # 6: a browsed system: the ship's spot does not pull the pick back.
    status(LAT, LON)
    scan._state["system"] = "Somewhere Else"
    check("6 browsed system: _mark_here does nothing", scan._mark_here(), False)
    scan._state["system"] = None

    # 7: Status.json torn mid-write.
    with open(os.path.join(OUT, "Status.json"), "w", encoding="utf-8") as handle:
        handle.write('{"BodyName": "Hyp')
    try:
        front(window)
        raised = None
    except Exception as err:                 # noqa: BLE001 - any raise is the failure
        raised = repr(err)
    check("7 torn Status.json: no raise, the last known mark kept",
          (raised, marked_rows(window)), (None, ["Monazite"]))

    def reopen(location):
        window.destroy()
        opened = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                           materials=("All",), here=BODY, location=location)
        opened.geometry("+-4000+-4000")
        for _ in range(20):
            root.update()
        return opened

    def arrows(window):
        """(unfolded, folded) location lines drawn."""
        found, stack = [], [window]
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            if isinstance(widget, tk.Label) and widget.cget("text") in ("▼", "▶"):
                found.append(widget.cget("text"))
        return found.count("▼"), found.count("▶")

    # 10: 5 km off every bookmark, the panel's Location at 22.
    status(LAT, east(5000.0))
    window = reopen(22)
    check("10 Location 22: only 22 unfolded", (scan._state["opened"], arrows(window)),
          ({(BODY, 22)}, (1, 2)))
    # 11: no Location, nothing in range.
    window = reopen(None)
    check("11 no Location: every location folded", (scan._state["opened"], arrows(window)),
          (set(), (0, 3)))
    # 12: unfolded by hand, then a redraw.
    scan._fold(BODY, 15)
    scan._draw()
    root.update()
    check("12 hand unfold survives a redraw", ((BODY, 15) in scan._state["opened"],
                                               arrows(window)), (True, (1, 2)))
except Exception:
    results.append(("harness ran without an exception", False, traceback.format_exc()))
finally:
    root.destroy()

lines = [f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]")
         for name, ok, detail in results]
ok = all(passed for _, passed, _ in results)
lines.append(f"\nresult: {'PASS' if ok else 'FAIL'}")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print("\n".join(lines))
print(OUT)
raise SystemExit(0 if ok else 1)
