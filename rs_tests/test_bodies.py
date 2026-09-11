"""The per-system body register, fed the way EDMC feeds it."""

from rs_core import bodies


class TestTracking:
    def test_a_scan_is_kept(self, make_scan):
        register = bodies.Register()
        assert register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert len(register) == 1
        assert register.system == "Andel"

    def test_the_same_scan_twice_changes_nothing(self, make_scan):
        """The game rescans on re-entry. A second identical Scan must not
        redraw the panel, or the count flickers on every approach."""
        register = bodies.Register()
        body = make_scan("Andel 1 a", "Rocky body")
        assert register.track(body, system="Andel")
        assert not register.track(dict(body), system="Andel")
        assert len(register) == 1

    def test_a_better_scan_of_the_same_body_replaces_it(self, make_scan):
        """AutoScan first, Detailed later, same body. One row, the newer facts."""
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(make_scan("Andel 1 a", "Rocky body", "major metallic magma"),
                       system="Andel")
        assert len(register) == 1
        assert register.bodies()[0]["ground"] == "volcanic magma"

    def test_unlandable_bodies_never_enter(self, make_scan):
        register = bodies.Register()
        assert not register.track(make_scan("Andel 2", "Gas giant", landable=False),
                                  system="Andel")
        assert not register.track({"event": "Scan", "BodyName": "Andel", "StarType": "M"},
                                  system="Andel")
        assert len(register) == 0

    def test_a_scan_without_a_name_is_dropped(self, make_scan):
        register = bodies.Register()
        entry = make_scan("x", "Rocky body")
        del entry["BodyName"]
        assert not register.track(entry, system="Andel")

    def test_other_events_are_ignored(self):
        register = bodies.Register()
        assert not register.track({"event": "Music", "MusicTrack": "Exploration"})
        assert not register.track(None)
        assert not register.track({})


class TestArrival:
    def test_jumping_empties_the_list(self, make_scan):
        """The panel answers 'what is here'. A list that still held the last
        system would answer it wrongly, and look right doing it."""
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.track({"event": "FSDJump", "StarSystem": "Loha"})
        assert len(register) == 0
        assert register.system == "Loha"

    def test_location_for_the_system_you_are_already_in_keeps_the_list(self, make_scan):
        """Location fires on game start. Throwing the list away there would
        empty the panel every time EDMC restarts while docked."""
        register = bodies.Register()
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert not register.track({"event": "Location", "StarSystem": "Andel"})
        assert len(register) == 1

    def test_a_carrier_jump_counts_as_arriving(self):
        register = bodies.Register()
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        assert register.track({"event": "CarrierJump", "StarSystem": "Loha"})
        assert register.system == "Loha"

    def test_a_scan_from_another_system_resets_the_list(self, make_scan):
        """Belt and braces: if an arrival event was missed, the first scan
        from elsewhere still clears what cannot be here."""
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(make_scan("Loha 3", "Rocky body"), system="Loha")
        assert register.system == "Loha"
        assert [body["name"] for body in register.bodies()] == ["Loha 3"]


class TestOrdering:
    def test_bodies_come_back_nearest_first(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Far", "Rocky body", distance=2000.0), system="A")
        register.track(make_scan("Near", "Rocky body", distance=30.0), system="A")
        assert [body["name"] for body in register.bodies()] == ["Near", "Far"]

    def test_a_body_with_no_distance_sorts_last(self, make_scan):
        register = bodies.Register()
        entry = make_scan("Unknown", "Rocky body")
        del entry["DistanceFromArrivalLS"]
        register.track(entry, system="A")
        register.track(make_scan("Far", "Rocky body", distance=9000.0), system="A")
        assert [body["name"] for body in register.bodies()] == ["Far", "Unknown"]

    def test_grouping_follows_the_system_map_order(self, make_scan):
        """Metal, then rock, then ice - not alphabetical, and not the order
        the commander happened to scan them in."""
        register = bodies.Register()
        register.track(make_scan("Ice", "Icy body"), system="A")
        register.track(make_scan("Rock", "Rocky body"), system="A")
        register.track(make_scan("Metal", "Metal rich body"), system="A")
        assert [ground for ground, _ in register.by_ground()] == [
            "metal-rich", "rocky", "icy"]

    def test_grouping_keeps_every_body(self, make_scan):
        register = bodies.Register()
        for index in range(3):
            register.track(make_scan(f"Rock {index}", "Rocky body", distance=index),
                           system="A")
        groups = register.by_ground()
        assert len(groups) == 1
        assert len(groups[0][1]) == 3
