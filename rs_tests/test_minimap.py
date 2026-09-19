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


class FakeConfig:
    """EDMC's config, as much of it as the map asks for."""

    def __init__(self, **values):
        self.values = values

    def get_bool(self, key, default=False):
        return self.values.get(key, default)

    def get_str(self, key, default=""):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


GAME = (100, 50, 1700, 950)          # a windowed game, 1600 x 900


class TestFreeMove:
    """Where a dragged map lands, and what keeps it on the screen."""

    def test_off_by_default(self):
        assert minimap.free_move() is False

    def test_the_offset_is_from_the_game_window_not_the_screen(self, monkeypatch):
        monkeypatch.setattr(minimap, "config",
                            FakeConfig(**{minimap.POS_KEY: "40,30"}))
        assert minimap.offset() == (40, 30)
        assert minimap.free_xy(GAME, 260, 380, (40, 30)) == (140, 80)

    def test_the_game_moving_takes_the_map_with_it(self):
        moved = (500, 200, 2100, 1100)
        assert minimap.free_xy(moved, 260, 380, (40, 30)) == (540, 230)

    def test_an_offset_past_the_edge_is_pulled_back_inside(self):
        """The game gets resized and a monitor gets unplugged. A map parked
        outside the window cannot be dragged back."""
        x, y = minimap.free_xy(GAME, 260, 380, (5000, 5000))
        assert (x, y) == (1700 - 260, 950 - 380)

    def test_a_negative_offset_stops_at_the_top_left(self):
        assert minimap.free_xy(GAME, 260, 380, (-800, -800)) == (100, 50)

    def test_a_window_bigger_than_the_game_still_starts_inside_it(self):
        assert minimap.free_xy(GAME, 4000, 4000, (10, 10)) == (100, 50)

    def test_nonsense_in_the_setting_is_no_offset_at_all(self, monkeypatch):
        """Then the map is back in its corner, which is somewhere it can be seen."""
        for stored in ("", "left", "10", "10,20,30", "a,b"):
            monkeypatch.setattr(minimap, "config", FakeConfig(**{minimap.POS_KEY: stored}))
            assert minimap.offset() is None

    def test_no_config_no_offset(self, monkeypatch):
        monkeypatch.setattr(minimap, "config", None)
        assert minimap.offset() is None


class TestPlaceMode:

    def test_placing_without_a_window_says_so_and_does_not_raise(self, monkeypatch):
        said = []
        monkeypatch.setattr(minimap, "_window", None)
        monkeypatch.setattr(minimap, "_notice_now", said.append)
        assert minimap.place() is False
        assert said and "SRV" in said[0]

    def test_locking_when_nothing_is_being_placed_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(minimap, "_placing", False)
        assert minimap._lock() is False
