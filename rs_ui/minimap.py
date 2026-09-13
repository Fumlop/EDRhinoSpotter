"""The minimap over the game: what the scanner has been driven over.

Up while you are in the SRV, hidden when you are not. Fed the Status.json the
panel already reads once a second, so it has no timer of its own. The painting
is rs_core.coverage; this is the window, the corner it sits in, and the
settings that switch it on and pick the corner.

It comes up by itself in the middle of a game, which the guide arrow never
does - that one is started by a click in EDMC. So the window is built once,
hidden, made click-through and no-activate before it has ever been shown, and
from then on shown, moved and hidden with Win32 calls that do not activate
it. Tk's own deiconify took the foreground in testing even with the
no-activate style already set.

The painted area is saved through rs_core.coverstore: the points, two seconds
after new ground at most, and a picture of the whole map each time the SRV
goes back into the ship. A launch within reach of a saved map carries it on.
"""

import base64
import io
import os
import threading
import time
import tkinter as tk

from rs_core import arrow, cards, coverage, coverstore, grounds, guide, palette, spotcard, spotmark, store
from rs_core.logging import logger
from rs_ui import overlay

try:
    import myNotebook as nb
    from config import config
except ImportError:      # running outside EDMC
    nb = config = None

ENABLED_KEY = "rhinospotter_minimap_enabled"
CORNER_KEY = "rhinospotter_minimap_corner"
CORNERS = ("top left", "top right", "bottom left", "bottom right")

KEY = overlay.KEY

# A game window shorter than this is minimised - Windows parks it as a 28 px
# title bar. No map over the desktop then.
MIN_GAME_HEIGHT = 200

# Bookmarks are read again at least this often, seconds.
MARKS_S = 10

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x10

_window = None
_canvas = None
_handle = None           # the Win32 window, or None off Windows
_shown = False
_placed = None
_photo = None            # the PhotoImage on the canvas - Tk drops it unreferenced
_drawn = None            # what the last picture was of, so standing still is free
_coverage = None
_saved = None            # (map, version, droppoints, location) last handed to _writes
_writes = store.Debounced(write=coverstore.save)
_in_srv = False
_failed = False          # a draw that raised: stay down until the next launch
_marks = None            # ((system, body, cards folder mtime), [(lat, lon, code), ...])
_codes = None            # grounds.Sheet.codes, read once
_fresh = []              # [(system, body, lat, lon, code, when)] bookmarked, maybe not on disk yet
_enabled = None          # tk.BooleanVar on the settings tab
_corner = None           # tk.StringVar on the settings tab


def enabled():
    return config.get_bool(ENABLED_KEY, default=True) if config is not None else True


def corner():
    value = config.get_str(CORNER_KEY, default=CORNERS[0]) if config is not None else CORNERS[0]
    return value if value in CORNERS else CORNERS[0]


def update(root, status, system=None):
    """One Status.json reading. Paints, and shows or hides the map.

    Nothing raises out of here: the caller is the panel's poll, and a raise
    would stop it rescheduling - Bookmark would stop greying out with it.
    """
    global _coverage, _in_srv, _failed
    if not status:
        # A read that landed mid-write. Not a reason to take the map down and
        # count the next fix as a fresh launch.
        return
    try:
        fix = coverage.srv_fix(status)
        if fix is None:
            if _in_srv:
                _docked(system)
            _in_srv = _failed = False
            hide()
            return
        previous = _coverage
        _coverage = coverage.follow(_coverage, fix, _in_srv, saved=coverstore.maps)
        if previous is not None and _coverage is not previous:
            # Written now: the timer holds one pending save, and the next one
            # is for another map.
            _writes.flush()
        _in_srv = True
        body, lat, lon, _, heading = fix
        in_reach = _coverage.add(lat, lon)
        index = spotmark.location_index(status)
        if index is not None:
            _coverage.location = index
        _remember()
        if _failed or not enabled():
            hide()
            return
        _show_map(root, status, system, lat, lon, heading, in_reach, body)
    except Exception:
        logger.exception("minimap: could not draw, down until the next launch")
        _failed = True
        hide()


