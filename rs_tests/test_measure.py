"""Measuring a patch: the geometry, and the border being driven."""

import math

import pytest

from rs_core import measure

RADIUS = 1_480_764.875          # a real body, out of Status.json


def square(size, radius=RADIUS, lat=0.0, lon=0.0):
    """A square `size` metres on a side, as latitudes and longitudes."""
    scale = measure.metres_per_degree(radius)
    dlat = size / scale
    dlon = size / (scale * math.cos(math.radians(lat)))
    return [(lat, lon), (lat, lon + dlon), (lat + dlat, lon + dlon), (lat + dlat, lon)]


def status(lat, lon, body="Andel 1 a", radius=RADIUS):
    return {"Latitude": lat, "Longitude": lon, "PlanetRadius": radius,
            "BodyName": body}


class TestArea:
    def test_a_square(self):
        polygon = measure.to_metres(square(100), RADIUS)
        assert measure.area(polygon) == pytest.approx(10_000, rel=0.01)

    def test_direction_does_not_matter(self):
        """Driving the border clockwise or anticlockwise is the same fence."""
        polygon = measure.to_metres(square(100), RADIUS)
        assert measure.area(polygon) == pytest.approx(measure.area(polygon[::-1]))

    def test_a_triangle_is_half_its_box(self):
        assert measure.area([(0, 0), (100, 0), (0, 100)]) == pytest.approx(5_000)

    def test_a_shape_that_is_not_a_shape(self):
        """Two points enclose nothing, and neither does one or none."""
        assert measure.area([(0, 0), (10, 10)]) == 0.0
        assert measure.area([(0, 0)]) == 0.0
        assert measure.area([]) == 0.0

    def test_a_concave_shape(self):
        """An L. The point of driving a border rather than a radius is that
        the shape is whatever you drove."""
        el = [(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100)]
        assert measure.area(el) == pytest.approx(7_500)


class TestInside:
    def test_the_middle_is_in(self):
        assert measure.inside([(0, 0), (100, 0), (100, 100), (0, 100)], 50, 50)

    def test_outside_is_out(self):
        box = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert not measure.inside(box, 150, 50)
        assert not measure.inside(box, -1, 50)
        assert not measure.inside(box, 50, 200)

    def test_the_notch_of_an_L_is_out(self):
        el = [(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100)]
        assert measure.inside(el, 25, 75)
        assert not measure.inside(el, 75, 75)


class TestRigs:
    def test_spacing_decides_the_count(self):
        """A 76 m grid on a 200 m square: three across, three up."""
        box = [(0, 0), (200, 0), (200, 200), (0, 200)]
        assert measure.rigs(box, spacing=76.0) == 9

    def test_a_patch_smaller_than_the_spacing_still_holds_one(self):
        """4,000 m2 is 63 m square - obviously room for a rig, and it read as
        none. The grid started on the corner, and a corner is on the boundary,
        which counts as outside."""
        box = [(0, 0), (63, 0), (63, 63), (0, 63)]
        assert measure.area(box) == pytest.approx(3_969)
        assert measure.rigs(box, spacing=76.0) == 1

    def test_a_sliver_that_misses_every_grid_point(self):
        """Long and thin: no grid point lands in it, and you can still put a
        rig down somewhere along it."""
        sliver = [(0, 0), (800, 0), (800, 5), (0, 5)]
        assert measure.rigs(sliver, spacing=76.0) >= 1

    def test_no_area_is_no_rigs(self):
        """The floor is one rig for a shape with area, not one rig for
        anything at all."""
        assert measure.rigs([(0, 0), (100, 0), (200, 0)], spacing=76.0) == 0

    def test_a_bigger_patch_holds_more(self):
        small = [(0, 0), (200, 0), (200, 200), (0, 200)]
        large = [(0, 0), (400, 0), (400, 400), (0, 400)]
        assert measure.rigs(large) > measure.rigs(small)

    def test_the_notch_is_not_counted(self):
        """The whole reason for a polygon: a shape with a bite out of it holds
        fewer rigs than its bounding box."""
        el = [(0, 0), (300, 0), (300, 150), (150, 150), (150, 300), (0, 300)]
        box = [(0, 0), (300, 0), (300, 300), (0, 300)]
        assert measure.rigs(el) < measure.rigs(box)

    def test_nothing_to_measure(self):
        assert measure.rigs([(0, 0), (10, 10)]) == 0
        assert measure.rigs([]) == 0


class TestTrack:
    def test_it_follows_the_border(self):
        track = measure.Track()
        for lat, lon in square(200):
            assert track.add(status(lat, lon))
        assert len(track) == 4
        assert track.area() == pytest.approx(40_000, rel=0.02)
        assert track.rigs() == 9

    def test_standing_still_adds_nothing(self):
        """Status.json is rewritten several times a second and the SRV drifts
        a metre while parked. Without a minimum step, a stop at the fence adds
        a hundred points that say nothing."""
        track = measure.Track()
        track.add(status(0.0, 0.0))
        for _ in range(50):
            assert not track.add(status(0.000001, 0.000001))
        assert len(track) == 1

    def test_a_status_with_no_position(self):
        """You are in the ship, or in the menu. Nothing to record."""
        track = measure.Track()
        assert not track.add({"BodyName": "Andel 1 a", "PlanetRadius": RADIUS})
        assert not track.add({})
        assert not track.add(None)
        assert len(track) == 0

    def test_a_status_with_no_radius(self):
        """Off a planet there is no radius, and without it metres cannot be
        worked out at all."""
        track = measure.Track()
        assert not track.add({"Latitude": 1.0, "Longitude": 2.0})

    def test_another_body_is_refused(self):
        """You cannot drive from one body to another, so a sample from
        somewhere else is a mistake and not a corner."""
        track = measure.Track()
        track.add(status(0.0, 0.0, body="Andel 1 a"))
        assert not track.add(status(10.0, 10.0, body="Andel 4 c"))
        assert len(track) == 1

    def test_it_remembers_the_body_and_radius(self):
        track = measure.Track()
        track.add(status(0.0, 0.0))
        assert track.body == "Andel 1 a"
        assert track.radius == RADIUS

    def test_nothing_driven_measures_nothing(self):
        track = measure.Track()
        assert track.area() == 0.0
        assert track.rigs() == 0
        assert track.polygon() == []
