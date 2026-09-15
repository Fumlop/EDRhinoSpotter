r"""The minimap's painted ground, kept, so an EDMC restart does not wipe it.

    %LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map 1.json.gz
    %LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map 1.png

A folder per body, a file per map. A body can hold several maps - two mining
locations more than 10 km apart are two - and one file each means a save never
has to read and merge the others.

Not a picture: the points the SRV painted new ground at, as latitude and
longitude, and the droppoints. Loading repaints the mask from them - 270
points from an hour's drive, 11 ms. A point is still right if SCAN_RADIUS_M or
the mask resolution changes; a picture would not be.

Gzipped: 270 points are 7.2 KB of JSON and 2.4 KB compressed, about 1.3 ms
for a whole save and 0.5 ms for a read. Plain .json is read too, for a file somebody
unpacked to look at.

The PNG beside it is for the commander to look at, and for mining markers
later. Nothing reads it back.

No tkinter. See rs_tests/test_coverstore.py.
"""

import gzip
import io
import json
import os
import time

from rs_core import atomic, names
from rs_core.logging import logger

ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                    or os.path.expanduser("~"), "RhinoSpotter", "coverage")
VERSION = 1
SUFFIXES = (".json.gz", ".json")


def folder(body, root=None):
    return os.path.join(root or ROOT, names.safe(body))


def maps(body, root=None, system_address=None):
    """[(name, data), ...] for every map saved on that body.

    A file that cannot be read, or is from another version, is skipped and
    logged - one broken map must not cost the others.

    The folder is by body name, and a name is only unique inside its system.
    With `system_address` given, a map that names a different one is a body of
    the same name elsewhere and is left out; a map from before the address was
    kept names none and stays in.
    """
    where = folder(body, root)
    try:
        files = sorted(os.listdir(where))
    except OSError:
        return []
    found = []
    for file in files:
        suffix = next((s for s in SUFFIXES if file.endswith(s)), None)
        if suffix is None:
            continue
        name = file[:-len(suffix)]
        if suffix == ".json" and name + ".json.gz" in files:
            continue            # the gzipped one is the one we wrote last
        try:
            with open(os.path.join(where, file), "rb") as handle:
                raw = handle.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
        except Exception as err:        # zlib.error and RecursionError too
            logger.warning(f"minimap: skipping {file} on {body}: {err}")
            continue
        if not isinstance(data, dict) or data.get("version") != VERSION:
            logger.warning(f"minimap: skipping {file} on {body}: not version {VERSION}")
            continue
        theirs = data.get("system_address")
        if system_address is not None and theirs is not None and theirs != system_address:
            logger.debug(f"minimap: {file} on {body} is in system {theirs}, not {system_address}")
            continue
        found.append((name, data))
    return found


def next_name(body, root=None):
    """'map N', one past the highest number already on that body."""
    taken = [0]
    try:
        for file in os.listdir(folder(body, root)):
            stem = file.split(".", 1)[0]
            if stem.startswith("map ") and stem[4:].isdigit():
                taken.append(int(stem[4:]))
    except OSError:
        pass
    return f"map {max(taken) + 1}"


def save(body, name, data, root=None):
    """Write one map, gzipped, through a temp file. The path, or None."""
    try:
        where = folder(body, root)
        os.makedirs(where, exist_ok=True)
        target = os.path.join(where, name + ".json.gz")
        # `saved` picks between two maps that both reach a launch - see
        # coverage._pick_saved.
        payload = dict(data, version=VERSION, body=body, saved=round(time.time(), 3))
        raw = gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        atomic.write_bytes(target, raw)
        return target
    except OSError as err:
        logger.warning(f"minimap: could not save {name} on {body}: {err}")
        return None


def save_png(body, name, image, root=None):
    """The map as a picture, beside its points. The path, or None."""
    try:
        where = folder(body, root)
        os.makedirs(where, exist_ok=True)
        target = os.path.join(where, name + ".png")
        # Through a temp file, like the points: EDMC closing mid-save or two
        # docks close together must not leave half a picture.
        picture = io.BytesIO()
        image.save(picture, "PNG")
        atomic.write_bytes(target, picture.getvalue())
        return target
    except (OSError, ValueError) as err:
        logger.warning(f"minimap: could not save the picture of {name} on {body}: {err}")
        return None


def latest_png(body, root=None):
    """The path of the map picture on that body written last, or None."""
    where = folder(body, root)
    try:
        pictures = [os.path.join(where, f) for f in os.listdir(where) if f.endswith(".png")]
        return max(pictures, key=os.path.getmtime) if pictures else None
    except OSError:
        return None


def usage(root=None):
    """(maps, bytes) over everything saved, for the settings tab."""
    count = size = 0
    for where, _, files in os.walk(root or ROOT):
        for file in files:
            if file.endswith(".json.gz") or (file.endswith(".json")
                                             and file[:-5] + ".json.gz" not in files):
                count += 1
            try:
                size += os.path.getsize(os.path.join(where, file))
            except OSError:
                pass
    return count, size
