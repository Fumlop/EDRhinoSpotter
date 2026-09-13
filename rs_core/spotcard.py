"""Render one marked mining spot as a PNG card.

Same palette as the scan window - see rs_core/palette.py - so a card dropped
into a chat beside a screenshot of the window looks like the same tool. PIL
ships inside EDMC, so nothing extra is vendored for this.

The card is the whole record: what was marked is what it shows. Nothing is
looked up, so it renders with nothing else running and no network.
"""

import json
import os

from PIL import Image, ImageDraw, ImageFont

from rs_core import names, palette

# Outside the plugin folder on purpose: cards outlive a plugin reinstall, and
# %LOCALAPPDATA% is somewhere Explorer opens without hunting for it.
CARDS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "cards")


def card_dir(system):
    r"""%LOCALAPPDATA%\RhinoSpotter\cards\<System>\.

    Spaces kept: this is the folder Explorer shows, and the name the game uses
    is easier to find in a list than the same name with underscores in it.
    """
    return os.path.join(CARDS_ROOT, names.safe(system))

W, H = 880, 360
PAD = 34

# The window's palette, converted once. A card dropped into a chat beside a
# screenshot of the scan window has to look like the same tool.
PAPER = palette.rgb(palette.BG)
SHEET = palette.rgb(palette.PANEL)
INK = palette.rgb(palette.FG)
INK_SOFT = palette.rgb(palette.FG_SOFT)
MUTED = palette.rgb(palette.MUTED)
RULE = palette.rgb(palette.RULE)
ACCENT = palette.rgb(palette.ACCENT)
SECOND = palette.rgb(palette.GOOD)

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


def _degrees(value):
    """One coordinate, or a dash.

    Six decimals, which is what the game gives and roughly a metre - enough to
    put the ship back on the same patch.
    """
    if value is None:
        return "-"
    return f"{float(value):.6f}"


def _fit(draw, text, font, width):
    """The longest head of the text that fits, so a long body name cannot run
    off the sheet."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def render(spot, out_path=None):
    """spot: a spotmark.mark() dict plus 'commodity' and 'rigs'. Returns the path."""
    ui = _font("segoeui.ttf", 15)
    title = _font("segoeuib.ttf", 34)
    mono = _font("consola.ttf", 15)
    mono_small = _font("consolab.ttf", 12)
    huge = _font("segoeuib.ttf", 40)

    image = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(image)

    draw.rectangle([PAD, PAD, W - PAD, H - PAD], fill=SHEET, outline=RULE)
    draw.rectangle([PAD, PAD, PAD + 3, H - PAD], fill=ACCENT)

    x = PAD + 26
    right = W - PAD - 26
    y = PAD + 22

    draw.text((x, y), "RHINO SURFACE MINING", font=mono_small, fill=MUTED)
    y += 24

    draw.text((x, y), _fit(draw, spot.get("planet_name") or "unknown body", title, right - x),
              font=title, fill=INK)
    y += 46
    draw.text((x, y), spot.get("system") or "", font=ui, fill=INK_SOFT)
    y += 30

    draw.line([x, y, right, y], fill=RULE)
    y += 24

    # The material is why anyone flies here, so it gets the size the t/h had.
    draw.text((x, y), _fit(draw, spot.get("commodity") or "no material", huge, 300),
              font=huge, fill=ACCENT)

    # Altitude used to sit in the fourth cell. You are landed when you press
    # the button, so it was the ship's height above a patch of ground measured
    # from that same patch of ground - always about zero, and it never told
    # anyone anything. The coordinates take its place: they are the one thing
    # on the card you cannot work out again afterwards.
    #
    # Two columns. The left is what you set before you pressed, the right is
    # where you were, one coordinate per line - a lat and a lon on one line is
    # a single long number that has to be read twice to be split.
    grid_x = x + 340
    settings = [
        ("Rigs", _fmt(spot.get("rigs")), INK),
        ("Location", _fmt(spot.get("location_index")), INK),
        ("Heading", _fmt(spot.get("heading"), "°"), INK),
    ]
    position = [
        ("Lat", _degrees(spot.get("latitude")), SECOND),
        ("Lon", _degrees(spot.get("longitude")), SECOND),
    ]
    for col, cells in enumerate((settings, position)):
        for row, (key, value, colour) in enumerate(cells):
            cx = grid_x + col * 250
            cy = y + row * 32
            draw.text((cx, cy), key.upper(), font=mono_small, fill=MUTED)
            draw.text((cx + 96, cy - 2), value, font=mono, fill=colour)

    y += 104
    draw.line([x, y, right, y], fill=RULE)
    y += 18

    # Both on one line: who and when are the same kind of fact, and stacking
    # them put the commander on the border of the sheet.
    if spot.get("commander"):
        draw.text((x, y), "CMDR " + spot["commander"], font=mono_small, fill=MUTED)
    marked = spot.get("marked_at")
    if marked:
        stamp = str(marked).split(".")[0]
        draw.text((right - draw.textlength(stamp, font=mono_small), y),
                  stamp, font=mono_small, fill=MUTED)

    if out_path is None:
        out_path = _free(os.path.join(card_dir(spot.get("system")), filename(spot)))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.save(out_path)
    _sidecar(out_path, spot)
    return out_path


def _sidecar(card_path, spot):
    """The same facts as JSON, beside the PNG.

    A card is a picture, and a picture cannot be searched. The scan window
    wants to know which bodies in this system have been marked, and reading
    that out of a filename means parsing a body name that had its spaces
    replaced and a material that was lowercased - both lossy, both guesses.

    Failing to write it costs a link in a window. The card is the record, so
    it is not worth taking the card down for.
    """
    record = {key: (None if value is None else
                    value if isinstance(value, (int, float, str)) else str(value))
              for key, value in spot.items()}
    record["card"] = os.path.basename(card_path)
    try:
        with open(os.path.splitext(card_path)[0] + ".json", "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=1)
    except OSError:
        pass


def _free(path):
    """The first free name at `path`, counting up: card.png, card_2.png, ...

    Two marks of the same location for the same material are two cards. They
    were the same file, and the second one silently replaced the first - which
    is the wrong way round, because the reason to mark a patch twice is that
    something about it differed. The plain name stays on the first card so
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
    gets a counter from _free rather than landing on the card already there."""
    parts = [spot.get("planet_name") or "spot",
             f"loc{_fmt(spot.get('location_index'), dash='x')}",
             (spot.get("commodity") or "unknown").lower()]
    return names.safe("_".join(parts), spaces=False) + ".png"
