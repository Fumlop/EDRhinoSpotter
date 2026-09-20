"""All-or-nothing file writes.

Writes to a NamedTemporaryFile in the target's directory, then os.replace()
onto the target. A concurrent reader sees the old file or the new one.

On failure the temporary file is removed and the exception re-raised; the
target is unchanged. The target directory must exist.

Used for map pictures and migrate.done. No tkinter. Tests in
rs_tests/test_atomic.py.
"""

import os
import tempfile
import time

# os.replace raises PermissionError on Windows while another process holds the
# target open (an image viewer on a map picture). 5 tries, 50 ms apart.
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
