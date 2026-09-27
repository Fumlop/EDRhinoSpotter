"""E2E harness: the minimap in the ship over a saved map (#16). Checks and blind spots: ship.md.

Run from the plugin folder:  python rs_e2etest/ship_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import math
import os
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

import ctypes                                            # noqa: E402
import tkinter as tk                                     # noqa: E402
from ctypes import wintypes                              # noqa: E402

from rs_core import coverage, coverstore, database       # noqa: E402
from rs_ui import hotkey, minimap, overlay               # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

u = ctypes.WinDLL("user32", use_last_error=True)
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.FindWindowW.restype = wintypes.HWND

BODY, OTHER = "E2E Ship 1 a", "E2E Ship 2 b"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0
SRV_FLAGS = coverage.IN_SRV | 0x200000
SHIP_FLAGS = 0x01000000 | 0x200000


class Config:
    """EDMC's config as far as minimap and overlay read and write it."""

    def __init__(self, **values):
        self.values = values

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    get_str = get_int = get_bool

    def get_list(self, key, default=None):
        return self.values.get(key, default if default is not None else [])

    def set(self, key, value):
        self.values[key] = value


class Notebook:
    Frame, Label, Button, Checkbutton = tk.Frame, tk.Label, tk.Button, tk.Checkbutton

    @staticmethod
    def OptionMenu(master, variable, default, *values):
        return tk.OptionMenu(master, variable, default, *values)


results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def north(metres):
    return LAT + math.degrees(metres / RADIUS)


def srv(lat, lon=LON, body=BODY):
    return {"Flags": SRV_FLAGS, "BodyName": body, "Latitude": lat, "Longitude": lon,
            "PlanetRadius": RADIUS, "Heading": 0}


def ship(lat, lon=LON, altitude=30.0, body=BODY, flags2=0):
    return {"Flags": SHIP_FLAGS, "Flags2": flags2, "BodyName": body, "Latitude": lat,
            "Longitude": lon, "PlanetRadius": RADIUS, "Heading": 90, "Altitude": altitude}


def tick(status):
    minimap.update(root, status)
    root.update()


def shown():
    return bool(minimap._handle) and bool(u.IsWindowVisible(minimap._handle)) and minimap._shown


def painted():
    c = minimap._coverage
    return (c.version, c.drop, c.mask.tobytes()) if c is not None else None


def saved_maps(body=BODY):
    minimap._writes.flush()
    return [name for name, _ in coverstore.maps(body)]


root = tk.Tk()
root.withdraw()
minimap.nb = Notebook
minimap.config = hotkey.config = overlay.config = Config(**{minimap.KEEP_KEY: True,
                                                            minimap.CORNER_KEY: "top right"})
stand_in = None
if not u.FindWindowW(None, overlay.GAME_TITLE):
    stand_in = tk.Toplevel(root)
    stand_in.title(overlay.GAME_TITLE)
    stand_in.geometry("1200x700+300+150")
    stand_in.configure(bg="#203040")
    pump(0.5)

try:
    # The SRV paints a map: 3 fixes 100 m apart.
    for m in (0, 100, 200):
        tick(srv(north(m)))
    check("setup: the SRV painted and showed the map", shown() and minimap._coverage.version > 0,
          f"shown {shown()}, version {minimap._coverage.version}")

    # 1. switch off (default): the ship over the map shows nothing
    tick(ship(north(200), altitude=500))
    check("1 switch off: not shown in the ship", not shown())

    # 2. switch on through Settings OK
    frame = minimap.prefs(tk.Frame(root))
    minimap._ship.set(True)
    minimap.prefs_changed()
    check("2 Settings OK stores the switch", minimap.config.values.get(minimap.SHIP_KEY) is True,
          repr(minimap.config.values.get(minimap.SHIP_KEY)))

    # 3. SRV back, docks: the ship on the same spot shows the same map, unpainted
    tick(srv(north(200)))
    cover = minimap._coverage
    before, maps_before = painted(), saved_maps()
    for m in (200, 220, 240, 260, 280):
        tick(ship(north(m)))
    check("3 docked: shown in the ship, same map", shown() and minimap._coverage is cover,
          f"shown {shown()}, same {minimap._coverage is cover}")
    check("3 not painted: version, drop, mask unchanged after 5 ship fixes", painted() == before)

    # 4. the marker moves with the ship
    drawn = minimap._drawn
    tick(ship(north(1200)))
    check("4 1 km on: drawn state moved, still not painted",
          minimap._drawn != drawn and painted() == before and shown())

    # 5. altitude
    tick(ship(north(1200), altitude=2100))
    check("5 2100 m: down", not shown())
    tick(ship(north(1200), altitude=1900))
    check("5 1900 m: up again", shown())
    tick(dict(ship(north(1200)), Altitude=None))
    check("5 no Altitude: down", not shown())
    tick(dict(ship(north(1200), altitude=500), Flags=SHIP_FLAGS | minimap.ALT_FROM_AVERAGE))
    check("5 Altitude from the average radius: down", not shown())

    # 6. off the map
    tick(ship(north(12000)))
    check("6 12 km off the map: down", not shown())

    # 7. fresh state: the saved map is found
    check("setup: no map written by the ship", saved_maps() == maps_before, f"{saved_maps()}")
    minimap._coverage = None
    tick(ship(north(300)))
    check("7 nothing in memory: the saved map shown", shown() and minimap._coverage is not None
          and minimap._coverage.name in maps_before,
          f"shown {shown()}, map {getattr(minimap._coverage, 'name', None)}")
    check("7 and no new map written", saved_maps() == maps_before, f"{saved_maps()}")

    # 8. a body with no saved map
    tick(ship(LAT, body=OTHER))
    check("8 body with no saved map: not shown", not shown())
    check("8 and no map created for it", saved_maps(OTHER) == [], f"{saved_maps(OTHER)}")

    # 9. on foot
    tick(ship(north(300), flags2=minimap.ON_FOOT))
    check("9 on foot: not shown", not shown())

    # 10. the SRV still paints after the ship
    tick(srv(north(300)))
    v = minimap._coverage.version
    tick(srv(north(700)))
    check("10 SRV after the ship: paints", minimap._coverage.version > v, f"{v} -> {minimap._coverage.version}")

    # 11. control: without ship_fix the docked case is not shown
    real = minimap.ship_fix
    minimap.ship_fix = lambda status: None
    tick(ship(north(700)))
    check("11 control: ship_fix None -> not shown", not shown())
    minimap.ship_fix = real
    tick(ship(north(700)))
    check("11 and with it restored: shown", shown())
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    minimap._writes.flush()
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
