"""E2E harness: mouse press tracker and rig radar. Checks and blind spots: rigradar.md.

Run from the plugin folder:  python rs_e2etest/rigradar_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt, presses.csv, radar-*.png. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the db starts empty.
"""

import csv
import ctypes
import glob
import json
import math
import os
import shutil
import sys
import threading
import time
import traceback
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_TRACE = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "trace")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
JOURNALS = os.path.join(OUT, "journals")
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
os.makedirs(JOURNALS)
live_before = sorted((f, os.path.getmtime(f)) for f in glob.glob(os.path.join(LIVE_TRACE, "*")))
os.environ["LOCALAPPDATA"] = OUT
os.environ["RHINOSPOTTER_DEBUG"] = "1"                   # the CSV the checks read is DEBUG only
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")

import tkinter as tk                                     # noqa: E402

from PIL import ImageGrab                                # noqa: E402
from rs_core import coverage, database, palette, paths, rigplan   # noqa: E402
from rs_ui import main, minimap, overlay, press, rigradar         # noqa: E402

assert database.PATH.startswith(OUT), database.PATH
assert press.DIR.startswith(OUT), press.DIR

SYSTEM, BODY = "E2E Rigradar", "E2E Rigradar 1 a"
RADIUS = 1_500_000.0
LAT, LON = 10.0, 20.0
u = ctypes.WinDLL("user32", use_last_error=True)
u.FindWindowW.restype = wintypes.HWND
u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.WindowFromPoint.argtypes = [wintypes.POINT]
u.WindowFromPoint.restype = wintypes.HWND
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

results = []


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


def status(flags=coverage.IN_SRV, north_m=0.0, east_m=0.0, heading=0):
    lat = LAT + math.degrees(north_m / RADIUS)
    lon = LON + math.degrees(east_m / (RADIUS * math.cos(math.radians(lat))))
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"Flags": flags, "BodyName": BODY, "Latitude": lat, "Longitude": lon,
                   "Altitude": 0, "PlanetRadius": RADIUS, "Heading": heading}, handle)


def pump(seconds):
    """Wait on the driver thread while the mainloop runs (main._on_ui needs it, as in EDMC)."""
    time.sleep(seconds)


MOUSE = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}   # MOUSEEVENTF_*DOWN, *UP
spot = {}                                                # "elite" / "harness": (x, y) to click at


def click(button, seconds, at):
    """Real button press via mouse_event at screen point `at`, held `seconds`."""
    down, up = MOUSE[button]
    u.SetCursorPos(*spot[at])
    u.mouse_event(down, 0, 0, 0, 0)
    pump(seconds)
    u.mouse_event(up, 0, 0, 0, 0)


def settle():
    """Release seen by the 20 ms poll, then a Tk call queued behind released()."""
    pump(0.15)
    on_tk(lambda: None)
    pump(0.1)


def hold(button, seconds, at="elite"):
    click(button, seconds, at)
    settle()


def tap(button, seconds=0.1, gap=0.6):
    click(button, seconds, "elite")
    pump(gap)


