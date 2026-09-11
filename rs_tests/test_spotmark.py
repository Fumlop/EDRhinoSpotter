"""Status.json parsing, without EDMC or the game in the way.

Status.json is live-only: it holds the ship's position and the mining location
it is targeting, and both are gone the moment you fly off. Everything here is
about reading it once, correctly, at the press.
"""

import json

import pytest

from rs_core import spotmark


class TestLocationIndex:
    @pytest.mark.parametrize("status,expected", [
        ({"Destination": {"Name": "$SAA_Unknown_Signal:#index=15;"}}, 15),
        ({"Destination": {"Name": "$SAA_Unknown_Signal:#index=3;", "Body": 12}}, 3),
        ({"Destination": {"Name": "$SAA_Unknown_Signal:#index=1;"}}, 1),
        # A body selected as the destination is not a mining location.
        ({"Destination": {"Name": "Col 285 Sector KM-V d2-106 3 a"}}, None),
        ({"Destination": {}}, None),
        ({}, None),
    ])
    def test_index(self, status, expected):
        assert spotmark.location_index(status) == expected


class TestReadStatus:
    def test_reads_a_file(self, tmp_path):
        path = tmp_path / "Status.json"
        path.write_text(json.dumps({"BodyName": "Andel 1 a"}), encoding="utf-8")
        assert spotmark.read_status(str(path))["BodyName"] == "Andel 1 a"

    def test_a_missing_file_is_empty_not_an_error(self, tmp_path):
        assert spotmark.read_status(str(tmp_path / "nope.json")) == {}

    def test_a_half_written_file_is_empty_not_an_error(self, tmp_path):
        """The game rewrites Status.json constantly. A read landing mid-write
        must cost the press, not the session."""
        path = tmp_path / "Status.json"
        path.write_text('{"BodyName": "And', encoding="utf-8")
        assert spotmark.read_status(str(path)) == {}


class TestMark:
    def test_carries_the_body_and_the_position(self):
        spot = spotmark.mark({"BodyName": "X 1 a", "Latitude": 1.5, "Longitude": -2.5,
                              "Heading": 214, "Altitude": 1200},
                             system="X", commander="Fumlop")
        assert spot["planet_name"] == "X 1 a"
        assert spot["system"] == "X"
        assert spot["commander"] == "Fumlop"
        assert spot["heading"] == 214
        assert spot["marked_at"] is not None

    def test_nothing_is_measured(self):
        """A mark off the surface is empty rather than wrong - that is what
        makes pressing on the wrong screen visible."""
        spot = spotmark.mark({})
        assert spot["planet_name"] is None
        assert spot["latitude"] is None


class TestOnSurface:
    def test_both_coordinates(self):
        assert spotmark.on_surface(
            spotmark.mark({"BodyName": "X 1 a", "Latitude": 1.5, "Longitude": -2.5}))

    @pytest.mark.parametrize("status", [
        {"BodyName": "X 1 a", "Latitude": 1.5},
        {"BodyName": "X 1 a", "Longitude": -2.5},
        {"BodyName": "X 1 a"},
        {},
    ])
    def test_a_mark_you_cannot_fly_back_to(self, status):
        assert not spotmark.on_surface(spotmark.mark(status))


class TestMaterials:
    def test_the_dropdown_is_not_empty(self):
        assert len(spotmark.MATERIALS) > 20

    def test_it_is_sorted_and_unique(self):
        """It is a dropdown. Two entries the same, or an unsorted list, is a
        thing you hunt through on every single press."""
        assert list(spotmark.MATERIALS) == sorted(spotmark.MATERIALS)
        assert len(set(spotmark.MATERIALS)) == len(spotmark.MATERIALS)
