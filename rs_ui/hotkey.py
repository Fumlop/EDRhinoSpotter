"""Two hotkeys for the minimap while you drive.

    Ctrl+Alt+Z  make where the SRV stands the centre of the map
    Ctrl+Alt+B  make where the SRV stands the location's border

Windows hotkeys, registered with RegisterHotKey on a thread of their own: the
game has the focus while you drive, so a key bound in Tk would never hear it.
RegisterHotKey delivers WM_HOTKEY to the thread that registered, which then
needs its own message loop - that is the whole of the thread.

The combinations are taken system-wide while EDMC runs. Ctrl+Alt+Z and
Ctrl+Alt+B: Ctrl+Alt+C, Ctrl+Shift+C and Ctrl+Shift+B were already held by
other programs on the machine this was written on (RegisterHotKey error 1409),
and the Ctrl keeps them clear of the NVIDIA overlay's Alt+Z. A combination
something else already holds is logged as a warning rather than silently
leaving a key that does nothing; the other one still works.

Callbacks run on this thread. The caller hands in something that bounces them
to Tk, the way every other worker in the plugin does.
"""

import threading

from rs_core.logging import logger

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# id -> (label, virtual key). Both are Ctrl+Alt.
CENTER = 0x5253             # 'RS'
BORDER = 0x5254
KEYS = {CENTER: ("Ctrl+Alt+Z", 0x5A), BORDER: ("Ctrl+Alt+B", 0x42)}
CENTER_LABEL = KEYS[CENTER][0]
BORDER_LABEL = KEYS[BORDER][0]

_thread = None
_thread_id = None


def start(callbacks):
    """Register the hotkeys and listen. `callbacks` is {CENTER: fn, BORDER: fn}.
    Safe to call twice; the second is ignored."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    try:
        import ctypes
        ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        logger.debug("hotkey: not Windows, no hotkeys")
        return
    ready = threading.Event()
    _thread = threading.Thread(target=_listen, args=(dict(callbacks), ready),
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


def _listen(callbacks, ready):
    global _thread_id
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    _thread_id = kernel32.GetCurrentThreadId()
    registered = []
    for key_id in callbacks:
        label, vk = KEYS[key_id]
        if user32.RegisterHotKey(None, key_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk):
            registered.append(key_id)
        else:
            logger.warning(f"hotkey: {label} is taken by another program, it does nothing here")
    ready.set()
    if not registered:
        _thread_id = None
        return
    try:
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY and message.wParam in callbacks:
                try:
                    callbacks[message.wParam]()
                except Exception:
                    logger.exception("hotkey: the press could not be handed on")
    finally:
        for key_id in registered:
            user32.UnregisterHotKey(None, key_id)
