"""E2E harness for minimap placing and topmost. Checks: minimap-place-topmost.md.

Run from the plugin folder:  python rs_e2etest/minimap_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and screenshots. Exit code 1 on a failure.
Live data is never opened: LOCALAPPDATA points at the run folder before rs_core loads.
"""

import logging
import os
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter")
LIVE_DB = os.path.join(LIVE, "db", "rhinospotter.db")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")

os.makedirs(os.path.join(DATA, "RhinoSpotter", "db"))
shutil.copy2(LIVE_DB, os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db"))
live_before = os.stat(LIVE_DB)
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import ctypes                                            # noqa: E402
import tkinter as tk                                     # noqa: E402
from ctypes import wintypes                              # noqa: E402

from rs_core import coverstore, database                 # noqa: E402
from rs_ui import hotkey, minimap, overlay               # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

log_lines = []
handler = logging.StreamHandler(type("W", (), {"write": lambda s, m: log_lines.append(m),
                                                "flush": lambda s: None})())
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
minimap.logger.addHandler(handler)
minimap.logger.setLevel(logging.DEBUG)

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.FindWindowW.restype = wintypes.HWND
NOTOPMOST, NOACT_NOMOVE = wintypes.HWND(-2), 0x10 | 0x1 | 0x2


class Config:
    """EDMC's config as far as minimap reads and writes it."""

    def __init__(self, **values):
        self.values = values

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    get_str = get_int = get_bool

    def set(self, key, value):
        self.values[key] = value


class Notebook:
    Frame, Label, Button, Checkbutton = tk.Frame, tk.Label, tk.Button, tk.Checkbutton

    @staticmethod
    def OptionMenu(master, variable, default, *values):
        return tk.OptionMenu(master, variable, default, *values)


results = []
errors = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def rect(handle):
    r = wintypes.RECT()
    u.GetWindowRect(handle, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def exstyle(handle):
    return u.GetWindowLongW(handle, -20) & 0xFFFFFFFF


def topmost(handle):
    return bool(exstyle(handle) & 0x8)


def grab(box):
    """The screen inside `box`, layered windows included: BitBlt with
    SRCCOPY | CAPTUREBLT. Without CAPTUREBLT a WS_EX_LAYERED window is left out."""
    from PIL import Image
    g = ctypes.WinDLL("gdi32")
    g.CreateCompatibleDC.restype = g.CreateCompatibleBitmap.restype = wintypes.HANDLE
    g.CreateCompatibleDC.argtypes = [wintypes.HANDLE]
    g.CreateCompatibleBitmap.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
    g.SelectObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    g.BitBlt.argtypes = [wintypes.HANDLE] + [ctypes.c_int] * 4 + [wintypes.HANDLE] + [ctypes.c_int] * 2 + [wintypes.DWORD]
    g.GetDIBits.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    g.DeleteObject.argtypes = g.DeleteDC.argtypes = [wintypes.HANDLE]
    u.GetDC.restype = wintypes.HANDLE
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HANDLE]
    g.GetDeviceCaps.argtypes = [wintypes.HANDLE, ctypes.c_int]
    screen = u.GetDC(None)
    # This process is DPI-unaware, as tkinter leaves it: GetWindowRect answers
    # in scaled pixels, the screen DC in physical ones. DESKTOPHORZRES (118)
    # over SM_CXSCREEN (0) is the factor, 1.25 at 125 %.
    scale = g.GetDeviceCaps(screen, 118) / u.GetSystemMetrics(0)
    left, top, right, bottom = (round(v * scale) for v in box)
    w, h = right - left, bottom - top
    mem = g.CreateCompatibleDC(screen)
    bmp = g.CreateCompatibleBitmap(screen, w, h)
    g.SelectObject(mem, bmp)
    g.BitBlt(mem, 0, 0, w, h, screen, left, top, 0x00CC0020 | 0x40000000)
    header = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    pixels = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mem, bmp, 0, h, pixels, header, 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(None, screen)
    return Image.frombuffer("RGB", (w, h), pixels, "raw", "BGRX", 0, 1)


def shot(name):
    try:
        grab(rect(minimap._handle)).save(os.path.join(OUT, name + ".png"))
    except Exception as err:
        log_lines.append(f"screenshot {name} failed: {traceback.format_exc()}")


def pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


STATUS = {"Flags": 0x4000000 | 0x200000, "BodyName": "E2E Test 1 a", "Latitude": 10.0,
          "Longitude": 20.0, "PlanetRadius": 1_500_000, "Heading": 90}


def tick(status=STATUS):
    minimap.update(root, status)
    root.update()


def at(body, lat=10.0, lon=20.0):
    return dict(STATUS, BodyName=body, Latitude=lat, Longitude=lon)


def corner_xy(got):
    """Top right of the Elite window for a map of `got`'s size, as _place computes it."""
    game = overlay._game_rect()
    inset = max(16, int((game[3] - game[1]) * 0.03))
    return game[2] - inset - (got[2] - got[0]), game[1] + inset


def placed_log():
    return sum("minimap: placed" in line for line in log_lines)


def settings_dialog():
    dialog = tk.Toplevel(root)
    dialog.title("E2E Settings")
    frame = minimap.prefs(dialog)
    frame.pack()
    dialog.wait_visibility()
    dialog.grab_set()                  # as EDMC prefs.py
    pump()
    button = next(w for w in frame.winfo_children()
                  if isinstance(w, tk.Button) and w.cget("text") == "Place the map")
    return dialog, button


def drag(dx, dy):
    c = minimap._canvas
    x0, y0 = minimap._window.winfo_rootx() + 20, minimap._window.winfo_rooty() + 20
    c.event_generate("<Button-1>", x=20, y=20, rootx=x0, rooty=y0)
    for step in range(1, 6):
        c.event_generate("<B1-Motion>", x=20, y=20, rootx=x0 + dx * step // 5, rooty=y0 + dy * step // 5)
        pump(0.05)
    c.event_generate("<ButtonRelease-1>", x=20, y=20, rootx=x0 + dx, rooty=y0 + dy)
    pump()


root = tk.Tk()
root.withdraw()
root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
minimap.nb = Notebook
minimap.config = hotkey.config = Config(**{minimap.KEEP_KEY: True, minimap.CORNER_KEY: "top right"})
elite = u.FindWindowW(None, overlay.GAME_TITLE)
stand_in = None
if not elite:
    # No game running: a plain window with the game's title, which is all
    # overlay._game_rect() and FindWindowW look at. Not topmost, like windowed Elite.
    stand_in = tk.Toplevel(root)
    stand_in.title(overlay.GAME_TITLE)
    stand_in.geometry("1200x700+300+150")
    stand_in.configure(bg="#203040")
    pump(0.5)
    elite = u.FindWindowW(None, overlay.GAME_TITLE)
game_at_start = overlay._game_rect()

try:
    # 0. Before any window: the hotkey path, place() with no root.
    check("0 place() without a window returns False", minimap.place() is False)
    check("0 place() without a window says so on the hint line",
          "no map window" in (minimap._hint() or ""), repr(minimap._hint()))

    # 1. Place from Settings, not in the SRV.
    dialog, button = settings_dialog()
    frame = button.master
    taken, clash = set(), []
    for widget in frame.winfo_children():
        info = widget.grid_info()
        if not info:
            continue
        row, column = int(info["row"]), int(info["column"])
        for k in range(int(info.get("columnspan", 1))):
            if (row, column + k) in taken:
                clash.append(f"{widget} on {(row, column + k)}")
            taken.add((row, column + k))
    check("0 settings tab: every widget in a grid cell of its own",
          not clash and len(taken) > 12, f"{len(taken)} cells, clashes {clash}")
    try:
        dialog.update_idletasks()
        x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
        grab((x, y, x + dialog.winfo_width(), y + dialog.winfo_height())).save(
            os.path.join(OUT, "0-settings.png"))
    except Exception:
        log_lines.append(f"screenshot 0-settings failed: {traceback.format_exc()}")
    check("0 Free move unticked by default", minimap.FREE_KEY not in minimap.config.values
          and minimap._free.get() is False, repr(minimap._free.get()))
    check("settings holds the grab before place", str(root.grab_current()) == str(dialog))
    button.invoke()
    pump()
    h = minimap._handle
    check("1 map built and visible outside the SRV", h and u.IsWindowVisible(h), f"handle {h}")
    check("1 placing mode on", minimap._placing)
    check("1 grab moved to the map", str(root.grab_current()) == str(minimap._window),
          f"grab on {root.grab_current()}")
    check("1 click-through off while placing", not exstyle(h) & 0x20, hex(exstyle(h)))
    shot("1-preview")

    # 2. Drag by 150 px.
    before = rect(h)
    drag(-150, 100)
    after = rect(h)
    check("2 drag moved the window -150/+100", (after[0] - before[0], after[1] - before[1]) == (-150, 100),
          f"{before[:2]} -> {after[:2]}")

    # 3. Lock with Esc.
    minimap._window.event_generate("<Escape>")
    pump()
    check("3 placing mode off", not minimap._placing)
    check("3 grab back on Settings", str(root.grab_current()) == str(dialog),
          f"grab on {root.grab_current()}")
    check("3 click-through back on", exstyle(h) & 0x20, hex(exstyle(h)))
    check("3 map hidden again, not in the SRV", not u.IsWindowVisible(h))

    # 4. Stored as screen pixels.
    stored = minimap.config.values.get(minimap.POS_KEY)
    check("4 position stored under rhinospotter_minimap_xy as screen pixels",
          stored == f"{after[0]},{after[1]}", f"stored {stored!r}, window {after[:2]}")
    check("4 Free move switched on", minimap.config.values.get(minimap.FREE_KEY) is True)

    # 5. A double-click without a drag stores nothing.
    minimap.config.values[minimap.POS_KEY] = "sentinel"
    button.invoke()
    pump()
    c = minimap._canvas
    rx, ry = minimap._window.winfo_rootx() + 20, minimap._window.winfo_rooty() + 20
    for _ in range(2):                  # Tk makes the second press a Double-Button-1
        c.event_generate("<Button-1>", x=20, y=20, rootx=rx, rooty=ry)
        c.event_generate("<ButtonRelease-1>", x=20, y=20, rootx=rx, rooty=ry)
    pump()
    check("5 double-click locks", not minimap._placing)
    check("5 double-click without a drag stores nothing",
          minimap.config.values.get(minimap.POS_KEY) == "sentinel",
          repr(minimap.config.values.get(minimap.POS_KEY)))
    minimap.config.values[minimap.POS_KEY] = stored

    # 6. In the SRV with Free move on: at the stored pixels.
    minimap._placed = None
    tick()
    pump(0.3)
    got = rect(h)
    check("6 in the SRV: shown", u.IsWindowVisible(h))
    check("6 no LaunchSRV seen: taken as the Rhino, painted",
          minimap._srv_type is None and minimap.SRV_KEY not in minimap.config.values
          and minimap._coverage is not None and minimap._coverage.version > 0,
          f"srv {minimap._srv_type!r}, version {getattr(minimap._coverage, 'version', None)}")
    check("6 free move: at the stored pixels", f"{got[0]},{got[1]}" == stored, f"{got[:2]} vs {stored}")
    shot("6-free")
    grab((0, 0, root.winfo_screenwidth(), root.winfo_screenheight())).save(os.path.join(OUT, "6-screen.png"))

    # 7. Free move off: the corner of the Elite window.
    minimap.config.values[minimap.FREE_KEY] = False
    minimap._placed = None
    tick()
    pump(0.3)
    got = rect(h)
    game = overlay._game_rect()
    if game:
        inset = max(16, int((game[3] - game[1]) * 0.03))
        want = (game[2] - inset - (got[2] - got[0]), game[1] + inset)
        check("7 free move off: top right of Elite", got[:2] == want, f"{got[:2]} vs {want}, game {game}")
    else:
        check("7 free move off: Elite window found", False, "Elite not running")
    shot("7-corner")

    # 8. Topmost after a tick.
    check("8 topmost after a tick", topmost(h), hex(exstyle(h)))

    # 9. Demoted behind Elite: back within TOPMOST_EVERY_S + one tick.
    tick()
    u.SetWindowPos(h, NOTOPMOST, 0, 0, 0, 0, NOACT_NOMOVE)
    if elite:
        u.SetWindowPos(h, elite, 0, 0, 0, 0, NOACT_NOMOVE)
    demoted = time.monotonic()
    check("9 demoted (setup)", not topmost(h))
    sent_at = overlay._topmost_sent[h][1]
    back = None
    early = []                          # (s since the last send, topmost) for ticks inside the interval
    while time.monotonic() - demoted < overlay.TOPMOST_EVERY_S + 3:
        since = time.monotonic() - sent_at
        tick()
        if since < overlay.TOPMOST_EVERY_S - 0.05:
            early.append((round(since, 1), topmost(h)))
        if topmost(h):
            back = time.monotonic() - demoted
            break
        pump(1.0)                       # the poll in rs_ui/main.py: 1000 ms
    check(f"9 back on top within {overlay.TOPMOST_EVERY_S} s + 1 tick",
          back is not None and back <= overlay.TOPMOST_EVERY_S + 1.2,
          f"{back:.1f} s" if back is not None else "never")
    check(f"9 not re-sent inside {overlay.TOPMOST_EVERY_S} s of the last send",
          len(early) >= 2 and not any(up for _, up in early), f"ticks inside: {early}")

    # 10. Hidden, demoted, shown: on top at once.
    minimap.hide()
    u.SetWindowPos(h, NOTOPMOST, 0, 0, 0, 0, NOACT_NOMOVE)
    tick()
    check("10 shown again: visible and topmost on the same tick", u.IsWindowVisible(h) and topmost(h),
          hex(exstyle(h)))

    # 14. Demoted inside the interval, then moved: re-sent on the same tick.
    tick()
    u.SetWindowPos(h, NOTOPMOST, 0, 0, 0, 0, NOACT_NOMOVE)
    minimap.config.values[minimap.FREE_KEY] = True
    minimap.config.values[minimap.POS_KEY] = "400,300"
    tick()
    got = rect(h)
    check("14 moved inside the interval: at the new pixels", got[:2] == (400, 300), str(got[:2]))
    check("14 moved inside the interval: topmost on the same tick", topmost(h), hex(exstyle(h)))

    # 15. Stored positions off the monitor, and unreadable ones.
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    minimap.config.values[minimap.POS_KEY] = "5000,5000"
    tick()
    got = rect(h)
    want = (sw - (got[2] - got[0]), sh - (got[3] - got[1]))
    check("15 5000,5000 pulled back to the monitor's bottom right", got[:2] == want,
          f"{got[:2]} vs {want}, screen {sw}x{sh}")
    shot("15-clamped")
    minimap.config.values[minimap.POS_KEY] = "-800,-800"
    tick()
    got = rect(h)
    check("15 -800,-800 stops at the monitor's top left", got[:2] == (0, 0), str(got[:2]))
    for stored_bad in ("", "left", "10", "10,20,30", "a,b"):
        minimap.config.values[minimap.POS_KEY] = stored_bad
        tick()
        got = rect(h)
        check(f"15 stored {stored_bad!r}: back in the corner", got[:2] == corner_xy(got),
              f"{got[:2]} vs {corner_xy(got)}")
    minimap.config.values[minimap.FREE_KEY] = False

    # 16. The Scarab: named, not painted, not saved.
    minimap.srv_event({"event": "LaunchSRV", "SRVType": "testbuggy"})
    check("16 LaunchSRV testbuggy stored under rhinospotter_srv_type",
          minimap.config.values.get(minimap.SRV_KEY) == "testbuggy",
          repr(minimap.config.values.get(minimap.SRV_KEY)))
    for lat in (30.0, 30.1):
        tick(at("E2E Scarab 1 a", lat, 40.0))
    check("16 Scarab: map down", not u.IsWindowVisible(h))
    minimap.srv_event({"event": "DockSRV", "SRVType": "mev_rhino"})
    tick(at("E2E Scarab 1 a", 30.2, 40.0))
    check("16 DockSRV naming mev_rhino: still the Scarab, map down",
          minimap.config.values.get(minimap.SRV_KEY) == "testbuggy" and not u.IsWindowVisible(h),
          repr(minimap.config.values.get(minimap.SRV_KEY)))

    # 17. The Rhino: up, painted.
    minimap.srv_event({"event": "LaunchSRV", "SRVType": "mev_rhino"})
    for lat in (50.0, 50.1):
        tick(at("E2E Rhino 1 a", lat, 60.0))
    cover = minimap._coverage
    check("17 LaunchSRV mev_rhino: map up", u.IsWindowVisible(h))
    check("17 Rhino: painted", cover is not None and cover.body == "E2E Rhino 1 a" and cover.version > 0,
          f"body {getattr(cover, 'body', None)!r}, version {getattr(cover, 'version', None)}")
    shot("17-rhino")

    # 18. Switched off in Settings: down, not painted.
    minimap.config.values[minimap.ENABLED_KEY] = False
    for lat in (70.0, 70.1):
        tick(at("E2E Off 1 a", lat, 80.0))
    check("18 switched off: map down", not u.IsWindowVisible(h))
    check("18 switched off: the Rhino map untouched", minimap._coverage is cover,
          f"body {getattr(minimap._coverage, 'body', None)!r}")
    minimap.config.values[minimap.ENABLED_KEY] = True

    # 16-18 on disk: the debounced write lands within 2 s.
    pump(3.0)
    saved = {body: len(coverstore.maps(body)) for body in ("E2E Rhino 1 a", "E2E Scarab 1 a", "E2E Off 1 a")}
    check("17 Rhino map saved to the test db", saved["E2E Rhino 1 a"] > 0, str(saved))
    check("16 Scarab: nothing saved", saved["E2E Scarab 1 a"] == 0, str(saved))
    check("18 switched off: nothing saved", saved["E2E Off 1 a"] == 0, str(saved))

    # 11. Settings closed while placing.
    button.invoke()
    pump()
    was_placing = minimap._placing
    dialog.destroy()
    pump()
    check("11 settings destroyed while placing: locked", was_placing and not minimap._placing)
    check("11 click-through back on", exstyle(h) & 0x20, hex(exstyle(h)))

    # 19. A hotkey picked in the dropdown, then OK (EDMC calls prefs_changed, then closes).
    dialog, button = settings_dialog()
    key_id, _, default, config_key = hotkey.ACTIONS[0]
    mods = default.rsplit("+", 1)[0]
    key_var = minimap._hotkeys[key_id][1]
    menus = [w for box in button.master.winfo_children() if isinstance(box, tk.Frame)
             for w in box.winfo_children()
             if isinstance(w, tk.OptionMenu) and w.cget("textvariable") == str(key_var)]
    if menus:
        menus[0]["menu"].invoke("Q")
    pump()
    minimap.prefs_changed()
    check(f"19 hotkey dropdown found for {config_key}", len(menus) == 1, f"{len(menus)} found")
    check(f"19 OK stores {mods}+Q under {config_key}",
          minimap.config.values.get(config_key) == f"{mods}+Q",
          repr(minimap.config.values.get(config_key)))
    check("19 hotkey.label() returns the new combination", hotkey.label(key_id) == f"{mods}+Q",
          hotkey.label(key_id))

    # 20. Settings closed without placing.
    stored_before, placed_before = minimap.config.values.get(minimap.POS_KEY), placed_log()
    dialog.destroy()
    pump()
    check("20 settings closed without placing: no lock",
          not minimap._placing and placed_log() == placed_before, f"'placed' logged {placed_log() - placed_before}x")
    check("20 settings closed without placing: position unchanged",
          minimap.config.values.get(minimap.POS_KEY) == stored_before,
          f"{stored_before!r} -> {minimap.config.values.get(minimap.POS_KEY)!r}")

    # 12. Tk callback errors across the run.
    check("12 no Tk callback exceptions", not errors, errors[0][-300:] if errors else "")
finally:
    try:
        minimap.stop()
        root.destroy()
    except Exception as err:
        errors.append(f"teardown: {err}")

live_after = os.stat(LIVE_DB)
check("13 live db untouched (size, mtime)",
      (live_before.st_size, live_before.st_mtime_ns) == (live_after.st_size, live_after.st_mtime_ns))
check("13 harness db is the copy", database.PATH.startswith(DATA), database.PATH)

failed = [r for r in results if not r[1]]
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"minimap E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.write(f"elite hwnd {elite}  game rect {game_at_start}  "
                 f"{'STAND-IN window, game not running' if stand_in else 'real game'}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
    report.write("\n--- plugin log ---\n" + "".join(log_lines))
    if errors:
        report.write("\n--- Tk errors ---\n" + "\n".join(errors))
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
