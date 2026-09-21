"""E2E harness for the in-plugin updater, rs_core/update.py. Checks and gaps: update.md.

Run from anywhere:  python rs_e2etest/update_e2e.py
Writes rs_e2etest/out/<timestamp>/report.txt. Exit code 1 on a failure.
Network: github.com, codeload.github.com, api.github.com (read only).
The install target is out/<timestamp>/plugin, a `git archive HEAD` of this repo:
rs_core is imported from there, so install_async's default target is the copy.
LOCALAPPDATA points at out/<timestamp>/localappdata before rs_core loads.
"""

import functools
import hashlib
import http.server
import io
import logging
import os
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", time.strftime("%Y%m%d-%H%M%S"))
DATA = os.path.join(OUT, "localappdata")
COPY = os.path.join(OUT, "plugin")
OLDER = "5.6.1"                     # RHINOSPOTTER_VERSION for the run
LIVE_DATA = os.path.join(os.environ["LOCALAPPDATA"], "RhinoSpotter")

os.makedirs(DATA)
os.makedirs(COPY)


def git(*args):
    return subprocess.run(["git", "-C", PLUGIN, *args], capture_output=True, check=True).stdout


def snapshot(root, skip=()):
    """relpath -> (size, mtime_ns) of every file under root, `skip` top-level names left out."""
    files = {}
    for folder, dirs, names in os.walk(root):
        if folder == root:
            dirs[:] = [d for d in dirs if d not in skip]
        for name in names:
            path = os.path.join(folder, name)
            stat = os.stat(path)
            files[os.path.relpath(path, root)] = (stat.st_size, stat.st_mtime_ns)
    return files


def contents(root):
    """relpath (forward slashes) -> sha1 of the bytes, every file under root."""
    files = {}
    for folder, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                files[os.path.relpath(path, root).replace(os.sep, "/")] = \
                    hashlib.sha1(handle.read()).hexdigest()
    return files


