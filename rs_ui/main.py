"""The panel EDMC draws, and the state behind it.

Two things live here and nothing else does: the widgets, and the handful of
variables that only make sense while a window is open. Everything that can be
answered without a screen is in rs_core, which is why rs_tests can run it.

Threads: the card render and the update check both run off the UI thread and
come back through _on_ui. Tk is not thread-safe, and a widget written from a
worker fails minutes later somewhere unrelated.
"""

import sqlite3
import threading
import tkinter as tk
from datetime import datetime, timezone

from rs_core import (bodies, cards, coverage, database, deposit, grounds, migrate, palette,
                     share, spansh, spotcard, spotmark, store, update, yields)
from rs_core.logging import logger
from rs_ui import clipboard, hotkey, minimap, scan

try:
    from theme import theme
except ImportError:      # running outside EDMC
    theme = None

_system = ""
_cmdr = None
_card_token = 0          # only the newest render may write to the status line

# One write per burst rather than one per body. A honk is forty-odd changes
# that all say the same file, and the last of them is the only one worth
# having - see store.Debounced for what a crash costs.
_writes = store.Debounced()
_register = bodies.Register(on_change=_writes, on_arrive=store.load)
_sheet = None            # rs_core.grounds.Sheet, read once at startup
# SystemAddress -> this session's Spansh state: "undiscovered", "asking" or
# "answered". Any entry means Spansh is not asked again this session.
_spansh = {}
_honked = {}             # SystemAddress -> the honk's BodyCount (stars and planets)
_spansh_known = {}       # SystemAddress -> stars and planets Spansh knows there
_all_found = set()       # SystemAddresses with FSSAllBodiesFound: nothing left to FSS
_prefilled = None        # the material MiningRefined last put in the dropdown
# Tons refined near a bookmark, counted into it. Written every yields.FLUSH_S
# and flushed when the SRV docks, on liftoff, at plugin_stop and before a
# Depleted mark closes a cycle.
_tally = yields.TALLY
# EDMC replays the journal file it is watching at startup, so MiningRefined
# arrives in bursts on load. Those tons were counted when they happened and
# have no Status.json position behind them now.
_started_at = None
_replayed = 0
_clip_seen = None        # the clipboard text _check_clipboard last looked at
_clip_sequence = None    # clipboard.sequence() at that look
_hint = None             # the line under the buttons: honk, or FSS when the honk brought nothing

_frame = None
_status = None
_done_after = None       # the pending return of the button to "Bookmark"
_scan_count = None       # how many landable bodies the current system has
# What the dropdown says before anything is picked. A real string rather than
# an empty one: an OptionMenu with "" in it draws as a blank sunken box with a
# marker floating in it, which reads as a broken text field.
NO_MATERIAL = "select material"
# The RhinoData picker's "everything" entry. Only that picker offers it: the
# panel's Material box names one deposit, and "All" is not a material to name
# it after. make_card and _prefill_material still test for it, because a
# session that ran an older version can have it in the box.
ALL_MATERIALS = "All"

_card_button = None      # Bookmark, until there is an update to install
_landed_after = None     # the pending look at whether we are on the ground
_poll_error = None       # the last failure the poll logged, so it logs each kind once
_update_after = None     # the pending hourly look for a new release
_loc = None              # tk.StringVar - mining location index
_rigs = None             # tk.StringVar - rigs on the patch
_material = None         # tk.StringVar - the material a new bookmark is named after
_filter = None           # tk.StringVar - the material RhinoData filters to
_density = None          # tk.StringVar - the deposit's HUD Density, or NOT_READ
_amount = None           # tk.StringVar - the deposit's HUD Amount, or NOT_READ
_search = None           # tk.StringVar - bookmark search text, not used yet
_menu = None             # the Material OptionMenu, refilled when the settings change
_offered = None          # (key, materials) - see _materials
SEARCH_SHOWN = False     # the Search row under Bookmark, off until search works
# Density and Amount before anything is picked. Not required: a bookmark without
# them is still a bookmark, it just cannot say how many tons are left.
NOT_READ = "-"


