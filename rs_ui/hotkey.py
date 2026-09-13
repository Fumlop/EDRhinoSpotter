"""Ctrl+Alt+Z: make where the SRV stands the centre of the map.

A Windows hotkey, registered with RegisterHotKey on a thread of its own: the
game has the focus while you drive, so a key bound in Tk would never hear it.
RegisterHotKey delivers WM_HOTKEY to the thread that registered, which then
needs its own message loop - that is the whole of the thread.

The combination is taken system-wide while EDMC runs. Ctrl+Alt+Z: Ctrl+Alt+C
and Ctrl+Shift+C were already held by other programs on the machine this was
written on (RegisterHotKey error 1409), and the Ctrl keeps it clear of the
NVIDIA overlay's Alt+Z. If something else already holds it, registering
fails, and that is logged as a warning rather than silently leaving a key that
does nothing.

The callback runs on this thread. The caller hands in something that bounces
it to Tk, the way every other worker in the plugin does.
"""

import threading

from rs_core.logging import logger

LABEL = "Ctrl+Alt+Z"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_Z = 0x5A
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x5253          # 'RS'

_thread = None
_thread_id = None


def start(callback):
    """Register the hotkey and listen. Safe to call twice; the second is ignored."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    try:
        import ctypes                                   # noqa: F401
        ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        logger.debug("hotkey: not Windows, no hotkey")
        return
    ready = threading.Event()
    _thread = threading.Thread(target=_listen, args=(callback, ready),
                               name="rhinospotter-hotkey", daemon=True)
    _thread.start()
    ready.wait(2.0)


def stop():
    """Unregister by ending the listening thread's message loop."""
    global _thread, _thread_id
    if _thread_id is not None:
        try:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(_thread_id, WM_QUIT, 0, 0)
        except (ImportError, AttributeError, OSError):
            pass
    if _thread is not None:
        _thread.join(1.0)
    _thread = _thread_id = None


def _listen(callback, ready):
    global _thread_id
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _thread_id = kernel32.GetCurrentThreadId()
    registered = user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_Z)
    ready.set()
    if not registered:
        logger.warning(f"hotkey: {LABEL} is taken by another program, the map centre "
                       f"cannot be set with it")
        _thread_id = None
        return
    try:
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY and message.wParam == HOTKEY_ID:
                try:
                    callback()
                except Exception:
                    logger.exception("hotkey: the centre could not be handed on")
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
