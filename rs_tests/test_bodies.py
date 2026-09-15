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
        assert register.bodies()[0]["ground"] == "rock 80%+ [metallic magma]"

    def test_unlandable_bodies_never_enter(self, make_scan):
        register = bodies.Register()
        register.track({"event": "Location", "StarSystem": "Andel"})
        assert not register.track(make_scan("Andel 2", "Gas giant", landable=False),
                                  system="Andel")
        assert not register.track({"event": "Scan", "BodyName": "Andel", "StarType": "M"},
                                  system="Andel")
        assert len(register) == 0

    def test_a_scan_without_a_name_is_dropped(self, make_scan):
        register = bodies.Register()
        register.track({"event": "Location", "StarSystem": "Andel"})
        entry = make_scan("x", "Rocky body")
        del entry["BodyName"]
        assert not register.track(entry, system="Andel")

    def test_other_events_are_ignored(self):
        register = bodies.Register()
        assert not register.track({"event": "Music", "MusicTrack": "Exploration"})
        assert not register.track(None)
        assert not register.track({})


class TestLearningTheSystem:
    """EDMC starts with the game already running, replays the journal, and
    names the system on every line it hands over."""

    def test_any_line_names_the_system(self):
        register = bodies.Register()
        assert register.track({"event": "Music", "MusicTrack": "DockingComputer"},
                              system="Andel")
        assert register.system == "Andel"

    def test_learning_the_name_keeps_what_arrived_first(self, make_scan):
        """A count can reach us before any line names the system. Treating
        that as an arrival threw it away."""
        register = bodies.Register()
        register.track({"event": "FSSBodySignals", "BodyName": "Andel 1 a",
                        "Signals": [{"Type": "$PlanetaryMiningLocation_Name;",
                                     "Count": 17}]})
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.system == "Andel"
        assert register.bodies()[0]["locations"] == 17

    def test_learning_the_name_still_loads_the_cache(self):
        register = bodies.Register(on_arrive=lambda system: [
            {"name": "Andel 1 a", "ground": "rock 80%+ [none]", "distance": 1.0, "locations": 5}])
        register.track({"event": "Music"}, system="Andel")
        assert len(register) == 1

    def test_the_same_name_again_changes_nothing(self):
        register = bodies.Register()
        assert register.track({"event": "Music"}, system="Andel")
        assert not register.track({"event": "Music"}, system="Andel")


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
            "metal-rich", "rock 80%+ [none]", "icy"]

    def test_grouping_keeps_every_body(self, make_scan):
        register = bodies.Register()
        for index in range(3):
            register.track(make_scan(f"Rock {index}", "Rocky body", distance=index),
                           system="A")
        groups = register.by_ground()
        assert len(groups) == 1
        assert len(groups[0][1]) == 3


