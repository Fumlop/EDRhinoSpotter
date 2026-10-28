"""E2E harness: Share map draws the bookmarks of the system on screen. Checks and blind spots: sharemap.md.

Run from the plugin folder:  python rs_e2etest/sharemap_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and <case>.png. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import math
import os
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk                                                # noqa: E402

from PIL import Image                                               # noqa: E402

from rs_core import bodies, coverage, coverstore, database, grounds, spotcard, store  # noqa: E402
from rs_ui import minimap, scan                                     # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E ShareMap", "E2E ShareMap 1 a"
OTHER = "E2E ShareMap Other"
RADIUS = 1_500_000.0
LAT, LON = 12.0, -45.0
SPOTS = ((0, 0), (1500, 0), (0, -1500))        # m east, m north of LAT, LON
PLANET = {"distance": 10.0, "locations": 7, "volcanism": "", "planet_class": "Metal rich body",
          "ground": "metal-rich"}

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def at(east_m, north_m):
    lat = LAT + math.degrees(north_m / RADIUS)
    lon = LON + math.degrees(east_m / (RADIUS * math.cos(math.radians(LAT))))
    return lat, lon


def widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from widgets(child)


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def centres(image, title_lines):
    """Pixel colour at each SPOTS centre in a picture with `title_lines` above the map."""
    side = bare.width
    top = (12 + title_lines * 18 + 6) if title_lines else 0
    left = (image.width - side) // 2
    scale = side / (2 * coverage.REACH_M)
    found = []
    for lat, lon in (at(*spot) for spot in SPOTS):
        mx, my = cover.xy(lat, lon)
        found.append(image.getpixel((int(round(left + side / 2 + mx * scale)),
                                     int(round(top + side / 2 - my * scale))))[:3])
    return found


for east, north in SPOTS:
    lat, lon = at(east, north)
    spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": lat, "longitude": lon,
                   "planet_radius": RADIUS, "commodity": "Monazite", "rigs": 1,
                   "amount": "High", "location_index": 1,
                   "marked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
store.save(SYSTEM, [dict(PLANET, name=BODY)])
cover = coverage.Coverage(BODY, LAT, LON, RADIUS)
for step in range(0, 2000, 50):
    cover.add(*at(step, 0))
    cover.add(*at(0, -step))
coverstore.save(BODY, "map 1", cover.to_dict())
bare = coverage.picture(cover.mask.copy())

opened = []
scan._open_card = opened.append

root = tk.Tk()
root.withdraw()
window = None
sheet = grounds.Sheet()

try:
    check("control: no MARK at the 3 centres on a picture without marks",
          coverage.MARK not in centres(bare, 0), f"{centres(bare, 0)}")

    live_here = bodies.Register()
    live_here.adopt(SYSTEM, [dict(PLANET, name=BODY)])
    live_empty = bodies.Register()
    live_empty.system = OTHER
    live_other = bodies.Register()
    live_other.adopt(OTHER, [dict(PLANET, name=OTHER + " 1")])

    for case, live, browse in (("live", live_here, False),
                               ("browsed-empty", live_empty, True),
                               ("browsed-other", live_other, True)):
        window = scan.show(root, live, sheet, None, variable=tk.StringVar(), materials=("All",))
        window.geometry("+-4000+-4000")
        if browse:
            scan._browse(SYSTEM)
        scan._state["body"] = BODY
        scan._draw()
        pump()
        button = next((w for w in widgets(window)
                       if isinstance(w, tk.Button) and w.cget("text") == "Share map"), None)
        enabled = button is not None and str(button.cget("state")) == "normal"
        opened.clear()
        pressed = time.time()
        if enabled:
            button.invoke()
            pump()
        check(f"{case} 1 Share map enabled, press opens a path", enabled and len(opened) == 1,
              f"button {button is not None}, opened {[os.path.relpath(p, OUT) for p in opened]}")
        if opened:
            path = opened[0]
            check(f"{case} 2 PNG written by this press", os.path.getmtime(path) >= pressed - 1,
                  f"mtime {os.path.getmtime(path) - pressed:+.1f} s")
            image = Image.open(path).convert("RGB")
            shutil.copy(path, os.path.join(OUT, f"{case}.png"))
            title, legend = minimap.picture_text(cover, SYSTEM)
            got = centres(image, len(title))
            check(f"{case} 3 MARK at each of the 3 bookmark centres",
                  got == [coverage.MARK] * len(SPOTS), f"{got}")
            want_h = (12 + len(title) * 18 + 6) + bare.height + (12 + len(SPOTS) * 18 + 12)
            check(f"{case} 4 legend: 3 rows (picture height)", image.height == want_h,
                  f"{image.height} px, want {want_h} px")
            os.remove(path)
        scan._back_to_live()
        window.destroy()
        window = None
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
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
print(os.path.relpath(OUT, PLUGIN))
sys.exit(1 if failed else 0)