def rows():
    files = glob.glob(os.path.join(press.DIR, "presses-*.csv"))
    if not files:
        return []
    with open(files[0], encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def radar_handle():
    if rigradar._window is None:
        return None
    return u.GetParent(rigradar._window.winfo_id()) or rigradar._window.winfo_id()


def visible():
    handle = radar_handle()
    return bool(handle) and bool(u.IsWindowVisible(handle))


def rings():
    """[(outline, width, dash)] of the rings on the canvas."""
    c = rigradar._canvas
    if c is None:
        return []
    return [(c.itemcget(i, "outline"), float(c.itemcget(i, "width")), c.itemcget(i, "dash"))
            for i in c.find_withtag("ring")]


def border():
    c = rigradar._canvas
    if c is None:
        return None
    return next((c.itemcget(i, "outline") for i in c.find_all() if c.type(i) == "rectangle"), None)


def hint():
    c = rigradar._canvas
    if c is None:
        return None
    return next((c.itemcget(i, "text") for i in c.find_withtag("hint")), None)


def grid():
    """(vertical, horizontal) raster lines on the canvas."""
    c = rigradar._canvas
    if c is None:
        return 0, 0
    lines = [c.coords(i) for i in c.find_withtag("grid")]
    return sum(1 for x0, y0, x1, y1 in lines if x0 == x1), sum(1 for x0, y0, x1, y1 in lines if y0 == y1)


def on_tk(function):
    """Run `function` on the Tk thread and wait for it."""
    done = threading.Event()
    out = []

    def call():
        try:
            out.append(function())
        finally:
            done.set()
    root.after(0, call)
    done.wait(10)
    return out[0] if out else None


class Notebook:
    Frame, Label, Button, Checkbutton = tk.Frame, tk.Label, tk.Button, tk.Checkbutton

    @staticmethod
    def OptionMenu(master, variable, default, *values):
        return tk.OptionMenu(master, variable, default, *values)


def front(at):
    """Stand-in ("elite") or harness window to the front by a real left click on it.

    No ALT tap: it put the Tk window in menu mode and stalled the mainloop 14 s.
    """
    click("left", 0.05, at)
    pump(0.4)


def foreign(box):
    """Windows of other processes at 7 x 7 probe points of `box`."""
    pid, found = os.getpid(), set()
    x0, y0, x1, y1 = box
    for i in range(7):
        for j in range(7):
            point = wintypes.POINT(int(x0 + (x1 - x0) * (i + 0.5) / 7), int(y0 + (y1 - y0) * (j + 0.5) / 7))
            handle = u.WindowFromPoint(point)
            owner = wintypes.DWORD()
            u.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value != pid:
                found.add(owner.value)
    return found


def shot(name):
    """Grab the radar. Box from GetWindowRect per-monitor aware: ImageGrab takes physical
    pixels, winfo_* gives scaled ones (125%: 794 -> 992 px)."""
    rigradar._window.update_idletasks()
    old = u.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
    try:
        rect = wintypes.RECT()
        u.GetWindowRect(radar_handle(), ctypes.byref(rect))
        box = (rect.left, rect.top, rect.right, rect.bottom)
        others = foreign(box)
    finally:
        u.SetThreadDpiAwarenessContext(old)
    if others:
        return f"not grabbed: windows of pids {sorted(others)} over the box"
    ImageGrab.grab(bbox=box, all_screens=True).save(os.path.join(OUT, name))
    return name


paths.journal_dir = lambda: JOURNALS
coverage.clear_old_textures = lambda: None
config = Config()
minimap.config = config
minimap.nb = Notebook
main.start(PLUGIN)
main.journal_entry("E2E", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
root = tk.Tk()
root.title("rigradar harness")
root.geometry("300x80+40+40")

# The real game takes the foreground back on its own and is grabbed under the
# click-through radar: the focus checks and grabs need the stand-in.
if u.FindWindowW(None, overlay.GAME_TITLE):
    sys.exit("Elite is running: close it, the harness brings its own stand-in window")
stand_in = tk.Toplevel(root)
stand_in.title(overlay.GAME_TITLE)
stand_in.geometry("1200x800+300+120")
stand_in.configure(bg="#203040")
for _ in range(25):
    root.update()
    time.sleep(0.02)
elite = u.FindWindowW(None, overlay.GAME_TITLE)
# Clicks land here: stand-in top left, clear of the radar; harness window middle.
spot.update(elite=(stand_in.winfo_rootx() + 100, stand_in.winfo_rooty() + 100),
            harness=(root.winfo_rootx() + 150, root.winfo_rooty() + 40))
cursor = wintypes.POINT()
u.GetCursorPos(ctypes.byref(cursor))
grabs = []

main.build(root)
errors = []
root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))


