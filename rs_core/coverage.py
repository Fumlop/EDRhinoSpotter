"""The minimap: how much ground the Rhino's scanner has been driven over.

Every fix out of Status.json while you are in the SRV stamps a disc of
SCAN_RADIUS_M onto a mask anchored at the map's centre. The discs overlap into one
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

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from rs_core import arrow, guide, measure, palette, spotcard

# Status.json Flags bit for "in the SRV", as EDMC's edmc_data names it.
IN_SRV = 0x4000000

# What the scanner sees from where the SRV is, in metres.
SCAN_RADIUS_M = 2000.0

# Half the width of what the map shows around the SRV. 12 km across is 50 m a
# pixel on a 1080p map - the mask's own resolution - and a 1 km grid still has
# 20 px between its lines.
VIEW_M = 6000.0

# Half the width of the mask around the centre. Few drive further than 6-7
# km from the ship in any direction; 10 km leaves room past that.
REACH_M = 10000.0

# Mask resolution. 50 m a pixel is 400 x 400, 160 KB, and still sharp on a map
# drawn 480 px wide.
MASK_M_PER_PX = 50.0

# A disc every this many metres driven. Two discs 250 m apart leave a 4 m dent
# in the edge between them, which nobody sees at 50 m a pixel.
STAMP_M = 250.0

# Grid lines, pinned to the centre so they move with the ground.
GRID_M = 1000.0

# The circles to drive round the centre, counted out from it: the first at
# 3.75 km, each next 1.75 km further. Measured from the centre, not back from
# the border - the drive goes round the centre, and the border is only where
# to stop. Without a border there are two; with one, rings are added until one
# scans out to it.
FIRST_RING_M = 3750.0
RING_STEP_M = 1750.0
RINGS_WITHOUT_BORDER = 2


def ring_radii(border_m=None):
    """Radii of the circles to drive, inside out."""
    radii = [FIRST_RING_M + k * RING_STEP_M for k in range(RINGS_WITHOUT_BORDER)]
    if not border_m:
        return radii
    radii = radii[:1]
    while radii[-1] + SCAN_RADIUS_M < border_m:
        radii.append(radii[-1] + RING_STEP_M)
    return radii

# How big the map is drawn, as a share of the game window's height, and the
# limits either side - a laptop window should not get a stamp, a 4K screen
# should not get a poster.
MAP_SHARE = 0.22
MAP_MIN_PX = 180
MAP_MAX_PX = 480

# What the size hotkey steps through, and how big the player may ask for.
# MAP_MAX_PX is what a map picks for itself; this is the ceiling on top of it,
# and it is a speed limit rather than a room limit: _draw_layer is redone on
# the Tk thread every STAMP_M driven, measured here at 41 ms at 428 px, 90 ms
# at 640 and 160 ms at 855. 640 keeps the worst press in the same range as a
# 4K window already sits in without touching the hotkey at all.
MAP_ZOOMS = (1.0, 2.0)
MAP_ZOOM_MAX_PX = 640

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


def map_side(window_height, zoom=1.0):
    """The map's side in pixels, for a game window this tall.

    `zoom` is the size hotkey's factor. It multiplies the side past MAP_MAX_PX
    - that cap is what a map picks by itself, not what the player may ask for -
    and stops at MAP_ZOOM_MAX_PX.
    """
    if not window_height:
        side = MAP_MIN_PX + (MAP_MAX_PX - MAP_MIN_PX) // 4
    else:
        side = max(MAP_MIN_PX, min(MAP_MAX_PX, int(round(window_height * MAP_SHARE))))
    return min(int(round(side * zoom)), MAP_ZOOM_MAX_PX)


class Coverage:
    """One map: everything painted around its centre.

    The centre is where the SRV first came out of the ship, until the player
    picks one with the hotkey - see recenter().
    """

    def __init__(self, body, lat, lon, radius, system_address=None):
        self.body = body
        # The game's IDs for the body, once known. Maps are kept by body name,
        # and a name is only unique inside its system.
        self.system_address = system_address
        self.body_id = None
        self.origin = (lat, lon)
        self.radius = radius
        self.mask = Image.new("L", (MASK_PX, MASK_PX), 0)
        # Goes up only when a disc paints ground that was not painted before.
        # Driving around inside what is already painted leaves it alone, and
        # so leaves the drawn layer alone.
        self.version = 0
        # What goes to disk: every point that painted new ground, as (lat,
        # lon). A point that painted nothing new adds nothing to a repaint.
        self.stamps = []
        # True once the player has set the centre; then `origin` is it.
        self.centered = False
        # The location's border as the player drove it: metres from the centre,
        # or None. Only set once there is a centre to measure from.
        self.border_m = None
        # Where the SRV last came out of the ship, (lat, lon). The rings and
        # the footer use it until a centre is set. Kept in memory only.
        self.drop = (lat, lon)
        # The file this map is saved as - coverstore's 'map N' - once it is.
        self.name = None
        # The mining location last targeted on this map. A label, not a key.
        self.location = None
        self._last = None
        self._clip = None       # the border as a mask, while one is set
        self._layer = None      # ((version, side, ring centre, border), image)

    def to_dict(self):
        """The map as coverstore writes it. New lists, so a writer on another
        thread never sees one change under it."""
        def points(fixes):
            return [[round(lat, 6), round(lon, 6)] for lat, lon in fixes]
        data = {"origin": points([self.origin])[0], "radius": self.radius,
                "location": self.location, "stamps": points(self.stamps)}
        if self.centered:
            data["center"] = points([self.origin])[0]
        if self.border_m is not None:
            data["border_m"] = round(self.border_m)
        if self.system_address is not None:
            data["system_address"] = self.system_address
        if self.body_id is not None:
            data["body_id"] = self.body_id
        return data

    @classmethod
    def from_dict(cls, body, data, name=None):
        """A map back from disk, repainted from its points. None when the data
        is not a map. Droppoints in older files are ignored."""
        try:
            lat, lon = data.get("center") or data["origin"]
            cover = cls(body, float(lat), float(lon), float(data["radius"]))
            cover.centered = bool(data.get("center"))
            border = data.get("border_m")
            cover.border_m = float(border) if cover.centered and border else None
            cover._repaint([(float(lat), float(lon)) for lat, lon in data["stamps"]])
        except (KeyError, TypeError, ValueError):
            return None
        cover.name = name
        cover.location = data.get("location")
        cover.system_address = data.get("system_address")
        cover.body_id = data.get("body_id")
        return cover

    def _repaint(self, points):
        """Paint these (lat, lon) points onto a clear mask, keeping each one
        in `stamps` - including those past the mask's edge, which paint
        nothing here but belong to the map on disk."""
        self.mask = Image.new("L", (MASK_PX, MASK_PX), 0)
        self._clip = None
        if self.border_m is not None:
            self._clip = Image.new("L", (MASK_PX, MASK_PX), 0)
            cx, cy = _mask_px(0.0, 0.0)
            r = self.border_m / MASK_M_PER_PX
            ImageDraw.Draw(self._clip).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
        self.stamps = []
        for lat, lon in points:
            x, y = self.xy(lat, lon)
            # Outside a known border the point is gone, from the mask and the
            # file: the player said the location ends there.
            if not self._inside(x, y):
                continue
            if abs(x) <= REACH_M + SCAN_RADIUS_M and abs(y) <= REACH_M + SCAN_RADIUS_M:
                self._stamp(x, y)
            self.stamps.append((lat, lon))
        self.version += 1
        self._last = None

    def recenter(self, lat, lon):
        """The player says this is the middle of the location: the mask is
        rebuilt around it from the saved points, and the rings follow."""
        self.origin = (lat, lon)
        self.centered = True
        # A border already set keeps its radius around the new centre, and
        # what falls outside it now is dropped.
        self._repaint(list(self.stamps))

    def set_border(self, lat, lon):
        """The player stands on the location's edge: its distance from the
        centre is the border. False, and nothing set, without a centre."""
        if not self.centered:
            return False
        self.border_m = math.hypot(*self.xy(lat, lon))
        self._repaint(list(self.stamps))
        return True

    def _inside(self, x, y):
        return self.border_m is None or math.hypot(x, y) <= self.border_m

    def anchor(self):
        """(x, y) metres the rings are drawn around: the centre once set, the
        latest droppoint until then."""
        return (0.0, 0.0) if self.centered else self.xy(*self.drop)

    def xy(self, lat, lon):
        """Metres east and north of the map's centre."""
        # Longitude taken the short way round: a body straddling the 180th
        # meridian is one step across it, not most of the way round the planet.
        lon = self.origin[1] + (lon - self.origin[1] + 180.0) % 360.0 - 180.0
        return measure.to_metres([(lat, lon)], self.radius, origin=self.origin)[0]

    def reaches(self, lat, lon):
        x, y = self.xy(lat, lon)
        return abs(x) <= REACH_M and abs(y) <= REACH_M

    def launched(self, lat, lon):
        """The SRV has come out of the ship again, here. The first fix is
        painted rather than measured against where the last launch ended - the
        ship flew between them and painted nothing."""
        self.drop = (lat, lon)
        self._last = None

    def add(self, lat, lon):
        """Paint here. False when here is outside the mask."""
        x, y = self.xy(lat, lon)
        if abs(x) > REACH_M or abs(y) > REACH_M:
            return False
        if self._last is not None and math.hypot(x - self._last[0], y - self._last[1]) < STAMP_M:
            return True
        self._last = (x, y)
        if not self._inside(x, y):
            return True             # outside the border: in reach, not painted
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
        if self._clip is not None:
            region = ImageChops.multiply(region, self._clip.crop(box))
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
        ring_at = tuple(round(v) for v in self.anchor())
        key = (self.version, side, ring_at, self.border_m)
        if self._layer is None or self._layer[0] != key:
            self._layer = (key, _draw_layer(self.mask, side, ring_at, self.border_m))
        return self._layer[1]


