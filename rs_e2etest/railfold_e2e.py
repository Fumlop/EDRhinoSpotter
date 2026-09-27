"""E2E harness: the RhinoData rail folds by ground and sorts by the picked material. Checks and blind spots: railfold.md.

Run from the plugin folder:  python rs_e2etest/railfold_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the live db is
copied in with sqlite3's backup API, read only.
"""

import os
import sqlite3
import sys
import time
import traceback

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")

HOME, AWAY = "Aramo", "HIP 44291"

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

from rs_core import cards, coverage, database, grounds   # noqa: E402
from rs_ui import main, scan                             # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

results = []
dumps = []
ARROWS = ("▼", "▶")


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def jump(system):
    main.journal_entry("CMDR Test", False, system, None,
                       {"event": "FSDJump", "StarSystem": system}, {})
    root.update()


def texts(widget):
    """Label texts of a frame's children, in pack order."""
    return [str(w.cget("text")) for w in widget.winfo_children() if isinstance(w, tk.Label)]


def rail_rows():
    """[(kind, texts, frame)] of the rail listing in pack order; kind 'ground' or 'body'."""
    rail = scan._panes["rail"]
    stack, rows = [rail], []
    while stack:
        widget = stack.pop(0)
        children = widget.winfo_children()
        found = texts(widget)
        if found and found[0] in ARROWS:
            rows.append(("ground", found, widget))
            continue
        # _rail_body: row -> inner -> labels, name first
        inner = texts(children[0]) if len(children) == 1 else []
        if len(inner) == 4 and (inner[1].endswith(" Ls") or inner[1] == "-"):
            rows.append(("body", inner, widget))
            continue
        stack[0:0] = children
    return rows


def headers():
    return [(t[0], t[1], t[2] if len(t) > 2 else "") for kind, t, _ in rail_rows() if kind == "ground"]


def open_grounds():
    return [label.rsplit(" (", 1)[0] for arrow, label, _ in headers() if arrow == "▼"]


def label_of(ground):
    return grounds.label(ground)


def dump(title):
    dumps.append(f"--- {title}")
    for kind, t, _ in rail_rows():
        dumps.append(("  " if kind == "body" else "") + " | ".join(t))


def click_header(label):
    for kind, t, frame in rail_rows():
        if kind == "ground" and t[1].startswith(label + " ("):
            frame.event_generate("<Button-1>")
            root.update()
            return True
    return False


def body_names():
    return [t[0] for kind, t, _ in rail_rows() if kind == "body"]


coverage.clear_old_textures = lambda: None               # plugin folder, not under test
# The live Status.json moves the pick (_mark_here, _unfold_near); {} = torn read, ignored.
status = {}
scan.spotmark.read_status = lambda: dict(status)
main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
var = tk.StringVar()

