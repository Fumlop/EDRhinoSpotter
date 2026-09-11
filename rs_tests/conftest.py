"""Shared fixtures, and the one path fix the suite needs.

pytest is run from the plugin folder, which EDMC puts on sys.path for us and
pytest does not. Without this every `from rs_core import ...` fails on import
rather than on a test.
"""

import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from rs_core import grounds                        # noqa: E402  - needs the path first


def scan(name, planet_class, volcanism="", landable=True, distance=100.0, **extra):
    """A journal Scan event, with only the fields the code reads.

    Deliberately not a full event: a fixture that carries forty fields hides
    which three the function under test actually uses.
    """
    entry = {
        "event": "Scan",
        "BodyName": name,
        "PlanetClass": planet_class,
        "Landable": landable,
        "Volcanism": volcanism,
        "DistanceFromArrivalLS": distance,
    }
    entry.update(extra)
    return entry


@pytest.fixture
def make_scan():
    return scan


@pytest.fixture
def sheet(tmp_path):
    """A Sheet over a small hand-written table.

    Not the shipped ground_rules.json: that file is regenerated from live data
    and its numbers move, which would make any assertion here a time bomb.
    """
    import json
    path = tmp_path / "ground_rules.json"
    path.write_text(json.dumps({
        "generated": "2026-01-01 00:00 UTC",
        "locations": {"volcanic magma": 57, "rocky": 164},
        "grounds": {
            "volcanic magma": [
                {"material": "Olivine",  "pct": 56.1, "median": 50000, "best": 90000},
                {"material": "Monazite", "pct": 45.6, "median": 400000, "best": 700000},
                {"material": "Tiny",     "pct": 1.2, "median": 1000, "best": 2000},
            ],
            "rocky": [
                {"material": "Magnesite", "pct": 43.3, "median": 40000, "best": 60000},
            ],
        },
    }), encoding="utf-8")
    return grounds.Sheet(str(path))


@pytest.fixture
def empty_sheet(tmp_path):
    """A Sheet whose file is not there - the panel still has to work."""
    return grounds.Sheet(str(tmp_path / "missing.json"))
