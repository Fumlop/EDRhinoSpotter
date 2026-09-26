"""The arrow over the game: where the bookmarked patch is from here.

A borderless, always-on-top window with a transparent background, parked at
the top middle of the Elite window. Only what is drawn is visible, and it is
click-through, so it is something to look at rather than something in the way.

It reads Status.json on a timer and rs_core.guide turns that into an angle.
Nothing is saved and nothing is sent anywhere.

Borderless and windowed are what this is built for. Fullscreen usually works
too - Windows turns most of it into a flip-model borderless behind the scenes,
which is why other overlays manage it - so the arrow is put up either way. It
hides while Elite is not the window in front, game not running included. The one thing
it cannot do anything about is the heading: without one from the game the
arrow can only point north-up, and it says so.

Nothing in here raises at the caller. A window that cannot be built is logged
and skipped - the bookmark list is still a bookmark list without an arrow over
the game.
"""

import base64
import io
import time
import tkinter as tk

from rs_core import arrow, guide, palette, spotmark
from rs_core.logging import logger

try:
    from config import config
except ImportError:      # running outside EDMC
    config = None

# The colour the window is filled with and then told to make a hole of. Not a
# palette colour: anything drawn in it would be a hole too. rs_core.arrow
# renders onto the same one, and keeps its faces clear of it.
KEY = arrow.KEY

WIDTH = 240
HEIGHT = 190
POLL_MS = 500

# How often set_topmost re-sends HWND_TOPMOST for a window that has not moved,
# seconds. A move, or a window just shown again, is sent at once.
TOPMOST_EVERY_S = 5

# How long a message stays up before the overlay takes itself down, when it
# never managed to point anywhere. You pressed Guide on the wrong body, it says
# so, and then it is gone - nobody should have to press Stop to clear a
# message. Long enough to read it twice.
NOTICE_MS = 10000

# How long HERE stays up before the guide stops itself. You are there; the
# arrow has nothing left to say, and Stop should not be a chore.
HERE_MS = 10000

# The Elite window carries this title in every build so far; the window class
# has not been as stable.
GAME_TITLE = "Elite - Dangerous (CLIENT)"
GAME_TITLE_PREFIX = "Elite - Dangerous"

# Off Windows: where the arrow was dragged, "x,y" screen pixels of its top left.
# No game window to find there, and the screen centre of two monitors is the seam.
POS_KEY = "rhinospotter_arrow_xy"

FG = palette.FG
DIM = palette.MUTED
ACCENT = palette.ACCENT
GOOD = palette.GOOD
WARN = palette.WARN

_window = None
_canvas = None
_target = None
_after = None
_placed = None           # the last geometry, so the game standing still is free
_on_stop = None          # the row that started this, to redraw when it ends
_since = None            # when the current no-arrow state began
_here = None             # when HERE was first shown on this run
_pointed = False         # whether this run ever drew an arrow
_hidden = False          # hidden because Elite is not the window in front
_frames = {}             # (bucket, colour) -> PhotoImage, built as angles come up
_typed_user32 = None     # own WinDLL: argtypes set here stay off EDMC's ctypes.windll.user32
_topmost_errors = {}     # handle -> last SetWindowPos error, logged when it changes
_topmost_sent = {}       # handle -> ((x, y, width, height), monotonic s) of the last send
_grab = None             # (pointer x, pointer y, window x, window y) while dragging, off Windows


def _key(record):
    """What makes two bookmarks the same one.

    Not the dict itself: the scan window rebuilds its rows, so the object
    guiding started with is gone by the time a button asks whether it is still
    the one being guided to.
    """
    if not record:
        return None
    return (record.get("planet_name"), record.get("location_index"),
            str(record.get("marked_at")))


def guiding(record=None):
    """Whether the overlay is up, and pointing at this bookmark if given."""
    if _window is None or not _window.winfo_exists():
        return False
    return record is None or _key(record) == _key(_target)


