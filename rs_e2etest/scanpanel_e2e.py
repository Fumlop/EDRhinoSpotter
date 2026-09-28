"""E2E harness: the panel above the RhinoData bookmark list. Checks and blind spots: scanpanel.md.

Run from the plugin folder:  python rs_e2etest/scanpanel_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import json
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

from rs_core import cards, coverage, database, palette, paths   # noqa: E402
from rs_ui import main, minimap, scan                    # noqa: E402

assert database.PATH.startswith(OUT), database.PATH

SYSTEM, BODY = "E2E Scanpanel", "E2E Scanpanel 1 a"
RADIUS = 1_500_000.0
ON_GROUND = 0x200000 | 0x10          # the Flags amount_e2e bookmarks with

results = []
tree = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


class Config:
    """EDMC's config as far as minimap reads and writes it."""
    def __init__(self, **values):
        self.values = values

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    get_str = get_int = get_bool

    def get_list(self, key, default=None):
        return self.values.get(key, default if default is not None else [])

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key, suppress=False):
        self.values.pop(key, None)


class Notebook:
    Frame, Label, Button, Checkbutton = tk.Frame, tk.Label, tk.Button, tk.Checkbutton

    @staticmethod
    def OptionMenu(master, variable, default, *values):
        return tk.OptionMenu(master, variable, default, *values)


def status(flags):
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": flags, "BodyName": BODY, "Latitude": 10.0, "Longitude": 20.0,
                   "Altitude": 0, "PlanetRadius": RADIUS, "Heading": 0}, handle)


def rows():
    return [r for r in cards.for_system(SYSTEM) if r.get("planet_name") == BODY]


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.05)


