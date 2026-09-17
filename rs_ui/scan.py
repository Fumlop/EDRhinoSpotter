"""The RhinoData window: what is worth landing on, here, right now.

One row per landable body, grouped by what kind of body it is, with the
materials that kind of body has been found to hold underneath. The body list
comes from the journal, with gaps filled from Spansh on the honk; the
percentages come from mining_sheet.json, which ships with the plugin.

The window is deliberately read-only and disposable. Nothing is saved from it,
so pressing the button twice costs nothing and the card flow is untouched.
"""

import os
import pathlib
import tkinter as tk
import webbrowser
from tkinter import font as tkfont, messagebox

from rs_core import (cards, coverage, coverstore, deposit, grounds, guide, palette,
                     spotmark)
from rs_core.logging import logger
from rs_ui import overlay, rhino

try:
    from theme import theme
except ImportError:      # running outside EDMC
    theme = None

# Three. Four was what the window was sized around, and it was the longest
# line in it by a hundred pixels - the fourth material is the least likely one
# anyway, and a row of four pairs is a run of words rather than a list.
TOP_MATERIALS = 3
MIN_PCT = 2.0

# Wide enough for "15 d a" and every other body designation in a normal
# system, and narrow enough that the numbers start in the same place.
NAME_WIDTH = 8

BG = palette.BG
PANEL = palette.PANEL
FG = palette.FG
DIM = palette.MUTED
# ACCENT is what can be clicked, and nothing else - the colour a button turns
# under the pointer. It was the heading colour too, which is why a heading and
# a thing you could press looked the same; headings are FG now.
ACCENT = palette.ACCENT
# GOOD is a verdict: this patch still has something in it. It was also every
# material rate, where it said nothing - 4% and 56% were the same green - and
# the number was doing that work already.
GOOD = palette.GOOD
WARN = palette.WARN

_window = None           # only ever one, so the button cannot bury the panel
_scan = None             # what show() was last given, so Back can rebuild
_body = None             # the bookmark view's own arguments, for the same reason
_view = None             # draws again whatever the window is showing
TOP_HERE = 3             # materials listed under a body's bookmark count


def is_open():
    return _window is not None and bool(_window.winfo_exists())


def show(parent, register, sheet, focus=None, variable=None, materials=(), here=None):
    """Open the window, or raise the one already open.

    `focus` is one material. Given one, only the grounds that have ever
    carried it are listed, and it leads every material line whatever its rate
    - the question has changed from "what is here" to "where is the jadeite",
    and a ground that answers it at 4% still answers it.

    `here` is the body name when Status.json has us on or over one - in the
    SRV, landed, or in orbital cruise. Then the window opens on that body's
    bookmarks, whether it has any yet or not; Back goes to the body list. It
    is read on the first open only: a window already up is redrawn where the
    commander left it, not sent back to the body under the ship.

    `variable` is the panel's own material StringVar, not a copy. The picker
    under the system name writes to it, so choosing here is the same act as
    choosing down in the panel and the two can never disagree. Watching that
    variable is the panel's job - one watcher, added once, rather than another
    one on every open.
    """
    global _window, _scan

    # First, so the redraw below and every view built after it read the
    # material that was just picked.
    _scan = (register, sheet, focus, variable, materials)

    if _window is not None and _window.winfo_exists():
        # Picking a material used to destroy the window and build a new one,
        # which put whoever was two views deep back on the body list with the
        # scroll at the top. The window stays; what it is showing is drawn
        # again, wherever it was moved to and whatever it was.
        logger.debug(f"scan: redraw, system={register.system!r} focus={focus!r}")
        (_view or (lambda: _scan_view(_window)))()
        _window.lift()
        return _window

    logger.debug(f"scan: open, system={register.system!r} focus={focus!r}")
    _window = tk.Toplevel(parent)
    _window.configure(bg=BG)
    # Debug only, and only on the window itself: whatever takes it away, this
    # is the line that names it. A window that vanishes with no Python frame
    # behind it is the one thing the stack cannot be asked about afterwards.
    _window.bind("<Destroy>", _log_destroy, add="+")
    # Over the game on the way up - the key that opens it is pressed with the
    # game in front, and a window behind it is not an answer. Borderless or
    # windowed only; nothing draws over exclusive fullscreen.
    #
    # Given up the moment something else is clicked. Left on, it would sit
    # over EDMC and everything else for as long as it is open, which is not
    # what a page of numbers gets to do.
    _window.attributes("-topmost", True)
    _window.bind("<FocusOut>", _drop_topmost, add="+")
    # The way out, for a window opened by a key press rather than a mouse.
    _window.bind("<Escape>", lambda event: _window.destroy())
    _window.focus_force()
    if here and register.system:
        _bookmarks_view(_window, register.system, here,
                        cards.by_body(register.system).get(here, []))
    else:
        _scan_view(_window)
    return _window


def _drop_topmost(event):
    """Stop shadowing the rest of the desktop, once.

    Only for the window itself: a FocusOut from a child widget - the material
    picker opening its menu is one - is not somebody leaving the window.
    """
    if _window is not None and event.widget is _window:
        _window.attributes("-topmost", False)
        _window.unbind("<FocusOut>")


def _log_destroy(event):
    if _window is not None and event.widget is _window:
        logger.debug("scan: the window was destroyed")


