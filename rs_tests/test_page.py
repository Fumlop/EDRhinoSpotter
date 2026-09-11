"""The bookmarks page for one body."""

import os

import pytest

from rs_core import page


def record(location=1, material="Jadeite", rigs=4, heading=214,
           lat=12.345678, lon=-98.765432, when="3311-05-14T18:40:00",
           card="Andel_1_a_loc1_jadeite.png"):
    return {"system": "Andel", "planet_name": "Andel 1 a",
            "location_index": location, "commodity": material, "rigs": rigs,
            "heading": heading, "latitude": lat, "longitude": lon,
            "marked_at": when, "card": card, "path": os.path.join("/x", card)}


class TestRender:
    def test_every_bookmark_gets_a_row(self):
        found = page.render("Andel", "Andel 1 a",
                            [record(1, "Jadeite"), record(2, "Monazite")])
        assert found.count("<tr>") == 3          # a header row and two bookmarks
        assert "Jadeite" in found and "Monazite" in found

    def test_the_card_is_shown_and_linked(self):
        """The image is the bookmark. A table of numbers beside a folder of
        pictures is two things to look at."""
        found = page.render("Andel", "Andel 1 a", [record(card="shot.png")])
        assert 'src="shot.png"' in found
        assert 'href="shot.png"' in found

    def test_the_image_path_is_relative(self):
        """The page sits beside the cards, so it opens from a file:// URL with
        nothing serving it."""
        found = page.render("Andel", "Andel 1 a", [record(card="shot.png")])
        assert "/x/shot.png" not in found

    def test_sorted_by_location(self):
        found = page.render("Andel", "Andel 1 a",
                            [record(9, "Nine"), record(2, "Two"), record(5, "Five")])
        assert found.index("Two") < found.index("Five") < found.index("Nine")

    def test_a_bookmark_from_orbit_sorts_last(self):
        """No location index - marked from orbit or with the destination
        deselected. Last, not location zero."""
        found = page.render("Andel", "Andel 1 a",
                            [record(None, "Orbit"), record(3, "Ground")])
        assert found.index("Ground") < found.index("Orbit")

    def test_missing_fields_read_as_a_dash(self):
        found = page.render("Andel", "Andel 1 a",
                            [record(None, None, None, None, None, None)])
        assert "-</td>" in found
        assert "None" not in found

    def test_the_count_is_stated(self):
        assert "1 bookmark<" in page.render("A", "B", [record()])
        assert "2 bookmarks" in page.render("A", "B", [record(1), record(2)])

    def test_a_name_that_is_markup(self):
        """Body names come from the journal, but escaping is not optional in
        something that writes HTML."""
        found = page.render("A", "<script>alert(1)</script>", [record()])
        assert "<script>alert(1)</script>" not in found
        assert "&lt;script&gt;" in found


class TestWrite:
    def test_writes_beside_the_cards(self, tmp_path):
        path = page.write("Andel", "Andel 1 a", [record()], root=str(tmp_path))
        assert os.path.dirname(path) == str(tmp_path)
        assert os.path.isfile(path)

    def test_named_after_the_body(self, tmp_path):
        path = page.write("Andel", "Andel 1 a", [record()], root=str(tmp_path))
        assert os.path.basename(path) == "Andel 1 a.html"

    def test_a_name_windows_refuses(self, tmp_path):
        path = page.write("Andel", "Odd:Body", [record()], root=str(tmp_path))
        assert ":" not in os.path.basename(path)
        assert os.path.isfile(path)

    def test_nothing_to_show_writes_nothing(self, tmp_path):
        assert page.write("Andel", "Andel 1 a", [], root=str(tmp_path)) is None
        assert list(tmp_path.iterdir()) == []

    def test_it_is_rewritten_each_time(self, tmp_path):
        """The bookmarks are the truth and this is a view of them, so a stale
        page is a bug waiting rather than a cache."""
        page.write("Andel", "Andel 1 a", [record(1, "First")], root=str(tmp_path))
        path = page.write("Andel", "Andel 1 a", [record(1, "Second")], root=str(tmp_path))
        text = open(path, encoding="utf-8").read()
        assert "Second" in text and "First" not in text

    def test_a_folder_it_cannot_write(self, tmp_path, monkeypatch):
        """A read-only folder costs the table, not the bookmarks."""
        def boom(*args, **kwargs):
            raise OSError("read only")
        monkeypatch.setattr(page.os, "makedirs", boom)
        assert page.write("Andel", "Andel 1 a", [record()],
                          root=str(tmp_path / "nope")) is None
