"""The one database: schema, transactions and the backup at shutdown."""

import os
import sqlite3

import pytest

from rs_core import database


@pytest.mark.unit
class TestConnect:

    def test_a_new_database_gets_the_schema(self, db):
        with database.connect() as conn:
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
            assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert {"bodies", "bookmarks", "maps"} <= tables
        assert os.path.isfile(db)

    def test_a_version_1_file_gets_the_newer_tables(self, db):
        with database.connect():
            pass
        with sqlite3.connect(db) as conn:
            conn.execute("DROP TABLE meta")
            conn.execute("PRAGMA user_version = 1")
        with database.connect() as conn:
            conn.execute("INSERT INTO meta (key, value) VALUES ('a', 'b')")
            assert conn.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION

    def test_a_block_that_raises_writes_nothing(self):
        with pytest.raises(RuntimeError):
            with database.connect() as conn:
                database.write_bookmark(conn, {"planet_name": "Andel 1 a"})
                raise RuntimeError("EDMC closing")
        with database.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 0

    def test_a_newer_schema_is_logged(self, db, caplog):
        with database.connect():
            pass
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA user_version = 99")
        with caplog.at_level("WARNING", logger="RhinoSpotter"):
            with database.connect():
                pass
        assert "schema 99" in caplog.records[0].getMessage()


@pytest.mark.unit
class TestWriteBookmark:

    def test_the_columns_follow_the_record(self):
        record = {"system": "Andel", "planet_name": "Andel 1 a", "commodity": "Monazite",
                  "rigs": 6, "location_index": 3, "system_address": 111, "body_id": 4}
        with database.connect() as conn:
            id = database.write_bookmark(conn, record)
            row = conn.execute("SELECT system, planet_name, commodity, rigs, location_index, "
                               "system_address, body_id, depleted_at FROM bookmarks "
                               "WHERE id = ?", (id,)).fetchone()
        assert row == ("Andel", "Andel 1 a", "Monazite", 6, 3, 111, 4, None)

    def test_the_same_source_is_imported_once(self):
        with database.connect() as conn:
            first = database.write_bookmark(conn, {"planet_name": "A"}, source="x.json")
            second = database.write_bookmark(conn, {"planet_name": "A"}, source="x.json")
            assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1
        assert first is not None and second is None


@pytest.mark.unit
class TestBackup:

    def test_nothing_to_back_up(self):
        assert database.backup() is None

    def test_an_empty_database_does_not_push_a_good_copy_out(self, db):
        with database.connect() as conn:
            id = database.write_bookmark(conn, {"planet_name": "Andel 1 a"})
        good = [database.backup() for _ in range(2)]
        with database.connect() as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = ?", (id,))
        assert database.backup() is None
        folder = os.path.join(os.path.dirname(db), "backups")
        assert sorted(os.path.join(folder, name) for name in os.listdir(folder)) == good

    def test_the_copy_holds_the_data(self):
        with database.connect() as conn:
            database.write_bookmark(conn, {"planet_name": "Andel 1 a"})
        copy = database.backup()
        with sqlite3.connect(copy) as conn:
            assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1

    def test_only_the_newest_two_are_kept(self, db):
        with database.connect() as conn:
            database.write_bookmark(conn, {"planet_name": "Andel 1 a"})
        made = [database.backup() for _ in range(4)]
        kept = sorted(os.listdir(os.path.join(os.path.dirname(db), "backups")))
        assert [os.path.join(os.path.dirname(db), "backups", name) for name in kept] == made[-2:]

    def test_a_failed_copy_keeps_the_old_ones_and_leaves_no_temp(self, db, monkeypatch):
        with database.connect() as conn:
            database.write_bookmark(conn, {"planet_name": "Andel 1 a"})
        good = [database.backup() for _ in range(2)]

        def refuse(src, dst):
            raise OSError("disk full")
        monkeypatch.setattr(database.os, "replace", refuse)
        assert database.backup() is None
        folder = os.path.join(os.path.dirname(db), "backups")
        assert sorted(os.path.join(folder, name) for name in os.listdir(folder)) == good