def start(plugin_dir):
    global _sheet, _started_at
    # Before anything reads the database: the JSON files of 4.1 go in once.
    try:
        migrate.run()
    except Exception:
        logger.exception("importing the old JSON files into the database failed - "
                         "the next start tries again")
    # The PNG texture set of 5.5.0 and older, where an install was unzipped
    # over the last one by hand.
    coverage.clear_old_textures()
    yields.regrow()
    _started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _sheet = grounds.Sheet()
    if not _sheet.loaded:
        logger.warning(f"no mining_sheet.json: {_sheet.error}")
    return "RhinoSpotter"


def build(parent):
    global _frame, _status, _scan_count, _card_button, _landed_after, _hint
    global _loc, _rigs, _material, _density, _amount, _search, _menu, _filter

    _frame = tk.Frame(parent)
    _frame.columnconfigure(1, weight=1)

    tk.Label(_frame, text=f"RhinoSpotter {update.RUNNING}", anchor="w").grid(
        row=0, column=0, sticky="w", padx=2, pady=(4, 2))

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
    # Ten is what a deposit can hold; the box used to go to twelve, which was
    # a number nobody can enter in the game.
    tk.Spinbox(_frame, from_=0, to=deposit.MAX_RIGS, textvariable=_rigs, width=4).grid(
        row=1, column=3, sticky="w", padx=2)

    _material = tk.StringVar(value=NO_MATERIAL)
    # The window's filter, not the panel's material. Separate variables: naming
    # the deposit under the ship and narrowing the system list are two
    # questions, and one control answering both meant mining gold refiltered
    # RhinoData to gold.
    _filter = tk.StringVar(value=ALL_MATERIALS)
    tk.Label(_frame, text="Material", anchor="w").grid(row=2, column=0, sticky="w", padx=2)
    _menu = tk.OptionMenu(_frame, _material, NO_MATERIAL, *_materials())
    _style_menu(_menu)
    _menu.grid(row=2, column=1, columnspan=3, sticky="we", padx=2)

    # What the HUD says about the targeted deposit. Neither is in the journal.
    # Rigs, Amount and Density give the bookmark a range of tons left: Density
    # sets how much a rig holds, Amount how much of it is still there - see
    # rs_core/deposit.py.
    # A row each, Amount over Density: the order the HUD lists them, top to
    # bottom. Side by side they were picked into each other's box, and each
    # label then sat against the far edge of the panel from its own menu.
    _density = tk.StringVar(value=NOT_READ)
    _amount = tk.StringVar(value=NOT_READ)
    tk.Label(_frame, text="Amount", anchor="w").grid(row=3, column=0, sticky="w", padx=2)
    amount_menu = tk.OptionMenu(_frame, _amount, NOT_READ, *deposit.AMOUNTS)
    _style_menu(amount_menu)
    amount_menu.grid(row=3, column=1, sticky="we", padx=2)
    tk.Label(_frame, text="Density", anchor="w").grid(row=4, column=0, sticky="w", padx=2)
    density_menu = tk.OptionMenu(_frame, _density, NOT_READ, *deposit.DENSITIES)
    _style_menu(density_menu)
    density_menu.grid(row=4, column=1, sticky="we", padx=2)

    # Own frame: column 1 stretches, and the buttons have to sit against each
    # other rather than spread to the far edge of the panel. Both are one
    # press with no confirmation, so they get a gap between them.
    row = tk.Frame(_frame)
    row.grid(row=5, column=0, columnspan=4, sticky="w", padx=2, pady=(4, 2))
    _card_button = tk.Button(row, text=CARD_TEXT, width=13, command=make_card)
    _card_button.pack(side="left")
    tk.Button(row, text="RhinoData", width=13, command=open_scan).pack(side="left", padx=(8, 0))

    # The place the bookmark search goes. Hidden until it does something.
    if SEARCH_SHOWN:
        _search = tk.StringVar(value="")
        tk.Label(_frame, text="Search", anchor="w").grid(row=6, column=0, sticky="w", padx=2)
        tk.Entry(_frame, textvariable=_search).grid(row=6, column=1, columnspan=3,
                                                    sticky="we", padx=2, pady=(0, 2))

    # What to do when the list is empty, said before you press the button and
    # wonder. The honk asks Spansh; only when that brings nothing does the FSS
    # have to describe the bodies. See _refresh_hint.
    _hint = tk.Label(_frame, text="", anchor="w", fg=palette.MUTED)
    _hint.grid(row=7, column=0, columnspan=4, sticky="w", padx=2, pady=(0, 2))

    _status = tk.Label(_frame, text="", anchor="w", wraplength=320, justify="left")
    _status.grid(row=8, column=0, columnspan=4, sticky="w", padx=2, pady=(2, 4))

    if theme:
        theme.update(_frame)

    # Test mode fills the register before the panel exists, and EDMC may also
    # start mid-session with a system already tracked. Either way the count
    # beside RhinoData has to say so without waiting for the next journal line.
    # One watcher for the whole session, on the filter only. The picker in the
    # scan window is the only other control that writes it.
    _filter.trace_add("write", _on_filter_changed)

    # Bookmark starts out grey and the poll turns it on, rather than the other
    # way round: EDMC usually starts while the commander is docked. Cancel
    # first: a second build would otherwise leave two chains polling forever.
    _card_button.config(state="disabled")
    _landed_after = _cancel_landed()
    _poll_landed()

    _refresh_scan_count()
    _check_updates()
    hotkey.start({hotkey.CENTER: lambda: _on_ui(minimap.center_here),
                  hotkey.BORDER: lambda: _on_ui(minimap.border_here),
                  hotkey.SIZE: lambda: _on_ui(minimap.bigger),
                  # The window is the only thing here that could not be
                  # reached without leaving the game: alt-tab, find EDMC,
                  # press the button. The key opens it where you are.
                  hotkey.SCAN: lambda: _on_ui(open_scan)})
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


