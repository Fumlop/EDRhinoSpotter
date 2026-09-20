r"""System and body names -> path segments Windows accepts.

Used for the card folder and the map picture folder.

No tkinter or PIL. Tests in rs_tests/test_names.py.
"""

# Characters Windows refuses in a path segment. Some system names contain
# them, so every segment is filtered rather than validated.
BAD = r'<>:"/\|?*'


def safe(text, fallback="unknown"):
    r"""`text` with every BAD character replaced by '_', trimmed.

    Spaces are kept. Empty or whitespace-only input returns `fallback`.
    """
    cleaned = "".join("_" if ch in BAD else ch for ch in (text or "")).strip()
    return cleaned or fallback
