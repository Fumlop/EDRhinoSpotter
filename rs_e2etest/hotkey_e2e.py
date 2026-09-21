"""E2E harness for rs_ui/hotkey.py. Checks and blind spots: hotkey.md.

Run from the plugin folder:  python rs_e2etest/hotkey_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads.
Registers Ctrl+Alt+Z/B/M/D and briefly every combo Settings offers, system-wide.
SendInput is used only for the four Ctrl+Alt defaults, only while they are
held by the module and a window of this process is foreground.
"""

import logging
import os
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")

os.makedirs(DATA)
live_before = os.stat(LIVE_DB) if os.path.exists(LIVE_DB) else None
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import ctypes                                            # noqa: E402
import tkinter as tk                                     # noqa: E402
from ctypes import wintypes                              # noqa: E402

from rs_core import database                             # noqa: E402
from rs_ui import hotkey, main                           # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

log_lines = []
handler = logging.StreamHandler(type("W", (), {"write": lambda s, m: log_lines.append(m),
                                                "flush": lambda s: None})())
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
hotkey.logger.addHandler(handler)
hotkey.logger.setLevel(logging.DEBUG)

u = ctypes.WinDLL("user32", use_last_error=True)
u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
u.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
u.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u.GetForegroundWindow.restype = wintypes.HWND
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.SetForegroundWindow.argtypes = [wintypes.HWND]
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND

ERROR_HOTKEY_ALREADY_REGISTERED = 1409
PROBE_ID = 0xB000