def open_scan():
    """The RhinoData window for the system the journal last named, opened on
    the bookmarks of the body under the ship when there is one.

    Only on the first open: a window already up is redrawn where it stands.

    The window gets `_filter`, not `_material`: the picker it draws under the
    system name writes the filter, and the panel's Material box goes on saying
    what the next bookmark is called.
    """
    if not _frame:
        return
    logger.debug(f"open_scan: focus={_focus()!r}")
    try:
        scan.show(_frame.winfo_toplevel(), _register, _sheet, _focus(),
                  variable=_filter,
                  materials=(ALL_MATERIALS,) + _materials(),
                  here=spotmark.body_here(spotmark.read_status()))
    except Exception as err:                       # a broken window must not
        logger.exception("RhinoData failed")       # take the card flow with it
        _set_status(f"no scan window: {err}")


def _on_filter_changed(*_):
    """Redraw the scan window for the material the filter was just set to.

    The filter changes which groups exist and how tall the window is, so the
    view is drawn again rather than updated in place - it is a dozen labels.

    Deferred by one idle tick: the write happens while the menu that caused it
    is still on screen, and destroying that menu's parent from under it is
    what Tk refuses.
    """
    open_now = bool(_frame) and scan.is_open()
    logger.debug(f"filter changed to {_filter.get()!r}, "
                 f"scan open={open_now} - {'redrawing' if open_now else 'nothing to do'}")
    if open_now:
        _frame.after_idle(open_scan)


# How often Status.json is read to see whether Bookmark has anything to mark.
# One small file, and the answer changes at walking pace.
LANDED_POLL_MS = 1000


def _poll_landed():
    """Grey Bookmark out while there is nothing under the ship.

    Only while the button is still Bookmark. It doubles as the update button,
    and an update that is downloading has its own reasons for being disabled.
    """
    global _landed_after, _poll_error
    if not _frame or not _card_button:
        return
    # Rescheduled first, whatever happens below. This poll is what brings the
    # minimap back after an alt-tab and turns Bookmark on; rescheduled only at
    # the end, one raise anywhere above it stopped both until EDMC restarted,
    # and a Tk callback error never reaches EDMC's log to say so.
    _landed_after = _frame.after(LANDED_POLL_MS, _poll_landed)
    try:
        status = spotmark.read_status()
        if str(_card_button.cget("text")) == CARD_TEXT:
            ready = spotmark.on_ground(status)
            _card_button.config(state="normal" if ready else "disabled")
        # The same reading, so the minimap costs no second parse.
        minimap.update(_frame.winfo_toplevel(), status, _system, ids=_register.ids,
                       ground=_register.ground)
        _poll_error = None
    except Exception as err:
        # Once per kind of failure, not once a second.
        if repr(err) != _poll_error:
            logger.warning(f"landed poll failed, retrying every second: {err!r}", exc_info=True)
            _poll_error = repr(err)
    # Own try: a failing Status.json read must not stop the import.
    try:
        _check_clipboard()
    except Exception:
        logger.exception("clipboard import failed")


