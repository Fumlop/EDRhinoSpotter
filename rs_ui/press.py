"""Mouse press lengths in the SRV: a long press counts as a rig placed.

A daemon thread polls GetAsyncKeyState every POLL_S for BUTTONS; each release
goes to `on_release(button, when, seconds)` on that thread (main passes it on
through _on_ui). `released()` runs on the Tk thread: one CSV row per press,
only with RHINOSPOTTER_DEBUG set (rs_core.logging.DEBUG),
in the SRV with Elite in front, and a rig for rigradar when the press qualifies.

    %LOCALAPPDATA%\\RhinoSpotter\\trace\\presses-<YYYYmmdd>.csv

The rig button is learned per EDMC session: the first press >= RIG_PRESS_S in
the Rhino sets _rig_button, a long press on the other button is not a rig.
GetAsyncKeyState reads the physical buttons. Off Windows nothing runs.
"""

import csv
import os
import threading
import time
from datetime import datetime, timedelta

from rs_core import coverage, database, spotmark
from rs_core.logging import DEBUG, logger
from rs_ui import minimap, overlay, rigradar

POLL_S = 0.02            # 20 ms: press lengths to +-20 ms
BUTTONS = {"left": 0x01, "right": 0x02}     # VK_LBUTTON, VK_RBUTTON
RIG_PRESS_S = 1.0        # placeholder until measured in game: press >= this places a rig
DOUBLE_S = 0.4           # release to next press on _rig_button, s: double click closes rigradar
DIR = os.path.join(database.ROOT, "trace")
COLUMNS = ["when", "button", "ms", "body", "lat", "lon", "heading", "radius", "rhino", "rig"]

_thread = None
_stop = threading.Event()
_rig_button = None       # "left" / "right" once learned, this EDMC session
_last_short = None       # release time of the last short press on _rig_button


def _down(vk):
    """Whether the button is held now (GetAsyncKeyState high bit)."""
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def start(on_release):
    """Poll on a daemon thread; a second call while it runs does nothing."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    if not overlay.win32():
        logger.info("press: no GetAsyncKeyState off Windows, rig presses not tracked")
        return
    _stop.clear()
    _thread = threading.Thread(target=_poll, args=(on_release,), name="rhinospotter-press",
                               daemon=True)
    _thread.start()


def stop():
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=1.0)
    _thread = None


def _poll(on_release):
    held = {}            # button -> (monotonic, wall clock) at press
    while not _stop.is_set():
        for button, vk in BUTTONS.items():
            try:
                down = _down(vk)
            except (AttributeError, OSError):
                logger.warning("press: GetAsyncKeyState failed, rig presses not tracked")
                return
            if down and button not in held:
                held[button] = (time.monotonic(), datetime.now())
            elif not down and button in held:
                began, when = held.pop(button)
                try:
                    on_release(button, when, time.monotonic() - began)
                except Exception:
                    logger.exception("press: release handler failed")
        _stop.wait(POLL_S)


def released(root, button, when, seconds):
    """Tk thread: one CSV row per press (DEBUG only); a rig for rigradar when it qualifies.

    Only with minimap.rig_radar() on, in the SRV and Elite in front: clicks in
    other windows are neither logged nor rigs. Rig: >= RIG_PRESS_S in the Rhino on
    _rig_button; the first such press sets it. Two short presses on _rig_button
    within DOUBLE_S close the radar.
    """
    global _rig_button, _last_short
    if not minimap.rig_radar() or not overlay.game_focused():
        return
    fix = coverage.srv_fix(spotmark.read_status())
    if fix is None:
        return
    body, lat, lon, radius, heading = fix
    rhino = minimap.in_rhino()
    rig = seconds >= RIG_PRESS_S and rhino and _rig_button in (None, button)
    if rig and _rig_button is None:
        _rig_button = button
        logger.info(f"press: rig button is {button} for this session")
    if DEBUG:
        _write([when.isoformat(timespec="milliseconds"), button, round(seconds * 1000), body,
                lat, lon, heading, radius, int(rhino), int(rig)])
    if rig:
        logger.info(f"press: rig placed on {body} at {lat:.6f}, {lon:.6f} ({seconds:.2f} s press)")
        rigradar.placed(root, body, lat, lon, radius, button)
    elif button == _rig_button and seconds < RIG_PRESS_S:
        double = _last_short is not None and (when - _last_short).total_seconds() <= DOUBLE_S
        if double and rigradar._window is not None:
            logger.info("press: double click on the rig button, rig radar closed")
            rigradar.close()
            _last_short = None
        else:
            _last_short = when + timedelta(seconds=seconds)


def _write(row):
    path = os.path.join(DIR, time.strftime("presses-%Y%m%d.csv"))
    try:
        os.makedirs(DIR, exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if new:
                writer.writerow(COLUMNS)
            writer.writerow(row)
    except OSError as err:
        logger.warning(f"press: could not write {path}: {err}")
