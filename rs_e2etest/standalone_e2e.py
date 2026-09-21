"""E2E harness for standalone.py and the lock it shares with the plugin.
Checks and blind spots: standalone.md.

Run from the plugin folder:  python rs_e2etest/standalone_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA and USERPROFILE point at the run folder before rs_core loads; one
real journal is read from the user's Saved Games folder and copied, filtered:
no Shutdown, no FSSDiscoveryScan (no Spansh request). Hotkeys are four
Ctrl+Alt+Shift+F9..F12 combos seeded in standalone.json; no key is sent,
WM_HOTKEY is posted to the module's own thread. Window messages go only to
windows of the child processes this harness starts.
"""

import ctypes
import glob
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_ROOT = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter")
LIVE_DB = os.path.join(LIVE_ROOT, "db", "rhinospotter.db")
REAL_JOURNALS = os.path.join(os.environ["USERPROFILE"], "Saved Games", "Frontier Developments",
                             "Elite Dangerous")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
JOURNAL_TAIL = ("Saved Games", "Frontier Developments", "Elite Dangerous")


def env_for(name):
    """(env, data root, journal folder) of a fresh LOCALAPPDATA/USERPROFILE pair."""
    base = os.path.join(OUT, name)
    data = os.path.join(base, "localappdata")
    profile = os.path.join(base, "profile")
    journals = os.path.join(profile, *JOURNAL_TAIL)
    os.makedirs(data)
    os.makedirs(journals)
    env = dict(os.environ, LOCALAPPDATA=data, USERPROFILE=profile, RHINOSPOTTER_DEBUG="1",
               PYTHONWARNINGS="ignore")
    return env, os.path.join(data, "RhinoSpotter"), journals


def live_snapshot():
    stat = os.stat(LIVE_DB) if os.path.exists(LIVE_DB) else None
    return ((stat.st_size, stat.st_mtime_ns) if stat else None,
            os.path.exists(os.path.join(LIVE_ROOT, "standalone.json")),
            os.path.exists(os.path.join(LIVE_ROOT, "db", "instance.lock")))


os.makedirs(OUT)
live_before = live_snapshot()
ENV_A, ROOT_A, JDIR_A = env_for("a")
os.environ.update(LOCALAPPDATA=ENV_A["LOCALAPPDATA"], USERPROFILE=ENV_A["USERPROFILE"],
                  RHINOSPOTTER_DEBUG="1")
sys.path.insert(0, PLUGIN)

results = []
errors = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


# ------------------------------------------------------------ the journal copy

def pick_journal():
    """(path, head lines, landable Scan lines after the head, system, cmdr) from the
    newest real journal carrying a landable Scan after a Location or FSDJump."""
    for path in sorted(glob.glob(os.path.join(REAL_JOURNALS, "Journal.*.log")),
                       key=os.path.getctime, reverse=True):
        with open(path, encoding="utf-8") as handle:
            lines = [line if line.endswith("\n") else line + "\n" for line in handle]
        system = cmdr = None
        for index, line in enumerate(lines):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            event = entry.get("event")
            if event == "LoadGame":
                cmdr = entry.get("Commander")
            if event in ("Location", "FSDJump"):
                system = entry.get("StarSystem")
            if event == "Scan" and entry.get("Landable") and system and cmdr:
                head = [x for x in lines[:index]
                        if '"event":"Shutdown"' not in x and "FSSDiscoveryScan" not in x]
                scans = []
                for later in lines[index:]:
                    if '"event":"FSDJump"' in later or '"event":"Location"' in later:
                        break
                    if '"event":"Scan"' in later and '"Landable":true' in later:
                        scans.append(later)
                return path, head, scans, system, cmdr
    return None


picked = pick_journal()
if picked is None:
    print("no real journal with a landable Scan found in " + REAL_JOURNALS)
    sys.exit(1)
SOURCE, HEAD, SCANS, SYSTEM, CMDR = picked
JOURNAL = os.path.join(JDIR_A, os.path.basename(SOURCE))
with open(JOURNAL, "w", encoding="utf-8", newline="") as handle:
    handle.writelines(HEAD)
STATUS = os.path.join(JDIR_A, "Status.json")

