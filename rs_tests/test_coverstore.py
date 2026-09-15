"""The minimap's saved maps: points to disk, gzipped, and back."""

import gzip
import json

import pytest

from rs_core import coverstore

BODY = "Col 285 Sector LS-P b7-1 A 2"
DATA = {"origin": [53.259235, -178.692352], "radius": 1352744.5, "location": 9,
        "drops": [[53.259235, -178.692352]], "stamps": [[53.259235, -178.692352]]}


@pytest.mark.unit
class TestRoundTrip:

    def test_saves_gzipped_and_loads(self, tmp_path):
        path = coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        assert path.endswith("map 1.json.gz")
        with open(path, "rb") as handle:
            assert handle.read(2) == b"\x1f\x8b"
        [(name, data)] = coverstore.maps(BODY, root=str(tmp_path))
        assert name == "map 1"
        assert data["stamps"] == DATA["stamps"] and data["body"] == BODY

    def test_plain_json_is_read_too(self, tmp_path):
        folder = tmp_path / BODY
        folder.mkdir()
        (folder / "map 1.json").write_text(json.dumps(dict(DATA, version=1)), encoding="utf-8")
        assert [name for name, _ in coverstore.maps(BODY, root=str(tmp_path))] == ["map 1"]

    def test_gzipped_wins_over_plain_of_the_same_name(self, tmp_path):
        coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        (tmp_path / BODY / "map 1.json").write_text(
            json.dumps(dict(DATA, version=1, location=1)), encoding="utf-8")
        [(_, data)] = coverstore.maps(BODY, root=str(tmp_path))
        assert data["location"] == 9

    def test_a_broken_map_is_skipped_not_fatal(self, tmp_path):
        coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        (tmp_path / BODY / "map 2.json.gz").write_bytes(gzip.compress(b"{not json"))
        (tmp_path / BODY / "map 3.json").write_text('{"version": 99}', encoding="utf-8")
        # Corrupt inside the deflate stream: zlib.error, not OSError.
        good = gzip.compress(json.dumps(dict(DATA, version=1)).encode() * 20)
        (tmp_path / BODY / "map 4.json.gz").write_bytes(good[:10] + bytes([good[10] ^ 0xFF]) + good[11:])
        assert [name for name, _ in coverstore.maps(BODY, root=str(tmp_path))] == ["map 1"]

    def test_an_unknown_body_has_no_maps(self, tmp_path):
        assert coverstore.maps("Nowhere 1", root=str(tmp_path)) == []


@pytest.mark.unit
class TestNames:

    def test_first_map_is_map_1(self, tmp_path):
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 1"

    def test_next_is_one_past_the_highest(self, tmp_path):
        coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        coverstore.save(BODY, "map 4", DATA, root=str(tmp_path))
        assert coverstore.next_name(BODY, root=str(tmp_path)) == "map 5"


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

    def test_counts_maps_not_files(self, tmp_path):
        from PIL import Image
        coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        coverstore.save("Other 3", "map 1", DATA, root=str(tmp_path))
        coverstore.save_png(BODY, "map 1", Image.new("RGB", (8, 8)), root=str(tmp_path))
        count, size = coverstore.usage(root=str(tmp_path))
        assert count == 2
        assert size == sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())

    def test_no_folder_is_nothing(self, tmp_path):
        assert coverstore.usage(root=str(tmp_path / "missing")) == (0, 0)


@pytest.mark.unit
class TestSystemAddress:
    """The folder is by body name; the address keeps a same-named body in
    another system from sharing its maps."""

    def test_a_same_named_body_elsewhere_does_not_get_the_map(self, tmp_path):
        coverstore.save(BODY, "map 1", dict(DATA, system_address=111), root=str(tmp_path))
        assert coverstore.maps(BODY, root=str(tmp_path), system_address=222) == []
        [(name, data)] = coverstore.maps(BODY, root=str(tmp_path), system_address=111)
        assert name == "map 1" and data["system_address"] == 111

    def test_a_map_from_before_the_address_is_kept(self, tmp_path):
        coverstore.save(BODY, "map 1", DATA, root=str(tmp_path))
        assert len(coverstore.maps(BODY, root=str(tmp_path), system_address=222)) == 1

    def test_no_address_asked_is_every_map(self, tmp_path):
        coverstore.save(BODY, "map 1", dict(DATA, system_address=111), root=str(tmp_path))
        assert len(coverstore.maps(BODY, root=str(tmp_path))) == 1
