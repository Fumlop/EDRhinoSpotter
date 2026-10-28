"""E2E harness for the location line in the scan window. Checks and blind spots: header.md.

Run from the plugin folder:  python rs_e2etest/header_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.

The child's LOCALAPPDATA is the run folder, set before the interpreter starts,
so the live database is never opened.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)

BODY = "Aramo A 1"
SYSTEM = "Aramo"
RADIUS = 1_500_000.0        # m
LAT, LON = 12.345678, -45.678901

# (location, material, rigs, depleted)
MARKS = ([(4, "Iridium", rigs, rigs == 6) for rigs in (1, 2, 3, 4, 5, 6)] + [(4, "Gold", 7, False)]
         + [(5, "Silver", 8, False), (5, "Gold", 5, False), (5, "Platinum", 3, False),
            (5, "Iridium", 1, False), (5, "Osmium", 2, False)]
         + [(6, "Bauxite", 6, False), (6, "Zzzite", 2, False), (6, "Silver", 1, False)]
         + [(7, "iridium", 3, False), (7, "Iridium", 2, False)])

WANT = {
    4: "7 deposits  ·  Iridium, Gold  ·  1 worked out",
    5: "5 deposits  ·  Iridium, Platinum, Osmium",
    6: "3 deposits  ·  Silver, Bauxite, Zzzite",
    7: "2 deposits  ·  iridium",
}


def child():
    import logging
    import tkinter as tk
    sys.path.insert(0, PLUGIN)
    logging.getLogger("RhinoSpotter").addHandler(
        logging.FileHandler(os.environ["E2E_LOG"], encoding="utf-8"))

    from rs_core import bodies, coverage, database, paths, spotcard
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    scratch = os.environ["LOCALAPPDATA"]
    paths.journal_dir = lambda: scratch
    coverage.clear_old_textures = lambda: None
    with open(os.path.join(scratch, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"BodyName": BODY, "Latitude": LAT, "Longitude": LON, "Altitude": 0.0,
                   "PlanetRadius": RADIUS, "Heading": 0}, handle)

    import load
    load.plugin_start3(PLUGIN)
    from rs_ui import main, scan
    root = tk.Tk()
    root.withdraw()
    main.build(root)
    main._cancel_landed()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for n, (loc, material, rigs, depleted) in enumerate(MARKS):
        record = {"system": SYSTEM, "planet_name": BODY, "latitude": LAT + n * 1e-4,
                  "longitude": LON, "planet_radius": RADIUS, "commodity": material,
                  "rigs": rigs, "location_index": loc, "marked_at": stamp}
        if depleted:
            record["depleted_at"] = stamp
        spotcard.save(record)

    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "metal-rich", "distance": 10.0,
                             "locations": 7, "volcanism": "", "planet_class": "Metal rich body"}])
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=1)
    window.geometry("+-4000+-4000")
    root.update()

    def lines():
        """{loc: summary text} from every frame holding a 'loc N' label and a 'deposit' label."""
        found, todo = {}, [window]
        while todo:
            widget = todo.pop()
            todo.extend(widget.winfo_children())
            texts = [child.cget("text") for child in widget.winfo_children()
                     if isinstance(child, tk.Label)]
            loc = next((t for t in texts if t.startswith("loc ")), None)
            summary = next((t for t in texts if " deposit" in t), None)
            if loc and summary:
                found[int(loc.split()[1])] = summary
        return found

    results, report = [], []

    def check(name, got, want):
        results.append((name, got == want, f"{got!r} != {want!r}"))

    drawn = lines()
    report += [f"sheet  loc {loc}: {text}" for loc, text in sorted(drawn.items())]
    for loc, want in WANT.items():
        check(f"loc {loc} line", drawn.get(loc), want)

    from rs_core import grounds
    sheet = scan._scan[1]
    missing = grounds.Sheet(os.path.join(scratch, "no_sheet.json"))
    check("missing sheet file: Sheet not loaded", missing.loaded, False)
    scan._scan = (scan._scan[0], missing) + scan._scan[2:]
    scan._draw()
    root.update()
    bare = lines()
    scan._scan = (scan._scan[0], sheet) + scan._scan[2:]
    report += [f"none   loc {loc}: {text}" for loc, text in sorted(bare.items())]
    check("missing sheet: loc 4 in row order, once each", bare.get(4),
          "7 deposits  ·  Gold, Iridium  ·  1 worked out")
    check("missing sheet: loc 5 in row order (most rigs first)", bare.get(5),
          "5 deposits  ·  Silver, Gold, Platinum")
    check("missing sheet: loc 6 in row order (Silver no longer first)", bare.get(6),
          "3 deposits  ·  Bauxite, Zzzite, Silver")
    root.destroy()

    for line in report:
        print(line)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]"))
    return 0 if results and all(ok for _, ok, _ in results) else 1


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=out, E2E_LOG=os.path.join(out, "plugin.log"),
               PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"],
                         cwd=PLUGIN, env=env, capture_output=True, text=True, encoding="utf-8")
    report = run.stdout + (f"\n--- stderr ---\n{run.stderr}" if run.stderr else "")
    report += f"\nresult: {'PASS' if run.returncode == 0 else 'FAIL'}\n"
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    print(out)
    return run.returncode


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    raise SystemExit(main())
