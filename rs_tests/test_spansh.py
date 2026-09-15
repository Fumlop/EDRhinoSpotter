"""Bodies from Spansh: mapped to the journal's words, and only ever filling gaps."""

import json

import pytest

from rs_core import bodies, spansh

ADDRESS = 3657332462290
# Trimmed from the real dump of Eme and r Velorum, 2026-09-15.
DUMP = {"system": {"name": "Eme", "id64": ADDRESS, "bodies": [
    {"name": "Eme A 1 a", "bodyId": 8, "isLandable": True, "subType": "Rocky body",
     "volcanismType": None, "gravity": 0.0528844702763332, "distanceToArrival": 471.305284,
     "signals": {"signals": {"$PlanetaryMiningLocation_Name;": 10,
                             "$SAA_SignalType_Biological;": 3}}},
    {"name": "Eme A 2 a", "bodyId": 12, "isLandable": True, "subType": "Icy body",
     "gravity": 0.1, "distanceToArrival": 900.0},
    {"name": "r Velorum 9 a", "bodyId": 40, "isLandable": True,
     "subType": "High metal content world", "volcanismType": "Major Rocky Magma",
     "gravity": 0.367236871622311, "distanceToArrival": 1300.0},
    {"name": "Eme A", "bodyId": 1, "type": "Star", "subType": "K (Yellow-Orange) Star"},
    {"name": "Eme A 3", "bodyId": 20, "isLandable": False, "subType": "Gas giant"},
]}}


class TestToBodies:

    def test_only_landables_in_the_journals_words(self):
        found = {b["name"]: b for b in spansh.to_bodies(DUMP, ADDRESS)}
        assert sorted(found) == ["Eme A 1 a", "Eme A 2 a", "r Velorum 9 a"]
        hmc = found["r Velorum 9 a"]
        # As the journal Scan of the same body wrote it.
        assert hmc["planet_class"] == "High metal content body"
        assert hmc["volcanism"] == "major rocky magma volcanism"
        assert hmc["ground"] == "high-metal-content"
        assert hmc["gravity"] == pytest.approx(3.601492, abs=1e-3)

    def test_no_volcanism_is_empty_and_the_count_comes_along(self):
        rock = spansh.to_bodies(DUMP, ADDRESS)[0]
        assert rock["volcanism"] == "" and rock["ground"] == "rock 80%+ [none]"
        assert rock["locations"] == 10 and rock["body_id"] == 8
        assert rock["system_address"] == ADDRESS and rock["source"] == "spansh"

    def test_a_body_without_a_count_is_unprobed(self):
        icy = [b for b in spansh.to_bodies(DUMP, ADDRESS) if b["name"] == "Eme A 2 a"][0]
        assert "locations" not in icy

    def test_nonsense_is_no_bodies(self):
        assert spansh.to_bodies({}, ADDRESS) == []
        assert spansh.to_bodies({"system": {"bodies": [None, 3]}}, ADDRESS) == []


class TestFetch:

    def test_an_answer(self):
        found = spansh.fetch(ADDRESS, opener=lambda url, timeout: json.dumps(DUMP).encode())
        assert len(found) == 3

    def test_offline_is_none_and_logged(self, caplog, monkeypatch):
        monkeypatch.setattr(spansh, "_warned", False)

        def offline(url, timeout):
            raise OSError("no route")
        with caplog.at_level("DEBUG", logger="RhinoSpotter"):
            assert spansh.fetch(ADDRESS, opener=offline) is None
            assert spansh.fetch(ADDRESS, opener=offline) is None
        assert [r.levelname for r in caplog.records] == ["WARNING", "DEBUG"]

    def test_garbage_is_none(self):
        assert spansh.fetch(ADDRESS, opener=lambda url, timeout: b"<html>") is None


def arrived(saved=None):
    register = bodies.Register(on_change=(lambda system, found: saved.append(found))
                               if saved is not None else None)
    register.track({"event": "FSDJump", "StarSystem": "Eme", "SystemAddress": ADDRESS})
    return register


def scan(name, planet_class="Rocky body", volcanism="", gravity=5.0):
    return {"event": "Scan", "BodyName": name, "Landable": True, "PlanetClass": planet_class,
            "Volcanism": volcanism, "SurfaceGravity": gravity, "DistanceFromArrivalLS": 470.0,
            "SystemAddress": ADDRESS, "BodyID": 8}


class TestAddKnown:
    """Spansh fills gaps. The journal and the cache always win."""

    def test_fills_an_empty_system_and_writes_it(self):
        saved = []
        register = arrived(saved)
        assert register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(register) == 3 and len(saved[-1]) == 3

    def test_a_body_already_scanned_is_left_alone(self):
        register = arrived()
        register.track(scan("Eme A 1 a", gravity=5.0), system="Eme")
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        mine = [b for b in register.bodies() if b["name"] == "Eme A 1 a"][0]
        assert mine["gravity"] == 5.0 and "source" not in mine

    def test_a_later_scan_replaces_the_spansh_body(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert register.track(scan("Eme A 1 a", gravity=5.0), system="Eme")
        mine = [b for b in register.bodies() if b["name"] == "Eme A 1 a"][0]
        assert mine["gravity"] == 5.0 and "source" not in mine

    def test_the_commanders_own_count_replaces_spanshs_even_if_lower(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        signals = {"event": "FSSBodySignals", "BodyName": "Eme A 1 a", "SystemAddress": ADDRESS,
                   "Signals": [{"Type": bodies.MINING_SIGNAL, "Count": 7}]}
        assert register.track(signals, system="Eme")
        assert [b["locations"] for b in register.bodies() if b["name"] == "Eme A 1 a"] == [7]

    def test_a_count_already_held_is_not_replaced(self):
        register = arrived()
        register.track(scan("Eme A 1 a"), system="Eme")
        register.track({"event": "SAASignalsFound", "BodyName": "Eme A 1 a",
                        "SystemAddress": ADDRESS,
                        "Signals": [{"Type": bodies.MINING_SIGNAL, "Count": 4}]}, system="Eme")
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert [b["locations"] for b in register.bodies() if b["name"] == "Eme A 1 a"] == [4]

    def test_an_answer_for_a_system_left_behind_is_dropped(self):
        register = arrived()
        register.track({"event": "FSDJump", "StarSystem": "Loha", "SystemAddress": 42})
        assert not register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(register) == 0

    def test_nothing_new_changes_nothing(self):
        saved = []
        register = arrived(saved)
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        before = len(saved)
        assert not register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(saved) == before
