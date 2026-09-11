"""Screenshots taken on a body, converted and filed with where they were taken.

The game drops a .bmp in the pictures folder and names it nothing useful. Every
Screenshot event carries the position it was taken from, and Status.json carries
the mining location that was selected at the time - the one thing the event does
not have. Both go into a sidecar JSON beside the image, so a material read
later can be tied to a place rather than to a filename.

    data/planetScreener/<System>/<Body>/loc<N>_<UTC>.jpg    the target panel
    data/planetScreener/<System>/<Body>/loc<N>_<UTC>.json   where it was taken

A folder per body, because a body is what gets worked: twenty-six shots of one
planet's locations belong together, and the location number leads the filename
so the folder sorts into the order you would read it in.

Only the target panel is kept. It names the materials of the selected mining
location, which is the whole point of the shot; the rest of the frame is 1.2 MB
of cockpit. Cropped and doubled so the names stay readable.
"""

import json
import os
import re
from datetime import datetime, timezone

try:
    from PIL import Image
    _PIL = True
except ImportError:      # EDMC ships PIL, but a bare interpreter may not
    _PIL = False

SHOT_DIR = os.path.expandvars(
    r"%USERPROFILE%\Pictures\Frontier Developments\Elite Dangerous"
)
STATUS_PATH = os.path.expandvars(
    r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous\Status.json"
)
JOURNAL_DIR = os.path.dirname(STATUS_PATH)

EDINTEL_ROOT = r"D:\Apps\EDIntel"
OUT_ROOT = os.path.join(EDINTEL_ROOT, "data", "planetScreener")
LOCAL_ROOT = os.path.join(os.path.dirname(__file__), "planetScreener")

# The .bmp is the game's scratch file and is what fills the pictures folder;
# it goes only once the crop is on disk with bytes in it.
REMOVE_BMP = True

BAD = r'\/:*?"<>|'

# The target panel, as fractions of the frame - the HUD scales with resolution,
# so pixels from one 1920x1080 shot would not survive a different monitor.
# Left edge kept loose: the panel slides with the length of the body name,
# and location 9 on 12 b clipped its first column at 0.744.
# The panel does not sit in the same place in every cockpit - the Mandalay puts
# it top right where the Panther Mk II puts it mid right - so the box is per
# ship type. A ship with no entry falls back to DEFAULT_BOX and will need
# measuring the first time its crop comes out as cockpit.
MATS_BOXES = {
    "panthermkii": (0.712, 0.466, 0.950, 0.665),
    "mandalay":    (0.795, 0.135, 1.000, 0.350),
}
DEFAULT_BOX = MATS_BOXES["panthermkii"]
MATS_SCALE = 2


def _safe(name):
    return "".join("_" if ch in BAD else ch for ch in (name or "")).strip()


def out_root():
    return OUT_ROOT if os.path.isdir(EDINTEL_ROOT) else LOCAL_ROOT


