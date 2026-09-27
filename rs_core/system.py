"""What RhinoSpotter runs on, read once at import.

    WINDOWS / LINUX   sys.platform
    FLATPAK           /.flatpak-info exists (EDMC from Flathub)
    SESSION           XDG_SESSION_TYPE: "wayland", "x11", "" (Windows, or unset)

describe() is the one line main.start logs, for bug reports.

No tkinter.
"""

import os
import sys

WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
FLATPAK = LINUX and os.path.exists("/.flatpak-info")
SESSION = os.environ.get("XDG_SESSION_TYPE", "") if LINUX else ""


def describe():
    """'Windows', 'Linux (wayland, Flatpak)', ..."""
    if WINDOWS:
        return "Windows"
    extras = [part for part in (SESSION, "Flatpak" if FLATPAK else "") if part]
    name = "Linux" if LINUX else sys.platform
    return f"{name} ({', '.join(extras)})" if extras else name
