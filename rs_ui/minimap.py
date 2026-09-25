"""The minimap over the game: what the scanner has been driven over.

Up while you are in the SRV or placing it from Settings, hidden otherwise. Fed the Status.json the
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
import itertools
import threading
import time
import tkinter as tk
from tkinter import messagebox

from rs_core import (arrow, cards, coverage, coverstore, database, grounds, guide, migrate,
                     palette, spansh, spotmark, store)
from rs_core.logging import logger
from rs_ui import hotkey, overlay

try:
    import myNotebook as nb
    from config import config
except ImportError:      # running outside EDMC
    nb = config = None

ENABLED_KEY = "rhinospotter_minimap_enabled"
CORNER_KEY = "rhinospotter_minimap_corner"
KEEP_KEY = "rhinospotter_minimap_keep"
FREE_KEY = "rhinospotter_minimap_free"
# Where the commander dragged it, as "x,y" screen pixels of its top left -
# any monitor, and it stays there when the game window moves. Not
# rhinospotter_minimap_pos: that held an offset from the game window (5.5.1).
POS_KEY = "rhinospotter_minimap_xy"
ZOOM_KEY = "rhinospotter_minimap_zoom"
SRV_KEY = "rhinospotter_srv_type"
# Whether the material lists carry the cheap half. Not a minimap setting - it
# lives here because this is the file that draws the settings tab.
LOW_VALUE_KEY = "rhinospotter_low_value"
# Golden circle radius, m: coverage.golden_m.
GOLDEN_KEY = "rhinospotter_golden_m"
GOLDEN_STEPS = tuple(range(500, 2501, 250))
# Only the Rhino has the mining scanner the painted area stands for.
RHINO = "mev_rhino"
CORNERS = ("top left", "top right", "bottom left", "bottom right")

KEY = overlay.KEY

# A game window shorter than this is minimised - Windows parks it as a 28 px
# title bar. No map over the desktop then.
MIN_GAME_HEIGHT = 200

# How much of the map covers the game behind it. 85%: the cockpit shows through
# faintly, and the painted area, dots and text still read at a glance.
MAP_ALPHA = 0.85

# How long a bookmark just made is drawn from memory, seconds - long past the
# worker thread writing its file and the folder change reading it back.
FRESH_S = 20

# How long a hotkey's refusal stays on the hint line, seconds.
NOTICE_S = 4

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

_window = None
_canvas = None
_handle = None           # the Win32 window, or None off Windows
_shown = False
_placed = None
_photo = None            # the PhotoImage on the canvas - Tk drops it unreferenced
_drawn = None            # what the last picture was of, so standing still is free
_coverage = None
_saved = None            # (map, version, centered, border, location) last handed to _writes
_here = None             # (lat, lon) of the last SRV fix, for the hotkeys
_notice = None           # (text, until monotonic) on the hint line, e.g. "set center first"
_writes = store.Debounced(write=coverstore.save)     # one pending save per (body, name)
_in_srv = False
_srv_type = None         # SRVType of the last LaunchSRV; None: not seen, read from config
_failed = False          # a draw that raised: stay down until the next launch
_marks = None            # ((system, body, bookmark revision), [(lat, lon, code, depleted), ...])
_why = None              # why the map is down, logged when it changes (debug only)
_codes = None            # (grounds.Sheet.codes, grounds.Sheet.values), read once
_fresh = []              # [(system, body, lat, lon, code, when)] bookmarked, maybe not on disk yet
_enabled = None          # tk.BooleanVar on the settings tab
_corner = None           # tk.StringVar on the settings tab
_keep = None             # tk.BooleanVar on the settings tab
_hotkeys = {}            # hotkey id -> (modifier StringVar, key StringVar) on the settings tab
_free = None             # tk.BooleanVar on the settings tab
_low_value = None        # tk.BooleanVar on the settings tab
_golden = None           # tk.StringVar on the settings tab, metres
_placing = False         # in place-the-map mode: click-through off, drag to move
_grab = None             # (pointer x, pointer y, window x, window y) while dragging
_held = None             # the widget whose Tk grab place() took - EDMC's Settings dialog


def enabled():
    return config.get_bool(ENABLED_KEY, default=True) if config is not None else True


def keep_up():
    """Whether the map stays up with Elite not in front - alt-tabbed to a
    browser, or reading something on a second screen while the SRV sits.

    Off unless asked for: over the desktop the map is on top of whatever is in
    that corner, and nobody should find that out by surprise."""
    return config.get_bool(KEEP_KEY, default=False) if config is not None else False


def corner():
    value = config.get_str(CORNER_KEY, default=CORNERS[0]) if config is not None else CORNERS[0]
    return value if value in CORNERS else CORNERS[0]


def free_move():
    """Whether the map sits where it was dragged instead of in a corner."""
    return config.get_bool(FREE_KEY, default=False) if config is not None else False


def low_value_shown():
    """Whether the material lists offer the ones under grounds.HIGH_VALUE_MIN.

    Off by default. Price is measured on Sheet.values(): the median, best
    across grounds.
    """
    return config.get_bool(LOW_VALUE_KEY, default=False) if config is not None else False


def golden():
    """Golden circle radius in m from config; not one of GOLDEN_STEPS: the default."""
    default = int(coverage.GOLDEN_RADIUS_M)
    try:
        value = int(config.get_int(GOLDEN_KEY, default=default)) if config is not None else default
    except (TypeError, ValueError):
        return default
    return value if value in GOLDEN_STEPS else default


def apply_golden():
    """Set coverage.golden_m from config: at start and on Settings OK."""
    coverage.golden_m = float(golden())


def position():
    """(x, y) in screen pixels, or None.

    Stored as text because EDMC's config holds strings and ints, and a pair
    of them is neither. Anything unreadable is no position at all, which puts
    the map back in its corner rather than at 0,0."""
    if config is None:
        return None
    try:
        x, y = config.get_str(POS_KEY, default="").split(",")
        return int(x), int(y)
    except (AttributeError, TypeError, ValueError):
        return None


def free_xy(bounds, width, height, where):
    """Where a dragged map goes: `where`, clamped inside `bounds` - the
    monitor it lands on.

    Clamped because a monitor gets unplugged and a stored position would then
    put the map off every screen."""
    left, top, right, bottom = bounds
    x = min(max(left, where[0]), max(left, right - width))
    y = min(max(top, where[1]), max(top, bottom - height))
    return x, y


def _monitor_rect(x, y, width, height):
    """(left, top, right, bottom) of the monitor nearest this
    rectangle, or None off Windows. MonitorFromRect, MONITOR_DEFAULTTONEAREST."""
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromRect.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        rect = wintypes.RECT(x, y, x + width, y + height)
        monitor = user32.MonitorFromRect(ctypes.byref(rect), 2)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        area = info.rcMonitor
        return area.left, area.top, area.right, area.bottom
    except (ImportError, AttributeError, OSError):
        return None


def _step():
    """Which of coverage.MAP_ZOOMS the size hotkey was left on. The step and
    not the factor: EDMC's config holds ints, and 1.4 is not one. A stored
    value from anywhere else is taken the long way round rather than guarded."""
    return config.get_int(ZOOM_KEY, default=0) % len(coverage.MAP_ZOOMS) if config else 0


def zoom():
    """How big the player has asked for the map to be."""
    return coverage.MAP_ZOOMS[_step()]


def _distances_shown():
    """Whether the lines between the bookmarks are drawn: anything but the
    smallest map. At 1x the map is 12 km of ground in a couple of hundred
    pixels, where a line covers the painted area it crosses and a number has
    nowhere to sit."""
    return _step() > 0


def bigger():
    """The hotkey: the next size up, and round to the smallest after the
    largest. Works outside the SRV too - the map is not up to see it change,
    but nothing about the size needs a fix."""
    global _placed, _drawn
    if config is None:
        return                        # outside EDMC there is nowhere to keep it
    step = (_step() + 1) % len(coverage.MAP_ZOOMS)
    config.set(ZOOM_KEY, step)
    # The window is a different size now, so it is placed and drawn again.
    _placed = _drawn = None
    logger.debug(f"minimap: size hotkey, now {coverage.MAP_ZOOMS[step]:g}x")


def srv_event(entry):
    """A journal line. LaunchSRV names the SRV; kept in config as well, since a
    login inside the SRV writes no LaunchSRV to learn it from."""
    global _srv_type
    if entry.get("event") != "LaunchSRV" or not entry.get("SRVType"):
        return
    _srv_type = entry["SRVType"].lower()
    if config is not None:
        config.set(SRV_KEY, _srv_type)


def in_rhino():
    """Whether the SRV is the Rhino. Not knowing counts as yes: a map missing a
    Rhino drive is worse than one painted by another SRV."""
    kind = _srv_type
    if kind is None and config is not None:
        kind = config.get_str(SRV_KEY, default="") or None
    return kind is None or kind == RHINO


def update(root, status, system=None, ids=None, ground=None):
    """One Status.json reading. Paints, and shows or hides the map.

    `ids(system, body)` gives the body's (system_address, body_id) - the
    register's - so a map is kept apart from a body of the same name elsewhere.
    `ground(system, body)` gives its ground key, which picks the map's texture.

    Nothing raises out of here: the caller is the panel's poll, and a raise
    would stop it rescheduling - Bookmark would stop greying out with it.
    """
    global _coverage, _in_srv, _failed, _here
    if not status:
        # A read that landed mid-write. Not a reason to take the map down and
        # count the next fix as a fresh launch.
        return
    if not enabled():
        # Switched off is off: nothing painted, saved or drawn - a map the
        # commander does not want is not kept behind their back either.
        _in_srv = False
        _down("switched off in Settings")
        return
    try:
        fix = coverage.srv_fix(status)
        if fix is None:
            if _in_srv:
                _docked(system)
            _in_srv = _failed = False
            _down("not in the SRV" if not int(status.get("Flags") or 0) & coverage.IN_SRV
                  else "in the SRV, but Status.json has no body or coordinates")
            return
        if not in_rhino():
            # Not painted either: another SRV has no scanner to paint with.
            _in_srv = False
            _down(f"in the SRV, but not the Rhino ({_srv_type})")
            return
        previous = _coverage
        address, body_id = ids(system, fix[0]) if ids else (None, None)
        _coverage = coverage.follow(
            _coverage, fix, _in_srv, system_address=address,
            saved=lambda body: coverstore.maps(body, system_address=address))
        if _coverage.system_address is None:
            _coverage.system_address = address
        if _coverage.body_id is None:
            _coverage.body_id = body_id
        if ground:
            _coverage.ground = ground(system, fix[0])
        if previous is not None and _coverage is not previous:
            # Written now rather than up to two seconds later: the old map is
            # done with. Off the Tk thread - see Debounced.flush_later.
            _writes.flush_later()
        _in_srv = True
        body, lat, lon, _, heading = fix
        _here = (lat, lon)
        in_reach = _coverage.add(lat, lon)
        index = spotmark.location_index(status)
        if index is not None:
            _coverage.location = index
        _remember()
        if _failed:
            _down("a draw failed earlier")
            return
        _show_map(root, status, system, lat, lon, heading, in_reach, body)
    except Exception:
        logger.exception("minimap: could not draw, down until the next launch")
        _failed = True
        _lock()                       # a hidden map must not keep Settings' grab
        hide()


def _show_map(root, status, system, lat, lon, heading, in_reach, body):
    global _drawn
    rect = overlay._game_rect()
    minimised = bool(rect) and rect[3] - rect[1] < MIN_GAME_HEIGHT
    if minimised or not (overlay.game_focused() or keep_up() or _placing):
        # Alt-tabbed out, or minimised: nothing over the desktop. Painting
        # carries on; only the window goes. The setting keeps it up through an
        # alt-tab, not through a minimise - a minimised game has no corner for
        # the map to sit in.
        _down(f"game window {rect} is minimised" if minimised
              else f"Elite not in front ({overlay.foreground_title()!r})")
        return
    if not _build(root):
        _down("no window could be built")
        return
    _up()
    height = rect[3] - rect[1] if rect else None
    # The map grows with the hotkey; the frame and the rows under it do not.
    base = coverage.map_side(height)
    side = coverage.map_side(height, zoom())
    where = corner()
    x, y = _coverage.xy(lat, lon)
    header = _header(status, body, system)
    marks = tuple((*_coverage.xy(mlat, mlon), code, depleted, value, rigs)
                  for mlat, mlon, code, depleted, value, rigs in _bookmarks(system, body))
    # What a picture is of, at the precision it is drawn at: a map pixel of
    # movement and a frame of the marker. Anything finer redraws for nothing.
    view = coverage.view_m(zoom())
    per_px = 2 * view / side
    state = (int(x // per_px), int(y // per_px),
             None if heading is None else arrow.bucket(heading),
             side, zoom(), where, in_reach, header, _coverage.version,
             _distances_shown(),
             tuple(round(v) for v in _coverage.anchor()), _coverage.centered,
             _coverage.border_m, _hint(), marks)
    if state != _drawn:
        _draw(side, x, y, heading, in_reach, header, marks, _distances_shown(), base, view)
        _drawn = state
    _place(side, where, rect, base)


def center_here():
    """The hotkey: where the SRV is now becomes the map's centre. Nothing
    outside the SRV - there is no fix to take and no map to move."""
    global _drawn
    if not _in_srv or _coverage is None or _here is None:
        logger.debug("minimap: centre hotkey outside the SRV, ignored")
        return
    _coverage.recenter(*_here)
    _drawn = None
    _remember()
    logger.debug(f"minimap: centre set at {_here[0]:.6f} / {_here[1]:.6f}")


def border_here():
    """The hotkey: where the SRV is now is the location's edge. Needs a centre
    to measure from; without one the hint line says so for a few seconds."""
    global _drawn, _notice
    if not _in_srv or _coverage is None or _here is None:
        logger.debug("minimap: border hotkey outside the SRV, ignored")
        return
    if not _coverage.set_border(*_here):
        _notice = ("set center first", time.monotonic() + NOTICE_S)
        _drawn = None
        return
    _drawn = None
    _remember()
    logger.debug(f"minimap: border set at {_coverage.border_m:.0f} m")


def _remember():
    """Hand the map to the two-second writer when it has changed."""
    global _saved
    state = (_coverage, _coverage.version, _coverage.centered, _coverage.border_m,
             _coverage.location, _coverage.system_address, _coverage.body_id)
    if state == _saved:
        return
    if _coverage.name is None:
        _coverage.name = coverstore.next_name(_coverage.body)
    _writes(_coverage.body, _coverage.name, _coverage.to_dict())
    _saved = state


def _bookmarks(system, body):
    """[(lat, lon, code, depleted, value, rigs), ...] of the bookmarks on this body.

    Read again when a bookmark was written, updated or deleted -
    database.revision() moves on every one. Nothing else changes a bookmark,
    so nothing else re-reads.
    """
    global _marks
    if not system or not body:
        return []
    key = (system, body, database.revision())
    if _marks is None or _marks[0] != key:
        try:
            records = cards.for_system(system, quiet=False)
        except Exception as err:            # sqlite3.Error, OSError: locked, say
            # Not cached: an empty answer kept under this revision would hide
            # the dots until the next bookmark change. The next poll reads again.
            logger.debug(f"minimap: bookmarks not read, retrying: {err}")
            records = None
        if records is not None:
            points = []
            for record in records:
                lat, lon = record.get("latitude"), record.get("longitude")
                if (record.get("planet_name") == body and isinstance(lat, (int, float))
                        and isinstance(lon, (int, float))):
                    points.append((lat, lon, _code(record.get("commodity")),
                                   bool(record.get("depleted_at")),
                                   _value(record.get("commodity")), record.get("rigs")))
            _marks = (key, points)
    # While a read fails: the last good read of this body, nothing for another.
    known = _marks[1] if _marks is not None and _marks[0][:2] == (system, body) else []
    now = time.monotonic()
    _fresh[:] = [f for f in _fresh if now - f[-1] < FRESH_S]
    on_disk = {(lat, lon) for lat, lon, *_ in known}
    fresh = [(lat, lon, code, False, value, rigs) for s, b, lat, lon, code, value, rigs, _ in _fresh
             if s == system and b == body and (lat, lon) not in on_disk]
    return known + fresh if fresh else known


def _sheet():
    """(codes, values) from the mining sheet, read once. One Sheet for both:
    the codes and the prices have to come from the same reading, or a dot could
    carry a letter the ranking beside it disagrees with."""
    global _codes
    if _codes is None:
        sheet = grounds.Sheet()
        _codes = (sheet.codes(), sheet.values())
    return _codes


def _code(material):
    """The short code for a material, or None for one the sheet does not know."""
    return _sheet()[0].get((material or "").lower())


def _value(material):
    """What a material is worth, for the line to the next one down. 0 for one
    the sheet does not price - those sit at the bottom together."""
    return _sheet()[1].get((material or "").lower(), 0)


def bookmarked(spot):
    """A bookmark was just made: on the map now, not when its card is on disk.

    The card renders on a worker thread, and until its bookmark is written and
    read back the dot would be missing. Kept beside what is read from disk for
    FRESH_S, by which time the bookmark has been read or the card failed.
    """
    global _drawn
    lat, lon = spot.get("latitude"), spot.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return
    _fresh.append((spot.get("system"), spot.get("planet_name"), lat, lon,
                   _code(spot.get("commodity")), _value(spot.get("commodity")),
                   spot.get("rigs"), time.monotonic()))
    _drawn = None


def _docked(system):
    """The SRV is back in the ship: the points written now, and the picture
    drawn off the Tk thread - 70 to 160 ms measured, and nothing waits for it."""
    _writes.flush_later()
    if _coverage is None or _coverage.name is None:
        return
    body, name = _coverage.body, _coverage.name
    mask = _coverage.mask.copy()
    # Only what this map reaches: golden_groups' 4-rig fallback depends on every
    # spot it is given (as scan._map_marks for Share map).
    marks = [(*_coverage.xy(lat, lon), code, depleted, value, rigs)
             for lat, lon, code, depleted, value, rigs in _bookmarks(system, body)
             if _coverage.reaches(lat, lon)]
    # The best coverage.GOLDEN_SHOWN by Cr/h, not every group that qualifies.
    spots = [(x, y, rigs, value or 0) for x, y, _, depleted, value, rigs in marks
             if not depleted]
    golden = coverage.golden_best(coverage.golden_groups(spots), spots)
    title, legend = picture_text(_coverage, system)
    border_m = _coverage.border_m
    ground = _coverage.ground

    def draw():
        try:
            coverstore.save_png(body, name, coverage.picture(mask, marks, title, legend, border_m,
                                                             golden, ground))
        except Exception:
            logger.exception(f"minimap: could not draw the picture of {name} on {body}")

    threading.Thread(target=draw, name="rhinospotter-map-png", daemon=True).start()


def picture_text(cover, system, when=None):
    """(title lines, legend rows) for the saved picture of a map.

    Title: the body, what kind of planet it is from the system's honk, and the
    map with the locations its bookmarks were made at. Legend: one row per
    bookmark on the map - its code, material, coordinates and rigs.
    """
    body = cover.body
    records = []
    if system:
        for record in cards.for_system(system):
            lat, lon = record.get("latitude"), record.get("longitude")
            if (record.get("planet_name") == body and isinstance(lat, (int, float))
                    and isinstance(lon, (int, float)) and cover.reaches(lat, lon)):
                records.append(record)
    records.sort(key=lambda r: (_code(r.get("commodity")) or "", r.get("location_index") or 0,
                                str(r.get("marked_at"))))

    planet = next((b for b in store.load(system) if b.get("name") == body), None) if system else None
    facts = []
    if planet:
        facts.append(grounds.label(planet.get("ground")))
        if isinstance(planet.get("gravity"), (int, float)):
            # Stored as the journal's SurfaceGravity, m/s²; the picture says g.
            facts.append(f"{planet['gravity'] / spansh.G:.2f} g")
        if isinstance(planet.get("distance"), (int, float)):
            facts.append(f"{planet['distance']:,.0f} Ls")
        if planet.get("locations") is not None:
            facts.append(f"{planet['locations']} locations")

    locations = sorted({r["location_index"] for r in records if r.get("location_index") is not None})
    if not locations and cover.location is not None:
        locations = [cover.location]
    about = [cover.name or "map"]
    if cover.centered:
        about.append(f"center {cover.origin[0]:.6f} / {cover.origin[1]:.6f}")
    if cover.border_m is not None:
        about.append(f"border {guide.metres(cover.border_m)}")
    if locations:
        about.append("loc " + ", ".join(str(n) for n in locations))
    about.append(f"{cover.painted_km2():.0f} km² prospected")
    about.append(time.strftime("%Y-%m-%d %H:%M", time.localtime(when)))

    title = [body]
    if system and body.startswith(system + " "):
        title = [f"{body[len(system) + 1:]}  -  {system}"]
    if facts:
        title.append("  ·  ".join(facts))
    title.append("  ·  ".join(about))

    legend = []
    for r in records:
        # Coordinates rather than the location: the title already names the
        # locations, and a latitude and longitude is what gets you back.
        parts = [r.get("commodity") or "?", f"{float(r['latitude']):.6f} / {float(r['longitude']):.6f}"]
        if r.get("rigs") is not None:
            parts.append(f"{r['rigs']} rig" + ("" if r["rigs"] == 1 else "s"))
        if r.get("depleted_at"):
            parts.append("depleted")
        legend.append((_code(r.get("commodity")), "  ·  ".join(parts), bool(r.get("depleted_at"))))
    return title, legend


def _down(reason):
    """Hide, and say why when the reason changes.

    At info rather than debug, and one line per change rather than one a
    second: "the map is gone and I do not know why" is the one question this
    window gets asked, and answering it used to cost a RHINOSPOTTER_DEBUG=1
    and an EDMC restart - by which time whatever hid it was over.
    """
    global _why
    if _placing:
        return                   # Settings -> Place the map keeps it up, in the SRV or not
    if reason != _why:
        logger.info(f"minimap: down, {reason}")
        _why = reason
    hide()


def _up():
    global _why
    if _why is not None:
        logger.info(f"minimap: up, was down: {_why}")
        _why = None


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
    global _coverage, _saved, _in_srv, _failed, _marks, _why, _placing, _held
    _writes.flush()
    if _window is not None:
        try:
            _window.destroy()
        except tk.TclError:
            pass
    _window = _canvas = _handle = _placed = _photo = _drawn = _coverage = _saved = _marks = None
    _shown = _in_srv = _failed = _placing = False
    _why = _held = None
    _fresh.clear()


# ---------------------------------------------------------------- settings

def prefs(parent):
    """The settings tab: the map on or off, whether it stays up through an
    alt-tab, which corner it sits in, the saved maps, the materials switch and
    the hotkeys.

    Rows come from `place_at`, not from numbers written here: hand-numbered
    rows put two widgets in row 9 the last time one was inserted.
    """
    global _enabled, _corner, _keep, _free, _low_value, _golden
    frame = nb.Frame(parent)
    _golden = tk.StringVar(value=str(golden()))
    _enabled = tk.BooleanVar(value=enabled())
    _corner = tk.StringVar(value=corner())
    _keep = tk.BooleanVar(value=keep_up())
    _free = tk.BooleanVar(value=free_move())
    _low_value = tk.BooleanVar(value=low_value_shown())

    rows = itertools.count()

    def place_at(row, widget, column=0, span=1, pady=2):
        widget.grid(row=row, column=column, columnspan=span, sticky="w", padx=10, pady=pady)
        return widget

    def line(left, right=None, pady=2):
        """One row: `left` across both columns, or left and right side by side.
        Each takes the frame and returns the widget."""
        row = next(rows)
        place_at(row, left(frame), span=1 if right else 2, pady=pady)
        if right:
            place_at(row, right(frame), column=1, pady=pady)
        return row

    line(lambda f: nb.Checkbutton(
        f, text="Minimap in the Rhino - off: not shown, nothing recorded",
        variable=_enabled), pady=(10, 2))
    line(lambda f: nb.Checkbutton(
        f, text="Keep it up when you alt-tab out of the game", variable=_keep))
    line(lambda f: nb.Label(f, text="Corner"),
         lambda f: nb.OptionMenu(f, _corner, _corner.get(), *CORNERS))
    line(lambda f: nb.Checkbutton(
        f, text="Free move - put it where you dragged it, not in a corner", variable=_free))
    line(lambda f: nb.Button(f, text="Place the map",
                             command=lambda: place(frame.nametowidget("."))),
         lambda f: nb.Label(f, text="Drag it, any monitor, then double-click or Esc."))
    line(lambda f: nb.Label(f, text="Painted means driven within "
                                    f"{coverage.SCAN_RADIUS_M / 1000:.0f} km, not scanned."))
    def steps(f):
        # Readonly: the arrows step through GOLDEN_STEPS, nothing typed in. Tk sets
        # the variable to the first value on creation, so it is set again after.
        box = tk.Spinbox(f, values=GOLDEN_STEPS, textvariable=_golden, width=6,
                         state="readonly", wrap=False)
        _golden.set(str(golden()))
        return box

    line(lambda f: nb.Label(f, text="Golden circle radius from the most-rigs spot, m"), steps)

    count, size = coverstore.usage()
    amount = f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size / 1024:.0f} KB"
    line(lambda f: nb.Label(f, text=f"Saved maps: {count} ({amount})"),
         lambda f: nb.Button(f, text="Open folder", command=_open_folder), pady=(2, 10))
    # The JSON files 4.1 wrote, once the database holds them.
    result = nb.Label(frame, text="")
    line(lambda f: nb.Button(f, text="Delete migrated JSON",
                             command=lambda: _delete_migrated(frame, result)),
         lambda f: result, pady=(2, 10))

    # What the Material dropdown and the picker in RhinoData offer. Off, the
    # cheap half is left out of both and out of the rates line under a body -
    # never out of a bookmark that already names one, nor out of a material
    # being mined right now. See rs_ui/main._materials.
    line(lambda f: nb.Label(f, text="Materials"), pady=(6, 2))
    line(lambda f: nb.Checkbutton(f, text="Show materials under "
                                          f"{grounds.HIGH_VALUE_MIN:,} Cr/t",
                                  variable=_low_value), pady=(2, 10))

    # The hotkeys: a modifier set and a key each. Taken on OK and registered
    # again at once; the rows under the map name them from the next frame.
    line(lambda f: nb.Label(f, text="Hotkeys"), pady=(6, 2))
    _hotkeys.clear()
    for key_id, name, _, _ in hotkey.ACTIONS:
        mods, key = hotkey.label(key_id).rsplit("+", 1)
        mod_var, key_var = tk.StringVar(value=mods), tk.StringVar(value=key)
        _hotkeys[key_id] = (mod_var, key_var)

        def keys(f, mod_var=mod_var, key_var=key_var, mods=mods, key=key):
            # Grid, not pack: EDMC's nb.Frame already grids a child of its own,
            # and Tk refuses both managers in one frame - the whole tab went
            # with it.
            box = nb.Frame(f)
            nb.OptionMenu(box, mod_var, mods, *hotkey.MODIFIER_SETS).grid(row=0, column=0)
            nb.OptionMenu(box, key_var, key, *hotkey.KEY_NAMES).grid(row=0, column=1, padx=(4, 0))
            return box

        line(lambda f, name=name: nb.Label(f, text=name), keys)
    # Settings closed, by OK or the window's X, while placing: locked where it is.
    frame.bind("<Destroy>", lambda event: _lock(), add="+")
    return frame


def _delete_migrated(frame, result):
    """Ask, then delete the old JSON files the database already holds.
    Pictures, skipped files and the database itself stay."""
    try:
        files = migrate.leftovers()
    except Exception as err:            # OSError, sqlite3.Error
        logger.warning(f"minimap: could not look for migrated JSON: {err}")
        result.config(text="could not check - see the log")
        return
    if not files:
        result.config(text="nothing to delete")
        return
    if not messagebox.askyesno(
            "Delete migrated JSON",
            f"Delete {len(files)} old JSON files from {database.ROOT}?" + os.linesep * 2
            + "They are in the database already. Map pictures, files the import "
              "skipped and the database stay.",
            default="no", parent=frame.winfo_toplevel()):
        return
    try:
        deleted, failed = migrate.delete_leftovers()
    except Exception as err:
        logger.warning(f"minimap: could not delete migrated JSON: {err}")
        result.config(text="could not check - see the log")
        return
    result.config(text=f"deleted {len(deleted)}" + (f", {len(failed)} failed - see the log"
                                                    if failed else ""))


def place(root=None):
    """Place the map: click-through off, drag it, Esc or a double-click to lock.

    `root` is EDMC's main window, to build the map under outside the SRV; there
    it shows as an empty frame of the size it will have. The Tk grab EDMC's
    Settings dialog holds (prefs.py grab_set) is taken for the drag and handed
    back in _lock - under it the map gets no mouse events.

    A drag and not a hover, because the window cannot feel a hover. It is
    WS_EX_TRANSPARENT so the mouse goes through it to the game - that is
    what keeps it from eating a click in a fight - and a window the mouse
    goes through gets no Enter, no Motion and no three seconds of anything.
    So the mode is entered from the settings tab, and while it is on the
    window takes the mouse like an ordinary one.
    """
    global _placing, _held
    if _placing:
        return _lock()
    if (_window is None or not _window.winfo_exists()) and (root is None or not _build(root)):
        _notice_now("no map window here to place")
        return False
    if not _shown:
        _preview()
    _placing = True
    try:
        _held = _window.grab_current()
        _window.grab_set()
    except tk.TclError:
        _held = None
    overlay._click_through(_window, on=False)
    try:
        _window.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
    _canvas.bind("<Button-1>", _take)
    _canvas.bind("<B1-Motion>", _drag)
    _canvas.bind("<ButtonRelease-1>", _drop)
    _canvas.bind("<Double-Button-1>", lambda event: _lock())
    _window.bind("<Escape>", lambda event: _lock())
    _window.focus_force()
    _notice_now("drag the map, double-click or Esc to lock it")
    logger.info("minimap: placing")
    return True


def _preview():
    """An empty map frame, sized as in the SRV, where the map would be."""
    global _drawn
    rect = overlay._game_rect()
    height = rect[3] - rect[1] if rect else None
    base = coverage.map_side(height)
    side = coverage.map_side(height, zoom())
    unit, _, _, width, full = _layout(side, base)
    _canvas.delete("all")
    _canvas.create_rectangle(1, 1, width - 2, full - 2, outline=palette.ACCENT, width=2)
    _canvas.create_text(width / 2, full / 2, text="Minimap\n\ndrag it here\ndouble-click or Esc",
                        fill=palette.FG, justify="center",
                        font=("Segoe UI", max(9, round(10 * unit)), "bold"))
    _drawn = None                            # the SRV draws over it on its next tick
    _place(side, corner(), rect, base)


def _take(event):
    global _grab
    _grab = (event.x_root, event.y_root, _window.winfo_x(), _window.winfo_y())


def _drag(event):
    if _grab is None:
        return
    px, py, wx, wy = _grab
    _window.geometry(f"+{wx + event.x_root - px}+{wy + event.y_root - py}")


def _drop(event):
    """Remember where it was dropped, in screen pixels. A click without a
    move, the first half of the locking double-click, stores nothing."""
    global _grab, _placed
    moved = _grab is not None and (_window.winfo_x(), _window.winfo_y()) != _grab[2:]
    _grab = None
    if not moved:
        return
    if config is not None:
        config.set(POS_KEY, f"{_window.winfo_x()},{_window.winfo_y()}")
        config.set(FREE_KEY, True)
    if _free is not None:
        _free.set(True)
    _placed = None                           # the next tick reads the new position


def _lock():
    """Out of place mode: the mouse goes through it again."""
    global _placing, _grab, _held
    if not _placing:
        return False
    _drop(None) if _grab else None
    _placing = False
    _grab = None
    for sequence in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>", "<Double-Button-1>"):
        _canvas.unbind(sequence)
    _window.unbind("<Escape>")
    overlay._click_through(_window, on=True)
    try:
        _window.attributes("-alpha", MAP_ALPHA)
    except tk.TclError:
        pass
    try:
        _window.grab_release()
        if _held is not None and _held.winfo_exists():
            _held.grab_set()
            _held.focus_force()
    except tk.TclError:
        pass
    _held = None
    if not _in_srv:
        hide()
    _notice_now("placed")
    logger.info("minimap: placed")
    return True


def _notice_now(text):
    """The hint line under the map, for a few seconds."""
    global _notice, _drawn
    _notice = (text, time.monotonic() + NOTICE_S)
    _drawn = None


def _open_folder():
    try:
        os.makedirs(coverstore.ROOT, exist_ok=True)
        os.startfile(coverstore.ROOT)
    except (OSError, AttributeError) as err:       # AttributeError: not Windows
        logger.warning(f"minimap: could not open {coverstore.ROOT}: {err}")


def prefs_changed():
    global _placed, _drawn
    if config is not None:
        if _enabled is not None:
            config.set(ENABLED_KEY, bool(_enabled.get()))
        if _corner is not None:
            config.set(CORNER_KEY, _corner.get())
        if _keep is not None:
            config.set(KEEP_KEY, bool(_keep.get()))
        if _free is not None:
            config.set(FREE_KEY, bool(_free.get()))
        if _low_value is not None:
            config.set(LOW_VALUE_KEY, bool(_low_value.get()))
        if _golden is not None:
            config.set(GOLDEN_KEY, int(_golden.get()))
            apply_golden()
        changed = False
        for key_id, _, _, config_key in hotkey.ACTIONS:
            if key_id not in _hotkeys:
                continue
            mod_var, key_var = _hotkeys[key_id]
            combo = f"{mod_var.get()}+{key_var.get()}"
            if hotkey.parse(combo) and combo != hotkey.label(key_id):
                config.set(config_key, combo)
                changed = True
        if changed:
            hotkey.restart()
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
            _window.attributes("-alpha", MAP_ALPHA)
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
        logger.warning(f"minimap: no window here, skipping it: {err}")
        stop()
        return False
    logger.info("minimap: built")
    return True


def _hint():
    """The refusal to show on the hint line, while it lasts, else None."""
    if _notice and time.monotonic() < _notice[1]:
        return _notice[0]
    return None


def _layout(side, base=None):
    """(unit, padding, text band, window width, window height) for a map this
    wide. Five bands: the header over the map, and three hotkey rows plus the
    distance row under it.

    `base` is the side the map would have at 1x. Everything round the map - the
    padding, the text bands and the type in them - is measured from that, so
    the size hotkey grows the ground you are looking at and leaves the frame
    and the rows under it exactly where they were.
    """
    unit = (base or side) / 240.0
    pad = max(6, round(8 * unit))
    band = max(18, round(22 * unit))
    return unit, pad, band, side + 2 * pad, side + 5 * band + 2 * pad


def _place(side, where, rect, base=None):
    """Into the corner or the dragged position, shown, and on top: moved every
    tick, HWND_TOPMOST re-sent every overlay.TOPMOST_EVERY_S and on a re-show."""
    global _placed, _shown
    _, _, _, width, height = _layout(side, base)
    if rect:
        left, top, right, bottom = rect
    else:
        left, top = 0, 0
        right, bottom = _window.winfo_screenwidth(), _window.winfo_screenheight()
    dragged = position() if free_move() else None
    if dragged is not None:
        screen = _monitor_rect(*dragged, width, height) or (left, top, right, bottom)
        x, y = free_xy(screen, width, height, dragged)
    else:
        inset = max(16, int((bottom - top) * 0.03))
        x = left + inset if "left" in where else right - inset - width
        y = top + inset if "top" in where else bottom - inset - height
    if _placing:
        # Being dragged: the window is where the pointer put it, and moving
        # it from here would fight the drag.
        x, y = _window.winfo_x(), _window.winfo_y()
    geometry = f"{width}x{height}+{x}+{y}"
    if geometry != _placed:
        _canvas.config(width=width, height=height)
        # Tk has to be told as well, or it puts the window back where it
        # thinks it is on the next layout.
        _window.geometry(geometry)
        _window.update_idletasks()
        _placed = geometry
    if _handle and not _placing:          # while dragging, Tk's geometry() moves it
        user32 = _user32()
        # Asked every tick, not trusted from _shown: after a hide through Win32
        # the map stayed down once Guide and RhinoData had been used, with
        # _shown saying it was up.
        hidden = not _shown or not user32.IsWindowVisible(_handle)
        overlay.set_topmost(_handle, x, y, width, height, force=hidden)
        if hidden:
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


def _draw(side, x, y, heading, in_reach, header, marks=(), distances=False, base=None,
          view=coverage.VIEW_M):
    global _photo
    unit, pad, band, width, height = _layout(side, base)
    image = coverage.render(_coverage, x, y, heading, side, marks, distances, view, base)
    data = io.BytesIO()
    image.save(data, "PNG", compress_level=1)
    _photo = tk.PhotoImage(data=base64.b64encode(data.getvalue()))

    small = ("Consolas", max(8, round(9 * unit)))
    bold = ("Segoe UI", max(9, round(10 * unit)), "bold")
    keys = ("Consolas", max(7, round(8 * unit)))     # the hotkey rows, a step under the rest
    top = pad + band

    _canvas.delete("all")
    _canvas.create_text(pad, pad + band / 2, text=header, fill=palette.MUTED,
                        font=small, anchor="w")
    _canvas.create_text(width - pad, pad + band / 2, text="N ↑", fill=palette.FG,
                        font=small, anchor="e")
    _canvas.create_image(pad, top, image=_photo, anchor="nw")

    _canvas.create_rectangle(pad - 1, top - 1, pad + side, top + side, outline=palette.RULE)

    # Scale bar: one grid square.
    bar = side * coverage.GRID_M / (2 * view)
    bx, by = pad + 8 * unit, top + side - 10 * unit
    _canvas.create_line(bx, by, bx + bar, by, fill=palette.FG, width=max(2, round(2 * unit)))
    _canvas.create_text(bx + bar + 4 * unit, by, text=guide.metres(coverage.GRID_M),
                        fill=palette.FG, font=small, anchor="w")

    # To the centre once one is set, to the latest droppoint - the ship - until
    # then. Short on the right: at the smallest map both lines share 196 px.
    foot = top + side + band / 2 + pad / 2
    to_x, to_y = _coverage.anchor()
    distance = ((to_x - x) ** 2 + (to_y - y) ** 2) ** 0.5
    label = "Center" if _coverage.centered else "Droppoint"
    _canvas.create_text(pad, foot,
                        text=f"{label}  {guide.metres(distance)} "
                             f"{guide.compass(coverage.bearing(x, y, to_x, to_y))}",
                        fill=palette.GOOD, font=small, anchor="w")
    notice = _hint()
    if notice:
        _canvas.create_text(pad, foot + band, text=notice, fill=palette.WARN, font=small, anchor="w")
    else:
        _canvas.create_text(pad, foot + band, text=f"{hotkey.label(hotkey.CENTER)}  set center",
                            fill=palette.MUTED, font=keys, anchor="w")
    _canvas.create_text(pad, foot + 2 * band, text=f"{hotkey.label(hotkey.BORDER)}  set border",
                        fill=palette.MUTED, font=keys, anchor="w")
    _canvas.create_text(pad, foot + 3 * band, text=f"{hotkey.label(hotkey.SIZE)}  zoom",
                        fill=palette.MUTED, font=keys, anchor="w")
    if in_reach:
        _canvas.create_text(width - pad, foot, text=f"{_coverage.painted_km2():.0f} km²",
                            fill=palette.ACCENT, font=bold, anchor="e")
    else:
        _canvas.create_text(width - pad, foot, text="out of range",
                            fill=palette.WARN, font=bold, anchor="e")
