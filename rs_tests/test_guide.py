"""Turning a Status.json and a bookmark into one arrow."""

import math

import pytest

from rs_core import guide

MOON = 1_738_000.0      # metres, near enough a small landable body


def status(**fields):
    """Status.json with the fields the guide reads, nothing else."""
    base = {"BodyName": "Andel 1 a", "Latitude": 0.0, "Longitude": 0.0,
            "Heading": 0, "Altitude": 30.0, "PlanetRadius": MOON}
    base.update(fields)
    return base


TARGET = {"planet_name": "Andel 1 a", "latitude": 0.0, "longitude": 0.0,
          "location_index": 11, "commodity": "Monazite"}


def target(**fields):
    spot = dict(TARGET)
    spot.update(fields)
    return spot


class TestBearing:
    def test_the_four_corners(self):
        assert guide.bearing(0, 0, 1, 0) == pytest.approx(0.0)
        assert guide.bearing(0, 0, 0, 1) == pytest.approx(90.0)
        assert guide.bearing(0, 0, -1, 0) == pytest.approx(180.0)
        assert guide.bearing(0, 0, 0, -1) == pytest.approx(270.0)

    def test_never_negative(self):
        """A bearing is what you set the compass to, and nobody flies -45."""
        assert 0.0 <= guide.bearing(10, 10, 9, 9) < 360.0


class TestDistance:
    def test_one_degree_of_latitude(self):
        """The same number metres_per_degree gives, which is what the flat
        measurement uses - the two must agree at short range or one of them is
        measuring a different planet."""
        assert guide.distance(0, 0, 1, 0, MOON) == pytest.approx(
            MOON * math.pi / 180.0, rel=1e-9)

    def test_longitude_shrinks_with_latitude(self):
        equator = guide.distance(0, 0, 0, 1, MOON)
        north = guide.distance(60, 0, 60, 1, MOON)
        assert north == pytest.approx(equator * 0.5, rel=1e-3)

    def test_standing_on_it(self):
        assert guide.distance(12.5, -40.25, 12.5, -40.25, MOON) == 0.0


class TestFix:
    def test_points_relative_to_the_nose(self):
        """Facing east with the spot due north is a left turn, not a bearing
        of zero."""
        reading = guide.fix(status(Heading=90), target(latitude=1.0))
        assert reading["state"] == "guiding"
        assert reading["bearing_deg"] == pytest.approx(0.0)
        assert reading["relative_deg"] == pytest.approx(270.0)

    def test_no_heading_leaves_the_arrow_north_up(self):
        """Heading is -1 where the game has none. The overlay draws a
        different instrument then, so the reading must say so rather than
        rotating by minus one degree."""
        reading = guide.fix(status(Heading=-1), target(latitude=1.0))
        assert reading["relative_deg"] is None
        assert reading["bearing_deg"] == pytest.approx(0.0)

    def test_arrived_inside_the_patch(self):
        close = 20.0 / (MOON * math.pi / 180.0)      # 20 m north, in degrees
        reading = guide.fix(status(), target(latitude=close))
        assert reading["state"] == "arrived"
        assert reading["distance_m"] == pytest.approx(20.0, rel=1e-3)

    def test_the_wrong_body_is_its_own_answer(self):
        """Sitting on the wrong moon and sitting in orbit look the same from
        the cockpit and want opposite actions."""
        reading = guide.fix(status(BodyName="Andel 4 c"), target())
        assert reading["state"] == "wrong body"
        assert reading["distance_m"] is None

    def test_too_high_for_coordinates(self):
        reading = guide.fix(status(Latitude=None, Longitude=None), target())
        assert reading["state"] == "no position"

    def test_not_at_a_body(self):
        reading = guide.fix({"Flags": 0}, target())
        assert reading["state"] == "no body"

    def test_a_bookmark_from_before_the_coordinates(self):
        reading = guide.fix(status(), target(latitude=None, longitude=None))
        assert reading["state"] == "no target"

    def test_an_empty_status_says_nothing_worse_than_no_body(self):
        """read_status returns {} on a read that landed mid-write, and that
        must not put the overlay into a state of its own."""
        assert guide.fix({}, target())["state"] == "no body"


class TestWords:
    def test_metres_then_kilometres(self):
        assert guide.metres(42.4) == "42 m"
        assert guide.metres(950) == "950 m"
        assert guide.metres(1420) == "1.4 km"
        assert guide.metres(118_000) == "118 km"
        assert guide.metres(None) == "-"

    def test_the_compass_rounds_to_the_eight(self):
        assert guide.compass(0) == "N"
        assert guide.compass(46) == "NE"
        assert guide.compass(200) == "S"
        assert guide.compass(359) == "N"
        assert guide.compass(None) == ""
