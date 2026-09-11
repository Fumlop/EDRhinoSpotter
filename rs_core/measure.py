"""How big is this patch, and how many rigs will it take.

You drive the border of a mining spot in the SRV and this follows along in
Status.json. What comes out is an area and a rig count for a shape that is
whatever you drove - not a circle, not a rectangle, and usually neither.

The rig count is a grid of RIG_SPACING laid over the shape with every point
outside it thrown away. It is an estimate and is meant to read as one: the
ground is not flat, you did not drive the border exactly, and two rigs 76 m
apart on a slope are not 76 m apart on the map.

No tkinter and no PIL, so all of it can be checked without EDMC or a display.
See rs_tests/test_measure.py.
"""

import math

# Frontier's own figure: rigs closer than this to each other do not deploy.
RIG_SPACING = 76.0

# Two samples closer together than this are the same place. The SRV idles with
# a metre of drift and Status.json is rewritten several times a second, so
# without this a stop at the fence adds a hundred points that say nothing.
MIN_STEP = 4.0


def metres_per_degree(radius):
    """Latitude degrees to metres. Longitude needs the cosine as well."""
    return radius * math.pi / 180.0


def to_metres(points, radius, origin=None):
    """[(lat, lon), ...] -> [(x, y), ...] in metres from the first point.

    Flat earth on purpose. A mining spot is a few hundred metres across on a
    body a thousand kilometres in radius, and over that distance the error of
    treating the surface as a plane is smaller than the error of having driven
    the border by eye.
    """
    if not points:
        return []
    origin = origin or points[0]
    scale = metres_per_degree(radius)
    lat0, lon0 = origin
    cos_lat = math.cos(math.radians(lat0))
    return [((lon - lon0) * scale * cos_lat, (lat - lat0) * scale)
            for lat, lon in points]


def area(polygon):
    """Square metres enclosed, by the shoelace formula.

    Absolute, so it does not matter which way round the border was driven.
    Fewer than three points enclose nothing.
    """
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def inside(polygon, x, y):
    """Is the point within the polygon - ray casting, counting crossings."""
    hit = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index - 1) % count]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def rigs(polygon, spacing=RIG_SPACING):
    """How many rigs the shape holds, on a grid of `spacing`.

    A grid rather than anything cleverer: rigs go where you drive to, and the
    best packing of a shape you measured roughly is a precision the input does
    not carry. It is laid from the shape's own bounding box, so the answer does
    not depend on where on the planet the shape is.
    """
    if len(polygon) < 3 or spacing <= 0:
        return 0
    xs = [x for x, _ in polygon]
    ys = [y for _, y in polygon]

    # Half a cell in from the corner, so a rig sits in the middle of its square
    # rather than on the fence. Starting on the corner put the only point of a
    # small patch exactly on its own boundary, which counts as outside - a
    # 4,000 m2 spot came back as room for no rigs at all.
    count = 0
    steps_x = int((max(xs) - min(xs)) // spacing) + 1
    steps_y = int((max(ys) - min(ys)) // spacing) + 1
    for row in range(steps_y):
        for column in range(steps_x):
            x = min(xs) + (column + 0.5) * spacing
            y = min(ys) + (row + 0.5) * spacing
            if inside(polygon, x, y):
                count += 1

    # A shape with area in it holds a rig somewhere, whatever the grid says. A
    # long thin patch can miss every grid point and still be somewhere you can
    # put one down.
    return count if count else (1 if area(polygon) > 0 else 0)


class Track:
    """A border being driven, one Status.json at a time.

    Holds raw degrees and converts on demand, so the answer is the same whether
    it is asked for once at the end or on every sample.
    """

    def __init__(self, spacing=RIG_SPACING, min_step=MIN_STEP):
        self.spacing = spacing
        self.min_step = min_step
        self.body = None
        self.radius = None
        self.points = []

    def add(self, status):
        """Feed one Status.json. True if it moved the border.

        A status from another body ends the track rather than bending it
        across a planet: you cannot drive from one to the other, so a sample
        from somewhere else is a mistake, not a corner.
        """
        if not status:
            return False
        lat, lon = status.get("Latitude"), status.get("Longitude")
        radius = status.get("PlanetRadius")
        if lat is None or lon is None or not radius:
            return False

        body = status.get("BodyName")
        if self.body and body and body != self.body:
            return False
        self.body = body or self.body
        self.radius = radius

        if self.points and self._step(lat, lon) < self.min_step:
            return False
        self.points.append((lat, lon))
        return True

    def _step(self, lat, lon):
        last_lat, last_lon = self.points[-1]
        scale = metres_per_degree(self.radius)
        dy = (lat - last_lat) * scale
        dx = (lon - last_lon) * scale * math.cos(math.radians(lat))
        return math.hypot(dx, dy)

    def polygon(self):
        return to_metres(self.points, self.radius) if self.radius else []

    def perimeter(self):
        """How far you drove, in metres. Only the border, not the way there."""
        polygon = self.polygon()
        if len(polygon) < 2:
            return 0.0
        return sum(math.hypot(polygon[i][0] - polygon[i - 1][0],
                              polygon[i][1] - polygon[i - 1][1])
                   for i in range(1, len(polygon)))

    def closure(self):
        """How far the last point is from the first, in metres.

        The one number that says whether the shape is worth anything. A border
        you drove right round closes within a few metres; a gap of two hundred
        is a shape with a side the shoelace formula invented, and the area will
        look perfectly reasonable.
        """
        polygon = self.polygon()
        if len(polygon) < 2:
            return 0.0
        return math.hypot(polygon[-1][0] - polygon[0][0],
                          polygon[-1][1] - polygon[0][1])

    def summary(self):
        """Everything worth writing to a log, in one dict."""
        return {
            "body": self.body,
            "radius_m": self.radius,
            "points": len(self.points),
            "perimeter_m": round(self.perimeter(), 1),
            "closure_m": round(self.closure(), 1),
            "area_m2": round(self.area(), 1),
            "rigs": self.rigs(),
            "spacing_m": self.spacing,
        }

    def area(self):
        return area(self.polygon())

    def rigs(self):
        return rigs(self.polygon(), self.spacing)

    def __len__(self):
        return len(self.points)
