"""The RhinoData window: what is worth landing on, here, right now.

Three panes on one screen, side by side, and nothing that navigates away:

    bodies of the system | the bookmarks of one body | the one that is picked

The rail on the left is every landable body, grouped by what kind of ground it
is, with how far away it is and how many bookmarks it carries. The middle is
the bookmarks of the body the rail has picked, folded into their mining
locations. The card on the right is the bookmark the middle has picked - its
coordinates, what the deposit read, what the ground pays for it - and every
button that acts on it.

The window is read-only apart from the card's buttons. Nothing is saved from
the list itself, so opening it twice costs nothing.
"""

import os
import pathlib
import io
import tkinter as tk
import webbrowser
from tkinter import messagebox

from PIL import Image

from rs_core import (bodies, cards, coverage, coverstore, database, deposit, grounds, guide,
                     palette, spotcard, spotmark, store)
from rs_core.logging import logger
from rs_ui import minimap, overlay, rhino

# Three. A fourth is the least likely material anyway, and a row of four pairs
# reads as a run of words rather than a list.
TOP_MATERIALS = 3
MIN_PCT = 2.0

# Wide enough for "15 d a" and every other body designation in a normal system.
NAME_WIDTH = 8

# The bookmark table, in characters: material, rigs, what is left of it.
MATERIAL_W = 22
RIGS_W = 6
LEFT_W = 20
# The map table: location, the maps on it, how many bookmarks lie on them.
LOCATION_W = 10
MAPS_W = 22
MARKS_W = 14
# What a location line says about itself before it starts taking room from the
# button and the distance packed on its right.
SUMMARY_W = 54
# The deposits of a location sit in from it, so the fold reads as a tree rather
# than as a list with headings in it.
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

# The window is a fixed share of the screen rather than a size measured off its
# own content. Three panes side by side have no natural width - the middle one
# is as wide as whatever is left - and a window that changed size every time a
# body was picked was the thing the old one did worst.
SCREEN_SHARE = 0.6
MIN_WIDTH = 900
MIN_HEIGHT = 520
RAIL_WIDTH = 280
CARD_WIDTH = 310
# The map over the bookmark card, in pixels. Square, and short enough that the
# card under it keeps its buttons on screen: at the card's full width the
# picture pushed Share map and Mark depleted off the bottom of the window.
MAP_PX = 240

# Material names that do not fit a 22-character column or a one-line sentence.
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
_scan = None             # (register, sheet, focus, variable, materials)
_canvases = {}           # the scrolling canvases of the draw on screen
_scroll = {}             # how far each of them had been scrolled, by name

# What the window is showing. Kept here rather than in the widgets: every draw
# throws the widgets away, and the body you were on has to survive that.
_state = {
    "body": None,         # the body the rail has picked
    "view": "bookmarks",  # "bookmarks" or "mapped"
    "selected": None,     # _key() of the bookmark the card is showing
    "map": None,          # the map row the card is showing, by its own key
    "collapsed": set(),   # (body, location index) of every folded location
    "status": "",
    "system": None,       # a system browsed from the search box, or None for the live one
    "search": "",         # what is typed in the search box
}

# The browsed system's register, kept between draws: adopt() re-reads the body
# cache, and a draw happens on every click in the window.
_browsed = None

# The search box: how many letters before it answers, and how many systems it
# names. Three of each - a list that opens on an empty box is in the way, and a
# fourth row pushes the body list down the rail.
SEARCH_MIN = 3
SEARCH_HITS = 3


def is_open():
    return _window is not None and bool(_window.winfo_exists())


def show(parent, register, sheet, focus=None, variable=None, materials=(), here=None):
    """Open the window, or raise the one already open.

    `focus` is one material. Given one, only the grounds that have ever carried
    it are listed and only its bookmarks are counted - the question has changed
    from "what is here" to "where is the jadeite".

    `here` is the body name when Status.json has us on or over one. Then the
    window opens with that body picked in the rail, and that body stays listed
    even when the material filter would drop its ground: the body under the
    ship is the one thing on screen that is not a choice.

    `variable` is the panel's filter StringVar, not a copy, so the picker in
    the rail and `focus` can never disagree. It is not the panel's Material
    box: that one names the next bookmark and is left alone.
    """
    global _window, _scan

    # First, so the draw below reads the material that was just picked.
    _scan = (register, sheet, focus, variable, materials)

    if _window is not None and _window.winfo_exists():
        logger.debug(f"scan: redraw, system={register.system!r} focus={focus!r}")
        # The material changed under us, so whatever the last press said is
        # about a list that is being rebuilt.
        _state["status"] = ""
        _draw()
        # lift() alone leaves a window behind another program, or minimised,
        # where it was: the same way up as a first open, topmost until left.
        if _window.state() == "iconic":
            _window.deiconify()
        _window.attributes("-topmost", True)
        _window.bind("<FocusIn>", _drop_topmost, add="+")
        _window.lift()
        _window.focus_force()
        return _window

    logger.debug(f"scan: open, system={register.system!r} focus={focus!r}")
    _window = tk.Toplevel(parent)
    _window.configure(bg=BG)
    # Debug only, and only on the window itself: whatever takes it away, this is
    # the line that names it. A window that vanishes with no Python frame behind
    # it is the one thing the stack cannot be asked about afterwards.
    _window.bind("<Destroy>", _log_destroy, add="+")
    # Over the game on the way up - the key that opens it is pressed with the
    # game in front, and a window behind it is not an answer. Given up the
    # moment something else is clicked.
    _window.attributes("-topmost", True)
    _window.bind("<FocusIn>", _drop_topmost, add="+")
    _window.bind("<Escape>", lambda event: _window.destroy())
    _window.focus_force()
    _size(_window)

    _state["view"] = "bookmarks"
    _state["selected"] = None
    _state["map"] = None
    _state["collapsed"] = set()
    _state["status"] = ""
    _scroll.clear()
    if here:
        _state["body"] = here
    _draw()
    return _window


