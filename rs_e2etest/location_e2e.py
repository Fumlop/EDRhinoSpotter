"""E2E harness: Location spinbox, the No location popup, loc 0. Checks and blind spots: location.md.

Run from the plugin folder:  python rs_e2etest/location_e2e.py
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
from rs_ui import main, scan                             # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E Location", "E2E Location 1 a"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0
STEP = math.degrees(300 / RADIUS)       # 300 m north: beyond cards.SAME_SPOT_M (100 m)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def status(lat, index=None, flags=0x200000 | 0x10):
    data = {"Flags": flags, "BodyName": BODY, "Latitude": lat, "Longitude": LON,
            "Altitude": 0, "PlanetRadius": RADIUS, "Heading": 0}
    if index is not None:
        data["Destination"] = {"Name": f"$SAA_Unknown_Signal:#index={index};"}
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def rows():
    return [r for r in cards.for_system(SYSTEM) if r.get("planet_name") == BODY]


def at(lat):
    return next((r for r in rows() if abs((r.get("latitude") or 0) - lat) < STEP / 10), None)


def pump_until(until, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.05)
    return False


def popup():
    return next((w for w in widgets(root, tk.Toplevel)
                 if w.winfo_exists() and w.title() == "No location"), None)


def widgets(parent, kind):
    found = []
    for child in parent.winfo_children():
        if isinstance(child, kind):
            found.append(child)
        found += widgets(child, kind)
    return found


def press(value=None, button="Bookmark"):
    """make_card with the popup answered: `value` typed into its spinbox, `button`
    pressed. Returns (popup seen, its text, spinbox from/to)."""
    seen = {}

    def answer():
        box = popup()
        if box is None:
            return
        spin = widgets(box, tk.Spinbox)[0]
        seen.update(master=box.master,
                    text=" ".join(w.cget("text") for w in widgets(box, tk.Label)),
                    range=(float(spin.cget("from")), float(spin.cget("to"))),
                    start=spin.get())
        if value is not None:
            spin.delete(0, "end")
            spin.insert(0, value)
        next(b for b in widgets(box, tk.Button) if b.cget("text") == button).invoke()

    root.after(300, answer)
    main.make_card()
    root.update()
    return seen


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.withdraw()

try:
    main.build(root)
    root.update()
    main._material.set(main._materials()[0])

    # 1. the panel's Location is a spinbox 0-50, empty at start
    spins = [w for w in widgets(main._frame, tk.Spinbox)
             if w.cget("textvariable") == str(main._loc)]
    check("1 Location is a Spinbox", len(spins) == 1, f"{len(spins)} found")
    if spins:
        check("1 range 0-50", (float(spins[0].cget("from")), float(spins[0].cget("to")))
              == (0.0, 50.0), (spins[0].cget("from"), spins[0].cget("to")))
    check("1 Loc empty at start", main._loc.get() == "", repr(main._loc.get()))

    # 2. empty Loc, nothing targeted, Cancel: popup, no bookmark
    lat = LAT
    status(lat)
    seen = press(button="Cancel")
    check("2 popup shown", bool(seen), seen)
    check("2 popup warns loc 0 gets no map", "no map" in seen.get("text", ""), seen.get("text"))
    check("2 popup spinbox 0-50, starts at 0",
          seen.get("range") == (0.0, 50.0) and seen.get("start") == "0", seen)
    root.update()
    time.sleep(0.5)
    root.update()
    check("2 Cancel saves nothing", len(rows()) == 0, f"{len(rows())} rows")
    check("2 status says cancelled", "cancelled" in main._status.cget("text"),
          main._status.cget("text"))
    check("2 popup gone", popup() is None)

    # 3. popup left at 0: bookmark at loc 0, Loc stays empty
    seen = press()
    check("3 popup shown", bool(seen), seen)
    check("3 saved at loc 0", pump_until(lambda: at(lat) is not None)
          and at(lat).get("location_index") == 0, at(lat))
    check("3 Loc stays empty", main._loc.get() == "", repr(main._loc.get()))

    # 4. popup answered 7: bookmark at loc 7, Loc shows 7
    lat += STEP
    status(lat)
    seen = press("7")
    check("4 popup shown", bool(seen), seen)
    check("4 saved at loc 7", pump_until(lambda: at(lat) is not None)
          and at(lat).get("location_index") == 7, at(lat))
    check("4 Loc set to 7", main._loc.get() == "7", repr(main._loc.get()))

    # 5. Loc typed: no popup
    lat += STEP
    status(lat)
    main._loc.set("4")
    seen = press(button="Cancel")
    check("5 typed Loc: no popup", not seen, seen)
    check("5 saved at loc 4", pump_until(lambda: at(lat) is not None)
          and at(lat).get("location_index") == 4, at(lat))

    # 6. Loc empty, Status.json targets index 12: no popup
    lat += STEP
    status(lat, index=12)
    main._loc.set("")
    seen = press(button="Cancel")
    check("6 targeted: no popup", not seen, seen)
    check("6 saved at loc 12", pump_until(lambda: at(lat) is not None)
          and at(lat).get("location_index") == 12, at(lat))

    # 7. not on the surface: no popup, no bookmark
    main._loc.set("")
    count = len(rows())
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": 0x200000, "BodyName": BODY}, handle)
    seen = press(button="Cancel")
    root.update()
    check("7 off surface: no popup", not seen, seen)
    check("7 off surface: nothing saved", len(rows()) == count, f"{len(rows())} rows")

    # 8. a map under the loc 0 bookmark ties to no location; loc 7 on a map does
    zero, seven = at(LAT), at(LAT + STEP)
    found = [("Map 1", {"origin": [LAT, LON], "radius": RADIUS})]
    mapped, unknown = coverage.mapped_locations(found, BODY, [zero])
    check("8 loc 0 ties no map", mapped == {} and unknown == ["Map 1"], (mapped, unknown))
    found7 = [("Map 2", {"origin": [LAT + STEP, LON], "radius": RADIUS})]
    mapped, unknown = coverage.mapped_locations(found7, BODY, [seven])
    check("8 control: loc 7 ties its map", mapped == {7: ["Map 2"]}, (mapped, unknown))

    # 9. Touchdown on the loc 0 bookmark does not fill Loc with 0
    # within=100 m: the bookmarks are 300 m apart, SAME_LOCATION_M reaches past that
    near0 = cards.location_at(SYSTEM, BODY, LAT, LON, RADIUS, within=100)
    near7 = cards.location_at(SYSTEM, BODY, LAT + STEP, LON, RADIUS, within=100)
    check("9 location_at skips loc 0", near0 is None, near0)
    check("9 control: location_at finds loc 7", (near7 or (None,))[0] == 7, near7)

    # 10. Edit: Location is a spinbox 0-50 holding 0; saving 3 re-books it
    scan._window = root
    edit = {}

    def in_edit():
        box = next((w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                    and w.winfo_exists() and w.title() == "Edit bookmark"), None)
        if box is None:
            return
        spin = next(w for w in widgets(box, tk.Spinbox) if int(w.grid_info()["row"]) == 6)
        edit.update(range=(float(spin.cget("from")), float(spin.cget("to"))), value=spin.get())
        spin.delete(0, "end")
        spin.insert(0, "3")
        scan._draw = lambda: None
        next(b for b in widgets(box, tk.Button) if b.cget("text") == "Save").invoke()

    root.after(300, in_edit)
    scan._edit_bookmark(zero)
    check("10 Edit Location is a Spinbox 0-50 at 0",
          edit.get("range") == (0.0, 50.0) and edit.get("value") == "0", edit)
    check("10 Edit saved loc 3", at(LAT) and at(LAT).get("location_index") == 3, at(LAT))

    # 11. Edit of a bookmark with no location: the spinbox shows empty, Save keeps None
    lat += STEP
    status(lat)
    main._loc.set("5")
    main.make_card()
    pump_until(lambda: at(lat) is not None)
    with database.connect() as conn:
        conn.execute("UPDATE bookmarks SET location_index = NULL, data = "
                     "json_set(data, '$.location_index', json('null')) WHERE id = ?",
                     (at(lat)["id"],))
    check("11 setup: bookmark has no location", at(lat).get("location_index") is None, at(lat))
    blank = {}

    def in_blank_edit():
        box = next((w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                    and w.winfo_exists() and w.title() == "Edit bookmark"), None)
        if box is None:
            return
        spin = next(w for w in widgets(box, tk.Spinbox) if int(w.grid_info()["row"]) == 6)
        blank.update(value=spin.get())
        next(b for b in widgets(box, tk.Button) if b.cget("text") == "Save").invoke()

    root.after(300, in_blank_edit)
    scan._edit_bookmark(at(lat))
    check("11 Edit: no location shows empty", blank.get("value") == "", blank)
    check("11 Edit: Save keeps no location", at(lat).get("location_index") is None, at(lat))

    # 12. the RhinoData copy of the panel, built after Loc is typed, keeps it
    main._loc.set("9")
    window = tk.Toplevel(root)
    main._dock_panel(window)
    root.update()
    check("12 RhinoData panel keeps typed Loc", main._loc.get() == "9", repr(main._loc.get()))
    main._loc.set("")
    window.destroy()
    main._docked = {}
    empty = tk.Toplevel(root)
    main._dock_panel(empty)
    root.update()
    check("12 RhinoData panel keeps an empty Loc empty", main._loc.get() == "",
          repr(main._loc.get()))
    empty.destroy()
    main._docked = {}

    # 13. pressed in RhinoData: the popup opens over RhinoData, not EDMC.
    # winfo_containing stands in for the pointer on the RhinoData Bookmark button.
    window = tk.Toplevel(root)
    main._dock_panel(window)
    root.update()
    lat += STEP
    status(lat)
    root.winfo_containing = lambda x, y: main._docked["card"]
    seen = press(button="Cancel")
    del root.winfo_containing
    check("13 popup over RhinoData", seen.get("master") is window,
          f"master {seen.get('master')}, RhinoData {window}")
    root.winfo_containing = lambda x, y: None
    seen = press(button="Cancel")
    del root.winfo_containing
    check("13 pointer over nothing: popup over EDMC", seen.get("master") is root,
          f"master {seen.get('master')}")
    window.destroy()
    main._docked = {}
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
