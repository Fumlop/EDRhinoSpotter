"""Lab, Ctrl+Alt+R: trace a deposit border, then guide to planned rig spots.

Press once, drive the border. The lap closes itself when the SRV comes back
within SNAP_M of the first fix after SNAP_PATH_M of driving; a second press
closes it early. rs_core.rigplan then plans the spots off the Tk thread and
rs_ui.overlay points at rig 1 and holds HERE (RIG_ARRIVE_M) until the placed key (Ctrl+Alt+P) moves it to the next.

Status.json mtime polled every POLL_MS; each new mtime is one CSV row.

    %LOCALAPPDATA%\\RhinoSpotter\\trace\\trace-<YYYYmmdd-HHMMSS>.csv
    %LOCALAPPDATA%\\RhinoSpotter\\trace\\trace-<YYYYmmdd-HHMMSS>.txt   rate summary + spots

Overlay while tracing: click-through text centred on the Elite window, upper third.
"""

import csv
import json
import math
import os
import statistics
import threading
import time
import tkinter as tk

from rs_core import database, paths, rigplan
from rs_core.logging import logger
from rs_ui import overlay

POLL_MS = 20         # two writes within 20 ms count as one
STILL_M = 0.5        # per-write step below this counts as standing
SNAP_M = 10.0        # lap closes this close to the first fix
SNAP_PATH_M = 60.0   # ... after at least this much driving
RIG_ARRIVE_M = 3.0   # arrow shows HERE inside this, m
NOTE_MS = 8000       # "no rig fits" stays up this long
DIR = os.path.join(database.ROOT, "trace")
FONT = ("Consolas", 16, "bold")
TEXT = "#ff8c0d"

_window = None
_label = None
_after = None
_handle = None       # open CSV file
_writer = None
_rows = []
_last_mtime = None
_bad_reads = 0
_stem = None
_root = None
_plan = []           # guide targets, rig 1 first
_step = 0            # index into _plan being guided to


def active():
    return _handle is not None


def toggle(root):
    """Start a trace, or close the running one early. `root`: any Tk widget."""
    if active():
        stop()
    else:
        start(root)


def start(root):
    global _handle, _writer, _rows, _last_mtime, _bad_reads, _stem, _root, _plan
    _root = root
    if _plan:
        _plan = []           # before overlay.stop(): _next() then ends instead of advancing
        overlay.stop()
    os.makedirs(DIR, exist_ok=True)
    _stem = os.path.join(DIR, time.strftime("trace-%Y%m%d-%H%M%S"))
    _handle = open(_stem + ".csv", "w", newline="", encoding="utf-8")
    _writer = csv.writer(_handle)
    _writer.writerow(["t", "mtime", "game_ts", "lat", "lon", "heading", "altitude", "radius", "flags"])
    _rows, _last_mtime, _bad_reads = [], None, 0
    _cancel()                # a pending "no rig fits" close
    _open_window(root)
    _show(_live_text())
    logger.info(f"trace: recording to {_stem}.csv")
    _poll()


def _cancel():
    global _after
    if _after is not None and _window is not None:
        _window.after_cancel(_after)
    _after = None


def shutdown():
    """EDMC closing: close the CSV, no planning, no guiding."""
    global _root, _plan
    _root, _plan = None, []
    stop()


def stop():
    """Close the lap: CSV closed, spots planned, arrow to rig 1."""
    global _handle, _writer
    _cancel()
    if _handle is None:
        return
    _handle.close()
    _handle = _writer = None
    lines = summary(_rows) + [f"reads failed mid-write {_bad_reads}", f"csv {_stem}.csv"]
    for line in lines:
        logger.info(f"trace: {line}")
    fixes = [r for r in _rows if r["lat"] is not None and r["radius"]]
    if len(fixes) < 3 or _root is None:     # EDMC closing, or nothing driven
        _write_txt(lines, [])
        _close_window()
        return
    _show("Planning rigs ...")
    body, radius = fixes[-1]["body"], fixes[-1]["radius"]
    points = [(r["lat"], r["lon"]) for r in fixes]

    result = []

    def work():
        try:
            result.append(rigplan.plan(points, radius))
        except Exception:
            logger.exception("trace: rig plan failed")
            result.append([])

    # Polled from the Tk thread: no Tk call from the worker.
    def wait():
        global _after
        _after = None
        if _root is None:
            return                           # EDMC closing
        if result:
            _planned(lines, body, result[0])
        else:
            _after = _window.after(100, wait)

    threading.Thread(target=work, name="rhinospotter-rigplan", daemon=True).start()
    wait()


