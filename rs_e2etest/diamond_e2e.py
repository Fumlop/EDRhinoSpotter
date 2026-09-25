"""E2E harness for the picked bookmark's diamond on the card map. Checks and
blind spots: diamond.md.

Run from the plugin folder:  python rs_e2etest/diamond_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
"""

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
    import tkinter as tk
    from rs_core import cards, coverage, coverstore, database, grounds, palette
    from rs_ui import scan
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    fails = []

    def check(name, ok, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            fails.append(f"{name} {detail}")

    with database.connect() as conn:
        systems = [s for (s,) in conn.execute("SELECT DISTINCT system FROM bookmarks")]
    records = [r for s in systems for r in cards.for_system(s)]
    (body_name, _), _ = Counter((r.get("planet_name"), r.get("location_index"))
                                for r in records).most_common(1)[0]
    body = {"name": body_name, "marks": [r for r in records if r.get("planet_name") == body_name]}
    maps = coverstore.maps(body_name)
    sheet = grounds.Sheet()
    root = tk.Tk()
    root.withdraw()
    dots = [palette.rgb(palette.GOOD), coverage.MARK_DEPLETED]

    def near_dot(photo, x, y):
        """Some pixel within 2 px of (x, y) is a dot colour, within 40 a channel."""
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                px, py = int(x) + dx, int(y) + dy
                if 0 <= px < scan.MAP_PX and 0 <= py < scan.MAP_PX:
                    got = photo.get(px, py)
                    if any(all(abs(a - b) <= 40 for a, b in zip(got, dot)) for dot in dots):
                        return True
        return False

    on_map = coverage.map_at(maps, body_name, body["marks"][0]["latitude"],
                             body["marks"][0]["longitude"])
    picks = [r for r in body["marks"]
             if coverage.map_at(maps, body_name, r["latitude"], r["longitude"]) == on_map][:4]
    print(f"{body_name} {on_map}: {len(picks)} picks")
    photo = centres = None
    for n, record in enumerate(picks, 1):
        frame = tk.Frame(root)
        scan._location_map(frame, sheet, body, record, maps)
        canvases = [w for w in frame.winfo_children() if isinstance(w, tk.Canvas)]
        check(f"pick {n}: a card map", len(canvases) == 1)
        if not canvases:
            continue
        canvas = canvases[0]
        item = canvas.find_withtag("picked")
        check(f"pick {n}: a diamond", len(item) == 1)
        if not item:
            continue
        xs = canvas.coords(item[0])
        x, y = sum(xs[0::2]) / 4, sum(xs[1::2]) / 4
        if photo is None:
            photo = scan._map_picture[1]
        check(f"pick {n}: picture not re-rendered", scan._map_picture[1] is photo)
        check(f"pick {n}: on its dot at {x:.0f},{y:.0f}", near_dot(photo, x, y),
              f"pixel {photo.get(int(x), int(y))}")
        check(f"pick {n}: blue, BG outline",
              canvas.itemcget(item[0], "fill") == scan.ACCENT
              and canvas.itemcget(item[0], "outline") == scan.BG)
        if centres and (x, y) in centres:
            fails.append(f"pick {n}: diamond did not move")
        centres = (centres or []) + [(x, y)]
        frame.destroy()

    frame = tk.Frame(root)
    nowhere = dict(picks[0], latitude=-picks[0]["latitude"], longitude=picks[0]["longitude"] + 90)
    scan._location_map(frame, sheet, body, nowhere, maps)
    check("no saved map: no canvas", not frame.winfo_children())

    # A pick in the list: two rows relit, the card rebuilt, nothing else.
    import time
    from rs_core import bodies
    print("pick in the list")
    register = bodies.Register()
    register.adopt(picks[0]["system"], [{"name": body_name, "ground": "rock 80%+ [metallic magma]",
                                         "distance": 10.0, "locations": 19, "volcanism": "",
                                         "planet_class": "Rocky body"}])
    loc = picks[0]["location_index"]
    same_loc = [r for r in body["marks"] if r.get("location_index") == loc][:3]
    window = scan.show(root, register, sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=body_name, location=loc)
    window.geometry("+-4000+-4000")
    scan._pick_record(same_loc[0])
    root.update()
    draws, real_draw = [], scan._draw

    def counted():
        start = time.perf_counter()
        real_draw()
        draws.append(time.perf_counter() - start)
    scan._draw = counted
    rows_before = dict(scan._rows)
    rail = window.winfo_children()[0].winfo_children()[0]
    diamond_at = []
    for record in same_loc[1:]:
        old = scan._state["selected"]
        start = time.perf_counter()
        scan._pick_record(record)
        root.update()
        took = time.perf_counter() - start
        key = scan._key(record)
        check("pick: no _draw", len(draws) == 0, len(draws))
        check("pick: rows and rail are the same widgets",
              scan._rows == rows_before and bool(rail.winfo_exists()))
        lit = (scan._rows[old].cget("bg"), scan._rows[key].cget("bg"))
        check("pick: old row unlit, new row lit", lit == (scan.BG, scan.PANEL), lit)
        canvas = next((w for w in scan._panes["card"].winfo_children()
                       if isinstance(w, tk.Canvas)), None)
        item = canvas.find_withtag("picked") if canvas is not None else ()
        xs = canvas.coords(item[0]) if item else []
        diamond_at.append((round(sum(xs[0::2]) / 4), round(sum(xs[1::2]) / 4)) if xs else None)
        check("pick: card on the new bookmark", scan._card_tons.get("key") == key,
              scan._card_tons.get("key"))
        print(f"     pick {took * 1000:.1f} ms")
    check("pick: diamond moved", len(set(diamond_at)) == len(diamond_at) and None not in diamond_at,
          diamond_at)
    scan._draw()
    print(f"     _draw {draws[-1] * 1000:.1f} ms")
    draws.clear()
    hidden = next(r for r in body["marks"] if r.get("location_index") != loc)
    scan._pick_record(hidden)
    check("pick of an undrawn row: one _draw", len(draws) == 1, len(draws))
    window.destroy()
    root.destroy()

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
