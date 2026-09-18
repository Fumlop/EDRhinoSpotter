"""One marked mining spot, written to the database as a bookmark.

A record per spot - body, material, rigs, location, heading,
coordinates, when and who - everything read from Status.json at the press.
The bookmarks page, Guide, the minimap's dots and the map picture's legend
all read it back through rs_core/cards.py.

It was a PNG card with this JSON beside it. The saved map picture shows the
spot with its neighbours, so the card is gone; older cards on disk are left
where they are, and rs_core/migrate.py reads their JSON in once.

The fonts helper stays here: the map picture draws its text with it.
"""

import functools
import os

from PIL import ImageFont

from rs_core import database, names

# Where 4.1 and before kept bookmarks, one JSON file each. Read by
# rs_core/migrate.py, and still where an old card's PNG is found.
CARDS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "cards")


def card_dir(system):
    r"""%LOCALAPPDATA%\RhinoSpotter\cards\<System>\.

    Spaces kept: this is the folder Explorer shows, and the name the game uses
    is easier to find in a list than the same name with underscores in it.
    """
    return os.path.join(CARDS_ROOT, names.safe(system))


FONTS = r"C:\Windows\Fonts"


@functools.lru_cache(maxsize=64)
def _font(name, size):
    """Kept: the minimap asks for three faces a frame and truetype() re-reads
    the file every time. A handful of (name, size) pairs are ever used."""
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def save(spot, id=None, db=None):
    """spot: a spotmark.mark() dict plus 'commodity' and 'rigs'. Returns the
    bookmark's id. With `id`, that bookmark is replaced.

    Raises when it cannot be written: this row is the bookmark, and the panel
    says why it is not there rather than claiming it is.
    """
    record = {key: (None if value is None else
                    value if isinstance(value, (int, float, str)) else str(value))
              for key, value in spot.items()}
    with database.connect(db) as conn:
        id = database.write_bookmark(conn, record, id)
    database.changed()
    return id
