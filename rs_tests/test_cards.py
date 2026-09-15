"""Reading back which bodies have been marked, from the database."""

import os
import sqlite3

import pytest

from rs_core import cards, database, spotcard


@pytest.fixture(autouse=True)
def cards_root(tmp_path, monkeypatch):
    """Where an old card's PNG is looked for - never the commander's folder."""
    root = tmp_path / "cards"
    monkeypatch.setattr(spotcard, "CARDS_ROOT", str(root))
    return root


def put(**fields):
    """A bookmark the way the plugin writes one. Its id."""
    record = {"system": "Andel", "planet_name": "Andel 1 a", "commodity": "Monazite",
              "latitude": 10.0, "longitude": 20.0, "marked_at": "2026-09-13 18:40:00"}
    record.update(fields)
    return spotcard.save(record)


def write_card(body, material, index, marked_at, with_png=True):
    """A bookmark from the days of PNG cards: the record names its picture."""
    stem = f"{body.replace(' ', '_')}_loc{index}_{material.lower()}"
    put(planet_name=body, commodity=material, location_index=index, marked_at=marked_at,
        card=stem + ".png")
    png = os.path.join(spotcard.card_dir("Andel"), stem + ".png")
    if with_png:
        os.makedirs(os.path.dirname(png), exist_ok=True)
        with open(png, "wb") as handle:
            handle.write(b"not really a png")
    return png


class TestForSystem:
    def test_reads_the_bookmarks(self):
        write_card("Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        write_card("Andel 4 c", "Monazite", 7, "3311-05-15T09:00:00")
        found = cards.for_system("Andel")
        assert {record["planet_name"] for record in found} == {"Andel 1 a", "Andel 4 c"}
        assert all(isinstance(record["id"], int) for record in found)

    def test_a_bookmark_without_a_png_is_kept(self):
        """The bookmark is the row; the card image is gone from the plugin."""
        write_card("Andel 1 a", "Jadeite", 22, "x", with_png=False)
        [record] = cards.for_system("Andel")
        assert record["planet_name"] == "Andel 1 a" and record["path"] is None

    def test_an_old_cards_path_points_at_its_png(self):
        png = write_card("Andel 1 a", "Jadeite", 22, "x")
        assert cards.for_system("Andel")[0]["path"] == png

    def test_another_systems_bookmarks_are_not_in_it(self):
        put()
        put(system="Loha", planet_name="Loha 2")
        assert [record["planet_name"] for record in cards.for_system("Andel")] == ["Andel 1 a"]

    def test_a_system_with_no_bookmarks(self):
        assert cards.for_system("Nowhere") == []

    def test_a_broken_row_says_which_in_the_log_once(self, db, caplog):
        """A bookmark cannot be rebuilt from the journal, so one that stops
        reading has to show up somewhere rather than just vanish from the list."""
        id = put()
        put(commodity="Jadeite")
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE bookmarks SET data = '{not json' WHERE id = ?", (id,))
        with caplog.at_level("WARNING", logger="RhinoSpotter"):
            assert [r["commodity"] for r in cards.for_system("Andel")] == ["Jadeite"]
            cards.for_system("Andel")                     # the minimap, after a change
        assert [r.levelname for r in caplog.records] == ["WARNING"]
        assert f"bookmark {id} " in caplog.records[0].getMessage()

    def test_a_row_with_no_body_is_skipped(self, db):
        id = put()
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE bookmarks SET data = '{\"system\": \"Andel\"}' WHERE id = ?",
                         (id,))
        assert cards.for_system("Andel") == []

    def test_a_database_that_cannot_be_opened_is_no_bookmarks(self, tmp_path, caplog):
        folder = tmp_path / "a folder, not a file"
        folder.mkdir()
        with caplog.at_level("WARNING", logger="RhinoSpotter"):
            assert cards.for_system("Andel", db=str(folder)) == []
        assert caplog.records


