"""E2E harness: a new bookmark saved at Amount Depleted is greyed on the maps. Checks and blind spots: newdepleted.md.

Run from the plugin folder:  python rs_e2etest/newdepleted_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and minimap.png. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

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

from rs_core import (bodies, cards, coverage, database, grounds, paths,  # noqa: E402
                     spotcard, yields)
from rs_ui import main, minimap, scan                               # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E NewDepleted", "E2E NewDepleted 1 a"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0
DAY = 86400

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def stamp(offset_s=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def north(metres):
    return LAT + math.degrees(metres / RADIUS)


def east(metres):
    return LON + math.degrees(metres / (RADIUS * math.cos(math.radians(LAT))))


def status(lat, lon):
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": 0x200000 | 0x10, "BodyName": BODY, "Latitude": lat,
                   "Longitude": lon, "Altitude": 0, "PlanetRadius": RADIUS, "Heading": 0}, handle)


def rows():
    return {r["id"]: r for r in cards.for_system(SYSTEM)}


def row(id):
    with database.connect() as conn:
        return json.loads(conn.execute("SELECT data FROM bookmarks WHERE id = ?",
                                       (id,)).fetchone()[0])


def widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from widgets(child)


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def pump_until(until, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.05)
    return False


def mark_new(amount, lat, lon):
    """The panel's Bookmark press on a fresh spot; the new row's id or None."""
    before = set(rows())
    main._amount.set(amount)
    status(lat, lon)
    main.make_card()
    pump_until(lambda: len(rows()) > len(before))
    new = set(rows()) - before
    return new.pop() if new else None


def legacy(lon, days):
    """A row as _render_card wrote it before the fix: Amount Depleted, no depleted_at."""
    return spotcard.save({"system": SYSTEM, "planet_name": BODY, "latitude": LAT,
                          "longitude": lon, "planet_radius": RADIUS, "commodity": material,
                          "rigs": 3, "amount": "Depleted", "location_index": 1,
                          "marked_at": stamp(-days * DAY)})


def flags(tuples, cover, ids):
    """{id: depleted} matching (x, y, code, depleted, ...) tuples to rows by position."""
    found = {}
    for id in ids:
        x, y = cover.xy(row(id)["latitude"], row(id)["longitude"])
        for t in tuples:
            if abs(t[0] - x) < 1e-6 and abs(t[1] - y) < 1e-6:
                found[id] = t[3]
    return found


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.withdraw()
window = None

try:
    main.build(root)
    main._cancel_landed()
    material = main._materials()[0]
    main._material.set(material)
    main._loc.set("1")

    # 1. new bookmark at Amount Depleted
    new = mark_new("Depleted", north(2000), LON)
    check("1 new bookmark saved", new is not None)
    r = row(new)
    check("1 depleted_at set", bool(r.get("depleted_at")), r.get("depleted_at"))
    check("1 depleted_at is marked_at", r.get("depleted_at") == r.get("marked_at"),
          f"{r.get('depleted_at')} vs {r.get('marked_at')}")
    check("1 depleted_at parses", yields.days_since_depleted(r) is not None
          and abs(yields.days_since_depleted(r)) < 0.01, yields.days_since_depleted(r))

    # 1b. new bookmark at High
    high = mark_new("High", north(-2000), LON)
    check("1b High bookmark saved", high is not None)
    check("1b High: no depleted_at", high is not None and not row(high).get("depleted_at"),
          high and row(high).get("depleted_at"))

    # 2. rows saved before the fix
    young, old = legacy(east(2000), 2), legacy(east(-2000), 20)
    yields.regrow()
    check("2 2 d old: depleted_at = marked_at",
          row(young).get("depleted_at") == row(young).get("marked_at"), row(young))
    check("2 20 d old: lifted, not stamped",
          (row(old).get("depleted_at"), row(old).get("amount"), len(row(old).get("regrown") or []))
          == (None, None, 1), row(old))
    before = (row(young), row(old))
    check("2 second regrow: lifts nothing, rows unchanged",
          (yields.regrow(), (row(young), row(old))) == (0, before), row(young))

    # 3. both map paths
    cover = coverage.Coverage(BODY, LAT, LON, RADIUS)
    want = {new: True, young: True, old: False, high: False}
    marks_mm = [(*cover.xy(lat, lon), code, depleted, value, rigs)
                for lat, lon, code, depleted, value, rigs in minimap._bookmarks(SYSTEM, BODY)]
    got = flags(marks_mm, cover, want)
    check("3 minimap._bookmarks flags", got == want, f"{got}")
    marks_sc, _ = scan._map_marks(cover, [r for r in cards.for_system(SYSTEM) if r.get('planet_name') == BODY], grounds.Sheet())
    got = flags(marks_sc, cover, want)
    check("3 scan._map_marks flags", got == want, f"{got}")

    # 4. the ring on the drawn map
    side = 480
    image = coverage.render(cover, 0, 0, None, side, marks=marks_mm)
    image.save(os.path.join(OUT, "minimap.png"))
    scale = side / (2 * coverage.VIEW_M)
    mx, my = cover.xy(row(new)["latitude"], row(new)["longitude"])
    cx, cy = side / 2 + mx * scale, side / 2 - my * scale
    rr = coverage._mark_radius(side)
    inner = image.getpixel((int(round(cx)), int(round(cy))))
    sides = [coverage.MARK_DEPLETED in [image.getpixel((int(round(cx + sign * d)), int(round(cy))))
                                        for d in range(int(rr) - 3, int(rr) + 1)]
             for sign in (-1, 1)]
    check("4 new one drawn as a hollow ring", inner != coverage.MARK and inner != coverage.MARK_DEPLETED
          and all(sides), f"centre {inner}, left/right {sides}")

    # 5. Set active on the card
    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "metal-rich", "distance": 10.0,
                             "locations": 7, "volcanism": "", "planet_class": "Metal rich body"}])
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=1)
    window.geometry("+-4000+-4000")
    scan._state["selected"] = scan._key(rows()[new])
    scan._draw()
    pump()
    button = next((w for w in widgets(window)
                   if isinstance(w, tk.Button) and w.cget("text") == "Set active"), None)
    check("5 card button reads Set active", button is not None)
    if button is not None:
        button.invoke()
        pump()
    check("5 Set active: depleted_at gone, Amount unread",
          (row(new).get("depleted_at"), row(new).get("amount")) == (None, None), row(new))
    yields.regrow()
    check("5 regrow after Set active: still active", not row(new).get("depleted_at"), row(new))
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
