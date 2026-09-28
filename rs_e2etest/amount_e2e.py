"""E2E harness: the panel's Amount starts at High. Checks and blind spots: amount.md.

Run from the plugin folder:  python rs_e2etest/amount_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
JOURNALS = os.path.join(OUT, "journals")
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.makedirs(JOURNALS)
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk                                     # noqa: E402

from rs_core import cards, coverage, database, paths     # noqa: E402
from rs_ui import main                                   # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E Amount", "E2E Amount 1 a"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def status(lat):
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": 0x200000 | 0x10, "BodyName": body_name, "Latitude": lat,
                   "Longitude": LON, "Altitude": 0, "PlanetRadius": RADIUS, "Heading": 0}, handle)


def rows():
    return [r for r in cards.for_system(SYSTEM) if r.get("planet_name") == BODY]


def pump_until(until, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.05)
    return False


body_name = BODY
paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.withdraw()

try:
    main.build(root)
    root.update()

    # 1. the default
    check("1 Amount starts at High", main._amount.get() == "High", repr(main._amount.get()))

    # 3. the menu keeps "-"
    menu = main._amount_menu["menu"] if hasattr(main, "_amount_menu") else None
    if menu is None:
        menu = next(w for w in main._frame.winfo_children()
                    if isinstance(w, tk.OptionMenu) and w.cget("textvariable") == str(main._amount))["menu"]
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
    check("3 menu: '-' first, then High, Medium, Low, Depleted",
          labels == [main.NOT_READ, "High", "Medium", "Low", "Depleted"], labels)

    # 2. untouched panel, material picked, pressed
    material = main._materials()[0]
    main._material.set(material)
    main._loc.set("1")      # an empty Loc opens the No location popup (location_e2e)
    status(LAT)
    main.make_card()
    check("2 bookmark saved", pump_until(lambda: len(rows()) == 1), f"{len(rows())} rows")
    check("2 its amount is High", rows() and rows()[0].get("amount") == "High",
          rows() and rows()[0].get("amount"))

    # 4. '-' picked, 300 m north: no amount
    main._amount.set(main.NOT_READ)
    status(LAT + math.degrees(300 / RADIUS))
    main.make_card()
    check("4 second bookmark saved", pump_until(lambda: len(rows()) == 2), f"{len(rows())} rows")
    newest = max(rows(), key=lambda r: r.get("latitude") or 0) if rows() else {}
    check("4 '-' saves no amount", newest.get("amount") is None, repr(newest.get("amount")))
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    main.stop()
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
