"""RhinoData window: rail of landable bodies | bookmarks of one body | card of the picked one.

Writes only from the card's buttons, the Edit dialog and the import box.
"""

import os
import pathlib
import sqlite3
import io
import tkinter as tk
import webbrowser
from tkinter import messagebox

from PIL import Image

from rs_core import (bodies, cards, coverage, coverstore, database, deposit, grounds, guide,
                     measure, palette, share, spotcard, spotmark, store, yields)
from rs_core.logging import logger
from rs_ui import clipboard, minimap, overlay, rhino, widgets

# Materials on the rates line, and the % of locations under which one is left off.
TOP_MATERIALS = 3
MIN_PCT = 2.0

# Wide enough for "15 d a" and every other body designation in a normal system.
NAME_WIDTH = 8

# The bookmark table, in characters: material, rigs, bearing and distance from
# the location's centre, tons taken out of it, what is left of it.
MATERIAL_W = 17     # "Quartz Pyroxenite", the longest _short() name
RIGS_W = 6
BEARING_W = 4
FROM_W = 6
MINED_W = 9
LEFT_W = 20
# The map table: location, the maps on it, how many bookmarks lie on them.
LOCATION_W = 10
MAPS_W = 22
MARKS_W = 14
# What a location line says about itself before it starts taking room from the
# button and the distance packed on its right.
SUMMARY_W = 54
HEADER_MATERIALS = 3     # materials named on a location line
# Indent of a bookmark row under its location line.
INDENT = "      "

BG = palette.BG
PANEL = palette.PANEL
FG = palette.FG
FG_SOFT = palette.FG_SOFT
DIM = palette.MUTED
ACCENT = palette.ACCENT
GOOD = palette.GOOD
WARN = palette.WARN
ALERT = palette.ALERT
GOLD = palette.GOLD
RULE = palette.RULE

# Window size: a share of the screen both ways, fixed so a pick does not resize it.
SCREEN_SHARE = 0.6
MIN_WIDTH = 900
MIN_HEIGHT = 520
RAIL_WIDTH = 280
CARD_WIDTH = 310
# Square map over the bookmark card, px. At CARD_WIDTH it pushed the card buttons off screen.
MAP_PX = 240
# Half the picked bookmark's diamond on that map, px: over a dot (~4 px at 240).
DIAMOND_PX = 6
# ms a resize has to settle before the card pane is redrawn at its new width.
RESIZE_MS = 150

# Material names that do not fit a MATERIAL_W column or a one-line sentence.
SHORT_NAMES = {
    "low temperature diamonds": "LTD",
    "low temp. diamonds": "LTD",
    "low temp diamonds": "LTD",
    "methanol monohydrate crystals": "Monohydrate",
    "periclase dunite": "P. Dunite",
}

HINT = ("A location folds. The arrow the card starts draws over the game, top "
        "middle - borderless or windowed only.")

_window = None           # only ever one, so the button cannot bury the panel
_host = None             # standalone.py: the root drawn into instead of a Toplevel
_dock = None             # the panel frame, a child of the window, kept across draws
_docking = None          # plugin: main._dock_panel, called with the window before each draw
_scan = None             # (register, sheet, focus, variable, materials)
_on_select = None        # main._pick_materials(parent), the gear beside MATERIAL FILTER; None: disabled
_status_label = None     # the middle pane's status line, rebuilt by every _draw()
_base_width = None       # the window width _size() set, px: the card grows past it
_resize_job = None       # the pending after() of _on_resize
_canvases = {}           # the scrolling canvases of the draw on screen
_scroll = {}             # how far each of them had been scrolled, by name

# What the window shows; survives _draw(), which destroys every widget.
_state = {
    "body": None,         # the body the rail has picked
    "view": "bookmarks",  # "bookmarks" or "mapped"
    "selected": None,     # _key() of the bookmark the card is showing
    "map": None,          # the map row the card is showing, by its own key
    "opened": set(),      # (body, location index) unfolded; every other one is folded
    "ground": None,       # the one rail ground unfolded, or None; every other one is folded
    "grounds_for": None,  # the body whose ground was last unfolded by _rail
    "status": "",
    "import": "",         # what is typed in the import box
    "system": None,       # a system browsed from the search box, or None for the live one
    "search": "",         # what is typed in the search box
    "here": None,         # _key() of the bookmark within yields.ATTRIBUTE_M of the SRV
    "here_picked": None,  # the last "here" put on the card; a hand pick after it stays
}

# The Mined labels of the drawn rows by _key(), and the card's {"key", "label"}
# (label None: no tons line): refresh_mined() sets their text without a redraw.
_mined = {}
_card_tons = {}
# The drawn 'depleted (X t)' and 'worked out (X t)' labels: [(key, label, word)].
_spent_labels = []
# The drawn rows by _key(), and the card pane with what _card() was given:
# _pick_record() relights two rows and rebuilds the card only.
_rows = {}
_panes = {}

# On open, a location with a bookmark this close to the ship is unfolded, m.
UNFOLD_M = 5000.0

# The row marker of the bookmark the ship is at; INDENT's width.
HERE_MARK = "  ◉   "

# The browsed system's register, kept between draws: adopt() re-reads the body
# cache, and a draw happens on every click in the window.
_browsed = None

# Search box: letters typed before it lists systems, and systems listed.
SEARCH_MIN = 3
SEARCH_HITS = 3


def is_open():
    return _window is not None and bool(_window.winfo_exists())


def host(window, dock):
    """Draw into `window` instead of a Toplevel, with `dock` on the Bookmarks tab.

    standalone.py only. `dock` must be a child of `window`: it is packed into
    the middle pane with `in_`, which Tk allows only inside the same toplevel.
    Escape is not bound to destroy `window`.
    """
    global _host, _dock
    _host, _dock = window, dock


def hosted():
    return _host is not None


def dock_with(build):
    """Plugin: `build(window)` returns the panel frame for the Bookmarks tab, a
    child of `window`, or None. Called before each draw; ignored under host()."""
    global _docking
    _docking = build


def _fetch_dock():
    global _dock
    if _host is None and _docking is not None:
        _dock = _docking(_window)


def show(parent, register, sheet, focus=None, variable=None, materials=(), here=None,
         location=None, on_select=None):
    """Open the window, or redraw and raise the open one.

    `focus`: one material; only grounds that carried it are listed, only its
    bookmarks counted. `here`: Status.json body, picked and listed whatever the
    filter. `variable`: the panel's filter StringVar itself, not the Material box.
    `location`: the panel's Location on `here`; unfolded on open with those of
    _mark_here and _unfold_near. `on_select(parent)`: the gear beside MATERIAL FILTER.
    """
    global _window, _scan, _on_select

    # First, so the draw below reads the material that was just picked.
    _scan = (register, sheet, focus, variable, materials)
    _on_select = on_select

    if _window is not None and _window.winfo_exists():
        logger.debug(f"scan: redraw, system={register.system!r} focus={focus!r}")
        _state["status"] = ""       # about the list being rebuilt
        _fetch_dock()
        _unfold_near()
        _mark_here()
        _draw()
        if _window.state() == "iconic":
            _window.deiconify()
        _raise()
        return _window

    logger.debug(f"scan: open, system={register.system!r} focus={focus!r}")
    _window = _host if _host is not None else tk.Toplevel(parent)
    _window.configure(bg=BG)
    # Debug: Tk can destroy the window with no Python frame to trace.
    _window.bind("<Destroy>", _log_destroy, add="+")
    if _host is None:
        _window.bind("<Escape>", lambda event: _window.destroy())
    _window.bind("<Activate>", _on_front, add="+")
    _raise()
    _size(_window)
    _window.bind("<Configure>", _on_resize, add="+")

    _reset(view="bookmarks", here=None, here_picked=None,
           opened={(here, location)} if here and location is not None else set())
    _scroll.clear()
    if here:
        _state["body"] = here
    _fetch_dock()
    _unfold_near()
    _mark_here()
    _draw()
    return _window


def _raise():
    """Topmost until the window has the focus (_drop_topmost), then lifted and focused.

    Opened by a key press with the game in front: lift() alone loses the foreground race.
    """
    _window.attributes("-topmost", True)
    _window.bind("<FocusIn>", _drop_topmost, add="+")
    _window.lift()
    _window.focus_force()


def _reset(**changes):
    """Clear the picked bookmark and map, the unfolded ground and the status line; apply `changes`."""
    _state.update(selected=None, map=None, ground=None, grounds_for=None, status="")
    _state.update(changes)


def _unfold_near():
    """On open: unfold every location holding a bookmark within UNFOLD_M of the
    Status.json position, whatever number it was filed under - a mistyped
    Location otherwise hides it. Live system only; no position, nothing."""
    live = _scan[0] if _scan else None
    if live is None or not live.system or _state["system"]:
        return
    status = spotmark.read_status()
    body, lat, lon = status.get("BodyName"), status.get("Latitude"), status.get("Longitude")
    radius = status.get("PlanetRadius")
    if not body or lat is None or lon is None or not radius:
        return
    for record in cards.for_system(live.system):
        if (record.get("planet_name") != body or record.get("latitude") is None
                or record.get("longitude") is None):
            continue
        if guide.distance(lat, lon, record["latitude"], record["longitude"], radius) <= UNFOLD_M:
            _state["opened"].add((body, record.get("location_index")))


def _on_front(event):
    """<Activate>: the window came to the front. Redraws only when the bookmark
    the ship is at changed since the last look."""
    if event.widget is _window and _mark_here():
        _draw()


