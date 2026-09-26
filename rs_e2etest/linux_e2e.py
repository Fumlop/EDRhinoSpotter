"""E2E harness for the Linux chat commands (#12), the arrow position (#11) and
the material pick (#10). Checks and blind spots: linux.md.

Run from the plugin folder:  python rs_e2etest/linux_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads. Puts the arrow
window on screen for ~2 s; registers the four default hotkeys while it runs.
"""

import logging
import os
import sys
import threading
import time
import traceback
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S") + "-linux")
DATA = os.path.join(OUT, "localappdata")
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
os.makedirs(DATA)
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import sqlite3                                           # noqa: E402
import tkinter as tk                                     # noqa: E402

# A copy of the live db, read through sqlite's backup API (WAL-safe): the
# commander's real bookmarks, so the material lists meet real data.
live_before = os.stat(LIVE_DB) if os.path.exists(LIVE_DB) else None
if live_before:
    TEST_DB = os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(TEST_DB))
    with sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True) as src,             sqlite3.connect(TEST_DB) as dst:
        src.backup(dst)


class Config:
    """EDMC's config as far as the plugin reads it."""

    def __init__(self):
        self.values = {}

    def get_str(self, key, default=None):
        return self.values.get(key, default)

    def get_bool(self, key, default=False):
        return bool(self.values.get(key, default))

    def get_int(self, key, default=0):
        return self.values.get(key, default)

    def get_list(self, key, default=None):
        # As EDMC 6.1 config.Config.get_list: a missing key is `default`, or [] for None.
        if key in self.values:
            return list(self.values[key])
        return default if default is not None else []

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key, suppress=False):
        self.values.pop(key, None)


config = Config()
sys.modules["config"] = types.SimpleNamespace(config=config)
sys.modules["myNotebook"] = types.SimpleNamespace(
    Frame=tk.Frame, Label=tk.Label, Checkbutton=tk.Checkbutton, Button=tk.Button,
    OptionMenu=tk.OptionMenu, Entry=tk.Entry)

from rs_core import coverage, database                   # noqa: E402
from rs_ui import hotkey, main, minimap, overlay         # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

lines, fails = [], []
log_lines = []
handler = logging.StreamHandler(type("W", (), {"write": lambda s, m: log_lines.append(m),
                                                "flush": lambda s: None})())
hotkey.logger.addHandler(handler)
hotkey.logger.setLevel(logging.DEBUG)


def out(text):
    print(text)
    lines.append(text)


def check(name, ok, detail=""):
    out(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)


def widgets(w):
    yield w
    for child in w.winfo_children():
        yield from widgets(child)


def texts(frame):
    return [str(w.cget("text")) for w in widgets(frame)
            if isinstance(w, (tk.Label, tk.Button, tk.Checkbutton, tk.Menubutton))]


coverage.clear_old_textures = lambda: None
main.start(PLUGIN)
root = tk.Tk()
root.geometry("+200+200")
main.build(root)
main._cancel_landed()
ui_thread = threading.get_ident()

fired = []


def recorder(name):
    return lambda *a: fired.append((name, threading.get_ident() == ui_thread))


minimap.center_here = recorder("center")
minimap.border_here = recorder("border")
minimap.bigger = recorder("zoom")
real_open_scan = main.open_scan
main.open_scan = recorder("data")


def say(message, event="SendText"):
    fired.clear()
    main.journal_entry("Cmdr", False, "Test", None,
                       {"event": event, "To": "local", "Message": message, "Sent": True}, {})
    root.update()
    return list(fired)


