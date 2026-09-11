"""The RhinoScan window: what is worth landing on, here, right now.

One row per landable body, grouped by what kind of body it is, with the
materials that kind of body has been found to hold underneath. The body list
comes from the journal; the percentages come from ground_rules.json, exported
from the EDIntel mining sheet. Neither needs the network.

The window is deliberately read-only and disposable. Nothing is saved from it,
so pressing the button twice costs nothing and the card flow is untouched.
"""

import tkinter as tk

from rs_core import grounds, palette

try:
    from theme import theme
except ImportError:      # running outside EDMC
    theme = None

# Four is what fits beside a body without the row wrapping, and the fifth
# material on rocky ground is already under 10%.
TOP_MATERIALS = 4
MIN_PCT = 2.0

BG = palette.BG
FG = palette.FG
DIM = palette.MUTED
ACCENT = palette.ACCENT
GOOD = palette.GOOD
WARN = palette.WARN

_window = None           # only ever one, so the button cannot bury the panel


def show(parent, register, sheet):
    """Open the window, or raise the one already open."""
    global _window

    if _window is not None and _window.winfo_exists():
        _window.destroy()

    _window = tk.Toplevel(parent)
    _window.title(f"RhinoScan - {register.system or 'unknown system'}")
    _window.configure(bg=BG)
    _window.geometry("620x560")

    outer = tk.Frame(_window, bg=BG)
    outer.pack(fill="both", expand=True, padx=14, pady=12)

    _header(outer, register, sheet)

    listing = _scrollable(outer)
    groups = register.by_ground()
    if not groups:
        _empty(listing, register)
    else:
        for ground, found in groups:
            _group(listing, ground, _shorten(found, register.system), sheet)

    _footer(outer, sheet)
    return _window


def _header(parent, register, sheet):
    tk.Label(parent, text=register.system or "no system yet", bg=BG, fg=FG,
             font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
    count = len(register)
    line = f"{count} landable {'body' if count == 1 else 'bodies'} scanned"
    if not sheet.loaded:
        line += "  -  no ground_rules.json, types only"
    tk.Label(parent, text=line, bg=BG, fg=DIM, anchor="w",
             font=("Segoe UI", 9)).pack(fill="x", pady=(0, 10))


def _empty(parent, register):
    text = ("Nothing scanned here yet. Honk the system - the discovery scan "
            "carries everything this needs."
            if register.system else
            "Waiting for the journal. Jump somewhere, or restart EDMC if you "
            "were already docked when it started.")
    tk.Label(parent, text=text, bg=BG, fg=DIM, wraplength=540, justify="left",
             anchor="w").pack(fill="x", pady=6)


def _group(parent, ground, found, sheet):
    """One body type, its bodies, and what that type has been found to hold."""
    block = tk.Frame(parent, bg=BG)
    block.pack(fill="x", pady=(0, 14))

    head = tk.Frame(block, bg=BG)
    head.pack(fill="x")
    tk.Label(head, text=grounds.label(ground), bg=BG, fg=ACCENT,
             font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left")
    tk.Label(head, text=f"{len(found)} of them", bg=BG, fg=DIM,
             font=("Segoe UI", 9), anchor="w").pack(side="left", padx=8)

    materials = sheet.materials(ground, limit=TOP_MATERIALS, minimum=MIN_PCT)
    if materials:
        # The sample size sits with the materials, not with the bodies: it
        # qualifies the percentages and nothing else on the row.
        text = "  ".join(f"{row['material']} {row['pct']}%" for row in materials)
        line = tk.Label(block, text=text, bg=BG, fg=GOOD, anchor="w",
                        font=("Consolas", 9), justify="left")
        line.pack(fill="x")
        _wrap_with(line, block)
        tk.Label(block, text=f"across {sheet.sample(ground)} locations read",
                 bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 8)).pack(fill="x")
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
    """One body: where it is, how probed it is, what its volcanism is.

    The location count comes from FSSBodySignals or SAASignalsFound. A body
    with none has not been counted rather than counted at zero, so it says so -
    "0 locations" reads as barren, which is the opposite of what it means.
    """
    distance = body.get('distance')
    parts = [body.get('short') or body['name']]
    if distance is not None:
        parts.append(f"{distance:,.0f} Ls")
    locations = body.get('locations')
    parts.append(f"{locations} loc" if locations is not None else "unprobed")
    volcanism = body.get('volcanism')
    if volcanism:
        parts.append(volcanism.replace(" volcanism", ""))
    return "  ".join(parts)


def _footer(parent, sheet):
    if sheet.loaded:
        text = (f"Rates from the EDIntel mining sheet, {sheet.generated}. "
                "What a location holds is in no game feed - this is where to "
                "prospect, not what you will find.")
    else:
        text = ("ground_rules.json is missing, so only the body types are "
                "shown. Export it from EDIntel: "
                "python scripts/export/rhinoscan_data.py")
    note = tk.Label(parent, text=text, bg=BG, fg=DIM, justify="left",
                    anchor="w", font=("Segoe UI", 8))
    note.pack(side="top", fill="x", pady=(8, 0))
    _wrap_with(note, parent)


def _wrap_with(label, container):
    """Wrap at whatever width the container actually has, now and after every
    resize. A fixed wraplength is a guess at the window size, and the window
    is resizable."""
    def resize(event):
        if event.width > 40:
            label.config(wraplength=event.width - 16)
    container.bind("<Configure>", resize, add="+")


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
    return inner