def _mark_here():
    """Pick the bookmark within 175 m of the SRV; True when that bookmark changed.

    Picks: its body, its location unfolded, the card on it. yields.ATTRIBUTE_M.
    In the SRV only (Status.json Flags & coverage.IN_SRV), live system only.
    One Status.json read and one cards.for_system() per call.
    """
    live, focus = (_scan[0], _scan[2]) if _scan else (None, None)
    if live is None or not live.system or _state["system"]:
        return False
    status = spotmark.read_status()
    if not status:
        return False            # torn read: keep what was known
    record = None
    if int(status.get("Flags") or 0) & coverage.IN_SRV:
        found = yields.nearest(cards.for_system(live.system), status.get("BodyName"),
                               status.get("Latitude"), status.get("Longitude"),
                               status.get("PlanetRadius"))
        record = found[0] if found else None
    # A bookmark the material filter hides cannot be shown or picked.
    if record and focus and (record.get("commodity") or "").lower() != focus.lower():
        record = None
    key = _key(record) if record else None
    if key == _state["here"]:
        return False
    _state["here"] = key
    if record is None:
        if _state["status"].startswith("You are at "):
            _state["status"] = ""
        return True
    if key != _state["here_picked"]:
        _state["here_picked"] = key
        _state["body"] = record.get("planet_name")
        _state["view"] = "bookmarks"
        _state["selected"] = key
        _state["opened"].add((record.get("planet_name"), record.get("location_index")))
        _state["status"] = (f"You are at {_loc(record.get('location_index'))}, "
                            f"{_short(record.get('commodity'))} - picked on the card.")
    return True


def _size(window):
    """SCREEN_SHARE of the screen both ways, at least MIN_WIDTH x MIN_HEIGHT; sets _base_width."""
    width = max(MIN_WIDTH, int(window.winfo_screenwidth() * SCREEN_SHARE))
    height = max(MIN_HEIGHT, int(window.winfo_screenheight() * SCREEN_SHARE))
    logger.debug(f"scan: {width}x{height}, {SCREEN_SHARE:.0%} of the screen")
    global _base_width
    window.geometry(f"{width}x{height}")
    window.minsize(MIN_WIDTH, MIN_HEIGHT)
    _base_width = width


def _grown(px):
    """`px` scaled by how far the window is wider than _size() made it; never below `px`."""
    width = _window.winfo_width() if _window is not None and _window.winfo_exists() else 0
    return round(px * max(1.0, width / _base_width)) if _base_width else px


def _on_resize(event):
    """<Configure>: once the size has held RESIZE_MS, one _draw if the card width changed."""
    global _resize_job
    if event.widget is not _window:
        return
    if _resize_job is not None:
        _window.after_cancel(_resize_job)

    def settle():
        global _resize_job
        _resize_job = None
        if _panes.get("card_px") != _grown(CARD_WIDTH):
            _draw()
    _resize_job = _window.after(RESIZE_MS, settle)


def _drop_topmost(event):
    """<FocusIn> on any widget of the window: drop topmost (set by _raise) and this binding."""
    if _window is None or not _window.winfo_exists():
        return
    if event.widget.winfo_toplevel() is not _window:
        return
    logger.debug("scan: in front, dropping topmost")
    _window.attributes("-topmost", False)
    _window.unbind("<FocusIn>")


def _log_destroy(event):
    if _window is not None and event.widget is _window:
        logger.debug("scan: the window was destroyed")


def _clear(window):
    for child in window.winfo_children():
        if child is not _dock:
            child.destroy()


def _pack_dock(parent):
    """The panel into `parent`, where the next pack call puts it.
    Unpacked again when `parent` is destroyed by the next draw."""
    if _dock is None:
        return
    # Natural width, left: filled, column 1 stretched Rigs and the menus to the pane's right edge.
    _dock.pack(in_=parent, anchor="w", padx=16, pady=(10, 0))
    # Older than the pane frames in stacking order: without lift() they cover it.
    _dock.lift()


# ---------------------------------------------------------------- the drawing


def _draw():
    """Rebuild all three panes; the lists keep their scroll position (_remember_scroll)."""
    if _window is None or not _window.winfo_exists() or _scan is None:
        return
    live, sheet, focus, variable, materials = _scan
    register = _shown_register(live)
    _remember_scroll()
    _clear(_window)
    _mined.clear()
    _card_tons.clear()
    _spent_labels.clear()
    _rows.clear()
    _panes.clear()

    listed = _bodies(register, sheet, focus)
    body = _current(listed)
    records = list(body["shown"]) if body else []
    groups = _by_location(records)
    # Read once a draw: gzipped blobs, used by the list, the location lines and the card.
    maps = coverstore.maps(body["name"], system_address=_system_address()) if body else {}

    _window.title(f"RhinoData - {register.system or 'unknown system'}"
                  + (f" - {body['short']}" if body else "")
                  + (f" - {focus}" if focus else ""))

    outer = tk.Frame(_window, bg=BG)
    outer.pack(fill="both", expand=True)

    rail = tk.Frame(outer, bg=PANEL, width=RAIL_WIDTH)
    rail.pack(side="left", fill="y")
    rail.pack_propagate(False)
    _rail(rail, register, sheet, focus, variable, materials, listed, body, live)
    _panes["rail"] = rail

    card = tk.Frame(outer, bg=BG, width=_grown(CARD_WIDTH))
    card.pack(side="right", fill="y")
    card.pack_propagate(False)

    middle = tk.Frame(outer, bg=BG)
    middle.pack(side="left", fill="both", expand=True)
    picked = _middle(middle, register, sheet, focus, body, records, groups, maps, materials)

    _import_strip(middle)

    _card(card, register, sheet, body, picked, maps)
    _panes.update(card=card, register=register, sheet=sheet, body=body, maps=maps,
                  card_px=_grown(CARD_WIDTH))


def _bodies(register, sheet, focus):
    """Every listed body in rail order.

    Each carries `marks`, all its bookmarks, and `shown`, those `focus` leaves.
    """
    marked = cards.by_body(register.system) if register.system else {}
    prefix = (register.system or "") + " "
    listed = []
    by_ground = register.by_ground()
    if focus:
        # Highest sheet rate of `focus` first, no row last; GROUND_ORDER on ties.
        by_ground.sort(key=lambda item: (sheet.rate(item[0], focus) is None,
                                         -(sheet.rate(item[0], focus) or 0)))
    for ground, found in by_ground:
        # The picked body stays listed whatever the filter.
        if focus and sheet.rate(ground, focus) is None \
                and not any(body["name"] == _state["body"] for body in found):
            continue
        for body in found:
            row = dict(body)
            name = body["name"]
            # System prefix dropped: it is in the heading, and pushed the counts off the rail.
            row["short"] = name[len(prefix):] if name.startswith(prefix) else name
            row["ground"] = ground
            row["marks"] = marked.get(name) or []
            row["shown"] = [r for r in row["marks"]
                            if not focus
                            or (r.get("commodity") or "").lower() == focus.lower()]
            listed.append(row)
    return listed


def _current(listed):
    """The picked body, else the first with a `shown` bookmark, else the first; sets _state["body"]."""
    if not listed:
        return None
    for entry in listed:
        if entry["name"] == _state["body"]:
            return entry
    for entry in listed:
        if entry["shown"]:
            _state["body"] = entry["name"]
            return entry
    _state["body"] = listed[0]["name"]
    return listed[0]


def _key(record):
    """(planet_name, location_index, commodity, marked_at): one bookmark across draws."""
    return (record.get("planet_name"), record.get("location_index"),
            record.get("commodity"), record.get("marked_at"))


def _short(material):
    """The names that do not fit a column: LTD and P. Dunite."""
    return SHORT_NAMES.get((material or "").lower(), material or "unknown")


def _pct(value):
    """40.0 -> '40', 61.9 -> '61.9'."""
    return f"{value:g}"


def _loc(index):
    """'loc 7', or 'loc -' for a bookmark from before location numbers."""
    return f"loc {index}" if index is not None else "loc -"


# ------------------------------------------------------------------- the rail


def _rail(parent, register, sheet, focus, variable, materials, listed, body, live=None):
    """The search box, the system, the material picker, and every body under it."""
    head = tk.Frame(parent, bg=PANEL)
    head.pack(fill="x", padx=13, pady=(14, 0))
    _search_box(head)
    name = tk.Label(head, text=register.system or "no system yet", bg=PANEL, fg=FG,
                    anchor="w", justify="left", font=("Segoe UI", 12, "bold"),
                    wraplength=RAIL_WIDTH - 26)
    name.pack(fill="x", pady=(6, 0))
    # Easter egg, unlabelled: a click on the system name runs rs_ui/rhino.py.
    name.bind("<Button-1>", lambda event: rhino.run(name.winfo_toplevel()))

    # Only while a searched system is shown.
    if _state["system"] and live is not None and live.system:
        back = widgets.button(head, f"\u25c0  Back to {live.system}", _back_to_live)
        back.config(fg=GOOD, font=("Segoe UI", 9, "bold"))
        back.pack(fill="x", pady=(6, 0))

    count = len(register)
    marks = sum(len(entry["shown"]) for entry in listed)
    line = (f"{count} landable {'body' if count == 1 else 'bodies'} scanned"
            f"  ·  {marks} bookmark{'' if marks == 1 else 's'}")
    tk.Label(head, text=line, bg=PANEL, fg=DIM, anchor="w", justify="left",
             font=("Segoe UI", 8), wraplength=RAIL_WIDTH - 26).pack(fill="x", pady=(3, 0))

    if variable is not None and materials:
        _picker(parent, variable, materials, focus)

    _rail_footer(parent, sheet)
    listing = _scrollable(parent, "rail", bg=PANEL, padx=(0, 0))
    # A newly picked body (open, here, jump, _mark_here) unfolds its ground and
    # folds the rest, once; a fold by hand after that stays.
    if body is not None and _state["grounds_for"] != body["name"]:
        _state["grounds_for"] = body["name"]
        _state["ground"] = body["ground"]
    ground = None
    for entry in listed:
        if entry["ground"] != ground:
            ground = entry["ground"]
            _rail_ground(listing, sheet, focus, ground,
                         [e for e in listed if e["ground"] == ground])
        if ground == _state["ground"]:
            _rail_body(listing, entry, body is not None and entry["name"] == body["name"])
    if not listed:
        tk.Label(listing, text="nothing listed here yet", bg=PANEL, fg=DIM, anchor="w",
                 font=("Segoe UI", 9)).pack(fill="x", padx=13, pady=(8, 0))


def arrived():
    """Redraw an open window for the system just jumped to, without raising it.

    Drops the picked body, bookmark and map of the old system. A system browsed
    from the search box stays shown.
    """
    if not is_open():
        return
    if not _state["system"]:
        _reset(body=None, opened=set())
    _draw()