class TestByBody:
    def test_groups_on_the_journal_name(self):
        """Keyed by the body exactly as the journal names it, which is what the
        window has in hand - no normalising on either side."""
        write_card("Andel 1 a", "Jadeite", 22, "a")
        write_card("Andel 1 a", "Monazite", 23, "b")
        write_card("Andel 4 c", "Olivine", 1, "c")
        grouped = cards.by_body("Andel")
        assert len(grouped["Andel 1 a"]) == 2
        assert len(grouped["Andel 4 c"]) == 1

    def test_an_unmarked_body_is_simply_absent(self):
        write_card("Andel 1 a", "Jadeite", 22, "a")
        assert "Andel 9 z" not in cards.by_body("Andel")


class TestNewest:
    def test_picks_the_latest_mark(self):
        write_card("Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        write_card("Andel 1 a", "Monazite", 23, "3311-05-16T08:00:00")
        found = cards.by_body("Andel")["Andel 1 a"]
        assert cards.newest(found)["commodity"] == "Monazite"

    def test_nothing_to_pick(self):
        assert cards.newest([]) is None


class TestDelete:
    """Removing a bookmark: its row, and an old card's PNG with it."""

    def test_the_row_and_the_png_go(self):
        png = write_card("Andel 1 a", "Jadeite", 22, "3311-05-14T18:40:00")
        record = cards.for_system("Andel")[0]
        assert cards.delete(record) is True
        assert cards.for_system("Andel") == []
        assert not os.path.exists(png)

    def test_a_png_already_gone_is_not_a_failure(self):
        write_card("Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel")[0]
        os.remove(record["path"])
        assert cards.delete(record) is True
        assert cards.for_system("Andel") == []

    def test_deleting_twice(self):
        put()
        record = cards.for_system("Andel")[0]
        assert cards.delete(record) is True
        assert cards.delete(record) is False

    def test_nothing_to_delete(self):
        assert cards.delete({}) is False

    def test_a_png_that_will_not_go_says_so_and_keeps_the_bookmark(self, monkeypatch):
        """Open in a viewer, or a read-only folder. The list must not claim it
        deleted something it did not."""
        write_card("Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel")[0]

        def refuse(path):
            raise PermissionError(13, "in use")

        monkeypatch.setattr(cards.os, "remove", refuse)
        assert cards.delete(record) is False
        assert len(cards.for_system("Andel")) == 1

    def test_a_delete_moves_the_revision(self):
        put()
        before = database.revision()
        cards.delete(cards.for_system("Andel")[0])
        assert database.revision() != before


class TestDepleted:
    """A bookmark marked mined out, and the mark taken off again."""

    def test_marking_writes_when(self):
        write_card("Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel")[0]
        assert cards.set_depleted(record, True, when="3311-05-20T10:00:00+00:00") is True
        again = cards.for_system("Andel")[0]
        assert again["depleted_at"] == "3311-05-20T10:00:00+00:00"
        assert record["depleted_at"] == again["depleted_at"]
        # Everything else in the bookmark is left as it was.
        assert again["commodity"] == "Jadeite" and again["location_index"] == 22

    def test_unmarking_removes_the_key(self):
        write_card("Andel 1 a", "Jadeite", 22, "x")
        record = cards.for_system("Andel")[0]
        cards.set_depleted(record, True)
        cards.set_depleted(record, False)
        assert "depleted_at" not in cards.for_system("Andel")[0]
        assert "depleted_at" not in record

    def test_a_bookmark_that_is_gone_says_so(self):
        put()
        record = cards.for_system("Andel")[0]
        cards.delete(record)
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
    def test_save_writes_one(self, cards_root):
        """The end this is all read from: a real bookmark, written by the real
        writer, and no file beside it."""
        id = spotcard.save({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 22,
            "commodity": "Jadeite", "rigs": 4, "heading": 214,
            "latitude": 1.5, "longitude": -2.5,
            "marked_at": "3311-05-14T18:40:00", "commander": "Example",
        })
        [found] = cards.for_system("Andel")
        assert found["id"] == id
        assert found["planet_name"] == "Andel 1 a" and found["commodity"] == "Jadeite"
        assert found["rigs"] == 4 and found["latitude"] == 1.5 and found["path"] is None
        assert not cards_root.exists()

    def test_a_second_mark_of_the_same_spot_is_a_second_bookmark(self):
        spot = {"system": "Andel", "planet_name": "Andel 1 a", "location_index": 22,
                "commodity": "Jadeite", "latitude": 1.0, "longitude": 2.0}
        first, second = spotcard.save(dict(spot)), spotcard.save(dict(spot))
        assert first != second and len(cards.for_system("Andel")) == 2

    def test_a_datetime_survives_as_text(self):
        """marked_at is a datetime when the plugin writes it and has to come
        back as something json can hold."""
        from datetime import datetime, timezone
        spotcard.save({
            "system": "Andel", "planet_name": "Andel 1 a", "location_index": 1,
            "commodity": "Jadeite", "latitude": 1.0, "longitude": 2.0,
            "marked_at": datetime(3311, 5, 14, tzinfo=timezone.utc),
        })
        assert "3311" in cards.for_system("Andel")[0]["marked_at"]

    def test_with_an_id_it_replaces_that_bookmark(self):
        id = put(amount="High")
        old = cards.for_system("Andel")[0]
        assert spotcard.save(cards.updated(old, {"amount": "Low"}), id=id) == id
        [again] = cards.for_system("Andel")
        assert again["amount"] == "Low" and again["id"] == id

    def test_an_update_of_a_deleted_bookmark_writes_it_again(self):
        """Deleted in the scan window while the worker was updating it - the
        file it used to be came back the same way."""
        id = put()
        old = cards.for_system("Andel")[0]
        cards.delete(old)
        assert spotcard.save(cards.updated(old, {"amount": "Low"}), id=id) is not None
        assert len(cards.for_system("Andel")) == 1

    def test_a_write_that_fails_raises_and_keeps_the_old_bookmark(self, monkeypatch):
        """The panel says why, and the bookmark is left as it was."""
        id = put(amount="High")
        old = cards.for_system("Andel")[0]

        def half_written(conn, record, id=None, source=None):
            conn.execute("UPDATE bookmarks SET data = '{}' WHERE id = ?", (id,))
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(database, "write_bookmark", half_written)
        with pytest.raises(sqlite3.OperationalError):
            spotcard.save(cards.updated(old, {"amount": "Low"}), id=id)
        assert cards.for_system("Andel")[0]["amount"] == "High"


class TestNearby:
    """A new mark within SAME_SPOT_M of the same material on the same body updates it."""

    RADIUS = 1352744.5

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

    def test_same_material_inside_the_radius_is_found(self):
        put()
        old = cards.nearby(self.spot(latitude=self.metres_north(90)))
        assert old is not None and round(old["distance_m"]) == 90

    def test_outside_the_radius_is_a_new_bookmark(self):
        put()
        assert cards.nearby(self.spot(latitude=self.metres_north(105))) is None

    def test_another_material_close_by_is_not_touched(self):
        put(commodity="Jadeite")
        assert cards.nearby(self.spot()) is None

    def test_another_body_is_not_touched(self):
        put(planet_name="Andel 1 b")
        assert cards.nearby(self.spot()) is None

    def test_the_nearest_of_two_wins(self):
        put(latitude=self.metres_north(80))
        near = put(latitude=self.metres_north(40))
        assert cards.nearby(self.spot())["id"] == near

    def test_no_radius_no_update(self):
        put()
        assert cards.nearby(self.spot(planet_radius=None)) is None


class TestUpdated:
    OLD = {"marked_at": "2026-09-13 18:40:00", "latitude": 10.0, "longitude": 20.0,
           "heading": 77, "rigs": 4, "location_index": 13, "amount": "High",
           "density": "Low", "id": 5, "path": None, "distance_m": 12.0}

    def test_only_amount_and_density_change(self):
        new = cards.updated(self.OLD, {"marked_at": "2026-09-13 20:30:00", "latitude": 10.001,
                                       "longitude": 20.001, "heading": 200, "rigs": 6,
                                       "location_index": 14, "amount": "Low", "density": "Medium"})
        assert new["amount"] == "Low" and new["density"] == "Medium"
        for key in ("marked_at", "latitude", "longitude", "heading", "rigs", "location_index"):
            assert new[key] == self.OLD[key]
        assert "updated_at" in new
        assert "id" not in new and "path" not in new and "distance_m" not in new

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
    """A drop within 10 km of a bookmark takes that bookmark's location."""

    RADIUS = 381784.9

    def put(self, **fields):
        put(**dict({"planet_name": "Andel 8 b", "location_index": 13}, **fields))

    def north(self, metres):
        import math
        return 10.0 + math.degrees(metres / self.RADIUS)

    def test_a_drop_near_a_bookmark_takes_its_location(self):
        self.put()
        index, metres = cards.location_at("Andel", "Andel 8 b", self.north(900), 20.0,
                                          self.RADIUS)
        assert index == 13 and round(metres) == 900

    def test_the_nearest_bookmark_wins(self):
        self.put(latitude=self.north(6500), location_index=2)
        self.put(latitude=self.north(3200), location_index=7)
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, self.RADIUS)[0] == 7

    def test_beyond_ten_km_there_is_no_answer(self):
        self.put()
        assert cards.location_at("Andel", "Andel 8 b", self.north(10100), 20.0,
                                 self.RADIUS) is None

    def test_a_bookmark_without_a_location_or_on_another_body_is_ignored(self):
        self.put(location_index=None)
        self.put(planet_name="Andel 8 c")
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, self.RADIUS) is None

    def test_no_radius_no_answer(self):
        self.put()
        assert cards.location_at("Andel", "Andel 8 b", 10.0, 20.0, None) is None