def _size(window):
    """Six tenths of the screen, both ways.

    A share rather than a measurement: the panes are fixed-width on the outside
    and elastic in the middle, so there is nothing to measure, and a window that
    keeps its size while the content under it changes is the point of the
    layout.
    """
    width = max(MIN_WIDTH, int(window.winfo_screenwidth() * SCREEN_SHARE))
    height = max(MIN_HEIGHT, int(window.winfo_screenheight() * SCREEN_SHARE))
    logger.debug(f"scan: {width}x{height}, {SCREEN_SHARE:.0%} of the screen")
    window.geometry(f"{width}x{height}")
    window.minsize(MIN_WIDTH, MIN_HEIGHT)


def _drop_topmost(event):
    """Topmost is a crowbar for the first raise, and nothing after it.

    The window is opened by a key press with the game in front, and a plain
    lift() loses that race: a process that does not have the foreground cannot
    take it. Topmost wins it. The moment the window has the focus it has won,
    and every second it keeps the flag after that is a second it spends
    shadowing whatever is clicked next.

    Any widget inside it counts - after a draw the focus sits on a button, not
    on the window.
    """
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
        child.destroy()


# ---------------------------------------------------------------- the drawing


def _draw():
    """Build all three panes into the empty window.

    Everything, every time: a pick in the rail changes the middle and the card,
    a pick in the middle changes the card and the row that is lit, and folding a
    location changes which bookmark the card is showing. Redrawing only the
    piece that changed would mean knowing which pieces those are for each of a
    dozen actions, and the whole window is a few hundred labels.

    What a draw must not throw away is how far the lists had been scrolled: a
    click on a body fourteen rows down would otherwise take both lists back to
    the top, and the row that was just clicked with them.
    """
    if _window is None or not _window.winfo_exists() or _scan is None:
        return
    live, sheet, focus, variable, materials = _scan
    register = _shown_register(live)
    _remember_scroll()
    _clear(_window)

    listed = _bodies(register, sheet, focus)
    body = _current(listed)
    records = list(body["shown"]) if body else []
    groups = _by_location(records)
    # Once for the whole draw: every map of a body is a gzipped blob in the
    # database, and the middle pane, the location lines and the card all want
    # the same answer.
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

    card = tk.Frame(outer, bg=BG, width=CARD_WIDTH)
    card.pack(side="right", fill="y")
    card.pack_propagate(False)

    middle = tk.Frame(outer, bg=BG)
    middle.pack(side="left", fill="both", expand=True)
    picked = _middle(middle, register, sheet, focus, body, records, groups, maps, materials)

    _card(card, register, sheet, body, picked, maps)


def _bodies(register, sheet, focus):
    """Every listed body, in rail order.

    Each entry carries `marks`, every bookmark on it, and `shown`, the ones the
    material filter leaves. The rail counts `shown` - a rail that says "3 bm"
    beside a list that says "no bookmarks" is the filter lying about itself -
    and the rates line needs `marks` to say which materials have been stood on.
    """
    marked = cards.by_body(register.system) if register.system else {}
    prefix = (register.system or "") + " "
    listed = []
    for ground, found in register.by_ground():
        # The body under the ship stays listed whatever the filter says: it is
        # where the commander is, not one of the answers to a question.
        if focus and sheet.rate(ground, focus) is None \
                and not any(body["name"] == _state["body"] for body in found):
            continue
        for body in found:
            row = dict(body)
            name = body["name"]
            # The system name is in the rail heading and the window title, and
            # repeating it on every row pushes the counts off a 280px rail.
            row["short"] = name[len(prefix):] if name.startswith(prefix) else name
            row["ground"] = ground
            row["marks"] = marked.get(name) or []
            row["shown"] = [r for r in row["marks"]
                            if not focus
                            or (r.get("commodity") or "").lower() == focus.lower()]
            listed.append(row)
    return listed


def _current(listed):
    """The body the rail has picked, or the first one carrying a bookmark the
    filter leaves, or the first one at all.

    Falls through on purpose: the material picker can drop the picked body out
    of the list entirely, and a window showing nothing because of a body that is
    no longer listed is a window that looks broken.
    """
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
    """What identifies a bookmark across a draw.

    Not the dict: the rows are read off disk again after every delete and every
    depleted flip, so the object the card was given is not the object the list
    holds a moment later.
    """
    return (record.get("planet_name"), record.get("location_index"),
            record.get("commodity"), record.get("marked_at"))


def _short(material):
    """The names that do not fit a column: LTD and P. Dunite."""
    return SHORT_NAMES.get((material or "").lower(), material or "unknown")


def _pct(value):
    """40.0 -> '40', 61.9 -> '61.9'. A trailing zero claims a precision the
    sheet does not have."""
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
    # Click the system name. Nothing says so - that is the point of it.
    name.bind("<Button-1>", lambda event: rhino.run(name.winfo_toplevel()))

    # Only while a searched system is shown. Bookmark always marks where the
    # ship is, so this is the way back to the system that can be marked.
    if _state["system"] and live is not None and live.system:
        back = _button(head, f"\u25c0  Back to {live.system}", _back_to_live)
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
    ground = None
    for entry in listed:
        if entry["ground"] != ground:
            ground = entry["ground"]
            tk.Label(listing, text=grounds.label(ground), bg=PANEL, fg=ACCENT, anchor="w",
                     font=("Segoe UI", 9, "bold")).pack(fill="x", padx=13, pady=(8, 2))
        _rail_body(listing, entry, body is not None and entry["name"] == body["name"])
    if not listed:
        tk.Label(listing, text="nothing listed here yet", bg=PANEL, fg=DIM, anchor="w",
                 font=("Segoe UI", 9)).pack(fill="x", padx=13, pady=(8, 0))