def _shown_register(live):
    """The live register, or a searched system's from the body cache (Register.adopt).

    The searched one is kept in _browsed between draws: adopt() re-reads the cache.
    """
    global _browsed
    system = _state["system"]
    if not system or system == live.system:
        return live
    if _browsed is None or _browsed.system != system:
        _browsed = bodies.Register()
        _browsed.adopt(system, store.load(system))
    return _browsed


def _bookmarked_systems():
    """[(system, bookmarks), ...] of the systems holding bookmarks, most recently marked first."""
    try:
        with database.connect() as conn:
            return conn.execute(
                "SELECT system, count(*) FROM bookmarks WHERE system IS NOT NULL "
                "GROUP BY system ORDER BY max(id) DESC").fetchall()
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"scan: could not list the bookmarked systems: {err}")
        return []


def _totals():
    """(systems, bookmarks, bodies, maps) over the whole database; None on a read error.

    systems counts as _bookmarked_systems() does: systems that hold bookmarks.
    """
    try:
        with database.connect() as conn:
            systems, marks, bodies_ = conn.execute(
                "SELECT count(DISTINCT system), count(*), count(DISTINCT planet_name) "
                "FROM bookmarks").fetchone()
            maps = conn.execute("SELECT count(*) FROM maps").fetchone()[0]
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"scan: could not count the totals: {err}")
        return None
    return systems, marks, bodies_, maps


def _totals_line(totals):
    """'235 bookmarks  ·  23 bodies  ·  44 maps'; '' with no bookmarks and no maps."""
    if not totals or not (totals[1] or totals[3]):
        return ""
    _, marks, bodies_, maps = totals
    return (f"{marks} bookmark{'' if marks == 1 else 's'}"
            f"  ·  {bodies_} {'body' if bodies_ == 1 else 'bodies'}"
            f"  ·  {maps} map{'' if maps == 1 else 's'}")


def _search_box(parent):
    """SYSTEMS WITH BOOKMARKS box: up to SEARCH_HITS matches from SEARCH_MIN letters; a pick browses it."""
    typed = tk.StringVar(value=_state["search"])
    entry = tk.Entry(parent, textvariable=typed, bg=BG, fg=FG, insertbackground=FG,
                     relief="solid", borderwidth=1, highlightthickness=0,
                     font=("Segoe UI", 9))
    totals = _totals()
    title = "SYSTEMS WITH BOOKMARKS" + (f"  ·  {totals[0]}" if totals else "")
    tk.Label(parent, text=title, bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(fill="x", pady=(0, 2))
    entry.pack(fill="x")

    hits = tk.Frame(parent, bg=PANEL)
    hits.pack(fill="x")
    line = _totals_line(totals)
    if line:
        tk.Label(parent, text=line, bg=PANEL, fg=DIM, anchor="w",
                 font=("Segoe UI", 8)).pack(fill="x", pady=(3, 0))

    def redraw(*_):
        text = typed.get().strip().lower()
        _state["search"] = typed.get()
        for child in hits.winfo_children():
            child.destroy()
        if len(text) < SEARCH_MIN:
            return
        found = [(system, n) for system, n in _bookmarked_systems()
                 if text in system.lower()]
        for system, n in found[:SEARCH_HITS]:
            row = tk.Label(hits, text=f"{system[:24]:<24} {n:>2} bm", bg=PANEL,
                           fg=ACCENT if system == _state["system"] else FG_SOFT,
                           anchor="w", font=("Consolas", 9))
            row.pack(fill="x")
            widgets.clickable(row, lambda pick=system: _browse(pick))
        if not found:
            tk.Label(hits, text="no bookmarks in a system of that name", bg=PANEL,
                     fg=DIM, anchor="w", font=("Segoe UI", 8)).pack(fill="x")

    typed.trace_add("write", redraw)
    redraw()


def _browse(system):
    """Show a searched system. Nothing about marking changes - the panel's
    Bookmark button reads the journal, not this."""
    if system == _state["system"]:
        return
    _reset(system=system, body=None,
           status=f"Showing {system}. Bookmark still marks where the ship is.")
    _draw()


def _back_to_live():
    _reset(system=None, search="", body=None)
    _draw()


def _rail_footer(parent, sheet):
    """At the foot of the rail: where the rates come from, or how to restore mining_sheet.json."""
    if sheet.loaded:
        text = (f"Rates from every mining location read so far, {sheet.generated}. "
                "Where to prospect, not what you will find.")
    else:
        text = ("mining_sheet.json is missing, so only the body types are shown. "
                "Reinstall the plugin, or drop the file back beside load.py.")
    tk.Frame(parent, bg=RULE, height=1).pack(side="bottom", fill="x")
    tk.Label(parent, text=text, bg=PANEL, fg=DIM, anchor="w", justify="left",
             font=("Segoe UI", 7), wraplength=RAIL_WIDTH - 26).pack(
        side="bottom", fill="x", padx=13, pady=(6, 8))


def _rail_ground(parent, sheet, focus, ground, entries):
    """A ground header in the rail: fold arrow, label, body count; with `focus`
    its sheet rate; bookmark sum. The whole row folds it."""
    row = tk.Frame(parent, bg=PANEL)
    row.pack(fill="x", pady=(8, 2))
    unfolded = ground == _state["ground"]
    tk.Label(row, text="▼" if unfolded else "▶", bg=PANEL, fg=ACCENT, width=3,
             font=("Segoe UI", 7)).pack(side="left", padx=(8, 0))
    tk.Label(row, text=f"{grounds.label(ground)} ({len(entries)})", bg=PANEL, fg=ACCENT,
             anchor="w", font=("Segoe UI", 9, "bold")).pack(side="left")
    marks = sum(len(e["shown"]) for e in entries)
    pct = sheet.rate(ground, focus) if focus else None
    right = "  ".join(t for t in (f"{_pct(pct)}%" if pct is not None else "",
                                  f"{marks} bm" if marks else "") if t)
    tk.Label(row, text=right, bg=PANEL, fg=GOLD, anchor="e",
             font=("Consolas", 9)).pack(side="right", padx=(0, 13))
    widgets.clickable(row, lambda: _toggle_ground(ground))


def _toggle_ground(ground):
    """Unfold one ground and fold the rest, or fold it if open; rebuilds the rail only."""
    _state["ground"] = None if ground == _state["ground"] else ground
    refresh_rail()


def _rail_body(parent, entry, chosen):
    """One rail row: name, distance, locations, bookmarks; the whole row picks the body."""
    row = tk.Frame(parent, bg=PANEL)
    row.pack(fill="x")
    inner = tk.Frame(row, bg=PANEL)
    inner.pack(side="left", fill="x", expand=True, padx=(13, 13), pady=5)

    marks = len(entry["shown"])
    locations = entry.get("locations")
    distance = entry.get("distance")
    # The picked body: name bold in gold.
    tk.Label(inner, text=entry["short"][:NAME_WIDTH], bg=PANEL,
             fg=GOLD if chosen else FG_SOFT, anchor="w", width=NAME_WIDTH,
             font=("Consolas", 10, "bold" if chosen else "normal")).pack(side="left")
    tk.Label(inner, text=f"{distance:,.0f} Ls" if distance is not None else "-",
             bg=PANEL, fg=DIM, anchor="e", width=9,
             font=("Consolas", 9)).pack(side="left")
    tk.Label(inner, text=f"{marks} bm" if marks else "", bg=PANEL, fg=GOLD, anchor="e",
             font=("Consolas", 9)).pack(side="right")
    tk.Label(inner, text=f"{locations} loc" if locations is not None else "unprobed",
             bg=PANEL, fg=DIM, anchor="e", font=("Consolas", 9)).pack(side="right", padx=6)

    widgets.clickable(row, lambda: _pick_body(entry["name"]))


def _picker(parent, variable, materials, focus):
    """MATERIAL FILTER: an OptionMenu on the panel's own `variable`, the gear, a hint line.

    No trace added here: one per open would draw the window once per open on each pick.
    """
    box = tk.Frame(parent, bg=PANEL)
    box.pack(fill="x", padx=13, pady=(10, 0))
    head = tk.Frame(box, bg=PANEL)
    head.pack(fill="x")
    tk.Label(head, text="MATERIAL FILTER", bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(side="left", anchor="s")
    # Packed side="right" in a fill="x" row: right edge flush with the picker's.
    # No gear without _on_select (standalone host).
    if _on_select is not None:
        gear = widgets.button(head, "⚙", lambda: _on_select(box.winfo_toplevel()))
        gear.config(padx=4, pady=0, font=("Segoe UI Symbol", 8))
        gear.pack(side="right")
        widgets.tooltip(gear, "Setting available materials")

    picker = tk.OptionMenu(box, variable, *materials)
    picker.config(relief="solid", borderwidth=1, highlightthickness=0,
                  bg=BG, fg=FG, activebackground=BG, activeforeground=ACCENT,
                  anchor="w", padx=6, pady=0, font=("Segoe UI", 9))
    picker["menu"].config(bg=PANEL, fg=FG, activebackground=ACCENT,
                          activeforeground=BG, borderwidth=1,
                          activeborderwidth=0, tearoff=False,
                          font=("Segoe UI", 9))
    widgets.letter_jump(picker)
    if len(materials) < 2:          # ALL_MATERIALS only
        widgets.no_materials_hint(picker)
    picker.pack(fill="x", pady=(4, 0))
    tk.Label(box, text=f"Only {_short(focus)}, everywhere." if focus
                       else "The rail counts and the list follow it.",
             bg=PANEL, fg=DIM, anchor="w", justify="left", font=("Segoe UI", 8),
             wraplength=RAIL_WIDTH - 26).pack(fill="x", pady=(4, 0))


# ----------------------------------------------------------------- the middle


def _middle(parent, register, sheet, focus, body, records, groups, maps, materials=()):
    """Body heading, its two tabs and the open tab's list.

    Returns what the card shows: a bookmark, a map row or None.
    """
    if body is None:
        _pack_dock(parent)
        _empty(parent, register, focus)
        _status_line(parent, "")
        return None

    head = tk.Frame(parent, bg=BG)
    head.pack(fill="x", padx=16, pady=(14, 0))

    title = tk.Frame(head, bg=BG)
    title.pack(fill="x")
    tk.Label(title, text=body["short"], bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 16, "bold")).pack(side="left")
    # Stop the arrow on the heading: its card may be folded away or on another body.
    if overlay.guiding():
        stop = widgets.button(title, "Stop the arrow", _stop_guide)
        stop.config(fg=GOOD)
        stop.pack(side="left", padx=(12, 0))

    # All the body's marks, not `shown`: the material filter does not apply to maps.
    mapped, unknown = coverage.mapped_locations(maps, body["name"], body["marks"])
    total = body.get("locations")
    # Packed from the right edge inwards, so Bookmarks lands left of Mapped.
    _tab(title, f"Mapped {len(mapped)}" + (f"/{total}" if total is not None else ""),
         "mapped", bool(maps))
    held = len(body["marks"])
    _tab(title, f"Bookmarks {len(records)}"
         + (f" of {held}" if focus and held != len(records) else ""), "bookmarks", True)

    tk.Label(head, text=_about(body), bg=BG, fg=DIM, anchor="w",
             font=("Segoe UI", 9)).pack(fill="x", pady=(4, 0))
    _rates(head, sheet, body, focus, materials)

    if _state["view"] == "bookmarks":
        _pack_dock(parent)
    if _state["view"] == "mapped":
        picked = _mapped_list(parent, body, mapped, unknown)
    else:
        picked = _bookmark_list(parent, body, groups, maps)

    _status_line(parent, HINT)
    return picked


def _status_line(parent, idle):
    """The status line at the bottom of `parent`; `idle`: its text while _state["status"] is empty."""
    global _status_label
    _status_label = tk.Label(parent, text=_state["status"] or idle, bg=BG, fg=DIM,
                             anchor="w", justify="left", font=("Segoe UI", 8))
    _status_label.pack(side="bottom", fill="x", padx=16, pady=(6, 10))
    _status_label.bind("<Configure>", widgets.wrap_to_width, add="+")


def _import_strip(parent):
    """One row at the bottom of the middle pane: a box for a RhinoData code and Import.
    The typed text is kept in _state["import"] across draws."""
    strip = tk.Frame(parent, bg=BG)
    strip.pack(side="bottom", fill="x", padx=16, pady=(6, 0))
    text = tk.StringVar(master=strip, value=_state["import"])
    text.trace_add("write", lambda *_: _state.__setitem__("import", text.get()))
    pasted = tk.Entry(strip, textvariable=text)
    widgets.style_field(pasted)
    widgets.button(strip, "Import", _import_code).pack(side="right", padx=(6, 0))
    pasted.pack(side="left", fill="x", expand=True)
    pasted.bind("<Return>", lambda _: _import_code())


def _import_code():
    """Import the RhinoData code in the import box; the result on the status line.

    Skips codes this install shared or imported (share.mine) and bookmarks
    already here (cards.nearby). The box is emptied on an import.
    """
    try:
        state, spot = share.take(_state["import"])
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not import a shared bookmark: {err}")
        _say(f"Bookmark not imported: {err}")
        return
    if state is None:
        _say("No RhinoData code found. Paste the whole RhinoData:... line.")
        return
    what = f"{spot['commodity']} on {spot['planet_name']}"
    if state == "seen":
        _say(f"{what}: this code was shared or imported here before.")
    elif state == "known":
        _say(f"{what} is already bookmarked.")
    else:
        parts = [spot["system"], spot["planet_name"]]
        if spot.get("location_index") is not None:
            parts.append(f"Location {spot['location_index']}")
        parts.append(spot["commodity"])
        if spot.get("rigs") is not None:
            parts.append(f"{spot['rigs']} rigs")
        _state["import"] = ""
        _state["status"] = " ".join(parts) + " bookmark imported"
        _draw()


def _say(text):
    """Set the status line without a _draw(): a full redraw rebuilds every pane."""
    _state["status"] = text
    if _status_label is not None and _status_label.winfo_exists():
        _status_label.config(text=text or HINT)
    else:
        _draw()


def _tab(parent, text, view, enabled):
    """The Bookmarks or Mapped tab, packed from the right edge inwards."""
    on = _state["view"] == view
    tab = widgets.button(parent, text, (lambda: _pick_view(view)) if enabled else None)
    tab.config(bg=PANEL if on else BG, fg=ACCENT if on else FG_SOFT,
               activebackground=PANEL, padx=10)
    tab.pack(side="right", padx=(6, 0))


def _bookmark_list(parent, body, groups, maps):
    """Column header and every location of the body, folded per _state["opened"].

    Returns the bookmark the card shows: the selected one if its location is
    open, else the first open row, else None.
    """
    header = tk.Frame(parent, bg=BG)
    header.pack(fill="x", padx=16, pady=(12, 0))
    # 4 px: the accent strip each row starts with.
    tk.Frame(header, bg=BG, width=4).pack(side="left", fill="y")
    tk.Label(header, text=INDENT + _columns("Material", "Rigs", "Brg", "Dist", "Mined", "Est. left"),
             bg=BG, fg=DIM, anchor="w", font=("Consolas", 9)).pack(side="left")
    if groups:
        folded = all(not _unfolded(body["name"], index) for index, _group in groups)
        widgets.button(header, "Open all" if folded else "Fold all",
                lambda: _fold_all(body["name"], groups, not folded)).pack(side="right")
    tk.Frame(parent, bg=RULE, height=1).pack(fill="x", padx=16, pady=(3, 0))

    listing = _scrollable(parent, "list")
    if not groups:
        tk.Label(listing, text="   no bookmarks on this body yet", bg=BG, fg=DIM,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(8, 0))
        return None

    # One Status.json read for the table; the distances are as of this draw.
    status = spotmark.read_status()
    ordered = [(index, cards.ordered(group), _unfolded(body["name"], index))
               for index, group in groups]
    # Picked before the rows are drawn: it is the lit one.
    open_rows = [record for _index, rows, open_here in ordered if open_here
                 for record in rows]
    picked = next((record for record in open_rows
                   if _key(record) == _state["selected"]),
                  open_rows[0] if open_rows else None)
    for index, rows, open_here in ordered:
        _location_header(listing, body["name"], index, rows, maps, status, open_here)
        if not open_here:
            continue
        for record in rows:
            _bookmark_row(listing, body["name"], record, picked, maps)
    return picked


def _location_header(parent, body, index, group, maps, status, open_here):
    """'loc 2', summary, nearest distance and Share map; a click on the line folds it.

    Button and distance packed first, from the right: pack gives out width in call order.
    """
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(8, 0))
    tk.Label(row, text="▼" if open_here else "▶", bg=BG, fg=ACCENT, width=3,
             font=("Segoe UI", 7)).pack(side="left")
    tk.Label(row, text=_loc(index), bg=BG, fg=FG, anchor="w", width=8,
             font=("Segoe UI", 10, "bold")).pack(side="left")

    # The picture is found on the press: that rebuilds a mask per saved map of the body.
    widgets.button(row, "Share map",
            (lambda: _share_map(body, group)) if maps else None).pack(
        side="right", padx=(8, 16))
    tk.Label(row, text=_nearest(group, status), bg=BG, fg=FG_SOFT, anchor="e",
             font=("Consolas", 9)).pack(side="right")

    # Each material once, HEADER_MATERIALS of them, most Cr/t first (Sheet.values()).
    # Unpriced (0, or mining_sheet.json missing) keep the row order: most rigs first.
    values = _scan[1].values()
    kinds = {}
    for record in group:
        kinds.setdefault((record.get("commodity") or "").lower(), record.get("commodity"))
    ranked = sorted(kinds.items(), key=lambda kind: -values.get(kind[0], 0))
    names = ", ".join(_short(name) for _lower, name in ranked[:HEADER_MATERIALS])
    worked = sum(1 for record in group if cards.depleted(record))
    summary = (f"{len(group)} deposit{'' if len(group) == 1 else 's'}  ·  {names}"
               + (f"  ·  {worked} worked out" if worked else ""))
    tk.Label(row, text=summary[:SUMMARY_W], bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 8)).pack(side="left")

    widgets.clickable(row, lambda: _fold(body, index), skip_buttons=True)
    tk.Frame(parent, bg=PANEL, height=1).pack(fill="x", padx=(0, 16), pady=(4, 0))


