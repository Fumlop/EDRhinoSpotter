"""E2E harness: rig-count medal on the RhinoData rail and bookmark table. Checks and blind spots: medal.md.

Run from the plugin folder:  python rs_e2etest/medal_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt and medals.png. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; the live db is
copied in with sqlite3's backup API, read only.
"""

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

SYSTEM, BODY = "Aramo", "Aramo A 1"
# Rigs written through the Edit dialog's save, by position in cards.ordered() of the body.
# Rail then: A 1 gold 7 (a live 7 and a depleted 7), AB 3 a bronze 4, AB 1 a silver 5.
# Needs the live db's Aramo: A 1 with 6+ bookmarks, AB 3 a and AB 1 a with 4+ rigs nowhere
# but AB 1 a's (set to 5 here).
EDITS = {BODY: {0: 6, 1: 7, 2: 2, 3: 4, 4: 5, 5: 7}}
DEPLETE_POS = 1         # in BODY: that 7 is depleted, so it must not count

os.makedirs(os.path.join(DATA, "RhinoSpotter", "db"))
src = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
dst = sqlite3.connect(os.path.join(DATA, "RhinoSpotter", "db", "rhinospotter.db"))
src.backup(dst)
src.close()
dst.close()
os.environ["LOCALAPPDATA"] = DATA
sys.path.insert(0, PLUGIN)

import tkinter as tk                                     # noqa: E402

from PIL import Image                                    # noqa: E402

from rs_core import cards, coverage, database, medal, palette   # noqa: E402
from rs_ui import main, scan                             # noqa: E402

assert database.PATH.startswith(DATA), database.PATH

results, lines = [], []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def expected_best(records):
    """Independent of scan._best_rigs: max rigs of not-depleted records, if 4+."""
    live = [r["rigs"] for r in records if isinstance(r.get("rigs"), int)
            and not r.get("depleted_at") and r.get("amount") != "Depleted"]
    best = max(live, default=None)
    return best if best is not None and best >= 4 else None


def medal_of(frame):
    """Rigs of the medal Label among `frame`'s children, None if none, '?' if unknown image."""
    for w in frame.winfo_children():
        if isinstance(w, tk.Label) and str(w.cget("image")):
            name = str(w.cget("image"))
            hit = [rigs for (rigs, _bg), photo in scan._medals.items() if str(photo) == name]
            return hit[0] if hit else "?"
    return None


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


coverage.clear_old_textures = lambda: None
scan.spotmark.read_status = lambda: {}
main.start(PLUGIN)
root = tk.Tk()
root.withdraw()
var = tk.StringVar()