def _shown_register(live):
    """The register the window draws: the live one, or a searched system filled
    from the body cache.

    Register.adopt() is the cache's own path in, so a browsed system lists and
    groups exactly as the live one does. Kept between draws - adopt() re-reads
    the cache and every click redraws.
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
    """[(system, bookmarks), ...], most recently marked first.

    Only systems that hold bookmarks: the search box is for finding a bookmark
    again, and a system with none is not an answer to that.
    """
    try:
        with database.connect() as conn:
            return conn.execute(
                "SELECT system, count(*) FROM bookmarks WHERE system IS NOT NULL "
                "GROUP BY system ORDER BY max(id) DESC").fetchall()
    except Exception as err:                       # sqlite3.Error, OSError
        logger.warning(f"scan: could not list the bookmarked systems: {err}")
        return []


def _search_box(parent):
    """Type a system, pick it, and the page shows that system's bookmarks.

    Only systems that hold bookmarks are listed - the box exists to find a
    bookmark again, and a system with none is not an answer to that.

    An entry rather than a picker: the list grows with every system marked in,
    and a dropdown of fifty is a scroll-hunt.

    Silent under SEARCH_MIN letters, and at most SEARCH_HITS matches.
    """
    typed = tk.StringVar(value=_state["search"])
    entry = tk.Entry(parent, textvariable=typed, bg=BG, fg=FG, insertbackground=FG,
                     relief="solid", borderwidth=1, highlightthickness=0,
                     font=("Segoe UI", 9))
    tk.Label(parent, text="SYSTEMS WITH BOOKMARKS", bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(fill="x", pady=(0, 2))
    entry.pack(fill="x")

    hits = tk.Frame(parent, bg=PANEL)
    hits.pack(fill="x")

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
            _clickable(row, lambda pick=system: _browse(pick))
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
    _state["system"] = system
    _state["body"] = None
    _state["selected"] = None
    _state["map"] = None
    _state["status"] = f"Showing {system}. Bookmark still marks where the ship is."
    _draw()


def _back_to_live():
    _state["system"] = None
    _state["search"] = ""
    _state["body"] = None
    _state["selected"] = None
    _state["map"] = None
    _state["status"] = ""
    _draw()


def _rail_footer(parent, sheet):
    """Where the percentages come from, or how to get them back.

    At the foot of the rail rather than under the list: it is about the sheet
    the whole window reads, not about the body that happens to be picked.
    """
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


def _rail_body(parent, entry, chosen):
    """One body in the rail: name, how far out, locations, bookmarks.

    The whole row is the button. A body with no bookmarks is still worth
    picking - the middle pane says what its ground pays - and the distance is
    here because "which of these is nearest" is a question about the list, not
    about the one body that is open.
    """
    row = tk.Frame(parent, bg=PANEL)
    row.pack(fill="x")
    # The picked body carries the accent down its left edge: a background alone
    # was not enough to find at a glance in a list of ten.
    tk.Frame(row, bg=ACCENT if chosen else PANEL, width=4).pack(side="left", fill="y")
    inner = tk.Frame(row, bg=PANEL)
    inner.pack(side="left", fill="x", expand=True, padx=(9, 13), pady=5)

    marks = len(entry["shown"])
    locations = entry.get("locations")
    distance = entry.get("distance")
    tk.Label(inner, text=entry["short"][:NAME_WIDTH], bg=PANEL,
             fg=FG if chosen else FG_SOFT, anchor="w", width=NAME_WIDTH,
             font=("Consolas", 10)).pack(side="left")
    tk.Label(inner, text=f"{distance:,.0f} Ls" if distance is not None else "-",
             bg=PANEL, fg=DIM, anchor="e", width=9,
             font=("Consolas", 9)).pack(side="left")
    tk.Label(inner, text=f"{marks} bm" if marks else "", bg=PANEL, fg=GOLD, anchor="e",
             font=("Consolas", 9)).pack(side="right")
    tk.Label(inner, text=f"{locations} loc" if locations is not None else "unprobed",
             bg=PANEL, fg=DIM, anchor="e", font=("Consolas", 9)).pack(side="right", padx=6)

    _clickable(row, lambda: _pick_body(entry["name"]))


def _picker(parent, variable, materials, focus):
    """The material picker, under the system name.

    Bound to the panel's own variable rather than a copy of its value, so
    choosing here is the same act as choosing down in the panel. Two pickers
    that can disagree are worse than one picker in the wrong place.

    Nothing is watched from here. A trace added on every open is a trace added
    three times by the third open, and then one pick draws the window three
    times.
    """
    box = tk.Frame(parent, bg=PANEL)
    box.pack(fill="x", padx=13, pady=(10, 0))
    tk.Label(box, text="MATERIAL FILTER", bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(fill="x")

    picker = tk.OptionMenu(box, variable, *materials)
    picker.config(relief="solid", borderwidth=1, highlightthickness=0,
                  bg=BG, fg=FG, activebackground=BG, activeforeground=ACCENT,
                  anchor="w", padx=6, pady=0, font=("Segoe UI", 9))
    picker["menu"].config(bg=PANEL, fg=FG, activebackground=ACCENT,
                          activeforeground=BG, borderwidth=1,
                          activeborderwidth=0, tearoff=False,
                          font=("Segoe UI", 9))
    picker.pack(fill="x", pady=(4, 0))
    tk.Label(box, text=f"Only {_short(focus)}, everywhere." if focus
                       else "The rail counts and the list follow it.",
             bg=PANEL, fg=DIM, anchor="w", justify="left", font=("Segoe UI", 8),
             wraplength=RAIL_WIDTH - 26).pack(fill="x", pady=(4, 0))


# ----------------------------------------------------------------- the middle


def _middle(parent, register, sheet, focus, body, records, groups, maps, materials=()):
    """The body's heading, its two tabs, and whatever the open tab holds.

    Returns what the card is to show - a bookmark, a map row, or None. It is the
    pane that knows what is folded, and the card is downstream of that.
    """
    if body is None:
        _empty(parent, register, focus)
        return None

    head = tk.Frame(parent, bg=BG)
    head.pack(fill="x", padx=16, pady=(14, 0))

    title = tk.Frame(head, bg=BG)
    title.pack(fill="x")
    tk.Label(title, text=body["short"], bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 16, "bold")).pack(side="left")
    # An arrow is up and its card may be two clicks away - a folded location, a
    # different body, the other tab. The way to take it down belongs where it
    # can always be reached.
    if overlay.guiding():
        stop = _button(title, "Stop the arrow", _stop_guide)
        stop.config(fg=GOOD)
        stop.pack(side="left", padx=(12, 0))

    # Every map of the body, not the ones the filter leaves: a map is driven
    # ground, and a material has nothing to say about which locations were on it.
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

    if _state["view"] == "mapped":
        picked = _mapped_list(parent, body, mapped, unknown)
    else:
        picked = _bookmark_list(parent, body, groups, maps)

    status = tk.Label(parent, text=_state["status"] or HINT, bg=BG, fg=DIM,
                      anchor="w", justify="left", font=("Segoe UI", 8))
    status.pack(side="bottom", fill="x", padx=16, pady=(6, 10))
    status.bind("<Configure>", _wrap_to_width, add="+")
    return picked


def _wrap_to_width(event):
    """Wrap a label at whatever width it has been given.

    A label with anchor="w" and fill="x" is as wide as its pane; wraplength
    knows nothing about that until it is told, and until then the sentence runs
    off the right edge of the window.
    """
    if event.width > 80:
        event.widget.config(wraplength=event.width - 8)


def _tab(parent, text, view, enabled):
    """Bookmarks and Mapped, packed from the right edge inwards.

    Tabs rather than a second page: the maps of a body and the bookmarks on it
    are two readings of the same ground, and stepping between them used to cost
    two clicks through the body list.
    """
    on = _state["view"] == view
    tk.Button(parent, text=text,
              command=(lambda: _pick_view(view)) if enabled else None,
              bg=PANEL if on else BG, fg=ACCENT if on else FG_SOFT,
              activebackground=PANEL, activeforeground=ACCENT, disabledforeground=DIM,
              relief="solid", borderwidth=1, highlightthickness=0,
              padx=10, pady=1, font=("Segoe UI", 8),
              cursor="hand2" if enabled else "arrow",
              state="normal" if enabled else "disabled").pack(side="right", padx=(6, 0))


def _bookmark_list(parent, body, groups, maps):
    """Every location of this body that carries a bookmark, folded.

    Returns the bookmark the card is to show: the one that was picked while its
    location is open, otherwise the first row of the first open location,
    otherwise nothing at all. A card left showing a bookmark whose location has
    just been folded away is a card about something you can no longer see.
    """
    header = tk.Frame(parent, bg=BG)
    header.pack(fill="x", padx=16, pady=(12, 0))
    # The 4px of the accent strip every row starts with, so the headings sit
    # over the columns they name rather than four pixels left of them.
    tk.Frame(header, bg=BG, width=4).pack(side="left", fill="y")
    tk.Label(header, text=INDENT + _columns("Material", "Rigs", "Est. left"), bg=BG,
             fg=DIM, anchor="w", font=("Consolas", 8)).pack(side="left")
    if groups:
        folded = all(not _unfolded(body["name"], index) for index, _group in groups)
        _button(header, "Open all" if folded else "Fold all",
                lambda: _fold_all(body["name"], groups, not folded)).pack(side="right")
    tk.Frame(parent, bg=RULE, height=1).pack(fill="x", padx=16, pady=(3, 0))

    listing = _scrollable(parent, "list")
    if not groups:
        tk.Label(listing, text="   no bookmarks on this body yet", bg=BG, fg=DIM,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(8, 0))
        return None

    # Once for the whole table rather than once a row, and a reading rather than
    # a subscription: the distances are what they were when the list was drawn.
    # The arrow is what follows you.
    status = spotmark.read_status()
    ordered = [(index, cards.ordered(group), _unfolded(body["name"], index))
               for index, group in groups]
    # Which row the card is showing has to be known before the first row is
    # drawn, because it is the one that is lit.
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
            _bookmark_row(listing, record, picked)
    return picked


def _location_header(parent, body, index, group, maps, status, open_here):
    """'loc 2', what is in it, and Share map for the picture it was driven on.

    The whole line folds it. The distance and the button are packed first, from
    the right edge inwards: pack hands out the width in the order it is asked
    for, and a location whose summary runs long was dropping both of them off
    the end of a narrow pane.
    """
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(8, 0))
    tk.Label(row, text="▼" if open_here else "▶", bg=BG, fg=ACCENT, width=3,
             font=("Segoe UI", 7)).pack(side="left")
    tk.Label(row, text=_loc(index), bg=BG, fg=FG, anchor="w", width=8,
             font=("Segoe UI", 10, "bold")).pack(side="left")

    # The picture is looked for when the button is pressed, not now: finding it
    # rebuilds a mask for every saved map of the body, and this line is drawn
    # for every location on every draw.
    _button(row, "Share map",
            (lambda: _share_map(body, group)) if maps else None).pack(
        side="right", padx=(8, 16))
    tk.Label(row, text=_nearest(group, status), bg=BG, fg=FG_SOFT, anchor="e",
             font=("Consolas", 9)).pack(side="right")

    names = ", ".join(_short(record.get("commodity")) for record in group)
    worked = sum(1 for record in group if record.get("depleted_at"))
    summary = (f"{len(group)} deposit{'' if len(group) == 1 else 's'}  ·  {names}"
               + (f"  ·  {worked} worked out" if worked else ""))
    tk.Label(row, text=summary[:SUMMARY_W], bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 8)).pack(side="left")

    _clickable(row, lambda: _fold(body, index), skip_buttons=True)
    tk.Frame(parent, bg=PANEL, height=1).pack(fill="x", padx=(0, 16), pady=(4, 0))


def _bookmark_row(parent, record, picked):
    """One deposit inside its location: material, rigs, what is left of it.

    One line. Where it is and when it was marked live on the card now, which is
    what let the row lose its second line.
    """
    lit = picked is not None and _key(record) == _key(picked)
    dead = _worked_out(record)
    bg = PANEL if lit else BG
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", padx=(0, 16), pady=1)
    tk.Frame(row, bg=ACCENT if lit else bg, width=4).pack(side="left", fill="y")

    rigs = record.get("rigs")
    left = deposit.describe(rigs, record.get("amount"), record.get("density"))
    if record.get("depleted_at"):
        left = "depleted"
    # Two labels rather than one line: the material is the accent colour and
    # what is left of the deposit is a verdict, and a label carries one colour.
    material = _short(record.get("commodity"))
    tk.Label(row, text=INDENT + f"{material[:MATERIAL_W]:<{MATERIAL_W}} "
                                f"{(str(rigs) if rigs is not None else '-'):>{RIGS_W}} ",
             bg=bg, fg=DIM if dead else ACCENT, anchor="w",
             font=("Consolas", 9)).pack(side="left")
    tk.Label(row, text=f"{left or '-':>{LEFT_W}}", bg=bg,
             fg=ALERT if dead else (WARN if left else DIM), anchor="e",
             font=("Consolas", 9)).pack(side="left")
    _button(row, "Edit", lambda: _edit_bookmark(record)).pack(side="right", padx=(6, 0))

    _clickable(row, lambda: _pick_record(record), skip_buttons=True)


def _worked_out(record):
    """Mined out, however it was said: marked Depleted here, or read Depleted
    off the HUD when the bookmark was made."""
    return bool(record.get("depleted_at")) or record.get("amount") == "Depleted"


def _columns(material, rigs, left):
    """The one place the bookmark table's column widths live, so the header
    cannot drift away from the rows it names."""
    return (f"{material[:MATERIAL_W]:<{MATERIAL_W}} {rigs:>{RIGS_W}} "
            f"{left:>{LEFT_W}}")


def _mapped_list(parent, body, mapped, unknown):
    """The locations of this body with a saved map, and the maps tied to none.

    Returns the map row the card is to show. Every row carries its own key - the
    untied ones are keyed by the map's name, because "-" is the same string for
    all of them, and three maps that cannot be told apart is three maps of which
    only the first can ever be opened.
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
    _clickable(frame, lambda: _pick_map(row["key"]))


