"""Render one marked mining spot as a PNG card.

Same palette as the scan window - see rs_core/palette.py - so a card dropped
into a chat beside a screenshot of the window looks like the same tool. PIL
ships inside EDMC, so nothing extra is vendored for this.

The card is the whole record: what was marked is what it shows. Nothing is
looked up, so it renders with nothing else running and no network.
"""

import os

from PIL import Image, ImageDraw, ImageFont

from rs_core import palette

# Outside the plugin folder on purpose: cards outlive a plugin reinstall, and
# %LOCALAPPDATA% is somewhere Explorer opens without hunting for it.
CARDS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                          or os.path.expanduser("~"), "RhinoSpotter", "cards")
BAD = r'<>:"/\|?*'


def card_dir(system):
    r"""%LOCALAPPDATA%\RhinoSpotter\cards\<System>\."""
    safe = "".join("_" if ch in BAD else ch for ch in (system or "unknown")).strip() or "unknown"
    return os.path.join(CARDS_ROOT, safe)

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


def _coords(spot):
    lat, lon = spot.get("latitude"), spot.get("longitude")
    if lat is None or lon is None:
        return "not on the surface when marked"
    return f"{float(lat):.6f} / {float(lon):.6f}"


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

    cells = [
        ("Rigs", _fmt(spot.get("rigs"))),
        ("Location", _fmt(spot.get("location_index"))),
        ("Heading", _fmt(spot.get("heading"), "°")),
        ("Altitude", _fmt(f"{float(spot['altitude']):.0f}" if spot.get("altitude") is not None else None, " m")),
    ]
    grid_x = x + 340
    for index, (key, value) in enumerate(cells):
        col, line = index % 2, index // 2
        cx = grid_x + col * 250
        cy = y + line * 34
        draw.text((cx, cy), key.upper(), font=mono_small, fill=MUTED)
        draw.text((cx + 96, cy - 2), value, font=mono, fill=INK)

    y += 78
    draw.line([x, y, right, y], fill=RULE)
    y += 18

    draw.text((x, y), _coords(spot), font=mono, fill=SECOND)
    marked = spot.get("marked_at")
    if marked:
        stamp = str(marked).split(".")[0]
        draw.text((right - draw.textlength(stamp, font=mono_small), y + 3),
                  stamp, font=mono_small, fill=MUTED)
    if spot.get("commander"):
        draw.text((x, y + 24), "CMDR " + spot["commander"], font=mono_small, fill=MUTED)

    if out_path is None:
        out_path = _free(os.path.join(card_dir(spot.get("system")), filename(spot)))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    image.save(out_path)
    return out_path


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
    stem = "_".join(parts)
    return "".join("_" if ch in BAD or ch == " " else ch for ch in stem) + ".png"
