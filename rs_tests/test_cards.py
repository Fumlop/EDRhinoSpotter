"""Reading back which bodies have been marked, from the sidecars."""

import json
import os

import pytest

from rs_core import cards, spotcard


def write_card(folder, body, material, index, marked_at, with_sidecar=True):
    """A card the way spotcard writes one: a PNG and its JSON."""
    stem = f"{body.replace(' ', '_')}_loc{index}_{material.lower()}"
    png = os.path.join(str(folder), stem + ".png")
    with open(png, "wb") as handle:
        handle.write(b"not really a png")
    if with_sidecar:
        with open(os.path.join(str(folder), stem + ".json"), "w", encoding="utf-8") as handle:
            json.dump({"system": "Andel", "planet_name": body, "commodity": material,
                       "location_index": index, "marked_at": marked_at,
                       "card": stem + ".png"}, handle)
    return png


class TestForSystem:
    def test_reads_the_sidecars(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        write_card(tmp_path, "Andel 4 c", "Monazite", 7, "3311-05-15T09:00:00")
        found = cards.for_system("Andel", root=str(tmp_path))
        assert {record["planet_name"] for record in found} == {"Andel 1 a", "Andel 4 c"}

    def test_a_png_without_a_sidecar_is_skipped(self, tmp_path):
        """Written by a version that kept none. A link to the wrong body is
        worse than no link, and the body name in a filename is a guess - the
        spaces are gone and the material is lowercased."""
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x", with_sidecar=False)
        assert cards.for_system("Andel", root=str(tmp_path)) == []

    def test_a_sidecar_without_its_png_is_skipped(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        os.remove(os.path.join(str(tmp_path), "Andel_1_a_loc22_jadeite.png"))
        assert cards.for_system("Andel", root=str(tmp_path)) == []

    def test_broken_json_is_skipped_not_raised(self, tmp_path):
        (tmp_path / "Andel_1_a_loc1_jadeite.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "Andel_1_a_loc1_jadeite.png").write_bytes(b"x")
        assert cards.for_system("Andel", root=str(tmp_path)) == []

    def test_a_sidecar_with_no_body_is_skipped(self, tmp_path):
        (tmp_path / "odd.json").write_text(json.dumps({"system": "Andel"}), encoding="utf-8")
        (tmp_path / "odd.png").write_bytes(b"x")
        assert cards.for_system("Andel", root=str(tmp_path)) == []

    def test_a_system_with_no_folder(self, tmp_path):
        assert cards.for_system("Nowhere", root=str(tmp_path / "nope")) == []

    def test_the_path_points_at_the_png(self, tmp_path):
        png = write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        assert cards.for_system("Andel", root=str(tmp_path))[0]["path"] == png


class TestByBody:
    def test_groups_on_the_journal_name(self, tmp_path):
        """Keyed by the body exactly as the journal names it, which is what the
        window has in hand - no normalising on either side."""
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "a")
        write_card(tmp_path, "Andel 1 a", "Monazite", 23, "b")
        write_card(tmp_path, "Andel 4 c", "Olivine", 1, "c")
        grouped = cards.by_body("Andel", root=str(tmp_path))
        assert len(grouped["Andel 1 a"]) == 2
        assert len(grouped["Andel 4 c"]) == 1

    def test_an_unmarked_body_is_simply_absent(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "a")
        assert "Andel 9 z" not in cards.by_body("Andel", root=str(tmp_path))


class TestNewest:
    def test_picks_the_latest_mark(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        write_card(tmp_path, "Andel 1 a", "Monazite", 23, "3311-05-16T08:00:00")
        found = cards.by_body("Andel", root=str(tmp_path))["Andel 1 a"]
        assert cards.newest(found)["commodity"] == "Monazite"

    def test_nothing_to_pick(self):
        assert cards.newest([]) is None


class TestDelete:
    """Removing a bookmark: the PNG and the sidecar, or neither."""

    def test_both_files_go(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        assert cards.delete(record) is True
        assert os.listdir(tmp_path) == []

    def test_the_sidecar_is_not_guessed_from_the_png(self, tmp_path):
        """The name has had its spaces replaced and its material lowercased,
        so the path the reader found is the only one that is certain."""
        write_card(tmp_path, "Andel 1 a", "Low Temp. Diamonds", 7, "x")
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        assert os.path.isfile(record["sidecar"])
        cards.delete(record)
        assert os.listdir(tmp_path) == []

    def test_a_file_already_gone_is_not_a_failure(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        os.remove(record["path"])
        assert cards.delete(record) is True
        assert os.listdir(tmp_path) == []

    def test_nothing_to_delete(self):
        assert cards.delete({}) is False

    def test_a_file_that_will_not_go_says_so(self, tmp_path, monkeypatch):
        """Open in a viewer, or a read-only folder. The list must not claim it
        deleted something it did not."""
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel", root=str(tmp_path))[0]

        def refuse(path):
            raise PermissionError(13, "in use")

        monkeypatch.setattr(cards.os, "remove", refuse)
        assert cards.delete(record) is False


class TestOrdered:
    """The order the bookmark list is read in: the best patch on this body
    first, not the one worked first."""

    def test_most_rigs_first(self):
        found = cards.ordered([{"rigs": 2, "location_index": 1},
                               {"rigs": 6, "location_index": 9},
                               {"rigs": 4, "location_index": 5}])
        assert [record["rigs"] for record in found] == [6, 4, 2]

    def test_equal_rigs_fall_back_to_location(self):
        found = cards.ordered([{"rigs": 4, "location_index": 9},
                               {"rigs": 4, "location_index": 2}])
        assert [record["location_index"] for record in found] == [2, 9]

    def test_an_uncounted_bookmark_sorts_last(self):
        """Not counted is not the same as counted at none."""
        found = cards.ordered([{"rigs": None, "location_index": 1},
                               {"rigs": 1, "location_index": 8}])
        assert [record["rigs"] for record in found] == [1, None]


class TestSidecarFromRender:
    def test_render_writes_one(self, tmp_path):
        """The end this is all read from: a real card, written by the real
        renderer."""
        path = spotcard.render({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 22,
            "commodity": "Jadeite", "rigs": 4, "heading": 214,
            "latitude": 1.5, "longitude": -2.5,
            "marked_at": "3311-05-14T18:40:00", "commander": "Example",
        }, str(tmp_path / "Andel_1_a_loc22_jadeite.png"))
        found = cards.for_system("Andel", root=str(tmp_path))
        assert len(found) == 1
        assert found[0]["planet_name"] == "Andel 1 a"
        assert found[0]["commodity"] == "Jadeite"
        assert found[0]["path"] == path

    def test_a_datetime_survives_as_text(self, tmp_path):
        """marked_at is a datetime when the plugin writes it and has to come
        back as something json can hold."""
        from datetime import datetime, timezone
        spotcard.render({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 1,
            "commodity": "Jadeite", "latitude": 1.0, "longitude": 2.0,
            "marked_at": datetime(3311, 5, 14, tzinfo=timezone.utc),
        }, str(tmp_path / "card.png"))
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        assert "3311" in record["marked_at"]
