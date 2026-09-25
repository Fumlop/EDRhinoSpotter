"""E2E harness for first-letter jumps in the material menus. Checks and blind
spots: letters.md.

Run from the plugin folder:  python rs_e2etest/letters_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
Opens real menus and sends keys: leave the keyboard alone for ~15 s.
"""

import ctypes
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
VK_RETURN, VK_ESCAPE, KEYUP = 0x0D, 0x1B, 0x2


def _key(vk):
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYUP, 0)


def child():
    sys.path.insert(0, PLUGIN)
    import json
    import tkinter as tk
    from rs_core import coverage, database
    from rs_ui import main, scan
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    coverage.clear_old_textures = lambda: None
    main.start(PLUGIN)
    root = tk.Tk()
    root.geometry("+200+200")
    main.build(root)
    main._cancel_landed()
    fails = []

    def check(name, ok, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            fails.append(f"{name} {detail}")

    def labels(option_menu):
        menu = option_menu["menu"]
        return [str(menu.entrycget(i, "label")) for i in range(menu.index("end") + 1)]

    def marked(option_menu, skip=()):
        """Every entry starting with a letter or digit carries underline 0, the
        skipped ones none."""
        menu = option_menu["menu"]
        return all((int(menu.entrycget(i, "underline")) == 0) == (label not in skip)
                   for i, label in enumerate(labels(option_menu)) if label[:1].isalnum())

    def typed(option_menu, variable, keys, start):
        """Open the menu for real, send `keys` (virtual-key codes), return the pick."""
        variable.set(start)
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update()

        def send():
            time.sleep(0.5)
            for vk in keys:
                _key(vk)
                time.sleep(0.25)
        threading.Thread(target=send, daemon=True).start()
        menu = option_menu["menu"]
        menu.tk_popup(option_menu.winfo_rootx(), option_menu.winfo_rooty())
        menu.grab_release()
        root.update()
        time.sleep(0.3)
        root.update()
        return variable.get()

    def interactive(tag, option_menu, variable, skip=()):
        start = labels(option_menu)[0]
        names = [n for n in labels(option_menu) if n[:1].isalpha() and n not in skip]
        firsts = {}
        for n in names:
            firsts.setdefault(n[0].upper(), []).append(n)
        # The first match must differ from the start value, or a dead key passes.
        shared = next((l for l, ns in firsts.items() if len(ns) > 1 and ns[0] != start), None)
        single = next((l for l, ns in firsts.items() if len(ns) == 1 and ns[0] != start), None)
        absent = next(l for l in "QXZJYWVUK" if l not in firsts)
        check(f"{tag}: a shared and a single letter to type", bool(shared and single),
              f"{shared!r}, {single!r}")
        if shared:
            got = typed(option_menu, variable, [ord(shared), VK_RETURN], start)
            check(f"{tag}: '{shared}' ({len(firsts[shared])} entries) + Enter -> first",
                  got == firsts[shared][0], f"{got!r}, want {firsts[shared][0]!r}")
        if single:
            got = typed(option_menu, variable, [ord(single), VK_ESCAPE], start)
            check(f"{tag}: '{single}' (1 entry) picks at once", got == firsts[single][0],
                  f"{got!r}, want {firsts[single][0]!r}")
        got = typed(option_menu, variable, [ord(absent), VK_ESCAPE], start)
        check(f"{tag}: '{absent}' (no entry) changes nothing", got == start, repr(got))

    print("panel Material")
    skip = (main.NO_MATERIAL,)
    check("panel: every entry lettered, placeholder not", marked(main._menu, skip))
    print("  entries: " + ", ".join(labels(main._menu)))
    interactive("panel", main._menu, main._material, skip)
    main._fill_menu()
    check("panel: lettered after _fill_menu (Settings refill)", marked(main._menu, skip))

    print("RhinoData filter")
    frame = tk.Frame(root)
    frame.pack()
    variable = tk.StringVar(value=main.ALL_MATERIALS)
    scan._picker(frame, variable, (main.ALL_MATERIALS,) + main._materials(), None)
    picker = next(w for w in frame.winfo_children()[0].winfo_children()
                  if isinstance(w, tk.OptionMenu))
    check("filter: every entry lettered", marked(picker))
    interactive("filter", picker, variable)

    print("Edit dialog Material")
    with database.connect() as conn:
        record = json.loads(conn.execute("SELECT data FROM bookmarks LIMIT 1").fetchone()[0])
    scan._window = tk.Toplevel(root)

    def in_dialog():
        box = next(w for w in scan._window.winfo_children()
                   if isinstance(w, tk.Toplevel) and w.title() == "Edit bookmark")
        picker = next(w for w in box.winfo_children() if isinstance(w, tk.OptionMenu))
        check("edit: every entry lettered", marked(picker))
        box.destroy()
    root.after(300, in_dialog)
    scan._edit_bookmark(record)
    scan._window.destroy()
    root.destroy()

    print(f"\nfails {len(fails)}")
    for line in fails:
        print("FAIL " + line)
    return 1 if fails else 0


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    live = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
    copy = os.path.join(out, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(copy))
    with sqlite3.connect(f"file:{live}?mode=ro", uri=True) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
    env = dict(os.environ, LOCALAPPDATA=out, PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child"], cwd=PLUGIN,
                         env=env, capture_output=True, text=True, encoding="utf-8")
    report = run.stdout.splitlines()
    if run.stderr.strip():
        report.append(run.stderr.strip())
    report.append(f"\nresult: {'PASS' if run.returncode == 0 else 'FAIL'}")
    text = "\n".join(report)
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text)
    print(out)
    return run.returncode


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child())
    raise SystemExit(main())
