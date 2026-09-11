"""The RhinoScan window: what is worth landing on, here, right now.

One row per landable body, grouped by what kind of body it is, with the
materials that kind of body has been found to hold underneath. The body list
comes from the journal; the percentages come from ground_rules.json, which
ships with the plugin. Neither needs the network.

The window is deliberately read-only and disposable. Nothing is saved from it,
so pressing the button twice costs nothing and the card flow is untouched.
"""

import tkinter as tk
from tkinter import font as tkfont

from rs_core import grounds, palette

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
    global _window

    if _window is not None and _window.winfo_exists():
        _window.destroy()

    _window = tk.Toplevel(parent)
    _window.title(f"RhinoScan - {register.system or 'unknown system'}"
                  + (f" - {focus}" if focus else ""))
    _window.configure(bg=BG)

    outer = tk.Frame(_window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    _header(outer, register, sheet, focus, variable, materials)

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
            _group(listing, ground, _shorten(found, register.system), sheet, wrap, focus)

    _footer(outer, sheet, _Wrapper(_window, margin=40))
    _fit(_window, listing, prose)
    return _window


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
    """
    widest = 0
    skip = set(skip)
    for label in labels:
        if label in skip:
            continue
        text = label.cget("text")
        if not text:
            continue
        metrics = tkfont.Font(font=label.cget("font"))
        for line in text.splitlines():
            widest = max(widest, metrics.measure(line))
    return widest


def _fit(window, listing, wrapped=()):
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
    content = _measure(_lines(listing), wrapped) + SCROLLBAR + 2 * OUTER_PAD + INDENT
    width = min(max(content, 420), MAX_WIDTH)
    wanted = max(window.winfo_reqheight(), listing.winfo_reqheight() + CHROME)
    height = min(max(wanted, 260), MAX_HEIGHT)
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

    picker = tk.OptionMenu(row, variable, *materials)
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


def _group(parent, ground, found, sheet, wrap, focus=None):
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
        tk.Label(block, text="   " + _body_line(body), bg=BG, fg=FG, anchor="w",
                 font=("Consolas", 9)).pack(fill="x")


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
        source.bind("<Configure>", self._resize, add="+")

    def __call__(self, label):
        self.labels.append(label)
        if self.width:
            label.config(wraplength=self.width)
        return label

    def _resize(self, event):
        if event.width <= 80:
            return
        self.width = event.width - self.margin
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
