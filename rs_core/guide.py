"""Where the spot is, from where you are standing.

Status.json says where the ship or the SRV is and which way it is pointing; a
bookmark says where the patch is. This turns the two into one arrow: how far,
and how far round from the nose.

Great circle rather than the flat earth measure.py uses. A patch is a few
hundred metres across and flat is right for that, but you start guiding from
orbital cruise, and over a hundred kilometres flat is not.

No tkinter, so the maths can be checked without EDMC or a display. See
rs_tests/test_guide.py.
"""

import math

# Close enough to be looking at it. The mining location itself is bigger than
# this, so a tighter number would be measuring the drift of Status.json.
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
    """One reading, from one Status.json and one bookmark.

    `state` is what the overlay draws, and every case that is not "guiding" or
    "arrived" is a case where there is no arrow to draw. They are separate
    states rather than one "no fix" because they need different words: sitting
    in orbit and sitting on the wrong body look identical from the cockpit and
    want opposite actions.
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
        # Supercruise, a station, or the game is not running.
        reading["state"] = "no body"
        return reading
    if reading["body"] != target.get("planet_name"):
        reading["state"] = "wrong body"
        return reading

    lat, lon = status.get("Latitude"), status.get("Longitude")
    radius = status.get("PlanetRadius")
    if lat is None or lon is None or not radius:
        # On the right body but too high for the game to give coordinates.
        reading["state"] = "no position"
        return reading

    reading["distance_m"] = distance(lat, lon, to_lat, to_lon, radius)
    reading["bearing_deg"] = bearing(lat, lon, to_lat, to_lon)

    # Heading is -1 when the game has none to give, which is most of the way
    # down. Without it the arrow can only point north-up, and saying so is
    # better than rotating by a number that means nothing.
    heading = status.get("Heading")
    if heading is not None and heading >= 0:
        reading["relative_deg"] = (reading["bearing_deg"] - heading) % 360.0

    reading["state"] = "arrived" if reading["distance_m"] <= ARRIVED_M else "guiding"
    return reading


def metres(value):
    """A distance as it is read out loud: 42 m, 950 m, 1.4 km, 118 km."""
    if value is None:
        return "-"
    if value < 1000:
        return f"{value:,.0f} m"
    if value < 10000:
        return f"{value / 1000:.1f} km"
    return f"{value / 1000:,.0f} km"


COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(degrees):
    """The bearing as a word, for when there is no heading to turn it into an
    arrow - a number of degrees is not something anyone flies by."""
    if degrees is None:
        return ""
    return COMPASS[int((degrees % 360.0) / 45.0 + 0.5) % 8]
