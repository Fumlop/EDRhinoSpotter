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
        body = b'{"detail": "Invalid access key"}' if code == 401 else b'{"detail": "ok"}'
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


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


def parked(core):
    """True when the worker thread's innermost frame is in threading's wait."""
    frame = sys._current_frames().get(core._upload_thread.ident)
    return frame is not None and frame.f_code.co_name == "wait"


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
    core = upload.UploadCore(enabled=False)
    proc0 = time.process_time()
    core.start()
    time.sleep(2.0)
    proc = time.process_time() - proc0
    check("3 disabled: no POST", not posts, f"{len(posts)} posts")
    check("3 disabled: worker parked in wait", parked(core))
    check("3 disabled: < 50 ms CPU in 2 s", proc < 0.05, f"{proc * 1000:.0f} ms")

    # 4. enabled
    core.enabled = True
    got = wait_for(lambda: posts, 3.0)
    sent = posts[0]["deposits"] if got else []
    check("4 enabled: one POST", got and len(posts) == 1, f"{len(posts)} posts")
    check("4 every bookmark sent", len(sent) == expected, f"{len(sent)} of {expected}")
    check("4 access key sent", got and posts[0].get("access_key") == "e2e-key")
    check("4 commander anonymous by default",
          bool(sent) and all(b.get("commander") == "anonymous" for b in sent))
    check("4 upload_data.json written",
          wait_for(lambda: upload.UPLOAD_DATA_FILEPATH.exists(), 2.0))

    # 5. next check
    time.sleep(1.5)
    check("5 nothing sent twice", len(posts) == 1, f"{len(posts)} posts")
    t0 = time.monotonic()
    core.stop()
    check("5 stop() while idle", time.monotonic() - t0 < 1.5, f"{time.monotonic() - t0:.2f} s")

    # 6. CMDR name on
    upload.UPLOAD_DATA_FILEPATH.unlink()
    posts.clear()
    config.set(upload.UPLOAD_INCLUDE_CMDR_NAME_KEY, True)
    named = upload.UploadCore(enabled=True)
    named.start()
    got = wait_for(lambda: posts, 3.0)
    stored = [b.get("commander") for b in rs_api.bookmarks()]
    sent = [b.get("commander") for b in posts[0]["deposits"]] if got else []
    check("6 CMDR name on: names sent as stored", got and sent == stored,
          f"{sum(1 for c in sent if c == 'anonymous')} anonymous of {len(sent)}")
    named.stop()

    # 7. server down
    upload.UPLOAD_DATA_FILEPATH.unlink()
    config.set(upload.UPLOAD_URL_KEY, f"http://127.0.0.1:{free_port()}/upload")
    down = upload.UploadCore(enabled=True)
    down.start()
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
    plain = upload.UploadCore(enabled=True)
    plain.start()
    refused = wait_for(lambda: "https://" in plain.status_msg, 3.0)
    plain.stop()
    log = open(os.path.join(OUT, "upload.log"), encoding="utf-8").read() if os.path.exists(
        os.path.join(OUT, "upload.log")) else ""
    check("11 http URL refused, says what to do", refused, plain.status_msg)
    check("11 URL path not in the log", "/upload" not in log)

    # 12. 401: the panel line says to check the access key, no HTTP code on it
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    config.set(upload.UPLOAD_URL_KEY, URL + "/401")
    denied = upload.UploadCore(enabled=True)
    denied.start()
    said = wait_for(lambda: "access key" in denied.status_msg, 3.0)
    denied.stop()
    check("12 401: says check the access key in Settings",
          said and "check the access key in Settings" in denied.status_msg, denied.status_msg)
    check("12 401: no HTTP code on the panel line", "401" not in denied.status_msg)

    # 13. 3 failed attempts, then the server works: the next check uploads (was off until restart)
    upload.UPLOAD_DATA_FILEPATH.unlink(missing_ok=True)
    upload.UPLOAD_RETRY_WAIT = 0.1
    posts.clear()
    config.set(upload.UPLOAD_URL_KEY, URL + "/401")
    again = upload.UploadCore(enabled=True)
    again.start()
    failed_round = wait_for(lambda: len(posts) >= upload.MAX_UPLOAD_ATTEMPTS, 3.0)
    config.set(upload.UPLOAD_URL_KEY, URL)
    recovered = wait_for(lambda: upload.UPLOAD_DATA_FILEPATH.exists(), 3.0)
    again.stop()
    check("13 3 attempts refused", failed_round, f"{len(posts)} posts")
    check("13 next check uploads once the server takes it", recovered, again.status_msg)

    # 8. _on_ui without an upload core
    import tkinter as tk                                 # noqa: E402
    from rs_ui import main                               # noqa: E402
    root = tk.Tk()
    root.withdraw()
    main._frame, main._upload_core = tk.Frame(root), None
    try:
        main._on_ui(lambda: None)
        check("8 _on_ui with _upload_core None", True)
    except Exception as err:
        check("8 _on_ui with _upload_core None", False, repr(err))

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

    # 10. Settings tab: "Include CMDR name" unticked with nothing stored
    sys.modules["myNotebook"] = types.SimpleNamespace(Checkbutton=tk.Checkbutton, Label=tk.Label)
    del config.values[upload.UPLOAD_INCLUDE_CMDR_NAME_KEY]
    import importlib                                     # noqa: E402
    import rs_ui.upload as ui_upload                     # noqa: E402
    importlib.reload(ui_upload)
    ui_upload.prefs(tk.Frame(root))
    shown = ui_upload._upload_include_cmdr_name.get()
    ui_upload.prefs_changed()
    stored = config.get_bool(upload.UPLOAD_INCLUDE_CMDR_NAME_KEY)
    check("10 settings tab: CMDR name unticked by default", shown is False, repr(shown))
    check("10 OK without touching it stores False", stored is False, repr(stored))
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