class TestMiningLocations:
    """The count comes from the journal, not from EDSM and not from Ardent.

    FSSBodySignals carries it from the FSS, without flying out to the body.
    SAASignalsFound carries it again after a detailed surface scan. Both were
    read off real journals before this was written.
    """

    def fss(self, name, count):
        return {"event": "FSSBodySignals", "BodyName": name, "Signals": [
            {"Type": "$PlanetaryMiningLocation_Name;",
             "Type_Localised": "Planetary Mining Location", "Count": count}]}

    def saa(self, name, count):
        return {"event": "SAASignalsFound", "BodyName": name, "Signals": [
            {"Type": "$PlanetaryMiningLocation_Name;", "Count": count},
            {"Type": "$SAA_SignalType_Human;", "Count": 1}]}

    def test_the_fss_count_lands_on_the_body(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.track(self.fss("Andel 1 a", 10))
        assert register.bodies()[0]["locations"] == 10

    def test_a_count_arriving_before_the_scan_is_not_lost(self, make_scan):
        """FSSBodySignals often lands first. Writing it into a row that does
        not exist yet would drop it."""
        register = bodies.Register()
        register.track(self.fss("Andel 1 a", 10))
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.bodies()[0]["locations"] == 10

    def test_a_surface_scan_raises_the_count(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(self.fss("Andel 1 a", 10))
        register.track(self.saa("Andel 1 a", 17))
        assert register.bodies()[0]["locations"] == 17

    def test_a_lower_count_never_wins(self, make_scan):
        """A detailed scan counts more than the FSS did, never fewer. A
        smaller number arriving later is a stale replay, not news."""
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(self.saa("Andel 1 a", 17))
        assert not register.track(self.fss("Andel 1 a", 10))
        assert register.bodies()[0]["locations"] == 17

    def test_a_body_nobody_counted_says_nothing(self, make_scan):
        """None, not 0. "0 locations" reads as barren, which is the opposite
        of what an uncounted body means."""
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.bodies()[0]["locations"] is None

    def test_signals_without_a_mining_type_are_ignored(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert not register.track({"event": "SAASignalsFound", "BodyName": "Andel 1 a",
                                   "Signals": [{"Type": "$SAA_SignalType_Biological;",
                                                "Count": 3}]})
        assert register.bodies()[0]["locations"] is None

    def test_a_ring_hotspot_is_not_a_mining_location(self):
        """SAASignalsFound on a ring lists hotspot materials. Those are laser
        mining, not ground mining, and no body row may take them."""
        register = bodies.Register()
        assert not register.track({"event": "SAASignalsFound",
                                   "BodyName": "Aramo AB 3 A Ring",
                                   "Signals": [{"Type": "Monazite", "Count": 3}]})

    def test_counts_do_not_survive_a_jump(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(self.saa("Andel 1 a", 17))
        register.track({"event": "FSDJump", "StarSystem": "Loha"})
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Loha")
        assert register.bodies()[0]["locations"] is None


class TestPersisting:
    """Every change goes to disk at once. A system you never leave - the game
    crashed, EDMC was closed on the pad - is exactly the one you would rather
    not scan a second time."""

    def test_every_scan_is_written(self, make_scan):
        seen = []
        register = bodies.Register(on_change=lambda system, found: seen.append((system, found)))
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track(make_scan("Andel 4 c", "Icy body", distance=1016.0), system="Andel")
        assert len(seen) == 2
        assert seen[-1][0] == "Andel"
        assert [body["name"] for body in seen[-1][1]] == ["Andel 1 a", "Andel 4 c"]

    def test_a_location_count_is_written_too(self, make_scan):
        seen = []
        register = bodies.Register(on_change=lambda system, found: seen.append(found))
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track({"event": "SAASignalsFound", "BodyName": "Andel 1 a",
                        "Signals": [{"Type": "$PlanetaryMiningLocation_Name;", "Count": 17}]})
        assert len(seen) == 2
        assert seen[-1][0]["locations"] == 17

    def test_a_repeat_scan_writes_nothing(self, make_scan):
        """Nothing changed, so nothing is written. The game rescans on every
        approach and each one would otherwise be a disk write."""
        seen = []
        register = bodies.Register(on_change=lambda system, found: seen.append(found))
        body = make_scan("Andel 1 a", "Rocky body")
        register.track(body, system="Andel")
        register.track(dict(body), system="Andel")
        assert len(seen) == 1

    def test_an_empty_system_writes_nothing(self):
        """A jump clears the list. Writing the empty result would replace a
        good cache file with an empty one."""
        seen = []
        register = bodies.Register(on_change=lambda system, found: seen.append(system))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        register.track({"event": "FSDJump", "StarSystem": "Loha"})
        assert seen == []

    def test_the_old_system_is_already_on_disk_before_the_jump(self, make_scan):
        seen = []
        register = bodies.Register(on_change=lambda system, found: seen.append(system))
        register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        register.track({"event": "FSDJump", "StarSystem": "Loha"})
        assert seen == ["Andel"]


class TestAdopting:
    def test_adopting_a_cached_system(self):
        register = bodies.Register()
        count = register.adopt("Andel", [
            {"name": "Andel 1 a", "ground": "rock 80%+ [magma]", "distance": 412.0,
             "locations": 17},
            {"name": "Andel 4 c", "ground": "icy", "distance": 1016.0, "locations": None},
        ])
        assert count == 2
        assert len(register) == 2
        assert register.system == "Andel"
        assert register.bodies()[0]["locations"] == 17
        assert [ground for ground, _ in register.by_ground()] == ["rock 80%+ [magma]", "icy"]

    def test_a_scan_after_adopting_still_updates(self, make_scan):
        register = bodies.Register()
        register.adopt("Andel", [{"name": "Andel 1 a", "ground": "rock 80%+ [none]",
                                  "distance": 412.0, "locations": 17}])
        assert register.track(make_scan("Andel 1 a", "Rocky body", "major metallic magma"),
                              system="Andel")
        body = register.bodies()[0]
        assert body["ground"] == "rock 80%+ [metallic magma]"
        assert body["locations"] == 17


    def test_a_body_cached_under_an_old_ground_name_groups_under_the_new_one(self):
        register = bodies.Register()
        register.adopt("Andel", [
            {"name": "Andel 1 a", "ground": "volcanic magma", "distance": 412.0, "locations": 17},
            {"name": "Andel 1 b", "ground": "rock 80%+ [magma]", "distance": 418.0, "locations": 8},
        ])
        assert [(ground, len(found)) for ground, found in register.by_ground()] \
            == [("rock 80%+ [magma]", 2)]


    def test_a_cached_magma_body_is_split_by_its_stored_volcanism(self):
        register = bodies.Register()
        register.adopt("Andel", [
            {"name": "Andel 1 a", "ground": "rock 80%+ [magma]", "distance": 412.0,
             "planet_class": "Rocky body", "volcanism": "minor rocky magma volcanism"},
            {"name": "Andel 1 b", "ground": "volcanic magma", "distance": 418.0},
        ])
        grounds_seen = {body["name"]: body["ground"] for body in register.bodies()}
        assert grounds_seen == {"Andel 1 a": "rock 80%+ [rocky magma]",
                                "Andel 1 b": "rock 80%+ [magma]"}


class TestArriving:
    """Jumping in loads what is known and the scans that follow add to it."""

    def cached(self, *names):
        return [{"name": name, "ground": "rock 80%+ [none]", "distance": float(index),
                 "locations": 5, "volcanism": "", "planet_class": "Rocky body"}
                for index, name in enumerate(names)]

    def test_a_known_system_arrives_filled(self):
        register = bodies.Register(on_arrive=lambda system: self.cached("Andel 1 a"))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        assert len(register) == 1
        assert register.bodies()[0]["locations"] == 5

    def test_an_unknown_system_arrives_empty(self):
        register = bodies.Register(on_arrive=lambda system: [])
        register.track({"event": "FSDJump", "StarSystem": "Nowhere"})
        assert len(register) == 0

    def test_new_scans_add_to_what_was_loaded(self, make_scan):
        register = bodies.Register(on_arrive=lambda system: self.cached("Andel 1 a"))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        register.track(make_scan("Andel 4 c", "Icy body", distance=1016.0), system="Andel")
        assert [body["name"] for body in register.bodies()] == ["Andel 1 a", "Andel 4 c"]

    def test_a_new_scan_updates_a_loaded_body(self, make_scan):
        """The cache said rocky because that is all the honk knew. A proper
        scan later has to win, and must not cost the location count."""
        register = bodies.Register(on_arrive=lambda system: self.cached("Andel 1 a"))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        register.track(make_scan("Andel 1 a", "Rocky body", "major metallic magma"),
                       system="Andel")
        body = register.bodies()[0]
        assert body["ground"] == "rock 80%+ [metallic magma]"
        assert body["locations"] == 5

    def test_arriving_does_not_write_back_what_it_just_read(self):
        """What came off disk is already on disk. Writing it again would turn
        every jump into a write."""
        written = []
        register = bodies.Register(on_change=lambda system, found: written.append(system),
                                   on_arrive=lambda system: self.cached("Andel 1 a"))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        assert written == []

    def test_the_first_new_scan_after_arriving_does_write(self, make_scan):
        written = []
        register = bodies.Register(on_change=lambda system, found: written.append(system),
                                   on_arrive=lambda system: self.cached("Andel 1 a"))
        register.track({"event": "FSDJump", "StarSystem": "Andel"})
        register.track(make_scan("Andel 4 c", "Icy body"), system="Andel")
        assert written == ["Andel"]


class TestIds:
    """SystemAddress and BodyID ride along with the names: a name is only
    unique inside its system."""

    def test_a_scan_keeps_the_ids_on_the_body(self, make_scan):
        written = []
        register = bodies.Register(on_change=lambda system, found: written.append(found))
        register.track(make_scan("Andel 1 a", "Rocky body", SystemAddress=111, BodyID=7),
                       system="Andel")
        assert written[-1][0]["system_address"] == 111 and written[-1][0]["body_id"] == 7
        assert register.ids("Andel", "Andel 1 a") == (111, 7)

    def test_a_body_cached_without_ids_is_written_once_with_them(self, make_scan):
        written = []
        register = bodies.Register(on_change=lambda system, found: written.append(found))
        register.adopt("Andel", [{"name": "Andel 1 a", "ground": "rock 80%+ [none]",
                                  "distance": 100.0, "volcanism": "", "gravity": None,
                                  "planet_class": "Rocky body"}])
        scan = make_scan("Andel 1 a", "Rocky body", SystemAddress=111, BodyID=7)
        assert register.track(scan, system="Andel")
        assert not register.track(dict(scan), system="Andel")
        assert len(written) == 1 and written[0][0]["body_id"] == 7

    def test_a_scan_without_ids_keeps_the_ones_held(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body", SystemAddress=111, BodyID=7),
                       system="Andel")
        assert not register.track(make_scan("Andel 1 a", "Rocky body"), system="Andel")
        assert register.bodies()[0]["body_id"] == 7

    def test_a_touchdown_names_a_body_no_scan_did(self):
        register = bodies.Register()
        register.track({"event": "FSDJump", "StarSystem": "Andel", "SystemAddress": 111})
        assert not register.track({"event": "Touchdown", "Body": "Andel 2", "BodyID": 9,
                                   "SystemAddress": 111}, system="Andel")
        assert register.ids("Andel", "Andel 2") == (111, 9)

    def test_a_jump_forgets_the_old_ids(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body", SystemAddress=111, BodyID=7),
                       system="Andel")
        register.track({"event": "FSDJump", "StarSystem": "Loha", "SystemAddress": 222})
        assert register.ids("Loha", "Andel 1 a") == (222, None)

    def test_a_line_about_another_system_names_nothing(self):
        register = bodies.Register()
        register.track({"event": "FSDJump", "StarSystem": "Andel", "SystemAddress": 111})
        register.track({"event": "ApproachBody", "Body": "Loha 3", "BodyID": 4,
                        "SystemAddress": 222}, system="Andel")
        assert register.ids("Andel", "Loha 3") == (111, None)

    def test_a_jump_target_is_not_where_you_are(self):
        """FSDTarget names the next system's address while you are still here."""
        register = bodies.Register()
        register.track({"event": "FSDTarget", "Name": "Loha", "SystemAddress": 222},
                       system="Andel")
        register.track({"event": "Touchdown", "Body": "Andel 2", "BodyID": 9,
                        "SystemAddress": 111}, system="Andel")
        assert register.ids("Andel", "Andel 2") == (111, 9)

    def test_asking_about_another_system_gives_nothing(self, make_scan):
        register = bodies.Register()
        register.track(make_scan("Andel 1 a", "Rocky body", SystemAddress=111, BodyID=7),
                       system="Andel")
        assert register.ids("Loha", "Andel 1 a") == (None, None)

    def test_adopting_a_cached_system_brings_its_ids(self):
        register = bodies.Register()
        register.adopt("Andel", [{"name": "Andel 1 a", "ground": "icy", "distance": 1.0,
                                  "system_address": 111, "body_id": 7}])
        assert register.ids("Andel", "Andel 1 a") == (111, 7)