def blob_sha(data):
    """git's blob id: sha1 over b"blob <len>\\0" + bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


live_plugin_before = snapshot(PLUGIN, skip=("rs_e2etest",))
live_data_before = snapshot(LIVE_DATA) if os.path.isdir(LIVE_DATA) else {}

with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD"))) as tar:
    tar.extractall(COPY, filter="data")

os.environ["LOCALAPPDATA"] = DATA
os.environ["RHINOSPOTTER_VERSION"] = OLDER
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, COPY)

import requests                                          # noqa: E402

from rs_core import update                               # noqa: E402

assert os.path.dirname(os.path.dirname(os.path.abspath(update.__file__))) == COPY, update.__file__

log_lines = []
handler = logging.StreamHandler(type("W", (), {"write": lambda s, m: log_lines.append(m),
                                                "flush": lambda s: None})())
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
update.logger.addHandler(handler)

results = []
notes = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def note(text):
    notes.append(text)
    print("INFO " + text, flush=True)


def run_install(timeout=120):
    """install_async() with no plugin_dir, as rs_ui/main.py:651 calls it. Returns (ok, message)."""
    done = threading.Event()
    answer = []
    update.install_async(lambda ok, message: (answer.append((ok, message)), done.set()))
    if not done.wait(timeout):
        return None, f"no callback in {timeout} s"
    return answer[0]


def start_plugin():
    """import load from the copy and call plugin_start3 in a fresh interpreter. Returns stdout lines."""
    code = (
        "import sys, os; sys.path.insert(0, os.getcwd()); import load, rs_core, rs_ui\n"
        "from rs_ui import main\n"
        "print('name', load.plugin_start3(os.getcwd()))\n"
        "print('version', load.VERSION, load.__version__)\n"
        "print('sheet', main._sheet.loaded)\n"
        "print('files', all(os.path.abspath(m.__file__).startswith(os.getcwd())"
        " for m in (load, rs_core, rs_ui, main)))\n"
    )
    env = dict(os.environ)
    env.pop("RHINOSPOTTER_VERSION")
    proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=COPY, env=env,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode:
        return {"error": proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "exit"}
    return dict(line.split(" ", 1) for line in proc.stdout.splitlines() if " " in line)


class Serve(http.server.BaseHTTPRequestHandler):
    """GET /<name> -> PAYLOADS[name] with 200, anything else 404."""
    payloads = {}

    def do_GET(self):
        body = self.payloads.get(self.path.lstrip("/"))
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Serve)
threading.Thread(target=server.serve_forever, daemon=True).start()
LOCAL = f"http://127.0.0.1:{server.server_port}"
silent = socket.socket()                        # accepts via backlog, never answers
silent.bind(("127.0.0.1", 0))
silent.listen(5)
SILENT = f"http://127.0.0.1:{silent.getsockname()[1]}/releases/latest"
REFUSED = "https://127.0.0.1:9/releases/latest"
NO_DNS = "https://rhinospotter-e2e.invalid/releases/latest"

original_zip_url = update.CODELOAD_ZIP
original_fetch = update.fetch_latest
tag = None
payload = None

try:
    # 1. Version constants in the copy.
    with open(os.path.join(COPY, "CHANGELOG.md"), encoding="utf-8") as handle:
        headings = [line.strip() for line in handle if line.startswith("## ")]
    check("1 changelog leads with update.VERSION", headings and headings[0] == f"## {update.VERSION}",
          f"{headings[0] if headings else None} vs {update.VERSION}")
    check("1 VERSION is three numbers", len(update.VERSION.split(".")) == 3
          and update.parse(update.VERSION) != (0, 0, 0), update.VERSION)
    check("1 RHINOSPOTTER_VERSION read at import", update.RUNNING == OLDER, update.RUNNING)
    before = start_plugin()
    check("1 load.py exposes VERSION and __version__ before the update",
          before.get("version") == f"{update.VERSION} {update.VERSION}", str(before))

    # 2. Latest release detection against the live release page.
    tag = update.fetch_latest()
    local_tags = git("tag", "--sort=-v:refname").decode().split()
    try:
        api = requests.get(f"https://api.github.com/repos/{update.REPO}/releases?per_page=100",
                           timeout=15)
        api.raise_for_status()
        releases = [r["tag_name"] for r in api.json() if not r["draft"] and not r["prerelease"]]
    except Exception as err:                    # noqa: BLE001 - oracle only
        releases = local_tags
        note(f"GitHub API not usable ({err}); latest checked against local tags only")
    newest_api = max(releases, key=update.parse) if releases else None
    check("2 fetch_latest = newest release (API) = newest local tag",
          tag and tag == local_tags[0] and (newest_api is None or tag == newest_api),
          f"page {tag}, api {newest_api}, git {local_tags[0]}")
    unreadable = [r for r in releases if update.parse(r) == (0, 0, 0)]
    check("2 every published release tag parses", releases and not unreadable,
          f"{len(releases)} releases, unreadable {unreadable}")
    order = sorted(releases, key=update.parse, reverse=True)
    check("2 parse order matches git's version order", order == [t for t in local_tags if t in releases],
          f"{order[:4]}")

    done = threading.Event()
    seen = []
    update.check_async(lambda t, newer: (seen.append((t, newer)), done.set()))
    done.wait(30)
    check("2 check_async with RUNNING older reports the release as new", seen == [(tag, True)], str(seen))
    check("2 the same tag against VERSION is not an update", tag and not update.is_newer(tag, update.VERSION))
    check("2 a local build ahead is not told to downgrade", tag and not update.is_newer(tag, "99.0.0"))
    check("2 unparsable tags never count as newer",
          not any(update.is_newer(t, "0.0.1") for t in ("", None, "latest", "nightly")))

    # 3. Download of the real zip.
    url = update.CODELOAD_ZIP.format(tag=tag)
    payload = update.download(url)
    check("3 download returns bytes", payload, f"{len(payload or b'')} bytes from {url}")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        bad = archive.testzip()
        names = archive.namelist()
        root = update.release_root(names)
        entries = {n[len(root) + 1:]: archive.read(n) for n in names
                   if root and not n.endswith("/") and n.startswith(root + "/")}
    check("3 zip CRCs all good", bad is None, f"first bad {bad}")
    check("3 one wrapper folder with the repo prefix",
          root and all(n.split("/")[0] == root for n in names), root)
    tree = {}
    for line in git("ls-tree", "-r", tag).decode().splitlines():
        meta, path = line.split("\t", 1)
        tree[path] = meta.split()[2]
    mismatched = sorted(p for p in tree if p not in entries or blob_sha(entries[p]) != tree[p])
    extra = sorted(set(entries) - set(tree))
    check(f"3 zip = git tree of {tag}, blob for blob", not mismatched and not extra,
          f"{len(tree)} blobs, mismatched {mismatched[:5]}, extra {extra[:5]}")

    # 4. Refused installs from a local server leave the copy as it was.
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        foreign = io.BytesIO()
        with zipfile.ZipFile(foreign, "w", zipfile.ZIP_DEFLATED) as out:
            for info in source.infolist():
                out.writestr(info.filename.replace(root, "Someone-Else-abc1234", 1),
                             source.read(info))
    flipped = bytearray(payload)
    middle = len(flipped) // 2
    flipped[middle:middle + 64] = bytes(b ^ 0xFF for b in flipped[middle:middle + 64])
    Serve.payloads.update({
        "truncated.zip": payload[:len(payload) // 2],
        "flipped.zip": bytes(flipped),
        "foreign.zip": foreign.getvalue(),
        "empty.zip": b"",
        "no-entries.zip": b"PK\x05\x06" + bytes(18),       # end-of-central-directory only
    })
    cases = [
        ("truncated zip (first half)", "truncated.zip", "install failed, see the log"),
        ("64 bytes flipped mid-zip", "flipped.zip", "install failed, see the log"),
        ("zip with root Someone-Else-abc1234", "foreign.zip", "install failed, see the log"),
        ("valid zip with no entries", "no-entries.zip", "install failed, see the log"),
        ("HTTP 404", "missing.zip", "download failed"),
        ("HTTP 200 with an empty body", "empty.zip", "download failed"),
    ]
    for label, name, expected in cases:
        update.CODELOAD_ZIP = f"{LOCAL}/{name}"
        before_copy = contents(COPY)
        got = run_install()
        after_copy = contents(COPY)
        changed = sorted(set(before_copy.items()) ^ set(after_copy.items()))
        check(f"4 {label}: refused as '{expected}'", got == (False, expected), str(got))
        check(f"4 {label}: copy unchanged, no rs_update_ folder", not changed,
              f"{len(changed)} differences {changed[:3]}")
    update.CODELOAD_ZIP = original_zip_url

    # 5. No network: reported, never raised.
    update._warned = False
    warnings_before = sum("WARNING update check failed" in line for line in log_lines)
    for label, page in (("connection refused", REFUSED), ("no DNS", NO_DNS)):
        started = time.monotonic()
        try:
            got = update.fetch_latest(page=page)
            raised = None
        except Exception as err:                # noqa: BLE001 - what is checked
            got, raised = "raised", err
        check(f"5 {label}: fetch_latest is None", got is None and raised is None,
              f"{got} {raised or ''} in {time.monotonic() - started:.1f} s")
    started = time.monotonic()
    got = update.fetch_latest(page=SILENT)
    took = time.monotonic() - started
    check(f"5 host that never answers: None within TIMEOUT {update.TIMEOUT} s + 5 s",
          got is None and took < update.TIMEOUT + 5, f"{got} in {took:.1f} s")
    warned = sum("WARNING update check failed" in line for line in log_lines) - warnings_before
    check("5 three failures log one warning", warned == 1, f"{warned} warnings")
    check("5 a page that lands off a tag is None",
          update.fetch_latest(page=f"https://github.com/{update.REPO}/releases") is None)

    update.fetch_latest = functools.partial(original_fetch, page=REFUSED)
    before_copy = contents(COPY)
    got = run_install()
    check("5 install_async with GitHub unreachable", got == (False, "no answer from GitHub"), str(got))
    update.fetch_latest = original_fetch
    update.CODELOAD_ZIP = "https://127.0.0.1:9/{tag}.zip"
    got = run_install()
    check("5 install_async with codeload unreachable", got == (False, "download failed"), str(got))
    update.CODELOAD_ZIP = original_zip_url
    check("5 copy unchanged after both", contents(COPY) == before_copy)

    # 6. The real install over the copy.
    for name in ("README.md", "mining_sheet.json"):
        with open(os.path.join(COPY, name), "a", encoding="utf-8") as handle:
            handle.write("\nlocal edit, update_e2e\n")
    sentinels = [os.path.join(COPY, *p) for p in
                 (("lib", "keep.txt"), ("data", "keep.txt"), ("cards", "keep.txt"))]
    stale_inside = os.path.join(COPY, "rs_core", "stale_e2e.py")
    stale_top = os.path.join(COPY, "stale_e2e.txt")
    for path in sentinels + [stale_inside, stale_top]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("update_e2e")

    got = run_install()
    check("6 install_async installs the release", got == (True, f"{tag} installed, restart EDMC"), str(got))
    installed = contents(COPY)
    wrong = sorted(p for p in tree if installed.get(p) != hashlib.sha1(entries[p]).hexdigest())
    check(f"6 every file of {tag} is in the copy byte for byte", not wrong,
          f"{len(tree)} files, wrong {wrong[:5]}")
    check("6 lib/, data/, cards/ kept", all(os.path.isfile(p) for p in sentinels))
    check("6 stale file inside a replaced folder removed", not os.path.exists(stale_inside))
    leftovers = [n for n in os.listdir(COPY) if n.startswith("rs_update_")]
    check("6 no rs_update_ temp folder left", not leftovers, str(leftovers))
    if os.path.exists(stale_top):
        note("a top-level file not in the release survives the update (stale_e2e.txt): "
             "install() copies over, never deletes top-level entries")

    after = start_plugin()
    check("6 updated plugin imports and plugin_start3 returns RhinoSpotter",
          after.get("name") == "RhinoSpotter", str(after))
    check(f"6 updated plugin reports {tag}",
          after.get("version") == f"{tag.lstrip('v')} {tag.lstrip('v')}", after.get("version", ""))
    check("6 updated plugin loads its mining sheet", after.get("sheet") == "True", str(after.get("sheet")))
    check("6 updated plugin runs from the copy", after.get("files") == "True", str(after.get("files")))

except Exception:                               # noqa: BLE001 - reported, then exit 1
    import traceback
    check("harness ran to the end", False, traceback.format_exc().strip().splitlines()[-1])
    traceback.print_exc()
finally:
    update.CODELOAD_ZIP = original_zip_url
    update.fetch_latest = original_fetch
    server.shutdown()
    silent.close()

check("live plugin folder untouched", snapshot(PLUGIN, skip=("rs_e2etest",)) == live_plugin_before)
check("live %LOCALAPPDATA%\\RhinoSpotter untouched",
      (snapshot(LIVE_DATA) if os.path.isdir(LIVE_DATA) else {}) == live_data_before)

failed = [r for r in results if not r[1]]
with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as report:
    report.write(f"update E2E  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.write(f"release {tag}  RHINOSPOTTER_VERSION {OLDER}  copy {COPY}\n")
    report.write(f"{len(results) - len(failed)}/{len(results)} passed\n\n")
    for name, ok, detail in results:
        report.write(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else "") + "\n")
    for text in notes:
        report.write("INFO " + text + "\n")
    report.write("\n--- plugin log ---\n" + "".join(log_lines))
print(f"{len(results) - len(failed)}/{len(results)} passed  ->  {OUT}")
sys.exit(1 if failed else 0)
