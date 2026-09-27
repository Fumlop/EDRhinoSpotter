"""E2E harness for the patched minimap layer. Checks and blind spots: layer.md.

Run from the plugin folder:  python rs_e2etest/layer_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.

One child with LOCALAPPDATA set to out/<timestamp>/, holding a sqlite backup
copy of the live db. Every saved map is replayed stamp by stamp; the patched
Coverage.layer() is compared pixel by pixel with a full _draw_layer.
"""

import gzip
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)

# (lside, view m) as render() asks. 180: 600 px drawn over a 400 px mask, a
# fractional scale (the case that broke the patch). 640: the largest layer;
# 4x (320 px, view 3000) draws the same 1067 px layer.
SIZES = ((180, 6000.0), (640, 6000.0))
EVERY = 10              # full-draw comparison every 10th stamp, and after the last
BORDER_M = 3000.0
# Metres from the centre: 9.9 km on each side, two corners, 1 m inside the edge.
EDGE_M = ((9900.0, 0.0), (-9900.0, 0.0), (0.0, 9900.0), (0.0, -9900.0),
          (9900.0, 9900.0), (-9999.0, -9999.0))


def child():
    sys.path.insert(0, PLUGIN)
    from PIL import ImageChops
    from rs_core import coverage, database
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH

    with database.connect() as conn:
        maps = [(body, name, json.loads(gzip.decompress(raw)))
                for body, name, raw in conn.execute("SELECT body, name, data FROM maps ORDER BY body, name")]
    print(f"maps {len(maps)}, stamps {sum(len(d['stamps']) for _, _, d in maps)}")

    # The committed coverage.py (git HEAD), for old-vs-new render() and picture().
    import importlib.util
    old_path = os.path.join(os.environ["LOCALAPPDATA"], "coverage_head.py")
    with open(old_path, "w", encoding="utf-8") as handle:
        handle.write(subprocess.run(["git", "show", "HEAD:rs_core/coverage.py"], cwd=PLUGIN,
                                    capture_output=True, text=True, encoding="utf-8",
                                    check=True).stdout)
    spec = importlib.util.spec_from_file_location("coverage_head", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    old.TEXTURE_DIR = coverage.TEXTURE_DIR      # resolved from __file__, i.e. the out folder

    fails, checks = [], 0
    stats = {"max": 0, "exact_off": 0, "old_new": 0, "edge_painted": 0}

    def to_latlon(cover, x, y):
        # Inverse of measure.to_metres around the map's origin.
        from rs_core import measure
        scale = measure.metres_per_degree(cover.radius)
        lat0, lon0 = cover.origin
        return lat0 + y / scale, lon0 + x / (scale * math.cos(math.radians(lat0)))

    def old_vs_new(cover, lside, view, label):
        side = int(round(lside * coverage.VIEW_M / view))
        # HEAD replays the same points through add(); from_dict(to_dict()) would
        # repaint from 6-decimal points and flip disc-edge pixels in both versions.
        was = old.Coverage.from_dict("x", dict(cover.to_dict(), stamps=[]))
        for lat, lon in cover.stamps:
            was._last = None
            was.add(lat, lon)
        was.ground = cover.ground
        stats["old_new"] += 1
        if ImageChops.difference(was.mask, cover.mask).getbbox():
            fails.append(f"{label}: mask differs from HEAD")
        for x, y in ((0.0, 0.0), (1234.0, -2345.0)):
            a = old.render(was, x, y, 90, side, view=view)
            b = coverage.render(cover, x, y, 90, side, view=view)
            stats["old_new"] += 1
            if ImageChops.difference(a, b).getbbox():
                fails.append(f"{label}: render() at {x:.0f},{y:.0f} differs from HEAD")
        a = old.picture(was.mask, border_m=was.border_m, ground=was.ground)
        b = coverage.picture(cover.mask, border_m=cover.border_m, ground=cover.ground)
        stats["old_new"] += 1
        if ImageChops.difference(a, b).getbbox():
            fails.append(f"{label}: picture() differs from HEAD")
    t_full, t_patch = {}, {}

    def fresh(data, border, ground):
        cover = coverage.Coverage.from_dict("x", dict(data, stamps=[]))
        if border:
            cover.centered, cover.border_m = True, BORDER_M
            cover._repaint([])
        cover.ground = ground
        return cover

    def compare(cover, lside, view, label):
        nonlocal checks
        ring_at = tuple(round(v) for v in cover.anchor())
        t = time.perf_counter()
        full = coverage._draw_layer(cover.mask, lside, ring_at, cover.border_m, view=view,
                                    ground=cover.ground)
        t_full.setdefault(lside, []).append(time.perf_counter() - t)
        diff = ImageChops.difference(cover.layer(lside, view), full)
        checks += 1
        worst = max(high for _, high in diff.getextrema())
        stats["max"] = max(stats["max"], worst)
        if worst:
            stats["exact_off"] += 1
            fails.append(f"{label}: differs by up to {worst} in {diff.getbbox()}")

    for body, name, data in maps:
        for lside, view in SIZES:
            for border, ground, step in ((False, None, 1), (True, "metal-rich", 3)):
                label = f"{body} / {name} / {lside}px view {view:.0f} border {border} ground {ground} step {step}"
                cover = fresh(data, border, ground)
                cover.layer(lside, view)
                stamps = data["stamps"]
                for i, (lat, lon) in enumerate(stamps, 1):
                    cover._last = None
                    cover.add(lat, lon)
                    if i % step == 0 or i == len(stamps):
                        t = time.perf_counter()
                        cover.layer(lside, view)
                        t_patch.setdefault(lside, []).append(time.perf_counter() - t)
                    if i % EVERY == 0 or i == len(stamps):
                        compare(cover, lside, view, f"{label} stamp {i}")
                    # Halfway: _repaint (recenter) must redraw whole.
                    if i == len(stamps) // 2 and step == 1 and not border:
                        cover.recenter(*cover.origin)
                        compare(cover, lside, view, f"{label} recenter {i}")
                # Discs within SCAN_RADIUS_M of the +-REACH_M mask edge: _stamp's clamped box.
                if not border:
                    for x, y in EDGE_M:
                        cover._last = None
                        before = cover.version
                        cover.add(*to_latlon(cover, x, y))
                        stats["edge_painted"] += cover.version > before
                        cover.layer(lside, view)
                        compare(cover, lside, view, f"{label} edge stamp {x:.0f},{y:.0f}")
                old_vs_new(cover, lside, view, label)
                # A key part other than version changing: ground swapped.
                cover.ground = None if ground else "metal-rich"
                compare(cover, lside, view, f"{label} ground swap")
        print(f"  {body} / {name}: {len(data['stamps'])} stamps")

    for lside, view in SIZES:
        full = sorted(t_full.get(lside, [0]))
        patch = sorted(t_patch.get(lside, [0]))
        print(f"{lside}px view {view:.0f}: full median {full[len(full) // 2] * 1000:.1f} ms, "
              f"patch median {patch[len(patch) // 2] * 1000:.1f} ms, "
              f"patch max {patch[-1] * 1000:.1f} ms")
    print(f"checks {checks}, not bit-identical {stats['exact_off']}, "
          f"worst channel difference {stats['max']} of 255, old-vs-new {stats['old_new']}, "
          f"edge stamps that painted {stats['edge_painted']}, "
          f"fails {len(fails)}")
    for line in fails[:30]:
        print("FAIL " + line)
    return 1 if fails or not checks else 0


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    live = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
    copy = os.path.join(out, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(copy))
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
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
