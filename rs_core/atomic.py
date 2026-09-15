"""A file written whole or not at all.

Written to a temporary file beside the target and moved onto it: EDMC can be
closed at any moment, and the minimap reads bookmarks while the worker thread
writes them. A reader sees the old file or the new one, never half of one.

On failure the temporary file is removed and the error raised; the target is
left as it was. The folder has to exist - the callers make it.

No tkinter. See rs_tests/test_atomic.py.
"""

import os
import tempfile
import time

# Windows refuses to replace a file another thread has open - the minimap
# reading the bookmark being updated. A read takes well under a millisecond,
# so a few short waits get past it.
REPLACE_TRIES = 5
REPLACE_WAIT_S = 0.05


def _replace(src, dst):
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT_S)


def _write(path, mode, content, **open_args):
    handle = tempfile.NamedTemporaryFile(mode, dir=os.path.dirname(path) or ".",
                                         suffix=".tmp", delete=False, **open_args)
    try:
        with handle:
            handle.write(content)
        _replace(handle.name, path)
    except BaseException:
        try:
            os.remove(handle.name)
        except OSError:
            pass
        raise


def write_text(path, text):
    _write(path, "w", text, encoding="utf-8")


def write_bytes(path, data):
    _write(path, "wb", data)
