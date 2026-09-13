"""The minimap: how much ground the Rhino's scanner has been driven over.

Every fix out of Status.json while you are in the SRV stamps a disc of
SCAN_RADIUS_M onto a mask anchored at the droppoint. The discs overlap into one
painted area, and the map shows that area around the SRV, north up.

Painted means driven within scanner range, not scanned. Nothing the game
writes says a scan happened, so the map cannot know, and it does not claim to.

SCAN_RADIUS_M is the community figure - Frontier has not published one. Change
it here and nothing else moves.

Flat earth, through measure.to_metres: REACH_M is 10 km on bodies a thousand
kilometres in radius, and at that distance the projection is off by less than
a disc edge is wide.

No tkinter - rs_ui/minimap.py puts the picture on the screen. See
rs_tests/test_coverage.py.
"""

import math

from PIL import Image, ImageDraw, ImageFilter

from rs_core import arrow, measure, palette, spotcard

# Status.json Flags bit for "in the SRV", as EDMC's edmc_data names it.
IN_SRV = 0x4000000

# What the scanner sees from where the SRV is, in metres.
SCAN_RADIUS_M = 2000.0

# Half the width of what the map shows around the SRV. 12 km across is 50 m a
# pixel on a 1080p map - the mask's own resolution - and a 1 km grid still has
# 20 px between its lines.
VIEW_M = 6000.0

# Half the width of the mask around the droppoint. Few drive further than 6-7
# km from the ship in any direction; 10 km leaves room past that.
REACH_M = 10000.0

# Mask resolution. 50 m a pixel is 400 x 400, 160 KB, and still sharp on a map
# drawn 480 px wide.
MASK_M_PER_PX = 50.0

# A disc every this many metres driven. Two discs 250 m apart leave a 4 m dent
# in the edge between them, which nobody sees at 50 m a pixel.
STAMP_M = 250.0

# Grid lines, pinned to the droppoint so they move with the ground.
GRID_M = 1000.0

# How big the map is drawn, as a share of the game window's height, and the
# limits either side - a laptop window should not get a stamp, a 4K screen
# should not get a poster.
MAP_SHARE = 0.22
MAP_MIN_PX = 180
MAP_MAX_PX = 480

# The layer is drawn twice the size and reduced, for edges that are not
# staircases.
SS = 2

MASK_PX = int(2 * REACH_M / MASK_M_PER_PX)


def srv_fix(status):
    """(body, lat, lon, planet radius, heading) while in the SRV, else None."""
    if not int(status.get("Flags") or 0) & IN_SRV:
        return None
    body = status.get("BodyName")
    lat, lon = status.get("Latitude"), status.get("Longitude")
    radius = status.get("PlanetRadius")
    if not body or lat is None or lon is None or not radius:
        return None
    return body, lat, lon, radius, status.get("Heading")


def map_side(window_height):
    """The map's side in pixels, for a game window this tall."""
    if not window_height:
        return MAP_MIN_PX + (MAP_MAX_PX - MAP_MIN_PX) // 4
    return max(MAP_MIN_PX, min(MAP_MAX_PX, int(round(window_height * MAP_SHARE))))