def _empty(parent, register, focus):
    """What to do, then why - in that order.

    The empty window is where everybody meets this plugin for the first time,
    and the thing they have just done is honk. The instruction has to be the
    first line, not the conclusion of a paragraph about journal events.
    """
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
    label.bind("<Configure>", _wrap_to_width, add="+")


# ------------------------------------------------------------------- the card


def _card(parent, register, sheet, body, picked, maps):
    """The bookmark that is picked, and every button that acts on it.

    A card rather than buttons on the row: there are five things to do to a
    bookmark and four numbers worth reading about it, and neither fits beside a
    row that also has to line its columns up with the row under it.

    The ground the bookmark sits on goes above the card, packed first. Picking
    a bookmark in the middle asks "where is this" before it asks "what is it",
    and the answer was two clicks away on the other tab.
    """
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
    """Why there is nothing to show - a different sentence in each of the three
    cases, because the wrong one reads as a broken window."""
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
    label.bind("<Configure>", _wrap_to_width, add="+")


def _bookmark_card(box, register, sheet, body, record, maps):
    index = record.get("location_index")
    dead = _worked_out(record)
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
    tk.Label(box, text="worked out" if dead else (left or "tons left unknown"),
             bg=PANEL, fg=ALERT if dead else WARN, anchor="w",
             font=("Consolas", 9)).pack(fill="x", padx=13, pady=(2, 0))
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

    _card_buttons(box, record, bool(record.get("depleted_at")), maps)