def _clear(window):
    for child in window.winfo_children():
        child.destroy()


def _scan_view(window):
    """The body list, built into an empty window.

    Rebuilt rather than hidden and shown again: Back comes through here, and a
    list kept alive behind the bookmarks is a list that missed every scan that
    landed while it was behind them.
    """
    global _body, _view
    register, sheet, focus, variable, materials = _scan
    logger.debug("scan: building the body list")
    _body = None            # the overlay's refresh must not draw bookmarks over the list
    _view = lambda: _scan_view(window)
    _clear(window)
    window.title(f"RhinoData - {register.system or 'unknown system'}"
                 + (f" - {focus}" if focus else ""))

    outer = tk.Frame(window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    _header(outer, register, sheet, focus, variable, materials)

    marked = cards.by_body(register.system) if register.system else {}
    groups = register.by_ground()
    if focus:
        groups = [(ground, found) for ground, found in groups
                  if sheet.rate(ground, focus) is not None]
    listing, wrap = _scrollable(outer)
    # Prose is excluded from the width measurement below - it fits whatever it
    # is given. The material lines are not: they are the widest real content,
    # and a window narrower than one of them wraps a list that should be a row.
    prose = []
    if not groups:
        prose.append(wrap(_empty(listing, register, focus)))
    else:
        for ground, found in groups:
            _group(listing, ground, _shorten(found, register.system), sheet, wrap,
                   focus, marked)

    _footer(outer, sheet, _Wrapper(window, margin=40))
    # Buttons are not labels and the width measurement cannot see them, so a
    # list with any of them on it asks for the room they take - see BUTTONS.
    _fit(window, listing, prose, extra=ROW_BUTTONS if marked else 0)


# What the window may grow to before it starts scrolling instead. Wide enough
# for four materials on one line and a body row beside them; tall enough for a
# well-scanned system without covering the whole screen.
MAX_WIDTH = 900
MAX_HEIGHT = 780
OUTER_PAD = 14
SCROLLBAR = 18
# The three spaces every body row starts with.
INDENT = 24
# What Tk adds around a label's text, left and right together.
LABEL_PAD = 6
# Borders, the canvas's own edge and rounding: without it the last word of the
# widest material line wrapped onto a second line by a few pixels.
SLACK = 24
# Header, the two lines above the list, and the footer under it. Generous on
# purpose: the footer wraps to two lines in a narrow window, and a height that
# is a little too large costs empty space while one that is too small eats the
# footer.
CHROME = 200


def _row(parent):
    """A frame whose labels sit side by side, and are measured as one line.

    _measure sees labels one at a time, so a body row with its bookmarks and
    Mapped links beside it was sized by its widest single piece and opened
    with the links cut off at the right edge.
    """
    frame = tk.Frame(parent, bg=BG)
    frame.rs_row = True
    return frame


def _rows(container):
    """Every side-by-side row in the list, however deeply nested."""
    found = []
    for child in container.winfo_children():
        if getattr(child, "rs_row", False):
            found.append(child)
        else:
            found.extend(_rows(child))
    return found


def _row_width(row, fonts):
    """The labels of one row laid end to end, with the padding Tk puts on each."""
    total = 0
    for label in row.winfo_children():
        if not isinstance(label, tk.Label) or not label.cget("text"):
            continue
        spec = str(label.cget("font"))
        metrics = fonts.get(spec)
        if metrics is None:
            metrics = fonts[spec] = tkfont.Font(font=spec)
        total += metrics.measure(label.cget("text")) + LABEL_PAD
    return total


def _lines(container):
    """Every label in the list, however deeply nested."""
    found = []
    for child in container.winfo_children():
        if isinstance(child, tk.Label):
            found.append(child)
        found.extend(_lines(child))
    return found


def _measure(labels, skip=()):
    """The width of the widest label, measured off its text and its font.

    Prose is skipped: it fits whatever width it is given, so letting it ask for
    its one-line width sized the window to the longest sentence in it - an
    empty system opened 900px wide to hold two lines of explanation.

    Not off the widgets: a frame inside a canvas reports whatever its children
    asked for before anything was laid out, and wraplength is still zero at
    that point, so the answer came back both too small and too late. Font
    metrics are exact and available immediately.

    One Font per font rather than one per label. Three fonts are ever used in
    here, and building a fresh one for each of a hundred labels was a Tcl call
    per label for an answer that does not differ - 31 ms against 14 on a
    well-scanned system.
    """
    widest = 0
    skip = set(skip)
    fonts = {}
    for label in labels:
        if label in skip:
            continue
        text = label.cget("text")
        if not text:
            continue
        spec = str(label.cget("font"))
        metrics = fonts.get(spec)
        if metrics is None:
            metrics = fonts[spec] = tkfont.Font(font=spec)
        for line in text.splitlines():
            widest = max(widest, metrics.measure(line))
    return widest


def _fit(window, listing, wrapped=(), extra=0):
    """Open at the size the content asks for, capped.

    Measured off the list rather than the window: a canvas has no natural size
    of its own, so asking the window how big it wants to be gets an answer
    that ignores everything inside the scrolling area - 520px, for content
    that needs 700.

    A fixed geometry was a guess and it was wrong in both directions: too
    narrow for four materials on a line, too tall for a system with two bodies
    in it. Past the cap the list scrolls, which is what the scrollbar is for.
    """
    window.update_idletasks()
    # The rows, plus the scrollbar they sit beside and the padding around them.
    # A row of labels side by side counts as the sum of them, not its widest.
    fonts = {}
    rows = max((_row_width(row, fonts) for row in _rows(listing)), default=0)
    content = (max(_measure(_lines(listing), wrapped), rows) + extra
               + SCROLLBAR + 2 * OUTER_PAD + INDENT + SLACK)
    width = min(max(content, 420), MAX_WIDTH)
    wanted = max(window.winfo_reqheight(), listing.winfo_reqheight() + CHROME)
    height = min(max(wanted, 260), MAX_HEIGHT)
    logger.debug(f"scan: fit to {width}x{height}")
    window.geometry(f"{width}x{height}")
    window.minsize(480, 240)


def _header(parent, register, sheet, focus=None, variable=None, materials=()):
    name = tk.Label(parent, text=register.system or "no system yet", bg=BG, fg=FG,
                    font=("Segoe UI", 15, "bold"), anchor="w")
    name.pack(fill="x")
    # Click the system name. Nothing says so - that is the point of it.
    name.bind("<Button-1>", lambda event: rhino.run(name.winfo_toplevel()))

    if variable is not None and materials:
        _picker(parent, variable, materials)

    count = len(register)
    line = f"{count} landable {'body' if count == 1 else 'bodies'} scanned"
    if not sheet.loaded:
        line += "  -  no mining_sheet.json, types only"
    tk.Label(parent, text=line, bg=BG, fg=DIM, anchor="w",
             font=("Segoe UI", 9)).pack(fill="x", pady=(0, 10))


def _picker(parent, variable, materials):
    """The material picker, under the system name.

    Bound to the panel's own variable rather than a copy of its value, so
    choosing here is the same act as choosing down in the panel. Two pickers
    that can disagree are worse than one picker in the wrong place.

    Nothing is watched from here. A trace added on every open is a trace added
    three times by the third open, and then one pick redraws the window three
    times.
    """
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(6, 2))
    tk.Label(row, text="Showing", bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left")

    before = variable.get()
    picker = tk.OptionMenu(row, variable, *materials)
    if variable.get() != before:
        logger.debug(f"picker: OptionMenu moved the material {before!r} -> "
                     f"{variable.get()!r}")
    picker.config(relief="solid", borderwidth=1, highlightthickness=0,
                  bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=ACCENT,
                  anchor="w", padx=6, pady=0, font=("Segoe UI", 9))
    picker["menu"].config(bg=PANEL, fg=FG, activebackground=ACCENT,
                          activeforeground=BG, borderwidth=1,
                          activeborderwidth=0, tearoff=False,
                          font=("Segoe UI", 9))
    picker.pack(side="left", padx=8)


def _empty(parent, register, focus=None):
    """What to do, then why - in that order.

    The empty window is where everybody meets this plugin for the first time,
    and the thing they have just done is honk. The instruction has to be the
    first line, not the conclusion of a paragraph about journal events.
    """
    if register.system and focus:
        action = f"No ground here carries {focus}"
        why = ("Set the material back to All to see what this system does "
               "have, or try the next one.")
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

    tk.Label(parent, text=action, bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 11, "bold")).pack(fill="x", pady=(6, 4))
    label = tk.Label(parent, text=why, bg=BG, fg=DIM, justify="left", anchor="w")
    label.pack(fill="x")
    return label