def follow(coverage, fix, was_in_srv, saved=None, system_address=None):
    """The Coverage this fix belongs to.

    The same one while the body is the same and the fix is inside its mask,
    so a ship hop of a few km carries on painting the same map. Anything else
    is a map saved on this body that reaches here - the last one saved - or a
    new map.

    `saved(body)` gives coverstore.maps' [(name, data), ...]. A body of the same
    name in another system - both addresses known and different - is another
    body.
    """
    body, lat, lon, radius, _ = fix
    same = (coverage is not None and coverage.body == body
            and (None in (coverage.system_address, system_address)
                 or coverage.system_address == system_address))
    if not same or (not was_in_srv and not coverage.reaches(lat, lon)):
        loaded = _pick_saved(saved(body) if saved else [], body, lat, lon,
                                skip=coverage.name if same else None)
        if loaded is None:
            return Coverage(body, lat, lon, radius, system_address)
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


def map_at(found, body, lat, lon):
    """The name of the saved map a point belongs to, or None: of the maps that
    reach it, the one whose centre is nearest. No repaint - reach is
    measured from each map's origin. `found` is coverstore.maps' list."""
    best = None
    for name, data in found:
        try:
            probe = Coverage(body, float(data["origin"][0]), float(data["origin"][1]),
                             float(data["radius"]))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if probe.reaches(lat, lon):
            distance = math.hypot(*probe.xy(lat, lon))
            if best is None or distance < best[0]:
                best = (distance, name)
    return best[1] if best else None