def _bookmark_row(parent, body, record, picked, maps):
    """One deposit row: material, rigs, bearing and distance from the map centre, mined, left, Edit."""
    lit = picked is not None and _key(record) == _key(picked)
    dead = cards.depleted(record)
    bg = PANEL if lit else BG
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=(0, 16), pady=1)
    tk.Frame(row, bg=ACCENT if lit else bg, width=4).pack(side="left", fill="y")
    _rows[_key(record)] = row
    # Packed before the labels: pack gives out width in call order, so a
    # narrow pane clips Est. left instead of dropping the button.
    widgets.button(row, "Edit", lambda: _edit_bookmark(record)).pack(side="right", padx=(6, 0))

    rigs = record.get("rigs")
    left = deposit.describe(rigs, record.get("amount"), record.get("density"))
    if dead:
        left = _spent(record, "depleted")
    # One label per colour.
    material = _short(record.get("commodity"))
    mark = HERE_MARK if _key(record) == _state["here"] else INDENT
    tk.Label(row, text=mark + f"{material[:MATERIAL_W]:<{MATERIAL_W}} "
                                f"{(str(rigs) if rigs is not None else '-'):>{RIGS_W}} ",
             bg=bg, fg=DIM if dead else ACCENT, anchor="w",
             font=("Consolas", 9)).pack(side="left")
    bearing, away = _from_centre(maps, body, record)
    tk.Label(row, text=f"{bearing:>{BEARING_W}} {away:>{FROM_W}} ", bg=bg,
             fg=DIM if dead else FG_SOFT, anchor="e",
             font=("Consolas", 9)).pack(side="left")
    # Own label: refresh_mined() sets it in place.
    mined = yields.short(record)
    label = tk.Label(row, text=f"{mined or '-':>{MINED_W}} ", bg=bg,
                     fg=GOOD if mined else DIM, anchor="e", font=("Consolas", 9))
    label.pack(side="left")
    _mined[_key(record)] = label
    left_label = tk.Label(row, text=f"{left or '-':>{LEFT_W}}", bg=bg,
                          fg=ALERT if dead else (WARN if left else DIM), anchor="e",
                          font=("Consolas", 9))
    left_label.pack(side="left")
    if dead:
        _spent_labels.append((_key(record), left_label, "depleted"))

    widgets.clickable(row, lambda: _pick_record(record), skip_buttons=True)