def _group(parent, ground, found, sheet, wrap, focus=None, marked=None):
    """One body type, its bodies, and what that type has been found to hold."""
    block = tk.Frame(parent, bg=BG)
    block.pack(fill="x", pady=(0, 16))

    head = tk.Frame(block, bg=BG)
    head.pack(fill="x")
    tk.Label(head, text=grounds.label(ground), bg=BG, fg=FG,
             font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left")
    tk.Label(head, text=f"{len(found)} of them", bg=BG, fg=DIM,
             font=("Segoe UI", 9), anchor="w").pack(side="left", padx=8)

    materials = sheet.best(ground, limit=TOP_MATERIALS, minimum=MIN_PCT)
    if focus:
        # The chosen material leads, whatever its rate, and in the accent
        # colour so it is not read as one of the others. A ground listed
        # because it carries jadeite has to say what it carries it at, even
        # when three better-paying things sit under it.
        # On one line with the other two: three materials side by side read as
        # one answer, and the focus stacked above them read as a heading.
        rate = sheet.rate(ground, focus)
        line = _row(block)
        line.pack(fill="x", pady=(2, 5))
        tk.Label(line, text=f"{focus} {rate}%", bg=BG, fg=FG, anchor="w",
                 font=("Consolas", 9, "bold")).pack(side="left")
        rest = [row for row in materials
                if row["material"].lower() != focus.lower()][:TOP_MATERIALS - 1]
        if rest:
            tk.Label(line, text="   ·   " + "   ·   ".join(
                         f"{row['material']} {row['pct']}% {_price(row.get('median'))}"
                         for row in rest),
                     bg=BG, fg=FG, anchor="w", font=("Consolas", 9)).pack(side="left")
    elif materials:
        # Separated, not just spaced: "Olivine 56.1%  Monazite 45.6%" reads as
        # one run of words, and the eye has to find the pairs itself.
        # The price beside the rate: this is the screen the body is picked
        # on, and a rate without what it pays is half the answer.
        text = "   ·   ".join(f"{row['material']} {row['pct']}% {_price(row.get('median'))}"
                              for row in materials)
        line = tk.Label(block, text=text, bg=BG, fg=FG, anchor="w",
                        font=("Consolas", 9), justify="left")
        line.pack(fill="x", pady=(1, 5))
        wrap(line)
    elif sheet.loaded:
        tk.Label(block, text="nothing measured on this ground yet", bg=BG, fg=WARN,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x")

    # Over every group, not once over the window: the list scrolls, the
    # groups are far apart, and a single header at the top names columns that
    # are three screens away by the time you are reading them.
    _table_header(block, _body_columns("Body", "Distance", "Locations",
                                       "Volcanism"))

    for body in found:
        # Unprobed bodies are dimmed rather than dropped. They are the right
        # ground, but nobody has counted them, so they are where you go once
        # the counted ones are worked out.
        probed = body.get("locations") is not None
        records = (marked or {}).get(body["name"]) or []
        row = _row(block)
        row.pack(fill="x")
        name = tk.Label(row, text="   " + _body_line(body), bg=BG,
                        fg=FG if probed else DIM, anchor="w",
                        font=("Consolas", 9))
        name.pack(side="left")
        _cards_link(row, records, focus)
        _mapped_link(row, body, records)
        _opens_bookmarks(row, name, body["name"], records)


def _opens_bookmarks(row, label, body, records):
    """The whole body row opens that body's bookmarks, marked or not.

    Not marked is the case that needed it: the page under a row is also where
    the ground's best-paying materials and their prices are (_top_here), and
    on a body nobody has bookmarked there was nothing to click at all.

    Bound on the frame and on the name label both - Tk hands a click to one
    widget and does not pass it up to the parent, and the links packed beside
    the name already have their own.
    """
    system = _scan[0].system if _scan else None

    def open_it(event):
        _bookmarks_view(row.winfo_toplevel(), system, body, records)

    for widget in (row, label):
        widget.config(cursor="hand2")
        widget.bind("<Button-1>", open_it)


def _cards_link(parent, records, focus=None):
    """A "2 bookmarks" button behind a body you have already marked.

    Only on bodies that have one. A count of zero on every other row would be
    nine pieces of nothing in a ten-body system, and the useful signal here is
    "you have been here before" - which is only worth saying when true.

    With a material picked, only that material's bookmarks count, and the list
    opens filtered to it - by the same picker, which is on that page too.
    """
    if focus:
        picked = [r for r in records or []
                  if (r.get("commodity") or "").lower() == focus.lower()]
    else:
        picked = records
    if not picked:
        return
    count = len(picked)
    system = records[0].get("system")
    body = records[0].get("planet_name")
    _button(parent, f"{count} bookmark{'' if count == 1 else 's'}",
            lambda: _bookmarks_view(parent.winfo_toplevel(), system, body, records)
            ).pack(side="left", padx=(10, 0))


def _system_address():
    """The SystemAddress of the register's system, or None - what keeps a body's
    maps apart from those of a body with the same name elsewhere."""
    return _scan[0].system_address if _scan else None


def _mapped_link(parent, body, records):
    """A "Mapped 3/20" button behind a body with saved maps.

    Only on bodies with a map, for the same reason as the bookmarks link: the
    signal is "you have driven here", and nothing is worth saying where you
    have not. The count is locations, not maps - two maps on one location is
    still one location done.
    """
    name = body["name"]
    maps = coverstore.maps(name, system_address=_system_address())
    if not maps:
        return
    mapped, _ = coverage.mapped_locations(maps, name, records or [])
    total = body.get("locations")
    text = f"Mapped {len(mapped)}/{total}" if total is not None else f"Mapped {len(mapped)}"
    _button(parent, text,
            lambda: _mapped_view(parent.winfo_toplevel(), name, total, records or [])
            ).pack(side="left", padx=(6, 0))


def _mapped_view(window, body, total, records):
    """The locations of one body that have a saved map, in the same window.

    Mapped locations only, numbered, each with its maps, how many bookmarks it
    has and Share map for its picture. Maps that no targeted location and no
    bookmark tie to anything are listed after, so no drive goes missing.
    """
    global _body, _view
    _body = None            # the overlay's refresh must not draw bookmarks over this
    _view = lambda: _mapped_view(window, body, total, records)
    maps = coverstore.maps(body, system_address=_system_address())
    mapped, unknown = coverage.mapped_locations(maps, body, records)
    logger.debug(f"scan: building the maps of {body}, {len(mapped)} location(s), "
                 f"{len(unknown)} untied")
    _clear(window)
    window.title(f"RhinoData - {body} - mapped")

    outer = tk.Frame(window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    back = tk.Frame(outer, bg=BG)
    back.pack(fill="x", pady=(0, 6))
    _button(back, "‹ Back", lambda: _scan_view(window)).pack(side="left")

    tk.Label(outer, text=body, bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 15, "bold")).pack(fill="x")
    system = _scan[0].system if _scan else None
    of = f"{len(mapped)} of {total} locations mapped" if total is not None \
        else f"{len(mapped)} location{'' if len(mapped) == 1 else 's'} mapped"
    tk.Label(outer, text=f"{system or ''}  -  {of}", bg=BG, fg=DIM, anchor="w",
             font=("Segoe UI", 9)).pack(fill="x")
    # Above the list, not under it: a short list opens a short window, and a
    # wrapped note at the bottom of one was cut off.
    note = tk.Label(outer, text="A location counts as mapped when it was targeted while the map "
                                "was driven, or when one of its bookmarks lies on the map.",
                    bg=BG, fg=DIM, anchor="w", justify="left", font=("Segoe UI", 8))
    note.pack(fill="x", pady=(2, 10))
    _Wrapper(window, margin=40)(note)

    _table_header(outer, _mapped_columns("Location", "Maps", "Bookmarks"))
    listing, _ = _scrollable(outer)
    counts = {}
    for record in records:
        counts[record.get("location_index")] = counts.get(record.get("location_index"), 0) + 1
    for location in sorted(mapped):
        count = counts.get(location, 0)
        marks = f"{count} bookmark{'' if count == 1 else 's'}" if count else "no bookmarks"
        _mapped_row(listing, body, f"loc {location}", mapped[location], marks)
    if unknown:
        tk.Label(listing, text="location unknown", bg=BG, fg=DIM, anchor="w",
                 font=("Segoe UI", 10, "bold")).pack(fill="x", pady=(10, 2))
        for name in unknown:
            _mapped_row(listing, body, "", [name], "")

    _fit(window, listing, extra=110)


def _mapped_columns(location, maps, marks):
    """The one place the map table's column widths live, so the header cannot
    drift away from the rows it names."""
    return f"{location:<8} {maps[:24]:<24} {marks}"


def _mapped_row(parent, body, location, names, marks):
    """loc 7   map 2, map 5   2 bookmarks   [Share map] - the newest picture of them."""
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=1)
    text = _mapped_columns(location, ", ".join(names), marks)
    tk.Label(row, text="   " + text, bg=BG, fg=FG, anchor="w",
             font=("Consolas", 9)).pack(side="left")
    pictures = [os.path.join(coverstore.folder(body), f"{name}.png") for name in names]
    pictures = [path for path in pictures if os.path.isfile(path)]
    picture = max(pictures, key=os.path.getmtime) if pictures else None
    _button(row, "Share map", (lambda: _open_card(picture)) if picture else None).pack(
        side="right")


# The three buttons on every bookmark row. Buttons are not labels, so the width
# measurement cannot see them and the window would open exactly that much too
# narrow - and a row too narrow does not wrap, it drops what is packed right.
BUTTONS = 220
# The same, for the two that sit behind a body on the list: bookmarks and
# mapped, side by side.
ROW_BUTTONS = 200


def _bookmarks_view(window, system, body, records):
    """The bookmarks of one body, in the window the body list was in.

    The same window on purpose: this is a step into the row that was clicked,
    not a second thing on the screen, and Back is the way out of it. It was a
    page in the browser, which meant leaving the game to read three numbers.
    """
    global _body, _view
    logger.debug(f"scan: building the bookmarks of {body}, {len(records)} of them")
    _body = (window, system, body, records)
    _view = lambda: _bookmarks_view(window, system, body, records)
    _clear(window)
    window.title(f"RhinoData - {body} - bookmarks")

    outer = tk.Frame(window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    back = tk.Frame(outer, bg=BG)
    back.pack(fill="x", pady=(0, 6))
    _button(back, "‹ Back", lambda: _scan_view(window)).pack(side="left")

    # The body, and under it the same picker the body list has, on the panel's
    # own material. One control for the whole plugin: a filter that lives only
    # on this page is a filter that can disagree with the list you came from.
    tk.Label(outer, text=body, bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 15, "bold")).pack(fill="x")
    focus = _scan[2] if _scan else None
    if _scan and _scan[3] is not None and _scan[4]:
        _picker(outer, _scan[3], _scan[4])
    shown = [r for r in records if focus is None
             or (r.get("commodity") or "").lower() == focus.lower()]

    count = len(records)
    counted = (f"{len(shown)} of {count} bookmarks" if len(shown) != count
               else f"{count} bookmark{'' if count == 1 else 's'}")
    tk.Label(outer, text=f"{system or ''}  -  {counted}",
             bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 9)).pack(fill="x")
    _top_here(outer, body)

    _table_header(outer, _columns("Loc", "Material", "Rigs", "Distance"))
    listing, _ = _scrollable(outer)
    if not records:
        tk.Label(listing, text="   no bookmarks on this body yet", bg=BG, fg=DIM, anchor="w",
                 font=("Segoe UI", 9)).pack(fill="x", pady=(6, 0))
    maps = coverstore.maps(body, system_address=_system_address())
    # Once for the whole table rather than once a row, and a reading rather
    # than a subscription: the distances are what they were when the page was
    # drawn. Back and forward redraws them; the arrow is what follows you.
    status = spotmark.read_status()
    for index, group in _by_location(shown):
        _location_header(listing, body, index, group, maps)
        for record in cards.ordered(group):
            _bookmark_row(listing, record, status)

    note = tk.Label(outer, text="Guide puts an arrow over the game, top middle - "
                                "borderless or windowed only. Share map opens the "
                                "picture of the map a location's bookmarks are on.",
                    bg=BG, fg=DIM, anchor="w", justify="left",
                    font=("Segoe UI", 8))
    note.pack(side="top", fill="x", pady=(8, 0))
    _Wrapper(window, margin=40)(note)
    _fit(window, listing, extra=BUTTONS)


