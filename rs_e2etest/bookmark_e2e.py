"""E2E harness for the Bookmark press on a bookmarked spot. Checks and blind
spots: bookmark.md.

Run from the plugin folder:  python rs_e2etest/bookmark_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
"""

import json
import math
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SYSTEM = "HIP 37645"
BODY = f"{SYSTEM} 4 a"
RADIUS = 1_200_000.0
LAT, LON = -10.48763, 21.49148


def north(metres):
    return LAT + math.degrees(metres / RADIUS)


def child():
    sys.path.insert(0, PLUGIN)
    import tkinter as tk
    from rs_core import cards, coverage, database, share, spotcard, yields
    from rs_ui import main
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH
    coverage.clear_old_textures = lambda: None
    from rs_core import update
    checks = []
    update.check_async = lambda callback: checks.append(callback)   # no network
    main.start(PLUGIN)
    root = tk.Tk()
    root.withdraw()
    main.build(root)
    main._cancel_landed()
    fails = []

    def check(name, ok, detail=""):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            fails.append(f"{name} {detail}")

    def spot(material, lat=LAT, rigs=5, amount="High", density="Low", loc=1):
        return {"system": SYSTEM, "planet_name": BODY, "planet_radius": RADIUS,
                "latitude": lat, "longitude": LON, "heading": 90, "commodity": material,
                "rigs": rigs, "amount": amount, "density": density, "location_index": loc,
                "commander": "E2E", "marked_at": datetime.now().isoformat()}

    def press(mark):
        main._card_token += 1
        main._render_card(mark, main._card_token)
        for _ in range(10):
            root.update()
        return main._status.cget("text") if main._status is not None else ""

    def rows():
        return sorted(cards.for_system(SYSTEM), key=lambda r: r["id"])

    print("different material on the same spot")
    press(spot("Monazite"))
    first = rows()[0]
    yields.TALLY.refined({"BodyName": BODY, "Latitude": LAT, "Longitude": LON,
                          "PlanetRadius": RADIUS, "Altitude": 0}, SYSTEM, "Monazite")
    yields.TALLY.flush()
    before = [r for r in rows() if r["id"] == first["id"]][0]
    said = press(spot("Alexandrite", rigs=6, amount="Medium", density="Medium", loc=7))
    after = rows()
    check("still one bookmark", len(after) == 1, len(after))
    one = after[0]
    check("material now Alexandrite", one.get("commodity") == "Alexandrite", one.get("commodity"))
    check("rigs/amount/density taken", (one.get("rigs"), one.get("amount"), one.get("density"))
          == (6, "Medium", "Medium"))
    kept = ("latitude", "longitude", "marked_at", "location_index")
    check("position, marked_at, location kept", all(one.get(k) == before.get(k) for k in kept),
          {k: (before.get(k), one.get(k)) for k in kept if one.get(k) != before.get(k)})
    check("counted tons kept", yields.cycles(one) == yields.cycles(before), yields.cycles(one))
    check("status line names the change", "Monazite -> Alexandrite" in said, said)

    print("another material 150 m away")
    press(spot("Ruby", lat=north(150)))
    check("a new bookmark", len(rows()) == 2, len(rows()))

    print("same material within 100 m")
    said = press(spot("Alexandrite", lat=north(40), rigs=4, amount="Low", density="Medium"))
    alex = [r for r in rows() if r["commodity"] == "Alexandrite"]
    check("no new bookmark", len(rows()) == 2, len(rows()))
    check("rigs/amount taken, material the same",
          (alex[0].get("rigs"), alex[0].get("amount"), alex[0].get("commodity"))
          == (4, "Low", "Alexandrite"))
    check("status line without an arrow", "->" not in said and "Alexandrite" in said, said)

    print("two within 100 m: the nearest wins")
    # Alexandrite at 0 m, Ruby at 150 m. A mark at 110 m: Ruby 40 m, Alexandrite 110 m.
    press(spot("Opal", lat=north(110)))
    kinds = sorted(r["commodity"] for r in rows())
    check("the Ruby (40 m) became Opal, Alexandrite untouched", kinds == ["Alexandrite", "Opal"],
          kinds)

    print("shared code of another material within 100 m")
    state, _ = share.take(share.encode(spot("Diamond", lat=north(20))))
    check("imported as its own bookmark", state == "imported" and len(rows()) == 3,
          f"{state!r}, {len(rows())} rows")

    print("update check")
    pending = [str(root.tk.call("after", "info", i))
               for i in root.tk.splitlist(root.tk.call("after", "info"))]
    check("one update check, at build", len(checks) == 1, len(checks))
    check("no later update check booked", not any("_check_updates" in p for p in pending),
          pending)

    root.destroy()
    print(f"\nfails {len(fails)}")
    for line in fails:
        print("FAIL " + line)
    return 1 if fails else 0


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out)
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
