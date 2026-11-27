"""E2E harness: bookmark upload (PR #29). Checks and blind spots: upload.md.

Run from the plugin folder:  python rs_e2etest/upload_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
LOCALAPPDATA points at the run folder before rs_core loads; db copied from the live one.
"""

import http.server
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
LIVE_DB = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter", "db", "rhinospotter.db")
os.makedirs(os.path.join(OUT, "RhinoSpotter", "db"))
shutil.copy(LIVE_DB, os.path.join(OUT, "RhinoSpotter", "db", "rhinospotter.db"))
os.environ["LOCALAPPDATA"] = OUT
sys.path.insert(0, PLUGIN)
sys.stdout.reconfigure(encoding="utf-8")


class Config:
    """EDMC's config as far as rs_core.upload reads it."""

    def __init__(self):
        self.values = {}

    def get_str(self, key, default=None):
        return self.values.get(key, default)

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


sys.modules["config"] = types.SimpleNamespace(config=Config())

import rs_api                                            # noqa: E402
from rs_core import database                             # noqa: E402
from rs_core import upload                               # noqa: E402

assert database.PATH.startswith(OUT), database.PATH
logging.getLogger().handlers.clear()
_log = logging.FileHandler(os.path.join(OUT, "upload.log"), encoding="utf-8")
logging.getLogger().addHandler(_log)
logging.getLogger().setLevel(logging.INFO)
config = upload.config
lines, failed = [], 0


def check(name, ok, detail=""):
    global failed
    failed += not ok
    line = f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else "")
    lines.append(line)
    print(line)


posts = []


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        code = 401 if self.path.endswith("/401") else 200
        if self.path.endswith("/slow"):
            time.sleep(0.1)                              # s per POST, so progress can be sampled
        body = b'{"detail": "Invalid access key"}' if code == 401 else b'{"detail": "ok"}'
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def deposits():
    """Every bookmark posted so far, across batches."""
    return [d for p in posts for d in p["deposits"]]


def done(core, timeout=5.0):
    """True once `core` reports a finished upload."""
    return wait_for(lambda: core.status_msg.endswith("uploaded"), timeout)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(cond, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()



server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}/upload"
upload.NEW_BOOKMARKS_CHECK_INTERVAL = 0.5    # s; read by the worker on each wait
expected = len(rs_api.bookmarks())

