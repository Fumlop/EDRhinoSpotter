r"""One RhinoSpotter per data folder: the EDMC plugin or standalone.py, first come.

%LOCALAPPDATA%\RhinoSpotter\db\instance.lock, 1 byte at LOCK_OFFSET locked with
msvcrt.locking(LK_NBLCK) (fcntl.flock off Windows), held until release() or
process exit - Windows drops the lock of a dead process. The file's text
names the holder for the refusal message; the locked byte sits past it so a
refused process can still read it.

No tkinter.
"""

import os

from rs_core import database
from rs_core.logging import logger

PATH = os.path.join(database.DIR, "instance.lock")
LOCK_OFFSET = 1 << 20          # 1 MiB, past any holder text
_fd = None


def _lock(fd):
    """Raises OSError when another process holds it."""
    try:
        import msvcrt
    except ImportError:                                  # not Windows
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)


def acquire(owner):
    """Take the lock as `owner` ("the EDMC plugin", "RhinoSpotter standalone").

    Returns None when this process holds it, else the holder's text.
    """
    global _fd
    if _fd is not None:
        return None
    os.makedirs(database.DIR, exist_ok=True)
    fd = os.open(PATH, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        _lock(fd)
    except OSError:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            holder = os.read(fd, 200).decode("utf-8", "replace").strip()
        finally:
            os.close(fd)
        return holder or "another RhinoSpotter"
    _fd = fd
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{owner} (pid {os.getpid()})".encode("utf-8"))
    except OSError as err:              # held, only the holder text is missing
        logger.warning(f"instance: could not write the holder to {PATH}: {err}")
    logger.info(f"instance: {owner} holds {PATH}")
    return None


def release():
    """Drop the lock. The file stays: deleting it races a process opening it."""
    global _fd
    if _fd is None:
        return
    try:
        import msvcrt
        os.lseek(_fd, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(_fd, msvcrt.LK_UNLCK, 1)      # LockFile docs: unlock before close
    except (ImportError, OSError):
        pass                                          # fcntl: close releases it
    try:
        os.close(_fd)
    except OSError:
        pass
    _fd = None
