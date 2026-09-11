"""Is there a newer release on GitHub?

Checks and reports. It does not download and it does not overwrite the folder
you are running from: an EDMC plugin that replaces its own files while EDMC
holds them open fails in ways that are hard to explain afterwards. The panel
shows the version and a link; the install is a human dropping a zip in place.

No tkinter, so the version comparison can be checked without EDMC in the way.
See rs_tests/test_update.py.
"""

import json
import re
import threading
import urllib.request

from rs_core.logging import logger

VERSION = "2.0.0"
REPO = "Fumlop/EDRhinoSpotter"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 10


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


def is_newer(latest, current=VERSION):
    """Strictly newer. Equal is not an update, and neither is older - a local
    build ahead of the release must not be told to downgrade."""
    return parse(latest) > parse(current)


def fetch_latest(url=RELEASES_URL, opener=urllib.request.urlopen):
    """The tag of the latest release, or None.

    None covers every failure the same way: no network, rate limited, repo not
    published yet. The plugin works offline, so none of them is worth a
    different message.
    """
    try:
        with opener(url, timeout=TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as err:                        # noqa: BLE001 - see docstring
        logger.debug(f"update check failed: {err}")
        return None
    return data.get("tag_name")


def check_async(callback):
    """Run fetch_latest off the UI thread and hand the callback (tag, is_newer).

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
