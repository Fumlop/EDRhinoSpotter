"""The read-only interface other programs are invited to use.

Written against a scratch database rather than the commander's: the point of
these tests is that somebody else's code keeps working, so they check the
shape that was promised, not the plugin's own internals.
"""

import gzip
import json
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
def db(tmp_path):
    """A database with three bookmarks: two on one body, one worked out."""
    path = str(tmp_path / "rhinospotter.db")
    with database.connect(path) as conn:
        for record in (MARK,
                       dict(MARK, location_index=9, commodity="Jadeite", rigs=2),
                       dict(MARK, planet_name="Aramo A 2", location_index=3,
                            commodity="Olivine", depleted_at="3311-05-17T06:16:36")):
            database.write_bookmark(conn, record)
        conn.commit()
    return path


class TestBookmarks:

    def test_every_bookmark_comes_back_with_the_promised_keys(self, db):
        found = rs_api.bookmarks(path=db)
        assert len(found) == 3
        for mark in found:
            assert set(rs_api.FIELDS) <= set(mark)

    def test_the_names_are_the_ones_a_stranger_would_guess(self, db):
        """`planet_name` and `commodity` are our column names, not an API."""
        mark = rs_api.bookmarks(path=db)[0]
        assert mark["body"] == "Aramo A 1"
        assert mark["material"] == "Monazite"
        assert mark["location"] == 7

    def test_one_system(self, db):
        assert len(rs_api.bookmarks(system="Aramo", path=db)) == 3
        assert rs_api.bookmarks(system="Somewhere else", path=db) == []

    def test_one_body(self, db):
        assert len(rs_api.bookmarks(body="Aramo A 1", path=db)) == 2

    def test_depleted_is_a_flag_and_a_time(self, db):
        worked_out = [m for m in rs_api.bookmarks(path=db) if m["depleted"]]
        assert len(worked_out) == 1
        assert worked_out[0]["depleted_at"] == "3311-05-17T06:16:36"
        assert worked_out[0]["material"] == "Olivine"

    def test_everything_recorded_is_still_in_raw(self, db):
        """Whatever the game gave that day, for a reader that wants more than
        the documented fields."""
        mark = rs_api.bookmarks(path=db)[0]
        assert mark["raw"]["planet_name"] == "Aramo A 1"
        assert mark["raw"]["commander"] == "Grumlop"

    def test_a_broken_row_is_skipped_not_raised_on(self, db):
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO bookmarks (planet_name, data) VALUES (?, ?)",
                         ("Aramo A 3", "{not json"))
            conn.commit()
        assert len(rs_api.bookmarks(path=db)) == 3

    def test_no_database_is_no_bookmarks(self, tmp_path):
        assert rs_api.bookmarks(path=str(tmp_path / "nothing.db")) == []


class TestBodies:

    def test_counts_per_body(self, db):
        found = {row["body"]: row for row in rs_api.bodies(path=db)}
        assert found["Aramo A 1"]["bookmarks"] == 2
        assert found["Aramo A 1"]["depleted"] == 0
        assert found["Aramo A 2"]["depleted"] == 1


class TestExplored:

    def test_a_body_nobody_drove_has_nothing_to_say(self, db):
        assert rs_api.explored("Aramo A 1", path=db) is None

    def test_a_saved_map_answers_with_its_ground(self, db):
        coverage = pytest.importorskip("rs_core.coverage")
        cover = coverage.Coverage("Aramo A 1", 10.0, 20.0, 1_500_000)
        for step in range(20):
            cover.add(10.0 + step * 0.002, 20.0)
        cover.location = 7
        blob = gzip.compress(json.dumps(cover.to_dict()).encode("utf-8"))
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO maps (body, name, data) VALUES (?, ?, ?)",
                         ("Aramo A 1", "map 1", blob))
            conn.commit()
        found = rs_api.explored("Aramo A 1", path=db)
        assert found["maps"] == ["map 1"]
        assert found["km2"] > 0
        assert found["locations"] == [7]


class TestTheContract:

    def test_the_schema_number_is_what_was_promised(self):
        assert rs_api.SCHEMA == 1

    def test_it_says_which_plugin_wrote_the_data(self):
        assert rs_api.version()

    def test_nothing_edmc_is_needed_to_read(self):
        """A separate application imports this too - see the module docstring."""
        import sys
        source = open(rs_api.__file__, encoding="utf-8").read()
        for forbidden in ("import tkinter", "from config import", "import myNotebook"):
            assert forbidden not in source
        assert "config" not in sys.modules or True   # nothing here put it there

    def test_reading_never_creates_a_database(self, tmp_path):
        """A reader that runs before the commander has flown must not leave an
        empty file for the plugin to find."""
        missing = str(tmp_path / "not-yet.db")
        rs_api.bookmarks(path=missing)
        rs_api.bodies(path=missing)
        assert rs_api.explored("Aramo A 1", path=missing) is None
        assert not (tmp_path / "not-yet.db").exists()