class Coverage:
    """One droppoint and everything painted around it."""

    def __init__(self, body, lat, lon, radius):
        self.body = body
        self.origin = (lat, lon)
        self.radius = radius
        self.mask = Image.new("L", (MASK_PX, MASK_PX), 0)
        # Goes up only when a disc paints ground that was not painted before.
        # Driving around inside what is already painted leaves it alone, and
        # so leaves the drawn layer alone.
        self.version = 0
        # Where the SRV came out of the ship, in metres from the first of them.
        # The last one is where the ship is now.
        self.drops = [(0.0, 0.0)]
        # What goes to disk: the droppoints, and every point that painted new
        # ground, as (lat, lon). A point that painted nothing new adds nothing
        # to a repaint either.
        self.drop_fixes = [(lat, lon)]
        self.stamps = []
        # The file this map is saved as - coverstore's 'map N' - once it is.
        self.name = None
        # The mining location last targeted on this map. A label, not a key.
        self.location = None
        self._last = None
        self._layer = None      # ((version, drops, side), image)

    def to_dict(self):
        """The map as coverstore writes it. New lists, so a writer on another
        thread never sees one change under it."""
        def points(fixes):
            return [[round(lat, 6), round(lon, 6)] for lat, lon in fixes]
        return {"origin": points([self.origin])[0], "radius": self.radius,
                "location": self.location, "drops": points(self.drop_fixes),
                "stamps": points(self.stamps)}

    @classmethod
    def from_dict(cls, body, data, name=None):
        """A map back from disk, repainted from its points. None when the data
        is not a map."""
        try:
            lat, lon = data["origin"]
            cover = cls(body, float(lat), float(lon), float(data["radius"]))
            for lat, lon in data["stamps"]:
                x, y = cover.xy(float(lat), float(lon))
                if cover._stamp(x, y):
                    cover.stamps.append((float(lat), float(lon)))
            drops = [(float(lat), float(lon)) for lat, lon in data["drops"]]
        except (KeyError, TypeError, ValueError):
            return None
        if drops:
            cover.drop_fixes = drops
            cover.drops = [cover.xy(lat, lon) for lat, lon in drops]
        cover.name = name
        cover.location = data.get("location")
        return cover

    def xy(self, lat, lon):
        """Metres east and north of the first droppoint."""
        # Longitude taken the short way round: a body straddling the 180th
        # meridian is one step across it, not most of the way round the planet.
        lon = self.origin[1] + (lon - self.origin[1] + 180.0) % 360.0 - 180.0
        return measure.to_metres([(lat, lon)], self.radius, origin=self.origin)[0]

    def reaches(self, lat, lon):
        x, y = self.xy(lat, lon)
        return abs(x) <= REACH_M and abs(y) <= REACH_M

    def launched(self, lat, lon):
        """The SRV has come out of the ship again, here. A new droppoint, and
        the first fix is painted rather than measured against where the last
        launch ended - the ship flew between them and painted nothing."""
        self.drops.append(self.xy(lat, lon))
        self.drop_fixes.append((lat, lon))
        self._last = None

    def add(self, lat, lon):
        """Paint here. False when here is outside the mask."""
        x, y = self.xy(lat, lon)
        if abs(x) > REACH_M or abs(y) > REACH_M:
            return False
        if self._last is not None and math.hypot(x - self._last[0], y - self._last[1]) < STAMP_M:
            return True
        self._last = (x, y)
        if self._stamp(x, y):
            self.stamps.append((lat, lon))
        return True

    def _stamp(self, x, y):
        """One disc at (x, y) metres. True when it painted new ground."""
        px, py = _mask_px(x, y)
        r = SCAN_RADIUS_M / MASK_M_PER_PX
        # Clamped to the mask. A crop past the edge is padded with zeros, the
        # disc paints them, and every stamp by the edge would look like new
        # ground and rebuild the layer.
        box = (max(0, int(px - r) - 1), max(0, int(py - r) - 1),
               min(MASK_PX, int(px + r) + 2), min(MASK_PX, int(py + r) + 2))
        region = self.mask.crop(box)
        before = region.histogram()[255]
        ImageDraw.Draw(region).ellipse(
            [px - r - box[0], py - r - box[1], px + r - box[0], py + r - box[1]], fill=255)
        if region.histogram()[255] > before:
            self.mask.paste(region, box[:2])
            self.version += 1
            return True
        return False

    def painted_km2(self):
        return sum(self.mask.histogram()[1:]) * (MASK_M_PER_PX / 1000.0) ** 2

    def layer(self, side):
        """The whole mask drawn at the scale of a map this big, kept until
        something new is painted."""
        key = (self.version, len(self.drops), side)
        if self._layer is None or self._layer[0] != key:
            self._layer = (key, _draw_layer(self.mask, self.drops, side))
        return self._layer[1]