def _top_here(parent, body):
    """The three best-paying materials on this body's ground - rate times median
    price, the same pick as the body list - each with its price, under the
    bookmark count. From the mining sheet, so a body the
    journal has not described yet has no ground and gets a line saying so."""
    register, sheet = (_scan[0], _scan[1]) if _scan else (None, None)
    ground = None
    if register is not None:
        for known in register.bodies():
            if known.get("name") == body:
                ground = known.get("ground")
                break
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(2, 10))
    if ground is None or sheet is None:
        tk.Label(row, text="no body type yet - FSS or scan the body for its likely materials",
                 bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        return
    rows = sheet.best(ground, limit=TOP_HERE, minimum=MIN_PCT)
    if not rows:
        tk.Label(row, text=f"{grounds.label(ground)}: nothing measured on this ground yet",
                 bg=BG, fg=WARN, anchor="w", font=("Segoe UI", 9)).pack(side="left")
        return
    text = "   ·   ".join(f"{r['material']} {r['pct']}% {_price(r.get('median'))}" for r in rows)
    tk.Label(row, text=text, bg=BG, fg=FG, anchor="w", font=("Consolas", 9)).pack(side="left")


def _price(credits):
    """208k, 1.2M, or 'no price' - the median a market pays per tonne."""
    if not credits:
        return "(no price)"
    if credits >= 1_000_000:
        return f"({credits / 1_000_000:.1f}M)"
    return f"({round(credits / 1000):,}k)"


def _by_location(records):
    """[(location, [bookmark, ...]), ...], by location, unnumbered last."""
    groups = {}
    for record in records:
        groups.setdefault(record.get("location_index"), []).append(record)
    return sorted(groups.items(), key=lambda item: (item[0] is None, item[0] or 0))


def _location_header(parent, body, index, group, maps):
    """'loc 2' over its bookmarks, and Share map for the map they were made on.

    The map is found from the bookmarks' own coordinates - maps are kept by
    where the SRV came down, not by location number. Greyed when none of them
    lies on a saved map with a picture.
    """
    head = tk.Frame(parent, bg=BG)
    head.pack(fill="x", pady=(8, 2))
    tk.Label(head, text="loc " + (str(index) if index is not None else "-"), bg=BG, fg=FG,
             anchor="w", font=("Segoe UI", 10, "bold")).pack(side="left")
    picture = None
    for record in group:
        lat, lon = record.get("latitude"), record.get("longitude")
        if lat is None or lon is None:
            continue
        name = coverage.map_at(maps, body, float(lat), float(lon))
        path = os.path.join(coverstore.folder(body), f"{name}.png") if name else None
        if path and os.path.isfile(path):
            picture = path
            break
    _button(head, "Share map", (lambda: _open_card(picture)) if picture else None).pack(
        side="left", padx=(10, 0))


def _columns(loc, material, rigs, away):
    """The one place the bookmark table's column widths live, so the header
    cannot drift away from the rows it names. It names the top line of a row
    only - the dim line under each one is position, time and heading."""
    return f"{loc.ljust(7)} {material[:22].ljust(22)} {rigs.rjust(7)} {away.rjust(8)}"


def _bookmark_row(parent, record, status):
    """One bookmark, on two lines.

    Two because one did not fit: the coordinates carry six decimals each and
    with a material beside them the line ran past the right edge of any
    sensible window, taking the buttons with it. The top line is the patch -
    what was mined there and how big it is - and the buttons that act on it;
    the dim line under it is where and when.
    """
    row = tk.Frame(parent, bg=BG)
    row.pack(fill="x", pady=(2, 6))

    head = tk.Frame(row, bg=BG)
    head.pack(fill="x")
    tk.Label(head, text="   " + _bookmark_line(record, status), bg=BG, fg=FG, anchor="w",
             font=("Consolas", 9)).pack(side="left")
    # Delete first: side="right" packs from the edge inwards, and Guide is the
    # one that belongs beside the row rather than at the very end. Clear of
    # the scrollbar on the right, which the row runs up against.
    _button(head, "Delete", lambda: _delete_bookmark(record),
            active=palette.ALERT).pack(side="right", padx=(4, 6))
    _guide_button(head, record)
    _depleted_button(head, record)

    tk.Label(row, text="   " + _bookmark_detail(record), bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 8)).pack(fill="x")


