"""E2E harness for the gear beside RhinoData's MATERIAL FILTER. Checks and
blind spots: gear.md.

Run from the plugin folder:  python rs_e2etest/gear_e2e.py
Writes rs_e2etest/out/<timestamp>-gear/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads.
"""

import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S") + "-gear")
DATA = os.path.join(OUT, "localappdata")
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
os.makedirs(DATA)
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import sqlite3                                           # noqa: E402
import tkinter as tk                                     # noqa: E402

if os.path.exists(LIVE_DB):
    TEST_DB = os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(TEST_DB))
    with sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True) as src, \
            sqlite3.connect(TEST_DB) as dst:
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

from rs_core import coverage, database, spotmark        # noqa: E402
from rs_ui import main, minimap, scan                    # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

lines, fails = [], []
KEY = minimap.MATERIALS_KEY
GEAR = "⚙"


def check(name, ok, detail=""):
    line = f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else "")
    lines.append(line)
    print(line.encode("ascii", "replace").decode())
    if not ok:
        fails.append(name)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def pump(root, ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def entries(option_menu):
    menu = option_menu["menu"]
    last = menu.index("end")
    return [str(menu.entrycget(i, "label")) for i in range(0 if last is None else last + 1)
            if menu.type(i) == "command" and menu.entrycget(i, "state") != "disabled"]


def gear_and_picker():
    """The gear button and the filter OptionMenu in the RhinoData window."""
    gear = next((w for w in walk(scan._window)
                 if isinstance(w, tk.Button) and w.cget("text") == GEAR), None)
    if gear is None:
        return None, None
    box = gear.master.master
    picker = next((w for w in box.winfo_children() if isinstance(w, tk.OptionMenu)), None)
    return gear, picker


def dialog():
    return next((w for w in walk(scan._window) if isinstance(w, tk.Toplevel)
                 and w.title() == "RhinoSpotter materials"), None)


def press_ok(box, ticked):
    """Set the dialog's checkboxes to `ticked` and press OK."""
    for w in walk(box):
        if isinstance(w, tk.Checkbutton):
            if (w.cget("text") in ticked) != bool(int(w.getvar(w.cget("variable")))):
                w.invoke()
    ok = next(w for w in walk(box) if isinstance(w, tk.Button) and w.cget("text") == "OK")
    ok.invoke()


def run():
    coverage.clear_old_textures = lambda: None
    main.start(PLUGIN)
    root = tk.Tk()
    root.geometry("+200+200")
    main.build(root)
    main._cancel_landed()
    main.open_scan()
    pump(root, 300)

    print("gear")
    gear, picker = gear_and_picker()
    check("gear on the MATERIAL FILTER row", gear is not None and picker is not None)
    if gear is None:
        return
    check("gear enabled", gear.cget("state") == "normal", gear.cget("state"))
    g_right = gear.winfo_rootx() + gear.winfo_width()
    p_right = picker.winfo_rootx() + picker.winfo_width()
    check("gear right edge flush with filter box", g_right == p_right, f"{g_right} vs {p_right} px")
    check("gear above the filter box",
          gear.winfo_rooty() + gear.winfo_height() <= picker.winfo_rooty(),
          f"gear bottom {gear.winfo_rooty() + gear.winfo_height()}, box top {picker.winfo_rooty()}")
    label = next(w for w in gear.master.winfo_children() if isinstance(w, tk.Label))
    l_mid = label.winfo_rooty() + label.winfo_height() // 2
    check("label beside the gear: label middle inside the gear's height",
          label.cget("text") == "MATERIAL FILTER"
          and gear.winfo_rooty() <= l_mid <= gear.winfo_rooty() + gear.winfo_height(),
          f"label middle {l_mid}, gear {gear.winfo_rooty()}-{gear.winfo_rooty() + gear.winfo_height()}")

    print("tooltip")
    tips = lambda: [w for w in gear.winfo_children() if isinstance(w, tk.Toplevel)]
    gear.event_generate("<Enter>")
    pump(root, 300)
    check("no tooltip at 300 ms", not tips())
    pump(root, 400)
    shown = tips()
    text = shown[0].winfo_children()[0].cget("text") if shown else None
    check("tooltip at 700 ms", text == "Setting available materials", repr(text))
    gear.event_generate("<Leave>")
    pump(root, 100)
    check("tooltip gone on Leave", not tips())
    gear.event_generate("<Enter>")
    pump(root, 700)
    shown_before = bool(tips())
    gear.event_generate("<ButtonPress>", button=1)
    pump(root, 100)
    check("tooltip gone on a click", shown_before and not tips(), f"shown before: {shown_before}")
    gear.event_generate("<Leave>")

    print("dialog from the gear, OK with three ticked")
    before = set(minimap.materials_shown(main._worth()))
    gear.invoke()
    pump(root, 200)
    box = dialog()
    check("dialog opens, child of RhinoData", box is not None)
    if box is None:
        return
    ticks = {w.cget("text") for w in walk(box) if isinstance(w, tk.Checkbutton)
             and int(w.getvar(w.cget("variable")))}
    check("dialog ticks = materials offered now", ticks == before,
          f"{len(ticks)} ticked, {len(before)} offered")
    want = ["Bromellite", "Osmium", "Platinum"]
    main._filter.set(main.ALL_MATERIALS)
    main._material.set(main.NO_MATERIAL)
    press_ok(box, want)
    pump(root, 400)
    check("key written with the ticked names", config.values.get(KEY) == want,
          repr(config.values.get(KEY)))
    panel = [n for n in entries(main._menu) if n != main.NO_MATERIAL]
    check("panel dropdown offers the ticked names", panel == want, repr(panel))
    gear, picker = gear_and_picker()
    check("gear still there after redraw", gear is not None and gear.cget("state") == "normal")
    rail = [n for n in entries(picker) if n != main.ALL_MATERIALS] if picker else None
    check("RhinoData picker offers the ticked names", rail == want, repr(rail))

    print("dialog from the gear, OK with none ticked")
    gear.invoke()
    pump(root, 200)
    press_ok(dialog(), ())
    pump(root, 400)
    check("key deleted", KEY not in config.values, repr(config.values.get(KEY)))
    default = [n for n in spotmark.MATERIALS if n in set(main._worth())]
    panel = [n for n in entries(main._menu) if n != main.NO_MATERIAL]
    check("panel dropdown back to the over-50,000 Cr/t default", panel == default,
          f"{len(panel)} vs {len(default)}")

    print("settings tab path")
    config.values[KEY] = list(want)
    tab = minimap.prefs(root, worth=main._worth())
    select = next((w for w in walk(tab) if isinstance(w, tk.Button)
                   and w.cget("text") == "Select..."), None)
    check("Settings tab has Select...", select is not None)
    if select is None:
        return
    select.invoke()
    pump(root, 200)
    box = next((w for w in walk(root) if isinstance(w, tk.Toplevel)
                and w.title() == "RhinoSpotter materials"), None)
    check("Select... opens the dialog", box is not None)
    if box is None:
        return
    press_ok(box, ["Osmium"])
    check("without on_ok: ticks kept in _picked", minimap._picked == ["Osmium"],
          repr(minimap._picked))
    check("without on_ok: key untouched until Settings OK", config.values.get(KEY) == want,
          repr(config.values.get(KEY)))
    minimap.prefs_changed()
    check("Settings OK writes _picked", config.values.get(KEY) == ["Osmium"],
          repr(config.values.get(KEY)))
    tab.destroy()

    print("no EDMC config")
    saved = minimap.config
    minimap.config = None
    try:
        main.open_scan()
        pump(root, 300)
        gear, picker = gear_and_picker()
        filter_label = any(isinstance(w, tk.Label) and w.cget("text") == "MATERIAL FILTER"
                           for w in walk(scan._window))
        check("no gear without config, filter still drawn", gear is None and filter_label)
    finally:
        minimap.config = saved
    root.destroy()


try:
    run()
except Exception:
    import traceback
    lines.append(traceback.format_exc())
    print(lines[-1])
    fails.append("exception")

lines.append(f"\nfails {len(fails)}\nresult: {'PASS' if not fails else 'FAIL'}")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(lines) + "\n")
print(lines[-1])
print(OUT)
raise SystemExit(1 if fails else 0)
