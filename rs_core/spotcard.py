"""Writes one marked spot to the bookmarks table.

One row per spot: body, material, rigs, location, heading, coordinates, time
and commander, all read from Status.json at the press. Read back through
rs_core/cards.py by the bookmarks page, Guide, the minimap dots and the map
picture legend.

Before 4.2 a spot was a PNG card plus a JSON sidecar. Old cards are left on
disk; rs_core/migrate.py imports their JSON once. CARDS_ROOT and card_dir()
still locate them.

_font() lives here because the map picture draws its text with it.
"""

import functools
import os

from PIL import ImageFont

from rs_core import database, names

# Bookmark storage up to 4.1: one JSON file each. Read by rs_core/migrate.py;
# old card PNGs are still found here.
CARDS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "cards")


def card_dir(system):
    r"""%LOCALAPPDATA%\RhinoSpotter\cards\<System>\, via names.safe().

    Spaces are kept; this path is shown in Explorer.
    """
    return os.path.join(CARDS_ROOT, names.safe(system))


FONTS = r"C:\Windows\Fonts"


@functools.lru_cache(maxsize=64)
def _font(name, size):
    """ImageFont for (name, size) from C:\Windows\Fonts, or load_default().

    Cached: the minimap requests 3 faces per frame and truetype() re-reads the
    file on every call. Fewer than 64 distinct pairs are used.
    """
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def save(spot, id=None, db=None):
    """Write `spot` and return the bookmark id. With `id`, replace that row.

    `spot` is a spotmark.mark() dict plus 'commodity' and 'rigs'. Values that
    are not int, float, str or None are stringified.

    Raises sqlite3.Error / OSError on failure rather than returning None: the
    row is the bookmark, and the caller reports the failure.
    """
    record = {key: (None if value is None else
                    value if isinstance(value, (int, float, str)) else str(value))
              for key, value in spot.items()}
    with database.connect(db) as conn:
        id = database.write_bookmark(conn, record, id)
    database.changed()
    return id