def _depleted_button(parent, record):
    """Green "Active" while the patch still has something, red "Depleted" once
    it is marked mined out; a press flips it. Packed after Guide, so it sits
    before it on the row."""
    depleted = bool(record.get("depleted_at"))
    button = _button(parent, "Depleted" if depleted else "Active",
                     lambda: _toggle_depleted(record))
    button.config(fg=palette.ALERT if depleted else GOOD)
    button.pack(side="right", padx=(0, 4))


def _toggle_depleted(record):
    if not cards.set_depleted(record, not record.get("depleted_at")):
        messagebox.showwarning(
            "Depleted", "The bookmark could not be written - see the EDMC log.",
            parent=_window)
    _reload()


def _guide_button(parent, record):
    """Guide, or Stop while this is the bookmark being guided to.

    Disabled on a bookmark with no coordinates - there were versions of the
    card before the coordinates went into the sidecar, and there is nothing to
    point at on one of those.
    """
    if record.get("latitude") is None or record.get("longitude") is None:
        _button(parent, "Guide").pack(side="right")
        return
    running = overlay.guiding(record)
    _button(parent, "Stop" if running else "Guide",
            lambda: _toggle_guide(record)).pack(side="right")


def _delete_bookmark(record):
    """Ask, then remove the bookmark from disk.

    Asked because it is the one button here that destroys something, and the
    thing it destroys cannot be taken again - the patch is findable, the
    reading of what was on it is not.
    """
    index = record.get("location_index")
    what = f"loc {index}" if index is not None else "this bookmark"
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
    _reload()


