"""Re-render every picture in the docs, from the code as it stands.

    set RHINOSPOTTER_DOCS=1
    python rs_tests/make_docs_images.py

Behind a variable and deliberately not written up anywhere a user would look.
It is maintenance tooling: it drives real windows, grabs the screen, and is of
no use to anyone running the plugin. Guarded so that neither a stray run nor a
reviewer reading the tree mistakes it for something the plugin does.

Run it after anything that changes how the panel, the window or a card looks.
A README showing last month's layout is worse than one showing none.

Invented system, invented commander. A screenshot in a public repo is
somebody's flight log otherwise, and the numbers here only have to be
plausible.
"""

import math
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)

from PIL import Image, ImageGrab                            # noqa: E402

from rs_core import bodies, coverage, coverstore, database, spotmark  # noqa: E402
from rs_ui import main, minimap, overlay, scan              # noqa: E402

DOCS = os.path.join(PLUGIN_DIR, "docs")
SYSTEM = "Hyperion Reach AB-C d1-42"
BODIES = [
    ("6 a", "high-metal-content",  210.0,   14, ""),
    ("6 b", "high-metal-content",  214.0, None, ""),
    ("1 a", "rock 80%+ [metallic magma]",      412.0,   19, "major metallic magma"),
    ("1 b", "rock 80%+ [metallic magma]",      418.0,    8, "minor metallic magma"),
    ("2 a", "rock 80%+ [rocky magma]",         903.0,   12, "major rocky magma"),
    ("4 a", "rock 80%+ [silicate vapour geysers]",  1284.0,   22, "major silicate vapour geysers"),
    ("4 c", "rock 80%+ [silicate vapour geysers]",  1291.0,    9, "minor silicate vapour geysers"),
    ("9 a", "rock 80%+ [none]",              2165.0,   13, ""),
    ("9 b", "rock 80%+ [none]",              2168.0,   10, ""),
    ("9 c", "rock 80%+ [none]",              2172.0, None, ""),
]


# Three bookmarks on one body, for the picture of the bookmark list. Invented
# like everything else here: the coordinates are somebody's flight log.
def bookmarks(body, card):
    return [
        {"system": SYSTEM, "planet_name": body, "location_index": 22,
         "commodity": "Jadeite", "rigs": 4, "heading": 214,
         "density": "Low", "amount": "High",
         "latitude": 12.345678, "longitude": -98.765432,
         "marked_at": "3311-05-14T18:40:00", "path": card},
        {"system": SYSTEM, "planet_name": body, "location_index": 9,
         "commodity": "Monazite", "rigs": 2, "heading": 77,
         "density": "Medium", "amount": "Low",
         "latitude": 12.401233, "longitude": -98.712001,
         "marked_at": "3311-05-14T19:12:44", "path": card},
        {"system": SYSTEM, "planet_name": body, "location_index": 15,
         "commodity": "Olivine", "rigs": None, "heading": None,
         "latitude": 12.388910, "longitude": -98.690004,
         "marked_at": "3311-05-15T08:02:10", "path": card},
    ]


# Maps on the bookmarked body, for "Mapped 3/22" and its page. Two sit on the
# bookmarks - one saved with the location targeted, one tied only by the
# bookmarks on it - and one lies away from all of them, so the page shows its
# "location unknown" section too. Written into the scratch database and coverage
# folder and removed again before the minimap pictures, which must not find them.
RADIUS_4A = 1352744.5

# The bookmarks on the map pictures: metres east and north of the drive's
# origin, the code the sheet gives the material, whether it is mined out, what
# it is worth, and what the saved map's legend says about it.
#
# Two pairs of one material and three prices, so both kinds of line have
# something to draw: solid between the two Thortveitite and the two Monazite,
# dotted from each of them down to the next material worth less.
SPOTS = [
    (2400, 400, "T", False, 940000, "Thortveitite", 2),
    (600, -300, "T", False, 940000, "Thortveitite", 4),
    (1900, -6100, "MZ", False, 460000, "Monazite", 3),
    (-1500, -5600, "MZ", False, 460000, "Monazite", 2),
    (-900, -6300, "PL", True, 180000, "Platinum", 3),
]


