"""One palette, for the window and for the cards.

They were two: the scan window took a cold blue, and the cards had a warm
olive-and-orange scheme left over from the notebook they were prototyped
in. Side by side they looked like two tools, which is exactly what a card
dropped into a chat next to a screenshot of the window is not.

Hex for tkinter, which wants "#87ceeb". RGB tuples for PIL, which wants
(135, 206, 235). Same numbers either way - `rgb()` is the only place a colour
is ever converted, so the two can never drift.

No tkinter and no PIL in here, so both sides can import it and the values can
be checked without either. See rs_tests/test_palette.py.
"""

# The ground everything sits on, and the panel that sits on it.
BG = "#0f1419"
PANEL = "#151c24"

# Text, in the three weights the design uses: what you read, what qualifies
# it, and what is only there so the layout does not look unfinished.
FG = "#e8f2ff"
FG_SOFT = "#b8d4f0"
MUTED = "#7c95b8"

# Hairlines and borders. Dark enough to separate, not dark enough to draw.
RULE = "#2a3744"

# The one colour that means "this is the thing": the material on a card, the
# body type in the window, the rule under a heading.
ACCENT = "#87ceeb"

# Verdicts. Good is also what coordinates are drawn in - a mark you can fly
# back to is the good outcome of pressing the button.
GOOD = "#69db7c"
WARN = "#ffd43b"
ALERT = "#ff8080"

# A group of bookmarks worth a whole stop of the Rhino - see coverage.golden_groups.
GOLD = "#f5c542"


def rgb(colour):
    """'#87ceeb' -> (135, 206, 235), for PIL.

    The only place a colour is converted, so the card and the window cannot
    drift apart by one of them being edited and the other forgotten.
    """
    value = colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"not a six-digit hex colour: {colour!r}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