try:
    main.journal_entry("CMDR Test", False, SYSTEM, None, {"event": "FSDJump", "StarSystem": SYSTEM}, {})
    root.update()
    register, sheet = main._register, main._sheet

    # setup through the real Edit save and Mark depleted
    scan._state["body"] = BODY
    scan.show(root, register, sheet, None, variable=var, materials=(main.ALL_MATERIALS,))
    root.update()
    def save(record, rigs):
        box = tk.Toplevel(root)
        scan._save_edit(box, record, record.get("commodity"), str(rigs), scan.NOT_SET, scan.NOT_SET,
                        str(record.get("location_index")))
        root.update()

    def of(body):
        return cards.ordered([r for r in cards.for_system(SYSTEM) if r["planet_name"] == body])

    mine = of(BODY)
    for pos, rigs in EDITS[BODY].items():
        save(mine[pos], rigs)
    target = of(BODY)[DEPLETE_POS]
    assert target.get("rigs") == 7, target.get("rigs")
    cards.set_depleted(target, True)
    save(of("Aramo AB 3 a")[0], 4)
    for record in of("Aramo AB 1 a"):
        if isinstance(record.get("rigs"), int) and record["rigs"] >= 4:
            save(record, 5 if record["rigs"] == 6 else 3)
    scan._state["body"] = BODY
    scan._draw()
    root.update()
    for button in walk(scan._window):
        if isinstance(button, tk.Button) and str(button.cget("text")) == "Open all":
            button.invoke()
            root.update()
            break

    records = cards.for_system(SYSTEM)
    by_body = {}
    for r in records:
        by_body.setdefault(r["planet_name"], []).append(r)
    lines.append(f"{BODY}: rigs now {[r.get('rigs') for r in by_body[BODY]]}, "
                 f"depleted {[r.get('rigs') for r in by_body[BODY] if r.get('depleted_at')]}")

    # 1. rail: every body row's medal vs its not-depleted bookmarks
    rail_seen = 0
    for frame in walk(scan._panes["rail"]):
        labels = [w for w in frame.winfo_children() if isinstance(w, tk.Label)]
        if not labels or not str(labels[0].cget("text")) or not any(
                str(w.cget("text")).endswith(" Ls") for w in labels):
            continue
        short = str(labels[0].cget("text")).strip()
        name = next((n for n in by_body if n.endswith(" " + short) or n == short), None)
        if name is None:
            continue
        rail_seen += 1
        want, got = expected_best(by_body[name]), medal_of(frame)
        lines.append(f"rail {name}: medal {got}, want {want}")
        check(f"rail {name}", got == want, f"got {got}, want {want}")
    check("rail: body rows found", rail_seen >= 1, f"{rail_seen} rows")

    # 1b. rail, each ground opened in turn: medal vs bookmarks on every body row,
    # the slot between name and distance, the distance column at one x
    xs, rows_by_medal, tiers = set(), {True: 0, False: 0}, set()
    def arrow_row(f):
        kids = f.winfo_children()
        return (len(kids) > 1 and all(isinstance(w, tk.Label) for w in kids[:2])
                and str(kids[0].cget("text")) in ("▼", "▶"))

    headers = [str(f.winfo_children()[1].cget("text")) for f in walk(scan._panes["rail"]) if arrow_row(f)]
    for title in headers:
        for f in walk(scan._panes["rail"]):
            kids = f.winfo_children()
            if arrow_row(f) and str(kids[1].cget("text")) == title and str(kids[0].cget("text")) == "▶":
                f.event_generate("<Button-1>")
                root.update()
                break
        for frame in walk(scan._panes["rail"]):
            kids = frame.winfo_children()
            labels = [w for w in kids if isinstance(w, tk.Label)]
            dist = [w for w in labels if str(w.cget("text")).endswith(" Ls")]
            if not dist:
                continue
            short = str(labels[0].cget("text")).strip()
            name = next((n for n in by_body if n.endswith(" " + short)), None)
            slot = kids[kids.index(dist[0]) - 1]
            ok_slot = kids.index(dist[0]) >= 2 and (
                bool(str(slot.cget("image"))) if isinstance(slot, tk.Label) else isinstance(slot, tk.Frame))
            check(f"rail slot before distance ({title} / {short})", ok_slot, slot.winfo_class())
            xs.add(dist[0].winfo_x())
            got = medal_of(frame)
            rows_by_medal[got is not None] += 1
            tiers.add(got)
            if name is not None:
                want = expected_best(by_body[name])
                check(f"rail medal {name}", got == want, f"got {got}, want {want}")
    lines.append(f"rail rows over {len(headers)} grounds: {rows_by_medal[True]} with medal, "
                 f"{rows_by_medal[False]} without; distance x {sorted(xs)}")
    check("rail rows with and without medal seen", all(rows_by_medal.values()), str(rows_by_medal))
    check("rail distance column aligned", len(xs) == 1, f"x {sorted(xs)}")
    check("rail shows bronze 4, silver 5, gold 7", {4, 5, 7} <= tiers, f"tiers {sorted(t for t in tiers if t)}")

    # 2. location headers of BODY
    groups = {}
    for r in by_body[BODY]:
        groups.setdefault(r.get("location_index"), []).append(r)
    for index, group in sorted(groups.items(), key=lambda g: (g[0] is None, g[0] or 0)):
        loc = scan._loc(index)
        frame = next((f for f in walk(scan._window)
                      if any(isinstance(w, tk.Label) and str(w.cget("text")) == loc
                             for w in f.winfo_children())), None)
        want = expected_best(group)
        got = medal_of(frame) if frame is not None else "no header"
        lines.append(f"header {loc}: medal {got}, want {want}, rigs {[r.get('rigs') for r in group]}")
        check(f"header {loc}", got == want, f"got {got}, want {want}")

    # 3. deposit rows: colour of the rigs column
    colour_want = {4: palette.BRONZE, 5: palette.SILVER, 6: palette.GOLD, 7: palette.GOLD}
    rows_checked = 0
    for r in by_body[BODY]:
        frame = scan._rows.get(scan._key(r))
        if frame is None:
            continue
        labels = [w for w in frame.winfo_children() if isinstance(w, tk.Label)]
        rigs_label = labels[1]
        dead = bool(r.get("depleted_at"))
        want = scan.DIM if dead else colour_want.get(r.get("rigs"), scan.ACCENT)
        got = str(rigs_label.cget("fg"))
        rows_checked += 1
        if r.get("rigs") in (2, 4, 5, 6, 7):
            lines.append(f"row rigs {r.get('rigs')}{' depleted' if dead else ''}: fg {got}, want {want}")
        check(f"row {scan._key(r)[2:]} rigs {r.get('rigs')}", got == want, f"got {got}, want {want}")
    check("rows: all of the body drawn", rows_checked == len(by_body[BODY]),
          f"{rows_checked} of {len(by_body[BODY])}")

    # 4. medal pixels: disc colour at 4/5/6/7, none under 4
    for rigs, want in ((4, palette.BRONZE), (5, palette.SILVER), (6, palette.GOLD), (7, palette.GOLD)):
        px = medal.image(rigs).getpixel((4, 8))
        close = all(abs(a - b) <= 40 for a, b in zip(px, palette.rgb(want)))
        check(f"medal {rigs} colour", close, f"{px} vs {palette.rgb(want)}")
    check("no medal under 4", medal.image(3) is None and medal.image(None) is None)
    sheet_img = Image.new("RGB", (4 * 136, 128), palette.rgb(palette.BG))
    for i, rigs in enumerate((4, 5, 6, 7)):
        sheet_img.paste(medal.image(rigs).resize((128, 128), Image.NEAREST), (i * 136, 0))
    sheet_img.save(os.path.join(OUT, "medals.png"))
except Exception:
    check("harness ran", False, traceback.format_exc())

failed = [r for r in results if not r[1]]
report = lines + [""] + [f"{'PASS' if ok else 'FAIL'} {name}" + (f": {d}" if d and not ok else "")
                         for name, ok, d in results]
report.append(f"result: {'FAIL' if failed else 'PASS'} ({len(results) - len(failed)}/{len(results)})")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as handle:
    handle.write("\n".join(report) + "\n")
print("\n".join(report))
print(os.path.relpath(OUT, PLUGIN))
sys.exit(1 if failed else 0)
