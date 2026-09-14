"""Status.json -> one marked mining spot.

No tkinter, no database, no PIL, so the parsing can be checked without EDMC in
the way. See test_spotmark.py.

Status.json is live-only: it holds the ship's position and the mining location
it is targeting, and both are gone the moment you fly off. Mark reads it once,
at the press, and keeps the answer.
"""

import json
import os
import re
from datetime import datetime, timezone

STATUS_PATH = os.path.expandvars(
    r"%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous\Status.json"
)

# The sheet's 22 materials plus bromellite, which is minable on ice and simply
# has no rows yet. Hardcoded rather than read off the sheet, so the dropdown
# fills even when mining_sheet.json is missing.
MATERIALS = (
    "Alexandrite", "Bastnasite", "Bromellite", "Deuterium", "Diamond",
    "Grandidierite", "Helium", "Helium-3", "Iridium", "Jadeite",
    "Low Temp Diamonds", "Magnesite", "Monazite", "Olivine", "Osmium",
    "Periclase Dunite", "Platinum", "Quartz Pyroxenite", "Rhodplumsite",
    "Ruby", "Sapphire", "Serendibite", "Thortveitite",
)


def _index(name):
    """The number out of '$SAA_Unknown_Signal:#index=15;', or None."""
    match = re.search(r"#index=(\d+)", name or "")
    return int(match.group(1)) if match else None


def location_index(status):
    """The mining location the ship is targeting, from Status.json.

    Destination.Name reads '$SAA_Unknown_Signal:#index=15;' while a planetary
    mining location is the selected destination.
    """
    return _index((status.get("Destination") or {}).get("Name"))


def nearest_index(entry):
    """The mining location a Touchdown or Liftoff happened at.

    Those two journal events carry `NearestDestination`, the same
    $SAA_Unknown_Signal string Status.json gives - and being in the journal it
    survives the moment, where Status.json holds it only while the location is
    still the selected destination.

    Nearest, not selected. Set down between two locations and it names the
    closer one, which is why the coordinates beside it are what a bookmark is
    actually made of.
    """
    return _index(entry.get("NearestDestination"))


def read_status(path=STATUS_PATH):
    """Status.json, or an empty dict - the game rewrites it constantly and a
    read that lands mid-write must not cost you the mark."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def mark(status, system=None, commander=None, marked_at=None):
    """One spot: where you are standing, nothing measured.

    latitude/longitude are absent unless the ship is on the surface, which is
    what makes a mark on the wrong screen visible rather than silently empty.
    """
    return {
        "system": system,
        "planet_name": status.get("BodyName"),
        "location_index": location_index(status),
        "latitude": status.get("Latitude"),
        "longitude": status.get("Longitude"),
        "heading": status.get("Heading"),
        "altitude": status.get("Altitude"),
        "planet_radius": status.get("PlanetRadius"),
        "commander": commander,
        "marked_at": marked_at or datetime.now(timezone.utc),
    }


def body_here(status):
    """The body Status.json has us on or over, or None.

    Latitude and longitude are only in Status.json near a body - orbital
    cruise, glide, landed, in the SRV - so their presence is the test, and the
    body is whatever it names. Deep space and supercruise give None.
    """
    if status.get("Latitude") is None or status.get("Longitude") is None:
        return None
    return status.get("BodyName") or None


def on_surface(spot):
    """A mark without coordinates is not a place anyone can fly back to."""
    return spot.get("latitude") is not None and spot.get("longitude") is not None


# Orbital cruise hands out coordinates too - 250 km up, over a body you have
# not landed on. A patch is where you are standing, so height is the test that
# separates the two, and a hundred metres is the ship on its gear plus slack.
GROUND_M = 100.0


def on_ground(status, ceiling=GROUND_M):
    """Whether Status.json is describing somewhere you are standing.

    Takes Status.json, not a mark - the panel asks this once a second to know
    whether Bookmark can do anything, and building a mark to ask would be
    building one every second.
    """
    if status.get("Latitude") is None or status.get("Longitude") is None:
        return False
    altitude = status.get("Altitude")
    return altitude is not None and altitude <= ceiling