def start(parent, record, on_stop=None):
    """Point at this bookmark. A second call retargets rather than stacking.

    `on_stop` is called when the overlay takes itself down, so the button that
    started it can go back to saying Guide.
    """
    global _window, _canvas, _target, _placed, _on_stop, _since, _pointed, _here
    _target = record
    _on_stop = on_stop
    _since = _here = None
    _pointed = False
    if guiding():
        # The pending tick first. Without this, retargeting books a second
        # timer beside the first and every press after that doubles the rate.
        _cancel()
        _tick()
        return _window

    # The root, not the window that asked: the scan window is disposable and
    # the arrow has to outlive it - you close the list and fly.
    root = parent.master or parent
    try:
        _window = tk.Toplevel(root)
        _window.overrideredirect(True)
        _window.configure(bg=KEY)
        _window.attributes("-topmost", True)
        try:
            _window.attributes("-transparentcolor", KEY)
        except tk.TclError:      # not Windows: a solid panel rather than nothing
            logger.warning("overlay: no transparent colour here, drawing solid")
        _canvas = tk.Canvas(_window, width=WIDTH, height=HEIGHT, bg=KEY,
                            highlightthickness=0, borderwidth=0)
        _canvas.pack()
        _placed = None
        _window.update_idletasks()
        _click_through(_window)
        if not win32():
            # Left drag moves it, right click back to the screen's top middle.
            _canvas.bind("<ButtonPress-1>", _take)
            _canvas.bind("<B1-Motion>", _drag)
            _canvas.bind("<ButtonRelease-1>", _drop)
            _canvas.bind("<ButtonPress-3>", _reset)
    except tk.TclError as err:
        # Whatever the reason - no window manager that will take it, a display
        # that will not have it on top - it is not worth a traceback out of a
        # button press. Say so and leave the list alone.
        logger.warning(f"overlay: no arrow here, skipping it: {err}")
        stop()
        return None
    logger.info(f"overlay: guiding to {_caption(record)} on "
                f"{record.get('planet_name')}")
    _tick()
    return _window


def _cancel():
    """Drop the pending tick, if there is one and anything to cancel it on."""
    global _after
    if _after and _window is not None and _window.winfo_exists():
        try:
            _window.after_cancel(_after)
        except tk.TclError:
            pass
    _after = None


def stop():
    """Take it down. Safe to call when nothing is up."""
    global _window, _canvas, _target, _after, _placed, _on_stop, _since, _pointed, _hidden, _here
    global _grab
    _cancel()
    _here = _grab = None
    _pointed = _hidden = False
    if _window is not None and _window.winfo_exists():
        _window.destroy()
    _window = _canvas = _target = _after = _placed = _since = None
    ending, _on_stop = _on_stop, None
    if ending:
        try:
            ending()
        except tk.TclError:      # the window that asked is gone, which is fine
            pass


def _tick():
    """One reading, drawn, and the next one booked."""
    global _after, _since, _pointed, _here
    if _window is None or not _window.winfo_exists():
        return
    focused = game_focused()
    # Not in front: nothing over the desktop or another window.
    _show(focused)
    reading = guide.fix(spotmark.read_status(), _target or {})
    # Arrival and its HERE_MS clock run with the game in the background too:
    # RhinoData in front kept the arrow, and the card's Stop, up for good.
    if reading["state"] == "arrived" and _here is None:
        _here = time.monotonic()
    if _here is not None and (time.monotonic() - _here) * 1000 >= HERE_MS:
        logger.info("overlay: arrived, closing")
        stop()
        return
    if not focused and _game_rect() is not None:
        # Alt-tabbed out of a running game. A message nobody can see is not
        # being read, so its clock waits. With no game at all it runs, and a
        # Guide pressed before launching still gives up after ten seconds.
        _since = None
        _after = _window.after(POLL_MS, _tick)
        return

    # A guide that never got going is a message, and a message that has been
    # read is in the way. One that has pointed at something stays: losing the
    # fix is what taking off does, and you are still going back down.
    if reading["state"] in ("guiding", "arrived"):
        _since = None
        _pointed = True
    elif not _pointed:
        _since = _since or time.monotonic()
        if (time.monotonic() - _since) * 1000 >= NOTICE_MS:
            logger.info(f"overlay: never got going ({reading['state']}), closing")
            stop()
            return

    try:
        if focused:
            _place()
            _draw(reading)
    except Exception:
        # Same rule as building it: an arrow that cannot be drawn is one the
        # commander does without, not a traceback every half second.
        logger.exception("overlay: could not draw, taking it down")
        stop()
        return
    _after = _window.after(POLL_MS, _tick)


# ---------------------------------------------------------------- placement

