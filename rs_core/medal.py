"""Rig-count medal, 16 px: 4 rigs BRONZE, 5 SILVER, 6-7 GOLD, the count inside.

Digits are 3 x 5 cell bitmaps: fonts differ per OS at 16 px. No tkinter.
"""

from PIL import Image, ImageDraw

from rs_core import palette

SIZE = 16           # px, square, as thumb.SIZE
SS = 4              # drawn at SIZE * SS and resized down: the anti-aliased edge
MIN_RIGS = 4

COLOUR = {4: palette.BRONZE, 5: palette.SILVER}     # 6+: palette.GOLD

# 3 x 5 cells, row by row, '#' filled.
DIGITS = {
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", "..#", "..#"),
}
CELL = 6            # px of a digit cell on the 64 px grid: digit 18 x 30


def colour(rigs):
    """Medal colour for a rig count, or None under MIN_RIGS or unknown."""
    if not isinstance(rigs, int) or rigs < MIN_RIGS:
        return None
    return COLOUR.get(rigs, palette.GOLD)


def image(rigs, background=palette.BG):
    """The medal for `rigs` on `background`, SIZE x SIZE RGB, or None under MIN_RIGS."""
    fill = colour(rigs)
    if fill is None:
        return None
    big = SIZE * SS
    picture = Image.new("RGB", (big, big), palette.rgb(background))
    draw = ImageDraw.Draw(picture)
    draw.ellipse((2, 2, big - 3, big - 3), outline=palette.rgb(fill), width=5)
    draw.ellipse((11, 11, big - 12, big - 12), fill=palette.rgb(fill))
    x0, y0 = (big - 3 * CELL) // 2, (big - 5 * CELL) // 2
    for row, line in enumerate(DIGITS[str(min(rigs, max(map(int, DIGITS))))]):
        for col, cell in enumerate(line):
            if cell == "#":
                x, y = x0 + col * CELL, y0 + row * CELL
                draw.rectangle((x, y, x + CELL - 1, y + CELL - 1), fill=palette.rgb(background))
    return picture.resize((SIZE, SIZE), Image.LANCZOS)
