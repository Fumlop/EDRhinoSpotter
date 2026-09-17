"""The rhino, running across the bottom of the window.

Nothing in here is load-bearing. Click the system name and the picture from
the README gallops across the window, bobbing, and takes itself down at the
far edge. Every failure is swallowed and logged at debug: an easter egg that
can break a mining tool is not an easter egg.

One at a time, and it is placed over the window with `place` rather than
packed into it, so nothing in the layout moves to let it past.
"""

import io
import os
import tkinter as tk

from PIL import Image

from rs_core import palette
from rs_core.logging import logger

IMAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs", "running.png")
STEP_MS = 30             # about thirty frames a second
STEP_PX = 5              # how far it gets per frame - a window in four seconds
HEIGHT = 64              # how tall it runs
# The gallop: pixels off the baseline, one per frame, round and round.
BOB = (0, -2, -4, -5, -4, -2, 0, 1, 2, 1)
MARGIN = 10              # how far off the bottom edge it runs

_running = False


def _flattened():
    """The picture as PNG bytes, onto the window's own background.

    Handed to Tk flat rather than as the RGBA file it is. Tk does have alpha,
    but what it composites a half-transparent edge against is not the label's
    background, so the rhino ran around inside a visible box. Mixed here
    against the one colour the window is, the box is the window.

    Cropped to what is actually drawn first - most of the file is empty
    corners, and those corners are what the box was made of.
    """
    picture = Image.open(IMAGE).convert("RGBA")
    box = picture.getbbox()
    if box:
        picture = picture.crop(box)
    width = max(1, round(picture.width * HEIGHT / picture.height))
    picture = picture.resize((width, HEIGHT), Image.LANCZOS)
    flat = Image.new("RGBA", picture.size, palette.BG)
    flat.alpha_composite(picture)
    out = io.BytesIO()
    flat.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def run(window):
    """Send it across `window`, once. A second call while one is running is
    ignored rather than queued - two rhinos is a bug, not twice the joke."""
    global _running
    if _running:
        return
    try:
        picture = tk.PhotoImage(master=window, data=_flattened())
        label = tk.Label(window, image=picture, bg=palette.BG,
                         borderwidth=0, highlightthickness=0)
        # Kept on the label: Tk drops an image nothing holds a reference to
        # and draws an empty box where it was.
        label.image = picture
    except (tk.TclError, OSError, ValueError) as err:
        logger.debug(f"rhino: not today - {err}")
        return

    _running = True
    window.update_idletasks()
    width = window.winfo_width()
    baseline = window.winfo_height() - picture.height() - MARGIN

    def step(x, frame):
        global _running
        try:
            if x > width:
                label.destroy()
                _running = False
                return
            label.place(x=x, y=baseline + BOB[frame % len(BOB)])
            window.after(STEP_MS, step, x + STEP_PX, frame + 1)
        except tk.TclError:
            # The window went while it was running. Nothing to clean up that
            # the window did not take with it.
            _running = False

    logger.debug("rhino: running")
    step(-picture.width(), 0)
