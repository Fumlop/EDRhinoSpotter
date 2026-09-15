"""The JSON files of 4.1 and before, read into the database once."""

import gzip
import json
import os
import sqlite3

import pytest

from rs_core import cards, coverstore, migrate, spotcard, store

SYSTEM = "Andel"
BODIES = [{"name": "Andel 1 a", "ground": "icy", "distance": 12.0, "body_id": 3},
          {"name": "Andel 4 c", "ground": "icy", "distance": 99.0}]
MAP = {"origin": [1.0, 2.0], "radius": 381784.9, "location": 7, "stamps": [[1.0, 2.0]],
       "version": 1, "body": "Andel 1 a", "saved": 1789303169.545, "system_address": 111}


@pytest.fixture
def old(tmp_path, monkeypatch):
    r"""A %LOCALAPPDATA%\RhinoSpotter the way 4.1.14 left it."""
    root = tmp_path / "RhinoSpotter"
    (root / "data").mkdir(parents=True)
    (root / "data" / "Andel.json").write_text(json.dumps(
        {"version": 1, "system": SYSTEM, "system_address": 111, "bodies": BODIES}),
        encoding="utf-8")
    folder = root / "cards" / SYSTEM
    folder.mkdir(parents=True)
    (folder / "Andel_1_a_loc7_monazite.json").write_text(json.dumps(
        {"system": SYSTEM, "planet_name": "Andel 1 a", "commodity": "Monazite", "rigs": 6,
         "location_index": 7, "latitude": 1.0, "longitude": 2.0,
         "card": "Andel_1_a_loc7_monazite.png"}), encoding="utf-8")
    (folder / "Andel_1_a_loc7_monazite.png").write_bytes(b"png")
    (root / "coverage" / "Andel 1 a").mkdir(parents=True)
    (root / "coverage" / "Andel 1 a" / "map 1.json.gz").write_bytes(
        gzip.compress(json.dumps(MAP).encode()))
    (root / "coverage" / "Andel 1 a" / "map 1.png").write_bytes(b"png")
    monkeypatch.setattr(spotcard, "CARDS_ROOT", str(root / "cards"))
    return root


def snapshot(root):
    return {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}


class TestImport:

    def test_everything_readable_comes_in(self, old):
        result = migrate.run(root=str(old))
        assert result["imported"] == {"bodies": 2, "bookmarks": 1, "maps": 1}
        assert result["failed"] == []

        bodies = store.load(SYSTEM)
        assert [body["name"] for body in bodies] == ["Andel 1 a", "Andel 4 c"]
        assert all(body["system_address"] == 111 for body in bodies)
        assert bodies[0]["body_id"] == 3

        [bookmark] = cards.for_system(SYSTEM)
        assert bookmark["commodity"] == "Monazite" and bookmark["rigs"] == 6
        assert bookmark["path"] == str(old / "cards" / SYSTEM / "Andel_1_a_loc7_monazite.png")

        [(name, data)] = coverstore.maps("Andel 1 a")
        assert name == "map 1" and data["saved"] == MAP["saved"] and data["stamps"] == MAP["stamps"]

    def test_the_old_files_are_left_exactly_as_they_were(self, old):
        before = snapshot(old)
        migrate.run(root=str(old))
        assert snapshot(old) == before

    def test_migrate_done_says_what_came_in(self, old, db):
        migrate.run(root=str(old))
        text = open(migrate.done_path(), encoding="utf-8").read()
        assert os.path.dirname(migrate.done_path()) == os.path.dirname(db)
        assert "bodies: 2 imported" in text and "bookmarks: 1 imported" in text
        assert "maps: 1 imported" in text and "skipped" not in text

    def test_nothing_there_is_still_done(self, tmp_path):
        result = migrate.run(root=str(tmp_path / "never installed"))
        assert result["imported"] == {"bodies": 0, "bookmarks": 0, "maps": 0}
        assert os.path.exists(migrate.done_path())

    def test_a_bookmark_without_a_card_key_finds_its_png_by_name(self, old):
        path = old / "cards" / SYSTEM / "Andel_1_a_loc7_monazite.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        del record["card"]
        path.write_text(json.dumps(record), encoding="utf-8")
        migrate.run(root=str(old))
        assert cards.for_system(SYSTEM)[0]["path"] is not None

    def test_a_plain_json_map_is_read_and_a_gzipped_one_wins(self, old):
        folder = old / "coverage" / "Andel 1 a"
        (folder / "map 1.json").write_text(json.dumps(dict(MAP, location=1)), encoding="utf-8")
        (folder / "map 2.json").write_text(json.dumps(dict(MAP, location=2)), encoding="utf-8")
        migrate.run(root=str(old))
        found = dict(coverstore.maps("Andel 1 a"))
        assert found["map 1"]["location"] == 7 and found["map 2"]["location"] == 2

    def test_temp_files_and_pictures_are_not_maps(self, old):
        (old / "coverage" / "Andel 1 a" / "tmpg8danipk.tmp").write_bytes(b"half")
        result = migrate.run(root=str(old))
        assert result["imported"]["maps"] == 1 and result["failed"] == []


