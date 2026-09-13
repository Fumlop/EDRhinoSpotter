r"""A name Windows will accept as a file or a folder.

Three places need one - the folder a card goes in, the card's own file name,
and the cache file for a system - and all three have to agree. They were three
copies of the same loop, and a system that is safe in one and not in another
is a card that cannot find its own cache.

No tkinter and no PIL. See rs_tests/test_names.py.
"""

# What Windows refuses in a path segment. Real system names carry some of them:
# "Col 285 Sector KM-V d2-36" is fine, one with a colon in it is not, and one
# bad system must not take the whole cache down.
BAD = r'<>:"/\|?*'


def safe(text, spaces=True, fallback="unknown"):
    r"""`text` with everything Windows refuses replaced by an underscore.

    `spaces=False` replaces those too, which is what a file name wants and a
    folder name does not: the folder is what Explorer shows, and
    `Col_285_Sector_LS-P_b7-1` is harder to read there than the name the game
    uses.
    """
    refused = BAD if spaces else BAD + " "
    cleaned = "".join("_" if ch in refused else ch for ch in (text or "")).strip()
    return cleaned or fallback