def _place():
    """Top middle of the Elite window, or of the screen when it is not there -
    which, with the arrow hidden unless Elite is in front, is off Windows only.

    Re-read every tick rather than once: the game gets moved and alt-tabbed,
    and an arrow left behind on the desktop is worse than one that follows.
    """
    global _placed
    if _grab is not None:
        return                   # being dragged: the pointer places it
    rect = _game_rect()
    dragged = position() if not win32() else None
    if rect:
        left, top, right, bottom = rect
        x = left + (right - left - WIDTH) // 2
        y = top + max(24, int((bottom - top) * 0.04))
    elif dragged:
        # Clamped to the whole screen: a monitor unplugged since.
        x = min(max(0, dragged[0]), max(0, _window.winfo_screenwidth() - WIDTH))
        y = min(max(0, dragged[1]), max(0, _window.winfo_screenheight() - HEIGHT))
    else:
        x = (_window.winfo_screenwidth() - WIDTH) // 2
        y = 40
    geometry = f"{WIDTH}x{HEIGHT}+{x}+{y}"
    if geometry != _placed:
        _window.geometry(geometry)
        _placed = geometry
    # Through Win32 as well, as the minimap does: hidden by _show before it was
    # first placed - Guide pressed with Elite behind - Tk counts the window as
    # unmapped and keeps the geometry to itself, and the arrow comes up top left.
    try:
        import ctypes
        user32 = ctypes.windll.user32
        set_topmost(user32.GetParent(_window.winfo_id()) or _window.winfo_id(), x, y, WIDTH, HEIGHT)
    except (ImportError, AttributeError, OSError):
        pass


def win32():
    """Whether the Win32 calls exist here."""
    try:
        import ctypes
        ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return False
    return True


def position(key=POS_KEY):
    """(x, y) stored as "x,y" under config `key`, or None. Unreadable is None."""
    if config is None:
        return None
    try:
        x, y = config.get_str(key, default="").split(",")
        return int(x), int(y)
    except (AttributeError, TypeError, ValueError):
        return None


def _take(event):
    global _grab
    _grab = (event.x_root, event.y_root, _window.winfo_x(), _window.winfo_y())


def _drag(event):
    if _grab is None:
        return
    px, py, wx, wy = _grab
    _window.geometry(f"+{wx + event.x_root - px}+{wy + event.y_root - py}")


def _drop(event):
    """Store where it was dropped. A click without a move stores nothing."""
    global _grab, _placed
    moved = _grab is not None and (_window.winfo_x(), _window.winfo_y()) != _grab[2:]
    _grab = None
    if moved and config is not None:
        config.set(POS_KEY, f"{_window.winfo_x()},{_window.winfo_y()}")
        logger.info(f"overlay: arrow moved to {_window.winfo_x()},{_window.winfo_y()}")
    _placed = None


def _reset(event=None):
    """Forget the dragged position: top middle of the screen again."""
    global _placed
    if config is not None:
        config.set(POS_KEY, "")
    _placed = None
    _place()


def foreground_title():
    """The title of the window in front, for a log line. '' when unknown."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return ""
    buffer = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 64)
    return buffer.value


def game_focused():
    """Whether Elite is the window in front. Not running counts as not in
    front; off Windows there is no asking, so it is always in front."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return True
    # By title prefix, as EDMC's own hotkey code does: an exact title that one
    # build changes would keep the arrow and the map down for good.
    buffer = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 64)
    return buffer.value.startswith(GAME_TITLE_PREFIX)


def _show(visible):
    """Hide or show without activating. Tk's deiconify takes the foreground,
    and that would take it from the game the moment it came back."""
    global _hidden
    if visible != _hidden:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        handle = user32.GetParent(_window.winfo_id()) or _window.winfo_id()
        user32.ShowWindow(handle, 4 if visible else 0)   # SW_SHOWNOACTIVATE, SW_HIDE
        if visible:
            _topmost_sent.pop(handle, None)              # raised on the next _place
    except (ImportError, AttributeError, OSError):
        return
    _hidden = not visible


def set_topmost(handle, x, y, width, height, force=False):
    """SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE): moved, sized, top of the topmost band.

    Typed: HWND_TOPMOST is (HWND)-1, and an untyped -1 is sent as a 32-bit int,
    refused with ERROR_INVALID_WINDOW_HANDLE (1400). Skipped, unless `force`,
    when the window has not moved and the last good send is under
    TOPMOST_EVERY_S old.
    """
    global _typed_user32
    now = time.monotonic()
    rect = (x, y, width, height)
    last = _topmost_sent.get(handle)
    if not force and last and last[0] == rect and now - last[1] < TOPMOST_EVERY_S:
        return
    import ctypes
    from ctypes import wintypes
    if _typed_user32 is None:
        _typed_user32 = ctypes.WinDLL("user32", use_last_error=True)
        _typed_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        _typed_user32.SetWindowPos.restype = wintypes.BOOL
    ok = _typed_user32.SetWindowPos(handle, wintypes.HWND(-1), x, y, width, height, 0x10)
    error = 0 if ok else ctypes.get_last_error()
    if ok:
        _topmost_sent[handle] = (rect, now)
    if error != _topmost_errors.get(handle, 0):
        if error:
            logger.warning(f"overlay: SetWindowPos HWND_TOPMOST failed, error {error}")
        _topmost_errors[handle] = error