def _card_buttons(box, record, dead, maps):
    """Guide across the top, then the pairs. Delete is last and red under the
    pointer: it is the one that destroys something."""
    buttons = tk.Frame(box, bg=PANEL)
    buttons.pack(fill="x", padx=13, pady=(12, 13))

    running = overlay.guiding(record)
    # Nothing to point at on a bookmark made before the coordinates went into
    # the sidecar, and nothing to share on a body nobody has driven.
    has_fix = record.get("latitude") is not None and record.get("longitude") is not None
    arrow = _button(buttons, "Stop the arrow" if running else "Guide me there",
                    (lambda: _toggle_guide(record)) if has_fix else None)
    arrow.config(fg=GOOD if running else ACCENT, font=("Segoe UI", 9))
    arrow.pack(fill="x")

    pair = tk.Frame(buttons, bg=PANEL)
    pair.pack(fill="x", pady=(6, 0))
    _button(pair, "Share map",
            (lambda: _share_map(record.get("planet_name"), [record]))
            if (maps and has_fix) else None).pack(side="left", fill="x", expand=True)
    depleted = _button(pair, "Set active" if dead else "Mark depleted",
                       lambda: _toggle_depleted(record))
    depleted.config(fg=WARN)
    depleted.pack(side="left", fill="x", expand=True, padx=(6, 0))

    pair = tk.Frame(buttons, bg=PANEL)
    pair.pack(fill="x", pady=(6, 0))
    _button(pair, "Copy coords",
            (lambda: _copy_coords(record)) if has_fix else None).pack(
        side="left", fill="x", expand=True)
    _button(pair, "Delete", lambda: _delete_bookmark(record), active=ALERT).pack(
        side="left", fill="x", expand=True, padx=(6, 0))


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
    note.bind("<Configure>", _wrap_to_width, add="+")

    picture = _newest_picture(body["name"], row["names"])
    button = _button(box, "Open the picture",
                     (lambda: _open_card(picture)) if picture else None)
    button.config(font=("Segoe UI", 9))
    button.pack(fill="x", padx=13, pady=(12, 13))


