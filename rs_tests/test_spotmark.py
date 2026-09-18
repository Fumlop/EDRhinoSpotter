"""Status.json parsing, without EDMC or the game in the way.

Status.json is live-only: it holds the ship's position and the mining location
it is targeting, and both are gone the moment you fly off. Everything here is
about reading it once, correctly, at the press.
"""

import json

import pytest

from rs_core import spotmark


class TestRefinedMaterial:
    """MiningRefined's slug -> the dropdown name, as the journal writes them."""

    @pytest.mark.parametrize("slug,name", [
        ("$monazite_name;", "Monazite"),
        ("$helium3_name;", "Helium-3"),
        ("$helium_name;", "Helium"),
        ("$lowtemperaturediamond_name;", "Low Temp Diamonds"),
        ("$periclasedunite_name;", "Periclase Dunite"),
        ("$Thortveitite_Name;", None),          # not the journal's case
    ])
    def test_journal_slugs(self, slug, name):
        assert spotmark.refined_material({"event": "MiningRefined", "Type": slug}) == name

    def test_every_seen_slug_maps_to_a_dropdown_material(self):
        seen = ("alexandrite deuterium grandidierite helium helium3 iridium "
                "lowtemperaturediamond magnesite monazite periclasedunite ruby thortveitite")
        for slug in seen.split():
            assert spotmark.refined_material({"Type": f"${slug}_name;"}) in spotmark.MATERIALS

    def test_tritium_is_its_market_name(self):
        """Not seen in a MiningRefined yet. Market.json names it
        $tritium_name; / "Tritium", and the sheet has it on icy ground - it is
        in the list for commanders who mine carrier fuel on the surface."""
        assert spotmark.refined_material({"Type": "$tritium_name;"}) == "Tritium"

    def test_not_a_material(self):
        assert spotmark.refined_material({"Type": "$painite_name;"}) is None
        assert spotmark.refined_material({}) is None


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


class TestNearestIndex:
    """Touchdown and Liftoff carry the mining location in NearestDestination,
    which is the only place it survives the moment - Status.json drops it as
    soon as the location stops being the selected destination."""

    def test_reads_a_touchdown(self):
        entry = {"event": "Touchdown", "Latitude": 37.944237,
                 "Longitude": 20.287926,
                 "NearestDestination": "$SAA_Unknown_Signal:"
                                       "#type=$PlanetaryMiningLocation_Name;:#index=3;",
                 "NearestDestination_Localised": "Planetary Mining Location Signal (3)"}
        assert spotmark.nearest_index(entry) == 3

    def test_a_landing_next_to_something_else(self):
        """Settlements and beacons are nearest destinations too, and none of
        them is a mining location."""
        assert spotmark.nearest_index(
            {"event": "Touchdown", "NearestDestination": "Hutton Orbital"}) is None

    def test_a_landing_next_to_nothing(self):
        assert spotmark.nearest_index({"event": "Touchdown"}) is None

    def test_taking_off_yourself_leaves_the_location(self):
        assert spotmark.leaves_location({"event": "Liftoff", "PlayerControlled": True})
        assert spotmark.leaves_location({"event": "Liftoff"})

    def test_sending_the_ship_away_from_the_srv_does_not(self):
        assert not spotmark.leaves_location({"event": "Liftoff", "PlayerControlled": False})

    def test_other_events_do_not(self):
        for event in ("Touchdown", "LaunchSRV", "DockSRV", "Embark"):
            assert not spotmark.leaves_location({"event": event})


class TestOnGround:
    """What Bookmark asks once a second: is there anything under us to mark."""

    def test_standing_on_it(self):
        assert spotmark.on_ground({"Latitude": 1.0, "Longitude": 2.0,
                                   "Altitude": 0.0}) is True

    def test_orbital_cruise_has_coordinates_too(self):
        """250 km up over a body you have not landed on. The coordinates are
        real and the place is not one you are standing in."""
        assert spotmark.on_ground({"Latitude": 9.674362, "Longitude": 153.538544,
                                   "Altitude": 250038.0}) is False

    def test_no_body_at_all(self):
        assert spotmark.on_ground({"Altitude": 0.0}) is False

    def test_no_altitude_is_not_the_ground(self):
        """In space Status.json has no Altitude, and a missing number is not a
        low one."""
        assert spotmark.on_ground({"Latitude": 1.0, "Longitude": 2.0}) is False

    def test_an_empty_status(self):
        assert spotmark.on_ground({}) is False


class TestBodyHere:
    def test_over_a_body(self):
        status = {"BodyName": "Andel 1 a", "Latitude": 12.3, "Longitude": -45.6}
        assert spotmark.body_here(status) == "Andel 1 a"

    def test_supercruise_names_no_body(self):
        assert spotmark.body_here({"BodyName": "Andel 1 a"}) is None

    def test_empty_status(self):
        assert spotmark.body_here({}) is None
