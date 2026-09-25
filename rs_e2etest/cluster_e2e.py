"""E2E harness for clustered bookmark order and golden groups. Checks and blind
spots: cluster.md.

Run from the plugin folder:  python rs_e2etest/cluster_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and <tag>-before/after.png.
Exit code 1 on a failure.
"""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)


def child():
    sys.path.insert(0, PLUGIN)
    import math
    from rs_core import cards, coverage, coverstore, database, grounds, guide, measure
    from rs_ui import scan
    out = os.environ["LOCALAPPDATA"]
    assert database.PATH.startswith(out), database.PATH

    old_path = os.path.join(out, "coverage_head.py")
    with open(old_path, "w", encoding="utf-8") as handle:
        handle.write(subprocess.run(["git", "show", "HEAD:rs_core/coverage.py"], cwd=PLUGIN,
                                    capture_output=True, text=True, encoding="utf-8",
                                    check=True).stdout)
    spec = importlib.util.spec_from_file_location("coverage_head", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    old.TEXTURE_DIR = coverage.TEXTURE_DIR

    with database.connect() as conn:
        systems = [s for (s,) in conn.execute("SELECT DISTINCT system FROM bookmarks")]
    records = [r for s in systems for r in cards.for_system(s)]
    (body, loc), count = Counter((r.get("planet_name"), r.get("location_index"))
                                 for r in records).most_common(1)[0]
    group = [r for r in records if r.get("planet_name") == body and r.get("location_index") == loc]
    system = group[0]["system"]
    print(f"{body} loc {loc}: {count} bookmarks")

    fails = []
    ordered = scan._clustered(group)
    if sorted(id(r) for r in ordered) != sorted(id(r) for r in group):
        fails.append("reorder lost or doubled a bookmark")

    radius = next(r["planet_radius"] for r in group if r.get("planet_radius"))
    live = [r for r in ordered if not scan._worked_out(r)]
    if ordered[:len(live)] != live:
        fails.append("a worked-out bookmark sits above a live one")
    points = [(x, y, int(r.get("rigs") or 0)) for (x, y), r in
              zip(measure.to_metres([(r["latitude"], r["longitude"]) for r in live], radius), live)]
    found = coverage.clusters(points)
    if [live[i] for m in found for i in m] != live:
        fails.append("list order is not coverage.clusters() order")

    print(f"\n{'#':>2} {'rigs':>4} {'to seed':>8}  material")
    seeds = []
    for n, members in enumerate(found, 1):
        sx, sy, srigs = points[members[0]]
        seeds.append(srigs)
        prev = srigs
        for i in members:
            x, y, rigs = points[i]
            d = math.hypot(x - sx, y - sy)
            print(f"{n:>2} {rigs:>4} {d:>6.0f} m  {live[i].get('commodity')}")
            if d > coverage.golden_m:
                fails.append(f"cluster {n}: member {d:.0f} m from its seed")
            if rigs > prev:
                fails.append(f"cluster {n}: {rigs} rigs below {prev}")
            prev = rigs
    for r in ordered[len(live):]:
        print(f" - {int(r.get('rigs') or 0):>4}  worked out  {r.get('commodity')}")
    if seeds != sorted(seeds, reverse=True):
        fails.append(f"seeds not most rigs first: {seeds}")

    # Golden groups on the saved map picture, HEAD against now.
    sheet = grounds.Sheet()

    def check_map(tag, body, system, lat, lon):
        found_maps = coverstore.maps(body)
        name = coverage.map_at(found_maps, body, lat, lon)
        cover = coverage.Coverage.from_dict(body, dict(found_maps)[name])
        marks, golden = scan._map_marks(cover, system, body, sheet)
        spots = [(x, y, rigs, value or 0) for x, y, _, spent, value, rigs in marks if not spent]
        before = old.golden_best(old.golden_groups(spots), spots)
        groups = coverage.golden_groups(spots)
        points = coverage._golden_points(spots)
        sums = [(sum(points[i][2] for i in m), sorted(m))
                for m in coverage.clusters([p[:3] for p in points])]
        least = (coverage.GOLDEN_RIGS if any(s >= coverage.GOLDEN_RIGS for s, _ in sums)
                 else coverage.GOLDEN_RIGS_LOW)
        if [g[3] for g in groups] != [m for s, m in sums if s >= least]:
            fails.append(f"{tag}: golden groups are not the clusters of {least}+ rigs")
        for g in groups:
            if g[2] > coverage.golden_m:
                fails.append(f"{tag}: golden circle {g[2]:.0f} m")
        print(f"\n{tag}: {body} {name}, {len(spots)} live spots, cluster rigs "
              f"{[s for s, _ in sums]}, threshold {least}")
        for label, best in (("HEAD", before), ("now", golden)):
            print(f"  {label}: " + "; ".join(
                f"{sum(points[i][2] for i in g[3])} rigs, r {g[2]:.0f} m, {g[4] / 1e6:.1f} M Cr"
                for g in best) if best else f"  {label}: none")
        coverage.picture(cover.mask.copy(), marks, golden=before).save(
            os.path.join(out, f"{tag}-before.png"))
        coverage.picture(cover.mask.copy(), marks, golden=golden).save(
            os.path.join(out, f"{tag}-after.png"))
        return least

    check_map("densest", body, system, group[0]["latitude"], group[0]["longitude"])
    # Where the SRV is now, from the game's Status.json.
    status_path = os.path.join(os.environ["USERPROFILE"], "Saved Games", "Frontier Developments",
                               "Elite Dangerous", "Status.json")
    try:
        with open(status_path, encoding="utf-8") as handle:
            status = json.load(handle)
        here = next((r for r in records if r.get("planet_name") == status["BodyName"]), None)
        if here is None:
            print(f"\nSKIP srv: no bookmarks on {status['BodyName']}")
        elif check_map("srv", status["BodyName"], here["system"], status["Latitude"],
                       status["Longitude"]) != coverage.GOLDEN_RIGS_LOW:
            print("  (srv map has a 5+ cluster: the 4-rig fallback is not exercised there)")
    except (OSError, KeyError, ValueError) as err:
        print(f"\nSKIP srv: no Status.json position ({err})")

    # Settings: the golden radius spinbox, OK, a bad stored value, start.
    import tkinter as tk
    from rs_ui import hotkey, main, minimap

    class Config:
        """EDMC's config as far as minimap reads and writes it (minimap_e2e's)."""
        def __init__(self, **values):
            self.values = values

        def get_bool(self, key, default=False):
            return self.values.get(key, default)

        get_str = get_int = get_bool

        def set(self, key, value):
            self.values[key] = value

    class Notebook:
        Frame, Label, Button, Checkbutton = tk.Frame, tk.Label, tk.Button, tk.Checkbutton

        @staticmethod
        def OptionMenu(master, variable, default, *values):
            return tk.OptionMenu(master, variable, default, *values)

    def check(name, ok, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            fails.append(f"settings: {name} {detail}")

    def spinboxes(widget):
        found = [widget] if isinstance(widget, tk.Spinbox) else []
        for kid in widget.winfo_children():
            found += spinboxes(kid)
        return found

    print("\nsettings")
    root = tk.Tk()
    root.withdraw()
    minimap.nb = Notebook
    minimap.config = hotkey.config = Config()
    frame = minimap.prefs(root)
    minimap.apply_golden()
    check("no key: spinbox 1250", minimap._golden.get() == "1250", minimap._golden.get())
    check("no key: golden_m 1250", coverage.golden_m == 1250.0, coverage.golden_m)
    box, = spinboxes(frame)
    values = [int(v) for v in root.tk.splitlist(box.cget("values"))]
    check("steps 500-2500 by 250", values == list(range(500, 2501, 250)), values)
    check("readonly", str(box.cget("state")) == "readonly", box.cget("state"))
    box.invoke("buttonup")
    check("up arrow 1250 -> 1500", minimap._golden.get() == "1500", minimap._golden.get())
    minimap.prefs_changed()
    check("OK stores 1500", minimap.config.values.get(minimap.GOLDEN_KEY) == 1500,
          minimap.config.values.get(minimap.GOLDEN_KEY))
    check("OK applies 1500", coverage.golden_m == 1500.0, coverage.golden_m)
    check_map("r1500", body, system, group[0]["latitude"], group[0]["longitude"])
    ordered = scan._clustered(group)
    live = [r for r in ordered if not scan._worked_out(r)]
    xy = measure.to_metres([(r["latitude"], r["longitude"]) for r in live], radius)
    points = [(x, y, int(r.get("rigs") or 0)) for (x, y), r in zip(xy, live)]
    far = max(math.hypot(points[i][0] - points[m[0]][0], points[i][1] - points[m[0]][1])
              for m in coverage.clusters(points) for i in m)
    check("list clusters within 1500 m", far <= 1500.0, f"furthest {far:.0f} m")
    for stored in (1300, "abc"):
        minimap.config = Config(**{minimap.GOLDEN_KEY: stored})
        check(f"stored {stored!r}: 1250", minimap.golden() == 1250, minimap.golden())
    minimap.config = hotkey.config = Config(**{minimap.GOLDEN_KEY: 1000})
    coverage.golden_m = coverage.GOLDEN_RADIUS_M
    main.start(PLUGIN)
    check("start applies stored 1000", coverage.golden_m == 1000.0, coverage.golden_m)
    root.destroy()
    coverage.golden_m = coverage.GOLDEN_RADIUS_M

    print(f"\nfails {len(fails)}")
    for line in fails:
        print("FAIL " + line)
    return 1 if fails else 0


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
