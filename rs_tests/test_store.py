"""The per-system cache: the commander's own scans, going to disk and back."""

import json
import time

import pytest

from rs_core import store

BODIES = [
    {"name": "Andel 1 a", "ground": "rock 80%+ [magma]", "distance": 412.0,
     "locations": 17, "volcanism": "major metallic magma", "planet_class": "Rocky body"},
    {"name": "Andel 4 c", "ground": "icy", "distance": 1016.0,
     "locations": None, "volcanism": "", "planet_class": "Icy body"},
]


class TestSafeName:
    @pytest.mark.parametrize("system,expected", [
        ("Andel", "Andel"),
        ("Col 285 Sector KM-V d2-36", "Col 285 Sector KM-V d2-36"),
        ("43 G. Canis Minoris", "43 G. Canis Minoris"),
        # Explorer refuses these, and one bad system must not take the cache down.
        ("Weird:System", "Weird_System"),
        ("a/b\\c", "a_b_c"),
        ("", "unknown"),
        (None, "unknown"),
    ])
    def test_names(self, system, expected):
        assert store.safe_name(system) == expected


class TestRoundTrip:
    def test_saves_and_loads(self, tmp_path):
        assert store.save("Andel", BODIES, root=str(tmp_path))
        assert store.load("Andel", root=str(tmp_path)) == BODIES

    def test_the_address_is_written_once_under_the_system(self, tmp_path):
        with_ids = [dict(body, system_address=111, body_id=index)
                    for index, body in enumerate(BODIES)]
        path = store.save("Andel", with_ids, root=str(tmp_path))
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        assert data["system_address"] == 111
        assert all("system_address" not in body for body in data["bodies"])
        assert [body["body_id"] for body in data["bodies"]] == [0, 1]
        assert store.load("Andel", root=str(tmp_path)) == with_ids

    def test_saving_does_not_change_the_bodies_handed_in(self, tmp_path):
        with_ids = [dict(BODIES[0], system_address=111)]
        store.save("Andel", with_ids, root=str(tmp_path))
        assert with_ids[0]["system_address"] == 111

    def test_an_unknown_system_is_empty(self, tmp_path):
        assert store.load("Nowhere", root=str(tmp_path)) == []

    def test_nothing_is_written_for_an_empty_system(self, tmp_path):
        """A system with no landable bodies is not worth a file, and writing
        one would make the next visit look cached and barren."""
        assert store.save("Andel", [], root=str(tmp_path)) is None
        assert store.save(None, BODIES, root=str(tmp_path)) is None
        assert store.systems(root=str(tmp_path)) == []

    def test_saving_twice_overwrites_rather_than_duplicates(self, tmp_path):
        store.save("Andel", BODIES, root=str(tmp_path))
        store.save("Andel", BODIES[:1], root=str(tmp_path))
        assert len(store.load("Andel", root=str(tmp_path))) == 1
        assert store.systems(root=str(tmp_path)) == ["Andel"]

    def test_listing_systems(self, tmp_path):
        store.save("Andel", BODIES, root=str(tmp_path))
        store.save("Loha", BODIES, root=str(tmp_path))
        assert store.systems(root=str(tmp_path)) == ["Andel", "Loha"]

    def test_listing_a_missing_folder(self, tmp_path):
        assert store.systems(root=str(tmp_path / "nope")) == []


class TestBadData:
    def test_broken_json_is_the_same_as_no_cache(self, tmp_path):
        (tmp_path / "Andel.json").write_text("{not json", encoding="utf-8")
        assert store.load("Andel", root=str(tmp_path)) == []

    def test_an_older_shape_is_dropped(self, tmp_path):
        """Dropping it costs one honk. Guessing at it costs a wrong answer
        that looks right."""
        (tmp_path / "Andel.json").write_text(
            json.dumps({"version": 0, "system": "Andel", "bodies": BODIES}),
            encoding="utf-8")
        assert store.load("Andel", root=str(tmp_path)) == []

    def test_bodies_that_are_not_a_list(self, tmp_path):
        (tmp_path / "Andel.json").write_text(
            json.dumps({"version": store.VERSION, "system": "Andel", "bodies": "nope"}),
            encoding="utf-8")
        assert store.load("Andel", root=str(tmp_path)) == []

    def test_no_temporary_file_survives_a_save(self, tmp_path):
        """The write goes through a temp file and a rename. A leftover .tmp
        would be a half-written system nobody ever cleans up."""
        store.save("Andel", BODIES, root=str(tmp_path))
        assert [p.name for p in tmp_path.iterdir()] == ["Andel.json"]


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
        debounced("Andel", BODIES, root=str(tmp_path))
        debounced.flush()
        assert store.load("Andel", root=str(tmp_path)) == BODIES
