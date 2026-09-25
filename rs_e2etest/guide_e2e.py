"""E2E harness: the guide arrow ends after HERE with the game in the background,
and the card's button follows. Checks and blind spots: guide.md.

Run from the plugin folder:  python rs_e2etest/guide_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
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
from rs_ui import main, overlay, scan                           # noqa: E402

assert database.PATH.startswith(OUT), database.PATH
paths.journal_dir = lambda: OUT
coverage.clear_old_textures = lambda: None

SYSTEM = "Hyperion Reach AB-C d1-42"
BODY = f"{SYSTEM} 4 a"
RADIUS = 1352744.5
LAT, LON = 12.4, -98.7
FOCUS = [True]
overlay.game_focused = lambda: FOCUS[0]
overlay._game_rect = lambda: (0, 0, 1920, 1080)
overlay.HERE_MS = 600
overlay.POLL_MS = 100


def east(metres):
    return LON + math.degrees(metres / (RADIUS * math.cos(math.radians(LAT))))


def status(lon):
    with open(os.path.join(OUT, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"BodyName": BODY, "Latitude": LAT, "Longitude": lon, "Altitude": 0,
                   "PlanetRadius": RADIUS, "Flags": coverage.IN_SRV, "Heading": 0}, handle)


results = []


def check(name, got, want):
    results.append((name, got == want, f"{got!r} != {want!r}"))


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def button():
    """The card's arrow button text, or None."""
    stack = [scan._panes.get("card")] if scan._panes.get("card") else []
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if isinstance(widget, tk.Button) and widget.cget("text") in ("Stop the arrow",
                                                                     "Guide me there"):
            return widget.cget("text")
    return None


main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
register = bodies.Register()
register.adopt(SYSTEM, [{"name": BODY, "ground": "rock 80%+ [silicate vapour geysers]",
                         "distance": 1284.0, "locations": 22, "volcanism": "",
                         "planet_class": "Rocky body"}])

try:
    spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT, "longitude": LON,
                   "planet_radius": RADIUS, "commodity": "Monazite", "rigs": 3,
                   "location_index": 9, "marked_at": "2026-09-25T10:00:00+00:00"})
    record = cards.for_system(SYSTEM)[0]
    status(east(3000.0))
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=9)
    window.geometry("+-4000+-4000")
    scan._pick_record(record)
    pump(0.2)

    def run(name, focus_steps, arrived=True):
        # Down first: a leftover arrow would make _toggle_guide switch it off, and
        # the run would pass without the arrow ever ending on its own.
        overlay.stop()
        pump(0.1)
        status(LON if arrived else east(3000.0))
        FOCUS[0] = focus_steps[0][0]
        scan._toggle_guide(record)
        pump(0.1)
        started = (overlay.guiding(), button())
        for focus, seconds in focus_steps:
            FOCUS[0] = focus
            pump(seconds)
        return started, (overlay.guiding(), button())

    started, ended = run("A", [(False, 1.5)])
    check("A arrived with the game in the background: arrow up, card says Stop",
          started, (True, "Stop the arrow"))
    check("A ... and after HERE_MS: arrow down, card says Guide", ended,
          (False, "Guide me there"))

    _, ended = run("B", [(True, 0.3), (False, 1.5)])
    check("B HERE seen, then the game loses focus: arrow down, card says Guide", ended,
          (False, "Guide me there"))

    _, ended = run("C", [(True, 1.5)])
    check("C game in front, arrived: arrow down after HERE_MS", ended, (False, "Guide me there"))

    started, ended = run("D", [(False, 1.5)], arrived=False)
    check("D not arrived, game in the background: the arrow stays", ended,
          (True, "Stop the arrow"))
    overlay.stop()
except Exception:
    results.append(("harness ran without an exception", False, traceback.format_exc()))
finally:
    root.destroy()

lines = [f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]")
         for name, ok, detail in results]
ok = all(passed for _, passed, _ in results) and bool(results)
lines.append(f"\nresult: {'PASS' if ok else 'FAIL'}")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print("\n".join(lines))
print(OUT)
raise SystemExit(0 if ok else 1)
