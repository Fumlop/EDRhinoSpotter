"""E2E harness for Share bookmark and the clipboard import. Checks and blind
spots: share.md.

Run from the plugin folder:  python rs_e2etest/share_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.

Two children, A (shares) and B (imports), each with LOCALAPPDATA set to its own
folder before the interpreter starts. They talk only through the real Windows
clipboard, which the parent saves first and puts back at the end.
"""

import base64
import json
import os
import subprocess
import sys
import time
import zlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)

SYSTEM = "Hyperion Reach AB-C d1-42"
BODY = f"{SYSTEM} 4 a"
SPOT = {"system": SYSTEM, "planet_name": BODY, "system_address": 123456789, "body_id": 14,
        "planet_radius": 1352744.5, "latitude": 12.401233, "longitude": -98.712001,
        "heading": 77, "altitude": 3, "location_index": 9, "commodity": "Monazite",
        "rigs": 2, "amount": "Low", "density": "Medium", "commander": "CMDR Private",
        "marked_at": "2026-09-24T10:00:00+00:00",
        "yield": {"cycles": [{"from": "x", "tons": {"Monazite": 12}}]}}


# ----------------------------------------------------------------- the children


def _boot():
    sys.path.insert(0, PLUGIN)
    import tkinter as tk
    from rs_core import coverage, database
    from rs_ui import main
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    coverage.clear_old_textures = lambda: None
    main.start(PLUGIN)
    root = tk.Tk()
    root.withdraw()
    main.build(root)
    main._cancel_landed()           # the poll is driven by hand here
    return tk, root, main


def _rows():
    from rs_core import database
    with database.connect() as conn:
        return [json.loads(data) for (data,) in conn.execute("SELECT data FROM bookmarks")]


def child_a(results):
    tk, root, main = _boot()
    from rs_core import bodies, share, spotcard
    from rs_ui import scan

    def check(name, got, want):
        results.append((name, got == want, f"{got!r} != {want!r}"))

    spotcard.save(dict(SPOT))
    register = bodies.Register()
    register.adopt(SYSTEM, [{"name": BODY, "ground": "rock 80%+ [silicate vapour geysers]",
                             "distance": 1284.0, "locations": 22, "volcanism": "",
                             "planet_class": "Rocky body"}])
    # Opened at the bookmark's location, as from the panel: every other one is folded.
    window = scan.show(root, register, main._sheet, None, variable=tk.StringVar(),
                       materials=("All",), here=BODY, location=SPOT["location_index"])
    window.geometry("+-4000+-4000")         # mapped, so grid sizes are real, not on screen
    scan._state["body"] = BODY
    scan._draw()
    for _ in range(20):
        root.update()

    buttons = {}
    stack = [window]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if isinstance(widget, tk.Button):
            buttons[str(widget.cget("text"))] = widget
    four = ("Share bookmark", "Mark depleted", "Copy coords", "Delete")
    check("9 the four buttons under Guide exist", all(name in buttons for name in four), True)
    widths = sorted({buttons[name].winfo_width() for name in four if name in buttons})
    check("9 the four buttons are one width", len(widths), 1)
    results.append(("9 widths (px)", True, str(widths)))

    buttons["Share bookmark"].invoke()
    root.update()
    check("12 no redraw on Share: the pressed button still exists",
          bool(buttons["Share bookmark"].winfo_exists()), True)
    check("12 status line says Copied", str(scan._status_label.cget("text")).startswith(
        "Copied a RhinoData code"), True)
    code = root.clipboard_get()
    check("1 clipboard holds a RhinoData line", code.startswith(share.PREFIX), True)
    payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(code[len(share.PREFIX):])))
    check("2 no commander, marked_at, altitude or yield in the code",
          sorted(set(payload) & {"commander", "marked_at", "altitude", "yield"}), [])
    results.append(("2 code length (chars)", True, str(len(code))))

    main._check_clipboard()
    check("3 own code not imported back", len(_rows()), 1)

    from rs_core import cards
    cards.delete(dict(_rows()[0], id=1))
    main._clip_seen = main._clip_sequence = None     # look at the same text again
    main._check_clipboard()
    check("4 after delete: own code still not imported (digest)", len(_rows()), 0)
    print("CODE " + code)
    root.destroy()


