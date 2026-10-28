"""E2E harness: no home folder and no foreground window title in the plugin log. Checks and blind spots: logpaths.md.

Run from the plugin folder:  python rs_e2etest/logpaths_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.

The child's LOCALAPPDATA is the run folder, set before the interpreter starts,
so the live database is never opened.
"""

import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)


def child():
    import ctypes
    import logging
    import tkinter as tk
    sys.path.insert(0, PLUGIN)
    log_path = os.environ["E2E_LOG"]
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logging.getLogger("RhinoSpotter").addHandler(handler)

    from rs_core import coverage, coverstore, database, paths
    from rs_core.logging import logger
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    scratch = os.environ["LOCALAPPDATA"]
    home = os.path.expanduser("~")
    assert scratch.lower().startswith(home.lower()), f"run folder {scratch} not under {home}"
    paths.journal_dir = lambda: scratch
    coverage.clear_old_textures = lambda: None

    # 1: instance line at start
    import load
    load.plugin_start3(PLUGIN)
    from rs_ui import main, minimap, overlay, scan
    root = tk.Tk()
    root.withdraw()
    main.build(root)
    main._cancel_landed()

    # 2: OSError text with the path in it
    blocker = os.path.join(scratch, "not_a_folder")
    with open(blocker, "w") as handle:
        handle.write("x")
    from PIL import Image
    saved = coverstore.save_png("Aramo A 1", "map", Image.new("RGB", (4, 4)), root=blocker)

    # 3: traceback through rs_ui/main.py
    def broken(*_, **__):
        raise RuntimeError(f"scan window could not open {scratch}")
    scan.show = broken
    main.open_scan()

    # 5, 6: slash form and upper case
    logger.warning(f"slash form {home.replace(chr(92), '/')}/x")
    logger.warning(f"upper case {home.upper()}\\x")

    # 7: Elite not in front
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(ctypes.windll.user32.GetForegroundWindow(), buffer, 256)
    front = buffer.value
    focused = overlay.game_focused()
    if not focused:                        # with Elite in front _show_map draws; check 7 fails on the premise
        minimap._show_map(root, {}, "Aramo", 0.0, 0.0, 0, True, "Aramo A 1")
    root.destroy()
    handler.flush()

    with open(log_path, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines()
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    def having(part):
        return [line for line in lines if part in line]

    check("8 plugin.log has lines", len(lines) >= 5, f"{len(lines)} lines")
    account = os.path.basename(home)
    leak = re.compile(r"users[\\/]+" + re.escape(account), re.IGNORECASE)
    hits = [line for line in lines if leak.search(line)]
    check("no line contains Users<sep(s)><account>, any slash form or count", not hits, " | ".join(hits[:3]))
    check("1 instance line kept, with ~", any("~" in l for l in having("instance:") if "holds" in l),
          " | ".join(having("instance:")))
    check("2 save_png returned None (premise)", saved is None, repr(saved))
    check("2 OSError line kept, with ~", any("~" in l for l in having("could not save the picture")),
          " | ".join(having("could not save the picture")))
    tb = text[text.find("RhinoData failed"):] if "RhinoData failed" in text else ""
    check("3 traceback kept", "Traceback" in tb and "main.py" in tb, tb[:200])
    check("3 traceback frames with ~", "~" in tb.split("RuntimeError")[0], tb[:300])
    check("5 slash form scrubbed", any(l.endswith("slash form ~/x") for l in lines),
          " | ".join(having("slash form")))
    check("6 upper case scrubbed", any(l.endswith("upper case ~\\x") for l in lines),
          " | ".join(having("upper case")))
    check("7 premise: Elite not in front", not focused, f"front window {front!r}")
    down = having("minimap: down")
    check("7 down line is exactly 'Elite not in front'",
          down and down[-1] == "INFO minimap: down, Elite not in front", " | ".join(down))
    check("7 foreground title not in log", not front or front not in text, repr(front))

    print("--- plugin.log ---")
    print(text)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"  [{detail}]"))
    return 0 if results and all(ok for _, ok, _ in results) else 1


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=out, E2E_LOG=os.path.join(out, "plugin.log"),
               PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"],
                         cwd=PLUGIN, env=env, capture_output=True, text=True, encoding="utf-8")
    report = run.stdout + (f"\n--- stderr ---\n{run.stderr}" if run.stderr else "")
    report += f"\nresult: {'PASS' if run.returncode == 0 else 'FAIL'}\n"
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    print(out)
    return run.returncode


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    raise SystemExit(main())
