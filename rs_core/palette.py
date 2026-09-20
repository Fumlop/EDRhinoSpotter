"""Colour constants for the tkinter windows and the PIL-rendered cards.

Values are hex strings for tkinter; rgb() converts to tuples for PIL. rgb() is
the only conversion point.

No tkinter or PIL imports, so both sides can import this. Tests in
rs_tests/test_palette.py.
"""

# Window background, and the panel drawn on it.
BG = "#0f1419"
PANEL = "#151c24"

# Text: primary, secondary, tertiary.
FG = "#e8f2ff"
FG_SOFT = "#b8d4f0"
MUTED = "#7c95b8"

# 1 px rules and widget borders.
RULE = "#2a3744"

# Emphasis: material names, body types, heading rules.
ACCENT = "#87ceeb"

# Status colours. GOOD also draws bookmark coordinates.
GOOD = "#69db7c"
WARN = "#ffd43b"
ALERT = "#ff8080"

# Bookmark groups from coverage.golden_groups.
GOLD = "#f5c542"


def rgb(colour):
    """'#87ceeb' -> (135, 206, 235). Raises ValueError on anything else.

    The only hex-to-RGB conversion in the plugin.
    """
    value = colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"not a six-digit hex colour: {colour!r}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
