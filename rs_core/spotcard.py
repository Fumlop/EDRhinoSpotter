"""One marked mining spot, written to disk as a bookmark.

A JSON record per spot - body, material, rigs, location, heading,
coordinates, when and who - everything read from Status.json at the press.
The bookmarks page, Guide, the minimap's dots and the map picture's legend
all read it back through rs_core/cards.py.

It was a PNG card with this JSON beside it. The saved map picture shows the
spot with its neighbours, so the card is gone; older cards on disk are left
where they are and their JSON still reads.

The fonts helper stays here: the map picture draws its text with it.
"""

import json
import os

from PIL import ImageFont

from rs_core import atomic, names

# Outside the plugin folder on purpose: bookmarks outlive a plugin reinstall,
# and %LOCALAPPDATA% is somewhere Explorer opens without hunting for it.
CARDS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "cards")


def card_dir(system):
    r"""%LOCALAPPDATA%\RhinoSpotter\cards\<System>\.

    Spaces kept: this is the folder Explorer shows, and the name the game uses
    is easier to find in a list than the same name with underscores in it.
    """
    return os.path.join(CARDS_ROOT, names.safe(system))


FONTS = r"C:\Windows\Fonts"


def _font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def _fmt(value, suffix="", dash="—"):
    if value is None or value == "":
        return dash
    if suffix:
        return f"{value}{suffix}"
    return str(value)


def save(spot, out_path=None):
    """spot: a spotmark.mark() dict plus 'commodity' and 'rigs'. Returns the path.

    Raises when it cannot be written: this file is the bookmark, and the panel
    says why it is not there rather than claiming it is.
    """
    record = {key: (None if value is None else
                    value if isinstance(value, (int, float, str)) else str(value))
              for key, value in spot.items()}
    if out_path is None:
        out_path = _free(os.path.join(card_dir(spot.get("system")), filename(spot)))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    atomic.write_text(out_path, json.dumps(record, indent=1))
    return out_path


def _free(path):
    """The first free name at `path`, counting up: spot.json, spot_2.json, ...

    Two marks of the same location for the same material are two bookmarks. They
    were the same file, and the second one silently replaced the first - which
    is the wrong way round, because the reason to mark a patch twice is that
    something about it differed. The plain name stays on the first one so
    nothing already on disk moves.
    """
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    number = 2
    while os.path.exists(f"{stem}_{number}{ext}"):
        number += 1
    return f"{stem}_{number}{ext}"


def filename(spot):
    """One file per material per spot. A repeat of the same spot and material
    gets a counter from _free rather than landing on the one already there."""
    parts = [spot.get("planet_name") or "spot",
             f"loc{_fmt(spot.get('location_index'), dash='x')}",
             (spot.get("commodity") or "unknown").lower()]
    return names.safe("_".join(parts), spaces=False) + ".json"