def _reload():
    """Read the folder again and redraw the rows.

    Off disk rather than off the list in hand: the list is what was there when
    the view opened, and after a delete that is exactly what it is not.
    """
    if not _body:
        return
    window, system, body, _records = _body
    records = cards.by_body(system).get(body, [])
    # Stays open with nothing on it. Every row in the list opens its body now,
    # so a body with no bookmarks is a page like any other - it still says what
    # the ground pays - and being thrown back to the list on the last delete
    # would be the odd one out.
    _bookmarks_view(window, system, body, records)


def _toggle_guide(record):
    """Start the arrow, or take it down, then redraw the rows.

    Redrawn because the button that was pressed is not the only one that
    changes: starting on a second bookmark has to turn the first one's Stop
    back into Guide.
    """
    if overlay.guiding(record):
        overlay.stop()
    elif overlay.start(_window, record, on_stop=_refresh) is None:
        # No arrow to be had here - it said why in the log. The row stays as
        # it was rather than offering a Stop for something that never started.
        logger.info("scan: no overlay, the bookmark list is unchanged")
    _refresh()


def _refresh():
    """Draw the bookmark rows again, if they are still what the window holds.

    The overlay calls this when it closes itself, which can be minutes after
    the press and with the window long since gone or moved on to another body.
    """
    if not _body or _window is None or not _window.winfo_exists():
        return
    _bookmarks_view(*_body)