# One render, kept: (what it is of, the PhotoImage). Picking a bookmark redraws
# the whole window, and repainting a map from its points and drawing it is
# 70-160 ms measured - too long to spend again on a picture that has not
# changed. Tk also drops an image nothing holds a reference to.
_map_picture = None


def _location_map(parent, sheet, body, record, maps):
    """The saved map the picked bookmark lies on, above its card.

    Of the maps that reach the bookmark, the one whose centre is nearest -
    coverage.map_at, the same tie the Mapped tab counts with.

    Bare: no title, no legend. The card directly under it already says the
    body, the location and the material, and a legend of five bookmarks would
    be taller than the picture at this width.

    Nothing at all when the bookmark lies on no saved map, rather than an empty
    frame where a picture sometimes is - that reads as a failed load.
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
    key = (body["name"], name, database.revision())
    if _map_picture is None or _map_picture[0] != key:
        photo = _draw_location_map(parent, sheet, body, name, dict(maps)[name])
        if photo is None:
            return
        _map_picture = (key, photo)
    label = tk.Label(parent, image=_map_picture[1], bg=BG,
                     borderwidth=0, highlightthickness=0)
    label.image = _map_picture[1]
    label.pack(padx=(0, 14), pady=(14, 0))


def _draw_location_map(parent, sheet, body, name, data):
    """That map repainted from its points, every bookmark on the body on it.

    Every bookmark, not only the ones this map reaches: the ones outside it
    fall off the edge of the picture on their own, and deciding which reach
    would be the same sum coverage.picture already does.

    A failure is logged and None - the card is the thing that has to work.
    """
    try:
        cover = coverage.Coverage.from_dict(body["name"], data, name)
        if cover is None:
            return None
        codes, values = sheet.codes(), sheet.values()
        marks = []
        for mark in body["marks"]:
            lat, lon = mark.get("latitude"), mark.get("longitude")
            if lat is None or lon is None:
                continue
            material = (mark.get("commodity") or "").lower()
            marks.append((*cover.xy(float(lat), float(lon)), codes.get(material),
                          bool(mark.get("depleted_at")), values.get(material, 0),
                          mark.get("rigs")))
        # The best coverage.GOLDEN_SHOWN by Cr/h, as Share map and the minimap draw them.
        # Circles only: the credit label, 11 px at 400 px, is ~7 px at MAP_PX.
        spots = [(x, y, rigs, value or 0) for x, y, _, spent, value, rigs in marks if not spent]
        golden = [group[:4] for group in
                  coverage.golden_best(coverage.golden_groups(spots), spots)]
        image = coverage.picture(cover.mask, marks, (), (), cover.border_m, golden)
        out = io.BytesIO()
        image.resize((MAP_PX, MAP_PX), Image.LANCZOS).save(out, format="PNG")
        return tk.PhotoImage(master=parent, data=out.getvalue())
    except Exception:
        logger.exception(f"scan: could not draw {name} on {body['name']}")
        return None


def _field(parent, name):
    tk.Label(parent, text=name, bg=PANEL, fg=DIM, anchor="w",
             font=("Segoe UI", 7)).pack(fill="x", padx=13, pady=(10, 2))


def _ground_lines(sheet, body, material):
    """What this ground reads for the bookmark's material, and what it pays.

    Two short lines rather than one long one: the card is 310px wide, and a
    sentence that wraps is a sentence that pushed the buttons down.
    """
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
    """What that ground pays, most per location first, with its prices.

    Green is a material this body already has a bookmark for: somebody has stood
    on it here. The rest are what the ground has read elsewhere. One label a
    material rather than one line, because a line carries one colour and the
    whole point is telling the two apart without reading it.

    A picked material leads the line whatever its rate: the question has become
    "where is the jadeite", and a ground listed because it carries it at 4% has
    to say so.

    `materials` is what the picker offers. The three shown are the best three
    of those, not the best three of the ground: a line recommending copper
    while copper cannot be picked is a dead end. Filtered before the limit, so
    the next ones up are promoted - on a thin ground the line still comes out
    shorter than three, which is what that ground has to offer.
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
        # Two different answers. A ground with no rows has never been measured;
        # a ground whose every row is under the low value line has been, and
        # saying "nothing measured" about it is a lie the settings tab fixes.
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
    _state["selected"] = _key(record)
    _state["status"] = ""
    _draw()


def _pick_map(key):
    _state["map"] = key
    _state["status"] = ""
    _draw()


def _unfolded(body, index):
    return (body, index) not in _state["collapsed"]


def _fold(body, index):
    _state["collapsed"] ^= {(body, index)}
    _draw()


def _fold_all(body, groups, fold):
    for index, _group in groups:
        if fold:
            _state["collapsed"].add((body, index))
        else:
            _state["collapsed"].discard((body, index))
    _draw()


def _toggle_depleted(record):
    """Flip the bookmark between worked out and still worth flying to.

    Said in the status line either way: the row dims and one line of the card
    changes, both of which are easy to miss, and a write that failed must not
    look the same as one that worked.
    """
    depleted = not record.get("depleted_at")
    if cards.set_depleted(record, depleted):
        _state["status"] = (f"{_loc(record.get('location_index'))}, "
                            f"{_short(record.get('commodity'))}, "
                            + ("marked depleted." if depleted else "is active again."))
    else:
        messagebox.showwarning(
            "Depleted", "The bookmark could not be written - see the EDMC log.",
            parent=_window)
        _state["status"] = "The bookmark could not be written - see the EDMC log."
    _draw()