def mapped_locations(found, body, records=()):
    """({location: [map name, ...]}, [map name, ...]) for one body.

    A location is mapped when a map saved it as the location targeted while
    driving, or when one of its bookmarks lies on a map - most maps never had
    a location targeted, so the stored number alone misses them. The second
    list is the maps neither way ties to a location. `found` is
    coverstore.maps' list, `records` the body's bookmarks.
    """
    by_location = {}
    for name, data in found:
        location = data.get("location")
        if isinstance(location, int) and not isinstance(location, bool):
            by_location.setdefault(location, set()).add(name)
    for record in records or ():
        location = record.get("location_index")
        lat, lon = record.get("latitude"), record.get("longitude")
        if location is None or lat is None or lon is None:
            continue
        try:
            name = map_at(found, body, float(lat), float(lon))
        except (TypeError, ValueError):
            continue
        if name:
            by_location.setdefault(int(location), set()).add(name)
    tied = set().union(*by_location.values()) if by_location else set()

    def number(name):
        tail = name.rsplit(" ", 1)[-1]
        return (0, int(tail), name) if tail.isdigit() else (1, 0, name)

    mapped = {location: sorted(names, key=number) for location, names in by_location.items()}
    unknown = sorted((name for name, _ in found if name not in tied), key=number)
    return mapped, unknown