def child_b(results, code):
    tk, root, main = _boot()
    from rs_core import share

    def check(name, got, want):
        results.append((name, got == want, f"{got!r} != {want!r}"))

    def clip(text):
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()

    check("5 the code survived A exiting", root.clipboard_get(), code)
    main._check_clipboard()
    rows = _rows()
    check("6 imported once", len(rows), 1)
    if rows:
        row = rows[0]
        check("6 fields as shared",
              {key: row.get(key) for key in share.FIELDS},
              {key: SPOT.get(key) for key in share.FIELDS})
        check("6 no commander in the imported row", "commander" in row, False)

    main._check_clipboard()
    check("7 same text polled again: no second row", len(_rows()), 1)
    clip(f"hey, try this one {code} - good rocks")
    main._check_clipboard()
    check("7 same code inside chat text: no second row", len(_rows()), 1)

    # Another sharer's code for the same patch: different heading, same spot.
    other = json.loads(zlib.decompress(base64.urlsafe_b64decode(code[len(share.PREFIX):])))
    other["heading"] = 200
    clip(share.PREFIX + base64.urlsafe_b64encode(
        zlib.compress(json.dumps(other).encode())).decode())
    main._check_clipboard()
    check("7 other code, same patch: no second row", len(_rows()), 1)
    check("7 and the status line says it is already bookmarked", "already bookmarked" in
          str(main._status.cget("text")), True)

    bomb = share.PREFIX + base64.urlsafe_b64encode(
        zlib.compress(b'{"a":"' + b"x" * 5_000_000 + b'"}', 9)).decode()
    tampered = json.loads(zlib.decompress(base64.urlsafe_b64decode(code[len(share.PREFIX):])))
    tampered.update(commodity="Gold Bars", latitude=12.9)
    tampered = share.PREFIX + base64.urlsafe_b64encode(
        zlib.compress(json.dumps(tampered).encode())).decode()
    def crafted(**changes):
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(code[len(share.PREFIX):])))
        data.update(changes)
        return share.PREFIX + base64.urlsafe_b64encode(
            zlib.compress(json.dumps(data).encode())).decode()

    for name, text in (("garbage", share.PREFIX + "!!!notbase64"),
                       ("NaN radius", crafted(planet_radius=float("nan"), latitude=11.0)),
                       ("zero radius", crafted(planet_radius=0, latitude=11.1)),
                       ("64+ char body name", crafted(planet_name="x" * 5000, latitude=11.2)),
                       ("int over 2^63", crafted(system_address=2 ** 70, latitude=11.3)),
                       ("unknown Amount", crafted(amount="Lots", latitude=11.4)),
                       ("truncated", code[:len(code) // 2]),
                       ("oversized zip", bomb),
                       ("unknown material", tampered),
                       ("prefix only", share.PREFIX)):
        clip(text)
        try:
            main._check_clipboard()
            raised = None
        except Exception as err:            # noqa: BLE001 - any raise is the failure
            raised = repr(err)
        check(f"8 {name}: no raise, no row", (raised, len(_rows())), (None, 1))

    # An imported code, its bookmark deleted, the same code seen again.
    from rs_core import cards
    clip(code)
    main._clip_seen = main._clip_sequence = None
    main._check_clipboard()
    cards.delete(dict(_rows()[0], id=1))
    main._clip_seen = main._clip_sequence = None
    main._check_clipboard()
    check("11 imported, deleted, seen again: not imported again", len(_rows()), 0)

    clip("plain text, nothing shared")
    main._clip_seen = main._clip_sequence = None
    start = time.perf_counter()
    for _ in range(1000):
        main._check_clipboard()
    per_call = (time.perf_counter() - start)
    results.append(("10 _check_clipboard, unchanged text: ms per call", True,
                    f"{per_call:.3f}"))
    check("10 under 1 ms per call", per_call < 1.0, True)
    root.destroy()


def child(role):
    results = []
    try:
        if role == "a":
            child_a(results)
        else:
            child_b(results, os.environ["SHARE_CODE"])
    except Exception:
        import traceback
        results.append(("harness ran without an exception", False, traceback.format_exc()))
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}  [{detail}]")
    return 0 if all(ok for _, ok, _ in results) else 1


# ---------------------------------------------------------------- the parent


def _clipboard(text=None):
    """Read the clipboard, or set it to `text`."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        if text is None:
            return root.clipboard_get()
        # Win32, not Tk: Tk's clipboard text goes with this process.
        sys.path.insert(0, PLUGIN)
        from rs_ui import clipboard
        clipboard.copy(root, text)
    except tk.TclError:
        return None
    finally:
        root.destroy()


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    saved = _clipboard()
    # A RhinoData code already there would be imported by the children's first poll.
    _clipboard("share_e2e: clipboard cleared for the run")
    report, ok, code = [], True, ""
    try:
        for role in ("a", "b"):
            data = os.path.join(out, role)
            os.makedirs(data, exist_ok=True)
            env = dict(os.environ, LOCALAPPDATA=data, SHARE_CODE=code, PYTHONIOENCODING="utf-8")
            run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", role],
                                 cwd=PLUGIN, env=env, capture_output=True, text=True,
                                 encoding="utf-8")
            lines = run.stdout.splitlines()
            code = next((line[5:] for line in lines if line.startswith("CODE ")), code)
            report.append(f"--- {role} ---")
            report += [line for line in lines if not line.startswith("CODE ")]
            if run.stderr.strip():
                report.append(run.stderr.strip())
            ok = ok and run.returncode == 0
    finally:
        if saved is not None:
            _clipboard(saved)
    report.append(f"\nresult: {'PASS' if ok else 'FAIL'}")
    text = "\n".join(report)
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text)
    print(out)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--child" in sys.argv:
        raise SystemExit(child(sys.argv[-1]))
    raise SystemExit(main())
