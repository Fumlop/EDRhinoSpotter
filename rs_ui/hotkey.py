"""Four hotkeys for the map and the data, while the game has the focus.

    Ctrl+Alt+Z  make where the SRV stands the centre of the map
    Ctrl+Alt+B  make where the SRV stands the location's border
    Ctrl+Alt+M  zoom the map
    Ctrl+Alt+D  open the RhinoData window over the game

Those are the defaults. Each can be changed in EDMC Settings, RhinoSpotter
tab; label() says what a key is bound to now, and everything that names a key
asks it rather than keeping a copy.

Windows hotkeys, registered with RegisterHotKey on a thread of their own: the
game has the focus while you drive, so a key bound in Tk would never hear it.
RegisterHotKey delivers WM_HOTKEY to the thread that registered, which then
needs its own message loop - that is the whole of the thread.

The combinations are taken system-wide while EDMC runs. Ctrl+Alt+Z and
Ctrl+Alt+B: Ctrl+Alt+C, Ctrl+Shift+C and Ctrl+Shift+B were already held by
other programs on the machine this was written on (RegisterHotKey error 1409),
and the Ctrl keeps them clear of the NVIDIA overlay's Alt+Z. A combination
something else already holds is logged as a warning rather than silently
leaving a key that does nothing; the other one still works. Ctrl+Alt+M was
free here and is far less contested than those; a commander who has bound it
in the game loses it to EDMC while EDMC runs, with nothing to say so.

Callbacks run on this thread. The caller hands in something that bounces them
to Tk, the way every other worker in the plugin does.

Linux: an X11 grab instead (hotkey_x11), live only while an X11 window such
as Elite under Proton has the focus. Off Windows the same callbacks are also
fired by chat text, `!rs center` / `border` / `zoom` / `data`, read from the
journal's SendText event (chat()); with no grab live, label() names those.
"""

import string
import threading

from rs_core import system
from rs_core.logging import logger
from rs_ui import hotkey_x11, overlay

try:
    from config import config
except ImportError:      # running outside EDMC
    config = None

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

CENTER = 0x5253             # 'RS'
BORDER = 0x5254
SCAN = 0x5255
SIZE = 0x5256

# What each key does, its default, and where a change is kept in EDMC's
# config. In the order Settings lists them.
ACTIONS = ((CENTER, "Set center", "Ctrl+Alt+Z", "rhinospotter_hotkey_center"),
           (BORDER, "Set border", "Ctrl+Alt+B", "rhinospotter_hotkey_border"),
           (SIZE, "Zoom", "Ctrl+Alt+M", "rhinospotter_hotkey_zoom"),
           (SCAN, "Open RhinoData", "Ctrl+Alt+D", "rhinospotter_hotkey_data"))

# Off Windows: the chat command per key, typed in any chat channel.
CHAT_PREFIX = "!rs"
CHAT = {CENTER: "center", BORDER: "border", SIZE: "zoom", SCAN: "data"}

# What Settings offers: a modifier set and a key. Every set has two modifiers
# at least - one alone would steal ordinary typing.
MODIFIER_SETS = ("Ctrl+Alt", "Ctrl+Shift", "Alt+Shift", "Ctrl+Alt+Shift")
KEY_NAMES = (tuple(string.ascii_uppercase) + tuple(string.digits)
             + tuple(f"F{n}" for n in range(1, 13)))
MODIFIERS = {"Ctrl": MOD_CONTROL, "Alt": MOD_ALT, "Shift": MOD_SHIFT}

_thread = None
_thread_id = None
_callbacks = {}


def parse(combo):
    """'Ctrl+Alt+Z' -> (modifier flags, virtual key), or None for anything
    Settings could not have offered."""
    parts = (combo or "").split("+")
    mods, key = parts[:-1], parts[-1].upper()
    if "+".join(mods) not in MODIFIER_SETS or key not in KEY_NAMES:
        return None
    flags = 0
    for mod in mods:
        flags |= MODIFIERS[mod]
    vk = 0x70 + int(key[1:]) - 1 if len(key) > 1 else ord(key)
    return flags, vk


def available():
    """Whether the key combos work here: Windows, or a live X11 grab."""
    return overlay.win32() or bool(hotkey_x11.grabbed())


def chat_command(key_id):
    """'!rs center' for CENTER."""
    return f"{CHAT_PREFIX} {CHAT[key_id]}"


def chat(entry):
    """Off Windows: a SendText entry naming a chat command fires its callback.
    The key id fired, or None. On Windows always None."""
    if entry.get("event") != "SendText" or overlay.win32():
        return None
    typed = " ".join(str(entry.get("Message") or "").lower().split())
    for key_id, word in CHAT.items():
        if typed == f"{CHAT_PREFIX} {word}" and key_id in _callbacks:
            logger.info(f"hotkey: chat command {typed!r}")
            _callbacks[key_id]()
            return key_id
    return None


def _combo(key_id):
    """The combo set in Settings for this key, or its default."""
    for kid, _, default, config_key in ACTIONS:
        if kid == key_id:
            combo = config.get_str(config_key, default=default) if config is not None else default
            return combo if parse(combo) else default
    raise KeyError(key_id)


def label(key_id):
    """What a key is bound to now: the one set in Settings, or its default.
    With no key working here (no X11 grab) the chat command."""
    if not available():
        return chat_command(key_id)
    return _combo(key_id)


def restart():
    """Settings changed a key: drop the old combinations, take the new ones."""
    stop()
    if _callbacks:
        start(_callbacks)


def start(callbacks):
    """Register the hotkeys and listen. `callbacks` is {CENTER: fn, ...} over
    the ids in ACTIONS. Safe to call twice; the second is ignored."""
    global _thread, _callbacks
    _callbacks = dict(callbacks)
    if _thread is not None and _thread.is_alive():
        return
    if not overlay.win32():
        chat = ", ".join(chat_command(key_id) for key_id in CHAT)
        if system.LINUX:
            hotkey_x11.start({key_id: _combo(key_id) for key_id in _callbacks}, _callbacks)
        if not hotkey_x11.grabbed():
            logger.info(f"hotkey: no hotkeys here; type in chat: {chat}")
        return
    ready = threading.Event()
    _thread = threading.Thread(target=_listen, args=(dict(callbacks), ready),
                               name="rhinospotter-hotkey", daemon=True)
    _thread.start()
    ready.wait(2.0)


def stop():
    """Unregister by ending the listening thread's message loop."""
    global _thread, _thread_id
    hotkey_x11.stop()
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
        combo = label(key_id)
        flags, vk = parse(combo)
        if user32.RegisterHotKey(None, key_id, flags | MOD_NOREPEAT, vk):
            registered.append(key_id)
        else:
            logger.warning(f"hotkey: {combo} is taken by another program or another "
                           f"RhinoSpotter key, it does nothing here")
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
