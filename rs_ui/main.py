"""The panel EDMC draws, and the state behind it.

Two things live here and nothing else does: the widgets, and the handful of
variables that only make sense while a window is open. Everything that can be
answered without a screen is in rs_core, which is why rs_tests can run it.

Threads: the card render and the update check both run off the UI thread and
come back through _on_ui. Tk is not thread-safe, and a widget written from a
worker fails minutes later somewhere unrelated.
"""

import os
import subprocess
import threading
import tkinter as tk

from rs_core import bodies, grounds, palette, screenshots, spotcard, spotmark, store, update
from rs_core.logging import logger
from rs_ui import scan

try:
    from theme import theme
except ImportError:      # running outside EDMC
    theme = None

_system = ""
_cmdr = None
_last_index = None       # the location the last press saw, for the sidecar
_card_token = 0          # only the newest render may write to the status line
_body_names = {}         # BodyID -> name, so a targeted location can be placed

_register = bodies.Register(on_change=store.save, on_arrive=store.load)
_sheet = None            # rs_core.grounds.Sheet, read once at startup

_frame = None
_status = None
_done = None             # "completed" beside the button, once a card is on disk
_scan_count = None       # how many landable bodies the current system has
# What the dropdown says before anything is picked. A real string rather than
# an empty one: an OptionMenu with "" in it draws as a blank sunken box with a
# marker floating in it, which reads as a broken text field.
NO_MATERIAL = "select material"
# Picking one filters the scan window to the grounds that carry it. "All" is
# how you get back, and it sits directly under the placeholder rather than in
# the alphabet with the materials - it is not one of them.
ALL_MATERIALS = "All"

_card_button = None      # Create Card, until there is an update to install
_loc = None              # tk.StringVar - mining location index
_rigs = None             # tk.StringVar - rigs on the patch
_material = None         # tk.StringVar - the material this spot is mined for


def start(plugin_dir):
    global _sheet
    _sheet = grounds.Sheet()
    if not _sheet.loaded:
        logger.warning(f"no ground_rules.json: {_sheet.error}")
    return "RhinoSpotter"


def build(parent):
    global _frame, _status, _done, _scan_count, _card_button, _loc, _rigs, _material

    _frame = tk.Frame(parent)
    _frame.columnconfigure(1, weight=1)

    tk.Label(_frame, text=f"RhinoSpotter {update.RUNNING}", anchor="w").grid(
        row=0, column=0, sticky="w", padx=2, pady=(4, 2))
    link = _folder_link(_frame)
    link.grid(row=0, column=1, sticky="w", padx=2, pady=(4, 2))

    # Up here with the system-level things, not down beside the button. How
    # many bodies are in this system is true before anyone presses anything,
    # and it was the only line in the panel that moved on its own.
    _scan_count = tk.Label(_frame, text="", anchor="e", fg=palette.MUTED)
    _scan_count.grid(row=0, column=2, columnspan=2, sticky="e", padx=2, pady=(4, 2))

    # Location and Rigs are both four characters wide, so they share a row and
    # set how far the panel runs. Material goes underneath and stretches to the
    # same right edge - the names are long enough that a narrow dropdown cut
    # "Low Temp Diamonds" in half.
    _loc = tk.StringVar(value="")
    _rigs = tk.StringVar(value="")
    tk.Label(_frame, text="Location", anchor="w").grid(row=1, column=0, sticky="w", padx=2)
    tk.Entry(_frame, textvariable=_loc, width=4).grid(row=1, column=1, sticky="w", padx=2)
    tk.Label(_frame, text="Rigs", anchor="w").grid(row=1, column=2, sticky="e", padx=2)
    tk.Spinbox(_frame, from_=0, to=12, textvariable=_rigs, width=4).grid(
        row=1, column=3, sticky="w", padx=2)

    _material = tk.StringVar(value=NO_MATERIAL)
    tk.Label(_frame, text="Material", anchor="w").grid(row=2, column=0, sticky="w", padx=2)
    _menu = tk.OptionMenu(_frame, _material, NO_MATERIAL, ALL_MATERIALS,
                          *spotmark.MATERIALS)
    _style_menu(_menu)
    _menu.grid(row=2, column=1, columnspan=3, sticky="we", padx=2)

    # Own frame: column 1 stretches, and the buttons have to sit against each
    # other rather than spread to the far edge of the panel. Both are one
    # press with no confirmation, so they get a gap between them.
    row = tk.Frame(_frame)
    row.grid(row=3, column=0, columnspan=4, sticky="w", padx=2, pady=(4, 2))
    _card_button = tk.Button(row, text="Create Card", width=13, command=make_card)
    _card_button.pack(side="left")
    _done = tk.Label(row, text="", anchor="w")
    _done.pack(side="left", padx=(8, 0))
    tk.Button(row, text="RhinoScan", width=13, command=open_scan).pack(side="left", padx=(16, 0))

    # The one thing RhinoScan cannot do for you, and the thing everyone gets
    # wrong first: the honk finds the bodies, it does not describe them. Only
    # a resolved body carries PlanetClass and Volcanism, which is all this
    # reads. Said here, before you press the button and wonder.
    tk.Label(_frame, text="FSS unknown systems", anchor="w",
             fg=palette.MUTED).grid(row=4, column=0, columnspan=4,
                                    sticky="w", padx=2, pady=(0, 2))

    _status = tk.Label(_frame, text="", anchor="w", wraplength=320, justify="left")
    _status.grid(row=5, column=0, columnspan=4, sticky="w", padx=2, pady=(2, 4))

    if theme:
        theme.update(_frame)
    # After the theme, which paints every label the same - the link has to stay
    # visibly a link.
    link.config(fg=palette.ACCENT)

    # Test mode fills the register before the panel exists, and EDMC may also
    # start mid-session with a system already tracked. Either way the count
    # beside RhinoScan has to say so without waiting for the next journal line.
    # One watcher for the whole session. The picker in the scan window writes
    # to this same variable, so this fires for either of them.
    _material.trace_add("write", _on_material_changed)

    _refresh_scan_count()
    update.check_async(_on_update_checked)
    return _frame


