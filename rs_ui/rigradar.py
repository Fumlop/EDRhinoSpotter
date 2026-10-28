"""Rig radar: rigs placed on this body, each a 76-80 m band, around the SRV.

Opened by `placed()` (press.released; a journal event can call it the same way).
VIEW_M across, north up, the SRV in the middle, GRID_M raster, no border. Each rig
gets a band from measure.RIG_SPACING (76 m) to SPACING_M (80 m), no outline: ALERT_BAND
while the SRV is inside one, GOOD_BAND once SPACING_M or more from every rig.
Centred under the guide arrow (overlay._place: top + max(24 px, 4%), overlay.HEIGHT
tall). Click-through, hidden while Elite is not in front; Status.json read every POLL_MS.
Closes and forgets the rigs when the SRV fix ends (docked, on foot, ship) or
the body changes.
"""

import math
import tkinter as tk

from rs_core import coverage, measure, palette, rigplan, spotmark
from rs_core.logging import logger
from rs_ui import overlay

VIEW_M = 250.0           # ground shown across, m: 80 m band = 31% of the side
GRID_M = 10.0            # raster, m: 8.8 px at SIZE
SIZE = 220               # map side, px
BAND = 30                # text line under the map, px
HINT = 20                # hide line under BAND, px
BORDER = 4               # px
GAP = 8                  # px under the arrow window
POLL_MS = 250
ALPHA = 0.85             # as minimap.MAP_ALPHA
FONT = ("Segoe UI", 11, "bold")
HINT_FONT = ("Segoe UI", 9)
# Band colour mixed 55% into BG: per-item alpha does not exist on a Tk canvas.
BAND_SHARE = 0.55
GOOD_BAND, ALERT_BAND = ("#%02x%02x%02x" % coverage._mix(palette.BG, colour, BAND_SHARE)
                         for colour in (palette.GOOD, palette.ALERT))

_window = None
_canvas = None
_after = None
_body = None
_radius = None
_rigs = []               # [(lat, lon)] placed on _body, oldest first
_shown = False
_text = ""               # the line under the map, last drawn
_clear = False           # bands GOOD, last drawn
_button = None           # "left" / "right": the rig button, named in the hide line


def placed(root, body, lat, lon, radius, button=None):
    """A rig down at lat, lon on body: band added, radar opened. button: hide line, None for none."""
    global _body, _radius, _button
    if body != _body:
        _rigs.clear()
    _body, _radius, _button = body, radius, button
    _rigs.append((lat, lon))
    _open(root)
    if _after is not None:
        _window.after_cancel(_after)             # one poll chain, not one per rig
    _tick()


def close():
    """Window gone, rigs forgotten."""
    global _window, _canvas, _after, _body, _shown
    if _window is not None:
        if _after is not None:
            try:
                _window.after_cancel(_after)
            except tk.TclError:
                pass
        try:
            _window.destroy()
        except tk.TclError:
            pass
    _window = _canvas = _after = _body = None
    _shown = False
    _rigs.clear()


def _open(root):
    global _window, _canvas
    if _window is not None:
        return
    _window = tk.Toplevel(root)
    _window.overrideredirect(True)
    _window.configure(bg=palette.BG)
    _window.attributes("-topmost", True)
    try:
        _window.attributes("-alpha", ALPHA)
    except tk.TclError:
        pass
    _canvas = tk.Canvas(_window, width=SIZE + 2 * BORDER, height=SIZE + BAND + HINT + 2 * BORDER,
                        bg=palette.BG, highlightthickness=0)
    _canvas.pack()
    _window.update_idletasks()
    overlay._click_through(_window)
    _window.withdraw()                           # _show() maps it, without activating


def _tick():
    global _after
    _after = None
    if _window is None:
        return
    status = spotmark.read_status()
    if status:                                   # {}: read landed mid-write, next tick
        fix = coverage.srv_fix(status)
        if fix is None or fix[0] != _body:
            logger.info(f"rigradar: closed, {'left the SRV' if fix is None else 'other body'}")
            close()
            return
        try:
            if overlay.game_focused():
                _draw(fix)
                _show(True)
            else:
                _show(False)
        except Exception:
            # Raised out of an after() callback the chain would end with the window up.
            logger.exception("rigradar: draw failed, closed")
            close()
            return
    _after = _window.after(POLL_MS, _tick)