def plant_maps(body):
    from PIL import Image
    for name, lat, lon, location in (("map 1", 12.345678, -98.765432, None),
                                     ("map 2", 12.401233, -98.712001, 9),
                                     ("map 3", 12.910000, -98.100000, None)):
        data = coverage.Coverage(body, lat, lon, RADIUS_4A).to_dict()
        data["location"] = location
        coverstore.save(body, name, data)
        coverstore.save_png(body, name, Image.new("RGB", (8, 8)))


def settle(window, ticks=40):
    """Tk lays out on idle, and a grab of a window mid-layout is a grab of
    whatever was behind it."""
    for _ in range(ticks):
        window.update_idletasks()
        window.update()
        time.sleep(0.03)


def grab(window, name, scale, top_margin=0, bottom=6):
    """Save a window, in physical pixels.

    Tk reports logical units and ImageGrab works in physical ones. On a display
    at 125% those differ, and every "the text is cut off" in this project so
    far was this and not the layout.
    """
    x, y = window.winfo_rootx(), window.winfo_rooty()
    w, h = window.winfo_width(), window.winfo_height()
    box = (int(x * scale), int((y - top_margin) * scale),
           int((x + w) * scale), int((y + h + bottom) * scale))
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
    # A plain screen behind everything grabbed. The grab box reaches past the
    # window's edges for the title bar and the corners, and without this they
    # carried whatever was open behind - the terminal running this, into a
    # public README.
    backdrop = tk.Toplevel(root)
    backdrop.configure(bg="#0a0a0a")
    backdrop.overrideredirect(True)
    backdrop.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
    # Pinned on top once, then released: that puts it above every other
    # program, and the windows built after it still stack above it.
    backdrop.attributes("-topmost", True)
    settle(backdrop, 5)
    backdrop.attributes("-topmost", False)
    settle(backdrop, 5)
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
    main._amount.set("High")
    main._density.set("Low")
    settle(panel, 15)
    # No shadow margin under this one: the panel has no menu to cast one, and
    # those few pixels are whatever else is on the desktop.
    grab(panel, "plugin.png", scale, bottom=0)
    panel.destroy()

    found = register()
    plant_maps(f"{SYSTEM} 4 a")
    # The body list reads bookmarks off disk, which holds the commander's own.
    # The invented ones stand in, so the row reads "3 bookmarks  Mapped 3/22"
    # like the pages behind it.
    from rs_core import cards
    was_by_body = cards.by_body
    cards.by_body = lambda system: {f"{SYSTEM} 4 a": bookmarks(f"{SYSTEM} 4 a", None)}
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

    card = None             # bookmarks carry no card image any more

    body = f"{SYSTEM} 4 a"
    marks = bookmarks(body, card)

    # The material back to All first, and its trace let through before
    # anything is built. The panel reopens the scan window when the material
    # changes, and that was destroying the window this grabs, halfway
    # through settling it.
    main._material.set("All")
    settle(root, 10)

    scan.show(root, found, sheet, None,
              variable=main._material, materials=picker)
    window = scan._window
    # Standing on the body among the three bookmarks, so the Distance column
    # has something to say. The real Status.json would put every row at "-",
    # or worse, be read at all.
    was_status = spotmark.read_status
    spotmark.read_status = lambda *args, **kwargs: {
        "BodyName": body, "Latitude": 12.37, "Longitude": -98.74,
        "PlanetRadius": RADIUS_4A, "Heading": 90}
    scan._bookmarks_view(window, SYSTEM, body, marks)
    window.attributes("-topmost", True)
    window.deiconify()
    window.lift()
    settle(window)
    grab(window, "bookmarks.png", scale, top_margin=34)
    window.destroy()
    spotmark.read_status = was_status

    scan.show(root, found, sheet, None,
              variable=main._material, materials=picker)
    window = scan._window
    scan._mapped_view(window, body, 22, marks)
    window.attributes("-topmost", True)
    window.deiconify()
    window.lift()
    settle(window)
    grab(window, "mapped.png", scale, top_margin=34)
    window.destroy()
    shutil.rmtree(coverstore.folder(body), ignore_errors=True)
    with database.connect() as conn:
        conn.execute("DELETE FROM maps WHERE body = ?", (body,))
    cards.by_body = was_by_body

    overlay_image(root, scale, marks[0])
    minimap_image(root, scale)
    backdrop.destroy()
    root.destroy()


