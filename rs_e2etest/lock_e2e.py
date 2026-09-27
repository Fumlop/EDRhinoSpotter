"""E2E harness: one RhinoSpotter per data folder, plugin side. Checks and blind spots: lock.md.

Run from the plugin folder:  python rs_e2etest/lock_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
Every child runs with LOCALAPPDATA at the run folder; the live data is not opened.
"""

import glob
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")
LOCK = os.path.join(DATA, "RhinoSpotter", "db", "instance.lock")
os.makedirs(DATA)
ENV = dict(os.environ, LOCALAPPDATA=DATA)
PY = sys.executable
sys.stdout.reconfigure(encoding="utf-8")

# mode "hold": start, say HELD, wait for a line on stdin, stop.
# mode "panel": start, build panel and prefs, one journal line, stop, print what was seen.
PLUGIN_CHILD = r"""
import json, sys, time, types, tkinter as tk
sys.path.insert(0, {plugin!r})
sys.modules["myNotebook"] = tk            # EDMC's nb.Frame for plugin_prefs


class Config:
    # EDMC's config as far as the plugin reads it: every key unset.
    def get_str(self, key, default=None): return default
    def get_bool(self, key, default=False): return default
    def get_int(self, key, default=0): return default
    def get_list(self, key, default=None): return default if default is not None else []
    def set(self, key, value): pass
    def delete(self, key, suppress=False): pass


sys.modules["config"] = types.SimpleNamespace(config=Config())
import load
from rs_ui import hotkey, main
t0 = time.monotonic()
load.plugin_start3({plugin!r})
took = time.monotonic() - t0
if {mode!r} == "hold":
    print("HELD", flush=True)
    sys.stdin.readline()
    load.plugin_stop()
    sys.exit(0)
root = tk.Tk()
root.withdraw()
frame = load.plugin_app(root)
texts = [str(w.cget("text")) for w in frame.winfo_children() if isinstance(w, tk.Label)]
load.journal_entry("E2E", False, "Sol", None, {{"event": "FSDJump", "StarSystem": "Sol"}}, {{}})
prefs = load.plugin_prefs(root, "E2E", False)
prefs_texts = [str(w.cget("text")) for w in prefs.winfo_children() if "text" in w.keys()]
print(json.dumps({{"took": took, "refused": main.refused(), "texts": texts, "prefs": prefs_texts,
                   "prefs_frame": isinstance(prefs, tk.Frame), "frame": main._frame is not None,
                   "hotkey_thread": getattr(hotkey, "_thread", None) is not None,
                   "system": main._system}}), flush=True)
load.plugin_stop()
"""

HOLDER_CHILD = r"""
import sys
sys.path.insert(0, {plugin!r})
from rs_core import instance
print("HELD" if instance.acquire("RhinoSpotter standalone") is None else "REFUSED", flush=True)
sys.stdin.readline()
"""

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def spawn(code, stdin=False):
    return subprocess.Popen([PY, "-c", code], env=ENV, cwd=PLUGIN, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.PIPE if stdin else None)


def holder(mode="plugin"):
    code = (PLUGIN_CHILD.format(plugin=PLUGIN, mode="hold") if mode == "plugin"
            else HOLDER_CHILD.format(plugin=PLUGIN))
    child = spawn(code, stdin=True)
    return child, child.stdout.readline().strip()


def panel():
    child = spawn(PLUGIN_CHILD.format(plugin=PLUGIN, mode="panel"))
    out, err = child.communicate(timeout=90)
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": err[-400:]}


def release(child):
    child.stdin.write("\n")
    child.stdin.flush()
    return child.wait(20)


def lock_text():
    try:
        with open(LOCK, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def backups():
    return glob.glob(os.path.join(DATA, "RhinoSpotter", "db", "backups", "*.db"))


try:
    os.environ["LOCALAPPDATA"] = DATA          # before rs_core loads: never the live folder
    sys.path.insert(0, PLUGIN)
    from rs_ui import main as main_module
    wait_s = main_module.LOCK_WAIT_S

    # 1. first plugin
    first, said = holder("plugin")
    check("1 first plugin holds the lock, file names it",
          said == "HELD" and "the EDMC plugin" in lock_text(), f"{said} {lock_text()!r}")

    # 2. second plugin while the first runs: waits LOCK_WAIT_S, then refused
    seen = panel()
    check("2 second plugin refused after ~LOCK_WAIT_S",
          seen.get("refused") and "the EDMC plugin" in seen["refused"]
          and wait_s - 0.5 <= seen.get("took", 0) <= wait_s + 3, f"{seen.get('took')} s, {seen.get('refused')}")
    check("2 refusal line in the panel", any("the EDMC plugin" in t for t in seen.get("texts", [])),
          seen.get("texts") or seen.get("error"))
    check("2 prefs is a Frame carrying the refusal",
          seen.get("prefs_frame") and any("the EDMC plugin" in t for t in seen.get("prefs", [])),
          seen.get("prefs"))

    # 3. the first stops while the second waits: the second takes it
    second = spawn(PLUGIN_CHILD.format(plugin=PLUGIN, mode="panel"))
    time.sleep(1.5)
    release(first)
    out, err = second.communicate(timeout=90)
    try:
        seen = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        seen = {"error": err[-400:]}
    check("3 first stops within LOCK_WAIT_S: the waiting plugin starts",
          seen.get("refused") is None and seen.get("frame") is True,
          seen.get("refused") or seen.get("error"))

    # 4. standalone holder: refused at once, nothing done
    before = backups()
    other, said = holder("standalone")
    check("setup: standalone stand-in holds the lock", said == "HELD", said)
    seen = panel()
    check("4 standalone holder: plugin refused in under 2 s, naming it",
          seen.get("refused") and "RhinoSpotter standalone" in seen["refused"]
          and seen.get("took", 99) < 2, f"{seen.get('took')} s, {seen.get('refused')}")
    check("4 no panel state, no hotkeys, journal ignored",
          not seen.get("frame") and not seen.get("hotkey_thread") and seen.get("system") == "", seen)
    check("4 no backup written", backups() == before, backups())

    # 5. killed holder
    other.kill()
    other.wait(10)
    seen = panel()
    check("5 killed holder: a new plugin takes the lock",
          seen.get("refused") is None and seen.get("frame") is True,
          seen.get("refused") or seen.get("error"))

    # 6. plugin_stop released it
    probe = spawn(HOLDER_CHILD.format(plugin=PLUGIN), stdin=True)
    said = probe.stdout.readline().strip()
    release(probe)
    check("6 after plugin_stop the lock is free", said == "HELD", said)
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())

failed = [r for r in results if not r[1]]
lines = [f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines.append(f"\n{len(results) - len(failed)}/{len(results)} passed")
report = "\n".join(lines)
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write(report + "\n")
print(report)
print(OUT)
sys.exit(1 if failed else 0)
