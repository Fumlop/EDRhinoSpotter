"""The RhinoScan window: what is worth landing on, here, right now.

One row per landable body, grouped by what kind of body it is, with the
materials that kind of body has been found to hold underneath. The body list
comes from the journal; the percentages come from ground_rules.json, which
ships with the plugin. Neither needs the network.

The window is deliberately read-only and disposable. Nothing is saved from it,
so pressing the button twice costs nothing and the card flow is untouched.
"""

import os
import pathlib
import tkinter as tk
import webbrowser
from tkinter import font as tkfont, messagebox

from rs_core import cards, grounds, palette
from rs_core.logging import logger
from rs_ui import overlay

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
ACCENT = palette.ACCENT
GOOD = palette.GOOD
WARN = palette.WARN

_window = None           # only ever one, so the button cannot bury the panel
_scan = None             # what show() was last given, so Back can rebuild
_body = None             # the bookmark view's own arguments, for the same reason


def is_open():
    return _window is not None and bool(_window.winfo_exists())


def show(parent, register, sheet, focus=None, variable=None, materials=()):
    """Open the window, or raise the one already open.

    `focus` is one material. Given one, only the grounds that have ever
    carried it are listed, and it leads every material line whatever its rate
    - the question has changed from "what is here" to "where is the jadeite",
    and a ground that answers it at 4% still answers it.

    `variable` is the panel's own material StringVar, not a copy. The picker
    under the system name writes to it, so choosing here is the same act as
    choosing down in the panel and the two can never disagree. Watching that
    variable is the panel's job - one watcher, added once, rather than another
    one on every open.
    """
    global _window, _scan

    if _window is not None and _window.winfo_exists():
        _window.destroy()

    logger.debug(f"scan: open, system={register.system!r} focus={focus!r}")
    _window = tk.Toplevel(parent)
    _window.configure(bg=BG)
    # Debug only, and only on the window itself: whatever takes it away, this
    # is the line that names it. A window that vanishes with no Python frame
    # behind it is the one thing the stack cannot be asked about afterwards.
    _window.bind("<Destroy>", _log_destroy, add="+")
    _scan = (register, sheet, focus, variable, materials)
    _scan_view(_window)
    return _window


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
    register, sheet, focus, variable, materials = _scan
    logger.debug("scan: building the body list")
    _clear(window)
    window.title(f"RhinoScan - {register.system or 'unknown system'}"
                 + (f" - {focus}" if focus else ""))

    outer = tk.Frame(window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    _header(outer, register, sheet, focus, variable, materials)

    marked = cards.by_body(register.system) if register.system else {}
    listing, wrap = _scrollable(outer)
    groups = register.by_ground()
    # Prose is excluded from the width measurement below - it fits whatever it
    # is given. The material lines are not: they are the widest real content,
    # and a window narrower than one of them wraps a list that should be a row.
    prose = []
    if focus:
        groups = [(ground, found) for ground, found in groups
                  if sheet.rate(ground, focus) is not None]
    if not groups:
        prose.append(wrap(_empty(listing, register, focus)))
    else:
        for ground, found in groups:
            _group(listing, ground, _shorten(found, register.system), sheet, wrap,
                   focus, marked)

    _footer(outer, sheet, _Wrapper(window, margin=40))
    _fit(window, listing, prose)


# What the window may grow to before it starts scrolling instead. Wide enough
# for four materials on one line and a body row beside them; tall enough for a
# well-scanned system without covering the whole screen.
MAX_WIDTH = 900
MAX_HEIGHT = 780
OUTER_PAD = 14
SCROLLBAR = 18
# The three spaces every body row starts with.
INDENT = 24
# Header, the two lines above the list, and the footer under it. Generous on
# purpose: the footer wraps to two lines in a narrow window, and a height that
# is a little too large costs empty space while one that is too small eats the
# footer.
CHROME = 200


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
    content = (_measure(_lines(listing), wrapped) + extra
               + SCROLLBAR + 2 * OUTER_PAD + INDENT)
    width = min(max(content, 420), MAX_WIDTH)
    wanted = max(window.winfo_reqheight(), listing.winfo_reqheight() + CHROME)
    height = min(max(wanted, 260), MAX_HEIGHT)
    logger.debug(f"scan: fit to {width}x{height}")
    window.geometry(f"{width}x{height}")
    window.minsize(480, 240)


def _header(parent, register, sheet, focus=None, variable=None, materials=()):
    tk.Label(parent, text=register.system or "no system yet", bg=BG, fg=FG,
             font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")

    if variable is not None and materials:
        _picker(parent, variable, materials)

    count = len(register)
    line = f"{count} landable {'body' if count == 1 else 'bodies'} scanned"
    if not sheet.loaded:
        line += "  -  no ground_rules.json, types only"
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
        action = "FSS the system, or the planet you are heading for"
        why = ("The honk finds the bodies. It does not describe them, and only "
               "a body the FSS has resolved carries the type this reads. "
               "Flying in works too - the auto-scan sweeps the near ones.")
    else:
        action = "Waiting for the journal"
        why = ("Jump somewhere, or restart EDMC if it started while you were "
               "already docked.")

    tk.Label(parent, text=action, bg=BG, fg=ACCENT, anchor="w",
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
    tk.Label(head, text=grounds.label(ground), bg=BG, fg=ACCENT,
             font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left")
    tk.Label(head, text=f"{len(found)} of them", bg=BG, fg=DIM,
             font=("Segoe UI", 9), anchor="w").pack(side="left", padx=8)

    materials = sheet.materials(ground, limit=TOP_MATERIALS, minimum=MIN_PCT)
    if focus:
        # The chosen material leads, whatever its rate, and in the accent
        # colour so it is not read as one of the others. A ground listed
        # because it carries jadeite has to say what it carries it at, even
        # when three likelier things sit under it.
        rate = sheet.rate(ground, focus)
        tk.Label(block, text=f"{focus} {rate}%", bg=BG, fg=ACCENT, anchor="w",
                 font=("Consolas", 10, "bold")).pack(fill="x", pady=(2, 0))
        materials = [row for row in materials
                     if row["material"].lower() != focus.lower()][:TOP_MATERIALS - 1]
    if materials:
        # Separated, not just spaced: "Olivine 56.1%  Monazite 45.6%" reads as
        # one run of words, and the eye has to find the pairs itself.
        text = "   ·   ".join(f"{row['material']} {row['pct']}%" for row in materials)
        line = tk.Label(block, text=text, bg=BG, fg=GOOD, anchor="w",
                        font=("Consolas", 9), justify="left")
        line.pack(fill="x", pady=(1, 5))
        wrap(line)
    elif sheet.loaded:
        tk.Label(block, text="nothing measured on this ground yet", bg=BG, fg=WARN,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x")

    for body in found:
        # Unprobed bodies are dimmed rather than dropped. They are the right
        # ground, but nobody has counted them, so they are where you go once
        # the counted ones are worked out.
        probed = body.get("locations") is not None
        row = tk.Frame(block, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="   " + _body_line(body), bg=BG,
                 fg=FG if probed else DIM, anchor="w",
                 font=("Consolas", 9)).pack(side="left")
        _cards_link(row, (marked or {}).get(body["name"]))


def _cards_link(parent, records):
    """"2 bookmarks" behind a body you have already marked, opening the list.

    Only on bodies that have one. A count of zero on every other row would be
    nine pieces of nothing in a ten-body system, and the useful signal here is
    "you have been here before" - which is only worth saying when true.
    """
    if not records:
        return
    count = len(records)
    label = tk.Label(parent, text=f"  {count} bookmark{'' if count == 1 else 's'} ›",
                     bg=BG, fg=ACCENT, anchor="w", cursor="hand2",
                     font=("Consolas", 9))
    label.pack(side="left")
    system = records[0].get("system")
    body = records[0].get("planet_name")
    label.bind("<Button-1>",
               lambda event: _bookmarks_view(label.winfo_toplevel(), system, body, records))


# The three buttons on every bookmark row. Buttons are not labels, so the width
# measurement cannot see them and the window would open exactly that much too
# narrow - and a row too narrow does not wrap, it drops what is packed right.
BUTTONS = 200


def _bookmarks_view(window, system, body, records):
    """The bookmarks of one body, in the window the body list was in.

    The same window on purpose: this is a step into the row that was clicked,
    not a second thing on the screen, and Back is the way out of it. It was a
    page in the browser, which meant leaving the game to read three numbers.
    """
    global _body
    logger.debug(f"scan: building the bookmarks of {body}, {len(records)} of them")
    _body = (window, system, body, records)
    _clear(window)
    window.title(f"RhinoScan - {body} - bookmarks")

    outer = tk.Frame(window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    back = tk.Frame(outer, bg=BG)
    back.pack(fill="x", pady=(0, 6))
    _button(back, "‹ Back", lambda: _scan_view(window)).pack(side="left")

    tk.Label(outer, text=body, bg=BG, fg=FG, anchor="w",
             font=("Segoe UI", 15, "bold")).pack(fill="x")
    count = len(records)
    tk.Label(outer, text=f"{system or ''}  -  {count} bookmark{'' if count == 1 else 's'}",
             bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(0, 10))

    _column_header(outer)
    listing, _ = _scrollable(outer)
    for record in cards.ordered(records):
        _bookmark_row(listing, record)

    note = tk.Label(outer, text="Guide puts an arrow over the game, top middle - "
                                "borderless or windowed only. Card opens the PNG.",
                    bg=BG, fg=DIM, anchor="w", justify="left",
                    font=("Segoe UI", 8))
    note.pack(side="top", fill="x", pady=(8, 0))
    _Wrapper(window, margin=40)(note)
    _fit(window, listing, extra=BUTTONS)


def _column_header(parent):
    """The names of the four columns, above the list rather than in it.

    Above because the list scrolls: a header that scrolls away is a header you
    have to scroll back for. It names the top line of a row only - the dim
    line under each one is position and time, which need no naming.
    """
    tk.Label(parent, text="   " + _columns("LOC", "MATERIAL", "RIGS", "HDG"),
             bg=BG, fg=DIM, anchor="w", font=("Consolas", 9)).pack(fill="x")
    tk.Frame(parent, bg=palette.RULE, height=1).pack(fill="x", pady=(2, 4))


def _columns(loc, material, rigs, heading):
    """The one place the column widths live, so the header cannot drift away
    from the rows it names."""
    return f"{loc.ljust(7)} {material[:22].ljust(22)} {rigs.rjust(7)} {heading.rjust(5)}"


def _bookmark_row(parent, record):
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
    tk.Label(head, text="   " + _bookmark_line(record), bg=BG, fg=FG, anchor="w",
             font=("Consolas", 9)).pack(side="left")
    # Card first: side="right" packs from the edge inwards, and Guide is the
    # one that belongs beside the row rather than at the very end.
    path = record.get("path")
    # Clear of the scrollbar on the right, which the row runs up against.
    _button(head, "Delete", lambda: _delete_bookmark(record),
            active=palette.ALERT).pack(side="right", padx=(4, 6))
    _button(head, "Card", (lambda: _open_card(path)) if path else None).pack(
        side="right", padx=(4, 0))
    _guide_button(head, record)

    tk.Label(row, text="   " + _bookmark_detail(record), bg=BG, fg=DIM, anchor="w",
             font=("Consolas", 8)).pack(fill="x")


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
    """Ask, then remove the card and its sidecar from disk.

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
            + "The card and its sidecar go from disk.",
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
    the view opened, and after a delete that is exactly what it is not. An
    empty body goes back to the scan, because a page of nothing is not a page.
    """
    if not _body:
        return
    window, system, body, _records = _body
    records = cards.by_body(system).get(body, [])
    if records:
        _bookmarks_view(window, system, body, records)
    else:
        _scan_view(window)


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


def _bookmark_line(record):
    """Location, material, rigs, heading - fixed-width, so the numbers of one
    row sit under the numbers of the next."""
    index = record.get("location_index")
    rigs = record.get("rigs")
    heading = record.get("heading")
    return _columns(f"loc {index}" if index is not None else "loc ?",
                    record.get("commodity") or "unknown",
                    f"{rigs} rigs" if rigs is not None else "-",
                    f"{heading}°" if heading is not None else "-")


def _bookmark_detail(record):
    """Where and when, dim, under the patch.

    The coordinates carry all six decimals the game gave: they are the one
    thing here that cannot be worked out again afterwards.
    """
    marked = str(record.get("marked_at") or "").split(".")[0].replace("T", " ")
    return "  ".join(part for part in (_coords(record), marked) if part)


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
    """One body as fixed-width columns: name, distance, locations, strength.

    Ragged columns were the thing that made the list hard to read - every row
    was the same weight of monospace and the numbers never lined up, so there
    was nothing for the eye to run down. Right-aligned numbers give it two.

    The volcanism is cut to "major" or "minor". What kind it is stands in the
    heading above, in bigger type, once instead of ten times.
    """
    name = (body.get("short") or body["name"])[:NAME_WIDTH].ljust(NAME_WIDTH)

    distance = body.get("distance")
    where = f"{distance:,.0f} Ls" if distance is not None else "-"

    locations = body.get("locations")
    counted = f"{locations} loc" if locations is not None else "unprobed"

    return f"{name} {where:>10} {counted:>9}  {_strength(body)}"


def _strength(body):
    """How much of it there is, from the volcanism string.

    The game says "major metallic magma" and "minor metallic magma"; the
    heading already said metallic magma. Only major or minor is news here.
    """
    volcanism = (body.get("volcanism") or "").lower()
    for word in ("major", "minor"):
        if word in volcanism:
            return word
    return ""


def _footer(parent, sheet, wrap):
    if sheet.loaded:
        text = (f"Rates from every mining location read so far, {sheet.generated}. "
                "Where to prospect, not what you will find.")
    else:
        text = ("ground_rules.json is missing, so only the body types are "
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
