r"""A name Windows will accept as a file or a folder.

The folder an old card sits in and the folder a map's pictures go in both
need one. It was three copies of the same loop, back when the card's file name
and the cache file for a system needed it too.

No tkinter and no PIL. See rs_tests/test_names.py.
"""

# What Windows refuses in a path segment. Real system names carry some of them:
# "Col 285 Sector KM-V d2-36" is fine, one with a colon in it is not, and one
# bad system must not take the whole cache down.
BAD = r'<>:"/\|?*'


def safe(text, fallback="unknown"):
    r"""`text` with everything Windows refuses replaced by an underscore.

    Spaces stay: the folder is what Explorer shows, and
    `Col_285_Sector_LS-P_b7-1` is harder to read there than the name the game
    uses.
    """
    cleaned = "".join("_" if ch in BAD else ch for ch in (text or "")).strip()
    return cleaned or fallback
