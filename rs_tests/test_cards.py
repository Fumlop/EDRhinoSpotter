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

    def test_a_bookmark_without_a_png_is_kept(self, tmp_path):
        """The JSON is the bookmark; the card image is gone from the plugin."""
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        os.remove(os.path.join(str(tmp_path), "Andel_1_a_loc22_jadeite.png"))
        [record] = cards.for_system("Andel", root=str(tmp_path))
        assert record["planet_name"] == "Andel 1 a" and record["path"] is None

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

    def test_an_old_cards_path_points_at_its_png(self, tmp_path):
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
    """Removing a bookmark: its JSON, and an old card's PNG with it."""

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


class TestDepleted:
    """A bookmark marked mined out, and the mark taken off again."""

    def test_marking_writes_when(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        assert cards.set_depleted(record, True, when="3311-05-20T10:00:00+00:00") is True
        again = cards.for_system("Andel", root=str(tmp_path))[0]
        assert again["depleted_at"] == "3311-05-20T10:00:00+00:00"
        assert record["depleted_at"] == again["depleted_at"]
        # Everything else in the bookmark is left as it was.
        assert again["commodity"] == "Jadeite" and again["location_index"] == 22

    def test_unmarking_removes_the_key(self, tmp_path):
        write_card(tmp_path, "Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        cards.set_depleted(record, True)
        cards.set_depleted(record, False)
        with open(record["sidecar"], encoding="utf-8") as handle:
            assert "depleted_at" not in json.load(handle)
        assert "depleted_at" not in record

    def test_a_bookmark_that_cannot_be_written_says_so(self, tmp_path):
        record = {"sidecar": str(tmp_path / "gone.json")}
        assert cards.set_depleted(record, True) is False
        assert cards.set_depleted({}, True) is False


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


class TestSave:
    def test_save_writes_one(self, tmp_path):
        """The end this is all read from: a real bookmark, written by the real
        writer, and no picture beside it."""
        path = spotcard.save({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 22,
            "commodity": "Jadeite", "rigs": 4, "heading": 214,
            "latitude": 1.5, "longitude": -2.5,
            "marked_at": "3311-05-14T18:40:00", "commander": "Example",
        }, str(tmp_path / "Andel_1_a_loc22_jadeite.json"))
        found = cards.for_system("Andel", root=str(tmp_path))
        assert len(found) == 1
        assert found[0]["planet_name"] == "Andel 1 a"
        assert found[0]["commodity"] == "Jadeite"
        assert found[0]["sidecar"] == path and found[0]["path"] is None
        assert os.listdir(tmp_path) == ["Andel_1_a_loc22_jadeite.json"]

    def test_a_second_mark_of_the_same_spot_is_a_second_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(spotcard, "CARDS_ROOT", str(tmp_path))
        spot = {"system": "Andel", "planet_name": "Andel 1 a", "location_index": 22,
                "commodity": "Jadeite", "latitude": 1.0, "longitude": 2.0}
        first, second = spotcard.save(dict(spot)), spotcard.save(dict(spot))
        assert first != second and second.endswith("_2.json")

    def test_a_datetime_survives_as_text(self, tmp_path):
        """marked_at is a datetime when the plugin writes it and has to come
        back as something json can hold."""
        from datetime import datetime, timezone
        spotcard.save({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 1,
            "commodity": "Jadeite", "latitude": 1.0, "longitude": 2.0,
            "marked_at": datetime(3311, 5, 14, tzinfo=timezone.utc),
        }, str(tmp_path / "spot.json"))
        record = cards.for_system("Andel", root=str(tmp_path))[0]
        assert "3311" in record["marked_at"]


class TestNearby:
    """A new mark within SAME_SPOT_M of the same material on the same body updates it."""

    RADIUS = 1352744.5

    def write(self, folder, name, **fields):
        import json
        record = {"system": "Andel", "planet_name": "Andel 1 a", "commodity": "Monazite",
                  "latitude": 10.0, "longitude": 20.0, "marked_at": "2026-09-13 18:40:00"}
        record.update(fields)
        (folder / name).write_text(json.dumps(record), encoding="utf-8")

    def spot(self, **fields):
        spot = {"system": "Andel", "planet_name": "Andel 1 a", "commodity": "Monazite",
                "latitude": 10.0, "longitude": 20.0, "planet_radius": self.RADIUS}
        spot.update(fields)
        return spot

    def metres_north(self, metres):
        import math
        return 10.0 + math.degrees(metres / self.RADIUS)

    def test_the_radius_covers_an_eight_rig_patch_plus_ten_percent(self):
        import math
        assert cards.SAME_SPOT_M == 100.0
        assert 76.0 / (2 * math.sin(math.pi / 7)) * 1.1 <= cards.SAME_SPOT_M

    def test_same_material_inside_the_radius_is_found(self, tmp_path):
        self.write(tmp_path, "a.json")
        old = cards.nearby(self.spot(latitude=self.metres_north(90)), root=str(tmp_path))
        assert old is not None and round(old["distance_m"]) == 90

    def test_outside_the_radius_is_a_new_bookmark(self, tmp_path):
        self.write(tmp_path, "a.json")
        assert cards.nearby(self.spot(latitude=self.metres_north(105)), root=str(tmp_path)) is None

    def test_another_material_close_by_is_not_touched(self, tmp_path):
        self.write(tmp_path, "a.json", commodity="Jadeite")
        assert cards.nearby(self.spot(), root=str(tmp_path)) is None

    def test_another_body_is_not_touched(self, tmp_path):
        self.write(tmp_path, "a.json", planet_name="Andel 1 b")
        assert cards.nearby(self.spot(), root=str(tmp_path)) is None

    def test_the_nearest_of_two_wins(self, tmp_path):
        self.write(tmp_path, "far.json", latitude=self.metres_north(80))
        self.write(tmp_path, "near.json", latitude=self.metres_north(40))
        old = cards.nearby(self.spot(), root=str(tmp_path))
        assert old["sidecar"].endswith("near.json")

    def test_no_radius_no_update(self, tmp_path):
        self.write(tmp_path, "a.json")
        assert cards.nearby(self.spot(planet_radius=None), root=str(tmp_path)) is None


class TestUpdated:
    OLD = {"marked_at": "2026-09-13 18:40:00", "latitude": 10.0, "longitude": 20.0,
           "heading": 77, "rigs": 4, "location_index": 13, "amount": "High",
           "density": "Low", "sidecar": "x.json", "distance_m": 12.0}

    def test_only_amount_and_density_change(self):
        new = cards.updated(self.OLD, {"marked_at": "2026-09-13 20:30:00", "latitude": 10.001,
                                       "longitude": 20.001, "heading": 200, "rigs": 6,
                                       "location_index": 14, "amount": "Low", "density": "Medium"})
        assert new["amount"] == "Low" and new["density"] == "Medium"
        for key in ("marked_at", "latitude", "longitude", "heading", "rigs", "location_index"):
            assert new[key] == self.OLD[key]
        assert "updated_at" in new
        assert "sidecar" not in new and "distance_m" not in new

    def test_an_unpicked_reading_keeps_the_old_one(self):
        new = cards.updated(self.OLD, {"amount": None, "density": None})
        assert new["amount"] == "High" and new["density"] == "Low"

    def test_a_live_amount_clears_depleted(self):
        old = {"marked_at": "a", "depleted_at": "2026-09-13T20:37:35+00:00"}
        assert "depleted_at" not in cards.updated(old, {"amount": "Medium"})

    def test_no_amount_keeps_depleted(self):
        old = {"marked_at": "a", "depleted_at": "2026-09-13T20:37:35+00:00"}
        assert cards.updated(old, {"amount": None})["depleted_at"] == old["depleted_at"]


class TestLocationAt:
    """A drop within 2 km of a bookmark takes that bookmark's location."""

    RADIUS = 381784.9

    def write(self, folder, name, **fields):
        import json
        record = {"system": "Andel", "planet_name": "Andel 8 b", "commodity": "Monazite",
                  "latitude": 10.0, "longitude": 20.0, "location_index": 13}
        record.update(fields)
        (folder / name).write_text(json.dumps(record), encoding="utf-8")

    def north(self, metres):
        import math
        return 10.0 + math.degrees(metres / self.RADIUS)

    def test_a_drop_near_a_bookmark_takes_its_location(self, tmp_path):
        self.write(tmp_path, "a.json")
        index, metres = cards.location_at("Andel", "Andel 8 b", self.north(900), 20.0,
                                          self.RADIUS, root=str(tmp_path))
        assert index == 13 and round(metres) == 900

    def test_the_nearest_bookmark_wins(self, tmp_path):
        self.write(tmp_path, "far.json", latitude=self.north(1500), location_index=2)
        self.write(tmp_path, "near.json", latitude=self.north(300), location_index=7)
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, self.RADIUS,
                                 root=str(tmp_path))[0] == 7

    def test_beyond_two_km_there_is_no_answer(self, tmp_path):
        self.write(tmp_path, "a.json")
        assert cards.location_at("Andel", "Andel 8 b", self.north(2100), 20.0,
                                 self.RADIUS, root=str(tmp_path)) is None

    def test_a_bookmark_without_a_location_or_on_another_body_is_ignored(self, tmp_path):
        self.write(tmp_path, "a.json", location_index=None)
        self.write(tmp_path, "b.json", planet_name="Andel 8 c")
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, self.RADIUS,
                                 root=str(tmp_path)) is None

    def test_no_radius_no_answer(self, tmp_path):
        self.write(tmp_path, "a.json")
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, None, root=str(tmp_path)) is None