# Hotkeys the live plugin does not hold; standalone reads them from its config.
HOTKEYS = {"rhinospotter_hotkey_center": "Ctrl+Alt+Shift+F9",
           "rhinospotter_hotkey_border": "Ctrl+Alt+Shift+F10",
           "rhinospotter_hotkey_zoom": "Ctrl+Alt+Shift+F11",
           "rhinospotter_hotkey_data": "Ctrl+Alt+Shift+F12"}
os.makedirs(ROOT_A)
with open(os.path.join(ROOT_A, "standalone.json"), "w", encoding="utf-8") as handle:
    json.dump(HOTKEYS, handle)


def append(text):
    with open(JOURNAL, "a", encoding="utf-8", newline="") as handle:
        handle.write(text)


def line(event, **fields):
    return json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "event": event, **fields}, separators=(",", ":")) + "\n"


def write_status(**fields):
    status = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "event": "Status", **fields}
    with open(STATUS + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(status, handle)
    os.replace(STATUS + ".tmp", STATUS)


def rows(sql, *args):
    from rs_core import database
    with sqlite3.connect(database.PATH, timeout=5) as conn:
        return conn.execute(sql, args).fetchall()


# ------------------------------------------------------------ Win32 helpers

u = ctypes.WinDLL("user32", use_last_error=True)
u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.IsWindowVisible.argtypes = [wintypes.HWND]
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
WM_CLOSE = 0x0010
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def probe(combo):
    """0 when `combo` was free, else the Win32 error (1409: held)."""
    from rs_ui import hotkey
    flags, vk = hotkey.parse(combo)
    out = []

    def run():
        if u.RegisterHotKey(None, 0xB001, flags, vk):
            u.UnregisterHotKey(None, 0xB001)
            out.append(0)
        else:
            out.append(ctypes.get_last_error())
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    return out[0]


def _text(hwnd):
    buffer = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(hwnd, buffer, 512)
    return buffer.value


def _class(hwnd):
    buffer = ctypes.create_unicode_buffer(128)
    u.GetClassNameW(hwnd, buffer, 128)
    return buffer.value


def windows_of(pid):
    """[(hwnd, class, title, [child texts])] of the visible top-level windows of `pid`."""
    found = []

    def top(hwnd, _):
        owner = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            texts = []
            u.EnumChildWindows(hwnd, ENUM(lambda child, _: texts.append(_text(child)) or True), 0)
            found.append((hwnd, _class(hwnd), _text(hwnd), texts))
        return True
    u.EnumWindows(ENUM(top), 0)
    return found


def wait(until, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = until()
        if value:
            return value
        time.sleep(0.1)
    return until()


# ------------------------------------------------------------ part A, in process

import standalone                                        # noqa: E402
from rs_core import database, instance                  # noqa: E402
from rs_ui import hotkey, main, minimap, scan            # noqa: E402

assert database.PATH.startswith(ENV_A["LOCALAPPDATA"]), database.PATH

delivered = []                   # (event, system argument) as journal_entry got them
_journal_entry = main.journal_entry


def recording(cmdr, is_beta, system, station, entry, state):
    delivered.append((entry.get("event"), system, entry))
    return _journal_entry(cmdr, is_beta, system, station, entry, state)


main.journal_entry = recording
free_before = {combo: probe(combo) for combo in HOTKEYS.values()}
app = standalone.open_app()
root = app.root
root.report_callback_exception = lambda *exc: errors.append(
    "".join(traceback.format_exception(*exc)))


def ui(function, *args):
    """Run on the Tk thread, return its result to the driver thread."""
    box = queue.Queue()

    def run():
        try:
            box.put((True, function(*args)))
        except Exception as err:                         # noqa: BLE001
            box.put((False, err))
    root.after(0, run)
    ok, value = box.get(timeout=15)
    if not ok:
        raise value
    return value


def ui_wait(until, seconds):
    return wait(lambda: ui(until), seconds)


def dock_master():
    """The widget the dock is packed into, or None when it is not packed."""
    if app.dock.winfo_manager() != "pack":
        return None
    return app.dock.nametowidget(str(app.dock.pack_info()["in"]))


def dock_in_middle():
    master = dock_master()
    return master is not None and master is not root and str(master).startswith(str(root))


def part_a():
    # 1. start
    with open(instance.PATH, encoding="utf-8") as handle:
        held = handle.read()
    check("1 lock file names the standalone", "RhinoSpotter standalone" in held, held)
    check("1 log file under log\\", os.path.isfile(standalone.LOG_PATH), standalone.LOG_PATH)

    # 2. catch-up
    events = [d[0] for d in delivered]
    check("2 catch-up: only a synthesised StartUp delivered", events == ["StartUp"], events[:5])
    startup = delivered[0][2] if delivered else {}
    check("2 StartUp names the file's last system", startup.get("StarSystem") == SYSTEM,
          f"{startup.get('StarSystem')!r} vs {SYSTEM!r}")
    check("2 panel system and cmdr from the file",
          ui(lambda: (main._system, main._cmdr)) == (SYSTEM, CMDR),
          ui(lambda: (main._system, main._cmdr)))
    check("2 register holds the system", ui(lambda: main._register.system) == SYSTEM)
    check("10a dock packed in the middle pane with no bodies", ui(dock_in_middle),
          ui(lambda: str(dock_master())))
    button = ui(lambda: main._card_button)

    # 3. appended landable scans
    append("".join(SCANS))
    counted = ui_wait(lambda: len(main._register) and main._scan_count.cget("text"), 5)
    check("3 appended Scan: panel count label", counted and counted.endswith("landable")
          and counted.startswith(str(ui(lambda: len(main._register)))), counted)
    stored = wait(lambda: rows("SELECT count(*) FROM bodies WHERE system = ?", SYSTEM)[0][0], 6)
    check("3 bodies reach the db after the debounce", stored > 0, f"{stored} rows")
    check("10a dock packed on the Bookmarks tab with bodies", ui_wait(dock_in_middle, 3),
          ui(lambda: str(dock_master())))
    ui(scan._pick_view, "mapped")
    check("10a dock not packed on the Mapped tab", ui(dock_master) is None)
    ui(scan._pick_view, "bookmarks")
    check("10a dock back on the Bookmarks tab", ui(dock_in_middle))
    check("10a panel widgets kept across redraws",
          ui(lambda: main._card_button is button and bool(button.winfo_exists())))

    # 4. half line
    append(line("Music", MusicTrack="E2E_half").rstrip("\n"))
    time.sleep(2.5)
    check("4 half line not delivered", not any(d[2].get("MusicTrack") == "E2E_half"
                                               for d in delivered))
    append("\n")
    check("4 delivered once its newline lands",
          wait(lambda: any(d[2].get("MusicTrack") == "E2E_half" for d in delivered), 3))

    # 5. rotation
    rotated = "E2E Rotated System"
    body = f"{rotated} A 1"
    append(line("Music", MusicTrack="E2E_old_last"))
    new_file = os.path.join(JDIR_A, "Journal." + time.strftime("%Y-%m-%dT%H%M%S") + ".01.log")
    with open(new_file, "w", encoding="utf-8", newline="") as handle:
        handle.write(line("Fileheader", part=1, gameversion="4.2.0.0", build="r1"))
        handle.write(line("Commander", FID="F1", Name="E2E Cmdr"))
        handle.write(line("LoadGame", Commander="E2E Cmdr", FID="F1"))
        handle.write(line("Location", StarSystem=rotated, SystemAddress=1234567890,
                          StarPos=[0.0, 0.0, 0.0], Body=body, BodyID=5, BodyType="Planet",
                          Docked=False, Population=0))
    global JOURNAL
    JOURNAL = new_file                             # append() writes here from now on
    check("5 rotation: panel follows the new file",
          ui_wait(lambda: main._system == rotated, 5), ui(lambda: main._system))
    order = [d[2].get("MusicTrack") or d[0] for d in delivered]
    check("5 old file drained before the new one",
          "E2E_old_last" in order and "Fileheader" in order
          and order.index("E2E_old_last") < order.index("Fileheader"), order[-6:])
    check("5 cmdr from the new file", ui(lambda: main._cmdr) == "E2E Cmdr")

    # 6. Status.json on the ground and not
    ground = dict(Flags=0x2, Latitude=10.0, Longitude=20.0, Altitude=0, Heading=90,
                  BodyName=body, PlanetRadius=1500000.0)
    write_status(**ground)
    check("6 on the ground: Bookmark enabled",
          ui_wait(lambda: str(main._card_button.cget("state")) == "normal", 3))
    write_status(Flags=0x1)
    check("6 docked: Bookmark disabled",
          ui_wait(lambda: str(main._card_button.cget("state")) == "disabled", 3))

    # 7. Bookmark press
    write_status(**ground)
    ui_wait(lambda: str(main._card_button.cget("state")) == "normal", 3)
    material = ui(lambda: main._materials()[0])
    ui(main._material.set, material)
    ui(main._card_button.invoke)
    marked = wait(lambda: rows("SELECT count(*) FROM bookmarks WHERE planet_name = ?",
                               body)[0][0], 5)
    check("7 Bookmark: a row in the db", marked == 1, f"{marked} rows, {material}")
    check("10a dock still packed after the bookmark redraw", ui_wait(dock_in_middle, 3))

    # 8. SRV and minimap
    append(line("LaunchSRV", SRVType="mev_rhino", Loadout="default", ID=1, PlayerControlled=True))
    ui_wait(lambda: minimap._srv_type == "mev_rhino", 3)
    with open(os.path.join(ROOT_A, "standalone.json"), encoding="utf-8") as handle:
        stored_config = json.load(handle)
    check("8 LaunchSRV kept in standalone.json",
          stored_config.get("rhinospotter_srv_type") == "mev_rhino")
    for step in range(4):
        write_status(Flags=0x4000000, Latitude=10.0 + step * 0.01, Longitude=20.0,
                     Altitude=0, Heading=0, BodyName=body, PlanetRadius=1500000.0)
        time.sleep(1.2)
    check("8 in the SRV: minimap painting",
          ui(lambda: minimap._in_srv and minimap._coverage is not None
             and minimap._coverage.version > 0))
    write_status(Flags=0x2, Latitude=10.03, Longitude=20.0, Altitude=0, Heading=0,
                 BodyName=body, PlanetRadius=1500000.0)
    maps = wait(lambda: rows("SELECT count(*) FROM maps WHERE body = ?", body)[0][0], 6)
    check("8 SRV docked: the map row in the db", maps >= 1, f"{maps} rows")

    # 9. hotkeys
    for combo in HOTKEYS.values():
        if free_before[combo]:
            check(f"9 {combo} held by standalone", True, "skipped: taken before the run")
        else:
            check(f"9 {combo} held by standalone",
                  probe(combo) == ERROR_HOTKEY_ALREADY_REGISTERED)
    zoom_before = ui(minimap.zoom)
    u.PostThreadMessageW(hotkey._thread_id or 0, hotkey.WM_HOTKEY, hotkey.SIZE, 0)
    check("9 WM_HOTKEY Zoom reaches the Tk loop and the config",
          ui_wait(lambda: minimap.zoom() != zoom_before, 3), f"zoom {zoom_before}")

    # 10. Settings
    ui(app.open_settings)
    menu_before = ui(lambda: main._menu["menu"].index("end"))

    def find(widget, kind, prefix):
        for child in widget.winfo_children():
            if isinstance(child, kind) and str(child.cget("text")).startswith(prefix):
                return child
            hit = find(child, kind, prefix)
            if hit is not None:
                return hit
        return None
    import tkinter as tk
    switch = ui(lambda: find(app.settings, tk.Checkbutton, "Show materials under"))
    ok = ui(lambda: find(app.settings, tk.Button, "OK"))
    check("10 Settings window with the minimap tab", switch is not None and ok is not None)
    if switch is not None and ok is not None:
        ui(switch.invoke)
        ui(ok.invoke)
        with open(os.path.join(ROOT_A, "standalone.json"), encoding="utf-8") as handle:
            stored_config = json.load(handle)
        check("10 OK writes rhinospotter_low_value", stored_config.get("rhinospotter_low_value")
              is True, stored_config.get("rhinospotter_low_value"))
        menu_after = ui(lambda: main._menu["menu"].index("end"))
        check("10 Material menu refilled with the cheap materials", menu_after > menu_before,
              f"{menu_before} -> {menu_after} entries")

    check("10a Tk callback exceptions", not errors, errors[0][-300:] if errors else "")

    # 11. stop
    backups_before = len(glob.glob(os.path.join(database.DIR, "backups", "*.db")))
    ui(app.close)
    wait(lambda: False, 0.5)
    backups_after = len(glob.glob(os.path.join(database.DIR, "backups", "*.db")))
    check("11 stop: db backup written", backups_after > backups_before,
          f"{backups_before} -> {backups_after}")
    taken = instance.acquire("harness")
    check("11 stop: lock released", taken is None, taken)
    instance.release()
    for combo in HOTKEYS.values():
        if not free_before[combo]:
            check(f"11 {combo} free after stop", probe(combo) == 0)


def driver():
    try:
        part_a()
    except Exception:
        errors.append(traceback.format_exc())
        check("part A ran to the end", False, errors[-1][-400:])
        try:
            root.after(0, app.close)
        except Exception:                                # noqa: BLE001
            pass


driver_thread = threading.Thread(target=driver, name="e2e-driver", daemon=True)
driver_thread.start()
root.mainloop()
driver_thread.join(30)          # its checks after close run before part B takes the same combos


# ------------------------------------------------------------ part B, children

PY = sys.executable
STANDALONE = os.path.join(PLUGIN, "standalone.py")
ENV_B, ROOT_B, _ = env_for("b")
LOCK_B = os.path.join(ROOT_B, "db", "instance.lock")
os.makedirs(ROOT_B)
with open(os.path.join(ROOT_B, "standalone.json"), "w", encoding="utf-8") as handle:
    json.dump(HOTKEYS, handle)                   # not the user's Ctrl+Alt defaults
children = []


def spawn(args, env, **kw):
    child = subprocess.Popen(args, env=env, cwd=PLUGIN, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, **kw)
    children.append(child)
    return child


def lock_text():
    try:
        with open(LOCK_B, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def dialog_of(child, seconds=20):
    """(hwnd, title, texts) of the child's message box, or None."""
    def find():
        for hwnd, cls, title, texts in windows_of(child.pid):
            if cls == "#32770":
                return hwnd, title, texts
        return None
    return wait(find, seconds)


def refused(label, holder_word):
    """A second standalone.py: dialog naming the holder, closed here, exit 1."""
    second = spawn([PY, STANDALONE], ENV_B)
    box = dialog_of(second)
    check(f"{label} refusal dialog shown", box is not None, box and box[1])
    if box:
        text = " ".join(box[2])
        check(f"{label} dialog names {holder_word}", holder_word in text, text[:160])
        u.PostMessageW(box[0], WM_CLOSE, 0, 0)
    try:
        code = second.wait(15)
    except subprocess.TimeoutExpired:
        second.kill()
        code = None
    err = second.stderr.read()
    check(f"{label} second instance exits 1", code == 1, f"exit {code}")
    check(f"{label} stderr names {holder_word}", holder_word in err, err.strip()[:160])


def close_gracefully(child):
    """WM_CLOSE to the child's main window once it is up; its exit code."""
    main_window = wait(lambda: next((hwnd for hwnd, _, title, _ in windows_of(child.pid)
                                     if title.startswith("RhinoData")), None), 20)
    if main_window:
        u.PostMessageW(main_window, WM_CLOSE, 0, 0)
    try:
        return child.wait(20)
    except subprocess.TimeoutExpired:
        child.kill()
        return None


PLUGIN_CHILD = r"""
import json, os, sys, tkinter as tk
sys.path.insert(0, {plugin!r})
sys.modules["myNotebook"] = tk            # EDMC's nb.Frame for plugin_prefs
import load
from rs_ui import hotkey, main
load.plugin_start3({plugin!r})
if {mode!r} == "hold":
    print("HELD", flush=True)
    sys.stdin.readline()
    load.plugin_stop()
    sys.exit(0)
root = tk.Tk()
frame = load.plugin_app(root)
texts = [w.cget("text") for w in frame.winfo_children() if isinstance(w, tk.Label)]
load.journal_entry("E2E", False, "Sol", None, {{"event": "FSDJump", "StarSystem": "Sol"}}, {{}})
prefs = load.plugin_prefs(root, "E2E", False)
prefs_texts = [w.cget("text") for w in prefs.winfo_children()]
load.prefs_changed("E2E", False)
load.plugin_stop()
print(json.dumps({{"texts": texts, "prefs": prefs_texts, "frame": main._frame is not None,
                   "hotkey_thread": hotkey._thread is not None, "system": main._system}}))
"""


def part_b():
    # 12. standalone first, a second one refused
    first = spawn([PY, STANDALONE], ENV_B)
    held = wait(lambda: f"pid {first.pid}" in lock_text(), 30)
    check("12 first standalone holds the lock", held, lock_text())
    refused("12", "RhinoSpotter standalone")

    # 15. standalone first, the EDMC hooks refused
    child = spawn([PY, "-c", PLUGIN_CHILD.format(plugin=PLUGIN, mode="panel")], ENV_B)
    out, err = child.communicate(timeout=60)
    try:
        seen = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        seen = {}
    check("15 plugin panel shows the refusal",
          any("RhinoSpotter standalone" in t for t in seen.get("texts", [])),
          seen.get("texts") or err[-300:])
    check("15 plugin Settings tab shows the refusal",
          any("RhinoSpotter standalone" in str(t) for t in seen.get("prefs", [])), seen.get("prefs"))
    check("15 plugin: no panel state, no hotkeys, journal ignored",
          seen and not seen["frame"] and not seen["hotkey_thread"] and seen["system"] == "",
          seen)
    backups = glob.glob(os.path.join(ROOT_B, "db", "backups", "*.db"))
    check("15 plugin wrote no backup", not backups, backups)

    # 13. standalone killed, a new one starts
    first.kill()
    first.wait(10)
    third = spawn([PY, STANDALONE], ENV_B)
    check("13 killed holder: a new standalone takes the lock",
          wait(lambda: f"pid {third.pid}" in lock_text(), 30), lock_text())
    code = close_gracefully(third)
    check("13 closed through its window: exit 0", code == 0, f"exit {code}")

    # 14. plugin first, standalone refused
    holder = spawn([PY, "-c", PLUGIN_CHILD.format(plugin=PLUGIN, mode="hold")], ENV_B,
                   stdin=subprocess.PIPE)
    ready = holder.stdout.readline().strip()
    check("14 plugin_start3 holds the lock", ready == "HELD" and "the EDMC plugin" in lock_text(),
          lock_text())
    refused("14", "the EDMC plugin")
    holder.stdin.write("\n")
    holder.stdin.flush()
    check("14 plugin_stop: exit 0", holder.wait(20) == 0)


try:
    part_b()
except Exception:
    errors.append(traceback.format_exc())
    check("part B ran to the end", False, errors[-1][-400:])
finally:
    for child in children:
        if child.poll() is None:
            child.kill()

live_after = live_snapshot()
check("16 no standalone.json or instance.lock in the live folder",
      live_after[1:] == live_before[1:], f"{live_before[1:]} -> {live_after[1:]}")
# The live db can move under a running EDMC; what this run writes is named E2E.
with sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True, timeout=5) as live:
    ours = [live.execute(sql, ("E2E Rotated System%",)).fetchone()[0] for sql in (
        "SELECT count(*) FROM bodies WHERE system LIKE ?",
        "SELECT count(*) FROM bookmarks WHERE planet_name LIKE ?",
        "SELECT count(*) FROM maps WHERE body LIKE ?")]
check("16 no row of this run in the live db", ours == [0, 0, 0],
      f"{ours}; live db {live_before[0]} -> {live_after[0]} (size, mtime)")

failed = [r for r in results if not r[1]]
log_text = ""
try:
    with open(standalone.LOG_PATH, encoding="utf-8") as handle:
        log_text = handle.read()
except OSError:
    pass
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"standalone E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.write(f"journal: {os.path.basename(SOURCE)} ({len(HEAD)} lines at start, "
                 f"{len(SCANS)} landable Scans appended), system {SYSTEM}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
    report.write("\n--- part A standalone log ---\n" + log_text[-20000:])
    if errors:
        report.write("\n--- errors ---\n" + "\n".join(errors))
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
