"""E2E harness for the data root off Windows. Checks and blind spots: datahome.md.

Run from the plugin folder:  python rs_e2etest/datahome_e2e.py
Writes rs_e2etest/out/<timestamp>-datahome/report.txt. Exit code 1 on a failure.
Every scenario is its own process; LOCALAPPDATA, XDG_DATA_HOME and USERPROFILE
point into the run folder. The live data is never opened.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S") + "-datahome")


def child():
    """`--child <action>`: one plugin start. Prints one JSON line."""
    import logging
    action = sys.argv[2]
    sys.path.insert(0, PLUGIN)
    handler = logging.FileHandler(os.environ["E2E_LOG"], encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logging.getLogger("RhinoSpotter").addHandler(handler)
    from rs_core import coverstore, database, migrate, spotcard
    out = {"root": database.ROOT, "path": database.PATH,
           "coverage": coverstore.ROOT, "cards": spotcard.CARDS_ROOT}
    if action == "start":                                 # rs_ui.main.start order
        out["adopted"] = database.adopt_legacy()
        migrate.run()
        with database.connect() as conn:
            out["bookmarks"] = [r[0] for r in conn.execute("SELECT system FROM bookmarks")]
    elif action == "api":                                 # a companion tool before EDMC
        import rs_api
        out["api"] = [b.get("system") for b in rs_api.bookmarks()]
        out["root_exists"] = os.path.exists(database.ROOT)
    elif action == "open":
        import webbrowser
        opened = []
        webbrowser.open = lambda url, *a, **k: opened.append(url) or True
        if hasattr(os, "startfile"):
            del os.startfile
        from rs_ui import minimap
        minimap._open_folder()
        out["opened"] = opened
    elif action == "click":
        import ctypes
        if hasattr(ctypes, "windll"):
            del ctypes.windll
        from rs_ui import overlay
        overlay._click_through(None)
    handler.close()
    print(json.dumps(out))


results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def run(name, action, local=None, xdg=None):
    """One start in scenario folder OUT/<name>. Returns (json, log text)."""
    home = os.path.join(OUT, name, "home")
    os.makedirs(home, exist_ok=True)
    log = os.path.join(OUT, name, f"{action}-{time.perf_counter_ns()}.log")
    env = {k: v for k, v in os.environ.items() if k not in ("LOCALAPPDATA", "XDG_DATA_HOME")}
    env.update(USERPROFILE=home, HOME=home, E2E_LOG=log, PYTHONIOENCODING="utf-8")
    if local:
        env["LOCALAPPDATA"] = local
    if xdg:
        env["XDG_DATA_HOME"] = xdg
    done = subprocess.run([sys.executable, __file__, "--child", action], capture_output=True,
                          text=True, env=env, timeout=60)
    if done.returncode:
        raise RuntimeError(f"{name}/{action}: {done.stderr[-800:]}")
    with open(log, encoding="utf-8") as handle:
        text = handle.read()
    return json.loads(done.stdout.strip().splitlines()[-1]), text


def legacy(name, systems):
    """~/RhinoSpotter as 5.7.12 left it off Windows: a db with bookmarks, a PNG."""
    sys.path.insert(0, PLUGIN)
    from rs_core import database
    root = os.path.join(OUT, name, "home", "RhinoSpotter")
    path = os.path.join(root, "db", "rhinospotter.db")
    with database.connect(path) as conn:
        for system in systems:
            database.write_bookmark(conn, {"system": system, "planet_name": f"{system} 1 a"})
    os.makedirs(os.path.join(root, "coverage", "Body 1 a"), exist_ok=True)
    with open(os.path.join(root, "coverage", "Body 1 a", "map 1.png"), "wb") as handle:
        handle.write(b"\x89PNG legacy")
    return root


def digest(root):
    sums = {}
    for folder, _, files in os.walk(root):
        for name in files:
            full = os.path.join(folder, name)
            with open(full, "rb") as handle:
                sums[os.path.relpath(full, root)] = hashlib.sha256(handle.read()).hexdigest()
    return sums


def under(path, root):
    return os.path.normcase(path).startswith(os.path.normcase(root) + os.sep)


def main():
    os.makedirs(OUT)
    # 1 Windows unchanged
    local = os.path.join(OUT, "win", "localappdata")
    a, _ = run("win", "roots", local=local)
    want = os.path.join(local, "RhinoSpotter")
    check("1 LOCALAPPDATA set: db, coverage, cards under %LOCALAPPDATA%\\RhinoSpotter",
          a["root"] == want and all(under(a[k], want) for k in ("path", "coverage", "cards")),
          a["root"])

    # 2 XDG_DATA_HOME
    xdg = os.path.join(OUT, "xdg", "flatpak-data")
    b, _ = run("xdg", "roots", xdg=xdg)
    want = os.path.join(xdg, "RhinoSpotter")
    check("2 no LOCALAPPDATA, XDG_DATA_HOME set: all under $XDG_DATA_HOME/RhinoSpotter",
          b["root"] == want and all(under(b[k], want) for k in ("path", "coverage", "cards")),
          b["root"])

    # 3 ~/.local/share
    c, _ = run("share", "roots")
    want = os.path.join(OUT, "share", "home", ".local", "share", "RhinoSpotter")
    check("3 no LOCALAPPDATA, no XDG_DATA_HOME: ~/.local/share/RhinoSpotter",
          c["root"] == want and under(c["path"], want), c["root"])

    # 4 legacy copied once
    old = legacy("copy", ["Legacy A"])
    before = digest(old)
    xdg = os.path.join(OUT, "copy", "xdg")
    d, log = run("copy", "start", xdg=xdg)
    new = os.path.join(xdg, "RhinoSpotter")
    check("4 old ~/RhinoSpotter copied: bookmark read from the new root",
          d["adopted"] == new and d["bookmarks"] == ["Legacy A"], f"{d['adopted']} {d['bookmarks']}")
    check("4 coverage PNG copied",
          os.path.isfile(os.path.join(new, "coverage", "Body 1 a", "map 1.png")))
    check("4 old folder byte-identical", digest(old) == before)
    check("4 one info line", log.count("INFO copied") == 1 and "WARNING" not in log, log.strip())

    # 5 second start: no copy
    legacy("copy", ["Legacy B"])
    e, log = run("copy", "start", xdg=xdg)
    check("5 new root present: no copy, later old bookmark not picked up",
          e["adopted"] is None and e["bookmarks"] == ["Legacy A"] and "copied" not in log,
          repr(e["bookmarks"]))

    # 6 LOCALAPPDATA wins, nothing copied
    legacy("win6", ["Legacy C"])
    local = os.path.join(OUT, "win6", "localappdata")
    f, _ = run("win6", "start", local=local)
    check("6 LOCALAPPDATA set, ~/RhinoSpotter present: nothing copied",
          f["adopted"] is None and f["bookmarks"] == [], repr(f["bookmarks"]))

    # 7 copy blocked, then retried
    legacy("fail", ["Legacy D"])
    xdg = os.path.join(OUT, "fail", "xdg")
    os.makedirs(xdg)
    block = os.path.join(xdg, "RhinoSpotter.tmp")
    with open(block, "w") as handle:
        handle.write("block")
    g, log = run("fail", "start", xdg=xdg)
    # migrate.run and connect() create the new root once adopt_legacy has given up,
    # so the check is: nothing copied, and warned.
    check("7 copy blocked: not copied, one warning",
          g["adopted"] is None and g["bookmarks"] == [] and log.count("WARNING could not copy") == 1,
          log.strip())
    os.remove(block)
    h, log = run("fail", "start", xdg=xdg)
    check("7 next start without the block: not retried, silent (new root exists)",
          h["adopted"] is None and h["bookmarks"] == [] and "copy" not in log, repr(h["bookmarks"]))

    # 10 rs_api read before the first plugin start
    legacy("api", ["Legacy E"])
    xdg = os.path.join(OUT, "api", "xdg")
    j, _ = run("api", "api", xdg=xdg)
    k, _ = run("api", "start", xdg=xdg)
    check("10 rs_api.bookmarks() before the first start: new root not created, then copied",
          j["api"] == [] and not j["root_exists"] and k["bookmarks"] == ["Legacy E"],
          f"api {j['api']} root_exists {j['root_exists']} start {k['bookmarks']}")

    # 8 open folder off Windows
    xdg = os.path.join(OUT, "open", "xdg")
    i, log = run("open", "open", xdg=xdg)
    want = "file:///" + os.path.join(xdg, "RhinoSpotter", "coverage").replace("\\", "/").lstrip("/")
    check("8 no os.startfile: file:// coverage root handed to webbrowser.open, no warning",
          i["opened"] == [want] and "WARNING" not in log, f"{i['opened']} {log.strip()}")

    # 9 click-through off Windows
    _, log = run("click", "click", xdg=os.path.join(OUT, "click", "xdg"))
    check("9 no ctypes.windll: _click_through logs no warning", "WARNING" not in log, log.strip())


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child()
        sys.exit(0)
    try:
        main()
    except Exception as err:                              # noqa: BLE001 - reported, exit 1
        check("harness ran", False, str(err))
    failed = [r for r in results if not r[1]]
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
        report.write(f"datahome E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
        for name, ok, detail in results:
            report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
    print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
    sys.exit(1 if failed else 0)
