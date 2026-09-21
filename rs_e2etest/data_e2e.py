"""E2E harness for migrate, replay and rs_api. Checks and blind spots: data-flow.md.

Run from the plugin folder:  python rs_e2etest/data_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt, one folder per scenario, one log
per plugin process under logs/. Exit code 1 on a failure.
Every plugin process runs with LOCALAPPDATA set to its scenario folder before
the interpreter starts. The live folder and the journals are only copied from.
"""

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
DAYS = 7
MARGIN_S = 600          # journals within 10 min of the window edge are not copied


# ------------------------------------------------------------ child processes


def child():
    """One plugin process: `--child <action> [args]`. LOCALAPPDATA and E2E_LOG
    come from the environment."""
    import logging
    action, args = sys.argv[2], sys.argv[3:]
    sys.path.insert(0, PLUGIN)
    handler = logging.FileHandler(os.environ["E2E_LOG"], encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger("RhinoSpotter").addHandler(handler)
    from rs_core import database
    assert database.PATH.startswith(os.environ["LOCALAPPDATA"]), database.PATH

    if action == "start":
        from rs_core import coverage
        coverage.clear_old_textures = lambda: None      # plugin folder, not under test
        import load
        print(load.plugin_start3(PLUGIN))
    elif action == "replay":
        from rs_core import replay
        sys.exit(replay.main(args))
    elif action == "leftovers":
        import tkinter as tk
        from rs_ui import minimap
        minimap.messagebox.askyesno = lambda *a, **k: True
        root = tk.Tk()
        root.withdraw()
        frame = tk.Frame(root)
        label = tk.Label(frame)
        minimap._delete_migrated(frame, label)
        print(label.cget("text"))
        root.destroy()
    elif action == "lock":
        seconds, mode = float(args[0]), args[1]
        with database.connect():
            pass
        conn = sqlite3.connect(database.PATH, timeout=1.0, isolation_level=None)
        if mode == "exclusive":
            conn.execute("PRAGMA locking_mode=EXCLUSIVE")
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('e2e-lock', 'x')")
        else:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO bookmarks (planet_name, data) VALUES (?, ?)",
                         ("E2E Uncommitted", json.dumps({"planet_name": "E2E Uncommitted"})))
        print("locked", flush=True)
        time.sleep(seconds)
        conn.execute("ROLLBACK")
        conn.close()
    elif action == "plugin":
        from rs_core import cards, spotcard
        op = args[0]
        if op == "insert":
            print(spotcard.save(json.loads(args[1])))
            return
        system, id = args[1], int(args[2])
        record = next(r for r in cards.for_system(system) if r["id"] == id)
        if op == "deplete":
            print(cards.set_depleted(record, True, when=args[3] if args[3:] else None))
        elif op == "undeplete":
            print(cards.set_depleted(record, False))
        elif op == "edit":
            print(spotcard.save(cards.edited(record, json.loads(args[3])), id))
        elif op == "delete":
            if record.get("path"):
                sys.exit(f"refusing: {record['path']} would be deleted")
            print(cards.delete(record))
    else:
        sys.exit(f"unknown action {action}")


# A separate application, as docs/API.md shows it: its own interpreter, the
# plugin folder appended to sys.path, nothing of rs_core imported first.
API_SCRIPT = r"""
import json, sys, time, types
sys.path.append(sys.argv[1])
import rs_api
out = {}
for key, name, kwargs in json.loads(sys.argv[2]):
    start = time.monotonic()
    try:
        out[key] = {"value": getattr(rs_api, name)(**kwargs)}
    except Exception as err:
        out[key] = {"error": repr(err)}
    out[key]["s"] = round(time.monotonic() - start, 2)
out["_modules"] = [m for m in ("tkinter", "PIL", "load", "rs_ui") if m in sys.modules]
out["_public"] = sorted(n for n, v in vars(rs_api).items()
                        if not n.startswith("_") and not isinstance(v, types.ModuleType))
out["_SCHEMA"] = rs_api.SCHEMA
print(json.dumps(out))
"""


# ------------------------------------------------------------------- parent

results, notes = [], []
counter = [0]


def check(name, ok, detail=""):
    detail = " | ".join(str(detail).split("\n")).strip(" |")
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def note(text):
    notes.append(text)
    print("NOTE " + text, flush=True)


def _env(root, log):
    return dict(os.environ, LOCALAPPDATA=root, E2E_LOG=log, PYTHONIOENCODING="utf-8")


def _log(name):
    counter[0] += 1
    return os.path.join(OUT, "logs", f"{counter[0]:02d}-{name}.log")


