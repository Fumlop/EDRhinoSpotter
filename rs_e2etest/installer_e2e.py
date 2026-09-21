"""E2E harness for the standalone installer. Checks: installer.md.

Run from the repo folder after `python installer/build.py`:
    python rs_e2etest/installer_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
"""

import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import time
import winreg
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from rs_core import update                                   # noqa: E402

SETUP = os.path.join(ROOT, "installer", "dist", f"RhinoSpotter-{update.VERSION}-Setup.exe")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
APP = os.path.join(OUT, "app")
DATA = os.path.join(OUT, "localappdata")
STORE = os.path.join(DATA, "RhinoSpotter")
JOURNALS = os.path.join(OUT, "journals")
LOG = os.path.join(STORE, "log", "rhinospotter.log")
LIVE = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter")
UNINSTALL_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\{5B7C1E2A-9D4F-4E6B-8A3C-2F1D7E9B4C60}_is1")
SYSTEM = "E2E Installer Test"
JOURNAL = os.path.join(JOURNALS, "Journal.2026-09-21T200000.01.log")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def line(**entry):
    entry.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return json.dumps(entry) + "\n"


def log_text():
    try:
        with open(LOG, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def wait(predicate, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.25)
    return predicate()


def windows_of(pid):
    u = ctypes.windll.user32
    found = []

    def each(hwnd, _):
        owner = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(128)
            u.GetWindowTextW(hwnd, text, 128)
            found.append(text.value)
        return True
    u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(each), 0)
    return found


def uninstall_key_exists():
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY))
        return True
    except FileNotFoundError:
        return False


def db_systems():
    path = os.path.join(STORE, "db", "rhinospotter.db")
    if not os.path.isfile(path):
        return []
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return [row[0] for row in conn.execute("SELECT DISTINCT system FROM bodies")]


live_before = (os.path.exists(os.path.join(LIVE, "standalone.json")),
               os.path.exists(os.path.join(LIVE, "db", "instance.lock")))
os.makedirs(JOURNALS)
os.makedirs(STORE)
with open(os.path.join(STORE, "standalone.json"), "w", encoding="utf-8") as handle:
    json.dump({"journaldir": JOURNALS, "rhinospotter_minimap_keep": True,
               # not the Ctrl+Alt defaults a running EDMC plugin holds
               "rhinospotter_hotkey_center": "Ctrl+Alt+Shift+F9",
               "rhinospotter_hotkey_border": "Ctrl+Alt+Shift+F10",
               "rhinospotter_hotkey_zoom": "Ctrl+Alt+Shift+F11",
               "rhinospotter_hotkey_data": "Ctrl+Alt+Shift+F12"}, handle)
with open(JOURNAL, "w", encoding="utf-8", newline="") as handle:
    handle.write(line(event="Fileheader", part=1, gameversion="4.2", build="e2e"))
    handle.write(line(event="Commander", FID="F0", Name="E2E"))
    handle.write(line(event="LoadGame", Commander="E2E", FID="F0"))
    handle.write(line(event="Location", StarSystem=SYSTEM, SystemAddress=4242, Body=f"{SYSTEM} 1 a",
                      BodyType="Planet", Docked=False))

app = None
try:
    # 1. install
    check("0 Setup.exe built", os.path.isfile(SETUP), SETUP)
    done = subprocess.run([SETUP, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOICONS",
                           f"/DIR={APP}", f"/LOG={os.path.join(OUT, 'install.log')}"], timeout=300)
    exe = os.path.join(APP, "RhinoSpotter.exe")
    check("1 Setup exits 0", done.returncode == 0, str(done.returncode))
    check("1 RhinoSpotter.exe and the bundled textures installed",
          os.path.isfile(exe) and os.path.isdir(os.path.join(APP, "_internal", "texture")))
    check("1 uninstall key written", uninstall_key_exists())

    # 2-3. start
    env = dict(os.environ, LOCALAPPDATA=DATA)
    app = subprocess.Popen([exe], env=env)
    check("2 instance.lock in the test data folder",
          wait(lambda: os.path.exists(os.path.join(STORE, "db", "instance.lock")), 20))
    check("2 log says started", wait(lambda: "standalone: started" in log_text(), 20), LOG)
    check("3 a visible window of the process", wait(lambda: windows_of(app.pid), 20),
          repr(windows_of(app.pid)))
    check("3 still running after 5 s", wait(lambda: False, 5) or app.poll() is None, str(app.poll()))

    # 4. journal: a landable Scan appended after start
    with open(JOURNAL, "a", encoding="utf-8", newline="") as handle:
        handle.write(line(event="Scan", ScanType="Detailed", BodyName=f"{SYSTEM} 1 a", BodyID=5,
                          StarSystem=SYSTEM, SystemAddress=4242, DistanceFromArrivalLS=100.0,
                          PlanetClass="Rocky body", Landable=True, Atmosphere="", Volcanism="",
                          SurfaceGravity=2.0, SurfaceTemperature=200.0))
    check("4 the Scan reaches the test db", wait(lambda: SYSTEM in db_systems(), 15),
          repr(db_systems()))

    # 5. in the SRV: the minimap draws from the bundled texture and sheet
    with open(os.path.join(JOURNALS, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"event": "Status", "Flags": 0x4000000 | 0x200000, "BodyName": f"{SYSTEM} 1 a",
                   "Latitude": 10.0, "Longitude": 20.0, "PlanetRadius": 1_500_000,
                   "Heading": 90}, handle)
    check("5 minimap built in the SRV", wait(lambda: "minimap: built" in log_text(), 15))

    text = log_text()
    check("6 no Traceback in the log", "Traceback" not in text)
    # grounds.Sheet keeps a read error to itself; the file is checked instead.
    check("6 no missing texture in the log", "texture, plain ground instead" not in text)
    check("6 mining_sheet.json bundled", os.path.isfile(os.path.join(APP, "_internal", "mining_sheet.json")))
finally:
    if app is not None and app.poll() is None:
        app.terminate()
        app.wait(timeout=15)
    with open(os.path.join(OUT, "rhinospotter.log"), "w", encoding="utf-8") as handle:
        handle.write(log_text())

# 7. uninstall
uninstaller = os.path.join(APP, "unins000.exe")
if os.path.isfile(uninstaller):
    done = subprocess.run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=120)
    wait(lambda: not os.path.isfile(os.path.join(APP, "RhinoSpotter.exe")), 20)
    check("7 uninstall exits 0", done.returncode == 0, str(done.returncode))
check("7 exe removed", not os.path.isfile(os.path.join(APP, "RhinoSpotter.exe")))
check("7 uninstall key removed", wait(lambda: not uninstall_key_exists(), 20))

# 8. live folder
live_after = (os.path.exists(os.path.join(LIVE, "standalone.json")),
              os.path.exists(os.path.join(LIVE, "db", "instance.lock")))
check("8 no standalone.json or instance.lock made in the live folder",
      live_after == live_before, f"{live_before} -> {live_after}")

failed = [r for r in results if not r[1]]
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"installer E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}  {os.path.basename(SETUP)}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