# Win32 virtual-key codes, from WinUser.h, independent of hotkey.parse().
VK = {**{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
      **{f"F{n}": 0x6F + n for n in range(1, 13)}}
MODS = {"Ctrl": 0x0002, "Alt": 0x0001, "Shift": 0x0004}


def win32(combo):
    """'Ctrl+Alt+Z' -> (flags, vk) from WinUser.h constants."""
    *mods, key = combo.split("+")
    flags = 0
    for m in mods:
        flags |= MODS[m]
    return flags, VK[key]


class Config:
    """EDMC's config as far as hotkey reads it."""

    def __init__(self):
        self.values = {}

    def get_str(self, key, default=None):
        return self.values.get(key, default)


results = []
errors = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def probe(combo):
    """RegisterHotKey for `combo` from a new thread, released at once.
    Returns 0 when it was free, else the Win32 error (1409: held)."""
    flags, vk = win32(combo)
    out = []

    def run():
        if u.RegisterHotKey(None, PROBE_ID, flags, vk):
            u.UnregisterHotKey(None, PROBE_ID)
            out.append(0)
        else:
            out.append(ctypes.get_last_error())
    t = threading.Thread(target=run)
    t.start()
    t.join()
    return out[0]


def held(combo):
    return probe(combo) == ERROR_HOTKEY_ALREADY_REGISTERED


def pump(until=lambda: False, seconds=2.0):
    """Wait on the driver thread while the mainloop runs; True once `until()` holds."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if until():
            return True
        time.sleep(0.01)
    return until()


fired = []          # (key_id, thread name of the callback, thread ident of the Tk function)


def callbacks(ids=(hotkey.CENTER, hotkey.BORDER, hotkey.SIZE, hotkey.SCAN)):
    """As rs_ui/main.py builds them: the hotkey thread calls main._on_ui."""
    def make(key_id):
        def on_hotkey_thread():
            name = threading.current_thread().name
            main._on_ui(lambda: fired.append((key_id, name, threading.get_ident())))
        return on_hotkey_thread
    return {k: make(k) for k in ids}


def post(key_id):
    return u.PostThreadMessageW(hotkey._thread_id or 0, hotkey.WM_HOTKEY, key_id, 0)


def delivered(key_id):
    return pump(lambda: any(f[0] == key_id for f in fired))


def warned(combo):
    return any("taken" in line and combo in line for line in log_lines)


def defaults():
    return {kid: default for kid, _, default, _ in hotkey.ACTIONS}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_ctrl_alt(vk):
    """SendInput Ctrl down, Alt down, vk down, vk up, Alt up, Ctrl up. Returns events sent."""
    seq = [(0x11, 0), (0x12, 0), (vk, 0), (vk, 2), (0x12, 2), (0x11, 2)]
    arr = (INPUT * len(seq))()
    for i, (key, flags) in enumerate(seq):
        arr[i].type = 1
        arr[i].ki = KEYBDINPUT(key, 0, flags, 0, 0)
    return u.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def foreground_is_ours():
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid(), pid.value


root = tk.Tk()
root.title("RhinoSpotter hotkey E2E")
root.geometry("420x80+200+200")
tk.Label(root, text="hotkey E2E running: SendInput Ctrl+Alt+Z/B/M/D").pack(expand=True)
root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
main._frame = root
hotkey.config = Config()
tk_ident = threading.get_ident()
blocker = None
send_mode = "not run"


def body():
    """The checks, off the Tk thread: main._on_ui needs the mainloop running, as in EDMC."""
    global blocker, send_mode
    try:
        free_before = {c: probe(c) for c in defaults().values()}
        check("0 defaults free before start (premise)", all(v == 0 for v in free_before.values()),
              str(free_before))

        # 1. Defaults held after start().
        hotkey.start(callbacks())
        tid1 = hotkey._thread_id
        check("1 thread alive with a thread id", hotkey._thread is not None and hotkey._thread.is_alive() and tid1,
              f"tid {tid1}")
        for kid, combo in defaults().items():
            check(f"1 {combo} held after start", held(combo), f"probe error {probe(combo)}")

        # 2. WM_HOTKEY posted to the module's thread: callback on the hotkey thread, function on Tk.
        for kid, combo in defaults().items():
            fired.clear()
            ok = post(kid)
            got = delivered(kid)
            f = next((f for f in fired if f[0] == kid), None)
            check(f"2 posted WM_HOTKEY {combo}: fired", ok and got, f"post {ok}")
            check(f"2 {combo}: callback on rhinospotter-hotkey, function on the Tk thread",
                  f and f[1] == "rhinospotter-hotkey" and f[2] == tk_ident, str(f))
        fired.clear()
        post(0x1234)
        check("2 unknown hotkey id ignored", not pump(lambda: bool(fired), 0.3) and hotkey._thread.is_alive())

        # 3. Real key press through SendInput, only with a window of ours in front.
        root.deiconify()
        root.lift()
        root.focus_force()
        u.SetForegroundWindow(u.GetParent(root.winfo_id()) or root.winfo_id())
        pump(seconds=0.5)
        ours, fg_pid = foreground_is_ours()
        if not ours:
            check("3 SendInput: a window of this process is foreground (premise)", False,
                  f"foreground pid {fg_pid}; SendInput not run")
        else:
            send_mode = "SendInput"
            for kid, combo in defaults().items():
                if not held(combo):
                    check(f"3 SendInput {combo}", False, "not held by the module; not sent")
                    continue
                fired.clear()
                n = send_ctrl_alt(win32(combo)[1])
                check(f"3 SendInput {combo}: WM_HOTKEY reached the callback and Tk", n == 6 and delivered(kid),
                      f"sent {n}/6, err {ctypes.get_last_error() if n != 6 else 0}")
        root.withdraw()

        # 4. A callback that raises: logged, the loop keeps going.
        hotkey.stop()
        boom = callbacks()
        boom[hotkey.CENTER] = lambda: 1 / 0
        hotkey.start(boom)
        fired.clear()
        post(hotkey.CENTER)
        post(hotkey.BORDER)
        check("4 after a raising callback the next key still fires", delivered(hotkey.BORDER))
        check("4 the exception is logged", any("could not be handed on" in line and "ZeroDivisionError" in line
                                               for line in log_lines))

        # 5. start() twice: one thread.
        before = hotkey._thread
        hotkey.start(callbacks())
        alive = [t for t in threading.enumerate() if t.name == "rhinospotter-hotkey"]
        check("5 second start() ignored: same thread, one listener", hotkey._thread is before and len(alive) == 1,
              f"{len(alive)} threads")

        # 6. stop(): all free, thread ended.
        thread = hotkey._thread
        hotkey.stop()
        check("6 stop(): thread ended", not thread.is_alive())
        for combo in defaults().values():
            check(f"6 {combo} free after stop (RegisterHotKey from a second thread succeeds)",
                  probe(combo) == 0, f"probe error {probe(combo)}")
        check("6 stop() twice is harmless", hotkey.stop() is None)

        # 7. restart() with new combos in config.
        new = {hotkey.CENTER: "Ctrl+Alt+Shift+F9", hotkey.BORDER: "Ctrl+Alt+Shift+F10",
               hotkey.SIZE: "Ctrl+Alt+Shift+F11", hotkey.SCAN: "Ctrl+Alt+Shift+F12"}
        check("7 new combos free before (premise)", all(probe(c) == 0 for c in new.values()))
        hotkey.start(callbacks())
        tid_old = hotkey._thread_id
        cfg_keys = {kid: ck for kid, _, _, ck in hotkey.ACTIONS}
        for kid, combo in new.items():
            hotkey.config.values[cfg_keys[kid]] = combo
        hotkey.restart()
        check("7 restart(): a new listening thread", hotkey._thread_id and hotkey._thread_id != tid_old,
              f"{tid_old} -> {hotkey._thread_id}")
        for kid, combo in new.items():
            check(f"7 {combo} held after restart", held(combo), f"probe error {probe(combo)}")
            check(f"7 label() says {combo}", hotkey.label(kid) == combo, hotkey.label(kid))
        for combo in defaults().values():
            check(f"7 old {combo} released by restart", probe(combo) == 0)
        fired.clear()
        post(hotkey.SIZE)
        check("7 dispatch after restart", delivered(hotkey.SIZE))
        hotkey.config.values.clear()

        # 8. Stored combos Settings could not offer: default taken.
        for bad in ("", "Z", "Alt+Z", "Ctrl+Alt+", "Ctrl+Alt+F13", "Win+Alt+Z", "Ctrl+Alt+ZZ", "nonsense"):
            hotkey.config.values[cfg_keys[hotkey.CENTER]] = bad
            hotkey.restart()
            check(f"8 stored {bad!r}: label falls back, Ctrl+Alt+Z held",
                  hotkey.label(hotkey.CENTER) == "Ctrl+Alt+Z" and held("Ctrl+Alt+Z"),
                  hotkey.label(hotkey.CENTER))
        hotkey.config.values.clear()
        hotkey.stop()

        # 9. Every combo Settings offers, bound to CENTER alone: held with the WinUser.h vk, or warned.
        held_n, taken, wrong = 0, [], []
        for mods in hotkey.MODIFIER_SETS:
            for key in hotkey.KEY_NAMES:
                combo = f"{mods}+{key}"
                hotkey.config.values[cfg_keys[hotkey.CENTER]] = combo
                log_mark = len(log_lines)
                hotkey.start(callbacks((hotkey.CENTER,)))
                ours = bool(hotkey._thread_id) and held(combo)
                if ours:
                    held_n += 1
                elif any("taken" in line and combo in line for line in log_lines[log_mark:]):
                    taken.append(combo)
                else:
                    wrong.append(combo)
                hotkey.stop()
                if ours and probe(combo) != 0:
                    wrong.append(combo + " (still held after stop)")
        total = len(hotkey.MODIFIER_SETS) * len(hotkey.KEY_NAMES)
        check(f"9 all {total} offered combos: held by the module or reported taken",
              not wrong and held_n + len(taken) == total,
              f"held {held_n}, taken elsewhere {len(taken)} {taken[:12]}, wrong {wrong[:12]}")
        hotkey.config.values.clear()

        # 10. A combo held by another process.
        other = "Ctrl+Alt+Shift+F8"
        flags, vk = win32(other)
        blocker = subprocess.Popen(
            [sys.executable, "-c",
             "import ctypes,sys\n"
             f"ok=ctypes.windll.user32.RegisterHotKey(None,1,{flags},{vk})\n"
             "print('held' if ok else 'fail', flush=True)\nsys.stdin.read()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        first = blocker.stdout.readline().strip()
        check(f"10 child process holds {other} (premise)", first == "held" and held(other), first)
        hotkey.config.values[cfg_keys[hotkey.BORDER]] = other
        raised = None
        try:
            hotkey.start(callbacks())
        except Exception as err:
            raised = err
        check("10 start() with a taken combo does not raise", raised is None, repr(raised))
        check(f"10 {other} reported as a warning", warned(other))
        for kid in (hotkey.CENTER, hotkey.SIZE, hotkey.SCAN):
            check(f"10 {defaults()[kid]} still held", held(defaults()[kid]))
        fired.clear()
        post(hotkey.CENTER)
        check("10 the other keys still dispatch", delivered(hotkey.CENTER))
        hotkey.stop()
        blocker.stdin.close()
        blocker.wait(5)
        hotkey.config.values.clear()

        # 11. Two actions on one combo.
        same = "Ctrl+Alt+Shift+F9"
        hotkey.config.values[cfg_keys[hotkey.CENTER]] = same
        hotkey.config.values[cfg_keys[hotkey.BORDER]] = same
        log_mark = len(log_lines)
        hotkey.start(callbacks())
        check(f"11 two actions on {same}: one holds it", held(same))
        check("11 the second is reported", any("taken" in line and same in line for line in log_lines[log_mark:]))
        hotkey.stop()
        hotkey.config.values.clear()

        pump(seconds=0.2)
        check("12 no Tk callback exceptions", not errors, errors[0][-300:] if errors else "")
    except Exception:
        errors.append(traceback.format_exc())
        check("harness ran to the end", False, errors[-1][-300:])
    finally:
        try:
            hotkey.stop()
            if blocker and blocker.poll() is None:
                blocker.kill()
            root.after(0, root.quit)
        except Exception as err:
            errors.append(f"teardown: {err}")


threading.Thread(target=body, name="e2e-driver", daemon=True).start()
root.mainloop()
root.destroy()

for combo in defaults().values():
    check(f"12 {combo} free at exit", probe(combo) == 0)
if live_before is not None:
    live_after = os.stat(LIVE_DB)
    check("12 live db untouched (size, mtime)",
          (live_before.st_size, live_before.st_mtime_ns) == (live_after.st_size, live_after.st_mtime_ns))
check("12 harness db path is the run folder", database.PATH.startswith(DATA), database.PATH)

failed = [r for r in results if not r[1]]
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"hotkey E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.write(f"delivery: PostThreadMessageW(WM_HOTKEY) to hotkey._thread_id; real press: {send_mode}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
    report.write("\n--- plugin log ---\n" + "".join(log_lines))
    if errors:
        report.write("\n--- errors ---\n" + "\n".join(errors))
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