class TestSameBody:
    """IDs decide when both sides have them; names only inside one system."""

    def test_same_name_in_another_system_is_another_body(self):
        record = {"planet_name": "Hyperion", "system_address": 111, "body_id": 3}
        assert not cards.same_body(record, "Hyperion", system_address=222, body_id=3)

    def test_same_ids_under_a_different_name_is_the_same_body(self):
        record = {"planet_name": "Andel 1 a", "system_address": 111, "body_id": 3}
        assert cards.same_body(record, "Hyperion", system_address=111, body_id=3)

    def test_a_bookmark_without_ids_matches_by_name(self):
        record = {"planet_name": "Andel 1 a"}
        assert cards.same_body(record, "Andel 1 a", system_address=111, body_id=3)
        assert not cards.same_body(record, "Andel 1 b", system_address=111, body_id=3)

    def test_nearby_skips_a_same_named_body_elsewhere(self):
        record = {"system": "Andel", "planet_name": "Hyperion", "commodity": "Monazite",
                  "latitude": 10.0, "longitude": 20.0, "system_address": 111, "body_id": 3}
        spotcard.save(record)
        spot = dict(record, system_address=222, planet_radius=1352744.5)
        assert cards.nearby(spot) is None
        assert cards.nearby(dict(spot, system_address=111)) is not None

    def test_location_at_skips_a_same_named_body_elsewhere(self):
        spotcard.save({"system": "Andel", "planet_name": "Hyperion", "latitude": 10.0,
                       "longitude": 20.0, "location_index": 4, "system_address": 111,
                       "body_id": 3})
        args = ("Andel", "Hyperion", 10.0, 20.0, 1352744.5)
        assert cards.location_at(*args, system_address=222) is None
        assert cards.location_at(*args, system_address=111)[0] == 4

    def test_an_update_gives_an_old_bookmark_the_ids(self):
        new = cards.updated({"planet_name": "Andel 1 a"},
                            {"system_address": 111, "body_id": 3, "amount": "Low"})
        assert new["system_address"] == 111 and new["body_id"] == 3

    def test_an_update_keeps_the_ids_already_there(self):
        new = cards.updated({"system_address": 111, "body_id": 3},
                            {"system_address": None, "body_id": None})
        assert new["system_address"] == 111 and new["body_id"] == 3