def _write_txt(lines, spots):
    spot_lines = [f"rig {i}: {lat:.6f}, {lon:.6f}" for i, (lat, lon) in enumerate(spots, 1)]
    with open(_stem + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines + [f"rigs {len(spots)} (spacing {rigplan.SPACING_M:.0f} m, "
                                   f"inset {rigplan.INSET_M:.0f} m)"] + spot_lines) + "\n")


def _planned(lines, body, spots):
    """Tk thread: plan is back. Arrow to rig 1, or say none fits."""
    global _plan, _step, _after
    _write_txt(lines, spots)
    logger.info(f"trace: {len(spots)} rig spot(s) on {body}")
    if not spots:
        _show("no rig fits here\ntrace the whole border")
        _after = _window.after(NOTE_MS, _close_window) if _window is not None else None
        return
    _close_window()
    stamp = time.time()
    key = _key(PLACED)
    _plan = [{"planet_name": body, "latitude": lat, "longitude": lon, "arrive_m": RIG_ARRIVE_M,
              "hold": True, "marked_at": f"rig-{stamp}-{i}",
              "caption": f"rig {i} of {len(spots)} - {key} when placed"}
             for i, (lat, lon) in enumerate(spots, 1)]
    _step = 0
    overlay.start(_root, _plan[0], on_stop=_ended)


def placed():
    """Placed key: arrow on to the next rig; after the last one, down."""
    global _plan, _step
    if not _plan or _root is None:
        return
    _step += 1
    logger.info(f"trace: rig {_step} of {len(_plan)} placed")
    if _step >= len(_plan):
        _plan = []           # before stop(): _ended() then has nothing to drop
        overlay.stop()
        return
    overlay.start(_root, _plan[_step], on_stop=_ended)    # retargets, no stop()


def _ended():
    """overlay closed by itself (Stop pressed, wrong body for NOTICE_MS): plan dropped."""
    global _plan
    if _plan:
        logger.info(f"trace: guide closed at rig {_step + 1} of {len(_plan)}, plan dropped")
    _plan = []


def _poll():
    global _after, _last_mtime, _bad_reads
    _after = None
    if _handle is None:
        return
    path = os.path.join(paths.journal_dir(), "Status.json")
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        mtime = None
    if mtime is not None and mtime != _last_mtime:
        now = time.perf_counter()
        try:
            with open(path, encoding="utf-8") as f:
                status = json.load(f)
        except (OSError, ValueError):
            _bad_reads += 1          # mid-write; the next poll sees the same mtime again
        else:
            _last_mtime = mtime
            row = {"t": now, "lat": status.get("Latitude"), "lon": status.get("Longitude"),
                   "radius": status.get("PlanetRadius"), "body": status.get("BodyName")}
            _rows.append(row)
            _writer.writerow([f"{now:.4f}", mtime, status.get("timestamp"), row["lat"], row["lon"],
                              status.get("Heading"), status.get("Altitude"), row["radius"],
                              status.get("Flags")])
            _handle.flush()
            if _closed():
                stop()
                return
            _show(_live_text())
    _after = _window.after(POLL_MS, _poll)


def _closed():
    """Lap done: back within SNAP_M of the first fix after SNAP_PATH_M of driving."""
    fixes = [r for r in _rows if r["lat"] is not None and r["radius"]]
    if len(fixes) < 3:
        return False
    at = lambda r: (r["lat"], r["lon"])
    path = sum(metres(at(a), at(b), b["radius"]) for a, b in zip(fixes, fixes[1:]))
    return path >= SNAP_PATH_M and metres(at(fixes[0]), at(fixes[-1]), fixes[-1]["radius"]) <= SNAP_M