def _toggle_guide(record):
    """Start the arrow, or take it down, then draw again.

    Drawn again because the button that was pressed is not the only thing that
    changes: starting on a second bookmark has to turn the first one's Stop back
    into Guide.
    """
    if overlay.guiding(record):
        overlay.stop()
        _state["status"] = "The arrow is down."
    elif overlay.start(_window, record, on_stop=_refresh) is None:
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


def _style_field(widget):
    """A dialog control in the window's colours.

    Tk draws Menubutton, Spinbox and Entry in the system theme - grey and white
    - which is what they were against the dark dialog. Menu entries are on the
    Menu widget, not the Menubutton, so the dropdown is configured separately.
    """
    widget.config(bg=PANEL, fg=FG, relief="solid", borderwidth=1,
                  highlightthickness=0, font=("Consolas", 9))
    if isinstance(widget, tk.Menubutton):
        widget.config(anchor="w", padx=6, pady=2, indicatoron=True,
                      activebackground=PANEL, activeforeground=ACCENT)
        widget["menu"].config(bg=PANEL, fg=FG, activebackground=BG,
                              activeforeground=ACCENT, borderwidth=1,
                              activeborderwidth=0, tearoff=False)
        return
    widget.config(insertbackground=FG, disabledbackground=PANEL,
                  readonlybackground=PANEL, selectbackground=RULE,
                  selectforeground=FG)
    if isinstance(widget, tk.Spinbox):
        widget.config(buttonbackground=PANEL)


def _pickable(record):
    """Materials the Edit dialog offers: what the picker offers, plus this
    bookmark's own material when the low value filter hides it."""
    offered = [name for name in (_scan[4] if _scan else ()) if name in spotmark.MATERIALS]
    current = record.get("commodity")
    if current and current not in offered:
        offered.insert(0, current)
    return offered or list(spotmark.MATERIALS)


def _edit_bookmark(record):
    """Change what was typed at the press: material, rigs, amount, density,
    location. Coordinates, heading and marked_at are readings and stay.

    Modal over the window, because the list under it is rebuilt on save.
    """
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
        _style_field(widget)
        widget.grid(row=row, column=1, sticky="we", padx=(0, 14), pady=3)

    field(2, "Material", tk.OptionMenu(box, material, *_pickable(record)))
    field(3, "Rigs", tk.Spinbox(box, from_=0, to=deposit.MAX_RIGS, textvariable=rigs))
    field(4, "Amount", tk.OptionMenu(box, amount, NOT_SET, *deposit.AMOUNTS))
    field(5, "Density", tk.OptionMenu(box, density, NOT_SET, *deposit.DENSITIES))
    field(6, "Location", tk.Entry(box, textvariable=location))

    buttons = tk.Frame(box, bg=BG)
    buttons.grid(row=7, column=0, columnspan=2, sticky="e", padx=14, pady=(10, 14))
    _button(buttons, "Cancel", box.destroy).pack(side="right")
    _button(buttons, "Save",
            lambda: _save_edit(box, record, material.get(), rigs.get(),
                               amount.get(), density.get(), location.get())
            ).pack(side="right", padx=(0, 6))

    _centre_over(box, _window)
    box.grab_set()
    box.wait_window()


def _centre_over(box, parent):
    """Put `box` in the middle of `parent`.

    update_idletasks first: a Toplevel reports 1x1 until Tk has laid it out,
    and the sum would centre it off the top left corner.
    """
    box.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - box.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - box.winfo_height()) // 2
    box.geometry(f"+{max(0, x)}+{max(0, y)}")


def _save_edit(box, record, material, rigs, amount, density, location):
    """Write the dialog back to the bookmark, then redraw.

    An unparsable Rigs or Location is left as it was rather than refused: the
    dialog has no room for an error line, and the field shows what was kept.
    """
    fields = {
        "commodity": material or record.get("commodity"),
        "rigs": _int_or(rigs, record.get("rigs")),
        "amount": None if amount == NOT_SET else amount,
        "density": None if density == NOT_SET else density,
        "location_index": _int_or(location, record.get("location_index")),
    }
    try:
        spotcard.save(cards.edited(record, fields), id=record["id"])
    except Exception as err:
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
    """Ask, then remove the bookmark from disk.

    Asked because it is the one button here that destroys something, and the
    thing it destroys cannot be taken again - the patch is findable, the reading
    of what was on it is not.
    """
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
    """The coordinates onto the clipboard, for a message to somebody else.

    clipboard_clear before append: Tk appends to whatever was there, and the
    second press would otherwise hand over both.
    """
    text = _coords(record)
    if not text or _window is None:
        return
    _window.clipboard_clear()
    _window.clipboard_append(text)
    _state["status"] = f"Copied {text}"
    _draw()


def _share_map(body, group):
    """The picture of the saved map these bookmarks lie on, opened.

    Found on the press rather than on the draw: it rebuilds a mask for every
    saved map of the body, and doing that for every location of every draw cost
    more than the whole rest of the window.

    Drawn again on every press, then saved: a picture holds the bookmarks, the
    prices and the golden groups as they were when it was written, and all
    three move. The PNG already on disk is the fallback when the redraw fails.
    """
    maps = coverstore.maps(body, system_address=_system_address())
    picture = _drawn_now(body, group, maps) or _picture(body, group, maps)
    if picture:
        _open_card(picture)
        return
    _state["status"] = "No saved map holds this location yet."
    _draw()


def _drawn_now(body, group, maps):
    """The map under these bookmarks, drawn from its points and saved. Or None
    when no saved map reaches them, or the draw fails - both leave the caller
    with the same "nothing to open" it had before."""
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
        marks, golden = _map_marks(cover, system, body, sheet)
        title, legend = minimap.picture_text(cover, system)
        ground = _scan[0].ground(system, body) if _scan and _scan[0] else None
        image = coverage.picture(cover.mask, marks, title, legend, cover.border_m, golden,
                                 ground)
    except Exception:
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


