"""Distance and bearing from a Status.json position to a bookmark.

fix() combines the two into the reading the overlay arrow draws: metres to the
target and degrees from the nose.

Great circle, not the flat approximation in measure.py: guiding starts in
orbital cruise at over 100 km, where flat is wrong.

No tkinter. Tests in rs_tests/test_guide.py.
"""

import math

# Arrival radius in metres. A mining location is wider than this; below it the
# reading would track Status.json drift.
ARRIVED_M = 50.0


def bearing(lat, lon, to_lat, to_lon):
    """Initial great-circle bearing in degrees. 0 is north, clockwise."""
    here, there = math.radians(lat), math.radians(to_lat)
    delta = math.radians(to_lon - lon)
    east = math.sin(delta) * math.cos(there)
    north = (math.cos(here) * math.sin(there)
             - math.sin(here) * math.cos(there) * math.cos(delta))
    return math.degrees(math.atan2(east, north)) % 360.0


def distance(lat, lon, to_lat, to_lon, radius):
    """Great-circle distance in metres over a body of that radius."""
    here, there = math.radians(lat), math.radians(to_lat)
    dlat = there - here
    dlon = math.radians(to_lon - lon)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(here) * math.cos(there) * math.sin(dlon / 2) ** 2)
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def fix(status, target):
    """One Status.json dict + one bookmark -> the reading the overlay draws.

    Returns {state, body, distance_m, bearing_deg, relative_deg, altitude_m}.
    state is one of: 'no target' (bookmark has no coordinates), 'no body'
    (supercruise, docked, game not running), 'wrong body', 'no position' (right
    body, too high for coordinates), 'guiding', 'arrived' (<= ARRIVED_M).

    Only 'guiding' and 'arrived' carry a distance and bearing. The other four
    are kept apart because they need different text.
    """
    reading = {
        "state": "no target",
        "body": status.get("BodyName"),
        "distance_m": None,
        "bearing_deg": None,
        "relative_deg": None,
        "altitude_m": status.get("Altitude"),
    }
    to_lat, to_lon = target.get("latitude"), target.get("longitude")
    if to_lat is None or to_lon is None:
        return reading

    if not reading["body"]:
        # Supercruise, docked, or the game is not running.
        reading["state"] = "no body"
        return reading
    if reading["body"] != target.get("planet_name"):
        reading["state"] = "wrong body"
        return reading

    lat, lon = status.get("Latitude"), status.get("Longitude")
    radius = status.get("PlanetRadius")
    if lat is None or lon is None or not radius:
        # Right body, but above the altitude where Status.json has lat/lon.
        reading["state"] = "no position"
        return reading

    reading["distance_m"] = distance(lat, lon, to_lat, to_lon, radius)
    reading["bearing_deg"] = bearing(lat, lon, to_lat, to_lon)

    # Status.json Heading is -1 for most of the descent. relative_deg stays
    # None then, and the overlay draws north-up.
    heading = status.get("Heading")
    if heading is not None and heading >= 0:
        reading["relative_deg"] = (reading["bearing_deg"] - heading) % 360.0

    reading["state"] = "arrived" if reading["distance_m"] <= ARRIVED_M else "guiding"
    return reading


def metres(value):
    """Metres -> '42 m', '950 m', '1.4 km', '118 km'. None -> '-'."""
    if value is None:
        return "-"
    if value < 1000:
        return f"{value:,.0f} m"
    if value < 10000:
        return f"{value / 1000:.1f} km"
    return f"{value / 1000:,.0f} km"


COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(degrees):
    """Degrees -> one of the 8 COMPASS points. None -> ''.

    Used when relative_deg is None and no arrow can be rotated.
    """
    if degrees is None:
        return ""
    return COMPASS[int((degrees % 360.0) / 45.0 + 0.5) % 8]