class TestBadFiles:

    def test_a_broken_file_is_listed_logged_and_the_rest_come_in(self, old, caplog):
        broken = old / "cards" / SYSTEM / "Andel_1_a_loc9_jadeite.json"
        broken.write_text("{not json", encoding="utf-8")
        (old / "data" / "Loha.json").write_text(json.dumps(
            {"version": 0, "system": "Loha", "bodies": BODIES}), encoding="utf-8")
        (old / "coverage" / "Andel 1 a" / "map 3.json.gz").write_bytes(b"\x1f\x8bnope")
        with caplog.at_level("WARNING", logger="RhinoSpotter"):
            result = migrate.run(root=str(old))

        assert result["imported"] == {"bodies": 2, "bookmarks": 1, "maps": 1}
        failed = [path for path, _ in result["failed"]]
        assert sorted(failed) == sorted([str(broken), str(old / "data" / "Loha.json"),
                                         str(old / "coverage" / "Andel 1 a" / "map 3.json.gz")])
        text = open(migrate.done_path(), encoding="utf-8").read()
        assert all(f"skipped {path}" in text for path in failed)
        assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 3
        assert "version 0, expected 1" in text

    def test_a_value_sqlite_will_not_store_skips_that_file_only(self, old):
        folder = old / "cards" / SYSTEM
        odd = folder / "Andel_1_a_loc8_jadeite.json"
        odd.write_text(json.dumps({"system": SYSTEM, "planet_name": "Andel 1 a",
                                   "rigs": [1, 2]}), encoding="utf-8")
        (old / "coverage" / "Andel 1 a" / "map 2.json").write_text(
            json.dumps(dict(MAP, body=None)), encoding="utf-8")
        result = migrate.run(root=str(old))
        assert result["imported"] == {"bodies": 2, "bookmarks": 1, "maps": 2}
        assert [path for path, _ in result["failed"]] == [str(odd)]
        assert os.path.exists(migrate.done_path())
        assert [name for name, _ in coverstore.maps("Andel 1 a")] == ["map 1", "map 2"]

    def test_a_folder_that_cannot_be_listed_leaves_no_marker(self, old, monkeypatch):
        real = os.listdir

        def locked(folder):
            if folder.endswith("cards"):
                raise PermissionError(13, "locked")
            return real(folder)
        monkeypatch.setattr(migrate.os, "listdir", locked)
        with pytest.raises(PermissionError):
            migrate.run(root=str(old))
        assert not os.path.exists(migrate.done_path())

    def test_a_database_that_cannot_be_written_leaves_no_marker(self, old, monkeypatch):
        """The next start tries again."""
        def broken(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")
        monkeypatch.setattr(migrate.database, "write_bookmark", broken)
        with pytest.raises(sqlite3.OperationalError):
            migrate.run(root=str(old))
        assert not os.path.exists(migrate.done_path())
        # and nothing half in: the bodies went in the same transaction
        assert store.load(SYSTEM) == []


class TestOnce:

    def test_with_migrate_done_no_folder_is_looked_at(self, old, monkeypatch):
        migrate.run(root=str(old))
        (old / "data" / "Loha.json").write_text(json.dumps(
            {"version": 1, "system": "Loha", "bodies": BODIES}), encoding="utf-8")

        def looked(*args):
            raise AssertionError("listed a folder")
        monkeypatch.setattr(migrate.os, "listdir", looked)
        assert migrate.run(root=str(old)) is None
        assert store.load("Loha") == []

    def test_a_lost_marker_is_written_again_without_importing(self, old):
        """migrate.done failed to write after the commit, or was deleted: the
        record in the database stands in, and a bookmark deleted since stays
        deleted."""
        migrate.run(root=str(old))
        report = open(migrate.done_path(), encoding="utf-8").read()
        os.remove(migrate.done_path())
        cards.delete(dict(cards.for_system(SYSTEM)[0], path=None))
        assert migrate.run(root=str(old)) is None
        assert open(migrate.done_path(), encoding="utf-8").read() == report
        assert cards.for_system(SYSTEM) == []

    def test_a_marker_that_cannot_be_written_leaves_the_record(self, old, monkeypatch):
        real, full = migrate.atomic.write_text, [True]

        def refuse(path, text):
            if full[0]:
                raise OSError("disk full")
            real(path, text)
        # Not monkeypatch.undo(): that would also undo the test database path.
        monkeypatch.setattr(migrate.atomic, "write_text", refuse)
        with pytest.raises(OSError):
            migrate.run(root=str(old))
        full[0] = False
        assert migrate.run(root=str(old)) is None
        assert os.path.exists(migrate.done_path())
        assert len(cards.for_system(SYSTEM)) == 1

    def test_a_second_run_with_no_record_adds_nothing_and_keeps_newer_rows(self, old, db):
        migrate.run(root=str(old))
        os.remove(migrate.done_path())
        with sqlite3.connect(db) as conn:
            conn.execute("DELETE FROM meta")
        # Written by the plugin after the first import - newer than the files.
        store.save(SYSTEM, BODIES[:1])
        record = cards.for_system(SYSTEM)[0]
        cards.set_depleted(record, True, when="2026-09-15T10:00:00+00:00")

        result = migrate.run(root=str(old))
        assert result["imported"]["bookmarks"] == 0 and result["kept"]["bookmarks"] == 1
        assert result["kept"]["maps"] == 1
        [again] = cards.for_system(SYSTEM)
        assert again["depleted_at"] == "2026-09-15T10:00:00+00:00"
        assert [body["name"] for body in store.load(SYSTEM)][0] == "Andel 1 a"


class TestLeftovers:

    def test_nothing_before_the_import(self, old):
        assert migrate.leftovers(root=str(old)) == []

    def test_the_imported_json_and_temp_files_go_pictures_stay(self, old):
        (old / "coverage" / "Andel 1 a" / "tmpg8danipk.tmp").write_bytes(b"half")
        migrate.run(root=str(old))
        deleted, failed = migrate.delete_leftovers(root=str(old))
        assert failed == [] and len(deleted) == 4
        left = sorted(str(p.relative_to(old)) for p in old.rglob("*") if p.is_file())
        assert left == [os.path.join("cards", SYSTEM, "Andel_1_a_loc7_monazite.png"),
                        os.path.join("coverage", "Andel 1 a", "map 1.png")]
        assert not (old / "data").exists()
        # and the plugin reads on as before
        assert len(store.load(SYSTEM)) == 2 and len(cards.for_system(SYSTEM)) == 1
        assert len(coverstore.maps("Andel 1 a")) == 1

    def test_a_lost_database_deletes_nothing(self, old, db):
        """migrate.done is still there, the database is new and empty."""
        migrate.run(root=str(old))
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(db + suffix):
                os.remove(db + suffix)
        assert [path for path in migrate.leftovers(root=str(old))
                if not path.endswith(".tmp")] == []

    def test_a_bookmark_deleted_after_the_import_keeps_its_file(self, old):
        migrate.run(root=str(old))
        cards.delete(dict(cards.for_system(SYSTEM)[0], path=None))
        assert not any(path.endswith("monazite.json")
                       for path in migrate.leftovers(root=str(old)))

    def test_a_skipped_file_is_kept(self, old):
        broken = old / "cards" / SYSTEM / "Andel_1_a_loc9_jadeite.json"
        broken.write_text("{not json", encoding="utf-8")
        migrate.run(root=str(old))
        assert str(broken) not in migrate.leftovers(root=str(old))

    def test_a_file_written_after_the_import_is_kept(self, old):
        migrate.run(root=str(old))
        newer = old / "data" / "Loha.json"
        newer.write_text("{}", encoding="utf-8")
        later = os.path.getmtime(migrate.done_path()) + 60
        os.utime(newer, (later, later))
        assert str(newer) not in migrate.leftovers(root=str(old))
