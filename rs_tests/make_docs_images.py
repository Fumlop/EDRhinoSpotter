"""Re-render every picture in the docs, from the code as it stands.

    python rs_tests/make_docs_images.py

Run it after anything that changes how the panel, the window or a card looks.
A README showing last month's layout is worse than one showing none.

Invented system, invented commander. A screenshot in a public repo is
somebody's flight log otherwise, and the numbers here only have to be
plausible.
"""

import os
import sys
import time
import tkinter as tk

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

from PIL import ImageGrab                                   # noqa: E402

from rs_core import bodies, spotcard                        # noqa: E402
from rs_ui import main, scan                                # noqa: E402

DOCS = os.path.join(PLUGIN_DIR, "docs")
SYSTEM = "Hyperion Reach AB-C d1-42"
BODIES = [
    ("6 a", "high-metal-content",  210.0,   14, ""),
    ("6 b", "high-metal-content",  214.0, None, ""),
    ("1 a", "volcanic magma",      412.0,   19, "major metallic magma"),
    ("1 b", "volcanic magma",      418.0,    8, "minor metallic magma"),
    ("2 a", "volcanic magma",      903.0,   12, "major rocky magma"),
    ("4 a", "volcanic silicate",  1284.0,   22, "major silicate vapour geysers"),
    ("4 c", "volcanic silicate",  1291.0,    9, "minor silicate vapour geysers"),
    ("9 a", "rocky",              2165.0,   13, ""),
    ("9 b", "rocky",              2168.0,   10, ""),
    ("9 c", "rocky",              2172.0, None, ""),
]


def settle(window, ticks=40):
    """Tk lays out on idle, and a grab of a window mid-layout is a grab of
    whatever was behind it."""
    for _ in range(ticks):
        window.update_idletasks()
        window.update()
        time.sleep(0.03)


def grab(window, name, scale, top_margin=0):
    """Save a window, in physical pixels.

    Tk reports logical units and ImageGrab works in physical ones. On a display
    at 125% those differ, and every "the text is cut off" in this project so
    far was this and not the layout.
    """
    x, y = window.winfo_rootx(), window.winfo_rooty()
    w, h = window.winfo_width(), window.winfo_height()
    box = (int(x * scale), int((y - top_margin) * scale),
           int((x + w) * scale), int((y + h + 6) * scale))
    path = os.path.join(DOCS, name)
    ImageGrab.grab(bbox=box).save(path)
    print(f"{name:<18} {w}x{h}")
    return path


def register():
    found = bodies.Register()
    found.adopt(SYSTEM, [{"name": f"{SYSTEM} {n}", "ground": g, "distance": ls,
                          "locations": loc, "volcanism": v,
                          "planet_class": "Rocky body"}
                         for n, g, ls, loc, v in BODIES])
    return found


def main_images():
    os.makedirs(DOCS, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    scale = ImageGrab.grab().width / root.winfo_screenwidth()
    main.start(PLUGIN_DIR)
    sheet = main._sheet

    # The panel, with something picked - an empty one shows nothing of what it
    # does with a material.
    panel = tk.Toplevel(root)
    panel.configure(bg="#0a0a0a")
    panel.attributes("-topmost", True)
    main.build(panel).pack(padx=10, pady=10)
    panel.deiconify()
    panel.lift()
    settle(panel, 25)
    main._material.set("Monazite")
    main._loc.set("22")
    main._rigs.set("4")
    settle(panel, 15)
    grab(panel, "plugin.png", scale)
    panel.destroy()

    found = register()
    picker = ("All",) + tuple(("Alexandrite", "Jadeite", "Monazite", "Olivine"))
    for focus, name in ((None, "rhinoscan.png"), ("Monazite", "rhinoscan-filtered.png")):
        main._material.set(focus or "All")
        window = scan.show(root, found, sheet, focus,
                           variable=main._material, materials=picker)
        window.attributes("-topmost", True)
        window.deiconify()
        window.lift()
        settle(window)
        grab(window, name, scale, top_margin=34)
        window.destroy()

    spotcard.render({
        "system": SYSTEM, "planet_name": f"{SYSTEM} 4 a", "location_index": 22,
        "commodity": "Jadeite", "rigs": 4, "heading": 214,
        "latitude": 12.345678, "longitude": -98.765432,
        "marked_at": "3311-05-14T18:40:00", "commander": "Example",
    }, os.path.join(DOCS, "miningcard.png"))
    print(f"{'miningcard.png':<18} rendered")
    root.destroy()


if __name__ == "__main__":
    main_images()
