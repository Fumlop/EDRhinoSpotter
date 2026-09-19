"""The read-only interface other programs are invited to use.

Written against a scratch database rather than the commander's: the point of
these tests is that somebody else's code keeps working, so they check the shape
that was promised, not the plugin's own internals.
"""

import sqlite3

import pytest

import rs_api
from rs_core import database

MARK = {"system": "Aramo", "planet_name": "Aramo A 1", "location_index": 7,
        "commodity": "Monazite", "rigs": 4, "latitude": 12.345678,
        "longitude": -98.765432, "heading": 214, "amount": "High",
        "density": "Low", "marked_at": "3311-05-14T18:40:00",
        "commander": "Grumlop"}


@pytest.fixture
def marks(tmp_path):
    """Three bookmarks: two on one body in one system, one worked out in
    another - so a filter that does nothing cannot pass."""
    path = str(tmp_path / "rhinospotter.db")
    with database.connect(path) as conn:
        for record in (MARK,
                       dict(MARK, location_index=9, commodity="Jadeite", rigs=2),
                       dict(MARK, system="Eme", planet_name="Eme A 1 a",
                            location_index=3, commodity="Olivine",
                            depleted_at="3311-05-17T06:16:36")):
            database.write_bookmark(conn, record)
        conn.commit()
    return path


class TestBookmarks:

    def test_the_names_are_the_ones_a_stranger_would_guess(self, marks):
        """`planet_name` and `commodity` are column names, not an interface."""
        mark = rs_api.bookmarks(path=marks)[0]
        assert mark["body"] == "Aramo A 1"
        assert mark["material"] == "Monazite"
        assert mark["location"] == 7
        assert mark["rigs"] == 4
        assert mark["latitude"] == 12.345678

    def test_one_system(self, marks):
        assert len(rs_api.bookmarks(system="Aramo", path=marks)) == 2
        assert len(rs_api.bookmarks(system="Eme", path=marks)) == 1
        assert rs_api.bookmarks(system="Somewhere else", path=marks) == []

    def test_one_body(self, marks):
        assert len(rs_api.bookmarks(body="Aramo A 1", path=marks)) == 2

    def test_depleted_is_a_flag_and_a_time(self, marks):
        worked_out = [m for m in rs_api.bookmarks(path=marks) if m["depleted"]]
        assert len(worked_out) == 1
        assert worked_out[0]["depleted_at"] == "3311-05-17T06:16:36"

    def test_the_plugins_own_storage_does_not_leak_through(self, marks):
        """Only the documented keys. What is stored beside them has changed
        twice already and is nobody else's to build on."""
        documented = {"system", "body", "location", "material", "rigs", "latitude",
                      "longitude", "heading", "amount", "density", "depleted",
                      "depleted_at", "marked_at", "commander", "id"}
        assert set(rs_api.bookmarks(path=marks)[0]) == documented

    def test_a_broken_row_is_skipped_not_raised_on(self, marks):
        with sqlite3.connect(marks) as conn:
            conn.execute("INSERT INTO bookmarks (planet_name, data) VALUES (?, ?)",
                         ("Aramo A 3", "{not json"))
            conn.commit()
        assert len(rs_api.bookmarks(path=marks)) == 3

    def test_no_database_is_no_bookmarks(self, tmp_path):
        assert rs_api.bookmarks(path=str(tmp_path / "nothing.db")) == []


class TestBodies:

    def test_counts_per_body(self, marks):
        found = {row["body"]: row for row in rs_api.bodies(path=marks)}
        assert found["Aramo A 1"]["bookmarks"] == 2
        assert found["Aramo A 1"]["depleted"] == 0
        assert found["Eme A 1 a"]["depleted"] == 1

    def test_one_system(self, marks):
        assert [row["body"] for row in rs_api.bodies(system="Eme", path=marks)]             == ["Eme A 1 a"]


class TestRevision:
    """The only way a separate program knows to read again."""

    def test_it_moves_when_a_bookmark_is_added(self, marks):
        before = rs_api.revision(path=marks)
        with database.connect(marks) as conn:
            database.write_bookmark(conn, dict(MARK, location_index=22,
                                               commodity="Jadeite"))
            conn.commit()
        assert rs_api.revision(path=marks) != before

    def test_it_moves_when_one_is_marked_depleted(self, marks):
        before = rs_api.revision(path=marks)
        with database.connect(marks) as conn:
            conn.execute("UPDATE bookmarks SET depleted_at = ? WHERE id = 1",
                         ("3311-05-18T09:00:00",))
            conn.commit()
        assert rs_api.revision(path=marks) != before

    def test_it_moves_when_one_is_deleted(self, marks):
        before = rs_api.revision(path=marks)
        with database.connect(marks) as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = 1")
            conn.commit()
        assert rs_api.revision(path=marks) != before

    def test_it_stands_still_while_nothing_changes(self, marks):
        assert rs_api.revision(path=marks) == rs_api.revision(path=marks)

    def test_it_does_not_come_from_this_process(self, marks):
        """The counter in rs_core.database belongs to whoever did the writing.
        A separate application polling that one read 0 for ever."""
        before = rs_api.revision(path=marks)
        database.changed()                         # the in-process counter moves
        assert rs_api.revision(path=marks) == before

    def test_no_database_is_zero(self, tmp_path):
        assert rs_api.revision(path=str(tmp_path / "nothing.db")) == 0


class TestTheContract:

    def test_the_surface_is_the_four_calls_and_the_schema(self):
        """Every public name has to keep working while SCHEMA is 1, so there are
        no more of them than were asked for."""
        public = {name for name in vars(rs_api)
                  if not name.startswith("_")
                  and name not in ("json", "os", "sqlite3", "zlib", "database",
                                   "VERSION")}
        assert public == {"SCHEMA", "version", "bookmarks", "bodies", "revision"}

    def test_reading_needs_neither_edmc_nor_pillow(self):
        """A separate application imports this in a plain interpreter."""
        import pathlib
        import subprocess
        import sys
        import tempfile
        source = ("import sys; sys.path.insert(0, %r); import rs_api;"
                  "print('tkinter' in sys.modules, 'PIL' in sys.modules)"
                  % str(pathlib.Path(rs_api.__file__).parent))
        out = subprocess.run([sys.executable, "-c", source], capture_output=True,
                             text=True, cwd=tempfile.gettempdir())
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "False False"

    def test_reading_never_creates_a_database(self, tmp_path):
        """A reader that runs before the commander has flown must not leave an
        empty file for the plugin to find."""
        missing = str(tmp_path / "not-yet.db")
        rs_api.bookmarks(path=missing)
        rs_api.bodies(path=missing)
        rs_api.revision(path=missing)
        assert not (tmp_path / "not-yet.db").exists()