# The map side that makes the saved picture come out at the mask's own size:
# the whole mask, 400 x 400 at 50 m a pixel.
PICTURE_SIDE = int(round(MASK_PX * VIEW_M / REACH_M))


def picture(mask, marks=(), title=(), legend=(), border_m=None):
    """The whole map as a PIL image, north up, bookmarks on it.

    Takes a copy of the mask and the bookmarks (metres) rather than the
    Coverage, so it can run off the Tk thread while the SRV keeps painting.

    `title` is lines of text above the map, the first one larger; `legend` is
    (code, text) or (code, text, depleted) rows below it, one per bookmark. Both optional - without them
    the picture is the bare map.
    """
    # No rings: the ground and the bookmarks are what the picture is kept for.
    image = _draw_layer(mask, PICTURE_SIDE, border_m=border_m, drive=False)
    scale = image.width / (2 * REACH_M)
    _bookmarks(image, [(image.width / 2 + mx * scale, image.height / 2 - my * scale, *rest)
                       for mx, my, *rest in marks], PICTURE_SIDE)
    if not title and not legend:
        return image

    pad, line = 12, 18
    big = spotcard._font("consolab.ttf", 17)
    small = spotcard._font("consola.ttf", 13)
    code_font = spotcard._font("consolab.ttf", 13)
    top = pad + (len(title) * line + 6 if title else 0)
    bottom = (pad + len(legend) * line + pad) if legend else pad
    # Wider than the map when a long system name needs it; the map centred.
    widths = [big.getlength(t) if i == 0 else small.getlength(t) for i, t in enumerate(title)]
    widths += [36 + small.getlength(text) for _, text, *_ in legend]
    width = max([image.width] + [int(w) + 2 * pad for w in widths])
    sheet = Image.new("RGB", (width, top + image.height + bottom), palette.rgb(palette.BG))
    sheet.paste(image, ((width - image.width) // 2, top))
    draw = ImageDraw.Draw(sheet)
    for i, text in enumerate(title):
        draw.text((pad, pad + i * line), text, font=big if i == 0 else small,
                  fill=palette.rgb(palette.FG if i == 0 else palette.MUTED))
    y = top + image.height + pad
    for code, text, *depleted in legend:
        draw.text((pad, y), code or "-", font=code_font,
                  fill=MARK_DEPLETED if depleted and depleted[0] else MARK)
        draw.text((pad + 36, y), text, font=small, fill=palette.rgb(palette.FG))
        y += line
    return sheet


def bearing(x, y, to_x, to_y):
    """Degrees clockwise from north, from (x, y) to (to_x, to_y), in metres."""
    return math.degrees(math.atan2(to_x - x, to_y - y)) % 360.0


def _mask_px(x, y):
    return (x + REACH_M) / MASK_M_PER_PX, (REACH_M - y) / MASK_M_PER_PX


def _mix(a, b, share):
    return tuple(int(round(p + (q - p) * share)) for p, q in zip(palette.rgb(a), palette.rgb(b)))


FILL = _mix(palette.BG, palette.ACCENT, 0.22)
EDGE = _mix(palette.BG, palette.ACCENT, 0.85)
RING = _mix(palette.BG, palette.GOOD, 0.4)
BORDER = palette.rgb(palette.FG_SOFT)      # not WARN: that is the mask edge
# Bookmarks: a colour nothing else on the map uses.
# Bookmarks: green while the patch still has something, red once depleted.
MARK = palette.rgb(palette.GOOD)
MARK_DEPLETED = palette.rgb(palette.ALERT)

# The centre the player set. Blue is the accent and nothing else on the map
# wears it, so the eye finds the centre first. It is a mark and not a hub: the
# lines run between the bookmarks, never out to it.
CENTRE = palette.rgb(palette.ACCENT)
# Bookmark to bookmark. Solid to the nearest of the same material, dotted to
# the next material down: the line you would drive to keep mining what you are
# mining, and the line you would drive to settle for less.
LINE_SPOT = _mix(palette.BG, palette.FG_SOFT, 0.5)
LINE_LOWER = _mix(palette.BG, palette.FG_SOFT, 0.35)

# Where along a line its number may sit, tried in this order. _distances adds
# one more past the far end, for lines with no clear span on them at all.
LABEL_ALONG = (0.5, 0.62, 0.38, 0.74, 0.26)


def _mark_radius(side):
    """A bookmark dot's radius: 1.8% of the map side, and still a dot at 180 px."""
    return max(3.0, side * 0.018)


def _mark_font(side):
    """A bookmark code's face: 5% of the map side, never under 9 px."""
    return spotcard._font("consolab.ttf", max(9, int(round(side * 0.05))))


def _code_at(cx, cy, side):
    """Where a bookmark's code is written: just right of its dot. _distances
    keeps its numbers out of this box, so the two have to agree on it."""
    return cx + _mark_radius(side) + 1, cy


def _on_map(image, cx, cy, r):
    """Whether a dot of radius r at (cx, cy) is on the map at all."""
    return -r <= cx <= image.width + r and -r <= cy <= image.height + r


def _bookmarks(image, points, side):
    """A dot per bookmark at these pixel positions, its material's code beside it.

    `points` are (x, y), (x, y, code) or (x, y, code, depleted) - grounds.Sheet.codes
    gives the code. A depleted bookmark is red, any other green.
    """
    r = _mark_radius(side)
    draw = ImageDraw.Draw(image)
    font = _mark_font(side)
    for cx, cy, *rest in points:
        if _on_map(image, cx, cy, r):
            colour = MARK_DEPLETED if len(rest) > 1 and rest[1] else MARK
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour,
                         outline=palette.rgb(palette.BG))
            if rest and rest[0]:
                # Outlined in the background colour: readable over the painted
                # area, the grid and the rings alike.
                draw.text(_code_at(cx, cy, side), rest[0], fill=colour, font=font,
                          anchor="lm", stroke_width=2, stroke_fill=palette.rgb(palette.BG))


def _dotted(draw, a, b, fill, width):
    """A dotted line from a to b. ImageDraw has no dash pattern, so the line is
    walked and the dots are put down one at a time."""
    (ax, ay), (bx, by) = a, b
    length = math.hypot(bx - ax, by - ay)
    if not length:
        return
    on, off = max(2.0, width * 2.0), max(3.0, width * 3.0)
    step = (bx - ax) / length, (by - ay) / length
    at = 0.0
    while at < length:
        end = min(at + on, length)
        draw.line([(ax + step[0] * at, ay + step[1] * at),
                   (ax + step[0] * end, ay + step[1] * end)], fill=fill, width=width)
        at = end + off


def _centre_radius(side):
    """The ring round the centre. _distances keeps its numbers outside it: the
    ring is drawn last and would otherwise cut straight through one."""
    return max(5.0, side * 0.026)


def _centre_mark(image, cx, cy, side):
    """The centre the player set with the hotkey: a small dot inside a ring.

    A ring rather than a filled disc - the centre is a place on the ground,
    and a disc that size would read as a bookmark of its own.
    """
    draw = ImageDraw.Draw(image)
    r = _centre_radius(side)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CENTRE,
                 width=max(1, int(round(side / 200))))
    dot = max(1.5, r * 0.34)
    draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=CENTRE)