def _check_clipboard():
    """Import a RhinoData code on the clipboard, once per clipboard text.

    Skips codes this install shared (share.mine) and bookmarks already here
    (cards.nearby). Non-text clipboard content raises TclError: nothing to do.
    """
    global _clip_seen, _clip_sequence
    # Windows: the text is read only when the sequence number moved, so a
    # multi-MB copy elsewhere is not read and compared once a second.
    number = clipboard.sequence()
    if number is not None and number == _clip_sequence:
        return
    try:
        text = _frame.clipboard_get()
    except tk.TclError:
        return      # no text, or another program has it open: retried next poll
    _clip_sequence = number
    if text == _clip_seen:
        return
    _clip_seen = text
    if share.PREFIX not in text:
        return
    try:
        state, spot = share.take(text)
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not import a shared bookmark: {err}")
        _note(f"shared bookmark not imported: {err}")
        return
    if state == "imported":
        _note(f"imported {spot['commodity']} on {spot['planet_name']}")
        scan.refresh()
    elif state == "known":
        _note(f"shared {spot['commodity']} on {spot['planet_name']} is already bookmarked")


def _cancel_landed():
    if _landed_after and _frame:
        try:
            _frame.after_cancel(_landed_after)
        except (ValueError, tk.TclError):
            pass
    return None


def stop():
    """EDMC is closing. Drop the polls before the widgets go.

    The landed poll reschedules itself forever, so it is still pending at
    teardown by design; left alone it fires once against a frame that is no
    longer there.
    """
    global _landed_after, _done_after, _update_after
    _landed_after = _cancel_landed()
    _done_after = _cancel_done()
    if _update_after and _frame:
        try:
            _frame.after_cancel(_update_after)
        except (ValueError, tk.TclError):
            pass
    _update_after = None
    hotkey.stop()
    minimap.stop()
    # Last, and not through the timer: EDMC is going, and a scan waiting on a
    # two-second thread would go with it.
    _writes.flush()
    _tally.flush()
    if _tally.unplaced or _tally.byproduct or _tally.unread or _replayed:
        logger.info(f"mining: {_tally.unplaced} t refined near no bookmark, "
                    f"{_tally.byproduct} t by-product not counted, "
                    f"{_tally.unread} t with no Status.json reading, "
                    f"{_replayed} replayed lines skipped")
    # After every write, so the copy has them.
    database.backup()


def _materials():
    """What the Material dropdown and the RhinoData picker offer.

    The whole list when the settings tab says so. Otherwise the ones worth the
    trip - grounds.HIGH_VALUE_MIN - plus two kinds of exception that have to
    stay pickable however little they pay:

      every material already bookmarked, because cards.nearby() matches a
      second mark to the first one on the material's name. Drop the name and
      that bookmark can never be marked again: the re-mark lands beside it as
      a duplicate instead of refreshing its Amount and Density.

      whatever either control holds right now - _prefill_material puts a
      material in the box when it is being mined, and a value with no menu
      entry behind it cannot be chosen again once it is left.

    Kept until the bookmarks change, the switch moves or either control does:
    this reads the database, and the scan window asks on every redraw.
    """
    global _offered
    held = tuple(var.get() for var in (_material, _filter) if var is not None)
    key = (minimap.low_value_shown(), database.revision(), held)
    if _offered is not None and _offered[0] == key:
        return _offered[1]
    if key[0]:
        names = tuple(spotmark.MATERIALS)
    else:
        kept = set(_sheet.worth(spotmark.MATERIALS))
        marked = cards.materials_marked()
        names = tuple(name for name in spotmark.MATERIALS
                      if name in kept or name.lower() in marked or name in held)
    _offered = (key, names)
    return names


