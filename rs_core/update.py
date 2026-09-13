"""Is there a newer release, and put it in place if there is.

Downloads the GitHub zipball, extracts it to a temporary folder beside the
plugin, and copies the result over. EDMC keeps the running .py files open on
Windows but does not lock them, so replacing them works - what does not work
is expecting the new code to run before EDMC is restarted, which is why the
button says so afterwards.

No tkinter, so all of it can be checked without EDMC in the way. The parts
worth checking are pure: which folder inside the zip is the release, and which
of its entries may overwrite what is here. See rs_tests/test_update.py.
"""

import io
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.request
import zipfile

from rs_core.logging import logger

VERSION = "3.5.1"

# For testing the update path without publishing a throwaway release: set
# RHINOSPOTTER_VERSION to something older and the running plugin will see the
# current release as new. It changes nothing else - what gets installed is
# still whatever the release actually contains.
RUNNING = os.environ.get("RHINOSPOTTER_VERSION") or VERSION
REPO = "Fumlop/EDRhinoSpotter"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 10
DOWNLOAD_TIMEOUT = 60

# A GitHub zipball wraps everything in one folder named <owner>-<repo>-<sha>.
ZIP_PREFIX = REPO.replace("/", "-") + "-"

# Never overwritten by an update:
#   ground_rules.json  a locally refreshed sheet is newer than the one in a
#                      release, so the release must not overwrite it.
#   lib/               vendored, gitignored, and therefore not in the zip - it
#                      is named here so a future release cannot quietly drop it.
# Cards and scans are not in this list because they do not live here: both sit
# under %LOCALAPPDATA%\RhinoSpotter, which an update never touches.
KEEP = ("ground_rules.json", "lib", "data", "cards")


def parse(version):
    """'v2.1.0-beta' -> (2, 1, 0). Anything unparsable sorts lowest, so a tag
    nobody can read never announces itself as an update."""
    numbers = re.findall(r"\d+", version or "")
    if not numbers:
        return (0, 0, 0)
    parts = [int(number) for number in numbers[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(latest, current=None):
    """Strictly newer. Equal is not an update, and neither is older - a local
    build ahead of the release must not be told to downgrade."""
    return parse(latest) > parse(current if current is not None else RUNNING)


def fetch_release(url=RELEASES_URL, opener=urllib.request.urlopen):
    """The latest release as GitHub describes it, or None.

    None covers every failure the same way: no network, rate limited, repo has
    no releases yet. The plugin works offline, so none of them is worth a
    different message.
    """
    try:
        with opener(url, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as err:                        # noqa: BLE001 - see docstring
        logger.debug(f"update check failed: {err}")
        return None


def fetch_latest(url=RELEASES_URL, opener=urllib.request.urlopen):
    """Just the tag of the latest release, or None."""
    release = fetch_release(url, opener)
    return release.get("tag_name") if release else None


def check_async(callback):
    """Run the check off the UI thread and hand the callback (tag, is_newer).

    The callback lands on a worker thread. A tkinter caller has to bounce it
    back with widget.after - Tk is not thread-safe and a panel written from
    here crashes EDMC minutes later, somewhere else.
    """
    def run():
        tag = fetch_latest()
        callback(tag, bool(tag) and is_newer(tag))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def release_root(names):
    """The single folder a zipball wraps everything in, or None.

    Matched on the prefix rather than "whatever the first entry is": a zip that
    is not the one we asked for should fail here, before anything is copied
    over a working install.
    """
    for name in names:
        head = name.split("/")[0]
        if head.startswith(ZIP_PREFIX):
            return head
    return None


def should_copy(name):
    """Whether an entry from the release may replace what is here."""
    return name not in KEEP


def install(zip_bytes, plugin_dir, keep=KEEP):
    """Unpack a zipball over the plugin folder. Returns True if it went in.

    Extracted to a temporary folder first and copied in a second pass, so a
    truncated download cannot leave half a plugin behind - the zip has to be
    readable and carry the expected folder before anything here is touched.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            root = release_root(archive.namelist())
            if not root:
                logger.error(f"not a {REPO} release zip")
                return False
            temp_dir = tempfile.mkdtemp(prefix="rs_update_", dir=plugin_dir)
            try:
                archive.extractall(temp_dir)
                source = os.path.join(temp_dir, root)
                for name in sorted(os.listdir(source)):
                    if name in keep:
                        logger.info(f"keeping local {name}")
                        continue
                    _replace(os.path.join(source, name),
                             os.path.join(plugin_dir, name))
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as err:                        # noqa: BLE001
        logger.exception("update failed")
        logger.error(f"update failed: {err}")
        return False
    return True


def _replace(source, target):
    if os.path.isdir(source):
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def download(url, opener=urllib.request.urlopen):
    """The bytes of a release zip, or None."""
    try:
        with opener(url, timeout=DOWNLOAD_TIMEOUT) as response:
            return response.read()
    except Exception as err:                        # noqa: BLE001
        logger.error(f"could not download the update: {err}")
        return None


def install_async(callback, plugin_dir=None):
    """Fetch the latest release and put it in place, off the UI thread.

    `callback(ok, message)` lands on a worker thread, so a tkinter caller has
    to bounce it back with widget.after.
    """
    target = plugin_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def run():
        release = fetch_release()
        if not release:
            callback(False, "no answer from GitHub")
            return
        url = release.get("zipball_url")
        if not url:
            callback(False, "release has no zip")
            return
        payload = download(url)
        if not payload:
            callback(False, "download failed")
            return
        ok = install(payload, target)
        callback(ok, f"{release.get('tag_name', 'update')} installed, restart EDMC"
                 if ok else "install failed, see the log")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