def _game_rect():
    """Where Elite is on screen, as (left, top, right, bottom), or None."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return None
    hwnd = user32.FindWindowW(None, GAME_TITLE)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    if rect.right <= rect.left or rect.bottom <= rect.top:
        return None
    return rect.left, rect.top, rect.right, rect.bottom


def _click_through(window, on=True):
    """Let the mouse through the whole window, arrow included.

    The transparent colour already passes clicks where nothing is drawn. This
    is for where something is: a triangle over the cockpit that eats a click
    is a triangle that will eat the wrong one.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except (ImportError, AttributeError, OSError):
        return                                               # not Windows: no WS_EX styles
    try:
        handle = user32.GetParent(window.winfo_id()) or window.winfo_id()
        style = user32.GetWindowLongW(handle, -20)           # GWL_EXSTYLE
        if on:
            style |= (0x80000                                # WS_EX_LAYERED
                      | 0x20                                 # WS_EX_TRANSPARENT
                      | 0x8000000)                           # WS_EX_NOACTIVATE
        else:
            # Layered stays: the transparent colour and the alpha hang off it.
            style &= ~0x20
            style &= ~0x8000000
        user32.SetWindowLongW(handle, -20, style)
    except (ImportError, AttributeError, OSError) as err:
        logger.warning(f"overlay: not click-through here: {err}")


# ------------------------------------------------------------------ drawing

def _draw(reading):
    _canvas.delete("all")
    state = reading["state"]
    target = _target or {}

    _line(WIDTH / 2, 12, _caption(target), DIM, ("Consolas", 9))

    if state == "arrived":
        _ring(WIDTH / 2, 100, 34, GOOD)
        _line(WIDTH / 2, 100, "HERE", GOOD, ("Segoe UI", 14, "bold"))
        _line(WIDTH / 2, 160, guide.metres(reading["distance_m"]), DIM,
              ("Consolas", 10))
        return

    if state == "guiding":
        # Without a heading the arrow can only point north-up, which is a
        # different instrument and has to look like one - dim, and labelled.
        north_up = reading["relative_deg"] is None
        angle = reading["bearing_deg"] if north_up else reading["relative_deg"]
        _arrow(WIDTH / 2, 96, angle, DIM if north_up else ACCENT)
        _line(WIDTH / 2, 158, guide.metres(reading["distance_m"]), FG,
              ("Segoe UI", 16, "bold"))
        if north_up:
            _line(WIDTH / 2, 178,
                  f"north up - {guide.compass(reading['bearing_deg'])}", WARN,
                  ("Consolas", 9))
        return

    _line(WIDTH / 2, 96, _excuse(state, target),
          WARN if state == "wrong body" else DIM, ("Segoe UI", 11, "bold"))


def _caption(target):
    index = target.get("location_index")
    where = f"loc {index}" if index is not None else "bookmark"
    return f"{where}  {target.get('commodity') or ''}".strip()


def _excuse(state, target):
    """Why there is no arrow, in the words of what to do about it."""
    if state == "wrong body":
        return f"fly to {target.get('planet_name') or 'the body'}"
    if state == "no position":
        return "too high for coordinates"
    if state == "no body":
        return "not at a body"
    return "this bookmark has no coordinates"


def _arrow(cx, cy, degrees, colour):
    """The arrow, pointing `degrees` clockwise from up.

    A picture rather than a canvas polygon: the faces that make it read as
    solid need a smooth edge, and the canvas has none to give.
    """
    _canvas.create_image(cx, cy, image=_photo(degrees, colour))


def _photo(degrees, colour):
    """The frame for that angle, rendered once and kept.

    Through PNG bytes rather than PIL's ImageTk: Tk reads those itself, and
    ImageTk is the one part of PIL that EDMC's build cannot be relied on to
    carry.
    """
    key = (arrow.bucket(degrees), colour)
    photo = _frames.get(key)
    if photo is None:
        data = io.BytesIO()
        arrow.frame(degrees, colour).save(data, "PNG")
        photo = tk.PhotoImage(data=base64.b64encode(data.getvalue()))
        _frames[key] = photo
    return photo


def _ring(cx, cy, radius, colour):
    _canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                        outline=colour, width=3)


def _line(cx, cy, text, colour, font):
    if text:
        _canvas.create_text(cx, cy, text=text, fill=colour, font=font)
