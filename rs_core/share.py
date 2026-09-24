"""A bookmark as one line of text, for the clipboard: `RhinoData:<code>`.

<code> is URL-safe base64 of zlib-compressed JSON of the FIELDS below. No
commander, no timestamps, no tons. Codes shared or imported here are kept as
SHA-256 digests in the `meta` table (`shared:<digest>`) and never imported
again: not a copy made here, not one deleted after its import.

No tkinter.
"""

import base64
import hashlib
import json
import math
import re
import sqlite3
import zlib
from datetime import datetime, timezone

from rs_core import cards, database, deposit, spotcard, spotmark
from rs_core.logging import logger

PREFIX = "RhinoData:"
CODE = re.compile(re.escape(PREFIX) + r"([A-Za-z0-9_-]+={0,2})")

# Written and accepted: key -> the types a value may have. None is always allowed.
FIELDS = {
    "system": (str,), "system_address": (int,), "planet_name": (str,),
    "body_id": (int,), "planet_radius": (int, float), "latitude": (int, float),
    "longitude": (int, float), "heading": (int, float), "location_index": (int,),
    "commodity": (str,), "rigs": (int,), "amount": (str,), "density": (str,),
}
# A code without these is refused on import.
REQUIRED = ("system", "planet_name", "planet_radius", "latitude", "longitude", "commodity")
# Accepted ranges, inclusive. Strings: at most MAX_TEXT characters.
RANGES = {"system_address": (0, 2 ** 62), "body_id": (0, 10_000),
          "planet_radius": (1.0, 1e8), "latitude": (-90.0, 90.0),
          "longitude": (-180.0, 180.0), "heading": (0, 360), "location_index": (0, 999),
          "rigs": (0, 99)}
CHOICES = {"commodity": spotmark.MATERIALS, "amount": deposit.AMOUNTS,
           "density": deposit.DENSITIES}
MAX_TEXT = 64

# Longest code accepted, in characters. A shared bookmark is ~250.
MAX_CODE = 4000


def encode(record):
    """`record` -> 'RhinoData:<code>'."""
    data = {key: record[key] for key in FIELDS if record.get(key) is not None}
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")


def decode(text):
    """(code, spot) for the first valid RhinoData code in `text`, else None."""
    found = CODE.search(text or "")
    if not found or len(found.group(1)) > MAX_CODE:
        return None
    try:
        # max_length caps what a crafted code can inflate to: 16 KB.
        raw = zlib.decompressobj().decompress(base64.urlsafe_b64decode(found.group(1)),
                                              MAX_CODE * 4)
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, zlib.error, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    spot = {}
    for key, types in FIELDS.items():
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, types):
            return None
        if isinstance(value, str) and len(value) > MAX_TEXT:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if key in RANGES and not RANGES[key][0] <= value <= RANGES[key][1]:
            return None
        if key in CHOICES and value not in CHOICES[key]:
            return None
        spot[key] = value
    if any(spot.get(key) in (None, "") for key in REQUIRED):
        return None
    return found.group(0), spot


def shareable(record):
    """Whether encode(record) is a code decode() accepts."""
    return decode(encode(record)) is not None


def _digest(code):
    return "shared:" + hashlib.sha256(code.encode("ascii")).hexdigest()


def remember(code, db=None):
    """Mark `code` as shared or imported here. A failed write is logged."""
    try:
        with database.connect(db) as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         (_digest(code), _now()))
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not remember a shared code: {err}")


def mine(code, db=None):
    """Whether `code` was shared or imported by this install."""
    try:
        with database.connect(db) as conn:
            return conn.execute("SELECT 1 FROM meta WHERE key = ?",
                                (_digest(code),)).fetchone() is not None
    except (sqlite3.Error, OSError) as err:
        logger.warning(f"could not read the shared codes: {err}")
        return True         # unreadable: import nothing rather than twice


def take(text, db=None):
    """Import the RhinoData code in `text`, if any.

    Returns (state, spot): state is None (no valid code), 'seen' (shared or
    imported here before), 'known' (same material on that body within
    cards.SAME_SPOT_M) or 'imported'. Raises sqlite3.Error / OSError when the
    save fails.
    """
    found = decode(text)
    if found is None:
        return None, None
    code, spot = found
    if mine(code, db):
        return "seen", spot
    if cards.nearby(spot, db) is not None:
        return "known", spot
    spot["marked_at"] = _now()
    spotcard.save(spot, db=db)
    remember(code, db)
    logger.info(f"imported shared bookmark: {spot['commodity']} on {spot['planet_name']}")
    return "imported", spot


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