def _show_map(root, status, system, lat, lon, heading, in_reach, body):
    global _drawn
    rect = overlay._game_rect()
    if not overlay.game_focused() or (rect and rect[3] - rect[1] < MIN_GAME_HEIGHT):
        # Alt-tabbed out, or minimised: nothing over the desktop. Painting
        # carries on; only the window goes.
        hide()
        return
    if not _build(root):
        return
    side = coverage.map_side(rect[3] - rect[1] if rect else None)
    where = corner()
    x, y = _coverage.xy(lat, lon)
    header = _header(status, body, system)
    marks = tuple((*_coverage.xy(mlat, mlon), code)
                  for mlat, mlon, code in _bookmarks(system, body))
    # What a picture is of, at the precision it is drawn at: a map pixel of
    # movement and a frame of the marker. Anything finer redraws for nothing.
    per_px = 2 * coverage.VIEW_M / side
    state = (int(x // per_px), int(y // per_px),
             None if heading is None else arrow.bucket(heading),
             side, where, in_reach, header, _coverage.version, len(_coverage.drops), marks)
    if state != _drawn:
        _draw(side, x, y, heading, in_reach, header, marks)
        _drawn = state
    _place(side, where, rect)


def _remember():
    """Hand the map to the two-second writer when it has changed."""
    global _saved
    state = (_coverage, _coverage.version, len(_coverage.drops), _coverage.location)
    if state == _saved:
        return
    if _coverage.name is None:
        _coverage.name = coverstore.next_name(_coverage.body)
    _writes(_coverage.body, _coverage.name, _coverage.to_dict())
    _saved = state


def _bookmarks(system, body):
    """[(lat, lon, code), ...] of the bookmarks on this body.

    Read again when the cards folder changes - a card written or deleted moves
    its modified time - and every MARKS_S besides: the card is written on a
    worker thread, a read that lands between the sidecar being created and
    filled skips it, and filling it does not move the folder's time.
    """
    global _marks
    if not system or not body:
        return []
    try:
        stamp = os.stat(spotcard.card_dir(system)).st_mtime_ns
    except OSError:
        stamp = None
    key = (system, body, stamp, int(time.monotonic() // MARKS_S))
    if _marks is None or _marks[0] != key:
        points = []
        if stamp is not None:
            for record in cards.for_system(system):
                lat, lon = record.get("latitude"), record.get("longitude")
                if (record.get("planet_name") == body and isinstance(lat, (int, float))
                        and isinstance(lon, (int, float))):
                    points.append((lat, lon, _code(record.get("commodity"))))
        _marks = (key, points)
    now = time.monotonic()
    _fresh[:] = [f for f in _fresh if now - f[5] < 2 * MARKS_S]
    on_disk = {(lat, lon) for lat, lon, _ in _marks[1]}
    fresh = [(lat, lon, code) for s, b, lat, lon, code, _ in _fresh
             if s == system and b == body and (lat, lon) not in on_disk]
    return _marks[1] + fresh if fresh else _marks[1]


def _code(material):
    """The short code for a material, or None for one the sheet does not know."""
    global _codes
    if _codes is None:
        _codes = grounds.Sheet().codes()
    return _codes.get((material or "").lower())


def bookmarked(spot):
    """A bookmark was just made: on the map now, not when its card is on disk.

    The card renders on a worker thread, and until its sidecar is written and
    read back the dot would be missing. Kept beside what is read from disk for
    twice MARKS_S, by which time the sidecar has been read or the card failed.
    """
    global _drawn
    lat, lon = spot.get("latitude"), spot.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return
    _fresh.append((spot.get("system"), spot.get("planet_name"), lat, lon,
                   _code(spot.get("commodity")), time.monotonic()))
    _drawn = None


def _docked(system):
    """The SRV is back in the ship: the points written now, and the picture
    drawn off the Tk thread - 70 to 160 ms measured, and nothing waits for it."""
    _writes.flush()
    if _coverage is None or _coverage.name is None:
        return
    body, name = _coverage.body, _coverage.name
    mask, drops = _coverage.mask.copy(), list(_coverage.drops)
    marks = [(*_coverage.xy(lat, lon), code) for lat, lon, code in _bookmarks(system, body)]

    def draw():
        try:
            coverstore.save_png(body, name, coverage.picture(mask, drops, marks))
        except Exception:
            logger.exception(f"minimap: could not draw the picture of {name} on {body}")

    threading.Thread(target=draw, name="rhinospotter-map-png", daemon=True).start()


def hide():
    """Hide the window. It and the painted area stay for the next launch."""
    global _shown
    if _window is None or not _shown:
        return
    try:
        if _handle:
            _user32().ShowWindow(_handle, SW_HIDE)
        else:
            _window.withdraw()
    except (tk.TclError, OSError):
        pass
    _shown = False


def stop():
    """EDMC is closing: the window goes, the map is written first."""
    global _window, _canvas, _handle, _shown, _placed, _photo, _drawn
    global _coverage, _saved, _in_srv, _failed, _marks
    _writes.flush()
    if _window is not None:
        try:
            _window.destroy()
        except tk.TclError:
            pass
    _window = _canvas = _handle = _placed = _photo = _drawn = _coverage = _saved = _marks = None
    _shown = _in_srv = _failed = False
    _fresh.clear()


# ---------------------------------------------------------------- settings

def prefs(parent):
    """The settings tab: the map on or off, and which corner it sits in."""
    global _enabled, _corner
    frame = nb.Frame(parent)
    _enabled = tk.BooleanVar(value=enabled())
    _corner = tk.StringVar(value=corner())
    nb.Checkbutton(frame, text="Show the minimap while in the SRV",
                   variable=_enabled).grid(row=0, column=0, columnspan=2,
                                           sticky="w", padx=10, pady=(10, 2))
    nb.Label(frame, text="Corner").grid(row=1, column=0, sticky="w", padx=10, pady=2)
    nb.OptionMenu(frame, _corner, _corner.get(), *CORNERS).grid(
        row=1, column=1, sticky="w", padx=10, pady=2)
    nb.Label(frame, text="Painted means driven within "
                         f"{coverage.SCAN_RADIUS_M / 1000:.0f} km, not scanned.").grid(
        row=2, column=0, columnspan=2, sticky="w", padx=10, pady=2)
    count, size = coverstore.usage()
    amount = f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size / 1024:.0f} KB"
    nb.Label(frame, text=f"Saved maps: {count} ({amount})").grid(
        row=3, column=0, sticky="w", padx=10, pady=(2, 10))
    nb.Button(frame, text="Open folder", command=_open_folder).grid(
        row=3, column=1, sticky="w", padx=10, pady=(2, 10))
    return frame


def _open_folder():
    try:
        os.makedirs(coverstore.ROOT, exist_ok=True)
        os.startfile(coverstore.ROOT)
    except (OSError, AttributeError) as err:       # AttributeError: not Windows
        logger.info(f"minimap: could not open {coverstore.ROOT}: {err}")


def prefs_changed():
    global _placed, _drawn
    if config is not None:
        if _enabled is not None:
            config.set(ENABLED_KEY, bool(_enabled.get()))
        if _corner is not None:
            config.set(CORNER_KEY, _corner.get())
    # Moved or switched off: the next reading places and draws it again.
    _placed = _drawn = None


# ------------------------------------------------------------------ window

def _user32():
    import ctypes
    return ctypes.windll.user32


def _build(root):
    """The window, built hidden the first time. False when it cannot be."""
    global _window, _canvas, _handle, _placed, _drawn, _shown
    if _window is not None and _window.winfo_exists():
        return True
    try:
        _window = tk.Toplevel(root)
        _window.withdraw()
        _window.overrideredirect(True)
        _window.configure(bg=KEY)
        _window.attributes("-topmost", True)
        try:
            # Nothing is drawn in the key colour. It is set because the
            # click-through style needs a layered window to have been given
            # attributes, and this is the call that gives them.
            _window.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        _canvas = tk.Canvas(_window, bg=palette.PANEL, highlightthickness=0, borderwidth=0)
        _canvas.pack()
        _window.update_idletasks()
        overlay._click_through(_window)
        try:
            _handle = _user32().GetParent(_window.winfo_id()) or None
        except (ImportError, AttributeError, OSError):
            _handle = None
        _placed = _drawn = None
        _shown = False
    except tk.TclError as err:
        logger.info(f"minimap: no window here, skipping it: {err}")
        stop()
        return False
    logger.info("minimap: built")
    return True


def _layout(side):
    unit = side / 240.0
    pad = max(6, round(8 * unit))
    band = max(18, round(22 * unit))
    return unit, pad, band, side + 2 * pad, side + 2 * band + 2 * pad


def _place(side, where, rect):
    """Into the corner, shown, and on top - every tick, since the game gets
    moved and a game going fullscreen takes the top of the Z-order with it."""
    global _placed, _shown
    _, _, _, width, height = _layout(side)
    if rect:
        left, top, right, bottom = rect
    else:
        left, top = 0, 0
        right, bottom = _window.winfo_screenwidth(), _window.winfo_screenheight()
    inset = max(16, int((bottom - top) * 0.03))
    x = left + inset if "left" in where else right - inset - width
    y = top + inset if "top" in where else bottom - inset - height
    geometry = f"{width}x{height}+{x}+{y}"
    if geometry != _placed:
        _canvas.config(width=width, height=height)
        # Tk has to be told as well, or it puts the window back where it
        # thinks it is on the next layout.
        _window.geometry(geometry)
        _window.update_idletasks()
        _placed = geometry
    if _handle:
        user32 = _user32()
        user32.SetWindowPos(_handle, HWND_TOPMOST, x, y, width, height, SWP_NOACTIVATE)
        if not _shown:
            user32.ShowWindow(_handle, SW_SHOWNOACTIVATE)
    elif not _shown:
        _window.deiconify()
    _shown = True


def _header(status, body, system):
    """'loc 3  A 2' - the body without the system in front of it."""
    short = body
    if system and body.startswith(system + " "):
        short = body[len(system) + 1:]
    index = spotmark.location_index(status)
    return f"loc {index}  {short}" if index is not None else short


def _draw(side, x, y, heading, in_reach, header, marks=()):
    global _photo
    unit, pad, band, width, height = _layout(side)
    image = coverage.render(_coverage, x, y, heading, side, marks)
    data = io.BytesIO()
    image.save(data, "PNG", compress_level=1)
    _photo = tk.PhotoImage(data=base64.b64encode(data.getvalue()))

    small = ("Consolas", max(8, round(9 * unit)))
    bold = ("Segoe UI", max(9, round(10 * unit)), "bold")
    top = pad + band
    per_m = side / (2 * coverage.VIEW_M)

    _canvas.delete("all")
    _canvas.create_text(pad, pad + band / 2, text=header, fill=palette.MUTED,
                        font=small, anchor="w")
    _canvas.create_text(width - pad, pad + band / 2, text="N ↑", fill=palette.FG,
                        font=small, anchor="e")
    _canvas.create_image(pad, top, image=_photo, anchor="nw")

    # Numbers beside the droppoints once there is more than one. Canvas text
    # rather than PIL, for the same fonts as the rest of the panel.
    drops = _coverage.drops
    if len(drops) > 1:
        for number, (mx, my) in enumerate(drops, 1):
            px = pad + side / 2 + (mx - x) * per_m + 9 * unit
            py = top + side / 2 - (my - y) * per_m
            if pad <= px <= pad + side - 6 * unit and top <= py <= top + side:
                latest = number == len(drops)
                _canvas.create_text(px, py, text=str(number), anchor="w",
                                    fill=palette.GOOD if latest else palette.MUTED,
                                    font=bold if latest else small)

    _canvas.create_rectangle(pad - 1, top - 1, pad + side, top + side, outline=palette.RULE)

    # Scale bar: one grid square.
    bar = side * coverage.GRID_M / (2 * coverage.VIEW_M)
    bx, by = pad + 8 * unit, top + side - 10 * unit
    _canvas.create_line(bx, by, bx + bar, by, fill=palette.FG, width=max(2, round(2 * unit)))
    _canvas.create_text(bx + bar + 4 * unit, by, text=guide.metres(coverage.GRID_M),
                        fill=palette.FG, font=small, anchor="w")

    # The latest droppoint is where the ship is. Short on the right: at the
    # smallest map both lines share 196 px.
    foot = top + side + band / 2 + pad / 2
    to_x, to_y = drops[-1]
    distance = ((to_x - x) ** 2 + (to_y - y) ** 2) ** 0.5
    label = f"Droppoint {len(drops)}" if len(drops) > 1 else "Droppoint"
    _canvas.create_text(pad, foot,
                        text=f"{label}  {guide.metres(distance)} "
                             f"{guide.compass(coverage.bearing(x, y, to_x, to_y))}",
                        fill=palette.GOOD, font=small, anchor="w")
    if in_reach:
        _canvas.create_text(width - pad, foot, text=f"{_coverage.painted_km2():.0f} km²",
                            fill=palette.ACCENT, font=bold, anchor="e")
    else:
        _canvas.create_text(width - pad, foot, text="out of range",
                            fill=palette.WARN, font=bold, anchor="e")
