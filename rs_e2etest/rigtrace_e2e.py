"""E2E harness: plan rigs from a driven border, guide to each (Ctrl+Alt+R / Ctrl+Alt+P). Checks: rigtrace.md.

Run from the plugin folder:  python rs_e2etest/rigtrace_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; RHINOSPOTTER_DEBUG is cleared.
Input: rs_e2etest/data/trace-20260929-095343.csv, a real lap (91 fixes, 1 Hz).
"""

import csv
import json
import math
import os
import sys
import time
import tkinter as tk
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
JOURNALS = os.path.join(OUT, "journals")
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.makedirs(JOURNALS)
os.environ["LOCALAPPDATA"] = OUT
os.environ.pop("RHINOSPOTTER_DEBUG", None)
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

from rs_core import coverage, database, guide, paths, rigplan       # noqa: E402
from rs_core.logging import DEBUG                                   # noqa: E402
from rs_ui import hotkey, minimap, overlay, press, rigradar, tracelog  # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

STEP_S = 0.05
SRC = os.path.join(HERE, "data", "trace-20260929-095343.csv")
with open(SRC, encoding="utf-8") as handle:
    ROWS = list(csv.DictReader(handle))
R = float(ROWS[0]["radius"])
LAT0, LON0 = float(ROWS[0]["lat"]), float(ROWS[0]["lon"])
BODY = "Test 1 a"
STATUS = os.path.join(JOURNALS, "Status.json")
paths.journal_dir = lambda: JOURNALS
overlay.HERE_MS = 600
overlay.game_focused = lambda: True          # draw although Elite is not in front
minimap.in_rhino = lambda: True

results = []


def check(tag, name, ok, detail=""):
    results.append((f"{tag} {name}", bool(ok), detail))


def ll(x, y):
    """Local m east/north -> (lat, lon)."""
    return LAT0 + math.degrees(y / R), LON0 + math.degrees(x / (R * math.cos(math.radians(LAT0))))


def xy(lat, lon):
    return math.radians(lon - LON0) * R * math.cos(math.radians(LAT0)), math.radians(lat - LAT0) * R


def write(lat, lon, heading=0.0, body=BODY):
    with open(STATUS, "w", encoding="utf-8") as handle:
        json.dump({"BodyName": body, "Latitude": lat, "Longitude": lon, "Heading": heading,
                   "Altitude": 0, "PlanetRadius": R, "Flags": coverage.IN_SRV}, handle)


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def fresh():
    tracelog._plan = []
    overlay.stop()
    tracelog._close_window()


def drive(points):
    """Feed (lat, lon, heading) fixes; the index the lap closed at, or None."""
    for i, (lat, lon, heading) in enumerate(points):
        write(lat, lon, heading)
        pump(STEP_S)
        if i == 0:
            tracelog.toggle(root)
            pump(0.1)
        elif not tracelog.active():
            return i
    return None


def wait_plan(seconds=30):
    t = time.time()
    while not tracelog._plan and time.time() - t < seconds:
        pump(0.1)
        if tracelog._window is not None and "no rig fits" in tracelog._label.cget("text"):
            break
    return time.time() - t


def rig_press(x, y, body=BODY, seconds=2.5):
    """A long press in the Rhino at local (x, y), through press.released like the mouse thread."""
    write(*ll(x, y), body=body)
    press.released(root, "left", __import__("datetime").datetime.now(), seconds)
    pump(0.3)


root = tk.Tk()
root.withdraw()
real = [(float(r["lat"]), float(r["lon"]), float(r["heading"])) for r in ROWS]