def body():
    try:
        status()
        u.SetForegroundWindow(elite)                     # no click: it would be a CSV row before check 1
        pump(0.4)
        check("0 stand-in Elite is in front", overlay.game_focused())

        # 1: short press
        hold("right", 0.3)
        r = rows()
        check("1 short press logged, rig 0", len(r) == 1 and r[0]["rig"] == "0" and r[0]["button"] == "right",
              repr(r[-1:]))
        check("1 short press: no radar", rigradar._window is None)

        # 2: long press
        hold("right", 1.3)
        r = rows()
        check("2 long press: rig 1", len(r) == 2 and r[1]["rig"] == "1", repr(r[-1:]))
        check("2 rig button learned: right", press._rig_button == "right", repr(press._rig_button))
        check("2 ms measured 1300 +-80", r and abs(int(r[-1]["ms"]) - 1300) <= 80, r[-1]["ms"] if r else "")
        check("2 radar visible", visible())
        check("2 text at the rig", rigradar._text == f"Next rig: drive {rigplan.SPACING_M:.0f} m on", rigradar._text)
        check("2 hide line names the rig button", hint() == "To hide: double click right mouse", repr(hint()))
        check("2 no border", rigradar._canvas is not None and border() is None, border())
        check("2 too close: ring thin dashed ALERT",
              rings() and all(o == palette.ALERT and w == 1 and d for o, w, d in rings()), repr(rings()))
        lines = grid()
        want = int(rigradar.VIEW_M / rigradar.GRID_M)
        check("2 10 m raster: 25-26 lines each way", all(want <= n <= want + 1 for n in lines), repr(lines))
        grabs.append(shot("radar-1-at-rig.png"))

        # 3: drive away
        status(north_m=50.0, heading=0)
        pump(0.6)
        check("3 50 m north: drive 30 m on", rigradar._text == "Next rig: drive 30 m on", rigradar._text)
        status(north_m=90.0, heading=45)
        pump(0.6)
        check("3 90 m north: OK here", rigradar._text == "Next rig: OK here", rigradar._text)
        check("3 90 m north: ring thick solid GOOD",
              rings() and all(o == palette.GOOD and w == 3 and not d for o, w, d in rings()), repr(rings()))
        check("3 90 m north: still no border", border() is None, border())
        grabs.append(shot("radar-2-ok.png"))

        # 4: position under the arrow
        left, top, right, bottom = overlay._game_rect()
        want_x = left + (right - left - rigradar._window.winfo_width()) // 2
        want_y = top + max(24, int((bottom - top) * 0.04)) + overlay.HEIGHT + rigradar.GAP
        got = (rigradar._window.winfo_rootx(), rigradar._window.winfo_rooty())
        check("4 centred under the guide arrow", abs(got[0] - want_x) <= 2 and abs(got[1] - want_y) <= 2,
              f"at {got}, want {(want_x, want_y)}")

        # 5: second rig
        hold("right", 1.3)
        check("5 two rings", len(rings()) == 2, f"{len(rings())} rings")
        check("5 text from the nearest (new) rig", rigradar._text == f"Next rig: drive {rigplan.SPACING_M:.0f} m on",
              rigradar._text)
        status(north_m=130.0, heading=180)
        pump(0.6)
        check("5 40 m past rig 2: drive 40 m on", rigradar._text == "Next rig: drive 40 m on", rigradar._text)
        grabs.append(shot("radar-3-two-rigs.png"))

        # 6: left button
        n = len(rows())
        hold("left", 1.3)
        r = rows()
        check("6 left long press after right learned: logged, rig 0", len(r) == n + 1 and r[-1]["button"] == "left"
              and r[-1]["rig"] == "0", repr(r[-1:]))

        # 7 / 8: Elite not in front
        front("harness")
        pump(0.6)
        check("7 Elite not in front: game_focused False", not overlay.game_focused())
        check("7 Elite not in front: radar hidden", not visible())
        n = len(rows())
        hold("right", 1.3, at="harness")
        check("8 long press, Elite not in front: not logged", len(rows()) == n, f"{len(rows()) - n} rows")
        check("8 still two rings", len(rings()) == 2, f"{len(rings())}")
        front("elite")
        pump(0.6)
        check("7 back in front: radar shown", visible())

        # 9: other SRV
        minimap.srv_event({"event": "LaunchSRV", "SRVType": "testbuggy"})
        n = len(rows())
        hold("right", 1.3)
        r = rows()
        check("9 other SRV: rig 0, rhino 0", len(r) == n + 1 and r[-1]["rig"] == "0" and r[-1]["rhino"] == "0",
              repr(r[-1:]))
        minimap.srv_event({"event": "LaunchSRV", "SRVType": minimap.RHINO})

        # 10: click-through
        exstyle = u.GetWindowLongW(radar_handle(), -20)
        check("10 WS_EX_TRANSPARENT set", bool(exstyle & 0x20), hex(exstyle))

        # 14: Settings toggle off, then on again
        on_tk(lambda: minimap.prefs(root))
        on_tk(lambda: minimap._rig_radar.set(False))
        on_tk(minimap.prefs_changed)
        check("14 toggle off: saved", config.values.get(minimap.RIG_RADAR_KEY) is False,
              repr(config.values.get(minimap.RIG_RADAR_KEY)))
        check("14 toggle off: open radar closed", rigradar._window is None and rigradar._rigs == [])
        n = len(rows())
        hold("right", 1.3)
        check("14 toggle off: long press not logged, no radar", len(rows()) == n and rigradar._window is None,
              f"{len(rows()) - n} rows")
        on_tk(lambda: minimap._rig_radar.set(True))
        on_tk(minimap.prefs_changed)
        hold("right", 1.3)
        check("14 toggle on again: rig placed", rigradar._window is not None and len(rigradar._rigs) == 1,
              repr(rigradar._rigs))

        # 15: new session, deploy bound to the left button
        press._rig_button = None                         # as at EDMC start (module import)
        hold("left", 1.3)
        r = rows()
        check("15 new session, long left press: rig, left learned",
              r[-1]["button"] == "left" and r[-1]["rig"] == "1" and press._rig_button == "left"
              and len(rigradar._rigs) == 2, repr(r[-1:]) + repr(press._rig_button))
        check("15 hide line names left", hint() == "To hide: double click left mouse", repr(hint()))
        hold("right", 1.3)
        r = rows()
        check("15 then long right press: rig 0", r[-1]["button"] == "right" and r[-1]["rig"] == "0"
              and len(rigradar._rigs) == 2, repr(r[-1:]))

        # 16: double click on the rig button (left since 15) closes the radar
        tap("right", gap=0.15)
        tap("right")
        check("16 double click on the other button: radar stays", rigradar._window is not None)
        tap("left", gap=1.0)
        tap("left")
        check("16 two taps 1.0 s apart: radar stays", rigradar._window is not None)
        tap("left", gap=0.15)
        tap("left")
        check("16 double click on the rig button: radar closed, rigs forgotten",
              rigradar._window is None and rigradar._rigs == [], repr(rigradar._rigs))

        # 17: release build (RHINOSPOTTER_DEBUG unset): no CSV, rig still placed
        press.DEBUG = False
        n = len(rows())
        hold("left", 1.3)
        check("17 DEBUG off: press not written, rig placed", len(rows()) == n and len(rigradar._rigs) == 1,
              f"{len(rows()) - n} rows, {len(rigradar._rigs)} rigs")
        press.DEBUG = True

        # 11: out of the SRV
        status(flags=0)
        pump(0.6)
        check("11 out of the SRV: radar closed", rigradar._window is None)
        check("11 rigs forgotten", rigradar._rigs == [], repr(rigradar._rigs))
        n = len(rows())
        hold("right", 1.3)
        check("11 press out of the SRV: not logged", len(rows()) == n, f"{len(rows()) - n} rows")
    except Exception:
        check("harness ran without an exception", False, traceback.format_exc())
    finally:
        root.after(0, root.quit)


threading.Thread(target=body, name="e2e-driver", daemon=True).start()
root.mainloop()
u.SetCursorPos(cursor.x, cursor.y)
main.stop()
check("12 main.stop(): press thread ended", press._thread is None)
check("13 no Tk callback exceptions", not errors, errors[0][-400:] if errors else "")
root.destroy()

check("0 CSV under the run folder", all(f.startswith(OUT) for f in glob.glob(os.path.join(press.DIR, "*"))),
      press.DIR)
check("0 live trace folder untouched",
      sorted((f, os.path.getmtime(f)) for f in glob.glob(os.path.join(LIVE_TRACE, "*"))) == live_before)
for f in glob.glob(os.path.join(press.DIR, "presses-*.csv")):
    shutil.copy(f, os.path.join(OUT, "presses.csv"))

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
lines += ["", "grabs:"] + [f"  {g}" for g in grabs]
report = "\n".join(lines)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(OUT)
sys.exit(1 if failed else 0)