def _spent(record, word):
    """`word`, with the tons the depleted cycle gave: 'depleted (612 t)'."""
    tons = yields.depleted_tons(record)
    return f"{word} ({tons:,} t)" if tons else word


def _columns(material, rigs, bearing, away, mined, left):
    """A bookmark table line at MATERIAL_W .. LEFT_W; the header and the rows both use it."""
    return (f"{material[:MATERIAL_W]:<{MATERIAL_W}} {rigs:>{RIGS_W}} "
            f"{bearing:>{BEARING_W}} {away:>{FROM_W}} "
            f"{mined:>{MINED_W}} {left:>{LEFT_W}}")


def _from_centre(maps, body, record):
    """('123°', '850 m') from the bookmark's map centre to the bookmark.

    ('-', '-') off any map, or on a map whose `center` was never set (Ctrl+Alt+Z).
    """
    found = _map_data(body, record, maps)
    centre = found[1].get("center") if found else None
    if not centre:
        return "-", "-"
    try:
        clat, clon = float(centre[0]), float(centre[1])
        lat, lon = float(record["latitude"]), float(record["longitude"])
        metres = guide.distance(clat, clon, lat, lon, float(found[1]["radius"]))
    except (IndexError, TypeError, ValueError):
        return "-", "-"
    return f"{round(guide.bearing(clat, clon, lat, lon)) % 360}°", guide.metres(metres)


def _mapped_list(parent, body, mapped, unknown):
    """Locations with a saved map, then the maps tied to none. Returns the map row the card shows.

    Untied rows are keyed by map name: their location is "-" for all of them.
    """
    header = tk.Frame(parent, bg=BG)
    header.pack(fill="x", padx=16, pady=(12, 0))
    tk.Frame(header, bg=BG, width=4).pack(side="left", fill="y")
    tk.Label(header, text="   " + _map_columns("Location", "Maps", "Bookmarks"),
             bg=BG, fg=DIM, anchor="w", font=("Consolas", 8)).pack(side="left")
    tk.Frame(parent, bg=RULE, height=1).pack(fill="x", padx=16, pady=(3, 0))

    listing = _scrollable(parent, "list")
    counts = {}
    for record in body["marks"]:
        index = record.get("location_index")
        counts[index] = counts.get(index, 0) + 1

    rows = [{"key": f"loc {index}", "location": f"loc {index}", "names": mapped[index],
             "count": counts.get(index, 0)} for index in sorted(mapped)]
    rows += [{"key": name, "location": "-", "names": [name], "count": 0}
             for name in unknown]
    if not rows:
        tk.Label(listing, text="   nothing driven on this body yet", bg=BG, fg=DIM,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(8, 0))
        return None

    picked = next((row for row in rows if row["key"] == _state["map"]), rows[0])
    for row in rows:
        _mapped_row(listing, row, row["key"] == picked["key"])
    return picked


def _map_columns(location, maps, marks):
    """The one place the map table's column widths live."""
    return f"{location:<{LOCATION_W}} {maps[:MAPS_W]:<{MAPS_W}} {marks:<{MARKS_W}}"


def _mapped_row(parent, row, lit):
    """loc 7   map 2, map 5   2 bookmarks - the row, not the picture."""
    bg = PANEL if lit else BG
    frame = tk.Frame(parent, bg=bg)
    frame.pack(fill="x", padx=(0, 16), pady=1)
    tk.Frame(frame, bg=ACCENT if lit else bg, width=4).pack(side="left", fill="y")
    count = row["count"]
    marks = f"{count} bookmark{'' if count == 1 else 's'}" if count else "no bookmarks"
    tk.Label(frame, text="   " + _map_columns(row["location"], ", ".join(row["names"]),
                                              marks),
             bg=bg, fg=FG_SOFT, anchor="w", font=("Consolas", 9)).pack(side="left")
    widgets.clickable(frame, lambda: _pick_map(row["key"]))


def _empty(parent, register, focus):
    """The empty middle pane: what to do in bold, then why."""
    if register.system and focus:
        action = f"No ground here carries {_short(focus)}"
        why = ("Set the material back to All to see what this system does have, "
               "or try the next one.")
    elif register.system:
        action = "Honk - then FSS the bodies if none show up"
        why = ("The honk asks Spansh for the bodies others have scanned. When "
               "Spansh does not know the system, the honk alone does not describe "
               "them - resolve them in the FSS, or fly in and let the auto-scan "
               "sweep the near ones.")
    else:
        action = "Waiting for the journal"
        why = ("Jump somewhere, or restart EDMC if it started while you were "
               "already docked.")
    box = tk.Frame(parent, bg=BG)
    box.pack(fill="both", expand=True, padx=16, pady=16)
    tk.Label(box, text=action, bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(6, 4))
    label = tk.Label(box, text=why, bg=BG, fg=DIM, justify="left", anchor="w",
                     font=("Segoe UI", 9))
    label.pack(fill="x")
    label.bind("<Configure>", widgets.wrap_to_width, add="+")


# ------------------------------------------------------------------- the card


def _card(parent, register, sheet, body, picked, maps):
    """The location map (bookmarks view), then the card of `picked`: bookmark, map row or empty."""
    if picked is not None and body is not None and _state["view"] == "bookmarks":
        _location_map(parent, sheet, body, picked, maps)
    box = tk.Frame(parent, bg=PANEL, highlightthickness=1,
                   highlightbackground=RULE, highlightcolor=RULE)
    box.pack(fill="x", padx=(0, 14), pady=(14, 0))

    if picked is None or body is None:
        _empty_card(box, body)
        return
    if _state["view"] == "mapped":
        _map_card(box, body, picked)
        return
    _bookmark_card(box, register, sheet, body, picked, maps)


def _empty_card(box, body):
    """'Nothing picked' and which case: no body, no map, no bookmark, all folded."""
    if body is None:
        hint = "No bodies in this system yet. The middle pane says what to do."
    elif _state["view"] == "mapped":
        hint = "No map of this body has been saved yet."
    elif not body["shown"]:
        hint = "No bookmarks on this body yet. Mark one in the SRV and it lands here."
    else:
        hint = "Every location is folded. Open one and its first deposit lands here."
    tk.Label(box, text="Nothing picked", bg=PANEL, fg=FG_SOFT, anchor="w",
             font=("Segoe UI", 11, "bold")).pack(fill="x", padx=13, pady=(13, 4))
    label = tk.Label(box, text=hint, bg=PANEL, fg=DIM, anchor="w", justify="left",
                     font=("Segoe UI", 9))
    label.pack(fill="x", padx=13, pady=(0, 13))
    label.bind("<Configure>", widgets.wrap_to_width, add="+")


def _bookmark_card(box, register, sheet, body, record, maps):
    """The card of `record`: coordinates, deposit, tons, ground rates, dates, buttons."""
    index = record.get("location_index")
    dead = cards.depleted(record)
    rigs = record.get("rigs")

    head = tk.Frame(box, bg=PANEL)
    head.pack(fill="x", padx=13, pady=(13, 0))
    tk.Label(head, text=_loc(index) + "  ·  ", bg=PANEL, fg=FG, anchor="w",
             font=("Segoe UI", 13, "bold")).pack(side="left")
    tk.Label(head, text=_short(record.get("commodity")), bg=PANEL, fg=ACCENT, anchor="w",
             font=("Segoe UI", 13, "bold")).pack(side="left")

    tk.Label(box, text=f"{register.system or ''} {body['short']}  ·  "
                       + (f"{rigs} rigs" if rigs is not None else "rigs unknown"),
             bg=PANEL, fg=DIM, anchor="w", justify="left",
             font=("Segoe UI", 8)).pack(fill="x", padx=13, pady=(3, 0))
    tk.Frame(box, bg=RULE, height=1).pack(fill="x", padx=13, pady=(10, 0))

    _field(box, "COORDINATES")
    tk.Label(box, text=_coords(record) or "none recorded", bg=PANEL, fg=GOOD, anchor="w",
             font=("Consolas", 11)).pack(fill="x", padx=13)
    heading = record.get("heading")
    tk.Label(box, text="  ·  ".join(part for part in (
                 f"heading {heading}°" if heading is not None else "",
                 _away_text(record)) if part),
             bg=PANEL, fg=DIM, anchor="w", font=("Consolas", 8)).pack(fill="x", padx=13)

    _field(box, "DEPOSIT")
    amount, density = record.get("amount"), record.get("density")
    read = "  ·  ".join(part for part in (f"{amount} amount" if amount else "",
                                          f"{density} density" if density else "") if part)
    tk.Label(box, text=read or "no HUD readings", bg=PANEL, fg=FG, anchor="w",
             font=("Consolas", 9)).pack(fill="x", padx=13)
    left = deposit.describe(rigs, amount, density)
    left_label = tk.Label(box, text=_spent(record, "worked out") if dead
                          else (left or "tons left unknown"),
                          bg=PANEL, fg=ALERT if dead else WARN, anchor="w",
                          font=("Consolas", 9))
    left_label.pack(fill="x", padx=13, pady=(2, 0))
    if dead:
        _spent_labels.append((_key(record), left_label, "worked out"))
    # Counted from MiningRefined within yields.ATTRIBUTE_M.
    collected = yields.describe(record)
    label = None
    if collected:
        label = tk.Label(box, text=collected, bg=PANEL, fg=GOOD, anchor="w",
                         font=("Consolas", 9))
        label.pack(fill="x", padx=13, pady=(2, 0))
    _card_tons.update(key=_key(record), label=label)
    for line in _ground_lines(sheet, body, record.get("commodity")):
        tk.Label(box, text=line, bg=PANEL, fg=DIM, anchor="w",
                 font=("Consolas", 8)).pack(fill="x", padx=13, pady=(2, 0))

    _field(box, "MARKED")
    # To the minute, and the depleted date without its time: the two full
    # stamps together ran off the right edge of a 310px card.
    marked = str(record.get("marked_at") or "").replace("T", " ")[:16]
    depleted = str(record.get("depleted_at") or "")[:10]
    tk.Label(box, text=(marked or "unknown")
                       + (f"  ·  depleted {depleted}" if depleted else "  ·  active"),
             bg=PANEL, fg=FG_SOFT, anchor="w",
             font=("Consolas", 8)).pack(fill="x", padx=13)
    # yields.regrow() takes the mark off at REGEN_DAYS, or RECHECK_DAYS after a
    # recheck, on start and each jump.
    days = yields.days_since_depleted(record)
    check = yields.last_check(record)
    if check:
        at = yields.days_since_depleted(record, check)
        left = max(0.0, yields.RECHECK_DAYS - (days - at))
        tk.Label(box, text=f"still depleted at {at:.0f} d, look again in {left:.0f} d",
                 bg=PANEL, fg=DIM, anchor="w",
                 font=("Consolas", 8)).pack(fill="x", padx=13)
    elif days is not None:
        tk.Label(box, text=f"{days:.0f} d since, back after {yields.REGEN_DAYS} d (assumed)",
                 bg=PANEL, fg=DIM, anchor="w",
                 font=("Consolas", 8)).pack(fill="x", padx=13)

    _card_buttons(box, record, dead)


