"""Thumb up / thumb down icons for the location line's mark buttons.

Drawn with PIL instead of the 👍 / 👎 emoji: Tk 8.6 draws an emoji only with a
colour emoji font, Segoe UI Emoji on Windows, none fixed on Linux.

No tkinter - rs_ui/scan.py converts what comes out of here.
"""

from PIL import Image, ImageDraw

from rs_core import palette

SIZE = 16           # px, square
SS = 4              # drawn at SIZE * SS and resized down: the anti-aliased edge

# On a 64 x 64 grid (SIZE * SS), y down, for the thumb up:
# (x0, y0, x1, y1, corner radius).
CUFF = (4, 30, 15, 60, 3)
FIST = (19, 28, 59, 60, 8)
THUMB = (21, 3, 37, 36, 8)
# Gaps between the fingers: y, from x 38 to the fist's right edge, 3 px wide.
FINGER_GAPS = (36, 44, 52)


def image(colour, down=False, background=palette.BG):
    """The thumb in `colour` on `background`, SIZE x SIZE RGB. `down`: thumb down."""
    big = SIZE * SS
    picture = Image.new("RGB", (big, big), palette.rgb(background))
    draw = ImageDraw.Draw(picture)
    fill, gap = palette.rgb(colour), palette.rgb(background)
    for x0, y0, x1, y1, radius in (CUFF, FIST, THUMB):
        draw.rounded_rectangle((x0, y0, x1, y1), radius, fill=fill)
    for y in FINGER_GAPS:
        draw.line((38, y, FIST[2], y), fill=gap, width=3)
    if down:
        picture = picture.transpose(Image.FLIP_TOP_BOTTOM)
    return picture.resize((SIZE, SIZE), Image.LANCZOS)
