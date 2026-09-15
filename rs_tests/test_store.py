"""The per-system cache: the commander's own scans, going to disk and back."""

import sqlite3
import time

from rs_core import store

BODIES = [
    {"name": "Andel 1 a", "ground": "rock 80%+ [magma]", "distance": 412.0,
     "locations": 17, "volcanism": "major metallic magma", "planet_class": "Rocky body"},
    {"name": "Andel 4 c", "ground": "icy", "distance": 1016.0,
     "locations": None, "volcanism": "", "planet_class": "Icy body"},
]


class TestRoundTrip:
    def test_saves_and_loads(self, db):
        assert store.save("Andel", BODIES) == db
        assert store.load("Andel") == BODIES

    def test_a_body_without_the_address_takes_the_systems(self):
        """The address belongs to the system; a body scanned before it was
        known gets it from the others on the way back."""
        with_ids = [dict(BODIES[0], system_address=111, body_id=0), dict(BODIES[1], body_id=1)]
        store.save("Andel", with_ids)
        assert [body["system_address"] for body in store.load("Andel")] == [111, 111]
        assert [body["body_id"] for body in store.load("Andel")] == [0, 1]

    def test_saving_does_not_change_the_bodies_handed_in(self):
        with_ids = [dict(BODIES[0], system_address=111)]
        store.save("Andel", with_ids)
        assert with_ids[0]["system_address"] == 111

    def test_an_unknown_system_is_empty(self):
        assert store.load("Nowhere") == []

    def test_nothing_is_written_for_an_empty_system(self):
        """A system with no landable bodies is not worth a row, and writing
        one would make the next visit look cached and barren."""
        assert store.save("Andel", []) is None
        assert store.save(None, BODIES) is None
        assert store.systems() == []

    def test_saving_twice_overwrites_rather_than_duplicates(self):
        store.save("Andel", BODIES)
        store.save("Andel", BODIES[:1])
        assert len(store.load("Andel")) == 1
        assert store.systems() == ["Andel"]

    def test_systems_do_not_mix(self):
        store.save("Andel", BODIES)
        store.save("Loha", BODIES[:1])
        assert len(store.load("Andel")) == 2 and len(store.load("Loha")) == 1

    def test_listing_systems(self):
        store.save("Loha", BODIES)
        store.save("Andel", BODIES)
        assert store.systems() == ["Andel", "Loha"]

    def test_an_explicit_database(self, tmp_path):
        other = str(tmp_path / "other.db")
        store.save("Andel", BODIES, db=other)
        assert store.load("Andel") == []
        assert store.load("Andel", db=other) == BODIES


class TestBadData:
    def test_a_database_that_cannot_be_opened_is_no_cache(self, tmp_path):
        folder = tmp_path / "a folder, not a file"
        folder.mkdir()
        assert store.load("Andel", db=str(folder)) == []
        assert store.systems(db=str(folder)) == []
        assert store.save("Andel", BODIES, db=str(folder)) is None

    def test_a_broken_row_is_the_same_as_no_cache(self, db, caplog):
        store.save("Andel", BODIES)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE bodies SET data = '{not json'")
        with caplog.at_level("WARNING", logger="RhinoSpotter"):
            assert store.load("Andel") == []
        assert "Andel" in caplog.records[0].getMessage()


class TestDebounced:
    """A burst of changes, written once. The timer is a real one, so the
    delays here are short and the waits are generous multiples of them."""

    def counter(self):
        calls = []
        return calls, lambda *args, **kwargs: calls.append(args) or "written"

    def test_a_burst_is_one_write(self):
        calls, write = self.counter()
        debounced = store.Debounced(delay=0.05, write=write)
        for index in range(45):
            debounced("Andel", BODIES[:1] * index)
        assert calls == []                      # nothing yet - that is the point
        time.sleep(0.3)
        assert len(calls) == 1

    def test_the_last_change_is_the_one_written(self):
        calls, write = self.counter()
        debounced = store.Debounced(delay=0.05, write=write)
        debounced("Andel", BODIES[:1])
        debounced("Andel", BODIES)
        time.sleep(0.3)
        assert calls == [("Andel", BODIES)]

    def test_flush_writes_now(self):
        calls, write = self.counter()
        debounced = store.Debounced(delay=30, write=write)
        debounced("Andel", BODIES)
        assert debounced.flush() == "written"
        assert len(calls) == 1

    def test_flush_takes_the_pending_write_with_it(self):
        # Otherwise shutdown writes once and the timer writes again after.
        calls, write = self.counter()
        debounced = store.Debounced(delay=0.05, write=write)
        debounced("Andel", BODIES)
        debounced.flush()
        time.sleep(0.3)
        assert len(calls) == 1

    def test_flush_with_nothing_waiting_does_nothing(self):
        calls, write = self.counter()
        debounced = store.Debounced(delay=0.05, write=write)
        assert debounced.flush() is None
        assert calls == []

    def test_a_burst_longer_than_the_delay_still_reaches_disk(self):
        # The timer is not restarted by every change, so a long sweep is
        # written as it goes rather than held until it ends.
        calls, write = self.counter()
        debounced = store.Debounced(delay=0.05, write=write)
        for _ in range(3):
            debounced("Andel", BODIES)
            time.sleep(0.15)
        assert len(calls) >= 2

    def test_it_drops_in_where_save_was(self, tmp_path):
        debounced = store.Debounced(delay=0.05)
        debounced("Andel", BODIES)
        debounced.flush()
        assert store.load("Andel") == BODIES
