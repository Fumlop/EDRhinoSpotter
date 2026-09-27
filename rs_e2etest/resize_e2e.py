"""E2E harness: the RhinoData card pane and its map grow with the window. Checks and blind spots: resize.md.

Run from the plugin folder:  python rs_e2etest/resize_e2e.py
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

SYSTEM, BODY, LOC = "Aramo", "Aramo AB 1 a", 11

os.makedirs(os.path.join(DATA, "RhinoSpotter", "db"))
src = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
dst = sqlite3.connect(os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db"))
src.backup(dst)
src.close()
dst.close()
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk                                            # noqa: E402

from rs_core import cards, coverage, coverstore, database       # noqa: E402
from rs_ui import main, scan                                    # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def widths():
    """(rail, card, map canvas) px of the window on screen."""
    card = scan._panes["card"]
    canvas = next((w for w in card.winfo_children() if isinstance(w, tk.Canvas)), None)
    return (scan._panes["rail"].winfo_width(), card.winfo_width(),
            canvas.winfo_width() if canvas is not None else None)


def diamond():
    canvas = next(w for w in scan._panes["card"].winfo_children() if isinstance(w, tk.Canvas))
    xs = canvas.coords(canvas.find_withtag("picked")[0])
    return sum(xs[0::2]) / 4, sum(xs[1::2]) / 4


coverage.clear_old_textures = lambda: None
scan.spotmark.read_status = lambda: {}
main.start(PLUGIN)
main.journal_entry("CMDR Test", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.withdraw()

try:
    maps = coverstore.maps(BODY)
    record = next(r for r in cards.for_system(SYSTEM)
                  if r.get("planet_name") == BODY and r.get("location_index") == LOC
                  and coverage.map_at(maps, BODY, float(r["latitude"]), float(r["longitude"])))
    window = scan.show(root, main._register, main._sheet, None, variable=tk.StringVar(),
                       materials=(main.ALL_MATERIALS,), here=BODY, location=LOC)
    window.geometry("+40+40")
    scan._pick_record(record)
    pump(0.5)
    base = scan._base_width

    # 1. default
    rail, card, px = widths()
    check("1 default: rail, card, map at RAIL_WIDTH, CARD_WIDTH, MAP_PX",
          (rail, card, px) == (scan.RAIL_WIDTH, scan.CARD_WIDTH, scan.MAP_PX), f"{(rail, card, px)}")
    d0 = diamond()

    # 2 + 3 + 4. wider in ten steps, one burst
    draws, real_draw = [], scan._draw
    scan._draw = lambda: (draws.append(1), real_draw())
    target = int(base * 1.6)
    for step in range(1, 11):
        window.geometry(f"{base + (target - base) * step // 10}x{window.winfo_height()}")
        root.update()
    pump(0.6)
    scan._draw = real_draw
    rail, card, px = widths()
    want_card, want_px = round(scan.CARD_WIDTH * target / base), round(scan.MAP_PX * target / base)
    check("2 wider x1.6: card and map grown, rail unchanged",
          rail == scan.RAIL_WIDTH and abs(card - want_card) <= 2 and abs(px - want_px) <= 2,
          f"rail {rail}, card {card} vs {want_card}, map {px} vs {want_px}")
    d1 = diamond()
    k = px / scan.MAP_PX
    want_d = (d0[0] * k, d0[1] * k)
    check("3 diamond at the scaled position", abs(d1[0] - want_d[0]) <= 2 and abs(d1[1] - want_d[1]) <= 2,
          f"{d1} vs {want_d}")
    check("4 ten steps in one burst: one _draw", len(draws) == 1, f"{len(draws)} draws")

    # 5. height only
    draws.clear()
    scan._draw = lambda: (draws.append(1), real_draw())
    window.geometry(f"{window.winfo_width()}x{window.winfo_height() - 60}")
    pump(0.6)
    check("5 height-only change: no _draw", not draws, f"{len(draws)} draws")

    # 6. back to default
    window.geometry(f"{base}x{window.winfo_height()}")
    pump(0.6)
    scan._draw = real_draw
    check("6 back to default: 310 / 240", widths()[1:] == (scan.CARD_WIDTH, scan.MAP_PX), f"{widths()}")

    # 7. narrower than default
    window.geometry(f"{scan.MIN_WIDTH}x{window.winfo_height()}")
    pump(0.6)
    check("7 narrower than default: 310 / 240", widths()[1:] == (scan.CARD_WIDTH, scan.MAP_PX),
          f"{widths()}")
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
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
