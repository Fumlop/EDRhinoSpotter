"""Rig positions inside a traced deposit outline.

plan() takes the Status.json fixes of one lap round the border and returns rig
spots on a hexagonal grid, SPACING_M apart, each at least INSET_M (0 m) inside the
outline, ordered as a drive from the last fix.

Local flat x/y (east/north, m) around the first fix: an outline is ~500 m
round, where the flat error is under 1 mm on a 780 km body.

No tkinter. ~2-8 s on a 90-fix outline: call it off the Tk thread.
"""

import math

SPACING_M = 80.0     # rig-to-rig minimum: 77 m measured, 80 m set by user 2026-09-29
INSET_M = 0.0        # rigs may sit on the traced border: the SRV lap is itself approximate; user 2026-09-29, trace-20260929-095343 = known 4-rig spot
ANGLE_STEP_DEG = 3   # grid rotations tried, 0-60 deg (hex repeats every 60)
OFFSET_STEP_M = 4.0  # grid shifts tried, both axes


def _to_xy(lat0, lon0, radius):
    k = math.cos(math.radians(lat0))
    return (lambda lat, lon: (math.radians(lon - lon0) * radius * k, math.radians(lat - lat0) * radius),
            lambda x, y: (lat0 + math.degrees(y / radius), lon0 + math.degrees(x / (radius * k))))


def _inside(poly, x, y):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def _edge_m(poly, x, y):
    """Distance in m from (x, y) to the nearest outline segment."""
    best = math.inf
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - x1 - t * dx, y - y1 - t * dy))
    return best


def plan(fixes, radius, spacing=SPACING_M, inset=INSET_M):
    """Rig spots for one outline.

    fixes: [(lat, lon)] in degrees, the lap in driving order (>= 3).
    radius: PlanetRadius, m.
    Returns [(lat, lon)], most rigs first; ties go to the grid whose
    closest rig sits furthest inside. Ordered nearest-neighbour from fixes[-1].
    """
    if len(fixes) < 3:
        return []
    to_xy, to_ll = _to_xy(fixes[0][0], fixes[0][1], radius)
    poly = [to_xy(lat, lon) for lat, lon in fixes]
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    x0, x1, y0, y1 = min(xs) + inset, max(xs) - inset, min(ys) + inset, max(ys) - inset
    reach = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / 2 + spacing
    n = int(reach / spacing) + 2
    row = spacing * math.sqrt(3) / 2
    best, best_key = [], (0, -math.inf)
    for step in range(0, 60, ANGLE_STEP_DEG):
        a = math.radians(step)
        ca, sa = math.cos(a), math.sin(a)
        ox = 0.0
        while ox < spacing:
            oy = 0.0
            while oy < 2 * row:
                spots, margin = [], math.inf
                for j in range(-n, n + 1):
                    for i in range(-n, n + 1):
                        u, v = i * spacing + (j % 2) * spacing / 2 + ox, j * row + oy
                        x, y = cx + u * ca - v * sa, cy + u * sa + v * ca
                        if not (x0 < x < x1 and y0 < y < y1) or not _inside(poly, x, y):
                            continue
                        edge = _edge_m(poly, x, y)
                        if edge < inset:
                            continue
                        spots.append((x, y))
                        margin = min(margin, edge)
                key = (len(spots), margin if spots else -math.inf)
                if key > best_key:
                    best, best_key = spots, key
                oy += OFFSET_STEP_M
            ox += OFFSET_STEP_M
    order, here, left = [], poly[-1], best[:]
    while left:
        nxt = min(left, key=lambda p: math.hypot(p[0] - here[0], p[1] - here[1]))
        order.append(nxt)
        left.remove(nxt)
        here = nxt
    return [to_ll(x, y) for x, y in order]
