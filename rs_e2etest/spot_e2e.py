"""E2E harness for Mark good / Mark bad on the location line. Checks and blind spots: spot.md.

Run from the plugin folder:  python rs_e2etest/spot_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.

The child's LOCALAPPDATA is the run folder, set before the interpreter starts,
so the live database is never opened.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)

BODY = "Aramo A 1"
SYSTEM = "Aramo"
RADIUS = 1_500_000.0        # m
LAT, LON = 12.345678, -45.678901

# (location, material, rigs); None: a bookmark from before location numbers.
MARKS = [(4, "Iridium", 3), (5, "Gold", 4), (6, "Silver", 5), (7, "Osmium", 2), (None, "Bauxite", 6)]


def child():
    import logging
    import tkinter as tk
    sys.path.insert(0, PLUGIN)
    logging.getLogger("RhinoSpotter").addHandler(
        logging.FileHandler(os.environ["E2E_LOG"], encoding="utf-8"))

    from rs_core import bodies, coverage, database, palette, paths, spotcard
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
    for n, (loc, material, rigs) in enumerate(MARKS):
        spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT + n * 1e-2,
                       "longitude": LON, "planet_radius": RADIUS, "commodity": material,
                       "rigs": rigs, "location_index": loc, "marked_at": stamp})

    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "metal-rich", "distance": 10.0,
                             "locations": 7, "volcanism": "", "planet_class": "Metal rich body"}])

    def open_window():
        window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                           materials=("All",), here=BODY, location=1)
        window.geometry("+-4000+-4000")
        root.update()
        return window

    window = open_window()

    def walk(widget):
        """Every widget under `widget`, depth first, in creation (= pack) order."""
        for child in widget.winfo_children():
            yield child
            yield from walk(child)

    def rows():
        """[(loc text, row frame)] of every location line, top to bottom."""
        found = []
        for widget in walk(window):
            texts = [c.cget("text") for c in widget.winfo_children() if isinstance(c, tk.Label)]
            loc = next((t for t in texts if t.startswith("loc ")), None)
            if loc and any(" deposit" in t for t in texts):
                found.append((loc, widget))
        return found

    def order():
        return [loc.split()[1] for loc, _row in rows()]

    def row_of(loc):
        return next((row for text, row in rows() if text == f"loc {loc}"), None)

    def button(row, word):
        """The Mark/Unmark `word` button of `row`, or None."""
        return next((c for c in row.winfo_children() if isinstance(c, tk.Button)
                     and c.cget("text") in (f"Mark {word}", f"Unmark {word}")), None)

    def label(row, kind):
        for c in row.winfo_children():
            if not isinstance(c, tk.Label):
                continue
            text = c.cget("text")
            if {"arrow": text in ("▼", "▶"), "loc": text.startswith("loc "),
                "summary": " deposit" in text,
                "distance": str(c.cget("anchor")) == "e"}[kind]:
                return c
        return None

    def colours(row, kinds=("arrow", "loc", "summary")):
        return [str(label(row, kind).cget("fg")).lower() for kind in kinds]

    gold, muted = palette.GOLD.lower(), palette.MUTED.lower()
    plain = [palette.ACCENT.lower(), palette.FG.lower(), muted, palette.FG_SOFT.lower()]

    def meta():
        with sqlite3.connect(database.PATH) as conn:
            return dict(conn.execute("SELECT key, value FROM meta WHERE key LIKE 'spot:%'"))

    def press(loc, word):
        button(row_of(loc), word).invoke()
        root.update()

    def key(loc, system=SYSTEM):
        return f"spot:{system}|{BODY}|{loc}"

    results, report = [], []

    def check(name, got, want):
        results.append((name, got == want, f"{got!r} != {want!r}"))

    def step(name):
        report.append(f"{name:<24} order {order()}  meta {meta()}  "
                      f"status {scan._status_label.cget('text')!r}")

    four = ("arrow", "loc", "summary", "distance")
    step("start")
    check("14: all five loc lines found", len(rows()), 5)
    row4 = row_of(4)
    parts = (button(row4, "good"), button(row4, "bad"), label(row4, "distance"),
             next(c for c in row4.winfo_children()
                  if isinstance(c, tk.Button) and c.cget("text") == "Share map"))
    check("1: loc 4 has Mark good, Mark bad",
          [p.cget("text") if p is not None else None for p in parts[:2]], ["Mark good", "Mark bad"])
    xs = [p.winfo_x() for p in parts]
    report.append(f"loc 4 x: Mark good {xs[0]}, Mark bad {xs[1]}, distance {xs[2]}, Share map {xs[3]}")
    check("1: Mark good < Mark bad < distance < Share map (x)", xs == sorted(xs) and len(set(xs)) == 4, True)
    # Width left on the loc 4 line, as drawn and at scan.MIN_WIDTH: report only, no check.
    drawn_width, height = window.winfo_width(), window.winfo_height()
    for width in (drawn_width, scan.MIN_WIDTH):
        window.geometry(f"{width}x{height}")
        root.update()
        row4 = row_of(4)
        needed = 0
        for c in row4.winfo_children():
            pad = c.pack_info().get("padx", 0)
            # padx comes back as 8, "8 16" or (8, 16), by Tk version.
            pads = str(pad).strip("()").replace(",", " ").split()
            needed += c.winfo_reqwidth() + sum(int(p) for p in pads)
        report.append(f"window {width} px: loc 4 row {row4.winfo_width()} px, line needs "
                      f"{needed} px (Mark good {button(row4, 'good').winfo_reqwidth()} px, "
                      f"Mark bad {button(row4, 'bad').winfo_reqwidth()} px, "
                      f"summary {label(row4, 'summary').winfo_reqwidth()} px)")
    window.geometry(f"{drawn_width}x{height}")
    root.update()
    check("2: no marks: by number, unnumbered last", order(), ["4", "5", "6", "7", "-"])
    check("2: no marks: loc 4 plain colours", colours(row_of(4), four), plain)
    check("12: unnumbered: both buttons disabled",
          [str(button(row_of("-"), w).cget("state")) for w in ("good", "bad")], ["disabled"] * 2)

    press(6, "good")
    step("good 6")
    check("3: loc 6 first", order(), ["6", "4", "5", "7", "-"])
    check("3: loc 6 arrow, loc, summary gold", colours(row_of(6)), [gold] * 3)
    check("3: loc 6 button renamed", button(row_of(6), "good").cget("text"), "Unmark good")
    check("3: loc 4 still plain", colours(row_of(4), four), plain)
    check("4: meta row 1", meta(), {key(6): "1"})

    window.destroy()
    root.update()
    window = open_window()
    step("reopened")
    check("5: kept on reopen: loc 6 first", order(), ["6", "4", "5", "7", "-"])
    check("5: kept on reopen: loc 6 gold", colours(row_of(6)), [gold] * 3)

    press(4, "bad")
    step("bad 4")
    check("6: loc 4 last", order(), ["6", "5", "7", "-", "4"])
    check("6: loc 4 arrow, loc, summary, distance muted", colours(row_of(4), four), [muted] * 4)
    check("6: loc 4 button renamed", button(row_of(4), "bad").cget("text"), "Unmark bad")
    check("6: meta row -1", meta(), {key(6): "1", key(4): "-1"})

    press(7, "good")
    step("good 7")
    check("7: two good by number", order(), ["6", "7", "5", "-", "4"])

    press(6, "bad")
    step("bad on good 6")
    check("8: good -> bad: loc 6 among the bad, by number", order(), ["7", "5", "-", "4", "6"])
    check("8: good -> bad: one row, -1", meta(), {key(4): "-1", key(6): "-1", key(7): "1"})
    check("8: good -> bad: loc 6 muted", colours(row_of(6), four), [muted] * 4)

    press(4, "bad")
    step("unmark bad 4")
    check("9: unmark: loc 4 back at its number", order(), ["7", "4", "5", "-", "6"])
    check("9: unmark: row deleted", meta(), {key(6): "-1", key(7): "1"})
    check("9: unmark: loc 4 plain", colours(row_of(4), four), plain)

    with sqlite3.connect(database.PATH) as conn:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, '1')", (key(5, "Other"),))
    scan._draw()
    root.update()
    step("other system's loc 5")
    check("10: another system's mark: loc 5 plain", colours(row_of(5), four), plain)
    check("10: another system's mark: order unchanged", order(), ["7", "4", "5", "-", "6"])

    with sqlite3.connect(database.PATH) as conn:
        conn.execute("INSERT INTO meta (key, value) VALUES (?, '2')", (key(5),))
    scan._draw()
    root.update()
    step("value '2' on loc 5")
    check("11: bad value: loc 5 plain", colours(row_of(5), four), plain)
    check("11: bad value: order unchanged", order(), ["7", "4", "5", "-", "6"])
    with open(os.environ["E2E_LOG"], encoding="utf-8") as handle:
        logged = [line.strip() for line in handle if "skipped, not 1 or -1" in line]
    report += [f"log: {line}" for line in logged[:1]]
    check("11: bad value: logged", bool(logged), True)
    with sqlite3.connect(database.PATH) as conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (key(5),))

    lock = sqlite3.connect(database.PATH, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")
    press(5, "good")
    lock.execute("ROLLBACK")
    lock.close()
    step("write blocked on 5")
    check("13: failed write on the status line", scan._status_label.cget("text"),
          "The mark could not be written - see the EDMC log.")
    check("13: failed write: order unchanged", order(), ["7", "4", "5", "-", "6"])
    check("13: failed write: loc 5 plain", colours(row_of(5), four), plain)
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
