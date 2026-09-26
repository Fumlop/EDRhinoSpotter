"""E2E harness for the Linux X11 hotkeys (rs_ui/hotkey_x11.py via rs_ui/hotkey.py).
Checks and blind spots: x11.md.

Linux only, with an X server and xdotool:
    xvfb-run -a python rs_e2etest/x11_e2e.py
Writes rs_e2etest/out/<timestamp>-x11/report.txt. Exit code 1 on a failure.
"""

import logging
import os
import subprocess
import sys
import textwrap
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S") + "-x11")
os.makedirs(OUT)
sys.path.insert(0, PLUGIN)

import tkinter as tk                                     # noqa: E402

from rs_core import system                               # noqa: E402
from rs_ui import hotkey, hotkey_x11                     # noqa: E402

lines, fails, log_lines = [], [], []
handler = logging.StreamHandler(type("W", (), {"write": lambda s, m: log_lines.append(m),
                                                "flush": lambda s: None})())
hotkey.logger.addHandler(handler)
hotkey.logger.setLevel(logging.DEBUG)


def out(text):
    print(text, flush=True)
    lines.append(text)


def check(name, ok, detail=""):
    out(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)


root = tk.Tk()
root.withdraw()
fired = []


def recorder(name):
    return lambda: fired.append(name)


CALLBACKS = {hotkey.CENTER: recorder("center"), hotkey.BORDER: recorder("border"),
             hotkey.SIZE: recorder("zoom"), hotkey.SCAN: recorder("data")}


def pump(seconds):
    """Tk's loop running in this thread while the grab thread reads its own display."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def press(*keys, wait=0.6):
    fired.clear()
    subprocess.run(["xdotool", "key", "--clearmodifiers", *keys], check=True)
    pump(wait)
    return list(fired)


# A second X client, as another program holding a combo would be.
HOLDER = textwrap.dedent("""
    import ctypes, ctypes.util, sys, time
    x = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XStringToKeysym.restype = ctypes.c_ulong
    x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int]
    x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    errors = []
    H = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    h = H(lambda d, e: errors.append(1) or 0)
    x.XSetErrorHandler(h)
    d = x.XOpenDisplay(None)
    code = x.XKeysymToKeycode(d, x.XStringToKeysym(sys.argv[1].encode()))
    x.XGrabKey(d, code, 4 | 8, x.XDefaultRootWindow(d), 1, 1, 1)
    x.XSync(d, 0)
    print("taken" if errors else "held", flush=True)
    time.sleep(float(sys.argv[2]))
