"""E2E harness: an open RhinoData window follows a jump. Checks and blind spots: scan-arrive.md.

Run from the plugin folder:  python rs_e2etest/scan_arrive_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the live db is
copied in with sqlite3's backup API, read only.
"""

import os
import sqlite3
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")

HOME, AWAY, BROWSED = "Aramo", "43 G. Canis Minoris", "HIP 44291"

os.makedirs(os.path.join(DATA, "RhinoSpotter", "db"))
if os.path.exists(LIVE_DB):
    src = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    dst = sqlite3.connect(os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db"))
    src.backup(dst)
    src.close()
    dst.close()
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import tkinter as tk                                     # noqa: E402

from rs_core import coverage, database                   # noqa: E402
from rs_ui import main, scan                             # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def jump(system):
    main.journal_entry("CMDR Test", False, system, None,
                       {"event": "FSDJump", "StarSystem": system}, {})
    root.update()


def title():
    return scan._window.title() if scan.is_open() else ""


coverage.clear_old_textures = lambda: None               # plugin folder, not under test
main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
shows = []
real_show = scan.show

try:
    jump(HOME)
    real_show(root, main._register, main._sheet, None,
              variable=tk.StringVar(), materials=(main.ALL_MATERIALS,))
    root.update()
    check("1 window opens on the live system", title().startswith(f"RhinoData - {HOME}"), title())
    scan._state["body"] = f"{HOME} A 1"

    scan.show = lambda *a, **k: shows.append(a)
    jump(AWAY)
    check("2 jump redraws the open window for the new system",
          title().startswith(f"RhinoData - {AWAY}"), title())
    check("3 picked body of the old system dropped",
          not (scan._state["body"] or "").startswith(HOME), repr(scan._state["body"]))
    check("4 window not raised: scan.show not called on the jump", not shows, f"{len(shows)} calls")

    jump(HOME)
    check("5 jump back redraws for the first system",
          title().startswith(f"RhinoData - {HOME}"), title())

    scan._browse(BROWSED)
    root.update()
    jump(AWAY)
    check("6 a system browsed from the search box stays shown after a jump",
          title().startswith(f"RhinoData - {BROWSED}"), title())
    scan._back_to_live()
    root.update()
    check("7 back to live after the jump shows the new system",
          title().startswith(f"RhinoData - {AWAY}"), title())

    # Control: without the arrival hook the window must go stale, or checks 2 and 5 prove nothing.
    real_arrived = scan.arrived
    scan.arrived = lambda: None
    jump(HOME)
    check("8 control: with scan.arrived a no-op the title stays stale",
          title().startswith(f"RhinoData - {AWAY}"), title())
    scan.arrived = real_arrived
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    scan.show = real_show
    root.destroy()

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
report = "\n".join(lines)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(os.path.join(OUT, "report.txt"))
sys.exit(1 if failed else 0)