def _card_buttons(box, record, dead):
    """Guide me there, then a 2 x 2 grid; Delete last, ALERT under the pointer."""
    buttons = tk.Frame(box, bg=PANEL)
    buttons.pack(fill="x", padx=13, pady=(12, 13))

    running = overlay.guiding(record)
    # No coordinates (bookmarks older than the sidecar): no Guide, Share or Copy.
    has_fix = record.get("latitude") is not None and record.get("longitude") is not None
    arrow = widgets.button(buttons, "Stop the arrow" if running else "Guide me there",
                    (lambda: _toggle_guide(record)) if has_fix else None)
    arrow.config(fg=GOOD if running else ACCENT, font=("Segoe UI", 9))
    arrow.pack(fill="x")

    # 2 x 2 grid, uniform columns: pack with expand sized each button by its text.
    grid = tk.Frame(buttons, bg=PANEL)
    grid.pack(fill="x", pady=(6, 0))
    grid.columnconfigure((0, 1), weight=1, uniform="card")
    depleted = widgets.button(grid, "Set active" if dead else "Mark depleted",
                       lambda: _toggle_depleted(record))
    depleted.config(fg=WARN)
    for index, button in enumerate((
            widgets.button(grid, "Share bookmark",
                    (lambda: _share_bookmark(record)) if share.shareable(record) else None),
            depleted,
            widgets.button(grid, "Copy coords", (lambda: _copy_coords(record)) if has_fix else None),
            widgets.button(grid, "Delete", lambda: _delete_bookmark(record), active=ALERT))):
        row, column = divmod(index, 2)
        # 3 px either side of the gap: padding on one column only made it 6 px narrower.
        button.grid(row=row, column=column, sticky="ew",
                    padx=(3, 0) if column else (0, 3), pady=(6 if row else 0, 0))


def _map_card(box, body, row):
    """The map row the middle pane has picked: what is on it, and the picture."""
    tk.Label(box, text=row["location"] if row["location"] != "-" else "off any location",
             bg=PANEL, fg=FG, anchor="w",
             font=("Segoe UI", 13, "bold")).pack(fill="x", padx=13, pady=(13, 0))
    tk.Label(box, text=f"{body['short']}  ·  {', '.join(row['names'])}",
             bg=PANEL, fg=DIM, anchor="w", justify="left",
             font=("Segoe UI", 8)).pack(fill="x", padx=13, pady=(3, 0))
    tk.Frame(box, bg=RULE, height=1).pack(fill="x", padx=13, pady=(10, 0))

    _field(box, "ON THIS MAP")
    count = row["count"]
    tk.Label(box, text=f"{count} bookmark{'' if count == 1 else 's'}" if count
                       else "no bookmarks", bg=PANEL, fg=FG, anchor="w",
             font=("Consolas", 9)).pack(fill="x", padx=13)
    note = tk.Label(box, text="A location counts as mapped when it was targeted while "
                              "the map was driven, or when one of its bookmarks lies "
                              "on it.",
                    bg=PANEL, fg=DIM, anchor="w", justify="left", font=("Segoe UI", 8))
    note.pack(fill="x", padx=13, pady=(6, 0))
    note.bind("<Configure>", widgets.wrap_to_width, add="+")

    picture = _newest_picture(body["name"], row["names"])
    button = widgets.button(box, "Open the picture",
                     (lambda: _open_card(picture)) if picture else None)
    button.config(font=("Segoe UI", 9))
    button.pack(fill="x", padx=13, pady=(12, 13))


# (key, PhotoImage) of the last card map: a render is 70-160 ms, and Tk drops an unreferenced image.
_map_picture = None


def _location_map(parent, sheet, body, record, maps):
    """Above the card: the saved map nearest the bookmark (coverage.map_at), no title or legend.

    Nothing at all when no saved map reaches it.
    """
    global _map_picture
    lat, lon = record.get("latitude"), record.get("longitude")
    if not maps or lat is None or lon is None:
        return
    try:
        name = coverage.map_at(maps, body["name"], float(lat), float(lon))
    except (TypeError, ValueError):
        return
    if not name:
        return
    px = _grown(MAP_PX)
    data = dict(maps)[name]
    key = (body["name"], name, _marks_key(body), coverage.golden_m, px)
    if _map_picture is None or _map_picture[0] != key:
        photo = _draw_location_map(parent, sheet, body, name, data, px)
        if photo is None:
            return
        _map_picture = (key, photo)
    canvas = tk.Canvas(parent, width=px, height=px, bg=BG,
                       borderwidth=0, highlightthickness=0)
    canvas.create_image(0, 0, image=_map_picture[1], anchor="nw")
    canvas.image = _map_picture[1]
    # The picked bookmark: a diamond on the canvas, not in the picture, so a
    # pick costs no re-render. Metres -> px as coverage.picture over 2 * REACH_M.
    try:
        centre = data.get("center") or data["origin"]
        probe = coverage.Coverage(body["name"], float(centre[0]), float(centre[1]),
                                  float(data["radius"]))
        mx, my = probe.xy(float(lat), float(lon))
    except (KeyError, IndexError, TypeError, ValueError):
        mx = my = None
    if mx is not None:
        per_m = px / (2 * coverage.REACH_M)
        x, y, r = px / 2 + mx * per_m, px / 2 - my * per_m, DIAMOND_PX
        if 0 <= x <= px and 0 <= y <= px:
            canvas.create_polygon(x, y - r, x + r, y, x, y + r, x - r, y,
                                  fill=ACCENT, outline=BG, width=2, tags="picked")
    canvas.pack(padx=(0, 14), pady=(14, 0))


def _marks_key(body):
    """The bookmark fields the card map draws: its cache key.

    Not database.revision(): the tally writes the rows every yields.FLUSH_S while mining.
    """
    return tuple((mark.get("latitude"), mark.get("longitude"),
                  mark.get("commodity"), cards.depleted(mark),
                  mark.get("rigs")) for mark in body["marks"])


def _draw_location_map(parent, sheet, body, name, data, px=MAP_PX):
    """Map `name` repainted with the body's bookmarks it reaches, as a PhotoImage.

    None on a failure, logged.
    """
    try:
        cover = coverage.Coverage.from_dict(body["name"], data, name)
        if cover is None:
            return None
        marks, golden = _map_marks(cover, body["marks"], sheet)
        image = coverage.picture(cover.mask, marks, (), (), cover.border_m, golden)
        out = io.BytesIO()
        image.resize((px, px), Image.LANCZOS).save(out, format="PNG")
        return tk.PhotoImage(master=parent, data=out.getvalue())
    except Exception:       # PIL and coverage: any raise must not cost the card
        logger.exception(f"scan: could not draw {name} on {body['name']}")
        return None


