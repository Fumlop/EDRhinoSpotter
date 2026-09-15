"""The minimap's saved maps: points to the database, gzipped, and back."""

import gzip
import sqlite3

import pytest

from rs_core import coverstore

BODY = "Col 285 Sector LS-P b7-1 A 2"
DATA = {"origin": [53.259235, -178.692352], "radius": 1352744.5, "location": 9,
        "drops": [[53.259235, -178.692352]], "stamps": [[53.259235, -178.692352]]}


@pytest.mark.unit
class TestRoundTrip:

    def test_saves_gzipped_and_loads(self, db):
        assert coverstore.save(BODY, "map 1", DATA) == db
        with sqlite3.connect(db) as conn:
            [(raw,)] = conn.execute("SELECT data FROM maps").fetchall()
        assert raw[:2] == b"\x1f\x8b"
        [(name, data)] = coverstore.maps(BODY)
        assert name == "map 1"
        assert data["stamps"] == DATA["stamps"] and data["body"] == BODY
        assert isinstance(data["saved"], float)

    def test_saving_a_name_again_replaces_it(self):
        coverstore.save(BODY, "map 1", DATA)
        coverstore.save(BODY, "map 1", dict(DATA, location=3))
        [(_, data)] = coverstore.maps(BODY)
        assert data["location"] == 3

    def test_a_broken_map_is_skipped_not_fatal(self, db):
        coverstore.save(BODY, "map 1", DATA)
        with sqlite3.connect(db) as conn:
            rows = [("map 2", gzip.compress(b"{not json")),
                    ("map 3", gzip.compress(b'{"version": 99}')),
                    ("map 4", b"not gzip at all")]
            conn.executemany("INSERT INTO maps (body, name, data) VALUES (?, ?, ?)",
                             [(BODY, name, raw) for name, raw in rows])
        assert [name for name, _ in coverstore.maps(BODY)] == ["map 1"]

    def test_an_unknown_body_has_no_maps(self):
        assert coverstore.maps("Nowhere 1") == []

    def test_a_database_that_cannot_be_opened_is_no_maps(self, tmp_path):
        folder = tmp_path / "a folder, not a file"
        folder.mkdir()
        assert coverstore.maps(BODY, db=str(folder)) == []
        assert coverstore.save(BODY, "map 1", DATA, db=str(folder)) is None


@pytest.mark.unit
class TestNames:

    def test_first_map_is_map_1(self, tmp_path):
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 1"

    def test_next_is_one_past_the_highest(self, tmp_path):
        coverstore.save(BODY, "map 1", DATA)
        coverstore.save(BODY, "map 4", DATA)
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 5"

    def test_a_picture_with_no_map_still_takes_its_number(self, tmp_path):
        """A new map must never overwrite an old one's PNG."""
        from PIL import Image
        coverstore.save(BODY, "map 1", DATA)
        coverstore.save_png(BODY, "map 6", Image.new("RGB", (8, 8)), root=str(tmp_path))
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 7"

    def test_another_bodys_maps_do_not_count(self, tmp_path):
        coverstore.save("Other 3", "map 8", DATA)
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 1"


@pytest.mark.unit
class TestLatestPicture:

    def test_the_newest_picture_on_the_body(self, tmp_path):
        import os
        from PIL import Image
        older = coverstore.save_png(BODY, "map 1", Image.new("RGB", (8, 8)), root=str(tmp_path))
        newer = coverstore.save_png(BODY, "map 2", Image.new("RGB", (8, 8)), root=str(tmp_path))
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))
        assert coverstore.latest_png(BODY, root=str(tmp_path)) == newer

    def test_none_for_a_body_never_driven(self, tmp_path):
        assert coverstore.latest_png("Nowhere 1", root=str(tmp_path)) is None


@pytest.mark.unit
class TestUsage:

    def test_counts_maps_and_their_bytes(self, db, tmp_path):
        from PIL import Image
        pictures = tmp_path / "coverage"
        coverstore.save(BODY, "map 1", DATA)
        coverstore.save("Other 3", "map 1", DATA)
        coverstore.save_png(BODY, "map 1", Image.new("RGB", (8, 8)), root=str(pictures))
        with sqlite3.connect(db) as conn:
            [(points,)] = conn.execute("SELECT SUM(LENGTH(data)) FROM maps").fetchall()
        count, size = coverstore.usage(root=str(pictures))
        assert count == 2
        assert size == points + sum(p.stat().st_size for p in pictures.rglob("*.png"))

    def test_nothing_saved_is_nothing(self, tmp_path):
        assert coverstore.usage(root=str(tmp_path / "missing")) == (0, 0)


@pytest.mark.unit
class TestSystemAddress:
    """A body name is only unique inside its system; the address keeps a
    same-named body in another system from sharing its maps."""

    def test_a_same_named_body_elsewhere_does_not_get_the_map(self):
        coverstore.save(BODY, "map 1", dict(DATA, system_address=111))
        assert coverstore.maps(BODY, system_address=222) == []
        [(name, data)] = coverstore.maps(BODY, system_address=111)
        assert name == "map 1" and data["system_address"] == 111

    def test_a_map_from_before_the_address_is_kept(self):
        coverstore.save(BODY, "map 1", DATA)
        assert len(coverstore.maps(BODY, system_address=222)) == 1

    def test_no_address_asked_is_every_map(self):
        coverstore.save(BODY, "map 1", dict(DATA, system_address=111))
        assert len(coverstore.maps(BODY)) == 1