def overlay_image(root, scale, mark):
    """The arrow, over a dark rectangle standing in for the cockpit.

    The overlay is transparent, so a grab of it is a grab of whatever is
    behind it - which on this machine is an editor. A backdrop keeps the
    picture about the arrow.
    """
    # Elite off, as far as the overlay is concerned. With the game running it
    # parks itself over the game window, and the picture would be half a
    # cockpit that is not ours to publish. Off, it falls back to the middle of
    # the screen, which is where the backdrop goes.
    was_rect = overlay._game_rect
    overlay._game_rect = lambda: None
    was = spotmark.read_status
    spotmark.read_status = lambda *args, **kwargs: {
        "BodyName": mark["planet_name"], "Latitude": 12.3400,
        "Longitude": -98.7700, "Heading": 95, "Altitude": 140.0,
        "PlanetRadius": 1738000.0,
    }
    backdrop = tk.Toplevel(root)
    backdrop.overrideredirect(True)
    backdrop.configure(bg="#05070a")
    backdrop.attributes("-topmost", True)
    backdrop.geometry(f"{overlay.WIDTH + 80}x{overlay.HEIGHT + 60}"
                      f"+{(root.winfo_screenwidth() - overlay.WIDTH) // 2 - 40}+10")
    backdrop.deiconify()
    settle(backdrop, 10)

    window = overlay.start(root, mark)
    settle(window, 20)

    # The backdrop under where the overlay actually landed, not where it was
    # guessed to land: the overlay parks itself on the Elite window if one is
    # running, and a picture half on the dark rectangle is worse than none.
    window.lift()
    settle(window, 10)
    grab(window, "guide.png", scale)
    overlay.stop()
    backdrop.destroy()
    spotmark.read_status = was
    overlay._game_rect = was_rect