try:
    # 1. Linux: no LOCALAPPDATA
    env = {k: v for k, v in os.environ.items() if k != "LOCALAPPDATA"}
    env["XDG_DATA_HOME"] = os.path.join(OUT, "xdg")
    probe = ("import sys, types; sys.modules['config'] = types.SimpleNamespace(config=None); "
             "from rs_core import upload; print(upload.UPLOAD_DATA_FILEPATH)")
    run = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {PLUGIN!r}); {probe}"],
                         env=env, capture_output=True, text=True, cwd=OUT)
    out = run.stdout.strip()
    check("1 import without LOCALAPPDATA", run.returncode == 0, run.stderr.strip()[-200:])
    check("1 path under $XDG_DATA_HOME/RhinoSpotter",
          out.startswith(os.path.join(OUT, "xdg", "RhinoSpotter")), os.path.relpath(out, OUT) if out else "")

    # 2. Windows path
    check("2 upload data beside the db",
          str(upload.UPLOAD_DATA_FILEPATH).startswith(os.path.join(OUT, "RhinoSpotter")),
          os.path.relpath(str(upload.UPLOAD_DATA_FILEPATH), OUT))

    # 3. disabled
    config.set(upload.UPLOAD_URL_KEY, URL)
    config.set(upload.UPLOAD_ACCESS_KEY_KEY, "e2e-key")
    core = upload.UploadCore()
    proc0 = time.process_time()
    core.update(False)
    time.sleep(2.0)
    proc = time.process_time() - proc0
    check("3 disabled: no POST", not posts, f"{len(posts)} posts")
    check("3 disabled: no worker thread", not core.running())
    check("3 disabled: < 50 ms CPU in 2 s", proc < 0.05, f"{proc * 1000:.0f} ms")

    # 4. enabled
    core.update(True)
    got = done(core)
    sent = deposits()
    check("4 enabled: uploaded in batches of 50", got and len(posts) == -(-expected // 50), f"{len(posts)} posts")
    check("4 every bookmark sent", len(sent) == expected, f"{len(sent)} of {expected}")
    check("4 access key sent", got and posts[0].get("access_key") == "e2e-key")
    stored = [b.get("commander") for b in rs_api.bookmarks()]
    check("4 CMDR names sent as stored by default",
          bool(sent) and [b.get("commander") for b in sent] == stored)
    check("4 upload_data.json written",
          wait_for(lambda: upload.UPLOAD_DATA_FILEPATH.exists(), 2.0))

    # 5. next check
    time.sleep(1.5)
    check("5 nothing sent twice", len(deposits()) == expected, f"{len(deposits())} sent")
    t0 = time.monotonic()
    core.stop()
    check("5 stop() while idle", time.monotonic() - t0 < 1.5, f"{time.monotonic() - t0:.2f} s")

    # 6. CMDR name off
    upload.UPLOAD_DATA_FILEPATH.unlink()
    posts.clear()
    config.set(upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, False)
    named = upload.UploadCore()
    named.update(True)
    got = done(named)
    sent = [b.get("commander") for b in deposits()]
    check("6 CMDR name off: commander anonymous", got and bool(sent) and all(c == "anonymous" for c in sent),
          f"{sum(1 for c in sent if c == 'anonymous')} anonymous of {len(sent)}")
    named.stop()

    # 7. server down
    upload.UPLOAD_DATA_FILEPATH.unlink()
    config.set(upload.UPLOAD_URL_KEY, f"http://127.0.0.1:{free_port()}/upload")
    down = upload.UploadCore()
    down.update(True)
    in_retry = wait_for(lambda: "unreachable" in down.status_msg, 5.0)
    t0 = time.monotonic()
    down.stop()
    took = time.monotonic() - t0
    check("7 server down: in a retry wait, says check the URL",
          in_retry and "check the URL in Settings" in down.status_msg, down.status_msg)
    check("7 stop() within 1.5 s", took < 1.5, f"{took:.2f} s")

    # 11. plain http to a non-loopback host: refused before any request
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    config.set(upload.UPLOAD_URL_KEY, "http://upload.invalid/upload")
    plain = upload.UploadCore()
    plain.update(True)
    refused = wait_for(lambda: "https://" in plain.status_msg, 3.0)
    plain.stop()
    log = open(os.path.join(OUT, "upload.log"), encoding="utf-8").read() if os.path.exists(
        os.path.join(OUT, "upload.log")) else ""
    check("11 http URL refused, says what to do", refused, plain.status_msg)
    check("11 URL path not in the log", "/upload" not in log)

    # 12. 401: the panel line says to check the access key, no HTTP code on it
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    config.set(upload.UPLOAD_URL_KEY, URL + "/401")
    denied = upload.UploadCore()
    denied.update(True)
    said = wait_for(lambda: "Access Key" in denied.status_msg, 3.0)
    denied.stop()
    check("12 401: says check the access key in Settings",
          said and "check Access Key in Settings" in denied.status_msg, denied.status_msg)
    check("12 401: no HTTP code on the panel line", "401" not in denied.status_msg)

    # 13. 401: one POST per check, no retries; once the server takes it, the next check uploads
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    upload.UPLOAD_RETRY_WAIT = 0.1
    posts.clear()
    config.set(upload.UPLOAD_URL_KEY, URL + "/401")
    again = upload.UploadCore()
    again.update(True)
    wait_for(lambda: posts, 3.0)
    time.sleep(0.35)                                     # 3 retries 0.1 s apart fit; the 0.5 s check does not
    one_post = len(posts)
    config.set(upload.UPLOAD_URL_KEY, URL)
    recovered = wait_for(lambda: upload.UPLOAD_DATA_FILEPATH.exists(), 3.0)
    again.stop()
    check("13 401: one POST, not retried", one_post == 1, f"{one_post} posts")
    check("13 next check uploads once the server takes it", recovered, again.status_msg)

    # 15. upload_data.json broken: UploadCore() still builds, starts empty (plugin start depends on it)
    for label, content in (("not JSON", b"{oops"), ("a JSON list", b"[]"),
                           ("checksums a list", b'{"uploaded_bookmark_checksums": []}')):
        upload.UPLOAD_DATA_FILEPATH.write_bytes(content)
        try:
            built = upload.UploadCore()
            check(f"15 upload_data.json {label}: builds, empty",
                  built._uploaded_bookmarks_checksums == {}, repr(built._uploaded_bookmarks_checksums)[:60])
        except Exception as err:
            check(f"15 upload_data.json {label}: builds, empty", False, repr(err))
    upload.UPLOAD_DATA_FILEPATH.unlink()

    # 16. URL pasted with spaces around it: still sent
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    posts.clear()
    config.set(upload.UPLOAD_URL_KEY, "  " + URL + " " + chr(10))
    spaced = upload.UploadCore()
    spaced.update(True)
    sent = wait_for(lambda: posts, 3.0)
    spaced.stop()
    check("16 URL with spaces around it: uploaded", sent, spaced.status_msg)
    config.set(upload.UPLOAD_URL_KEY, URL)

    # 17. a bookmark with no system in the db (planet_name is NOT NULL): all still upload
    import sqlite3                                       # noqa: E402
    with sqlite3.connect(database.PATH) as db:
        db.execute("UPDATE bookmarks SET system = NULL, data = json_remove(data, '$.system') "
                   "WHERE id = (SELECT MIN(id) FROM bookmarks)")
    premise = any(b["system"] is None for b in rs_api.bookmarks())
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    posts.clear()
    nameless = upload.UploadCore()
    nameless.update(True)
    done(nameless)
    nameless.stop()
    count = len(deposits())
    check("17 premise: rs_api returns a bookmark with system None", premise)
    check("17 bookmark without system: all uploaded", count == len(rs_api.bookmarks()),
          f"{count} of {len(rs_api.bookmarks())}")

    # 18. worker only with URL and access key set
    config.set(upload.UPLOAD_URL_KEY, URL)
    config.set(upload.UPLOAD_ACCESS_KEY_KEY, "")
    keyless = upload.UploadCore()
    keyless.update(True)
    check("18 no access key: no worker, says set it", not keyless.running()
          and keyless.status_msg == "Set the upload access key in Settings", keyless.status_msg)
    config.set(upload.UPLOAD_ACCESS_KEY_KEY, "e2e-key")
    keyless.update(True)
    check("18 key set, OK again: worker runs", keyless.running())
    config.set(upload.UPLOAD_URL_KEY, "")
    keyless.update(True)
    check("18 URL cleared: worker stops, says set it", not keyless.running()
          and keyless.status_msg == "Set the upload server URL in Settings", keyless.status_msg)
    keyless.update(False)
    check("18 uploads off: no worker, no line", not keyless.running() and keyless.status_msg == "")
    config.set(upload.UPLOAD_URL_KEY, URL)

    # 20. Settings OK while the worker sleeps: checks at once, not at the next interval
    upload.NEW_BOOKMARKS_CHECK_INTERVAL = 60
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    posts.clear()
    awake = upload.UploadCore()
    awake.update(True)
    first = done(awake)
    after_first = len(posts)
    with sqlite3.connect(database.PATH) as db:
        db.execute("UPDATE bookmarks SET rigs = 99, data = json_set(data, '$.rigs', 99) "
                   "WHERE id = (SELECT MAX(id) FROM bookmarks)")
    t0 = time.monotonic()
    awake.update(True)                                   # what Settings OK calls
    second = wait_for(lambda: len(posts) > after_first, 3.0)
    took = time.monotonic() - t0
    awake.stop()
    upload.NEW_BOOKMARKS_CHECK_INTERVAL = 0.5
    check("20 first upload on start", first)
    check("20 OK uploads the changed bookmark within 3 s (interval 60 s)",
          second and len(posts[after_first]["deposits"]) == 1, f"{took:.2f} s, {len(posts)} posts")

    # 21. batches of UPLOAD_BATCH, progress (sent, total) meanwhile, None after
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    posts.clear()
    config.set(upload.UPLOAD_URL_KEY, URL + "/slow")
    batched = upload.UploadCore()
    seen = []
    batched.update(True)
    end = time.monotonic() + 5.0
    while time.monotonic() < end and not batched.status_msg.endswith("uploaded"):
        if batched.progress and batched.progress not in seen:
            seen.append(batched.progress)
        time.sleep(0.02)
    batched.stop()
    config.set(upload.UPLOAD_URL_KEY, URL)
    total = len(rs_api.bookmarks())
    sizes = [len(p["deposits"]) for p in posts]
    check("21 one POST per 50 bookmarks", sizes == [min(50, total - i) for i in range(0, total, 50)], str(sizes))
    check("21 progress seen rising, total right",
          len(seen) >= 3 and all(b[0] > a[0] for a, b in zip(seen, seen[1:])) and seen[0][1] == total,
          str(seen[:4]))
    check("21 progress None when done", batched.progress is None, batched.status_msg)

    # 8. _on_ui without an upload core
    import tkinter as tk                                 # noqa: E402
    import tkinter.ttk                                   # noqa: E402
    from rs_ui import main                               # noqa: E402
    root = tk.Tk()
    root.withdraw()
    main._frame, main._upload_core = tk.Frame(root), None
    try:
        main._on_ui(lambda: None)
        check("8 _on_ui with _upload_core None", True)
    except Exception as err:
        check("8 _on_ui with _upload_core None", False, repr(err))

    # 22. panel bar: shown with the progress, hidden without
    bar = tkinter.ttk.Progressbar(tk.Frame(root))
    bar.grid(row=10, column=0)
    bar.grid_remove()
    line = tk.Label(tk.Frame(root), text="")
    line.grid(row=9, column=0)
    main._upload_status, main._upload_bar = line, bar
    main._upload_core = types.SimpleNamespace(enabled=True, status_msg="", progress=(150, 379))
    main._set_upload_status("Uploading 150 of 379 bookmarks")
    shown = bar.winfo_manager() == "grid" and float(bar.cget("value")) == 150 and float(bar.cget("maximum")) == 379
    main._upload_core.progress = None
    main._set_upload_status("379 bookmarks uploaded")
    check("22 bar shown at 150 of 379", shown)
    check("22 bar hidden when done", bar.winfo_manager() == "")
    main._upload_core = main._upload_status = main._upload_bar = None

    # 9. _on_ui (called from hotkey, press and Spansh threads) leaves the upload core alone
    touched = []
    main._upload_core = types.SimpleNamespace(
        status_msg="", upload_bookmarks=lambda: touched.append("upload_bookmarks"))
    from_thread = threading.Thread(target=main._on_ui, args=(lambda: None,))
    from_thread.start()
    from_thread.join(2.0)
    check("9 _on_ui from a worker thread: upload core not touched", not touched, ",".join(touched))
    main._upload_core = None

    # 14. Panel upload line: hidden while off, shown once enabled without a restart
    line = tk.Label(tk.Frame(root), text="")
    line.grid(row=9, column=0)
    line.grid_remove()                                   # as _panel leaves it
    main._upload_status = line
    main._upload_core = types.SimpleNamespace(enabled=False, status_msg="")
    main._set_upload_status("12 bookmarks uploaded")
    hidden = line.winfo_manager() == ""
    main._upload_core.enabled = True                     # what prefs_changed sets
    main._set_upload_status("12 bookmarks uploaded")
    shown = line.winfo_manager() == "grid" and line.cget("text") == "12 bookmarks uploaded"
    main._upload_core.enabled = False
    main._set_upload_status("12 bookmarks uploaded")
    check("14 upload line hidden while off", hidden)
    check("14 shown once enabled, no restart", shown, line.cget("text"))
    check("14 hidden again when turned off", line.winfo_manager() == "")
    main._upload_core = main._upload_status = None

    # 10. Settings tab: "Send my CMDR name" ticked with nothing stored
    sys.modules["myNotebook"] = types.SimpleNamespace(Checkbutton=tk.Checkbutton, Label=tk.Label)
    del config.values[upload.UPLOAD_INCLUDE_CMDR_NAME_KEY]
    import importlib                                     # noqa: E402
    import rs_ui.upload as ui_upload                     # noqa: E402
    importlib.reload(ui_upload)
    ui_upload.prefs(tk.Frame(root))
    shown = ui_upload._upload_include_cmdr_name.get()
    ui_upload.prefs_changed()
    stored = config.get_bool(upload.UPLOAD_INCLUDE_CMDR_NAME_KEY)
    check("10 settings tab: CMDR name ticked by default", shown is True, repr(shown))
    check("10 OK without touching it stores True", stored is True, repr(stored))

    # 19. Settings OK with uploads on and no access key: a warning names it
    warned = []
    ui_upload.messagebox = types.SimpleNamespace(showwarning=lambda title, text: warned.append(text))
    ui_upload._upload_enabled.set(True)
    ui_upload._upload_url.set(URL)
    ui_upload._upload_access_key.set("")
    ui_upload.prefs_changed()
    check("19 OK, key empty: warning names the access key",
          len(warned) == 1 and "Set the upload access key in Settings" in warned[0], repr(warned))
    warned.clear()
    ui_upload._upload_access_key.set("e2e-key")
    ui_upload.prefs_changed()
    check("19 OK, both set: no warning", not warned, repr(warned))
    root.destroy()
except Exception:
    failed += 1
    lines.append(traceback.format_exc())
    print(lines[-1])
finally:
    server.shutdown()

passed = sum(line.startswith("PASS") for line in lines)
lines.append(f"\n{passed}/{passed + failed} passed")
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(lines[-1].strip(), " ", os.path.relpath(OUT, PLUGIN))
sys.exit(1 if failed else 0)
