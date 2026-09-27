"""E2E harness: the 1 km grid in dim yellow. Checks and blind spots: grid.md.

Run from the plugin folder:  python rs_e2etest/grid_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt, minimap.png. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads.
"""

import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(OUT)
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

from rs_core import coverage, palette                   # noqa: E402

LAT, LON, RADIUS = 10.0, 20.0, 1_500_000.0
SIDE = 480
RULE = palette.rgb(palette.RULE)
WARN = palette.rgb(palette.WARN)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def fix(east_m, north_m):
    return (LAT + math.degrees(north_m / RADIUS),
            LON + math.degrees(east_m / (RADIUS * math.cos(math.radians(LAT)))))


def column(image, x_m, ys_m):
    """Pixels on the vertical line x = x_m metres from the image centre, at ys_m."""
    k = image.width / (2 * coverage.REACH_M)
    x = int(round(image.width / 2 + x_m * k))
    out = []
    for y_m in ys_m:
        y = int(round(image.height / 2 - y_m * k))
        # The line is a pixel wide after the reduce: the pixel or its neighbour.
        out.append(min((image.getpixel((xx, y)) for xx in (x - 1, x, x + 1)),
                       key=lambda p: sum(abs(a - b) for a, b in zip(p, coverage.GRID))))
    return out


def near(p, q, tol=6):
    return sum(abs(a - b) for a, b in zip(p, q)) <= tol


try:
    cover = coverage.Coverage("E2E Grid 1 a", LAT, LON, RADIUS)
    for i in range(36):
        a = i / 36 * 2 * math.pi
        cover.add(*fix(600 * math.cos(a), 600 * math.sin(a)))
    cover.recenter(*fix(500, 0))            # 5. centre 500 m east of the first fix
    layer = cover.layer(SIDE)
    layer.save(os.path.join(OUT, "minimap.png"))
    outside = [-8750 + 500 * i for i in range(9)]            # -8.75 to -4.75 km: undriven, off every horizontal line

    # 1. minimap, outside the driven area
    for x in (1000, 3000):
        px = column(layer, x, outside)
        check(f"1 minimap: {x // 1000} km grid line is GRID outside the driven area",
              all(near(p, coverage.GRID) for p in px), px[:3])

    # 2. on the driven area (within ~2 km of the fixes, which sit round -500, 0)
    px = column(layer, -1000, [0, 300, -300])
    check("2 on the driven area the grid stands out from FILL (>40 apart)",
          all(sum(abs(a - b) for a, b in zip(p, coverage.FILL)) > 40 for p in px), px)

    # 3. Share map / card map
    picture = coverage.picture(cover.mask.copy())
    px = column(picture, 3000, outside)
    check("3 coverage.picture: the 3 km grid line is GRID", all(near(p, coverage.GRID) for p in px), px[:3])

    # 4. not RULE, not WARN
    lines = column(layer, 1000, outside) + column(layer, 3000, outside) + column(picture, 3000, outside)
    check("4 no RULE pixel on the grid lines", not any(near(p, RULE) for p in lines))
    check("4 GRID is not WARN (the mask edge)", not near(coverage.GRID, WARN, 40), coverage.GRID)

    # 5. pinned to the centre: a line at the centre (x=0) and none halfway (x=500)
    centre = column(layer, 0, outside)
    check("5 a grid line through the centre", all(near(p, coverage.GRID) for p in centre), centre[:3])
    half = column(layer, 500, outside)
    check("5 no line halfway between (500 m)", not any(near(p, coverage.GRID) for p in half), half[:3])
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())

failed = [r for r in results if not r[1]]
lines_out = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
             for name, ok, detail in results]
lines_out.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
report = "\n".join(lines_out)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(OUT)
sys.exit(1 if failed else 0)
