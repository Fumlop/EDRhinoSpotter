"""E2E harness for Ctrl+Alt+B before Ctrl+Alt+Z. Checks and blind spots: border.md.

Run from the plugin folder:  python rs_e2etest/border_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
Shows the minimap window for a few seconds.
"""

import math
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SYSTEM = "Hyperion Reach AB-C d1-42"
BODY = f"{SYSTEM} 4 a"
RADIUS = 1738000.0
LAT0, LON0 = 12.34, -98.77


def reading(x, y, flags):
    per_degree = RADIUS * math.pi / 180.0
    return {"Flags": flags, "BodyName": BODY, "Heading": 90, "PlanetRadius": RADIUS,
            "Latitude": LAT0 + y / per_degree,
            "Longitude": LON0 + x / (per_degree * math.cos(math.radians(LAT0)))}


def child():
    sys.path.insert(0, PLUGIN)
    import tkinter as tk
    from rs_core import coverage, coverstore, database
    from rs_ui import minimap
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    coverage.clear_old_textures = lambda: None
    minimap._bookmarks = lambda system, body: []
    root = tk.Tk()
    root.withdraw()
    fails = []

    def check(name, ok, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            fails.append(f"{name} {detail}")

    def drive(points):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            steps = max(1, int(math.hypot(x2 - x1, y2 - y1) // 50))
            for i in range(steps + 1):
                minimap.update(root, reading(x1 + (x2 - x1) * i / steps,
                                             y1 + (y2 - y1) * i / steps, coverage.IN_SRV),
                               SYSTEM)
        root.update()

    def press(x, y, hotkey):
        fix = reading(x, y, coverage.IN_SRV)
        minimap.update(root, fix, SYSTEM)
        minimap._here = (fix["Latitude"], fix["Longitude"])
        hotkey()

    def painted():
        return sum(minimap._coverage.mask.histogram()[1:])

    def notice():
        return minimap._notice[0] if minimap._notice else None

    print("B before Z")
    drive([(0, 0), (6000, 0), (6000, 3000)])
    cover = minimap._coverage
    before = painted()
    press(6000, 3000, minimap.border_here)
    check("no centre: border_m stays None", cover.border_m is None, cover.border_m)
    check("no centre: point kept", cover.border_at is not None, cover.border_at)
    check("no centre: painted ground unchanged", painted() == before, f"{before} -> {painted()}")
    check("hint says kept", notice() == "border kept - set center", notice())
    drive([(6000, 3000), (4500, 0)])
    press(4500, 0, minimap.border_here)
    kept = cover.border_at
    lat, lon = reading(4500, 0, 0)["Latitude"], reading(4500, 0, 0)["Longitude"]
    check("second B: later point wins", kept == (lat, lon), f"{kept} vs {(lat, lon)}")

    minimap._writes.flush()
    data = dict(coverstore.maps(BODY)).get(cover.name, {})
    check("saved: border_at on disk", data.get("border_at") == [round(lat, 6), round(lon, 6)],
          data.get("border_at"))
    back = coverage.Coverage.from_dict(BODY, data, cover.name)
    check("loaded: border_at back", back is not None and back.border_at is not None
          and math.isclose(back.border_at[0], lat, abs_tol=1e-6), back and back.border_at)

    press(500, 0, minimap.center_here)
    check("Z: border = centre -> kept point", cover.border_m is not None
          and abs(cover.border_m - 4000) < 2, cover.border_m)
    check("Z: kept point cleared", cover.border_at is None, cover.border_at)
    minimap._writes.flush()
    data = dict(coverstore.maps(BODY)).get(cover.name, {})
    check("saved: border_m, no border_at", data.get("border_m") == 4000
          and "border_at" not in data, {k: data.get(k) for k in ("border_m", "border_at")})
    press(0, 0, minimap.center_here)
    check("Z again: radius kept", abs(cover.border_m - 4000) < 2, cover.border_m)

    print("Z before B (unchanged)")
    minimap._coverage = None
    minimap.update(root, reading(0, 0, 0x1000000), SYSTEM)   # docked
    drive([(20000, 0), (22000, 0)])
    other = minimap._coverage
    check("new map for the second launch", other is not cover)
    minimap._notice = None
    press(22000, 0, minimap.center_here)
    press(25000, 0, minimap.border_here)
    check("border from the centre", other.border_m is not None
          and abs(other.border_m - 3000) < 2, other.border_m)
    check("no 'kept' hint", notice() is None, notice())

    root.destroy()
    print(f"\nfails {len(fails)}")
    for line in fails:
        print("FAIL " + line)
    return 1 if fails else 0


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out)
    env = dict(os.environ, LOCALAPPDATA=out, PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"], cwd=PLUGIN,
                         env=env, capture_output=True, text=True, encoding="utf-8")
    report = run.stdout.splitlines()
    if run.stderr.strip():
        report.append(run.stderr.strip())
    report.append(f"\nresult: {'PASS' if run.returncode == 0 else 'FAIL'}")
    text = "\n".join(report)
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text)
    print(out)
    return run.returncode


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    raise SystemExit(main())