def _status():
    try:
        with open(STATUS_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def destination(status):
    """(body id, location index) of the targeted mining location.

    Status.json names the destination body only by id. The panel in the shot
    describes *that* body's location, which is not always the body the
    Screenshot event names - park above 12 a with a location on 12 b selected
    and the event says 12 a while the screen shows 12 b.
    """
    dest = status.get("Destination") or {}
    match = re.search(r"#index=(\d+)", dest.get("Name") or "")
    return dest.get("Body"), int(match.group(1)) if match else None


def location_index(status):
    """The mining location selected as destination, or None.

    Status.json writes it as '$SAA_Unknown_Signal:#index=15;' and nothing else
    reports it - not the Screenshot event, not the journal.
    """
    name = (status.get("Destination") or {}).get("Name") or ""
    match = re.search(r"#index=(\d+)", name)
    return int(match.group(1)) if match else None


def sidecar(entry, status, run_location=None, bodies=None):
    """What was true when the shutter went, from the event first, Status second.

    Status.json is live: by the time this runs the ship may be at another body,
    and a planet radius from the wrong one is worse than none. So Status only
    contributes while it still names the same body.

    The exception is the destination. A targeted mining location belongs to the
    body it is on, and that is what the panel is showing, so it wins over the
    body the event happens to name.
    """
    system = entry.get("System") or ""
    body = entry.get("Body") or status.get("BodyName") or ""
    near_body = body

    dest_id, dest_index = destination(status)
    dest_body = (bodies or {}).get(dest_id) if dest_id is not None else None
    if dest_index is not None and dest_body:
        body = dest_body

    if status.get("BodyName") and near_body and status["BodyName"] != near_body:
        status = {}
    record = {
        "timestamp": entry.get("timestamp"),
        "system": system,
        "body": body,
        "latitude": entry.get("Latitude", status.get("Latitude")),
        "longitude": entry.get("Longitude", status.get("Longitude")),
        "heading": entry.get("Heading", status.get("Heading")),
        "altitude": entry.get("Altitude", status.get("Altitude")),
        "planet_radius_m": status.get("PlanetRadius") if body == near_body else None,
        "location_index": dest_index,
        "destination_body_id": dest_id,
        "width": entry.get("Width"),
        "height": entry.get("Height"),
        "source_bmp": os.path.basename((entry.get("Filename") or "").replace("\\", os.sep)),
    }
    if body != near_body:
        # Worth keeping: it says the shot was taken from somewhere else, which
        # is why the distance on the panel is large.
        record["near_body"] = near_body
    # A screenshot taken during a run belongs to that run's patch even when the
    # destination has since been cleared.
    if record["location_index"] is None and run_location is not None:
        record["location_index"] = run_location
        record["location_from"] = "open run"
    return record


def _ship():
    """The ship type flying, from the last Loadout the journal wrote.

    Read from the journal rather than held in memory because a plugin reload
    mid-session would forget it, and a forgotten ship crops the wrong corner of
    every shot until the next dock.
    """
    try:
        logs = sorted(f for f in os.listdir(JOURNAL_DIR)
                      if f.startswith("Journal.") and f.endswith(".log"))
    except OSError:
        return None
    for name in reversed(logs[-3:]):
        try:
            with open(os.path.join(JOURNAL_DIR, name), encoding="utf-8",
                      errors="replace") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            if '"event":"Loadout"' not in line:
                continue
            try:
                return json.loads(line).get("Ship")
            except ValueError:
                continue
    return None


def _crop_materials(image, path):
    """The target panel, doubled, as JPEG."""
    width, height = image.size
    mats_box = MATS_BOXES.get(_ship() or "", DEFAULT_BOX)
    box = (int(mats_box[0] * width), int(mats_box[1] * height),
           int(mats_box[2] * width), int(mats_box[3] * height))
    crop = image.crop(box)
    crop = crop.resize((crop.width * MATS_SCALE, crop.height * MATS_SCALE),
                       Image.LANCZOS)
    crop.convert("RGB").save(path, "JPEG", quality=92)


def convert(entry, run_location=None, bodies=None):
    """Crop one Screenshot event's .bmp. Returns the JPEG path, or raises."""
    if not _PIL:
        raise RuntimeError("PIL not available")

    name = os.path.basename((entry.get("Filename") or "").replace("\\", os.sep))
    if not name:
        raise ValueError("Screenshot event carried no filename")
    bmp = os.path.join(SHOT_DIR, name)

    status = _status()
    record = sidecar(entry, status, run_location, bodies)

    system = record["system"] or "Unknown"
    body = record["body"] or ""
    if body.startswith(system):
        body = body[len(system):].strip()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if record["timestamp"]:
        stamp = record["timestamp"].replace("-", "").replace(":", "").replace("T", "-")[:15]

    index = record["location_index"]
    stem = f"loc{index:02d}_{stamp}" if index else stamp
    directory = os.path.join(out_root(), _safe(system) or "Unknown",
                             _safe(body) or "orbit")
    os.makedirs(directory, exist_ok=True)
    jpg = os.path.join(directory, stem + ".jpg")

    with Image.open(bmp) as image:
        _crop_materials(image, jpg)

    with open(os.path.join(directory, stem + ".json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)

    if REMOVE_BMP and os.path.getsize(jpg) > 0:
        try:
            os.remove(bmp)
        except OSError:
            pass
    return jpg