def _field(parent, name):
    tk.Label(parent, text=name, bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(fill="x", padx=13, pady=(10, 2))


def _ground_lines(sheet, body, material):
    """Two lines: % of the ground's locations with `material`, and its median Cr/t; [] without a sheet."""
    if not material or not sheet.loaded or not body.get("ground"):
        return []
    rate = sheet.rate(body["ground"], material)
    if rate is None:
        return [f"{_short(material)} never read on this ground"]
    median = None
    for row in sheet.materials(body["ground"]):
        if row["material"].lower() == material.lower():
            median = row.get("median")
            break
    return [f"{_short(material)} in {_pct(rate)}% of the planet's locations",
            f"median {median:,} Cr per tonne" if median else "no price known"]


def _rates(parent, sheet, body, focus, materials=()):
    """The ground's best TOP_MATERIALS by % of locations, with prices; GOOD: bookmarked on this body.

    `materials` (the picker's) filter before the limit. `focus` leads whatever its rate.
    """
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(8, 0))
    if not sheet.loaded:
        tk.Label(row, text="no mining_sheet.json - body types only", bg=BG, fg=WARN,
                 anchor="w", font=("Segoe UI", 9)).pack(side="left")
        return
    measured = sheet.best(body["ground"], minimum=MIN_PCT)
    rows = measured
    if materials:
        offered = {name.lower() for name in materials}
        rows = [row for row in rows if row["material"].lower() in offered]
    rows = rows[:TOP_MATERIALS]
    if focus and not any(entry["material"].lower() == focus.lower() for entry in rows):
        rate = sheet.rate(body["ground"], focus)
        if rate is not None:
            rows = [{"material": focus, "pct": rate}] + rows[:TOP_MATERIALS - 1]
    if not rows:
        # No rows: never measured, or every row under the low value line (Settings).
        tk.Label(row, text="every material here is under the low value line - "
                           "Settings offers them" if measured
                      else "nothing measured on this ground yet",
                 bg=BG, fg=WARN, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        return
    confirmed = {(record.get("commodity") or "").lower() for record in body["marks"]}
    for index, entry in enumerate(rows):
        if index:
            tk.Label(row, text="   ·   ", bg=BG, fg=DIM,
                     font=("Consolas", 9)).pack(side="left")
        tk.Label(row, text=f"{_short(entry['material'])} {_pct(entry['pct'])}% "
                           f"{_price(entry.get('median'))}",
                 bg=BG, fg=GOOD if entry["material"].lower() in confirmed else FG_SOFT,
                 anchor="w", font=("Consolas", 9, "bold")).pack(side="left")


# ---------------------------------------------------------------- the actions


def _pick_body(name):
    _state["body"] = name
    _state["selected"] = None
    _state["map"] = None
    _state["view"] = "bookmarks"
    _state["status"] = ""
    _scroll["list"] = 0.0
    _draw()


def _pick_view(view):
    _state["view"] = view
    _state["status"] = ""
    _scroll["list"] = 0.0
    _draw()


def _pick_record(record):
    """The card on this bookmark: two rows relit and the card pane rebuilt, not
    the window (a _draw rebuilds every widget and flickers). _draw when the row
    or the card pane is not there."""
    key, old = _key(record), _state["selected"]
    card = _panes.get("card")
    if key not in _rows or card is None or not card.winfo_exists():
        _state["selected"] = key
        _state["status"] = ""
        _draw()
        return
    _state["selected"] = key
    _say("")
    if old in _rows and old != key:
        _light(_rows[old], False)
    _light(_rows[key], True)
    for child in card.winfo_children():
        child.destroy()
    _card(card, _panes["register"], _panes["sheet"], _panes["body"], record, _panes["maps"])


def _light(row, lit):
    """A list row's background and left strip as _bookmark_row draws them."""
    bg = PANEL if lit else BG
    row.config(bg=bg)
    for child in row.winfo_children():
        if isinstance(child, tk.Frame) and int(child.cget("width")) == 4:
            child.config(bg=ACCENT if lit else bg)
        elif isinstance(child, tk.Label):
            child.config(bg=bg)


def _pick_map(key):
    _state["map"] = key
    _state["status"] = ""
    _draw()


def _unfolded(body, index):
    return (body, index) in _state["opened"]


def _fold(body, index):
    _state["opened"] ^= {(body, index)}
    _draw()


def _fold_all(body, groups, fold):
    for index, _group in groups:
        if fold:
            _state["opened"].discard((body, index))
        else:
            _state["opened"].add((body, index))
    _draw()


def _toggle_depleted(record):
    """Mark depleted or Set active; the result on the status line, a failed write also in a dialog."""
    depleted = not cards.depleted(record)
    checks = len(record.get("rechecks") or [])
    if cards.set_depleted(record, depleted):
        still = len(record.get("rechecks") or []) > checks
        _state["status"] = (f"{_loc(record.get('location_index'))}, "
                            f"{_short(record.get('commodity'))}, "
                            + (f"still depleted, look again in {yields.RECHECK_DAYS} d." if still
                               else "marked depleted." if depleted else "is active again."))
    else:
        messagebox.showwarning(
            "Depleted", "The bookmark could not be written - see the EDMC log.",
            parent=_window)
        _state["status"] = "The bookmark could not be written - see the EDMC log."
    _draw()


def _toggle_guide(record):
    """Start or stop the arrow, then _draw: another card's Stop turns back into Guide."""
    if overlay.guiding(record):
        overlay.stop()
        _state["status"] = "The arrow is down."
    elif overlay.start(_window, record, on_stop=refresh) is None:
        # No arrow to be had here - it said why in the log.
        logger.info("scan: no overlay, the card is unchanged")
        _state["status"] = "No arrow: the game is not on this body."
    else:
        _state["status"] = (f"Arrow on {_loc(record.get('location_index'))} - top "
                            "middle of the game window, borderless or windowed.")
    _draw()


def _stop_guide():
    """The arrow down from the heading, whatever the card is showing."""
    overlay.stop()
    _state["status"] = "The arrow is down."
    _draw()


# The Edit dialog: what an unset Amount or Density reads, how wide the value
# column is, and how far the body name wraps.
NOT_SET = "-"
EDIT_FIELD_PX = 170
EDIT_WIDTH_PX = 300


def _pickable(record):
    """Materials the Edit dialog offers: what the picker offers, plus this
    bookmark's own material when the low value filter hides it."""
    offered = [name for name in (_scan[4] if _scan else ()) if name in spotmark.MATERIALS]
    current = record.get("commodity")
    if current and current not in offered:
        offered.insert(0, current)
    return offered or list(spotmark.MATERIALS)


def _edit_bookmark(record):
    """Modal Edit dialog: material, rigs, amount, density, location; coordinates, heading, marked_at stay."""
    if _window is None:
        return
    box = tk.Toplevel(_window, bg=BG)
    box.title("Edit bookmark")
    box.transient(_window)
    box.resizable(False, False)
    box.columnconfigure(1, weight=1, minsize=EDIT_FIELD_PX)

    tk.Label(box, text=f"{_loc(record.get('location_index'))} on "
                       f"{record.get('planet_name') or 'no body'}",
             bg=BG, fg=FG, anchor="w", justify="left", wraplength=EDIT_WIDTH_PX,
             font=("Segoe UI", 11, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 0))
    tk.Label(box, text=_coords(record) or "no coordinates", bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 8)).grid(row=1, column=0, columnspan=2, sticky="w",
                                        padx=14, pady=(2, 8))

    material = tk.StringVar(value=record.get("commodity") or "")
    rigs = tk.StringVar(value="" if record.get("rigs") is None else str(record["rigs"]))
    amount = tk.StringVar(value=record.get("amount") or NOT_SET)
    density = tk.StringVar(value=record.get("density") or NOT_SET)
    location = tk.StringVar(value="" if record.get("location_index") is None
                            else str(record["location_index"]))

    def field(row, text, widget):
        tk.Label(box, text=text, bg=BG, fg=FG_SOFT, anchor="w",
                 font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", padx=(14, 8), pady=3)
        widgets.style_field(widget)
        widget.grid(row=row, column=1, sticky="we", padx=(0, 14), pady=3)

    picker = tk.OptionMenu(box, material, *_pickable(record))
    widgets.letter_jump(picker)
    field(2, "Material", picker)
    field(3, "Rigs", tk.Spinbox(box, from_=0, to=deposit.MAX_RIGS, textvariable=rigs))
    field(4, "Amount", tk.OptionMenu(box, amount, NOT_SET, *deposit.AMOUNTS))
    field(5, "Density", tk.OptionMenu(box, density, NOT_SET, *deposit.DENSITIES))
    field(6, "Location", tk.Spinbox(box, from_=spotmark.NO_LOCATION, to=spotmark.MAX_LOCATION,
                                    textvariable=location))
    # tk.Spinbox writes from_ into an empty variable: a bookmark with no
    # location would save as loc 0.
    location.set("" if record.get("location_index") is None else str(record["location_index"]))

    buttons = tk.Frame(box, bg=BG)
    buttons.grid(row=7, column=0, columnspan=2, sticky="e", padx=14, pady=(10, 14))
    widgets.button(buttons, "Cancel", box.destroy).pack(side="right")
    widgets.button(buttons, "Save",
            lambda: _save_edit(box, record, material.get(), rigs.get(),
                               amount.get(), density.get(), location.get())
            ).pack(side="right", padx=(0, 6))

    widgets.centre_over(box, _window)
    box.grab_set()
    box.wait_window()


def _save_edit(box, record, material, rigs, amount, density, location):
    """Write the dialog back, then _draw. An unparsable Rigs or Location keeps the old value."""
    fields = {
        "commodity": material or record.get("commodity"),
        "rigs": _int_or(rigs, record.get("rigs")),
        "amount": None if amount == NOT_SET else amount,
        "density": None if density == NOT_SET else density,
        "location_index": _int_or(location, record.get("location_index")),
    }
    try:
        spotcard.save(cards.edited(record, fields), id=record["id"])
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.exception("scan: could not save the edit")
        messagebox.showwarning("Edit bookmark", f"Not saved: {err}", parent=box)
        return
    box.destroy()
    _state["selected"] = _key(dict(record, **fields))
    _state["status"] = f"{_loc(fields['location_index'])}, {fields['commodity']}, edited."
    _draw()


def _int_or(text, fallback):
    """'4' -> 4, '' -> None, anything else -> `fallback`."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return fallback


def _delete_bookmark(record):
    """Ask, then delete the bookmark row; its arrow is stopped first."""
    what = _loc(record.get("location_index"))
    material = record.get("commodity") or "no material"
    if not messagebox.askyesno(
            "Delete bookmark",
            f"Delete {what}, {material}, on {record.get('planet_name')}?"
            + os.linesep * 2
            + "The bookmark goes from disk.",
            default="no", parent=_window):
        return
    if overlay.guiding(record):
        overlay.stop()
    if not cards.delete(record):
        messagebox.showwarning(
            "Delete bookmark",
            "Nothing was deleted. The file is open somewhere, or the folder "
            "is read-only - see the EDMC log.", parent=_window)
    _state["selected"] = None
    _state["status"] = f"{what}, {material}, deleted."
    _draw()


def _copy_coords(record):
    """The coordinates onto the clipboard, for a message to somebody else."""
    text = _coords(record)
    if not text or _window is None:
        return
    clipboard.copy(_window, text)
    _say(f"Copied {text}")


def _share_bookmark(record):
    """The bookmark as a RhinoData code on the clipboard.

    Remembered (share.remember), so pasting it into the import box here adds no copy.
    """
    if _window is None:
        return
    code = share.encode(record)
    share.remember(code)
    clipboard.copy(_window, code)
    _say(f"Copied a RhinoData code for {_short(record.get('commodity'))} - "
         f"paste it into the import box under the bookmarks of another RhinoData")


def _share_map(body, group):
    """Redraw the map picture these bookmarks lie on, save and open it; the saved PNG if the redraw fails."""
    maps = coverstore.maps(body, system_address=_system_address())
    picture = _drawn_now(body, group, maps) or _picture(body, group, maps)
    if picture:
        _open_card(picture)
        return
    _state["status"] = "No saved map holds this location yet."
    _draw()


def _drawn_now(body, group, maps):
    """The map under these bookmarks drawn from its points and saved: its path, or None."""
    data = next((data for record in group
                 for data in [_map_data(body, record, maps)] if data), None)
    if data is None:
        return None
    name, stored = data
    try:
        cover = coverage.Coverage.from_dict(body, stored, name)
        if cover is None:
            return None
        system = _scan[0].system if _scan and _scan[0] else None
        sheet = _scan[1] if _scan else None
        records = [r for r in (cards.for_system(system) if system else ())
                   if r.get("planet_name") == body]
        marks, golden = _map_marks(cover, records, sheet)
        title, legend = minimap.picture_text(cover, system)
        ground = _scan[0].ground(system, body) if _scan and _scan[0] else None
        image = coverage.picture(cover.mask, marks, title, legend, cover.border_m, golden,
                                 ground)
    except Exception:       # PIL and coverage: any raise must not cost Share map
        logger.exception(f"scan: could not draw {name} on {body}")
        return None
    saved = coverstore.save_png(body, name, image)
    logger.info(f"scan: drew {name} on {body} on the press - "
                f"{'saved' if saved else 'not saved'}")
    return saved


def _map_data(body, record, maps):
    """(name, stored map) the bookmark lies on, or None."""
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        name = coverage.map_at(maps, body, float(lat), float(lon))
    except (TypeError, ValueError):
        return None
    return (name, dict(maps)[name]) if name else None


def _map_marks(cover, records, sheet):
    """(marks, golden groups) of the `records` that `cover` reaches, as coverage.picture takes them.

    marks: (x m east, y m north, code, depleted, Cr/t, rigs). Only those it reaches:
    golden_groups' 4-rig fallback depends on every spot it is given.
    """
    codes = sheet.codes() if sheet is not None else {}
    values = sheet.values() if sheet is not None else {}
    marks = []
    for record in records:
        lat, lon = record.get("latitude"), record.get("longitude")
        if (not isinstance(lat, (int, float)) or not isinstance(lon, (int, float))
                or not cover.reaches(lat, lon)):
            continue
        material = (record.get("commodity") or "").lower()
        marks.append((*cover.xy(lat, lon), codes.get(material),
                      cards.depleted(record), values.get(material, 0),
                      record.get("rigs")))
    spots = [(x, y, rigs, value or 0) for x, y, _, spent, value, rigs in marks if not spent]
    golden = coverage.golden_best(coverage.golden_groups(spots), spots)
    return marks, golden


def refresh_rail():
    """The rail rebuilt with the register's bodies, the rest left standing (a
    _draw rebuilds every widget and flickers): for a Spansh answer. _draw when
    the picked body is not the one the middle pane shows, or none was."""
    if _window is None or not _window.winfo_exists() or _scan is None:
        return
    rail, shown = _panes.get("rail"), _panes.get("body")
    live, sheet, focus, variable, materials = _scan
    register = _shown_register(live)
    listed = _bodies(register, sheet, focus)
    body = _current(listed)
    if (rail is None or not rail.winfo_exists() or shown is None or body is None
            or body["name"] != shown["name"]):
        _draw()
        return
    _remember_scroll()
    for child in rail.winfo_children():
        child.destroy()
    _rail(rail, register, sheet, focus, variable, materials, listed, body, live)


def refresh_mined():
    """Mined, card tons and spent labels set in place from one cards.for_system read.

    _draw when a label is missing, e.g. a card whose first ton just came.
    """
    if _window is None or not _window.winfo_exists() or not _scan:
        return
    system = _shown_register(_scan[0]).system
    found = {_key(r): r for r in (cards.for_system(system) if system else ())}
    if any(key not in found for key in _mined):
        _draw()
        return
    for key, label in _mined.items():
        mined = yields.short(found[key])
        label.config(text=f"{mined or '-':>{MINED_W}} ", fg=GOOD if mined else DIM)
    if _card_tons:
        key, label = _card_tons["key"], _card_tons["label"]
        collected = yields.describe(found[key]) if key in found else ""
        if label is None and collected:
            _draw()
        elif label is not None:
            label.config(text=collected)
    for key, label, word in _spent_labels:
        if key in found and label.winfo_exists():
            label.config(text=f"{_spent(found[key], word):>{LEFT_W}}" if word == "depleted"
                         else _spent(found[key], word))


def refresh():
    """_draw if the window exists, without raising it; clears a stale 'Arrow on' status line.

    Called by main after a save, and by the overlay when it takes itself down.
    """
    if _window is None or not _window.winfo_exists():
        return
    if not overlay.guiding() and _state["status"].startswith("Arrow on "):
        _state["status"] = ""
    _draw()


# ---------------------------------------------------------------- the reading


def _system_address():
    """The SystemAddress of the register's system, or None - what keeps a body's
    maps apart from those of a body with the same name elsewhere."""
    if not _scan:
        return None
    return _shown_register(_scan[0]).system_address


def _by_location(records):
    """[(location, [bookmark, ...]), ...], by location, unnumbered last."""
    groups = {}
    for record in records:
        groups.setdefault(record.get("location_index"), []).append(record)
    return sorted(((index, _clustered(group)) for index, group in groups.items()),
                  key=lambda item: (item[0] is None, item[0] or 0))


def _clustered(group):
    """One location's bookmarks in coverage.clusters() order, depleted last.

    No coordinates or planet_radius: after the placed ones, most rigs first.
    """
    def rigs(record):
        return int(record.get("rigs") or 0)

    live = [r for r in group if not cards.depleted(r)]
    gone = [r for r in group if cards.depleted(r)]
    radius = next((r["planet_radius"] for r in group if r.get("planet_radius")), None)
    placed = [r for r in live if radius and r.get("latitude") is not None
              and r.get("longitude") is not None]
    loose = sorted((r for r in live if r not in placed), key=lambda r: -rigs(r))
    if not placed:
        return loose + gone
    xy = measure.to_metres([(r["latitude"], r["longitude"]) for r in placed], radius)
    points = [(x, y, rigs(r)) for (x, y), r in zip(xy, placed)]
    ordered = [placed[i] for members in coverage.clusters(points) for i in members]
    return ordered + loose + gone


def _picture(body, group, maps):
    """The saved PNG of the map the first placed bookmark of `group` lies on, or None."""
    for record in group:
        found = _map_data(body, record, maps)
        picture = _newest_picture(body, [found[0]]) if found else None
        if picture:
            return picture
    return None


def _newest_picture(body, names):
    """The newest saved PNG of these maps, or None."""
    paths = [os.path.join(coverstore.folder(body), f"{name}.png") for name in names]
    paths = [path for path in paths if os.path.isfile(path)]
    return max(paths, key=os.path.getmtime) if paths else None


def _nearest(group, status):
    """Distance to the location's nearest bookmark, or '-'."""
    best = None
    for record in group:
        metres = guide.fix(status, record).get("distance_m")
        if metres is not None and (best is None or metres < best):
            best = metres
    return guide.metres(best) if best is not None else "-"


