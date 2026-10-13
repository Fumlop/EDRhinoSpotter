"""E2E harness: totals in the RhinoData rail header. Checks and blind spots: totals.md.

Run from the plugin folder:  python rs_e2etest/totals_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure, 2 without a live db.
LOCALAPPDATA points at the run folder before rs_core loads; the live db is
copied in with sqlite3's backup API, read only.
"""

import hashlib
import os
import sqlite3
import sys
import time
import traceback

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")

if not os.path.exists(LIVE_DB):
    sys.exit(2)
live_before = hashlib.sha256(open(LIVE_DB, "rb").read()).hexdigest()
os.makedirs(os.path.join(DATA, "RhinoSpotter", "db"))
src = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
dst = sqlite3.connect(os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db"))
src.backup(dst)
src.close()
dst.close()
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import tkinter as tk                                     # noqa: E402

from rs_core import cards, coverage, database            # noqa: E402
from rs_ui import main, scan                             # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

TITLE = "SYSTEMS WITH BOOKMARKS"
results = []
seen = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def expected():
    """(systems, line) from the scratch db rows, counted in Python."""
    with sqlite3.connect(database.PATH) as conn:
        rows = conn.execute("SELECT system, planet_name FROM bookmarks").fetchall()
        maps = len(conn.execute("SELECT body FROM maps").fetchall())
    systems = len({system for system, _ in rows if system is not None})
    marks, bodies = len(rows), len({body for _, body in rows})
    if not marks and not maps:
        return systems, None
    line = (f"{marks} {'bookmark' if marks == 1 else 'bookmarks'}  ·  "
            f"{bodies} {'body' if bodies == 1 else 'bodies'}  ·  "
            f"{maps} {'map' if maps == 1 else 'maps'}")
    return systems, line


def labels(widget):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            found.append(child)
        found.extend(labels(child))
    return found


def header():
    """(title text, totals label or None) from the open window."""
    all_labels = labels(scan._window)
    title = next(str(l.cget("text")) for l in all_labels if str(l.cget("text")).startswith(TITLE))
    totals = next((l for l in all_labels if " bookmark" in str(l.cget("text"))
                   and str(l.cget("text")).rstrip("s").endswith(" map")), None)
    seen.append(f"{title!r} / {totals.cget('text') if totals else None!r}")
    return title, totals


def jump(system):
    main.journal_entry("CMDR Test", False, system, None,
                       {"event": "FSDJump", "StarSystem": system}, {})
    root.update()


def reopen():
    if scan.is_open():
        scan._window.destroy()
        root.update()
    scan.show(root, main._register, main._sheet, None, variable=var,
              materials=(main.ALL_MATERIALS,))
    root.update()


coverage.clear_old_textures = lambda: None               # plugin folder, not under test
scan.spotmark.read_status = lambda: {}
main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
var = tk.StringVar()

try:
    with sqlite3.connect(database.PATH) as conn:
        ranked = conn.execute("SELECT system FROM bookmarks WHERE system IS NOT NULL "
                              "GROUP BY system ORDER BY count(*) DESC").fetchall()
    assert len(ranked) >= 2, "live db needs bookmarks in 2+ systems"
    home, away = ranked[0][0], ranked[1][0]

    # 1: header and line against the scratch db
    jump(home)
    reopen()
    systems, line = expected()
    title, totals = header()
    check("1 header carries the system count", title == f"{TITLE}  ·  {systems}", title)
    check("1 totals line matches the db", totals is not None and totals.cget("text") == line,
          f"{totals.cget('text') if totals else None!r} vs {line!r}")

    # 3: fits the rail
    if totals is not None:
        check("3 line fits the rail", totals.winfo_reqwidth() <= scan.RAIL_WIDTH - 26,
              f"{totals.winfo_reqwidth()} px of {scan.RAIL_WIDTH - 26}")

    # 2: whole db, not the shown system
    jump(away)
    reopen()
    _, totals_away = header()
    check("2 same line in another system", totals_away is not None
          and totals_away.cget("text") == line, f"{home} -> {away}")

    # 4: one bookmark deleted
    cards.delete(cards.for_system(away)[0])
    reopen()
    systems, line = expected()
    _, totals = header()
    check("4 delete -> next draw counts it", totals is not None and totals.cget("text") == line,
          f"{totals.cget('text') if totals else None!r} vs {line!r}")

    # 5: search hits still under the entry
    entries = []

    def find_entries(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Entry):
                entries.append(child)
            find_entries(child)

    find_entries(scan._window)
    search = entries[0]
    search.insert(0, home[:scan.SEARCH_MIN + 1])
    root.update()
    hits = [str(l.cget("text")) for l in labels(search.master) if str(l.cget("text")).endswith(" bm")]
    check("5 search lists hits", any(h.startswith(home[:24]) for h in hits), repr(hits))
    order = search.master.pack_slaves()                  # pack order, as drawn top to bottom
    hits_frame = next(w for w in order if isinstance(w, tk.Frame) and labels(w))
    line_label = next(l for l in order if isinstance(l, tk.Label)
                      and str(l.cget("text")).rstrip("s").endswith(" map"))
    check("5 hits sit between entry and totals line",
          order.index(search) < order.index(hits_frame) < order.index(line_label),
          f"entry {order.index(search)}, hits {order.index(hits_frame)}, line {order.index(line_label)}")
    search.delete(0, "end")
    root.update()

    # 6: nothing saved
    with sqlite3.connect(database.PATH) as conn:
        keep_mark = conn.execute("SELECT * FROM bookmarks ORDER BY id LIMIT 1").fetchone()
        keep_map = conn.execute("SELECT * FROM maps LIMIT 1").fetchone()
        conn.execute("DELETE FROM bookmarks")
        conn.execute("DELETE FROM maps")
    reopen()
    title, totals = header()
    check("6 empty db: no totals line", totals is None, repr(totals and totals.cget("text")))
    check("6 empty db: header '· 0'", title == f"{TITLE}  ·  0", title)

    # 7: one of each
    with sqlite3.connect(database.PATH) as conn:
        conn.execute(f"INSERT INTO bookmarks VALUES ({','.join('?' * len(keep_mark))})", keep_mark)
        if keep_map:
            conn.execute(f"INSERT INTO maps VALUES ({','.join('?' * len(keep_map))})", keep_map)
    reopen()
    _, totals = header()
    want = "1 bookmark  ·  1 body  ·  1 map" if keep_map else "1 bookmark  ·  1 body  ·  0 maps"
    check("7 singular on 1", totals is not None and totals.cget("text") == want,
          f"{totals.cget('text') if totals else None!r}")
except Exception:
    check("harness ran without an exception", False, traceback.format_exc())
finally:
    root.destroy()

check("0 live db unchanged", hashlib.sha256(open(LIVE_DB, "rb").read()).hexdigest() == live_before)

lines = [f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else "")
         for name, ok, detail in results]
lines += ["", "seen:"] + seen
passed = sum(ok for _, ok, _ in results)
lines.append(f"{passed}/{len(results)} passed  ->  {OUT}")
open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(0 if passed == len(results) else 1)