def _live_text():
    """Overlay while tracing: what to do next; distance back once SNAP_PATH_M is driven."""
    fixes = [r for r in _rows if r["lat"] is not None and r["radius"]]
    if not fixes:
        return "Land and get into the SRV"
    at = lambda r: (r["lat"], r["lon"])
    path = sum(metres(at(a), at(b), b["radius"]) for a, b in zip(fixes, fixes[1:]))
    lines = ["Drive the border slowly"]
    if path >= SNAP_PATH_M:
        lines.append(f"back to start: {metres(at(fixes[0]), at(fixes[-1]), fixes[-1]['radius']):.0f} m")
    lines.append(f"{_key(TRACE)}: finish here")
    return "\n".join(lines)


TRACE, PLACED = "trace", "placed"


def _key(action):
    """Current binding of the trace or placed key, e.g. 'Ctrl+Alt+P'."""
    from rs_ui import hotkey     # hotkey imports overlay; late import keeps the cycle out
    return hotkey.label(hotkey.TRACE if action == TRACE else hotkey.PLACED)


def metres(a, b, radius):
    """Great-circle distance in m between (lat, lon) degree pairs on a sphere of `radius` m."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def _pct(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def summary(rows):
    """rows: dicts with t (s), lat, lon (deg), radius (m). Returns printable lines."""
    fixes = [r for r in rows if r["lat"] is not None and r["radius"]]
    lines = [f"writes {len(rows)}, with position+PlanetRadius {len(fixes)}"]
    if len(rows) > 1:
        gaps = [b["t"] - a["t"] for a, b in zip(rows, rows[1:])]
        lines.append(f"interval s: median {statistics.median(gaps):.3f}  p90 {_pct(gaps, 0.9):.3f}  max {max(gaps):.3f}")
    if len(fixes) > 1:
        steps = [(metres((a["lat"], a["lon"]), (b["lat"], b["lon"]), b["radius"]), b["t"] - a["t"])
                 for a, b in zip(fixes, fixes[1:])]
        moving = [(m, s) for m, s in steps if m >= STILL_M]
        still = [m for m, _ in steps if m < STILL_M]
        if moving:
            dist = [m for m, _ in moving]
            lines.append(f"moving m/write: median {statistics.median(dist):.2f}  p90 {_pct(dist, 0.9):.2f}  max {max(dist):.2f}")
            speeds = [m / s for m, s in moving if s > 0]
            if speeds:
                lines.append(f"speed m/s: median {statistics.median(speeds):.2f}  max {max(speeds):.2f}")
        lines.append(f"standing steps {len(still)}" + (f", max {max(still):.3f} m" if still else ""))
        lines.append(f"start->end {metres((fixes[0]['lat'], fixes[0]['lon']), (fixes[-1]['lat'], fixes[-1]['lon']), fixes[-1]['radius']):.1f} m")
    return lines


def _open_window(root):
    global _window, _label
    if _window is not None:
        return
    _window = tk.Toplevel(root)
    _window.overrideredirect(True)
    _window.configure(bg=overlay.KEY)
    _window.attributes("-topmost", True)
    try:
        _window.attributes("-transparentcolor", overlay.KEY)
    except tk.TclError:
        pass
    _label = tk.Label(_window, bg=overlay.KEY, fg=TEXT, font=FONT, justify="center")
    _label.pack()
    _window.update_idletasks()
    overlay._click_through(_window)


def _close_window():
    global _window, _label, _after
    _after = None
    if _window is not None:
        _window.destroy()
    _window = _label = None


def _show(text):
    if _window is None:
        return
    _label.configure(text=text)
    _window.update_idletasks()
    w, h = _label.winfo_reqwidth(), _label.winfo_reqheight()
    rect = overlay._game_rect()
    if rect:
        left, top, right, bottom = rect
    else:
        left, top, right, bottom = 0, 0, _window.winfo_screenwidth(), _window.winfo_screenheight()
    # Upper third: the centre holds the SRV reticle.
    x, y = left + (right - left - w) // 2, top + (bottom - top) // 3 - h // 2
    _window.geometry(f"{w}x{h}+{x}+{y}")
    if overlay.win32():
        try:
            import ctypes
            handle = ctypes.windll.user32.GetParent(_window.winfo_id()) or _window.winfo_id()
            overlay.set_topmost(handle, x, y, w, h)
        except (ImportError, AttributeError, OSError):
            pass