def _style_menu(menu):
    """Make an OptionMenu look like the rest of the panel.

    Tk gives it a two-pixel raised border, centred text and a fat indicator -
    next to EDMC's flat entry fields it looked like a different toolkit. The
    menu it drops down is a separate widget and has to be told the same
    things.
    """
    # A solid one-pixel border, so it sits beside the Location entry as the
    # same kind of thing. Tk gives a Menubutton a two-pixel raised border and
    # centred text by default, which next to EDMC's flat fields looked like a
    # different toolkit.
    #
    # The indicator stays on. Writing a caret into the text instead does
    # nothing - an OptionMenu binds textvariable, and that wins over text.
    menu.config(relief="solid", borderwidth=1, highlightthickness=0,
                anchor="w", padx=6, pady=1, indicatoron=True)
    menu["menu"].config(borderwidth=1, activeborderwidth=0, tearoff=False)


def _on_ui(function, *args):
    """Run something on the UI thread, or drop it.

    Every worker in here comes back through this. `after` is how you get from
    a thread to Tk, and it raises if the mainloop has gone - which is exactly
    what happens when EDMC is closing while an update check is still in
    flight. A daemon thread throwing a traceback into the log on the way out
    is noise, and there is nothing left to update anyway.
    """
    if not _frame:
        return
    try:
        _frame.after(0, function, *args)
    except (RuntimeError, tk.TclError):
        pass


def _folder_link(parent):
    """The cards folder, one click away - a path you cannot open is a path you
    stop looking at."""
    label = tk.Label(parent, text="cards folder ↗", anchor="w", cursor="hand2")
    label.bind("<Button-1>", lambda event: open_cards())
    return label


def open_cards():
    """Explorer on the cards folder, made if this is the first time."""
    try:
        os.makedirs(spotcard.CARDS_ROOT, exist_ok=True)
        # startfile is Windows-only and EDMC is too, but a failure here must not
        # be the thing that eats a card.
        os.startfile(spotcard.CARDS_ROOT)          # noqa: S606
    except AttributeError:
        subprocess.Popen(["explorer", spotcard.CARDS_ROOT])
    except OSError as err:
        _set_status(f"cannot open {spotcard.CARDS_ROOT}: {err}")


def open_scan():
    """The RhinoScan window for the system the journal last named.

    The window gets the panel's own material variable, not a copy of its
    value: the picker it draws under the system name writes straight back
    here, so the two can never disagree about what is being shown.
    """
    if not _frame:
        return
    try:
        scan.show(_frame.winfo_toplevel(), _register, _sheet, _focus(),
                  variable=_material,
                  materials=(ALL_MATERIALS,) + tuple(spotmark.MATERIALS))
    except Exception as err:                       # a broken window must not
        logger.exception("RhinoScan failed")       # take the card flow with it
        _set_status(f"no scan window: {err}")


def _on_material_changed(*_):
    """Redraw the scan window for the material that was just picked.

    One watcher, added once when the panel is built. The filter changes which
    groups exist and how tall the window is, so it is drawn again rather than
    updated in place - it is a dozen labels.

    Deferred by one idle tick: the write happens while the menu that caused it
    is still on screen, and destroying that menu's parent from underneath it is
    how Tk is told to close a window in the middle of closing itself.
    """
    if _frame and scan.is_open():
        _frame.after_idle(open_scan)


def _focus():
    """The material the window should filter to, or None for everything."""
    chosen = _material.get() if _material else ""
    return None if chosen in ("", NO_MATERIAL, ALL_MATERIALS) else chosen