def _distances(image, points, side, centre, per_px):
    """How far apart things are: a line from the centre to every spot, and one
    from every spot to the spot nearest it, each with its length on it.

    `points` are the spots in pixels, `centre` the map's centre in pixels or
    None while the player has not set one. `per_px` is metres a pixel.

    Only spots on the map are joined up. A bookmark on the far side of the
    body is in `points` - nothing filters them by distance - and a line to one
    would be a ray off the edge towards something the player cannot see, at the
    cost of drawing it: fourteen bookmarks on one body, thirteen of them off
    the map, measured 3.1 ms a frame against 0.2 ms for the one that is on it.

    Each spot is joined twice: a solid line to the nearest spot holding the
    same material, and a dotted one to the nearest spot holding the next
    material down the sheet's price ranking. Two spots of one material that
    pick each other share their solid line; a dotted line only ever runs
    downhill, so it can never be drawn twice.

    `centre` is not joined to anything - it is only kept clear, since the ring
    marking it is drawn after these lines and would cut through a number.

    A number is left off when it would not fit on the map or would land on
    something already drawn - another number, a dot with its code, the SRV, the
    centre, or the scale bar the window writes over the bottom left corner.
    """
    draw = ImageDraw.Draw(image)
    size = max(8, int(round(side * 0.042)))
    font = spotcard._font("consola.ttf", size)
    width = max(1, int(round(side / 300)))
    r = _mark_radius(side)
    spots, code_of, value_of = [], {}, {}
    for point in points:
        if not _on_map(image, point[0], point[1], r):
            continue
        spot = (float(point[0]), float(point[1]))
        spots.append(spot)
        code_of[spot] = point[2] if len(point) > 2 else None
        value_of[spot] = point[4] if len(point) > 4 else 0

    # What goes on over these lines, so the numbers keep out of its way rather
    # than being painted over: the SRV in the middle, the centre ring, the dots
    # with their codes, and the scale bar the window draws into the corner.
    half = _marker_size(side) / 2.0
    written = [(side / 2 - half, side / 2 - half, side / 2 + half, side / 2 + half),
               (0, side - side / 12.0, side / 3.0, side)]
    if centre is not None:
        ring = _centre_radius(side)
        written.append((centre[0] - ring, centre[1] - ring, centre[0] + ring, centre[1] + ring))
    mark_font = _mark_font(side)
    # How far past a spot a number has to start to clear the dot and the code
    # written beside it. Without the code in the sum, a short line's last
    # candidate lands on its own bookmark's letters and the number is lost.
    behind = {}
    for point in points:
        cx, cy = float(point[0]), float(point[1])
        if not _on_map(image, cx, cy, r):
            continue
        written.append((cx - r, cy - r, cx + r, cy + r))
        code = point[2] if len(point) > 2 else None
        clear = r
        if code:
            box = draw.textbbox(_code_at(cx, cy, side), code, font=mark_font, anchor="lm")
            written.append(box)
            clear = box[2] - cx
        behind[(cx, cy)] = clear + size

    def label(a, b, colour):
        """The line's length on it, at the first place along it that is free.

        The middle first, then out either way, and last of all just past the
        far end: the lines all leave the centre, so a short one has the SRV at
        one end and a dot with its code at the other and no clear span in
        between - measured, every centre line under about 3 km lost its number
        before the last place was tried.
        """
        (ax, ay), (bx, by) = a, b
        length = math.hypot(bx - ax, by - ay)
        if length < r:
            return                    # two bookmarks from one standing position
        text = guide.metres(length * per_px)
        past = (length + behind.get(b, r + size) + draw.textlength(text, font=font) / 2) / length
        for along in LABEL_ALONG + (past,):
            tx, ty = ax + (bx - ax) * along, ay + (by - ay) * along
            left, top, right, bottom = draw.textbbox((tx, ty), text, font=font, anchor="mm")
            # The stroke widens the text by two pixels a side, and a gap of one
            # more keeps two numbers from touching.
            box = (left - 3, top - 3, right + 3, bottom + 3)
            if box[0] < 0 or box[1] < 0 or box[2] > side or box[3] > side:
                continue
            if any(box[0] < other[2] and other[0] < box[2]
                   and box[1] < other[3] and other[1] < box[3] for other in written):
                continue
            written.append(box)
            draw.text((tx, ty), text, fill=colour, font=font, anchor="mm",
                      stroke_width=2, stroke_fill=palette.rgb(palette.BG))
            return

    def away(spot):
        return lambda other: math.hypot(other[0] - spot[0], other[1] - spot[1])

    same, lower = set(), []
    for spot in spots:
        kin = [o for o in spots if o != spot and code_of[o] == code_of[spot]]
        if kin:
            same.add(tuple(sorted((spot, min(kin, key=away(spot))))))
        # The next material down, not any material down: the best of what is
        # worth less, and the nearest of those when several share it.
        under = [o for o in spots if value_of[o] < value_of[spot]]
        if under:
            step = max(value_of[o] for o in under)
            lower.append((spot, min((o for o in under if value_of[o] == step), key=away(spot))))
    same = sorted(same)

    # Every line first, then every number: a line drawn after a number would
    # run through it.
    for a, b in same:
        draw.line([a, b], fill=LINE_SPOT, width=width)
    for a, b in lower:
        _dotted(draw, a, b, LINE_LOWER, width)
    # The same material first: it is the number worth the room when a solid and
    # a dotted line want the same piece of map.
    for a, b in same:
        label(a, b, palette.rgb(palette.FG_SOFT))
    for a, b in lower:
        label(a, b, LINE_LOWER)


