"""Text onto the clipboard so it outlives the process.

Tk on Windows offers clipboard text by delayed rendering: once EDMC exits, the
text is gone (checked 2026-09-24, Python 3.13 / Tk 8.6). SetClipboardData with
CF_UNICODETEXT hands Windows the text itself. Elsewhere, Tk's own clipboard.
"""

import ctypes
import sys
import time

from rs_core.logging import logger

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# OpenClipboard fails while another program holds it: 10 tries, 10 ms apart.
OPEN_TRIES = 10


def copy(widget, text):
    """Put `text` on the clipboard. `widget` is any Tk widget, used off Windows
    and when the Win32 calls fail."""
    if sys.platform == "win32":
        try:
            if _win32(text):
                return
        except OSError as err:
            logger.warning(f"Win32 clipboard failed, using Tk's: {err}")
    widget.clipboard_clear()
    widget.clipboard_append(text)


def sequence():
    """GetClipboardSequenceNumber, which moves on every clipboard change. None off Windows."""
    if sys.platform != "win32":
        return None
    return ctypes.windll.user32.GetClipboardSequenceNumber()


def _win32(text):
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    data = text.encode("utf-16-le") + b"\0\0"
    for _ in range(OPEN_TRIES):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.01)
    else:
        logger.warning(f"clipboard busy: OpenClipboard failed {OPEN_TRIES} times")
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)     # still ours: Windows only owns it on success
            logger.warning(f"SetClipboardData failed: {ctypes.get_last_error()}")
            return False
        return True
    finally:
        user32.CloseClipboard()