try:
    # K: the keys are a feature, not lab
    names = {key_id: name for key_id, name, _, _ in hotkey.ACTIONS}
    check("K1", "Plan rigs and Next rig in Settings without RHINOSPOTTER_DEBUG",
          not DEBUG and names.get(hotkey.TRACE) == "Plan rigs (drive the border)"
          and names.get(hotkey.PLACED) == "Next rig", names)
    check("K2", "chat commands without RHINOSPOTTER_DEBUG",
          (hotkey.chat_command(hotkey.TRACE), hotkey.chat_command(hotkey.PLACED))
          == ("!rs trace", "!rs placed"),
          (hotkey.chat_command(hotkey.TRACE), hotkey.chat_command(hotkey.PLACED)))

    # F2: out 20 m and back = 40 m < 60 m
    fresh()
    pts = [ll(0, y) + (0,) for y in range(0, 21, 5)] + [ll(0, y) + (180,) for y in range(20, -1, -5)]
    check("F2", "no snap under 60 m", drive(pts) is None and tracelog.active(), f"{len(pts)} fixes")
    tracelog.shutdown()
    # F3: 40 m square ending 15 m from the start
    fresh()
    sq = ([(x, 0) for x in range(0, 41, 5)] + [(40, y) for y in range(5, 41, 5)]
          + [(x, 40) for x in range(35, -1, -5)] + [(0, y) for y in range(35, 14, -5)])
    check("F3", "no snap 15 m off start", drive([ll(*p) + (0,) for p in sq]) is None
          and tracelog.active(), "path 145 m")
    tracelog.shutdown()
    # F4: the key half way round closes and plans
    fresh()
    drive(real[:50])
    was = tracelog.active()
    tracelog.toggle(root)
    wait_plan()
    check("F4", "key press closes lap and plans", was and not tracelog.active() and tracelog._plan,
          f"{len(tracelog._plan)} rigs from 50 fixes")
    # F15: 5 m circle twice: snaps, nothing fits, says what to do
    fresh()
    circ = [ll(5 * math.cos(a / 8 * 2 * math.pi) - 5, 5 * math.sin(a / 8 * 2 * math.pi)) + (0,)
            for a in range(17)]
    closed = drive(circ + circ)
    wait_plan(10)
    note = tracelog._label.cget("text") if tracelog._window is not None else ""
    check("F15", "tiny lap: 0 rigs, says trace the whole border",
          closed is not None and not tracelog._plan and note == "no rig fits here\ntrace the whole border",
          note)

    # Main run on the real lap
    fresh()
    closed = drive(real)
    check("F1", "real lap snaps by itself", closed is not None, f"at fix {closed} of {len(real)}")
    took = wait_plan()
    plan = list(tracelog._plan)
    check("F5", "plan arrives", plan, f"{len(plan)} rigs in {took:.1f} s")
    spots = [xy(p["latitude"], p["longitude"]) for p in plan]
    poly = [xy(la, lo) for la, lo, _ in real[:closed + 1]]
    gaps = [math.dist(a, b) for i, a in enumerate(spots) for b in spots[i + 1:]]
    check("F6", f"rigs >= {rigplan.SPACING_M:.0f} m apart",
          all(g >= rigplan.SPACING_M - 0.5 for g in gaps), f"min {min(gaps):.1f} m" if gaps else "")
    check("F7", "rigs inside the outline", all(rigplan._inside(poly, *s) for s in spots))
    check("F16", "known 4-rig spot gives 4", len(plan) == 4, f"{len(plan)} rigs")
    pump(0.7)
    texts = ([overlay._canvas.itemcget(i, "text") for i in overlay._canvas.find_all()
              if overlay._canvas.type(i) == "text"] if overlay._canvas else [])
    here_lat, here_lon, _ = real[closed]
    want = guide.metres(guide.distance(here_lat, here_lon, plan[0]["latitude"], plan[0]["longitude"], R))
    check("F8", "overlay on rig 1 shows distance", overlay.guiding(plan[0]) and want in texts,
          f"texts {texts}, want {want!r}")
    check("F18", "caption: place it, or the key to skip",
          plan[0]["caption"] == "rig 1 of 4: place it here, or Ctrl+Alt+P to skip", plan[0]["caption"])

    def park(k, off):
        x, y = spots[k]
        write(*ll(x, y + off))
        pump(0.8)

    park(0, 4.0)
    check("F10", "4 m off rig 1: no HERE", overlay._here is None and tracelog._step == 0)
    park(0, 2.0)
    check("F11", "2 m off rig 1: HERE", overlay._here is not None)
    pump(1.5)
    check("F17", "HERE held past HERE_MS without a rig", tracelog._step == 0
          and overlay.guiding(plan[0]) and overlay._here is not None)

    # G: the rig placed in the game moves the arrow
    x, y = spots[0]
    rig_press(x + 60, y)
    check("G1", "rig press 60 m from rig 1: arrow stays", tracelog._step == 0, f"step {tracelog._step}")
    rig_press(x + 5, y, body="Other 2 b")
    check("G2", "rig press on another body: arrow stays", tracelog._step == 0, f"step {tracelog._step}")
    rig_press(x + 2, y, seconds=1.0)
    check("G3", "1 s press (not a rig): arrow stays", tracelog._step == 0, f"step {tracelog._step}")
    rig_press(x + 10, y)
    check("G4", "rig press 10 m from rig 1: arrow on rig 2",
          tracelog._step == 1 and overlay.guiding(plan[1]), f"step {tracelog._step}")
    check("G5", "the rig radar got the rig too", len(rigradar._rigs) >= 1, rigradar._rigs)
    rigradar.close()

    # R: rig radar rings stop at the map square (Tk canvas does not clip)
    write(*ll(x, y))
    rigradar.placed(root, BODY, *ll(x, y - 60), R)       # ring reaches 138 m south: past the square
    pump(0.5)
    c = rigradar._canvas
    side, edge = rigradar.SIZE, rigradar.BORDER
    below = (edge, edge + side + 1, edge + side, edge + side + rigradar.BAND + rigradar.HINT)
    stack = list(c.find_overlapping(*below)) if c is not None else []
    rings = [i for i in stack if "ring" in c.gettags(i)]
    masks = [i for i in stack if "mask" in c.gettags(i)]
    check("R1", "a ring crosses the strip under the map (premise)", rings, len(rings))
    check("R2", "every ring there is under a BG mask",
          rings and masks and max(stack.index(i) for i in rings) < min(stack.index(i) for i in masks),
          f"{len(rings)} rings, {len(masks)} masks")
    if c is not None:
        c.postscript(file=os.path.join(OUT, "rigradar.ps"))
    rigradar.close()

    tracelog.placed()
    pump(0.5)
    check("F12", "Ctrl+Alt+P skips to rig 3", tracelog._step == 2 and overlay.guiding(plan[2]),
          f"step {tracelog._step}")
    for _ in range(2, len(plan)):
        tracelog.placed()
        pump(0.3)
    check("F13", "chain ends after last rig", not tracelog._plan and not overlay.guiding(),
          f"step {tracelog._step}")
    tracelog.placed()
    rig_press(x, y)
    check("F19", "key or rig press with no plan does nothing",
          not tracelog._plan and not overlay.guiding())
    rigradar.close()

    # M: the minimap names the key under the map, never over the zoom row
    for height, shown in ((1080, True), (720, False)):
        overlay._game_rect = lambda h=height: (0, 0, h * 16 // 9, h)
        write(LAT0, LON0)
        minimap.update(root, {"Flags": coverage.IN_SRV | 0x200000, "BodyName": BODY, "Latitude": LAT0,
                              "Longitude": LON0, "PlanetRadius": R, "Heading": 0})
        pump(0.3)
        canvas = minimap._canvas
        items = canvas.find_withtag("plan_rigs") if canvas is not None else ()
        zoom = [i for i in (canvas.find_all() if canvas is not None else ())
                if canvas.type(i) == "text" and canvas.itemcget(i, "text").endswith("  zoom")]
        text = canvas.itemcget(items[0], "text") if items else None
        apart = bool(items and zoom) and canvas.bbox(zoom[0])[2] < canvas.bbox(items[0])[0]
        check("M1" if shown else "M2",
              f"{height} px window: " + ("'Ctrl+Alt+R  plan rigs' right of the zoom row" if shown
                                         else "hint dropped, does not overlap zoom"),
              (text == "Ctrl+Alt+R  plan rigs" and apart) if shown else (not items and zoom),
              (text, canvas.bbox(zoom[0]) if zoom else None, canvas.bbox(items[0]) if items else None)
              if canvas is not None else "no minimap canvas")
    minimap.hide() if hasattr(minimap, "hide") else None

    # B: no trace files without RHINOSPOTTER_DEBUG
    check("B1", "no trace folder written", not os.path.exists(tracelog.DIR), tracelog.DIR)
except Exception:
    check("X", "harness ran without an exception", False, traceback.format_exc())
finally:
    tracelog.shutdown()
    overlay.stop()
    rigradar.close()
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