def _draw(fix):
    """Rings, rigs and SRV chevron; border and line from the nearest rig."""
    global _text, _clear
    _, lat, lon, radius, heading = fix
    points = measure.to_metres(_rigs, radius or _radius, origin=(lat, lon))
    nearest = min(math.hypot(x, y) for x, y in points)
    _clear = nearest >= rigplan.SPACING_M
    _text = "Next rig: OK here" if _clear else \
        f"Next rig: drive {rigplan.SPACING_M - nearest:.0f} m on"
    scale = SIZE / VIEW_M
    mid = BORDER + SIZE / 2
    c = _canvas
    c.delete("all")
    # GRID_M raster on the first rig, so it moves under the SRV as it drives.
    gx, gy = points[0]
    for n in range(-math.ceil(VIEW_M / GRID_M), math.ceil(VIEW_M / GRID_M) + 1):
        vx = mid + (gx % GRID_M + n * GRID_M) * scale
        vy = mid - (gy % GRID_M + n * GRID_M) * scale
        if BORDER <= vx <= BORDER + SIZE:
            c.create_line(vx, BORDER, vx, BORDER + SIZE, fill=palette.RULE, tags="grid")
        if BORDER <= vy <= BORDER + SIZE:
            c.create_line(BORDER, vy, BORDER + SIZE, vy, fill=palette.RULE, tags="grid")
    # 76-80 m band as one oval line: radius the middle, width the band (4 m = 3.5 px, drawn 4 px).
    # Whole px: EDMC's Tk raises "bad screen distance" on a float width.
    r = (measure.RIG_SPACING + rigplan.SPACING_M) / 2 * scale
    band = max(1, round((rigplan.SPACING_M - measure.RIG_SPACING) * scale))
    for x, y in points:
        cx, cy = mid + x * scale, mid - y * scale
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=GOOD_BAND if _clear else ALERT_BAND,
                      width=band, tags="ring")
        c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=palette.FG_SOFT, outline="")
    if heading is None:
        c.create_oval(mid - 6, mid - 6, mid + 6, mid + 6, fill=palette.SRV, outline=palette.BG)
    else:
        a = math.radians(heading)
        chevron = [(0, -1.0), (0.7, 0.8), (0, 0.4), (-0.7, 0.8)]
        c.create_polygon([v for px, py in chevron
                          for v in (mid + (px * math.cos(a) - py * math.sin(a)) * 10,
                                    mid + (px * math.sin(a) + py * math.cos(a)) * 10)],
                         fill=palette.SRV, outline=palette.BG)
    c.create_text(BORDER + SIZE / 2, BORDER + SIZE + BAND / 2, text=_text, font=FONT,
                  fill=palette.GOOD if _clear else palette.WARN)
    if _button:
        c.create_text(BORDER + SIZE / 2, BORDER + SIZE + BAND + HINT / 2,
                      text=f"To hide: double click {_button} mouse", font=HINT_FONT,
                      fill=palette.FG_SOFT, tags="hint")
    _place()


def _place():
    width, height = SIZE + 2 * BORDER, SIZE + BAND + HINT + 2 * BORDER
    rect = overlay._game_rect()
    if rect:
        left, top, right, bottom = rect
    else:
        left, top, right, bottom = 0, 0, _window.winfo_screenwidth(), _window.winfo_screenheight()
    x = left + (right - left - width) // 2
    y = top + max(24, int((bottom - top) * 0.04)) + overlay.HEIGHT + GAP
    _window.geometry(f"{width}x{height}+{x}+{y}")
    if overlay.win32():
        try:
            import ctypes
            handle = ctypes.windll.user32.GetParent(_window.winfo_id()) or _window.winfo_id()
            overlay.set_topmost(handle, x, y, width, height)
        except (ImportError, AttributeError, OSError):
            pass


def _show(visible):
    """Show or hide without taking the foreground (SW_SHOWNOACTIVATE / SW_HIDE)."""
    global _shown
    if visible == _shown:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        handle = user32.GetParent(_window.winfo_id()) or _window.winfo_id()
        user32.ShowWindow(handle, 4 if visible else 0)
    except (ImportError, AttributeError, OSError):
        if visible:
            _window.deiconify()
        else:
            _window.withdraw()
    _shown = visible