def _map_marks(cover, system, body, sheet):
    """(marks, golden groups) for every bookmark of the body the map reaches.

    Same shape minimap hands coverage.picture: metres east and north of the
    origin, the material's code, whether it is worked out, what it is worth and
    how many rigs are on it.
    """
    codes = sheet.codes() if sheet is not None else {}
    values = sheet.values() if sheet is not None else {}
    marks = []
    for record in (cards.for_system(system) if system else ()):
        lat, lon = record.get("latitude"), record.get("longitude")
        if (record.get("planet_name") != body or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float)) or not cover.reaches(lat, lon)):
            continue
        material = (record.get("commodity") or "").lower()
        marks.append((*cover.xy(lat, lon), codes.get(material),
                      bool(record.get("depleted_at")), values.get(material, 0),
                      record.get("rigs")))
    spots = [(x, y, rigs, value or 0) for x, y, _, spent, value, rigs in marks if not spent]
    golden = coverage.golden_best(coverage.golden_groups(spots), spots)
    return marks, golden


def _refresh():
    """Draw again, if the window is still there.

    The overlay calls this when it takes itself down, which can be minutes after
    the press and with the window long since gone - so the line that said an
    arrow was up goes with it.
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
    return sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or 0))


def _picture(body, group, maps):
    """The saved map picture the first of these bookmarks lies on, or None."""
    for record in group:
        lat, lon = record.get("latitude"), record.get("longitude")
        if lat is None or lon is None:
            continue
        name = coverage.map_at(maps, body, float(lat), float(lon))
        picture = _newest_picture(body, [name]) if name else None
        if picture:
            return picture
    return None


def _newest_picture(body, names):
    """The newest PNG of these maps, or None - two maps of one location are two
    drives, and the later one is the one worth sending."""
    paths = [os.path.join(coverstore.folder(body), f"{name}.png") for name in names]
    paths = [path for path in paths if os.path.isfile(path)]
    return max(paths, key=os.path.getmtime) if paths else None


def _nearest(group, status):
    """How far the closest bookmark of one location is, or '-'.

    On the location line rather than on every row: the deposits of one location
    are a few dozen metres apart, and the question the list answers is which
    location to drive to. Guide answers the last hundred metres.
    """
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
    """The PNG, in whatever shows PNGs here.

    Opened rather than drawn into this window: it is a picture made to be sent
    to somebody, and the viewer that opens it is the thing that can save it,
    zoom it and copy it.
    """
    try:
        os.startfile(path)                       # Windows, which is where EDMC runs
    except AttributeError:
        webbrowser.open(pathlib.Path(path).as_uri())
    except OSError as err:
        logger.warning(f"could not open {path}: {err}")


# ------------------------------------------------------------------ the parts


def _button(parent, text, command=None, active=ACCENT):
    """The window has one button style, and this is it.

    Without a command the button is disabled rather than silently dead: a button
    that does nothing when pressed reads as a bug, and a greyed one reads as not
    finished. `active` is what it turns under the pointer - the one button that
    destroys something says so there rather than by sitting in red all the time.
    """
    return tk.Button(parent, text=text, command=command,
                     bg=BG, fg=FG, activebackground=BG,
                     activeforeground=active, disabledforeground=DIM,
                     relief="solid", borderwidth=1, highlightthickness=0,
                     padx=8, pady=1, font=("Segoe UI", 8),
                     cursor="hand2" if command else "arrow",
                     state="normal" if command else "disabled")


def _clickable(widget, command, skip_buttons=False):
    """A whole row, clickable.

    Tk hands a click to the widget under the pointer and does not pass it up to
    the parent, so a row is only clickable if every label in it is. Buttons keep
    their own command - which is what skip_buttons is for on the location line,
    where Share map must not fold it.
    """
    def press(event):
        command()

    pending = [widget]
    while pending:
        current = pending.pop()
        if skip_buttons and isinstance(current, tk.Button):
            continue
        current.config(cursor="hand2")
        current.bind("<Button-1>", press)
        pending.extend(current.winfo_children())


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
    """A canvas with a frame in it, because Tk has no scrolling frame.

    Returns the inner frame. `name` is what the scroll position is remembered
    under, so a draw puts the list back where it was rather than at the top.
    """
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
    _wheel(canvas)
    # After the layout, not now: the scrollregion is set by the <Configure> the
    # rows above are about to fire, and moving to a fraction of nothing is a
    # move to the top.
    canvas.after_idle(lambda: _restore_scroll(canvas, name))
    return inner


def _restore_scroll(canvas, name):
    try:
        if canvas.winfo_exists():
            canvas.yview_moveto(_scroll.get(name, 0.0))
    except tk.TclError:
        pass


def _wheel(canvas):
    """The wheel scrolls whichever list the pointer is over.

    bind_all while the pointer is inside, because the rows live in frames inside
    the canvas and the event goes to the widget under the pointer rather than to
    the canvas. Whatever was bound is put back on the way out: EDMC and the
    other plugins bind the wheel the same way, and unbind_all takes theirs with
    it.
    """
    def scroll(event):
        canvas.yview_scroll(-int(event.delta / 120), "units")

    def enter(event):
        canvas.rs_previous = canvas.bind_all("<MouseWheel>")
        canvas.bind_all("<MouseWheel>", scroll)

    def leave(event):
        canvas.unbind_all("<MouseWheel>")
        if getattr(canvas, "rs_previous", None):
            canvas.bind_all("<MouseWheel>", canvas.rs_previous)
            canvas.rs_previous = None

    canvas.bind("<Enter>", enter, add="+")
    canvas.bind("<Leave>", leave, add="+")
    canvas.bind("<Destroy>", leave, add="+")