def _fill_menu():
    """Put _materials() in the dropdown, in place.

    Nothing is reset here. _materials() already carries whatever is in the box,
    so the pick survives a change of the switch rather than being thrown back
    to All by a settings dialog opened for some unrelated reason.
    """
    if _menu is None:
        return
    inner = _menu["menu"]
    inner.delete(0, "end")
    for name in (NO_MATERIAL,) + _materials():
        inner.add_command(label=name, command=lambda pick=name: _material.set(pick))


def prefs(parent):
    return minimap.prefs(parent)


def prefs_changed():
    minimap.prefs_changed()
    # The switch may have taken materials out of the list or put them back, and
    # _on_material_changed only fires when the picked one moves.
    _fill_menu()
    if _frame is not None and scan.is_open():
        _frame.after_idle(open_scan)


def _focus():
    """The material RhinoData filters to, or None for everything."""
    chosen = _filter.get() if _filter else ""
    return None if chosen in ("", NO_MATERIAL, ALL_MATERIALS) else chosen


def journal_entry(cmdr, is_beta, system, station, entry, state):
    global _system, _cmdr

    if system:
        _system = system
    if cmdr:
        _cmdr = cmdr

    minimap.srv_event(entry)

    # Landing or dropping the SRV fills Loc in. The nearest bookmark within 10 km
    # on this body says which location this is, and it was checked when it was made;
    # only without one does Touchdown's nearest-location guess stand in, which
    # names the wrong one when two locations are close.
    if entry.get("event") in ("Touchdown", "LaunchSRV") and _loc is not None:
        _fill_location(entry, system)
    elif spotmark.leaves_location(entry) and _loc is not None:
        _loc.set("")

    # 1 t into the bookmark of that material it was refined at, and the
    # material into the dropdown so the Bookmark made there is already filled.
    # Never over a material picked by hand: a by-product must not rename it.
    if entry.get("event") == "MiningRefined":
        _refined(entry, system)
    elif entry.get("event") in ("DockSRV", "Liftoff"):
        _tally.flush()

    # Arriving in a system scanned before fills the list straight from disk -
    # EDMC hands plugins only new journal lines, and last week's honk is gone.
    # The register does that itself through on_arrive; this only redraws.
    before = _register.system
    if _register.track(entry, system=system):
        _refresh_scan_count()
        # scan.show() would raise the window over the game on every jump.
        if _register.system != before:
            yields.regrow()     # a session can outlast REGEN_DAYS
            scan.arrived()

    # The honk: ask Spansh for the bodies the journal will not describe until
    # they are scanned - once a session per system, see spansh.should_ask. Off
    # the UI thread; what comes back only fills gaps.
    fresh = spansh.undiscovered(entry)
    if fresh:
        _spansh.setdefault(fresh, "undiscovered")
    event = entry.get("event")
    if event == "FSSDiscoveryScan" and entry.get("SystemAddress"):
        _honked[entry["SystemAddress"]] = entry.get("BodyCount")
    elif event == "FSSAllBodiesFound" and entry.get("SystemAddress"):
        _all_found.add(entry["SystemAddress"])
        _refresh_hint()
    address = spansh.should_ask(entry, _register, _spansh)
    if address:
        _spansh[address] = "asking"
        honked = _register.system
        spansh.fetch_async(address,
                           lambda address, answer: _on_ui(_add_spansh, honked, address, answer))
    if fresh or event == "FSSDiscoveryScan":
        _refresh_hint()


def _refined(entry, system):
    """One MiningRefined: 1 t into the nearest bookmark of that material, and
    the dropdown.

    One Status.json read for both. A line older than the plugin start is a
    replay of this session's journal and is counted in _replayed, not again.
    """
    global _replayed
    material = spotmark.refined_material(entry)
    if not material:
        return
    stamp = str(entry.get("timestamp") or "")
    if _started_at and stamp and stamp < _started_at:
        _replayed += 1
        return
    status = spotmark.read_status()
    _tally.refined(status, system or _system, material, entry.get("timestamp"))
    if _material is not None and spotmark.on_ground(status):
        _prefill_material(material)


def _prefill_material(refined):
    global _prefilled
    current = _material.get()
    if current == refined:
        return
    if current not in ("", NO_MATERIAL, ALL_MATERIALS, _prefilled):
        return                  # picked by hand
    _prefilled = refined
    _material.set(refined)
    # The filter may not carry what was just mined. _materials() lets the
    # box through, so the dropdown has to be built again to hold it.
    _fill_menu()