try:
    # ------------------------------------------------------------ #12
    out("#12 chat commands")
    check("2 Windows: hotkeys available", hotkey.available())
    check("2 Windows: '!rs center' fires nothing", say("!rs center") == [])
    check("2 Windows: label is the key", hotkey.label(hotkey.CENTER) == "Ctrl+Alt+Z",
          hotkey.label(hotkey.CENTER))

    real_available = hotkey.available
    hotkey.available = lambda: False
    for typed, want in (("!rs center", "center"), ("!rs border", "border"),
                        ("!rs zoom", "zoom"), ("!rs data", "data"),
                        ("  !RS   Zoom ", "zoom")):
        got = say(typed)
        # (name, ran on the Tk thread): checks 1 and 4.
        check(f"1+4 {typed!r} -> {want} on the Tk thread", got == [(want, True)], repr(got))
    for typed in ("!rs centerx", "!rsc", "!rs", "hello !rs center", "rs center"):
        got = say(typed)
        check(f"3 {typed!r} fires nothing", got == [], repr(got))
    got = say("!rs center", event="ReceiveText")
    check("3 ReceiveText '!rs center' fires nothing", got == [], repr(got))
    check("6 label off Windows", hotkey.label(hotkey.SIZE) == "!rs zoom",
          hotkey.label(hotkey.SIZE))

    log_lines.clear()
    hotkey.stop()
    hotkey.start(hotkey._callbacks)
    info = [m for m in log_lines if "type in chat" in m]
    check("7 start logs the chat commands", bool(info) and "!rs data" in info[0], repr(info))
    check("7 no listener thread", hotkey._thread is None)

    frame = main.prefs(root)
    shown = texts(frame)
    check("5 Settings says Windows only", any("Windows only" in t for t in shown))
    check("5 Settings lists !rs center", "!rs center" in shown)
    check("5 no hotkey OptionMenus", not any("Ctrl+" in t for t in shown),
          [t for t in shown if "Ctrl+" in t])
    before = dict(config.values)
    main.prefs_changed()
    written = {k: v for k, v in config.values.items() if k.startswith("rhinospotter_hotkey")}
    check("5 Settings OK writes no hotkey", not written, repr(written))
    frame.destroy()
    hotkey.available = real_available

    # ------------------------------------------------------------ #10
    out("#10 material pick")
    marked_names = main.cards.materials_marked()
    want_seed = [n for n in main.spotmark.MATERIALS
                 if n in set(main._worth()) or n.lower() in marked_names]
    check("24 start seeded worth + bookmarked", before.get(minimap.MATERIALS_KEY) == want_seed,
          f"{len(before.get(minimap.MATERIALS_KEY) or [])} vs {len(want_seed)}: "
          f"{before.get(minimap.MATERIALS_KEY)}")
    config.set(minimap.MATERIALS_KEY, ["Monazite"])
    check("24 no second seed over a pick",
          minimap.seed_materials(main._worth(), marked_names) is None
          and config.values[minimap.MATERIALS_KEY] == ["Monazite"],
          config.values[minimap.MATERIALS_KEY])
    config.values = {k: v for k, v in before.items() if k not in (minimap.MATERIALS_KEY,
                                                                    minimap.LOW_VALUE_KEY)}
    main._material.set(main.NO_MATERIAL)
    main._filter.set(main.ALL_MATERIALS)
    worth = main._worth()
    marked = sorted(main.cards.materials_marked())
    out(f"    live db copy: {len(marked)} bookmarked materials: {', '.join(marked)}")
    out(f"    worth: {len(worth)} of {len(main.spotmark.MATERIALS)}")

    def panel():
        menu = main._menu["menu"]
        return [str(menu.entrycget(i, "label")) for i in range(menu.index("end") + 1)]

    def rhinodata():
        """The RhinoData window opened the way the panel's button opens it;
        the entries of its MATERIAL FILTER menu."""
        real_open_scan()
        root.update()
        window = main.scan._window
        pickers = [w for w in widgets(window) if isinstance(w, tk.Menubutton)
                   and main.ALL_MATERIALS in [str(w["menu"].entrycget(i, "label"))
                                              for i in range(w["menu"].index("end") + 1)]]
        menu = pickers[0]["menu"]
        labels = [str(menu.entrycget(i, "label")) for i in range(menu.index("end") + 1)]
        window.destroy()
        root.update()
        return labels

    def dialog():
        """Settings opened, Select... pressed: (frame, dialog, {name: checkbox}, {text: button})."""
        frame = main.prefs(root)
        next(w for w in widgets(frame) if isinstance(w, tk.Button)
             and w.cget("text") == "Select...").invoke()
        box = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                   and w.title() == "RhinoSpotter materials")
        boxes = {str(w.cget("text")): w for w in widgets(box) if isinstance(w, tk.Checkbutton)}
        buttons = {str(w.cget("text")): w for w in widgets(box) if isinstance(w, tk.Button)}
        return frame, box, boxes, buttons

    def ticked(boxes):
        return {name for name, w in boxes.items() if root.getvar(w.cget("variable"))}

    main._fill_menu()
    check("15 never picked: panel = the worth list", panel()[1:] == list(worth),
          f"{len(panel()) - 1} entries")
    config.set(minimap.LOW_VALUE_KEY, True)
    main._fill_menu()
    check("16 old switch on: all 38", len(panel()) - 1 == 38, len(panel()) - 1)
    config.values.pop(minimap.LOW_VALUE_KEY)
    main._fill_menu()

    def bookmark_rows():
        with database.connect() as conn:
            return conn.execute("SELECT id, commodity, data FROM bookmarks ORDER BY id").fetchall()

    rows_before = bookmark_rows()

    # The commander's run: None, tick Monazite, OK, Settings OK.
    frame, box, boxes, buttons = dialog()
    check("17 dialog: 38 boxes", len(boxes) == 38, len(boxes))
    check("17 dialog opens with the list's ticks", ticked(boxes) == set(worth),
          sorted(ticked(boxes) ^ set(worth)))
    buttons["None"].invoke()
    check("17 None unticks all", ticked(boxes) == set(), sorted(ticked(boxes)))
    boxes["Monazite"].invoke()
    buttons["OK"].invoke()
    check("18 dialog OK stores nothing yet", minimap.MATERIALS_KEY not in config.values)
    main.prefs_changed()
    frame.destroy()
    check("19 Settings OK stores ['Monazite']",
          config.values.get(minimap.MATERIALS_KEY) == ["Monazite"],
          config.values.get(minimap.MATERIALS_KEY))
    check("19+20 panel: Monazite only, bookmarked ones gone",
          panel() == [main.NO_MATERIAL, "Monazite"], panel())
    got = rhinodata()
    check("19+20 RhinoData filter: Monazite only",
          got == [main.ALL_MATERIALS, "Monazite"], got)
    rows_after = bookmark_rows()
    check("20 bookmarks kept: every row unchanged", rows_after == rows_before,
          f"{len(rows_before)} -> {len(rows_after)} rows")

    frame, box, boxes, buttons = dialog()
    check("17 reopened dialog: Monazite only ticked", ticked(boxes) == {"Monazite"},
          sorted(ticked(boxes)))
    box.destroy()
    check("21 dialog closed with X: no pick", minimap._picked is None, minimap._picked)
    main.prefs_changed()
    frame.destroy()
    check("21 stored pick unchanged",
          config.values.get(minimap.MATERIALS_KEY) == ["Monazite"])

    main._material.set("Gold")
    main._fill_menu()
    check("20 the material in the box stays", panel() == [main.NO_MATERIAL, "Gold", "Monazite"],
          panel())
    main._material.set(main.NO_MATERIAL)
    main._fill_menu()

    frame, box, boxes, buttons = dialog()
    buttons["None"].invoke()
    buttons["OK"].invoke()
    main.prefs_changed()
    frame.destroy()
    check("22 none ticked: key removed", minimap.MATERIALS_KEY not in config.values,
          config.values.get(minimap.MATERIALS_KEY))
    check("22 none ticked: panel = the worth list", panel()[1:] == list(worth), panel())

    # Safety net: a list that comes out empty says where to pick materials.
    real_shown = minimap.materials_shown
    minimap.materials_shown = lambda worth: ()
    main._fill_menu()
    menu = main._menu["menu"]
    last = menu.index("end")
    check("23 panel: empty list shows the Settings hint",
          menu.entrycget(last, "label") == main.scan.NO_MATERIALS
          and menu.entrycget(last, "state") == "disabled",
          menu.entrycget(last, "label"))
    variable = tk.StringVar(value=main.ALL_MATERIALS)
    holder = tk.Frame(root)
    main.scan._picker(holder, variable, (main.ALL_MATERIALS,) + main._materials(), None)
    picker = next(w for w in widgets(holder) if isinstance(w, tk.Menubutton))
    pmenu = picker["menu"]
    check("23 RhinoData: empty list shows the Settings hint",
          pmenu.entrycget(pmenu.index("end"), "label") == main.scan.NO_MATERIALS)
    holder.destroy()
    minimap.materials_shown = real_shown
    main._fill_menu()
    menu = main._menu["menu"]
    check("23 hint gone once materials are back",
          menu.entrycget(menu.index("end"), "label") != main.scan.NO_MATERIALS)

    # ------------------------------------------------------------ #11
    out("#11 arrow position")
    real = (overlay.win32, overlay._game_rect, overlay.game_focused)
    overlay.win32 = lambda: False
    overlay._game_rect = lambda: None
    overlay.game_focused = lambda: True
    record = {"planet_name": "Test 1", "location_index": 1, "marked_at": "x",
              "latitude": 1.0, "longitude": 1.0, "commodity": "Platinum"}
    window = overlay.start(root, record)
    root.update()
    sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
    out(f"    screen {sw}x{sh}")
    check("8 default: top middle of the screen",
          (window.winfo_x(), window.winfo_y()) == ((sw - overlay.WIDTH) // 2, 40),
          (window.winfo_x(), window.winfo_y()))
    canvas = overlay._canvas
    check("14 drag bound off Windows", "<B1-Motion>" in canvas.bind(), canvas.bind())

    config.set(overlay.POS_KEY, "100,200")
    overlay._placed = None
    overlay._place()
    root.update()
    check("9 stored position used", (window.winfo_x(), window.winfo_y()) == (100, 200),
          (window.winfo_x(), window.winfo_y()))

    canvas.event_generate("<ButtonPress-1>", x=10, y=10, rootx=110, rooty=210)
    canvas.event_generate("<B1-Motion>", x=160, y=70, rootx=260, rooty=270)
    root.update()
    mid = (window.winfo_x(), window.winfo_y())
    overlay._placed = None
    overlay._tick()
    root.update()
    check("10 drag moves it", mid == (250, 260), mid)
    check("10 tick leaves it mid-drag", (window.winfo_x(), window.winfo_y()) == (250, 260),
          (window.winfo_x(), window.winfo_y()))
    canvas.event_generate("<ButtonRelease-1>", x=160, y=70, rootx=260, rooty=270)
    root.update()
    check("11 drop stored", config.values.get(overlay.POS_KEY) == "250,260",
          config.values.get(overlay.POS_KEY))
    overlay._tick()
    root.update()
    check("11 stays after the next tick", (window.winfo_x(), window.winfo_y()) == (250, 260),
          (window.winfo_x(), window.winfo_y()))

    config.set(overlay.POS_KEY, "99999,99999")
    overlay._placed = None
    overlay._place()
    root.update()
    check("12 off-screen clamped",
          (window.winfo_x(), window.winfo_y()) == (sw - overlay.WIDTH, sh - overlay.HEIGHT),
          (window.winfo_x(), window.winfo_y()))

    canvas.event_generate("<ButtonPress-3>", x=5, y=5)
    root.update()
    check("13 right click forgets", config.values.get(overlay.POS_KEY) == "",
          config.values.get(overlay.POS_KEY))
    check("13 back to top middle",
          (window.winfo_x(), window.winfo_y()) == ((sw - overlay.WIDTH) // 2, 40),
          (window.winfo_x(), window.winfo_y()))
    overlay.stop()

    overlay.win32 = real[0]
    overlay._game_rect = lambda: (0, 0, 1920, 1080)
    config.set(overlay.POS_KEY, "100,200")
    window = overlay.start(root, record)
    root.update()
    check("14 Windows: top middle of the game, stored position ignored",
          (window.winfo_x(), window.winfo_y()) == ((1920 - overlay.WIDTH) // 2, 43),
          (window.winfo_x(), window.winfo_y()))
    check("14 Windows: no drag bound", not overlay._canvas.bind(), overlay._canvas.bind())
    overlay.stop()
    overlay._game_rect, overlay.game_focused = real[1], real[2]
except Exception:
    out(traceback.format_exc())
    fails.append("exception")
finally:
    hotkey.stop()
    root.destroy()

if live_before:
    after = os.stat(LIVE_DB)
    check("live db untouched (size, mtime)",
          (after.st_size, after.st_mtime) == (live_before.st_size, live_before.st_mtime))

out(f"\n{len(fails)} failed" + (": " + ", ".join(fails) if fails else ""))
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"report: {os.path.join(OUT, 'report.txt')}")
sys.exit(1 if fails else 0)
