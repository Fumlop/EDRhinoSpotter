"""E2E harness: bookmarks on a body the register lacks (issue 23). Checks and blind spots: missingbody.md.

Run from the plugin folder:  python rs_e2etest/missingbody_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
"""

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

import tkinter as tk                                                # noqa: E402

from rs_core import bodies, coverage, database, paths, spotcard    # noqa: E402
from rs_ui import main, scan                                        # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM = "E2E Missing"
MISSING, KNOWN, OTHER = f"{SYSTEM} 3 a", f"{SYSTEM} 5 b", f"{SYSTEM} 5 c"
RADIUS = 1_500_000.0

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def mark(body, material, lat):
    return spotcard.save({"system": SYSTEM, "planet_name": body, "latitude": lat,
                          "longitude": 20.0, "planet_radius": RADIUS, "commodity": material,
                          "rigs": 3, "amount": "High", "density": "Medium",
                          "location_index": 1, "marked_at": "2026-10-28T18:01:00Z"})


def widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from widgets(child)


def texts():
    return [str(w.cget("text")) for w in widgets(window) if isinstance(w, tk.Label)]


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def rail_row(short):
    """Label texts of the rail row whose name label is `short`, or None."""
    for w in widgets(scan._panes["rail"]):
        if isinstance(w, tk.Label) and w.cget("text") == short:
            return [str(s.cget("text")) for s in w.master.winfo_children()
                    if isinstance(s, tk.Label)]
    return None


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
window = None

try:
    main.build(root)
    for i in range(4):
        mark(MISSING, "Monazite", -10.5 + i * 0.1)
    mark(MISSING, "Painite", -11.0)
    mark(KNOWN, "Opal", 5.0)

    register = bodies.Register()
    register.adopt(SYSTEM, [
        {"name": KNOWN, "ground": "rock 80%+ [silicate]", "distance": 3459.0, "locations": 19},
        {"name": OTHER, "ground": "rock 80%+ [silicate]", "distance": 3459.0}])
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",))
    window.geometry("+-4000+-4000")
    pump()

    # 1. rail and header
    scan._state["ground"] = None        # unfold the unknown group
    scan._draw()
    pump()
    row = rail_row("3 a")
    check("1 3 a in the rail", row is not None, texts())
    check("1 3 a row says 5 bm", row is not None and "5 bm" in row, row)
    check("1 5 b listed once", [b["name"] for b in scan._bodies(register, main._sheet, None)]
          .count(KNOWN) == 1)
    header = next((t for t in texts() if "landable" in t), None)
    check("1 header counts 6 bookmarks", header is not None and header.endswith("6 bookmarks"),
          header)

    # 2. pick it
    scan._pick_body(MISSING)
    pump()
    check("2 title names 3 a", window.title().endswith("- 3 a"), window.title())
    body = scan._panes["body"]
    check("2 its 5 bookmarks are the picked body's", body is not None
          and len(body["shown"]) == 5 and body["ground"] is None, body and len(body["shown"]))
    check("2 Painite bookmark on screen", any("Painite" in t for t in texts()))

    # 3. material filter
    scan._state["body"] = None
    mona = [b for b in scan._bodies(register, main._sheet, "Monazite") if b["name"] == MISSING]
    check("3 focus Monazite: 3 a listed, 4 shown", len(mona) == 1 and len(mona[0]["shown"]) == 4,
          mona and len(mona[0]["shown"]))
    opal = [b["name"] for b in scan._bodies(register, main._sheet, "Opal")]
    check("3 focus Opal: 3 a not listed", MISSING not in opal, opal)

    # 4. no body data at all
    empty = bodies.Register()
    empty.adopt(SYSTEM, [])
    names = sorted(b["name"] for b in scan._bodies(empty, main._sheet, None))
    check("4 0 register bodies: 3 a and 5 b listed", names == [MISSING, KNOWN], names)
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    main.stop()
    if window is not None:
        window.destroy()
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