def _add_spansh(system, address, answer):
    """Spansh's answer - (bodies, stars and planets known) or None - back on
    the UI thread."""
    if answer is None:
        # Forgotten: the pause stops a second request, and once it is over
        # the next honk here may ask again. The hint is redrawn then, so it
        # does not keep saying "unreachable".
        _spansh.pop(address, None)
        if _frame:
            _frame.after(int(spansh.PAUSE_S * 1000) + 1000, _refresh_hint)
    elif system != _register.system:
        # Jumped on before it came back. Forgotten, so the honk on the way
        # back in asks again rather than the hint saying Spansh has nothing.
        _spansh.pop(address, None)
    else:
        found, known = answer
        _spansh[address] = "answered"
        _spansh_known[address] = known
        spansh.mark_answered(address)
        if _register.add_known(system, address, found) and scan.is_open():
            open_scan()
    _refresh_scan_count()


def _fill_location(entry, system):
    status = spotmark.read_status()
    body = entry.get("Body") or status.get("BodyName")
    lat = entry.get("Latitude", status.get("Latitude"))
    lon = entry.get("Longitude", status.get("Longitude"))
    # Touchdown names the IDs itself; LaunchSRV does not, and the register has them.
    address, body_id = _register.ids(system or _system, body)
    known = cards.location_at(system or _system, body, lat, lon, status.get("PlanetRadius"),
                              system_address=entry.get("SystemAddress", address),
                              body_id=entry.get("BodyID", body_id))
    if known is not None:
        index, metres = known
        _loc.set(str(index))
        _note(f"Location set to {index} - your bookmark {metres:.0f} m away is there")
        return
    if entry.get("event") == "Touchdown":
        index = spotmark.nearest_index(entry)
        if index is not None:
            _loc.set(str(index))


def make_card():
    """Mark where the ship is standing and render the bookmark for it."""
    global _card_token

    _set_done("")
    if _material.get() in ("", NO_MATERIAL, ALL_MATERIALS):
        _set_status("pick one material - a bookmark names what you mined")
        return

    spot = spotmark.mark(spotmark.read_status(), system=_system, commander=_cmdr)
    # Status.json has no IDs; the register has them from the journal's Scan,
    # ApproachBody or Touchdown for this body.
    spot["system_address"], spot["body_id"] = _register.ids(_system, spot["planet_name"])

    # A typed Loc wins: Status.json only knows the location while it is the
    # selected destination, and it is often deselected by the time you land.
    typed = _int(_loc.get())
    if typed is None and spot["location_index"] is not None:
        _loc.set(str(spot["location_index"]))
    else:
        spot["location_index"] = typed

    if not spotmark.on_surface(spot):
        _set_status(f"no coordinates in Status.json for "
                    f"{spot['planet_name'] or 'no body'} - are you on the surface?")
        return

    # Tk variables belong to the main thread - read them here, not in the worker.
    spot["commodity"] = _material.get()
    spot["rigs"] = _int(_rigs.get())
    spot["density"] = None if _density.get() == NOT_READ else _density.get()
    spot["amount"] = None if _amount.get() == NOT_READ else _amount.get()

    _set_status("")
    minimap.bookmarked(spot)
    _card_token += 1
    threading.Thread(target=_render_card, args=(spot, _card_token), daemon=True).start()


def _render_card(spot, token):
    """The file name is not worth reading - either the bookmark is there or
    the reason it is not."""
    try:
        old = cards.nearby(spot)
        if old is None:
            spotcard.save(spot)
            message = None
        else:
            spotcard.save(cards.updated(old, spot), id=old["id"])
            message = (f"updated Rigs/Amount/Density of the {spot.get('commodity')} "
                       f"bookmark {old['distance_m']:.0f} m away")
    except Exception as err:
        message = f"no bookmark: {err}"
    _on_ui(_report, message, token)


def _report(message, token):
    """Stale renders stay quiet - a finished one must not label a running one."""
    # Every finished save, stale or not: the row is in the database either way.
    if not message or message.startswith("updated"):
        scan.refresh()
    if token != _card_token:
        return
    _set_status(message or "")
    _set_done(DONE_TEXT if not message or message.startswith("updated") else "")