def _draw_layer(mask, side, ring_at=None, border_m=None, drive=True):
    """Painted area, grid, the edge of the mask, the rings around `ring_at`
    (metres, or None for no rings) and the location's border around the centre
    (metres, or None), over all of REACH_M, at `side` pixels to 2 * VIEW_M."""
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

    # The circles to drive, ring_radii. A pixel wide after the reduce, and dim.
    # With a border they sit round the centre and run out to the border;
    # without one, two round the centre or the latest droppoint.
    if border_m and drive:
        ring_at, radii = (0.0, 0.0), ring_radii(border_m)
    else:
        radii = ring_radii()
    if ring_at is not None:
        dx, dy = at(*ring_at)
        for radius_m in radii:
            r = radius_m * scale
            draw.ellipse([dx - r, dy - r, dx + r, dy + r], outline=RING, width=SS)

    # The border the player drove to, bold: it is a claim about the location,
    # which the rings are not.
    if border_m:
        cx, cy = at(0.0, 0.0)
        r = border_m * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BORDER, width=3 * SS)

    # A box average is all two-times supersampling needs, and a tenth of what
    # LANCZOS costs.
    return image.reduce(SS)


_markers = {}            # (frame or None, pixels) -> RGBA


def _marker_size(side):
    """The SRV marker's side in pixels, on a map this wide."""
    return max(12, int(round(side * 0.09)))


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


