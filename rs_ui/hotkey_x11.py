"""Linux hotkeys: XGrabKey on the X root window, through ctypes and libX11.

Own Display connection, read on its own thread; Tk's connection is never
touched. Under Wayland the grab goes through XWayland and fires only while an
X11 window has the focus - Elite under Proton is one.

Each combo is grabbed four times: plain, with CapsLock (LockMask), with
NumLock (Mod2Mask), with both. XkbSetDetectableAutoRepeat: a held key is one
press. A combo another client holds (BadAccess) is a warning for that combo.

No tkinter. E2E: rs_e2etest/x11_e2e.py (Xvfb + xdotool, x11.md).
"""

import ctypes
import ctypes.util
import os
import select
import threading

from rs_core.logging import logger

SHIFT_MASK, LOCK_MASK, CONTROL_MASK, MOD1_MASK, MOD2_MASK = 1, 2, 4, 8, 16
MODIFIERS = {"Ctrl": CONTROL_MASK, "Alt": MOD1_MASK, "Shift": SHIFT_MASK}
IGNORED = (0, LOCK_MASK, MOD2_MASK, LOCK_MASK | MOD2_MASK)
KEY_PRESS, KEY_RELEASE = 2, 3
GRAB_MODE_ASYNC = 1
BAD_ACCESS = 10
POLL_S = 0.25


class XKeyEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("root", ctypes.c_ulong),
                ("subwindow", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("x_root", ctypes.c_int), ("y_root", ctypes.c_int),
                ("state", ctypes.c_uint), ("keycode", ctypes.c_uint),
                ("same_screen", ctypes.c_int)]


class XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xkey", XKeyEvent), ("pad", ctypes.c_long * 24)]


class XErrorEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("display", ctypes.c_void_p),
                ("resourceid", ctypes.c_ulong), ("serial", ctypes.c_ulong),
                ("error_code", ctypes.c_ubyte), ("request_code", ctypes.c_ubyte),
                ("minor_code", ctypes.c_ubyte)]


ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(XErrorEvent))

_thread = None
_stop = threading.Event()
_grabbed = {}            # key id -> combo, grabbed on the live display


def grabbed():
    """{key id: combo} held right now; empty when no grab is live."""
    return dict(_grabbed)


def _lib():
    name = ctypes.util.find_library("X11") or "libX11.so.6"
    x = ctypes.CDLL(name)
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XStringToKeysym.restype = ctypes.c_ulong
    x.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x.XKeysymToKeycode.restype = ctypes.c_ubyte
    x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
                           ctypes.c_int, ctypes.c_int, ctypes.c_int]
    x.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
    x.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x.XPending.argtypes = [ctypes.c_void_p]
    x.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
    x.XConnectionNumber.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x.XSetErrorHandler.restype = ctypes.c_void_p
    x.XSetErrorHandler.argtypes = [ctypes.c_void_p]
    x.XkbSetDetectableAutoRepeat.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    return x


def _keysym_name(key):
    """'Z' -> 'z', '5' -> '5', 'F3' -> 'F3': the XStringToKeysym name."""
    return key.lower() if len(key) == 1 else key


def start(combos, callbacks):
    """Grab {key id: 'Ctrl+Alt+Z'} and fire callbacks[key id] on a press.

    Returns {key id: combo} grabbed; {} when there is no X display or libX11,
    or nothing could be grabbed. Logs why. Safe to call twice: stops first.
    """
    global _thread
    stop()
    if not os.environ.get("DISPLAY"):
        logger.warning("hotkey: no DISPLAY, no X11 grab")
        return {}
    try:
        x = _lib()
    except OSError as err:
        logger.warning(f"hotkey: libX11 not loadable ({err}), no X11 grab")
        return {}
    ready = threading.Event()
    _stop.clear()
    _thread = threading.Thread(target=_listen, args=(x, dict(combos), dict(callbacks), ready),
                               name="rhinospotter-hotkey-x11", daemon=True)
    _thread.start()
    ready.wait(3.0)
    return grabbed()


def stop():
    """End the thread; it ungrabs and closes its display on the way out."""
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(2.0)
    _thread = None
    _grabbed.clear()


def _listen(x, combos, callbacks, ready):
    display = x.XOpenDisplay(None)
    if not display:
        logger.warning(f"hotkey: cannot open X display {os.environ.get('DISPLAY')!r}, no X11 grab")
        ready.set()
        return
    root = x.XDefaultRootWindow(display)
    errors = []

    # Xlib's error handler is process-wide: ours only while grabbing, and an
    # error on another display (Tk's) goes to the one it replaced.
    def on_error(err_display, event):
        if err_display == display:
            errors.append(event.contents.error_code)
            return 0
        return previous_fn(err_display, event) if previous_fn else 0

    handler = ERROR_HANDLER(on_error)
    previous = x.XSetErrorHandler(ctypes.cast(handler, ctypes.c_void_p))
    previous_fn = ERROR_HANDLER(previous) if previous else None

    keys = {}            # (keycode, modifier mask) -> key id
    held = []            # (keycode, mask) grabbed
    try:
        for key_id, combo in combos.items():
            *mods, key = combo.split("+")
            mask = 0
            for mod in mods:
                mask |= MODIFIERS[mod]
            keycode = x.XKeysymToKeycode(display, x.XStringToKeysym(_keysym_name(key).encode()))
            if not keycode:
                logger.warning(f"hotkey: {combo}: no keycode for {key!r} on this keyboard")
                continue
            del errors[:]
            for extra in IGNORED:
                x.XGrabKey(display, keycode, mask | extra, root, 1,
                           GRAB_MODE_ASYNC, GRAB_MODE_ASYNC)
            x.XSync(display, 0)
            if errors:
                for extra in IGNORED:
                    x.XUngrabKey(display, keycode, mask | extra, root)
                x.XSync(display, 0)
                logger.warning(f"hotkey: {combo} is taken by another program, it does nothing here"
                               f" (X error {errors[0]})")
                continue
            held.append((keycode, mask))
            keys[(keycode, mask)] = key_id
            _grabbed[key_id] = combo
    finally:
        x.XSetErrorHandler(previous)
    x.XkbSetDetectableAutoRepeat(display, 1, None)
    if _grabbed:
        logger.info(f"hotkey: X11 grab on {os.environ.get('DISPLAY')}: "
                    + ", ".join(_grabbed.values()))
    ready.set()

    down = set()
    event = XEvent()
    fd = x.XConnectionNumber(display)
    try:
        while held and not _stop.is_set():
            if not x.XPending(display):
                select.select([fd], [], [], POLL_S)
                continue
            x.XNextEvent(display, ctypes.byref(event))
            if event.type not in (KEY_PRESS, KEY_RELEASE):
                continue
            code = event.xkey.keycode
            mask = event.xkey.state & ~(LOCK_MASK | MOD2_MASK) & (SHIFT_MASK | CONTROL_MASK | MOD1_MASK)
            if event.type == KEY_RELEASE:
                down.discard(code)
                continue
            key_id = keys.get((code, mask))
            if key_id is None or code in down:
                continue
            down.add(code)
            try:
                callbacks[key_id]()
            except Exception:
                logger.exception("hotkey: the press could not be handed on")
    finally:
        for keycode, mask in held:
            for extra in IGNORED:
                x.XUngrabKey(display, keycode, mask | extra, root)
        x.XCloseDisplay(display)
        _grabbed.clear()
