"""The guide arrow, drawn as a folded shape rather than a flat triangle.

Tk's canvas has no anti-aliasing and no gradients, so a triangle drawn there is
a triangle with a staircase down both sides - at the size this is shown, two
shaded canvas polygons read as a broken shape rather than as depth. PIL has
both, and it is already in the plugin for the cards, so the arrow is rendered
here and the overlay only puts the picture on the screen.

One frame per STEP degrees, rendered the first time that angle is asked for
and kept. Turning through a full circle costs 72 renders and then nothing; a
frame is about 2 ms, which is why they are not all built at startup.

The fold is fixed to the shape, not to the screen: the left face is always the
lit one and the whole thing turns together. A light fixed in the window
instead would have the faces swapping brightness as the arrow came round,
which reads as flicker rather than as a solid object.

No tkinter - the overlay converts what comes out of here. See
rs_tests/test_arrow.py.
"""

import math

from PIL import Image, ImageDraw

from rs_core import palette

# The frame, in pixels, and how much of it the arrow fills. 0.46 puts the
# shape at the size the canvas polygon used to be drawn at.
SIZE = 120
SCALE = 0.46

# Degrees between frames. Five is below what anyone reads off an arrow, and it
# caps the cache at 72 pictures per colour.
STEP = 5
STEPS = 360 // STEP

# Drawn this many times over and resized down, which is where the smooth edge
# comes from. Four is the point past which the result stops changing.
SS = 4

# The colour the overlay window makes a hole of. Nothing drawn may land on it,
# which is what the floor in _tone is for.
KEY = "#010101"

# The two faces, either side of the fold. Same outline as the flat arrow it
# replaces: tip, tail corner, notch.
LEFT = ((0.0, -1.0), (0.0, 0.42), (-0.62, 0.82))
RIGHT = ((0.0, -1.0), (0.62, 0.82), (0.0, 0.42))

# What the fold does to the colour on each side. Far enough apart to read as
# two faces at a glance, near enough that it is still one arrow.
LIT = 1.18
SHADE = 0.5

# No channel goes below this. A face that came out as the key colour would be
# a hole in the middle of the arrow.
FLOOR = 12


def bucket(degrees):
    """Which frame an angle belongs to: 0 to STEPS - 1.

    Rounded rather than floored, so the frame shown is the nearest one and the
    arrow is never off by a whole step in the same direction.
    """
    return int(round((degrees or 0.0) % 360.0 / STEP)) % STEPS


def _tone(colour, factor):
    """One face's colour. Clipped at both ends - white at the top, and the
    floor at the bottom so a face can never be the key colour."""
    return tuple(max(FLOOR, min(255, int(round(channel * factor))))
                 for channel in palette.rgb(colour))


def _points(shape, radians, extent, centre):
    cos, sin = math.cos(radians), math.sin(radians)
    return [(centre + (x * cos - y * sin) * extent,
             centre + (x * sin + y * cos) * extent)
            for x, y in shape]


def frame(degrees, colour=palette.ACCENT, size=SIZE):
    """One arrow, pointing `degrees` clockwise from up, on the key colour.

    Returned as a PIL image on a solid background rather than with an alpha
    channel: the overlay keys one colour out of the whole window, so a picture
    that is transparent where it is empty and opaque where it is not is
    exactly the same picture to it.
    """
    big = size * SS
    image = Image.new("RGB", (big, big), palette.rgb(KEY))
    draw = ImageDraw.Draw(image)
    radians = math.radians(bucket(degrees) * STEP)
    extent = big * SCALE
    # The shaded face first. They share the fold, and the lit one is the shape
    # the eye should find - it goes on top.
    for shape, factor in ((RIGHT, SHADE), (LEFT, LIT)):
        draw.polygon(_points(shape, radians, extent, big / 2),
                     fill=_tone(colour, factor))
    return image.resize((size, size), Image.LANCZOS)