def _away_text(record):
    """'821 m away', or what is in the way of knowing - another body, orbit,
    supercruise."""
    reading = guide.fix(spotmark.read_status(), record)
    if reading.get("distance_m") is not None:
        return f"{guide.metres(reading['distance_m'])} away"
    return {"wrong body": "another body",
            "no body": "supercruise or docked",
            "no position": "too high up for a fix"}.get(reading.get("state"), "no fix")


def _coords(record):
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is None or lon is None:
        return ""
    return f"{float(lat):.6f} / {float(lon):.6f}"


def _about(body):
    """Rocky World [silicate] · 1,284 Ls · 22 locations · major silicate vapour
    geysers."""
    distance = body.get("distance")
    locations = body.get("locations")
    parts = [grounds.label(body["ground"]),
             f"{distance:,.0f} Ls" if distance is not None else "",
             f"{locations} locations" if locations is not None else "unprobed",
             _volcanism(body)]
    return "  ·  ".join(part for part in parts if part)


def _price(credits):
    """208k, 1.2M, or 'no price' - the median a market pays per tonne."""
    if not credits:
        return "(no price)"
    if credits >= 1_000_000:
        return f"({credits / 1_000_000:.1f}M)"
    return f"({round(credits / 1000):,}k)"


def _volcanism(body):
    """What kind of volcanism and how much of it - "major metallic magma"."""
    words = " ".join((body.get("volcanism") or "").lower().split())
    # The journal's own suffix - "major rocky magma volcanism". The line already
    # says it once.
    if words.endswith(" volcanism"):
        words = words[:-len(" volcanism")]
    return words


def _open_card(path):
    """Open the PNG in the system viewer: os.startfile, webbrowser where that is missing."""
    try:
        os.startfile(path)                       # Windows, which is where EDMC runs
    except AttributeError:
        webbrowser.open(pathlib.Path(path).as_uri())
    except OSError as err:
        logger.warning(f"could not open {path}: {err}")


# ------------------------------------------------------------------ the parts


def _remember_scroll():
    """How far each list had been scrolled, before the draw throws it away."""
    for name, canvas in _canvases.items():
        try:
            if canvas.winfo_exists():
                _scroll[name] = canvas.yview()[0]
        except tk.TclError:                      # destroyed between the two calls
            pass
    _canvases.clear()


def _scrollable(parent, name, bg=BG, padx=(16, 0)):
    """A scrolling frame (canvas + inner frame), returned; `name` keys its scroll position across draws."""
    box = tk.Frame(parent, bg=bg)
    box.pack(side="top", fill="both", expand=True, padx=padx, pady=(4, 0))
    canvas = tk.Canvas(box, bg=bg, highlightthickness=0)
    bar = tk.Scrollbar(box, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)

    inner.bind("<Configure>",
               lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfig(window, width=event.width))
    canvas.configure(yscrollcommand=bar.set)

    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    _canvases[name] = canvas
    widgets.wheel(canvas)
    # After the layout: the scrollregion comes from the <Configure> about to fire.
    # On the root: destroying the canvas deletes the pending command, and tkinter
    # can reuse its "<id><lambda>" name for a bind lambda Tcl then calls bare.
    canvas._root().after_idle(lambda: _restore_scroll(canvas, name))
    return inner


def _restore_scroll(canvas, name):
    try:
        if canvas.winfo_exists():
            canvas.yview_moveto(_scroll.get(name, 0.0))
    except tk.TclError:
        pass
