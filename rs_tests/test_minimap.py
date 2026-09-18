"""The Rhino check: which SRV paints the minimap."""

import pytest

from rs_ui import minimap

IN_SRV = {"Flags": 1 << 26, "BodyName": "Test A 1", "Latitude": 10.0,
          "Longitude": 20.0, "PlanetRadius": 1_500_000, "Heading": 0}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(minimap, "_srv_type", None)
    monkeypatch.setattr(minimap, "_coverage", None)
    monkeypatch.setattr(minimap, "_in_srv", False)
    monkeypatch.setattr(minimap, "config", None)
    monkeypatch.setattr(minimap, "_down", lambda reason: None)
    monkeypatch.setattr(minimap, "_remember", lambda: None)
    monkeypatch.setattr(minimap, "enabled", lambda: True)
    monkeypatch.setattr(minimap, "_show_map", lambda *args: None)


def launch(kind):
    minimap.srv_event({"event": "LaunchSRV", "SRVType": kind})


class TestRhino:
    def test_an_srv_never_named_counts_as_the_rhino(self):
        assert minimap.in_rhino()

    def test_the_rhino(self):
        launch("mev_rhino")
        assert minimap.in_rhino()

    def test_the_scarab_is_not(self):
        launch("testbuggy")
        assert not minimap.in_rhino()

    def test_other_events_leave_it(self):
        launch("testbuggy")
        minimap.srv_event({"event": "DockSRV", "SRVType": "mev_rhino"})
        assert not minimap.in_rhino()

    def test_the_rhino_paints(self):
        launch("mev_rhino")
        minimap.update(None, IN_SRV)
        assert minimap._coverage is not None and minimap._coverage.version > 0

    def test_switched_off_paints_nothing(self, monkeypatch):
        monkeypatch.setattr(minimap, "enabled", lambda: False)
        launch("mev_rhino")
        minimap.update(None, IN_SRV)
        assert minimap._coverage is None

    def test_another_srv_paints_nothing(self):
        launch("testbuggy")
        minimap.update(None, IN_SRV)
        assert minimap._coverage is None
