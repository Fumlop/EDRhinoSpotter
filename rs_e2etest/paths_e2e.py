"""E2E harness for finding the journal folder. Checks: paths.md.

Run from the plugin folder:  python rs_e2etest/paths_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
Every scenario is its own process; LOCALAPPDATA points at the run folder.
"""

import json
import os
import subprocess
import sys
import time
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
MOVED = os.path.join(OUT, "D-Games", "Saved Games", "Frontier Developments", "Elite Dangerous")
OTHER = os.path.join(OUT, "E-Other", "Elite Dangerous")
TYPED = os.path.join(OUT, "F-Typed", "Elite Dangerous")

# Run inside the child: fake EDMC modules, then the plugin's own imports.
CHILD = r"""
import json, os, sys, types
sys.path.insert(0, {plugin!r})
monitor = types.ModuleType("monitor")
monitor.monitor = types.SimpleNamespace(currentdir=None)          # not started yet
config = types.ModuleType("config")
settings = {{"journaldir": {typed!r}}}
config.config = types.SimpleNamespace(get_str=lambda key, default=None: settings.get(key, default),
                                      default_journal_dir={moved!r})
config.appname = "EDMarketConnector"
if {edmc!r}:
    sys.modules["monitor"], sys.modules["config"] = monitor, config
from rs_core import paths, replay, spotmark                      # what load.py pulls in
out = {{"first": spotmark.read_status().get("BodyName"), "dir": paths.journal_dir(),
       "journals": [os.path.basename(p) for p in replay.journal_files()]}}
if {edmc!r}:
    monitor.monitor.currentdir = {other!r}                        # the monitor starts
    out["after_start"] = spotmark.read_status().get("BodyName")
    monitor.monitor.currentdir = {moved!r}                        # changed later: kept answer
    out["after_change"] = spotmark.read_status().get("BodyName")
    import time
    n = 20000
    start = time.perf_counter()
    for _ in range(n):
        paths.journal_dir()
    out["us"] = (time.perf_counter() - start) / n * 1e6
out["saved_games"] = paths._saved_games()
print(json.dumps(out))
"""

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def run(edmc=True, typed=""):
    code = CHILD.format(plugin=PLUGIN, moved=MOVED, other=OTHER, typed=typed, edmc=edmc)
    env = dict(os.environ, LOCALAPPDATA=os.path.join(OUT, "localappdata"))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                          timeout=60)
    if done.returncode:
        raise RuntimeError(done.stderr[-800:])
    return json.loads(done.stdout.strip().splitlines()[-1])


def status(folder, body):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "Status.json"), "w", encoding="utf-8") as handle:
        json.dump({"event": "Status", "Flags": 0x4000000, "BodyName": body}, handle)


def registry_saved_games():
    """Where Explorer has Saved Games. The value is only written once the
    folder has been moved; without it the folder is the default one."""
    key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, _ = winreg.QueryValueEx(handle, "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}")
    except FileNotFoundError:
        value = r"%USERPROFILE%\Saved Games"
    return os.path.normcase(os.path.expandvars(value))


status(MOVED, "Moved 1 a")
status(OTHER, "Other 2 b")
status(TYPED, "Typed 3 c")
with open(os.path.join(MOVED, "Journal.2026-09-21T120000.01.log"), "w", encoding="utf-8") as handle:
    handle.write('{"timestamp":"2026-09-21T12:00:00Z","event":"Fileheader"}\n')

try:
    a = run(edmc=True)
    check("1 monitor not started: Status.json from EDMC's default (moved) folder",
          a["first"] == "Moved 1 a", f"read {a['first']!r} from {a['dir']}")
    check("2 monitor started on another folder: next read follows it",
          a["after_start"] == "Other 2 b", repr(a["after_start"]))
    check("7 looked up once a start: a later change of the monitor's folder is not read",
          a["after_change"] == "Other 2 b", repr(a["after_change"]))
    check("5 replay.journal_files() without a root finds the moved journal",
          a["journals"] == ["Journal.2026-09-21T120000.01.log"], repr(a["journals"]))
    check("6 journal_dir() with the monitor started: under 5 us",
          a["us"] < 5, f"{a['us']:.2f} us")

    b = run(edmc=True, typed=TYPED)
    check("3 journaldir typed in EDMC's settings wins over the default",
          b["first"] == "Typed 3 c", repr(b["first"]))

    c = run(edmc=False)
    want = os.path.normcase(os.path.join(registry_saved_games(), "Frontier Developments",
                                         "Elite Dangerous"))
    check("4 outside EDMC: the Saved Games known folder answered (not the fallback)",
          c["saved_games"] is not None
          and os.path.normcase(c["saved_games"]) == registry_saved_games(), repr(c["saved_games"]))
    check("4 outside EDMC: journal folder below it",
          os.path.normcase(c["dir"]) == want, f"{c['dir']} vs {want}")
except Exception as err:                                  # noqa: BLE001 - reported, exit 1
    check("harness ran", False, str(err))

failed = [r for r in results if not r[1]]
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"paths E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