def pump_until(until, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        if until():
            return True
        time.sleep(0.05)
    return False


def copy():
    return main._docked


def alive(widget):
    return widget is not None and bool(widget.winfo_exists())


def open_now():
    main.open_scan()
    scan._window.geometry("+-4000+-4000")
    pump(0.3)


def find(frame, kind, **match):
    """The first descendant of `frame` of `kind` whose options equal `match`."""
    stack = [frame]
    while stack:
        widget = stack.pop(0)
        if isinstance(widget, kind) and all(str(widget.cget(k)) == str(v) for k, v in match.items()):
            return widget
        stack.extend(widget.winfo_children())
    return None


def describe(widget, depth=0):
    text = ""
    if "text" in widget.keys():
        text = repr(str(widget.cget("text")))
    tree.append(f"{'  ' * depth}{widget.winfo_class()} {text}".rstrip())
    for child in widget.winfo_children():
        describe(child, depth + 1)


def menu_labels(menu):
    inner = menu["menu"]
    return [inner.entrycget(i, "label") for i in range(inner.index("end") + 1)]


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
config = Config()
minimap.config = config
minimap.nb = Notebook
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
main._register.adopt(SYSTEM, [{"name": BODY, "ground": "rock 80%+ [silicate vapour geysers]",
                               "distance": 1284.0, "locations": 22, "volcanism": "",
                               "planet_class": "Rocky body"}])
root = tk.Tk()
root.withdraw()

try:
    main.build(root)
    status(0)
    root.update()

    # 1. default on; off builds nothing
    check("1 setting unset: panel_in_scan() on", minimap.panel_in_scan() is True, "")
    config.set(minimap.PANEL_KEY, False)
    open_now()
    check("1 setting off: no copy", not copy() and scan._dock is None, f"{copy()} {scan._dock}")

    # 2. setting on
    config.set(minimap.PANEL_KEY, True)
    open_now()
    dock = copy().get("frame")
    check("2 copy is a child of the RhinoData window", alive(dock) and dock.winfo_toplevel() is scan._window,
          f"{dock}")
    check("2 copy mapped", alive(dock) and dock.winfo_ismapped(), "")
    master = root.nametowidget(dock.pack_info()["in"]) if alive(dock) and dock.winfo_manager() else None
    slaves = master.pack_slaves() if master else []
    check("2 copy packed above the list", dock in slaves and slaves.index(dock) < len(slaves) - 1,
          f"index {slaves.index(dock) if dock in slaves else None} of {len(slaves)}")
    check("2 scan._dock is the copy", scan._dock is dock, f"{scan._dock}")
    check("2 copy has no RhinoData button; EDMC's panel has one",
          find(dock, tk.Button, text="RhinoData") is None
          and find(main._frame, tk.Button, text="RhinoData") is not None, "")
    version = f"RhinoSpotter {main.update.RUNNING}"
    check("2 copy has no version label or landable count; EDMC's panel has both",
          find(dock, tk.Label, text=version) is None and copy().get("count") is None
          and find(main._frame, tk.Label, text=version) is not None and main._scan_count is not None, "")
    check("2 copy at its natural width, narrower than its pane",
          dock.winfo_width() == dock.winfo_reqwidth() < master.winfo_width(),
          f"{dock.winfo_width()} / req {dock.winfo_reqwidth()} / pane {master.winfo_width()} px")

    # 3. shared variables
    entry = find(dock, tk.Spinbox, textvariable=str(main._loc))
    entry.delete(0, "end")
    entry.insert(0, "7")
    spin = find(dock, tk.Spinbox, textvariable=str(main._rigs))
    spin.delete(0, "end")
    spin.insert(0, "4")
    main._amount.set("Low")
    amount_copy = find(dock, tk.Menubutton, textvariable=str(main._amount))
    density_copy = find(dock, tk.Menubutton, textvariable=str(main._density))
    density_copy["menu"].invoke(menu_labels(density_copy).index("High"))
    check("3 Location typed in the copy reaches main._loc", main._loc.get() == "7", repr(main._loc.get()))
    check("3 Rigs typed in the copy reaches main._rigs", main._rigs.get() == "4", repr(main._rigs.get()))
    check("3 EDMC-side Amount shows in the copy", amount_copy is not None
          and str(amount_copy.cget("text")) == "Low", amount_copy and amount_copy.cget("text"))
    check("3 Density picked in the copy reaches main._density", main._density.get() == "High",
          repr(main._density.get()))

    # 4. Bookmark state follows the ground
    card = copy()["card"]
    check("4 off the ground: copy's Bookmark disabled",
          pump_until(lambda: str(card.cget("state")) == "disabled", 2.5), str(card.cget("state")))
    status(ON_GROUND)
    check("4 on the ground: copy's Bookmark normal",
          pump_until(lambda: str(card.cget("state")) == "normal", 2.5), str(card.cget("state")))
    check("4 EDMC's Bookmark normal too", str(main._card_button.cget("state")) == "normal",
          str(main._card_button.cget("state")))

    # 5. pick and press in the copy
    menu = copy()["menu"]
    labels = menu_labels(menu)
    material = main._materials()[0]
    menu["menu"].invoke(labels.index(material))
    check("5 Material picked in the copy reaches main._material", main._material.get() == material,
          main._material.get())
    card.invoke()
    check("5 copy's Bookmark saved one bookmark", pump_until(lambda: len(rows()) == 1), f"{len(rows())} rows")
    row = rows()[0] if rows() else {}
    saved = tuple(row.get(k) for k in ("location_index", "rigs", "amount", "density", "commodity"))
    check("5 it has location 7, rigs 4, amount Low, density High, the material",
          saved == (7, 4, "Low", "High", material), repr(saved))
    # The worker's _on_ui bounce needs a running mainloop; this harness pumps
    # update(), so the bounce is dropped and _report is called here instead.
    main._report(None, main._card_token)
    check("5 copy's button says completed like EDMC's",
          str(card.cget("text")) == str(main._card_button.cget("text")) == main.DONE_TEXT,
          f"{card.cget('text')} / {main._card_button.cget('text')}")

    # 6. texts
    main._set_status("E2E status line")
    main._refresh_scan_count()
    check("6 status line mirrored", copy()["status"].cget("text") == main._status.cget("text") == "E2E status line",
          copy()["status"].cget("text"))
    check("6 landable count still set on EDMC's panel", main._scan_count.cget("text") != "",
          repr(main._scan_count.cget("text")))
    check("6 hint mirrored", copy()["hint"].cget("text") == main._hint.cget("text"),
          f"{copy()['hint'].cget('text')!r} / {main._hint.cget('text')!r}")

    describe(dock)

    # 8. redraws keep the one copy
    before = copy()["frame"]
    for _ in range(10):
        main.open_scan()
    pump(0.3)
    check("8 ten redraws: the same copy", copy()["frame"] is before and alive(before), "")
    stray = [w for w in scan._window.winfo_children() if isinstance(w, tk.Frame)
             and find(w, tk.Spinbox) is not None and w is not before]
    check("8 no second copy in the window", not stray, f"{len(stray)} extra")

    # 10. Mapped tab
    scan._state["view"] = "mapped"
    scan._draw()
    pump(0.2)
    check("10 Mapped tab: copy not mapped", not before.winfo_ismapped(), "")
    scan._state["view"] = "bookmarks"
    scan._draw()
    pump(0.2)
    check("10 back on Bookmarks: copy mapped", before.winfo_ismapped(), "")

    # 11. materials refill
    main._fill_menu()
    check("11 copy's Material menu = EDMC's", menu_labels(copy()["menu"]) == menu_labels(main._menu),
          f"{len(menu_labels(copy()['menu']))} / {len(menu_labels(main._menu))}")

    # 7. update state (after 5: the done text would otherwise take the button back)
    main._show_update("v99.0.0", True)
    card = copy()["card"]
    check("7 copy reads Update in WARN", (str(card.cget("text")), str(card.cget("fg")))
          == ("Update", palette.WARN), f"{card.cget('text')} {card.cget('fg')}")

    # 9. close and reopen
    old = copy()["frame"]
    scan._window.destroy()
    pump(0.2)
    open_now()
    new = copy().get("frame")
    check("9 reopened: a new copy in the new window", alive(new) and new is not old
          and new.winfo_toplevel() is scan._window and new.winfo_ismapped(), f"{new}")
    check("9 reopened copy starts as Update, like EDMC's",
          str(copy()["card"].cget("text")) == str(main._card_button.cget("text")) == "Update",
          f"{copy()['card'].cget('text')} / {main._card_button.cget('text')}")

    # 12. setting off with the window open
    config.set(minimap.PANEL_KEY, False)
    open_now()
    check("12 setting off: copy destroyed", not alive(new) and not copy() and scan._dock is None,
          f"{copy()} {scan._dock}")

    # 13. settings row
    tab = main.prefs(root)
    check("13 plugin: the setting row is on the tab", minimap._in_scan is not None
          and find(tab, tk.Checkbutton, variable=str(minimap._in_scan)) is not None, "")
    tab.destroy()
    config.set(minimap.PANEL_KEY, True)
    hosted_dock = tk.Frame(root)
    scan.host(root, hosted_dock)
    tab = main.prefs(root)
    check("13 standalone (scan.host): no setting row", minimap._in_scan is None, "")
    tab.destroy()
    scan._window = root
    scan._fetch_dock()
    check("13 standalone with the setting on: its own dock kept, no copy built",
          scan._dock is hosted_dock and not copy(), f"{scan._dock} {copy()}")
    scan._host = scan._dock = None
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    main.stop()
    root.destroy()

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
lines.append("\nThe copy, as built (check 6):")
lines.extend(tree)
report = "\n".join(lines)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(OUT)
sys.exit(1 if failed else 0)