def run(action, root, *args, name=None, timeout=180):
    """A plugin process to completion. CompletedProcess; .log is its log file."""
    log = _log(name or action)
    proc = subprocess.run([sys.executable, __file__, "--child", action, *args],
                          env=_env(root, log), cwd=PLUGIN, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(f"\n--- exit {proc.returncode}\n--- stdout\n{proc.stdout}\n--- stderr\n{proc.stderr}")
    proc.log = log
    return proc


def log_text(proc):
    with open(proc.log, encoding="utf-8") as handle:
        return handle.read()


def hold_lock(root, seconds, mode="exclusive"):
    """A child holding the db locked for `seconds`. Returns once it holds it."""
    log = _log(f"lock-{mode}")
    proc = subprocess.Popen([sys.executable, __file__, "--child", "lock", str(seconds), mode],
                            env=_env(root, log), cwd=PLUGIN, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8")
    line = proc.stdout.readline().strip()
    if line != "locked":
        raise RuntimeError(f"lock child: {line!r} {proc.stderr.read()}")
    return proc


def api(root, calls):
    """rs_api from a separate interpreter. {key: {"value"|"error", "s"}, ...}."""
    proc = subprocess.run([sys.executable, "-c", API_SCRIPT, PLUGIN, json.dumps(calls)],
                          env=_env(root, _log("api")), cwd=OUT, capture_output=True,
                          encoding="utf-8", timeout=120)
    if proc.returncode:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def rows(db, sql, values=()):
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return conn.execute(sql, values).fetchall()
    finally:
        conn.close()


def execute(db, sql, values=()):
    conn = sqlite3.connect(db)
    try:
        with conn:
            conn.execute(sql, values)
    finally:
        conn.close()


def stat(path):
    s = os.stat(path)
    return s.st_size, s.st_mtime_ns


def tree(folder):
    """{relative path: (size, mtime_ns)} of every file under `folder`."""
    found = {}
    for where, _, files in os.walk(folder):
        for file in files:
            path = os.path.join(where, file)
            found[os.path.relpath(path, folder)] = stat(path)
    return found


def hashes(folder, skip=()):
    found = {}
    for where, _, files in os.walk(folder):
        for file in files:
            path = os.path.join(where, file)
            if not any(part in path for part in skip):
                with open(path, "rb") as handle:
                    found[path] = hashlib.sha256(handle.read()).hexdigest()
    return found


def seed(name, db=True):
    """A scenario LOCALAPPDATA. With db, a copy of the pristine live-db copy."""
    root = os.path.join(OUT, name)
    target = os.path.join(root, "RhinoSpotter", "db")
    if db:
        shutil.copytree(PRISTINE, target)
    else:
        os.makedirs(root)
    return root, os.path.join(target, "rhinospotter.db")


def body_rows(db):
    return {(s, n): json.loads(d) for s, n, d in rows(db, "SELECT system, name, data FROM bodies")}


def table(db, name):
    return sorted(rows(db, f"SELECT * FROM {name}"), key=repr)


# ----------------------------------------------------------------- journals


def copy_journals():
    """Copies of the journals in the window, one older than it, Status.json;
    then a garbage line, a whole line after it and a truncated last line
    appended to the newest copy with a landable Scan. Returns the window copies,
    oldest first, and the names of the two added bodies."""
    folder = os.path.join(OUT, "journals")
    os.makedirs(folder)
    now = time.time()
    window, older = [], []
    for file in os.listdir(JOURNALS):
        path = os.path.join(JOURNALS, file)
        if file == "Status.json":
            shutil.copy2(path, folder)
        if not (file.startswith("Journal.") and file.endswith(".log")):
            continue
        age = now - os.path.getmtime(path)
        if age < DAYS * 86400 - MARGIN_S:
            window.append(path)
        elif age > DAYS * 86400 + MARGIN_S:
            older.append(path)
    copies = [shutil.copy2(path, folder) for path in window]
    if older:
        shutil.copy2(max(older, key=os.path.getmtime), folder)
    copies.sort(key=os.path.getmtime)

    for path in reversed(copies):
        with open(path, encoding="utf-8", errors="ignore") as handle:
            scans = [line for line in handle if '"event":"Scan"' in line
                     and '"Landable":true' in line and '"StarSystem"' in line]
        if scans:
            break
    line = json.loads(scans[-1])
    after = dict(line, BodyName=line["BodyName"] + " E2E after garbage")
    cut = json.dumps(dict(line, BodyName=line["BodyName"] + " E2E truncated"))
    stamp = os.stat(path)
    with open(path, "ab") as handle:
        handle.write(b"\xff\xfe\x00{garbage line\n" + json.dumps(after).encode() + b"\n"
                     + cut[:len(cut) * 6 // 10].encode())
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    return folder, copies, after["BodyName"], json.loads(cut)["BodyName"]


def oracle(files):
    """{(system, body): last landable Scan} over the files in order, read the
    way the journal is written: one JSON object per line."""
    found, current = {}, None
    for path in files:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                event = entry.get("event")
                if event in ("FSDJump", "CarrierJump", "Location") and entry.get("StarSystem"):
                    current = entry["StarSystem"]
                if (event == "Scan" and entry.get("Landable")
                        and (entry.get("PlanetClass") or "").strip() and entry.get("BodyName")):
                    found[(entry.get("StarSystem") or current, entry["BodyName"])] = entry
    return found


# ------------------------------------------------------------------ old JSON


def safe(text):
    from rs_core import names
    return names.safe(text)


def make_old_tree(root, source_db):
    """%LOCALAPPDATA%\\RhinoSpotter as 4.1 left it, written from the rows of a
    live-db copy, plus broken files. Returns what migrate should make of it."""
    base = os.path.join(root, "RhinoSpotter")
    want = {"bodies": {}, "cards": {}, "maps": {}, "bad": set(), "keep": set(), "png_cards": set()}

    def write(path, data, raw=False):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data if raw else json.dumps(data).encode("utf-8"))
        return path

    systems = {}
    for system, data in rows(source_db, "SELECT system, data FROM bodies ORDER BY system, rowid"):
        systems.setdefault(system, []).append(json.loads(data))
    for system, found in systems.items():
        address = next((b.get("system_address") for b in found if b.get("system_address")), None)
        write(os.path.join(base, "data", safe(system) + ".json"),
              {"version": 1, "system": system, "system_address": address, "bodies": found})
        for body in found:
            want["bodies"][(system, body["name"])] = (
                dict(body, system_address=body.get("system_address", address))
                if address is not None else body)

    marks = rows(source_db, "SELECT id, system, data FROM bookmarks ORDER BY id")
    sample = None
    for id, system, data in marks:
        record = json.loads(data)
        if not system or not record.get("planet_name"):
            continue
        record.pop("card", None)
        folder = os.path.join(base, "cards", safe(system))
        stem = f"{safe(record['planet_name']).replace(' ', '_')}_loc{record.get('location_index')}_" \
               f"{str(record.get('commodity')).lower().replace(' ', '_')}_{id}"
        expected = dict(record)
        if id % 3 == 0:                                   # card key given
            record["card"] = stem + ".png"
            expected["card"] = stem + ".png"
        if id % 2 == 0 or id % 3 == 0:                    # PNG beside it
            want["keep"].add(write(os.path.join(folder, stem + ".png"), b"\x89PNG\r\n\x1a\ne2e", raw=True))
            expected.setdefault("card", stem + ".png")    # found by name
            want["png_cards"].add(id)
        path = write(os.path.join(folder, stem + ".json"), record)
        want["cards"][path] = expected
        sample = sample or (folder, dict(record))

    maps = rows(source_db, "SELECT body, name, data FROM maps ORDER BY body, name")
    for index, (body, name, blob) in enumerate(maps):
        data = json.loads(gzip.decompress(blob).decode("utf-8"))
        folder = os.path.join(base, "coverage", safe(body))
        want["maps"][(body, name)] = dict(data, body=data.get("body") or safe(body))
        if index == 0:                                    # plain JSON of 4.0
            write(os.path.join(folder, name + ".json"), data)
        elif index == 1:                                  # gz wins over a stale plain one
            write(os.path.join(folder, name + ".json.gz"),
                  gzip.compress(json.dumps(data).encode()), raw=True)
            write(os.path.join(folder, name + ".json"), dict(data, location=-1))
        elif index == 2:                                  # body missing: from the folder
            write(os.path.join(folder, name + ".json.gz"),
                  gzip.compress(json.dumps(dict(data, body=None)).encode()), raw=True)
            want["maps"][(body, name)]["body"] = safe(body)
        else:
            write(os.path.join(folder, name + ".json.gz"),
                  gzip.compress(json.dumps(data).encode()), raw=True)
        want["keep"].add(write(os.path.join(folder, name + ".png"), b"\x89PNG e2e", raw=True))
    map_folder = os.path.join(base, "coverage", safe(maps[0][0]))
    write(os.path.join(map_folder, "tmpe2e0001.tmp"), b"half", raw=True)

    card_folder, card = sample
    full = json.dumps(card)
    bad = want["bad"]
    bad.add(write(os.path.join(card_folder, "E2E_truncated.json"),
                  full[:len(full) * 4 // 10].encode(), raw=True))
    bad.add(write(os.path.join(card_folder, "E2E_notjson.json"), b"{not json", raw=True))
    bad.add(write(os.path.join(card_folder, "E2E_rigs_list.json"), dict(card, rigs=[1, 2])))
    bad.add(write(os.path.join(card_folder, "E2E_noplanet.json"),
                  {k: v for k, v in card.items() if k != "planet_name"}))
    bad.add(write(os.path.join(base, "data", "E2E Old.json"),
                  {"version": 0, "system": "E2E Old", "bodies": [{"name": "E2E Old 1"}]}))
    noname = write(os.path.join(base, "data", "E2E Noname.json"),
                   {"version": 1, "system": "E2E Noname",
                    "bodies": [{"name": "E2E Noname 1", "ground": "icy"}, {"ground": "icy"}]})
    bad.add(noname)
    want["bodies"][("E2E Noname", "E2E Noname 1")] = {"name": "E2E Noname 1", "ground": "icy"}
    bad.add(write(os.path.join(map_folder, "map 90.json.gz"), b"\x1f\x8bnope", raw=True))
    bad.add(write(os.path.join(map_folder, "map 91.json"), dict(version=2, stamps=[])))
    want["good_cards"] = len(want["cards"])
    return base, want


def marker_skipped(text):
    return {line[len("skipped "):].split(": ", 1)[0] for line in text.splitlines()
            if line.startswith("skipped ")}


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------- scenarios


def scenario_replay(journals, window, after_name, cut_name):
    root, db = seed("replay-live-copy")
    marker = os.path.join(os.path.dirname(db), "migrate.done")
    before = body_rows(db)
    others = {name: table(db, name) for name in ("bookmarks", "maps")}
    expect = oracle(window)
    systems = {system for system, _ in expect}

    # R1 plugin start with migrate.done present: migrate looks at nothing.
    db_before, marker_before = stat(db), read(marker)
    proc = run("start", root)
    check("R1 plugin_start3 with migrate.done: returns RhinoSpotter",
          proc.stdout.strip() == "RhinoSpotter", proc.stdout.strip() or proc.stderr[-300:])
    check("R1 db file not written (size, mtime)", stat(db) == db_before)
    check("R1 migrate.done unchanged", read(marker) == marker_before)

    # R2 --rebuild over the real journals.
    proc = run("replay", root, "--rebuild", "--days", str(DAYS), "--root", journals, "--top", "0",
               name="replay-rebuild")
    after = body_rows(db)
    check("R2 --rebuild exit 0", proc.returncode == 0, proc.stderr[-300:])
    m = re.search(r"^(\d+) journal file\(s\)", proc.stdout, re.M)
    check("R2 journal files read = copies in the window (older copy, Status.json left out)",
          m and int(m.group(1)) == len(window), f"printed {m and m.group(1)}, window {len(window)}")
    m = re.search(r"rebuilt (\d+) system\(s\)", proc.stdout)
    check("R2 systems rebuilt = systems with a landable Scan",
          m and int(m.group(1)) == len(systems), f"printed {m and m.group(1)}, journals {len(systems)}")
    missing = [key for key in expect if key not in after]
    check(f"R2 every landable Scan body in the db ({len(expect)})", not missing, missing[:5])
    wrong = [key for key, entry in expect.items() if key in after and (
        after[key].get("body_id") != entry.get("BodyID")
        or after[key].get("system_address") != entry.get("SystemAddress")
        or after[key].get("distance") != entry.get("DistanceFromArrivalLS"))]
    check("R2 body_id, system_address, distance = the last Scan of that body", not wrong, wrong[:5])
    check("R2 truncated last line not read", not any(n == cut_name for _, n in after), cut_name)
    check("R2 line after invalid UTF-8 bytes read", any(n == after_name for _, n in after), after_name)
    untouched = [k for k, v in before.items() if k[0] not in systems and after.get(k) != v]
    check("R2 systems not in the journals unchanged", not untouched, untouched[:5])
    lost = [k for k in before if k not in after]
    check("R2 no cached body dropped (merge, not replace)", not lost, lost[:5])
    forgot = [k for k, v in before.items() if k in after and v.get("locations") is not None
              and after[k].get("locations") is None]
    check("R2 no body loses its counted locations", not forgot,
          f"{len(forgot)}: {forgot[:4]}")
    check("R2 bookmarks and maps untouched",
          all(table(db, n) == others[n] for n in others))

    # R3 again: nothing changes.
    first = after
    proc = run("replay", root, "--rebuild", "--days", str(DAYS), "--root", journals, "--top", "0",
               name="replay-rebuild-again")
    check("R3 second --rebuild: bodies identical", proc.returncode == 0 and body_rows(db) == first)

    # R4 ranking, no flags: ordered, every system listed, db not written.
    proc = run("replay", root, "--days", str(DAYS), "--root", journals, "--top", "1000",
               name="replay-rank")
    ranked = [(s, float(v), int(n), int(c)) for s, v, n, c in re.findall(
        r"^(.+?)   score ([\d.]+), (\d+) landable, (\d+) locations counted$", proc.stdout, re.M)]
    check("R4 rank exit 0, every system listed", proc.returncode == 0
          and {r[0] for r in ranked} == systems, f"{len(ranked)} listed, {len(systems)} in journals")
    order = [(-v, -c, s) for s, v, n, c in ranked]
    check("R4 order: score desc, then locations counted desc, then name", order == sorted(order),
          f"ties on score: {len(ranked) - len({r[1] for r in ranked})}")
    counts = {s: sum(1 for sys_, _ in expect if sys_ == s) for s in systems}
    wrong = [(s, n, counts.get(s)) for s, v, n, c in ranked if counts.get(s) != n]
    check("R4 landable count per system = journal count", not wrong, wrong[:5])
    check("R4 rank run writes no bodies", body_rows(db) == first)

    # R5 a journal folder that is not there.
    proc = run("replay", root, "--root", os.path.join(OUT, "no-journals"), name="replay-missing")
    check("R5 missing journal folder: exit 1, 0 files, no landable bodies",
          proc.returncode == 1 and proc.stdout.startswith("0 journal file(s)")
          and "no landable bodies" in proc.stdout, proc.stdout.strip()[:120])
    return expect, ranked[0][0] if ranked else None


def scenario_testmode(journals, top):
    root, db = seed("replay-testmode")
    before = body_rows(db)
    proc = run("replay", root, "--testmode", "--days", str(DAYS), "--root", journals, "--top", "0",
               name="replay-testmode")
    m = re.search(r"test mode: (.+) \(score ([\d.]+), (\d+) landable\)", proc.stdout)
    check("T1 --testmode exit 0, names a system", proc.returncode == 0 and m, proc.stdout[-200:])
    if not m:
        return
    system, count = m.group(1), int(m.group(3))
    check("T1 --testmode picks the first system of the ranking", system == top, f"{system} vs {top}")
    after = body_rows(db)
    have = [n for s, n in after if s == system]
    check("T1 the system's bodies are in the db", len(have) >= count, f"{len(have)} rows, {count} printed")
    lost = [n for s, n in before if s == system and (s, n) not in after]
    check("T1 cached bodies of that system kept", not lost,
          f"{len(lost)} dropped of {sum(1 for s, _ in before if s == system)}: {lost[:4]}")


def scenario_replay_locked(journals, expect):
    root, db = seed("replay-locked")
    before = body_rows(db)
    first = next(iter(dict.fromkeys(s for s, _ in expect)))
    extra = [n for s, n in before if s == first and (s, n) not in expect]
    lock = hold_lock(root, 7.0)
    probe = sqlite3.connect(db, timeout=0.3)
    try:
        probe.execute("SELECT count(*) FROM bodies").fetchone()
        blocked = False
    except sqlite3.OperationalError:
        blocked = True
    probe.close()
    check("L0 lock child blocks a reader (setup)", blocked)
    started = time.monotonic()
    proc = run("replay", root, "--rebuild", "--days", str(DAYS), "--root", journals, "--top", "0",
               name="replay-rebuild-locked")
    lock.wait()
    after = body_rows(db)
    m = re.search(r"rebuilt (\d+) system\(s\)", proc.stdout)
    warnings = log_text(proc).count("WARNING")
    note(f"L1 --rebuild under a 7 s lock: exit {proc.returncode}, printed rebuilt "
         f"{m and m.group(1)}, {warnings} warnings in the log (none on stdout), "
         f"{time.monotonic() - started:.1f} s; first system {first!r} had {len(extra)} "
         f"cached bodies not in the journals")
    lost = [k for k in before if k not in after]
    check("L1 --rebuild under a lock drops no cached body", not lost,
          f"{len(lost)} dropped: {lost[:4]}")
    check("L1 lock failure visible on stdout", "could not" in proc.stdout or proc.returncode != 0,
          "warnings go to the logger only; CLI prints 'rebuilt N'")


def scenario_api(expect_docs):
    root, db = seed("api-live-copy")
    marks = rows(db, "SELECT id, system, planet_name, depleted_at, data FROM bookmarks ORDER BY id")
    valid = [(i, s, p, d, json.loads(data)) for i, s, p, d, data in marks]
    systems = sorted({s for _, s, _, _, _ in valid if s})
    bodies_sql = rows(db, "SELECT system, planet_name, count(*), "
                          "sum(depleted_at IS NOT NULL) FROM bookmarks "
                          "GROUP BY system, planet_name ORDER BY system, planet_name")
    body0 = valid[0][2]
    calls = [["all", "bookmarks", {}], ["bodies", "bodies", {}],
             ["bodies_s", "bodies", {"system": systems[0]}],
             ["body", "bookmarks", {"body": body0}], ["rev1", "revision", {}],
             ["rev2", "revision", {}], ["version", "version", {}],
             ["none", "bookmarks", {"system": "E2E Nowhere"}]]
    calls += [[f"sys:{s}", "bookmarks", {"system": s}] for s in systems]
    dir_before, db_before = tree(os.path.dirname(db)), stat(db)
    out = api(root, calls)
    got = out["all"].get("value", [])
    check("A1 bookmarks(): every row, oldest first",
          [m["id"] for m in got] == [v[0] for v in valid], f"{len(got)} of {len(valid)}")
    check("A1 keys = the table in docs/API.md", got and all(set(m) == expect_docs for m in got),
          sorted(set(got[0]) ^ expect_docs) if got else "")
    mapping = {"system": "system", "body": "planet_name", "location": "location_index",
               "material": "commodity", "rigs": "rigs", "latitude": "latitude",
               "longitude": "longitude", "heading": "heading", "planet_radius": "planet_radius",
               "amount": "amount", "density": "density", "depleted_at": "depleted_at",
               "marked_at": "marked_at", "commander": "commander"}
    wrong = [m["id"] for m, v in zip(got, valid)
             if any(m[k] != v[4].get(c) for k, c in mapping.items())
             or m["depleted"] != bool(v[4].get("depleted_at"))]
    check("A1 values = the stored record", not wrong, wrong[:5])
    per = {s: sum(1 for v in valid if v[1] == s) for s in systems}
    wrong = [s for s in systems if [m["id"] for m in out[f"sys:{s}"]["value"]]
             != [v[0] for v in valid if v[1] == s]]
    check(f"A2 bookmarks(system=) for {len(systems)} systems", not wrong, f"{per} bad {wrong}")
    check("A2 bookmarks(body=)", [m["id"] for m in out["body"]["value"]]
          == [v[0] for v in valid if v[2] == body0])
    check("A2 unknown system -> []", out["none"]["value"] == [])
    want = [{"system": s, "body": b, "bookmarks": n, "depleted": d or 0} for s, b, n, d in bodies_sql]
    check("A3 bodies() = GROUP BY over the table", out["bodies"]["value"] == want)
    check("A3 bodies(system=)", out["bodies_s"]["value"] == [w for w in want if w["system"] == systems[0]])
    check("A4 revision() stands still with no change", out["rev1"]["value"] == out["rev2"]["value"] != 0)
    version = re.search(r'^VERSION = "(.+)"', read(os.path.join(PLUGIN, "rs_core", "update.py")), re.M)
    check("A5 version() = rs_core/update.py VERSION", out["version"]["value"] == version.group(1))
    check("A5 SCHEMA = 1", out["_SCHEMA"] == 1)
    public = set(out["_public"]) - {"VERSION"}
    check("A5 public surface: SCHEMA + four calls", public == {"SCHEMA", "version", "bookmarks",
                                                                "bodies", "revision"}, sorted(public))
    check("A5 no tkinter, PIL, load or rs_ui imported", out["_modules"] == [], out["_modules"])
    check("A6 reads leave the db file alone (size, mtime)", stat(db) == db_before)
    created = sorted(set(tree(os.path.dirname(db))) - set(dir_before))
    check("A6 reads create no file beside the db", not created, created)

    # A7 revision seen from this process while plugin processes write.
    def rev():
        return api(root, [["r", "revision", {}], ["b", "bookmarks", {}]])

    def plugin(*args):
        proc = run("plugin", root, *args, name="plugin-" + args[0])
        return proc.returncode == 0 and proc.stdout.strip() not in ("False", "None")

    def max_data_id():
        return rows(db, "SELECT id FROM bookmarks ORDER BY data DESC LIMIT 1")[0][0]

    r0 = rev()
    new = {"system": systems[0], "planet_name": body0, "commodity": "Painite", "rigs": 3,
           "location_index": 99, "latitude": 1.5, "longitude": 2.5, "planet_radius": 1000000.0,
           "marked_at": "2026-09-21T12:00:00+00:00", "commander": "E2E"}
    ok = plugin("insert", json.dumps(new))
    r1 = rev()
    added = [m for m in r1["b"]["value"] if m["material"] == "Painite" and m["location"] == 99]
    check("A7 insert by the plugin: revision moves, the new mark reads back",
          ok and r1["r"]["value"] != r0["r"]["value"] and len(added) == 1
          and added[0]["planet_radius"] == 1000000.0)
    top = max_data_id()
    a, b = [v for v in valid if v[0] != top and not v[3]][:2]
    ok = plugin("deplete", a[1], str(a[0]))              # as rs_ui/scan.py: time now
    r2 = rev()
    check("A7 depleted by the plugin: revision moves, depleted + depleted_at read back",
          ok and r2["r"]["value"] != r1["r"]["value"] and any(
              m["id"] == a[0] and m["depleted"] and m["depleted_at"] for m in r2["b"]["value"]))
    time.sleep(1.1)                                     # depleted_at has 1 s resolution
    ok = plugin("deplete", b[1], str(b[0]))
    r3 = rev()
    check("A7 second depleted: revision moves", ok and r3["r"]["value"] != r2["r"]["value"])
    undo_top = max_data_id() == a[0]
    ok = plugin("undeplete", a[1], str(a[0]))
    r4 = rev()
    check("A7 depleted mark taken off (not the newest mark, not max(data)): revision moves",
          ok and r4["r"]["value"] != r3["r"]["value"],
          f"row {a[0]} {'was' if undo_top else 'not'} max(data); r3={r3['r']['value']} r4={r4['r']['value']}")
    c = next(v for v in valid if v[0] not in (a[0], b[0]) and v[0] != max_data_id())
    rigs = (c[4].get("rigs") or 0) + 1
    ok = plugin("edit", c[1], str(c[0]), json.dumps({"rigs": rigs}))
    r5 = rev()
    check("A7 edit by the Edit dialog path (rigs +1): revision moves",
          ok and r5["r"]["value"] != r4["r"]["value"],
          f"row {c[0]}; r4={r4['r']['value']} r5={r5['r']['value']}")
    check("A7 edit reads back", any(m["id"] == c[0] and m["rigs"] == rigs for m in r5["b"]["value"]))
    ok = plugin("delete", b[1], str(b[0]))
    r6 = rev()
    check("A7 delete by the plugin: revision moves, the mark is gone",
          ok and r6["r"]["value"] != r5["r"]["value"]
          and all(m["id"] != b[0] for m in r6["b"]["value"]))

    # A8 a reader during an uncommitted plugin write.
    count = len(r6["b"]["value"])
    lock = hold_lock(root, 6.0, mode="write")
    out = api(root, [["b", "bookmarks", {}]])
    lock.wait()
    check("A8 read during a plugin write: committed rows, not blocked",
          len(out["b"]["value"]) == count and out["b"]["s"] < 1.0, f"{out['b']['s']} s")

    # A9 a reader while another process holds the db exclusively.
    lock = hold_lock(root, 12.0)
    out = api(root, [["b", "bookmarks", {}], ["r", "revision", {}]])
    lock.wait()
    check("A9 locked db: bookmarks() and revision() return, no exception",
          "value" in out["b"] and "value" in out["r"] and out["b"]["s"] < 6.5,
          f"{out['b']['s']} s, {out['r']['s']} s")
    note(f"A9 locked db answers bookmarks() -> {len(out['b'].get('value') or [])} marks "
         f"(db holds {count}), revision() -> {out['r'].get('value')}: same as 'no bookmarks'")

    # A10 broken rows.
    execute(db, "INSERT INTO bookmarks (planet_name, data) VALUES (?, ?)", ("E2E Broken", "{not json"))
    execute(db, "INSERT INTO bookmarks (planet_name, data) VALUES (?, ?)",
            ("E2E Noplanet", json.dumps({"system": "E2E"})))
    out = api(root, [["b", "bookmarks", {}]])
    check("A10 unreadable rows skipped, the rest returned", len(out["b"]["value"]) == count)

    # A11 no database; A12 a file that is not a database.
    empty, _ = seed("api-no-db", db=False)
    out = api(empty, [["b", "bookmarks", {}], ["o", "bodies", {}], ["r", "revision", {}]])
    check("A11 no db: [], [], 0",
          (out["b"]["value"], out["o"]["value"], out["r"]["value"]) == ([], [], 0))
    check("A11 no db: nothing created", os.listdir(empty) == [])
    junk_root = os.path.join(OUT, "api-corrupt")
    junk = os.path.join(junk_root, "RhinoSpotter", "db", "rhinospotter.db")
    os.makedirs(os.path.dirname(junk))
    with open(junk, "wb") as handle:
        handle.write(os.urandom(8192))
    was = stat(junk)
    out = api(junk_root, [["b", "bookmarks", {}], ["r", "revision", {}]])
    check("A12 corrupt db file: [] and 0, no exception",
          out["b"].get("value") == [] and out["r"].get("value") == 0, out)
    check("A12 corrupt db file left as it was", stat(junk) == was)


def scenario_migrate():
    root = os.path.join(OUT, "migrate-old-json")
    base, want = make_old_tree(root, os.path.join(PRISTINE, "rhinospotter.db"))
    db = os.path.join(base, "db", "rhinospotter.db")
    marker = os.path.join(base, "db", "migrate.done")
    files_before = hashes(base)
    bad = want["bad"]

    # M1 first start.
    proc = run("start", root, name="start-migrate")
    check("M1 plugin_start3 returns RhinoSpotter", proc.stdout.strip() == "RhinoSpotter",
          proc.stderr[-300:])
    check("M1 migrate.done written", os.path.isfile(marker))
    text = read(marker) if os.path.isfile(marker) else ""
    counts = dict(re.findall(r"^(\w+): (\d+) imported", text, re.M))
    expected = {"bodies": str(len(want["bodies"])), "bookmarks": str(want["good_cards"]),
                "maps": str(len(want["maps"]))}
    check("M1 migrate.done counts = readable fixtures", counts == expected, f"{counts} vs {expected}")
    check("M1 migrate.done lists exactly the broken files", marker_skipped(text) == bad,
          sorted(marker_skipped(text) ^ bad))
    warnings = log_text(proc).count("WARNING migrate: skipped")
    check("M1 one log warning per skipped entry", warnings == text.count("\nskipped "),
          f"{warnings} warnings")
    got = body_rows(db)
    check("M1 bodies = the fixture bodies, record for record", got == want["bodies"],
          f"{len(got)} vs {len(want['bodies'])}")
    marks = {s: json.loads(d) for s, d in rows(db, "SELECT source, data FROM bookmarks")}
    wrong = [p for p, r in want["cards"].items() if marks.get(os.path.abspath(p)) != r]
    check("M1 bookmarks: one row per card file, source = its path, record as written",
          len(marks) == want["good_cards"] and not wrong, f"{len(marks)} rows, {len(wrong)} differ")
    maps = {(b, n): json.loads(gzip.decompress(d)) for b, n, d in rows(db, "SELECT body, name, data FROM maps")}
    check("M1 maps: gz wins over plain, missing body from the folder, .tmp/.png ignored",
          maps == want["maps"], sorted(set(maps) ^ set(want["maps"]))[:4])
    check("M1 the old files are left byte for byte", hashes(base, skip=[os.sep + "db" + os.sep]) == files_before)

    # M2 what migrate wrote, read through rs_api by another program.
    out = api(root, [["b", "bookmarks", {}]])
    key = lambda r: (r.get("planet_name"), r.get("location_index"), r.get("commodity"),
                     r.get("latitude"), r.get("longitude"))
    seen = sorted((m["body"], m["location"], m["material"], m["latitude"], m["longitude"])
                  for m in out["b"]["value"])
    check("M2 rs_api reads every migrated bookmark",
          seen == sorted(key(r) for r in want["cards"].values()), f"{len(seen)}")

    # M3 second start: migrate.done there, nothing looked at.
    late = os.path.join(base, "data", "E2E Late.json")
    with open(late, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "system": "E2E Late", "bodies": [{"name": "E2E Late 1"}]}, handle)
    db_stat, text = stat(db), read(marker)
    proc = run("start", root, name="start-again")
    check("M3 second start: db and migrate.done untouched, a new file not imported",
          stat(db) == db_stat and read(marker) == text
          and not rows(db, "SELECT 1 FROM bodies WHERE system = 'E2E Late'"))

    # M4 migrate.done lost: written again from the db, a deleted bookmark stays deleted.
    os.replace(marker, marker + ".moved-1")
    gone = next((r, p) for p, r in want["cards"].items()
                if not os.path.exists(os.path.join(os.path.dirname(p), r.get("card") or "-")))
    gone_id = rows(db, "SELECT id FROM bookmarks WHERE source = ?", (os.path.abspath(gone[1]),))[0][0]
    ok = run("plugin", root, "delete", gone[0]["system"], str(gone_id), name="plugin-delete")
    proc = run("start", root, name="start-lost-marker")
    check("M4 lost migrate.done: written again, same text",
          os.path.isfile(marker) and read(marker) == read(marker + ".moved-1"))
    check("M4 bookmark deleted after the import stays deleted",
          ok.returncode == 0 and not rows(db, "SELECT 1 FROM bookmarks WHERE id = ?", (gone_id,)))

    # M5 no marker and no meta row: a second import adds nothing that is there.
    os.replace(marker, marker + ".moved-2")
    execute(db, "DELETE FROM meta WHERE key = 'migrate.done'")
    kept = next(p for p in want["cards"] if p != gone[1])
    kept_row = rows(db, "SELECT id, system FROM bookmarks WHERE source = ?", (os.path.abspath(kept),))[0]
    run("plugin", root, "deplete", kept_row[1], str(kept_row[0]), "2026-09-15T10:00:00+00:00",
        name="plugin-deplete")
    run("start", root, name="start-no-record")
    text = read(marker) if os.path.isfile(marker) else ""
    check("M5 re-import: only the deleted bookmark comes back, the rest kept",
          f"bookmarks: 1 imported, {want['good_cards'] - 1} already in the database" in text,
          [line for line in text.splitlines() if line.startswith("bookmarks")])
    check("M5 re-import: no duplicate rows",
          rows(db, "SELECT count(*) FROM bookmarks")[0][0] == want["good_cards"])
    check("M5 re-import: depleted_at written after the first import kept",
          rows(db, "SELECT depleted_at FROM bookmarks WHERE id = ?", (kept_row[0],))[0][0]
          == "2026-09-15T10:00:00+00:00")

    # M6 "Delete migrated JSON" in Settings.
    later = os.path.getmtime(marker) + 60
    os.utime(late, (later, later))
    before = {os.path.join(w, f) for w, _, fs in os.walk(base) for f in fs
              if os.sep + "db" + os.sep not in os.path.join(w, f) + os.sep}
    keep = want["keep"] | bad | {late}
    proc = run("leftovers", root, name="delete-migrated")
    after = {os.path.join(w, f) for w, _, fs in os.walk(base) for f in fs
             if os.sep + "db" + os.sep not in os.path.join(w, f) + os.sep}
    check("M6 button reports the count deleted", proc.stdout.strip() == f"deleted {len(before - keep)}",
          proc.stdout.strip() or proc.stderr[-300:])
    check("M6 left: PNGs, skipped files, the file newer than migrate.done", after == keep,
          sorted(os.path.relpath(p, base) for p in after ^ keep)[:5])
    empty = [w for w, ds, fs in os.walk(base) if not ds and not fs]
    check("M6 emptied folders removed", not empty, empty[:3])
    out = api(root, [["b", "bookmarks", {}]])
    check("M6 bookmarks still read after the delete", len(out["b"]["value"]) == want["good_cards"])


def scenario_migrate_lost_db():
    root = os.path.join(OUT, "migrate-lost-db")
    base, want = make_old_tree(root, os.path.join(PRISTINE, "rhinospotter.db"))
    run("start", root, name="start-migrate-2")
    db = os.path.join(base, "db", "rhinospotter.db")
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(db + suffix):
            os.replace(db + suffix, db + suffix + ".moved")
    proc = run("leftovers", root, name="delete-lost-db")
    tmp = [p for w, _, fs in os.walk(base) for p in [os.path.join(w, f) for f in fs] if p.endswith(".tmp")]
    check("D1 db replaced by an empty one: only the .tmp is deleted",
          proc.stdout.strip() == "deleted 1" and not tmp, proc.stdout.strip() or proc.stderr[-300:])


def scenario_migrate_locked():
    root = os.path.join(OUT, "migrate-locked")
    base, want = make_old_tree(root, os.path.join(PRISTINE, "rhinospotter.db"))
    marker = os.path.join(base, "db", "migrate.done")
    lock = hold_lock(root, 8.0)
    proc = run("start", root, name="start-locked")
    lock.wait()
    db = os.path.join(base, "db", "rhinospotter.db")
    check("C1 locked db: start returns, failure logged, no migrate.done",
          proc.stdout.strip() == "RhinoSpotter" and "importing the old JSON files" in log_text(proc)
          and not os.path.exists(marker), proc.stderr[-200:])
    check("C1 locked db: nothing half in", rows(db, "SELECT count(*) FROM bodies")[0][0] == 0)
    run("start", root, name="start-after-lock")
    text = read(marker) if os.path.isfile(marker) else ""
    check("C2 next start imports everything",
          f"bookmarks: {want['good_cards']} imported" in text
          and f"bodies: {len(want['bodies'])} imported" in text, text.splitlines()[1:4])


def scenario_migrate_unlistable():
    root = os.path.join(OUT, "migrate-unlistable")
    base, want = make_old_tree(root, os.path.join(PRISTINE, "rhinospotter.db"))
    cards = os.path.join(base, "cards")
    user = os.environ["USERNAME"]
    deny = subprocess.run(["icacls", cards, "/deny", f"{user}:(RD)"], capture_output=True, text=True)
    try:
        listable = True
        try:
            os.listdir(cards)
        except PermissionError:
            listable = False
        check("U0 cards folder not listable (setup)", deny.returncode == 0 and not listable,
              deny.stdout.strip()[-120:])
        proc = run("start", root, name="start-unlistable")
    finally:
        restore = subprocess.run(["icacls", cards, "/remove:d", user], capture_output=True, text=True)
        check("U0 ACL restored (setup)", restore.returncode == 0, restore.stdout.strip()[-120:])
    db = os.path.join(base, "db", "rhinospotter.db")
    check("U1 unlistable folder: failure logged, no migrate.done, nothing in",
          "importing the old JSON files" in log_text(proc)
          and not os.path.exists(os.path.join(base, "db", "migrate.done"))
          and rows(db, "SELECT count(*) FROM bodies")[0][0] == 0)
    proc = run("leftovers", root, name="delete-before-import")
    check("U2 before any import: button says nothing to delete",
          proc.stdout.strip() == "nothing to delete", proc.stdout.strip() or proc.stderr[-200:])
    run("start", root, name="start-listable")
    check("U3 next start imports", os.path.isfile(os.path.join(base, "db", "migrate.done")))


def scenario_nothing():
    root, _ = seed("migrate-never-installed", db=False)
    run("start", root, name="start-nothing")
    marker = os.path.join(root, "RhinoSpotter", "db", "migrate.done")
    text = read(marker) if os.path.isfile(marker) else ""
    check("N1 nothing to import: migrate.done says 0 of each",
          all(f"{k}: 0 imported" in text for k in ("bodies", "bookmarks", "maps")))


def documented_keys():
    text = read(os.path.join(PLUGIN, "docs", "API.md"))
    section = text.split("### `bookmarks", 1)[1].split("###", 1)[0]
    return {key for line in section.splitlines() if line.startswith("| `")
            for key in re.findall(r"`(\w+)`", line.split("|")[1])}


def main():
    global OUT, PRISTINE, JOURNALS
    live = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter")
    JOURNALS = os.path.join(os.environ["USERPROFILE"], "Saved Games", "Frontier Developments",
                            "Elite Dangerous")
    OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(OUT, "logs"))
    os.environ["LOCALAPPDATA"] = os.path.join(OUT, "parent")   # before any rs_core import
    sys.path.insert(0, PLUGIN)
    live_before = tree(live)
    PRISTINE = os.path.join(OUT, "live-db-copy")
    os.makedirs(PRISTINE)
    for file in os.listdir(os.path.join(live, "db")):
        if os.path.isfile(os.path.join(live, "db", file)):
            shutil.copy2(os.path.join(live, "db", file), PRISTINE)
    journals, window, after_name, cut_name = copy_journals()
    errors = []
    try:
        expect, top = scenario_replay(journals, window, after_name, cut_name)
        scenario_testmode(journals, top)
        scenario_replay_locked(journals, expect)
    except Exception:
        import traceback
        errors.append(traceback.format_exc())
    for scenario in (lambda: scenario_api(documented_keys()), scenario_migrate,
                     scenario_migrate_lost_db, scenario_migrate_locked,
                     scenario_migrate_unlistable, scenario_nothing):
        try:
            scenario()
        except Exception:
            import traceback
            errors.append(traceback.format_exc())
    check("Z harness raised no exception", not errors, errors[0][-400:] if errors else "")
    check("Z live folder untouched (every file: size, mtime)", tree(live) == live_before,
          sorted(set(tree(live).items()) ^ set(live_before.items()))[:3])

    failed = [r for r in results if not r[1]]
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
        report.write(f"data flow E2E (migrate, replay, rs_api)  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.write(f"journals: {len(window)} in the last {DAYS} days, copied from {JOURNALS}\n")
        report.write(f"live db copied from {live}\n")
        report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
        for name, ok, detail in results:
            report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
        if notes:
            report.write("\n--- notes ---\n" + "\n".join(notes) + "\n")
        if errors:
            report.write("\n--- harness errors ---\n" + "\n".join(errors))
    print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child()
    else:
        main()
