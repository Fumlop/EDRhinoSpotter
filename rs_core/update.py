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
import os
import re
import shutil
import tempfile
import threading
import urllib.request
import zipfile

from rs_core.logging import logger

try:
    import requests         # ships inside EDMC, with its own certificates
except ImportError:         # a bare interpreter without it
    requests = None

VERSION = "5.1.0-beta.1"

# For testing the update path without publishing a throwaway release: set
# RHINOSPOTTER_VERSION to something older and the running plugin will see the
# current release as new. It changes nothing else - what gets installed is
# still whatever the release actually contains.
RUNNING = os.environ.get("RHINOSPOTTER_VERSION") or VERSION
REPO = "Fumlop/EDRhinoSpotter"
# Not the GitHub API: it allows 60 requests an hour per address without a
# login, shared by everyone behind one router, and a player who hits it simply
# never hears of an update. The releases page redirects to the newest tag, and
# codeload serves that tag's source zip - the same <owner>-<repo>-<sha> folder
# inside that the API's zipball had. Neither is rate limited that way.
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
CODELOAD_ZIP = f"https://codeload.github.com/{REPO}/legacy.zip/refs/tags/{{tag}}"
TIMEOUT = 10
DOWNLOAD_TIMEOUT = 60

# A GitHub zipball wraps everything in one folder named <owner>-<repo>-<sha>.
ZIP_PREFIX = REPO.replace("/", "-") + "-"

# Never overwritten by an update:
#   lib/               vendored, gitignored, and therefore not in the zip - it
#                      is named here so a future release cannot quietly drop it.
# Cards and scans are not in this list because they do not live here: both sit
# under %LOCALAPPDATA%\RhinoSpotter, which an update never touches.
# The mining sheet is not kept either: a release carries the current one. It is
# mining_sheet.json since 4.1.4 because 4.1.3 and older keep ground_rules.json,
# and the updater doing the install is the old version's.
KEEP = ("lib", "data", "cards")


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


def _open(url, timeout):
    """GET `url`, following redirects, as a context manager with read() and
    geturl() - the shape urlopen has, so tests hand in either.

    Through `requests` when it is there, as EliteMeritTracker does: EDMC ships
    it with certifi and the system proxy settings, which is the path players'
    machines are known to allow. urllib otherwise.
    """
    if requests is None:
        return urllib.request.urlopen(url, timeout=timeout)
    response = requests.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            response.close()
            return False

        def read(self):
            return response.content

        def geturl(self):
            return response.url
    return Answer()


_warned = False


def fetch_latest(page=RELEASES_PAGE, opener=_open):
    """The newest release's tag, from where the releases/latest page redirects
    to, or None.

    None covers every failure the same way: no network, no releases yet, a page
    that did not land on a tag. The plugin works offline. A failure is a warning
    once a session - the check repeats hourly, and an offline evening is not
    worth 24 lines in EDMC's log.
    """
    global _warned
    try:
        with opener(page, timeout=TIMEOUT) as response:
            final = response.geturl()
    except Exception as err:                        # noqa: BLE001 - see docstring
        final = None
        reason = err
    else:
        reason = f"landed on {final}"
    match = re.search(r"/releases/tag/([^/?#]+)$", final or "")
    if match:
        return match.group(1)
    if not _warned:
        logger.warning(f"update check failed: {reason}; it tries again every hour")
        _warned = True
    else:
        logger.debug(f"update check failed: {reason}")
    return None


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


def download(url, opener=_open):
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
        tag = fetch_latest()
        if not tag:
            callback(False, "no answer from GitHub")
            return
        payload = download(CODELOAD_ZIP.format(tag=tag))
        if not payload:
            callback(False, "download failed")
            return
        ok = install(payload, target)
        callback(ok, f"{tag} installed, restart EDMC" if ok else "install failed, see the log")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