# How often a running EDMC looks for a new release. Once at start was all it
# did, and a session left open for a day never heard of one.
UPDATE_CHECK_MS = 60 * 60 * 1000


def _check_updates():
    """Look for a release now, and again in an hour."""
    global _update_after
    if not _frame:
        return
    update.check_async(_on_update_checked)
    _update_after = _frame.after(UPDATE_CHECK_MS, _check_updates)


def _on_update_checked(tag, newer):
    """Called on a worker thread - bounce to Tk before touching a widget."""
    _on_ui(_show_update, tag, newer)


def _show_update(tag, newer):
    """Bookmark becomes the update, rather than a fourth button appearing.

    A permanent version button only made the panel wider, and a temporary one
    still widens it on the day it matters. The card can wait the thirty
    seconds: a release is rare, and the panel is two buttons either way.

    Offline or already current: nothing changes at all.
    """
    if not _card_button or not newer:
        return
    if str(_card_button.cget("text")) in ("Updating...", "Restart EDMC"):
        return          # an hourly check must not undo an install under way
    # "Update", not "Update v2.1.0": the tag would be the one string wider
    # than the button, and widening the panel is what this design avoids. The
    # version it is going to goes in the status line instead.
    # Enabled: the button starts disabled and only the landed poll turns it on,
    # and that poll leaves anything not reading "Bookmark" alone - so starting
    # EDMC docked gave a grey Update nobody could press.
    _card_button.config(text="Update", fg=palette.WARN, command=_install_update, state="normal")
    _set_status(f"{tag} is out - press Update")


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
    _refresh_hint()


def _refresh_hint():
    """Before the honk: honk. After it: FSS when Spansh brought nothing, or
    fewer bodies than the honk counted. Nothing otherwise."""
    if not _hint:
        return
    address = _register.system_address
    state = _spansh.get(address)
    known, counted = _spansh_known.get(address), _honked.get(address)
    if (isinstance(known, int) and isinstance(counted, int) and 0 < known < counted
            and address not in _all_found):
        text = f"Spansh {known}/{counted} bodies - FSS for the rest"
    elif len(_register):
        text = ""
    elif state == "undiscovered":
        text = "New system - FSS planets"
    elif state == "asking":
        text = "Asking Spansh..."
    elif spansh.paused():
        text = "Spansh unreachable - FSS planets"
    elif state == "answered" or (address and spansh.recently_answered(address)):
        text = "No Spansh bodies - FSS planets"
    else:
        text = "Honk on missing data"
    _hint.config(text=text)


def _set_status(text):
    if _status:
        _status.config(text=text)


# How long a passing note stays on the status line. Errors and updates stay
# until something replaces them; a note only says what was just filled in.
NOTE_MS = 8000


def _note(text):
    """The status line for NOTE_MS, then empty again - unless something else
    has been written there meanwhile."""
    _set_status(text)
    if _frame:
        _frame.after(NOTE_MS, lambda: _status and _status.cget("text") == text
                     and _set_status(""))


# What the button says when it is itself, and what it says for a moment after
# a card lands. The result goes on the button because that is where the eye
# already is at the end of a press, and a label that is empty the rest of the
# time was an empty row for the sake of one word.
CARD_TEXT = "Bookmark"
DONE_TEXT = "completed"
DONE_MS = 5000


def _set_done(text):
    """Say it on the button, and take it back after DONE_MS."""
    global _done_after
    if not _card_button or not _frame:
        return
    _done_after = _cancel_done()
    if text:
        _card_button.config(text=text)
        _done_after = _frame.after(DONE_MS, _restore_card_button)
    else:
        _restore_card_button()


def _restore_card_button():
    """Only ever takes back our own word. An update can claim the button while
    the message is up, and an update outranks a bookmark that already landed."""
    global _done_after
    _done_after = None
    if _card_button and str(_card_button.cget("text")) == DONE_TEXT:
        _card_button.config(text=CARD_TEXT)


def _cancel_done():
    if _done_after and _frame:
        try:
            _frame.after_cancel(_done_after)
        except (ValueError, tk.TclError):
            pass
    return None


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