def follow(coverage, fix, was_in_srv, saved=None):
    """The Coverage this fix belongs to.

    The same one while the body is the same and the fix is inside its mask,
    so a ship hop of a few km carries on painting the same map. Anything else
    is a map saved on this body that reaches here - the last one saved, carried on
    with a new droppoint - or a new map.

    `saved(body)` gives coverstore.maps' [(name, data), ...].
    """
    body, lat, lon, radius, _ = fix
    if coverage is None or coverage.body != body or (
            not was_in_srv and not coverage.reaches(lat, lon)):
        loaded = _pick_saved(saved(body) if saved else [], body, lat, lon,
                                skip=coverage.name if coverage and coverage.body == body else None)
        if loaded is None:
            return Coverage(body, lat, lon, radius)
        coverage = loaded
        was_in_srv = False
    if not was_in_srv:
        coverage.launched(lat, lon)
    return coverage


def _pick_saved(found, body, lat, lon, skip=None):
    """The saved map that reaches here and was saved last, repainted; nearest
    origin breaks a tie. Last saved, not nearest: while EDMC runs, a launch
    that two maps reach carries on the one in memory, which is the one used
    last, and a restart has to pick the same one or the ground splits across
    two files. Reach is measured from each map's origin first, so only the one
    chosen pays for a repaint. One that will not load gives way to the next."""
    reaching = []
    for name, data in found:
        if name == skip:
            continue
        try:
            probe = Coverage(body, float(data["origin"][0]), float(data["origin"][1]),
                             float(data["radius"]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if probe.reaches(lat, lon):
            saved_at = data.get("saved")
            order = (-(saved_at if isinstance(saved_at, (int, float)) else 0),
                     math.hypot(*probe.xy(lat, lon)))
            reaching.append((order, name, data))
    for _, name, data in sorted(reaching, key=lambda item: item[0]):
        cover = Coverage.from_dict(body, data, name)
        if cover is not None:
            return cover
    return None


# The map side that makes the saved picture come out at the mask's own size:
# the whole mask, 400 x 400 at 50 m a pixel.
PICTURE_SIDE = int(round(MASK_PX * VIEW_M / REACH_M))


def picture(mask, drops, marks=()):
    """The whole map as a PIL image, north up, droppoints numbered, bookmarks
    on it.

    Takes a copy of the mask, the droppoints and the bookmarks (metres) rather
    than the Coverage, so it can run off the Tk thread while the SRV keeps
    painting.
    """
    image = _draw_layer(mask, drops, PICTURE_SIDE)
    scale = image.width / (2 * REACH_M)
    _bookmarks(image, [(image.width / 2 + mx * scale, image.height / 2 - my * scale)
                       for mx, my in marks], PICTURE_SIDE)
    draw = ImageDraw.Draw(image)
    font = spotcard._font("consola.ttf", 16)
    for number, (mx, my) in enumerate(drops, 1):
        dx, dy = image.width / 2 + mx * scale, image.height / 2 - my * scale
        draw.text((dx + PICTURE_SIDE * 0.035, dy - 8), str(number),
                  fill=palette.rgb(palette.FG), font=font)
    return image


def bearing(x, y, to_x, to_y):
    """Degrees clockwise from north, from (x, y) to (to_x, to_y), in metres."""
    return math.degrees(math.atan2(to_x - x, to_y - y)) % 360.0


def _mask_px(x, y):
    return (x + REACH_M) / MASK_M_PER_PX, (REACH_M - y) / MASK_M_PER_PX


def _mix(a, b, share):
    return tuple(int(round(p + (q - p) * share)) for p, q in zip(palette.rgb(a), palette.rgb(b)))


FILL = _mix(palette.BG, palette.ACCENT, 0.22)
EDGE = _mix(palette.BG, palette.ACCENT, 0.85)
# Earlier droppoints: still worth seeing, not where the ship is.
DROP_OLD = _mix(palette.BG, palette.GOOD, 0.45)
# Bookmarks: a colour nothing else on the map uses.
MARK = palette.rgb(palette.ALERT)


def _bookmarks(image, points, side):
    """A dot per bookmark at these pixel positions. Radius 1.8% of the map side
    against the latest droppoint's 3%: smaller than it, still a dot at 180 px."""
    r = max(3.0, side * 0.018)
    draw = ImageDraw.Draw(image)
    for cx, cy in points:
        if -r <= cx <= image.width + r and -r <= cy <= image.height + r:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MARK,
                         outline=palette.rgb(palette.BG))


def _draw_layer(mask, drops, side):
    """Painted area, grid, the edge of the mask and the droppoints, over all of
    REACH_M, at `side` pixels to 2 * VIEW_M."""
    size = int(round(side * REACH_M / VIEW_M))
    big = size * SS
    scale = big / (2 * REACH_M)                   # pixels a metre

    def at(mx, my):
        return big / 2 + mx * scale, big / 2 - my * scale

    image = Image.new("RGB", (big, big), palette.rgb(palette.BG))
    painted = mask.resize((big, big), Image.BILINEAR)
    image.paste(FILL, mask=painted)
    edge = painted.point(lambda v: 255 if v > 127 else 0).filter(ImageFilter.FIND_EDGES)
    image.paste(EDGE, mask=edge)

    draw = ImageDraw.Draw(image)
    steps = int(REACH_M // GRID_M)
    for k in range(-steps, steps + 1):
        gx, gy = at(k * GRID_M, k * GRID_M)
        draw.line([(gx, 0), (gx, big)], fill=palette.rgb(palette.RULE), width=SS)
        draw.line([(0, gy), (big, gy)], fill=palette.rgb(palette.RULE), width=SS)

    # Where the mask ends - past it nothing is painted.
    draw.rectangle([0, 0, big - 1, big - 1], outline=palette.rgb(palette.WARN), width=SS)

    for number, (mx, my) in enumerate(drops, 1):
        latest = number == len(drops)
        dx, dy = at(mx, my)
        s = side * SS * (0.03 if latest else 0.025)
        draw.polygon([(dx, dy - s), (dx + s, dy), (dx, dy + s), (dx - s, dy)],
                     fill=palette.rgb(palette.GOOD) if latest else DROP_OLD,
                     outline=palette.rgb(palette.BG))

    # A box average is all two-times supersampling needs, and a tenth of what
    # LANCZOS costs.
    return image.reduce(SS)


_markers = {}            # (frame or None, pixels) -> RGBA


def _marker(heading, size):
    """The SRV: a chevron turned to the heading, or a dot without one.
    Drawn at four times the size, once per arrow.STEP degrees, and kept."""
    key = (None if heading is None else arrow.bucket(heading), size)
    sprite = _markers.get(key)
    if sprite is None:
        big = size * 4
        sprite = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sprite)
        fg = palette.rgb(palette.FG) + (255,)
        bg = palette.rgb(palette.BG) + (255,)
        if heading is None:
            draw.ellipse([big * 0.3, big * 0.3, big * 0.7, big * 0.7], fill=fg, outline=bg, width=4)
        else:
            a = math.radians(key[0] * arrow.STEP)
            chevron = [(0, -1.0), (0.7, 0.8), (0, 0.4), (-0.7, 0.8)]
            draw.polygon([(big / 2 + (px * math.cos(a) - py * math.sin(a)) * big * 0.45,
                           big / 2 + (px * math.sin(a) + py * math.cos(a)) * big * 0.45)
                          for px, py in chevron], fill=fg, outline=bg, width=4)
        sprite = sprite.reduce(4)
        _markers[key] = sprite
    return sprite


def render(coverage, x, y, heading, side, marks=()):
    """The map, side x side, the SRV at (x, y) in the middle, north up.

    A crop of the kept layer with the bookmarks and the marker on top - the
    painting itself is only redone when coverage.version moves. `marks` are
    bookmarks in metres from the first droppoint.
    """
    layer = coverage.layer(side)
    scale = side / (2 * VIEW_M)
    left = int(round(layer.width / 2 + x * scale - side / 2))
    top = int(round(layer.height / 2 - y * scale - side / 2))
    image = Image.new("RGB", (side, side), palette.rgb(palette.BG))
    image.paste(layer, (-left, -top))
    _bookmarks(image, [(side / 2 + (mx - x) * scale, side / 2 - (my - y) * scale)
                       for mx, my in marks], side)
    size = max(12, int(round(side * 0.09)))
    marker = _marker(heading, size)
    image.paste(marker, ((side - size) // 2, (side - size) // 2), marker)
    return image