def _bookmark_line(record, status):
    """Location, material, rigs, how far away - fixed-width, so the numbers of
    one row sit under the numbers of the next.

    Distance rather than the heading the bookmark was made on: the question on
    this page is which of these to drive to, and a compass bearing recorded
    once, from wherever the SRV happened to be standing, does not answer it.
    The heading is still on the dim line under the row.
    """
    index = record.get("location_index")
    rigs = record.get("rigs")
    return _columns(f"loc {index}" if index is not None else "loc ?",
                    record.get("commodity") or "unknown",
                    f"{rigs} rigs" if rigs is not None else "-",
                    _away(record, status))


def _away(record, status):
    """How far the patch is from where the ship or SRV is standing, or "-".

    "-" is every case the overlay would have no arrow for: another body,
    supercruise, or too high up for the game to give coordinates.
    """
    metres = guide.fix(status, record).get("distance_m")
    return guide.metres(metres) if metres is not None else "-"


def _bookmark_detail(record):
    """Where and when, dim, under the patch.

    The coordinates carry all six decimals the game gave: they are the one
    thing here that cannot be worked out again afterwards.
    """
    marked = str(record.get("marked_at") or "").split(".")[0].replace("T", " ")
    depleted = str(record.get("depleted_at") or "").split("+")[0].replace("T", " ")
    heading = record.get("heading")
    return "  ".join(part for part in (_coords(record), marked,
                                       f"{heading}°" if heading is not None else "",
                                       f"depleted {depleted}" if depleted else "",
                                       _deposit_text(record)) if part)


def _deposit_text(record):
    """'High amount · Low density · ≈ 620-1,200 t left', or '' for a bookmark
    made without the HUD readings. The range needs rigs and Amount; Density
    sets how many tons a rig holds, and without it the range is wider - see
    rs_core/deposit.py. A marked-depleted bookmark says nothing here: the date
    before it already does."""
    if record.get("depleted_at"):
        return ""
    density, amount = record.get("density"), record.get("amount")
    parts = [f"{amount} amount" if amount else "",
             f"{density} density" if density else "",
             deposit.describe(record.get("rigs"), amount, density)]
    return " · ".join(part for part in parts if part)


def _coords(record):
    lat, lon = record.get("latitude"), record.get("longitude")
    if lat is None or lon is None:
        return ""
    return f"{float(lat):.6f} / {float(lon):.6f}"


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


def _button(parent, text, command=None, active=ACCENT):
    """The window has no buttons anywhere else, so this is the style.

    Without a command the button is disabled rather than silently dead: a
    button that does nothing when pressed reads as a bug, and a greyed one
    reads as not finished. `active` is what it turns under the pointer - the
    one button that destroys something says so there rather than by sitting in
    red all the time.
    """
    return tk.Button(parent, text=text, command=command,
                     bg=PANEL, fg=FG, activebackground=PANEL,
                     activeforeground=active, disabledforeground=DIM,
                     relief="solid", borderwidth=1, highlightthickness=0,
                     padx=8, pady=0, font=("Segoe UI", 8),
                     cursor="hand2" if command else "arrow",
                     state="normal" if command else "disabled")