def render(coverage, x, y, heading, side, marks=(), distances=False):
    """The map, side x side, the SRV at (x, y) in the middle, north up.

    A crop of the kept layer with the bookmarks and the marker on top - the
    painting itself is only redone when coverage.version moves. `marks` are
    bookmarks in metres from the map's centre.

    `distances` draws the lines between them. Off at the smallest size the map
    comes in: 12 km of ground in 180 px has no room for a number, and the lines
    themselves cover the painted area they are drawn over.
    """
    layer = coverage.layer(side)
    scale = side / (2 * VIEW_M)
    left = int(round(layer.width / 2 + x * scale - side / 2))
    top = int(round(layer.height / 2 - y * scale - side / 2))
    image = Image.new("RGB", (side, side), palette.rgb(palette.BG))
    image.paste(layer, (-left, -top))
    spots = [(side / 2 + (mx - x) * scale, side / 2 - (my - y) * scale, *rest)
             for mx, my, *rest in marks]
    # The centre is the map's origin, so it is where (0, 0) metres lands.
    centre = (side / 2 - x * scale, side / 2 + y * scale) if coverage.centered else None
    if distances:
        _distances(image, spots, side, centre, 1.0 / scale)
    _bookmarks(image, spots, side)
    if centre is not None:
        _centre_mark(image, centre[0], centre[1], side)
    size = _marker_size(side)
    marker = _marker(heading, size)
    image.paste(marker, ((side - size) // 2, (side - size) // 2), marker)
    return image
