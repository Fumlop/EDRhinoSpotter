"""E2E harness: bookmark dots - pale dot, hollow ring once depleted. Checks and blind spots: dots.md.

Run from the plugin folder:  python rs_e2etest/dots_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt, minimap.png, picture.png. Exit code 1 on a failure.
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

from rs_core import cards, coverage, database, grounds, palette, spotcard, yields  # noqa: E402
from rs_ui import minimap, scan                                                   # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E Dots", "E2E Dots 1 a"
RADIUS = 1_500_000.0
LAT, LON = 12.0, -45.0
MATERIAL = "Monazite"

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def at(east_m, north_m):
    """(lat, lon) `east_m`, `north_m` from LAT, LON."""
    lat = LAT + math.degrees(north_m / RADIUS)
    lon = LON + math.degrees(east_m / (RADIUS * math.cos(math.radians(LAT))))
    return lat, lon


def bookmark(east_m, north_m, rigs):
    lat, lon = at(east_m, north_m)
    return spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": lat, "longitude": lon,
                          "planet_radius": RADIUS, "commodity": MATERIAL, "rigs": rigs,
                          "amount": "High", "location_index": 1,
                          "marked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def row(id):
    return next(r for r in cards.for_system(SYSTEM) if r.get("id") == id)


def refine(id, tons):
    record = row(id)
    status = {"BodyName": BODY, "Latitude": record["latitude"], "Longitude": record["longitude"],
              "Altitude": 0.0, "PlanetRadius": RADIUS}
    for _ in range(tons):
        yields.TALLY.refined(status, SYSTEM, MATERIAL)
    yields.TALLY.flush()


def states_by_id(tuples, key_xy):
    """{id: state} matching tuples to bookmarks by position."""
    found = {}
    for id, (x, y) in key_xy.items():
        for t in tuples:
            if abs(t[0] - x) < 1e-6 and abs(t[1] - y) < 1e-6:
                found[id] = t[3]
    return found


try:
    # idle far out; mining + depleted 1 km apart, inside golden_m 1250 m (2 + 3 rigs = 5 if
    # depleted counted); a second idle 2 rigs 1 km beside mining: mining + it = GOLDEN_RIGS_LOW 4.
    idle = bookmark(-3000, 2000, 1)
    mining = bookmark(2000, -2000, 2)
    spent = bookmark(3000, -2000, 3)
    beside = bookmark(2000, -3000, 2)
    refine(mining, 3)
    refine(spent, 4)
    check("setup: Depleted written", cards.set_depleted(dict(row(spent)), True), True)

    cover = coverage.Coverage(BODY, LAT, LON, RADIUS)
    xy = {id: cover.xy(row(id)["latitude"], row(id)["longitude"]) for id in (idle, mining, spent, beside)}
    want = {idle: False, mining: False, spent: True, beside: False}

    # 1. minimap
    marks_mm = [(*cover.xy(lat, lon), code, depleted, value, rigs)
                for lat, lon, code, depleted, value, rigs in minimap._bookmarks(SYSTEM, BODY)]
    got = states_by_id(marks_mm, xy)
    check("1 minimap._bookmarks: depleted for the marked one only", got == want, f"{got}")

    # 2. card map / Share map
    marks_sc, golden = scan._map_marks(cover, SYSTEM, BODY, grounds.Sheet())
    got2 = states_by_id(marks_sc, xy)
    check("2 scan._map_marks: same flags as the minimap", got2 == want, f"{got2}")

    # 3 + 4. rendered dots, rings and letters
    side = 480
    image = coverage.render(cover, 0, 0, None, side, marks=marks_mm)
    image.save(os.path.join(OUT, "minimap.png"))
    scale = side / (2 * coverage.VIEW_M)
    fg = palette.rgb(palette.FG)
    r = coverage._mark_radius(side)
    for id, name in ((idle, "untouched"), (mining, "mined"), (spent, "depleted")):
        mx, my = xy[id]
        cx, cy = side / 2 + mx * scale, side / 2 - my * scale
        if want[id]:
            for size in (side, 240):
                small = image if size == side else coverage.render(cover, 0, 0, None, size, marks=marks_mm)
                k = size / (2 * coverage.VIEW_M)
                sx, sy = size / 2 + mx * k, size / 2 - my * k
                inner = small.getpixel((int(round(sx)), int(round(sy))))
                rr = coverage._mark_radius(size)
                sides = [coverage.MARK_DEPLETED in [small.getpixel((int(round(sx + sign * d)), int(round(sy))))
                                                    for d in range(int(rr) - 3, int(rr) + 1)]
                         for sign in (-1, 1)]
                check(f"3 depleted ring at {size} px: hollow, ring colour left and right",
                      inner != coverage.MARK_DEPLETED and all(sides),
                      f"centre {inner}, left/right {sides}")
        else:
            centre = image.getpixel((int(round(cx)), int(round(cy))))
            check(f"3 {name} dot centre MARK", centre == coverage.MARK, f"{centre}")
        tx, ty = coverage._code_at(cx, cy, side)
        box = [image.getpixel((i, j)) for i in range(int(tx) + 1, int(tx + 2 * r))   # letter width; the next dot is 40 px out
               for j in range(int(ty - r), int(ty + r))]
        marker = {coverage.MARK, coverage.MARK_DEPLETED}
        check(f"4 {name} letter in FG, no dot or ring colour in it",
              fg in box and not any(p in marker for p in box),
              f"fg {box.count(fg)} px, marker-coloured {sum(p in marker for p in box)} px")
    coverage.picture(cover.mask, marks_sc, ["dots"],
                     [("MZ", "untouched", False), ("MZ", "mined", False), ("MZ", "depleted", True)],
                     None, golden).save(os.path.join(OUT, "picture.png"))

    # 5. a leftover ton after Depleted
    refine(spent, 1)
    check("5 leftover ton after Depleted: still depleted", bool(row(spent).get("depleted_at")), True)
    check("5 and it went into the depleted cycle",
          [c.get("ended") for c in yields.cycles(row(spent))], ["depleted"])

    # 6. golden spots: depleted left out
    spots = [(x, y, rigs, value or 0) for x, y, _, spent_, value, rigs in marks_sc if not spent_]
    points = coverage._golden_points(spots)
    sums = [sum(points[i][2] for i in g[3]) for g in golden]
    check("6 one golden group of 4 rigs: mining + beside, depleted left out", sums == [4],
          f"groups {sums}")
    every = [(x, y, rigs, value or 0) for x, y, _, _, value, rigs in marks_sc]
    control = [sum(coverage._golden_points(every)[i][2] for i in g[3])
               for g in coverage.golden_best(coverage.golden_groups(every), every)]
    check("6 control: with the depleted one counted the groups differ", control != [4],
          f"groups {control}")

    # 7. no credits label over the golden circle; the circle itself is gold
    bare = coverage.picture(cover.mask, marks_sc, golden=golden)
    k = bare.width / (2 * coverage.REACH_M)
    gx, gy, radius = golden[0][0], golden[0][1], golden[0][2]
    cx, cy = bare.width / 2 + gx * k, bare.height / 2 - gy * k
    top = cy - (radius * k + coverage._mark_radius(coverage.PICTURE_SIDE) + 5)
    above = [bare.getpixel((i, j)) for i in range(int(cx) - 20, int(cx) + 21)
             for j in range(int(top) - 22, int(top) - 3)]
    on = [bare.getpixel((int(cx) + d, int(round(top)) + e)) for d in (-1, 0, 1) for e in (-1, 0, 1)]
    check("7 credits label gone: no GOLD above the circle", coverage.GOLD not in above,
          f"{above.count(coverage.GOLD)} gold px")
    check("7 control: the circle itself is GOLD", coverage.GOLD in on, f"{on}")
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())

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
