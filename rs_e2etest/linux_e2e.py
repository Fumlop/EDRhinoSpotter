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
os.makedirs(DATA)
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import tkinter as tk                                     # noqa: E402


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
        return list(self.values[key]) if key in self.values else default

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
    config.values = {k: v for k, v in before.items() if k not in (minimap.MATERIALS_KEY,
                                                                    minimap.LOW_VALUE_KEY)}
    main._offered = None
    worth = main._worth()
    check("15 never picked: worth list", main._materials() == worth,
          f"{len(main._materials())} vs {len(worth)}")
    out(f"    worth: {len(worth)} of {len(main.spotmark.MATERIALS)}")
    config.set(minimap.LOW_VALUE_KEY, True)
    check("16 old switch on: all 38", len(main._materials()) == len(main.spotmark.MATERIALS),
          len(main._materials()))
    config.values.pop(minimap.LOW_VALUE_KEY)

    frame = main.prefs(root)
    button = next(w for w in widgets(frame) if isinstance(w, tk.Button)
                  and w.cget("text") == "Select...")
    button.invoke()
    box = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
               and w.title() == "RhinoSpotter materials")
    boxes = [w for w in widgets(box) if isinstance(w, tk.Checkbutton)]
    ticked = {str(w.cget("text")) for w in boxes if root.getvar(w.cget("variable"))}
    check("17 dialog: 38 boxes", len(boxes) == 38, len(boxes))
    check("17 dialog ticks = list", ticked == set(worth), sorted(ticked ^ set(worth)))
    buttons = {str(w.cget("text")): w for w in widgets(box) if isinstance(w, tk.Button)}
    buttons["None"].invoke()
    deut = next(w for w in boxes if w.cget("text") == "Deuterium")
    deut.invoke()
    buttons["OK"].invoke()
    check("18 dialog OK stores nothing yet", minimap.MATERIALS_KEY not in config.values)
    check("18 dialog OK keeps the pick", minimap._picked == ["Deuterium"], minimap._picked)
    main.prefs_changed()
    check("19 Settings OK stores the pick",
          config.values.get(minimap.MATERIALS_KEY) == ["Deuterium"],
          config.values.get(minimap.MATERIALS_KEY))
    menu = main._menu["menu"]
    labels = [str(menu.entrycget(i, "label")) for i in range(menu.index("end") + 1)]
    check("19 dropdown refilled", labels == [main.NO_MATERIAL, "Deuterium"], labels)
    frame.destroy()

    main._material.set("Gold")
    check("20 held material stays", "Gold" in main._materials(), main._materials())
    main._material.set(main.NO_MATERIAL)
    with database.connect() as conn:
        database.write_bookmark(conn, {"planet_name": "Test 1", "commodity": "Platinum",
                                       "system": "Test"})
    database.changed()
    check("20 bookmarked material stays", "Platinum" in main._materials(), main._materials())

    frame = main.prefs(root)
    next(w for w in widgets(frame) if isinstance(w, tk.Button)
         and w.cget("text") == "Select...").invoke()
    box = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
               and w.title() == "RhinoSpotter materials")
    box.destroy()
    check("21 dialog closed with X: no pick", minimap._picked is None, minimap._picked)
    main.prefs_changed()
    check("21 stored pick unchanged",
          config.values.get(minimap.MATERIALS_KEY) == ["Deuterium"])
    frame.destroy()

    config.set(minimap.MATERIALS_KEY, [])
    got = main._materials()
    check("22 empty pick: only the bookmarked one", got == ("Platinum",), got)

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

out(f"\n{len(fails)} failed" + (": " + ", ".join(fails) if fails else ""))
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"report: {os.path.join(OUT, 'report.txt')}")
sys.exit(1 if fails else 0)