""")


def holder(key, seconds):
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, key, str(seconds)],
                            stdout=subprocess.PIPE, text=True)
    return proc, proc.stdout.readline().strip()


def error_handler_now():
    x = hotkey_x11._lib()
    current = x.XSetErrorHandler(None)
    x.XSetErrorHandler(current)
    return current


try:
    out(f"system: {system.describe()}, DISPLAY={os.environ.get('DISPLAY')}")
    check("platform flag says Linux", system.LINUX and not system.WINDOWS)

    tk_handler = error_handler_now()
    hotkey.start(CALLBACKS)
    pump(0.5)
    live = hotkey_x11.grabbed()
    check("1 grab live for the four defaults", len(live) == 4, live)
    check("6 Tk's X error handler back in place", error_handler_now() == tk_handler)
    check("11 available() with the grab", hotkey.available())
    check("11 label() names the combo", hotkey.label(hotkey.CENTER) == "Ctrl+Alt+Z",
          hotkey.label(hotkey.CENTER))

    for keys, want in (("ctrl+alt+z", "center"), ("ctrl+alt+b", "border"),
                       ("ctrl+alt+m", "zoom"), ("ctrl+alt+d", "data")):
        got = press(keys)
        check(f"2+7 {keys} -> {want}, once, Tk pumping", got == [want], got)
    got = press("ctrl+alt+q")
    check("4 ctrl+alt+q fires nothing", got == [], got)
    got = press("ctrl+z")
    check("4 ctrl+z (not our modifiers) fires nothing", got == [], got)

    subprocess.run(["xdotool", "key", "Num_Lock"], check=True)
    got = press("ctrl+alt+z")
    subprocess.run(["xdotool", "key", "Num_Lock"], check=True)
    check("3 NumLock on: still fires", got == ["center"], got)
    subprocess.run(["xdotool", "key", "Caps_Lock"], check=True)
    got = press("ctrl+alt+z")
    subprocess.run(["xdotool", "key", "Caps_Lock"], check=True)
    check("3 CapsLock on: still fires", got == ["center"], got)

    fired.clear()
    subprocess.run(["xdotool", "keydown", "ctrl+alt+z"], check=True)
    pump(1.5)
    subprocess.run(["xdotool", "keyup", "ctrl+alt+z"], check=True)
    pump(0.3)
    check("10 held 1.5 s: fires once", fired == ["center"], fired)

    out("chat on Linux with the grab live")
    hotkey._callbacks = CALLBACKS
    fired.clear()
    hotkey.chat({"event": "SendText", "To": "local", "Message": "!rs zoom"})
    check("11 chat still fires with the grab live", fired == ["zoom"], fired)

    hotkey.stop()
    pump(0.3)
    check("9 stop: thread gone", hotkey_x11._thread is None)
    check("9 stop: nothing grabbed", not hotkey_x11.grabbed())
    got = press("ctrl+alt+z")
    check("9 stop: key does nothing", got == [], got)
    proc, state = holder("z", 1)
    check("9 stop: another client can take Ctrl+Alt+Z", state == "held", state)
    proc.wait()

    proc, state = holder("b", 8)
    check("5 setup: another client holds Ctrl+Alt+B", state == "held", state)
    log_lines.clear()
    hotkey.start(CALLBACKS)
    pump(0.5)
    live = hotkey_x11.grabbed()
    check("5 the other three still grabbed", sorted(live.values())
          == ["Ctrl+Alt+D", "Ctrl+Alt+M", "Ctrl+Alt+Z"], live)
    warned = [m for m in log_lines if "Ctrl+Alt+B is taken" in m]
    check("5 warning for Ctrl+Alt+B only", len(warned) == 1, log_lines)
    got = press("ctrl+alt+z")
    check("5 Ctrl+Alt+Z works beside it", got == ["center"], got)
    # Reaching here at all: the BadAccess did not end the process (Xlib default handler).
    proc.wait()

    class Config:
        values = {"rhinospotter_hotkey_center": "Ctrl+Shift+F5"}

        def get_str(self, key, default=None):
            return self.values.get(key, default)

    hotkey.config = Config()
    hotkey.restart()
    pump(0.5)
    check("8 restart: new combo grabbed",
          hotkey_x11.grabbed().get(hotkey.CENTER) == "Ctrl+Shift+F5", hotkey_x11.grabbed())
    got = press("ctrl+shift+F5")
    check("8 restart: new combo fires", got == ["center"], got)
    got = press("ctrl+alt+z")
    check("8 restart: old combo dead", got == [], got)
    hotkey.stop()

    saved = os.environ.pop("DISPLAY")
    log_lines.clear()
    hotkey.start(CALLBACKS)
    os.environ["DISPLAY"] = saved
    check("1 no DISPLAY: no grab, no raise", not hotkey_x11.grabbed())
    check("1 no DISPLAY: chat fallback logged", any("type in chat" in m for m in log_lines),
          log_lines)
    hotkey.stop()
except Exception:
    out(traceback.format_exc())
    fails.append("exception")
finally:
    hotkey.stop()
    root.destroy()

out("\nlog:\n" + "".join(log_lines))
out(f"{len(fails)} failed" + (": " + ", ".join(fails) if fails else ""))
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"report: {os.path.join(OUT, 'report.txt')}")
sys.exit(1 if fails else 0)