try:
    jump(HOME)
    register, sheet = main._register, main._sheet
    by_ground = dict(register.by_ground())
    assert len(by_ground) >= 3, by_ground.keys()

    # A material with a rate on 2+ of HOME's grounds and no row on at least one.
    materials = sorted({row["material"] for rows in sheet.grounds.values() for row in rows})
    focus = none_ground = None
    for material in materials:
        rated = [g for g in by_ground if sheet.rate(g, material) is not None]
        unrated = [g for g in by_ground if sheet.rate(g, material) is None]
        if len({sheet.rate(g, material) for g in rated}) >= 2 and unrated:
            focus, none_ground = material, unrated[0]
            break
    assert focus, "no material splits HOME's grounds"
    here_body = by_ground[none_ground][0]["name"]
    dumps.append(f"HOME={HOME} focus={focus} here={here_body} ({none_ground})")

    # 1: here given, all materials
    scan.show(root, register, sheet, None, variable=var, materials=(main.ALL_MATERIALS,),
              here=here_body)
    root.update()
    dump("1 open, here, all materials")
    check("1 open with here: only its ground open",
          open_grounds() == [label_of(none_ground)], repr(open_grounds()))

    # 3: all materials keeps GROUND_ORDER
    order = [label_of(g) for g, _ in register.by_ground()]
    shown = [label.rsplit(" (", 1)[0] for _, label, _ in headers()]
    check("3 all materials: header order == GROUND_ORDER", shown == order, repr(shown))

    # 8: collapsed header carries the body count
    folded = [(label, g) for g in by_ground for _, label, _ in headers()
              if label.startswith(label_of(g) + " (") and g != none_ground]
    label, g = folded[0]
    check("8 collapsed header carries body count", label.endswith(f"({len(by_ground[g])})"), label)

    # 2: in space, picked body elsewhere
    scan._window.destroy()
    root.update()
    other = next(g for g in by_ground if g != none_ground)
    scan._state["body"] = by_ground[other][0]["name"]
    scan.show(root, register, sheet, None, variable=var, materials=(main.ALL_MATERIALS,))
    root.update()
    dump("2 open, in space, picked in " + other)
    check("2 open without here: only picked body's ground open",
          open_grounds() == [label_of(other)], repr(open_grounds()))
    scan._window.destroy()
    root.update()

    # 11: in the SRV at a bookmark on a body of a third ground
    record = next(r for r in cards.for_system(HOME)
                  if r.get("latitude") is not None and not r.get("depleted_at")
                  and not any(b["name"] == r["planet_name"]
                              for g in (none_ground, other) for b in by_ground[g]))
    srv_ground = next(g for g, found in by_ground.items()
                      if any(b["name"] == record["planet_name"] for b in found))
    status.update(Flags=coverage.IN_SRV, BodyName=record["planet_name"],
                  Latitude=record["latitude"], Longitude=record["longitude"],
                  PlanetRadius=1_000_000.0)
    scan.show(root, register, sheet, None, variable=var, materials=(main.ALL_MATERIALS,),
              here=here_body)
    root.update()
    dump(f"11 open, SRV at {record['planet_name']}")
    check("11 SRV at a bookmark: only that body's ground open",
          open_grounds() == [label_of(srv_ground)],
          f"body={scan._state['body']!r} open={open_grounds()}")
    scan._window.destroy()
    root.update()
    status.clear()
    scan._state["here"] = scan._state["here_picked"] = None

    # 4: material picked, here in a ground without a row
    scan.show(root, register, sheet, focus, variable=var, materials=(main.ALL_MATERIALS, focus),
              here=here_body)
    root.update()
    dump(f"4 open, here, focus {focus}")
    rates = [(label, right) for _, label, right in headers()]
    pcts = [float(right.split("%")[0]) if "%" in right else None for _, right in rates]
    rated = [p for p in pcts if p is not None]
    check("4 material: rates descending, no-row ground last",
          rated == sorted(rated, reverse=True) and pcts[-1] is None
          and pcts.count(None) == 1 and len(rated) >= 2, repr(rates))

    # 5 + 6: click a folded header
    target = next(label.rsplit(" (", 1)[0] for arrow, label, _ in headers() if arrow == "▶")
    outer = scan._window.winfo_children()[0]
    middle_card = [w for w in outer.winfo_children() if w is not scan._panes.get("rail")]
    draws, real_draw = [], scan._draw
    scan._draw = lambda: (draws.append(1), real_draw())
    before = len(body_names())
    click_header(target)
    dump(f"5 after click on {target}")
    check("5 click unfolds it and folds the one open before",
          open_grounds() == [target] and len(body_names()) != before,
          f"{before} -> {len(body_names())} bodies, open={open_grounds()}")
    check("5 only the rail rebuilt: no _draw, middle and card the same widgets",
          not draws and all(w.winfo_exists() for w in middle_card), f"{len(draws)} draws")
    scan._draw = real_draw

    # 7: survives a full redraw
    scan.refresh()
    root.update()
    check("7 fold state survives scan.refresh()", open_grounds() == [target], repr(open_grounds()))
    before = len(body_names())

    click_header(target)
    check("6 second click folds it: none open",
          open_grounds() == [] and body_names() == [],
          f"{len(body_names())} bodies, open={open_grounds()}")

    # 10: control, toggle a no-op
    real_toggle = scan._toggle_ground
    scan._toggle_ground = lambda ground: None
    click_header(target)
    check("10 control: with _toggle_ground a no-op the click unfolds nothing",
          target not in open_grounds(), repr(open_grounds()))
    scan._toggle_ground = real_toggle

    # 9: jump resets to the new system's picked body
    click_header(target)
    jump(AWAY)
    dump(f"9 after jump to {AWAY}")
    picked = scan._state["body"]
    away = dict(main._register.by_ground())
    want = [label_of(g) for g, found in away.items() if any(b["name"] == picked for b in found)]
    check("9 jump: only the new picked body's ground open",
          open_grounds() == want, f"picked={picked!r} open={open_grounds()} want={want}")
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    root.destroy()

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed\n")
report = "\n".join(lines + dumps)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(os.path.join(OUT, "report.txt"))
sys.exit(1 if failed else 0)
