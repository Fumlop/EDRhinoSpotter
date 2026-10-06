"""E2E harness: the SRV marker on the minimap is orange. Checks and blind spots: srv_marker.md.

Run from the plugin folder:  python rs_e2etest/srv_marker_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt, minimap.png. Exit code 1 on a failure.
"""

import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image                      # noqa: E402
from rs_core import coverage, palette      # noqa: E402

BODY = "E2E Srv 1 a"
RADIUS = 1_500_000.0
LAT, LON = 12.0, -45.0

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def at(east_m, north_m):
    """(lat, lon) `east_m`, `north_m` from LAT, LON."""
    lat = LAT + math.degrees(north_m / RADIUS)
    return lat, LON + math.degrees(east_m / (RADIUS * math.cos(math.radians(lat))))


SRV = palette.rgb(palette.SRV)
FG = palette.rgb(palette.FG)

# 2. distance to every other colour drawn on the map
others = {"MARK": coverage.MARK, "MARK_DEPLETED": coverage.MARK_DEPLETED, "CENTRE": coverage.CENTRE,
          "GOLD": coverage.GOLD, "GRID": coverage.GRID, "WARN": palette.rgb(palette.WARN),
          "EDGE": coverage.EDGE, "FILL": coverage.FILL}
for name, colour in others.items():
    d = math.dist(SRV, colour)
    check(f"2 SRV vs {name} RGB distance >= 80", d >= 80, f"{d:.0f}")

cover = coverage.Coverage(BODY, LAT, LON, RADIUS)
for step in range(0, 3001, 50):
    cover.add(*at(step, step * 0.4))
x, y = cover.xy(*at(3000, 1200))
# 3. one dot on the SRV, two nearby, one depleted
marks = [(x, y, "AL", False), (x + 400, y - 300, "MZ", False), (x - 600, y + 200, "PA", True)]

shots = []
for side, base in ((180, None), (240, None), (480, None), (480, 240)):
    for heading in (0, 135, None):
        image = coverage.render(cover, x, y, heading, side, marks=marks, distances=side > 180, base=base)
        c = side // 2
        centre = image.getpixel((c, c))
        tag = f"{side}px base={base} heading={heading}"
        check(f"1/3/4/5 marker centre is SRV ({tag})", centre == SRV, f"{centre}")
        # Without marks: the bookmark codes are drawn in FG beside their dots.
        bare = coverage.render(cover, x, y, heading, side, base=base)
        size = coverage._marker_size(base or side)
        box = [bare.getpixel((i, j)) for i in range(c - size // 2, c + size // 2)
               for j in range(c - size // 2, c + size // 2)]
        check(f"1 no FG pixel in the marker box ({tag})", FG not in box, f"FG {box.count(FG)} px")
        if heading != 135:
            shots.append(image)

sheet = Image.new("RGB", (sum(s.width for s in shots) + 8 * len(shots), 480), palette.rgb(palette.BG))
left = 0
for shot in shots:
    sheet.paste(shot, (left, 0))
    left += shot.width + 8
sheet.save(os.path.join(OUT, "minimap.png"))

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}  {detail}" for name, ok, detail in results]
lines.append(f"{len(results) - len(failed)}/{len(results)} passed")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print("\n".join(lines))
print(OUT)
sys.exit(1 if failed else 0)