def minimap_image(root, scale):
    """The minimap after three launches with two ship hops between them, fed
    invented Status.json readings.

    A pretend 1080p game window at the top left of the screen, so the map comes
    out the size most people will see it at and not whatever this monitor is.
    """
    was_rect = overlay._game_rect
    overlay._game_rect = lambda: (0, 0, 1920, 1080)
    # Opaque for the picture: at the real 85% the grab carries whatever window
    # is behind the map.
    was_alpha, minimap.MAP_ALPHA = minimap.MAP_ALPHA, 1.0
    radius = 1738000.0
    per_degree = radius * math.pi / 180.0
    lat0, lon0 = 12.3400, -98.7700
    launches = [
        [(0, 0), (1500, 2200), (3200, 2600), (2600, 400)],
        [(6500, -2500), (8200, -1200), (9000, -3600), (7200, -4400)],
        [(1500, -6000), (-600, -7400), (-1800, -5200), (400, -4300)],
    ]

    def reading(x, y, heading, flags):
        return {
            "Flags": flags, "BodyName": f"{SYSTEM} 4 a",
            "Latitude": lat0 + y / per_degree,
            "Longitude": lon0 + x / (per_degree * math.cos(math.radians(lat0))),
            "Heading": heading, "PlanetRadius": radius,
            "Destination": {"Name": "$SAA_Unknown_Signal:#index=22;"},
        }

    # Five bookmarks on the body, where the drive went past them - about what a
    # location holds once its worthwhile materials are marked. Two would draw
    # the distance lines without showing what they look like in the way.
    was_marks = minimap._bookmarks
    minimap._bookmarks = lambda system, body: [
        (reading(x, y, 0, 0)["Latitude"], reading(x, y, 0, 0)["Longitude"], code, depleted, value)
        for x, y, code, depleted, value, _, _ in SPOTS]

    for track in launches:
        for (x1, y1), (x2, y2) in zip(track, track[1:]):
            steps = int(math.hypot(x2 - x1, y2 - y1) // 30)
            heading = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 360
            for i in range(steps + 1):
                minimap.update(root, reading(x1 + (x2 - x1) * i / steps,
                                             y1 + (y2 - y1) * i / steps,
                                             heading, minimap.coverage.IN_SRV), SYSTEM)
        if track is not launches[-1]:
            # Back in the ship for the hop: nothing painted until the next launch.
            minimap.update(root, reading(*track[-1], 0, 0x1000000), SYSTEM)

    # Three pictures of the same drive: as it is, after the centre hotkey in
    # the middle of it, and after the border hotkey at its southern edge. One
    # more fix after each press so the map draws what it did.
    last = launches[-1][-1]

    def shoot(name):
        minimap.update(root, reading(*last, 0, minimap.coverage.IN_SRV), SYSTEM)
        window = minimap._window
        settle(window, 20)
        path = grab(window, name, scale)
        # grab() takes 6 px under the window for menu shadows. The map is a
        # solid panel with none, and those 6 px are whatever desktop is behind.
        shot = Image.open(path)
        shot.crop((0, 0, shot.width, shot.height - int(6 * scale))).save(path)

    def press(x, y, hotkey):
        minimap._here = (reading(x, y, 0, 0)["Latitude"], reading(x, y, 0, 0)["Longitude"])
        hotkey()

    shoot("minimap.png")
    press(2500, -2500, minimap.center_here)
    shoot("minimap-center.png")
    press(2500, -8500, minimap.border_here)
    shoot("minimap-border.png")

    # The second press: twice the size, and the step that draws the lines
    # between the bookmarks at all. Patched rather than pressed - zoom() and
    # _distances_shown() read EDMC's config, which is not here.
    was_zoom, was_shown = minimap.zoom, minimap._distances_shown
    minimap.zoom, minimap._distances_shown = lambda: coverage.MAP_ZOOMS[1], lambda: True
    minimap._placed = minimap._drawn = None
    shoot("minimap-big.png")
    minimap.zoom, minimap._distances_shown = was_zoom, was_shown
    minimap._placed = minimap._drawn = None

    # The same drive as a shared map picture, with the title and legend the
    # plugin writes. Spelled out rather than read from cards and the system
    # cache, which hold the commander's own flights.
    cover = minimap._coverage
    marks, legend = [], []
    for x, y, code, depleted, _, material, rigs in SPOTS:
        at = reading(x, y, 0, 0)
        marks.append((*cover.xy(at["Latitude"], at["Longitude"]), code, depleted))
        legend.append((code, f"{material}  ·  {at['Latitude']:.6f} / {at['Longitude']:.6f}"
                             f"  ·  {rigs} rigs" + ("  ·  depleted" if depleted else ""), depleted))
    centre = cover.origin
    title = ["4 a  -  " + SYSTEM, "Rocky World  ·  0.16 g  ·  1,284 Ls  ·  22 locations",
             f"map 1  ·  loc 22  ·  center {centre[0]:.6f} / {centre[1]:.6f}  ·  border 6.0 km",
             f"{cover.painted_km2():.0f} km² prospected  ·  3311-05-14 18:40"]
    coverage.picture(cover.mask, marks, title, legend, cover.border_m).save(
        os.path.join(DOCS, "mapshare.png"))
    print(f"{'mapshare.png':<18} rendered")
    minimap.stop()
    minimap._bookmarks = was_marks
    minimap.MAP_ALPHA = was_alpha
    overlay._game_rect = was_rect

if __name__ == "__main__":
    if not os.environ.get("RHINOSPOTTER_DOCS"):
        raise SystemExit("set RHINOSPOTTER_DOCS=1 to re-render the docs images")
    # Before anything builds the panel: its poll feeds the real Status.json to
    # the minimap, and neither that nor the invented body may save maps into
    # the commander's folder.
    with tempfile.TemporaryDirectory(prefix="rhinospotter-docs-") as scratch:
        coverstore.ROOT = scratch
        database.PATH = os.path.join(scratch, "rhinospotter.db")
        # The overlays hide while Elite is not the window in front, and while
        # this runs the terminal that started it is.
        overlay.game_focused = lambda: True
        main_images()