def _shorten(found, system):
    """Drop the system name from each body. It is in the title and the header,
    and repeating it on every row pushed the distance and the location count
    off the right edge."""
    prefix = (system or "") + " "
    out = []
    for body in found:
        row = dict(body)
        name = body["name"]
        row["short"] = name[len(prefix):] if name.startswith(prefix) else name
        out.append(row)
    return out


def _body_line(body):
    """One body under the headings: body, distance, locations, volcanism.

    Ragged columns were the thing that made the list hard to read - every row
    was the same weight of monospace and the numbers never lined up, so there
    was nothing for the eye to run down. Right-aligned numbers give it two.

    """
    name = (body.get("short") or body["name"])[:NAME_WIDTH]

    distance = body.get("distance")
    where = f"{distance:,.0f} Ls" if distance is not None else "-"

    locations = body.get("locations")
    counted = f"{locations} loc" if locations is not None else "unprobed"

    return _body_columns(name, where, counted, _volcanism(body))


def _body_columns(name, distance, locations, volcanism):
    """The one place the body list's column widths live, so the header cannot
    drift away from the rows it names."""
    return f"{name.ljust(NAME_WIDTH)} {distance:>10} {locations:>9}  {volcanism}"


def _table_header(parent, text):
    """The column names of one table, over the rows they name.

    The bookmark and map tables are one table each and it goes above the
    scrolling area, where it cannot scroll away. The body list is one table
    per ground, so each of them gets its own - see _group.
    """
    tk.Label(parent, text="   " + text, bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 9)).pack(fill="x")
    tk.Frame(parent, bg=palette.RULE, height=1).pack(fill="x", pady=(2, 4))


def _volcanism(body):
    """What kind of volcanism and how much of it - "major metallic magma".

    Cut to major/minor before, on the grounds that the heading above already
    said the kind. It does on the magma grounds, whose name is the volcanism.
    It does not on an icy, rocky-ice or metal-rich body, where the heading is
    the body class and what it spits out is the thing that decides whether it
    is worth landing on.
    """
    words = " ".join((body.get("volcanism") or "").lower().split())
    # The journal's own suffix - "major rocky magma volcanism". The column is
    # called Volcanism; it does not need saying twice on every row.
    if words.endswith(" volcanism"):
        words = words[:-len(" volcanism")]
    return words or "-"


def _footer(parent, sheet, wrap):
    if sheet.loaded:
        text = (f"Rates from every mining location read so far, {sheet.generated}. "
                "Where to prospect, not what you will find.")
    else:
        text = ("mining_sheet.json is missing, so only the body types are "
                "shown. Reinstall the plugin, or drop the file back beside "
                "load.py.")
    note = tk.Label(parent, text=text, bg=BG, fg=DIM, justify="left",
                    anchor="w", font=("Segoe UI", 8))
    note.pack(side="top", fill="x", pady=(8, 0))
    wrap(note)


class _Wrapper:
    """Wraps labels at the width of the thing that actually knows it.

    A frame inside a canvas grows to fit its widest child, so asking the frame
    how wide it is gets the label's own width back and nothing ever wraps -
    it just ran off the right edge instead. The canvas is clipped to the
    window, so it is the one to ask, and it says so again on every resize.
    """

    def __init__(self, source, margin=0):
        self.labels = []
        self.margin = margin
        self.width = 0
        self.source = source
        source.bind("<Configure>", self._resize, add="+")

    def __call__(self, label):
        self.labels.append(label)
        if self.width:
            label.config(wraplength=self.width)
        return label

    def _resize(self, event):
        # Only the widget this was bound to. A child's bindtags carry its
        # toplevel, so a wrapper on the window hears every widget inside it -
        # including the label it wraps, whose own width then set the
        # wraplength, which changed the label's height, which was another
        # Configure. The footer flipped between one line and two forever, and
        # the list under it jumped by the difference.
        if event.widget is not self.source:
            return
        if event.width <= 80:
            return
        self.width = event.width - self.margin
        # A view this window has replaced leaves its labels destroyed and this
        # binding behind, and configuring a destroyed widget raises.
        self.labels = [label for label in self.labels if label.winfo_exists()]
        for label in self.labels:
            label.config(wraplength=self.width)


def _scrollable(parent):
    """A canvas with a frame in it, because Tk has no scrolling frame.

    Returns the inner frame. Bodies in a well-scanned system run past any
    sensible window height, and a list you cannot reach the bottom of is worse
    than no list.
    """
    # Own container: side="left" and side="right" only mean "left and right of
    # this box". Packed straight into the parent they claimed the whole window
    # and the footer ended up beside the list rather than under it.
    box = tk.Frame(parent, bg=BG)
    box.pack(side="top", fill="both", expand=True)
    canvas = tk.Canvas(box, bg=BG, highlightthickness=0)
    bar = tk.Scrollbar(box, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=BG)

    inner.bind("<Configure>",
               lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfig(window, width=event.width))
    canvas.configure(yscrollcommand=bar.set)

    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    # Bound to the canvas, not to the window: an unbound wheel scrolls whatever
    # EDMC had focused, which is the panel behind this.
    canvas.bind_all("<MouseWheel>",
                    lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    canvas.bind("<Destroy>", lambda event: canvas.unbind_all("<MouseWheel>"))
    # 24px off the canvas width: the rows are indented three spaces and a
    # wrapped line that touches the scrollbar looks like a bug.
    return inner, _Wrapper(canvas, margin=24)