def journal_entry(cmdr, is_beta, system, station, entry, state):
    global _system, _cmdr

    if system:
        _system = system
    if cmdr:
        _cmdr = cmdr

    # Status.json names the destination body by id only, so the names have to
    # come from the journal, where half a dozen events carry both.
    body_id = entry.get("BodyID")
    body_name = entry.get("Body") or entry.get("BodyName")
    if body_id is not None and body_name:
        _body_names[body_id] = body_name

    # Arriving in a system scanned before fills the list straight from disk -
    # EDMC replays one journal file, and last week's honk is in an older one.
    # The register does that itself through on_arrive; this only redraws.
    if _register.track(entry, system=system):
        _refresh_scan_count()

    if entry.get("event") == "Screenshot":
        # Off the main thread: a 1080p bmp read plus a PNG write is long enough
        # to stutter the panel, and nothing here needs an answer.
        threading.Thread(target=_convert_shot,
                         args=(entry, _location(), dict(_body_names)),
                         daemon=True).start()


def make_card():
    """Mark where the ship is standing and render the card for it."""
    global _card_token, _last_index

    _set_done("")
    if _material.get() in ("", NO_MATERIAL, ALL_MATERIALS):
        _set_status("pick one material - a card names what you mined")
        return

    spot = spotmark.mark(spotmark.read_status(), system=_system, commander=_cmdr)
    _last_index = spot["location_index"]

    # A typed Loc wins: Status.json only knows the location while it is the
    # selected destination, and it is often deselected by the time you land.
    typed = _int(_loc.get())
    if typed is None and _last_index is not None:
        _loc.set(str(_last_index))
    else:
        spot["location_index"] = typed

    if not spotmark.on_surface(spot):
        _set_status(f"no coordinates in Status.json for "
                    f"{spot['planet_name'] or 'no body'} - are you on the surface?")
        return

    # Tk variables belong to the main thread - read them here, not in the worker.
    spot["commodity"] = _material.get()
    spot["rigs"] = _int(_rigs.get())

    _set_status("")
    _card_token += 1
    threading.Thread(target=_render_card, args=(spot, _card_token), daemon=True).start()


def _render_card(spot, token):
    """The file name is not worth reading - either the card is there or the
    reason it is not."""
    try:
        spotcard.render(spot)
        message = None
    except Exception as err:
        message = f"no card: {err}"
    _on_ui(_report, message, token)


def _report(message, token):
    """Stale renders stay quiet - a finished one must not label a running one."""
    if token != _card_token:
        return
    _set_status(message or "")
    _set_done("" if message else "completed")


def _on_update_checked(tag, newer):
    """Called on a worker thread - bounce to Tk before touching a widget."""
    _on_ui(_show_update, tag, newer)


def _show_update(tag, newer):
    """Create Card becomes the update, rather than a fourth button appearing.

    A permanent version button only made the panel wider, and a temporary one
    still widens it on the day it matters. The card can wait the thirty
    seconds: a release is rare, and the panel is two buttons either way.

    Offline or already current: nothing changes at all.
    """
    if not _card_button or not newer:
        return
    # "Update", not "Update v2.1.0": the tag would be the one string wider
    # than the button, and widening the panel is what this design avoids. The
    # version it is going to goes in the status line instead.
    _card_button.config(text="Update", fg=palette.WARN, command=_install_update)
    _set_status(f"{tag} is out")


def _install_update():
    """Fetch the release and put it in place. One press, no confirmation - the
    only thing it can cost is a restart."""
    if not _card_button:
        return
    _card_button.config(text="Updating...", state="disabled")
    _set_status(f"downloading from {update.RELEASES_PAGE}")
    update.install_async(_on_update_installed)


def _on_update_installed(ok, message):
    """Called on a worker thread - bounce to Tk before touching a widget."""
    _on_ui(_report_update, ok, message)


def _report_update(ok, message):
    _set_status(message)
    if not _card_button:
        return
    if ok:
        # The new code is on disk and the old code is what is running. Nothing
        # this button could do now would be the thing the commander expects.
        _card_button.config(text="Restart EDMC", state="disabled", fg=palette.GOOD)
    else:
        # Left pressable on purpose: a failed download is usually a retry.
        _card_button.config(text="Retry update", state="normal", fg=palette.ALERT)


def _refresh_scan_count():
    if not _scan_count:
        return
    count = len(_register)
    _scan_count.config(text=f"{count} landable" if count else "")


def _set_status(text):
    if _status:
        _status.config(text=text)


def _set_done(text):
    if _done:
        _done.config(text=text)


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _location():
    """The mining location this session believes it is on, for the sidecar."""
    typed = _int(_loc.get()) if _loc else None
    return typed if typed else _last_index


def _convert_shot(entry, mark_location, body_names):
    try:
        path = screenshots.convert(entry, mark_location, body_names)
        message = "shot: " + os.path.basename(path)
    except Exception as err:
        message = f"screenshot not saved: {err}"
    _on_ui(_set_status, message)
