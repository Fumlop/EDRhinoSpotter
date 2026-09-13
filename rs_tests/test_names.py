"""The one filename rule, which three places used to each have their own."""

import pytest

from rs_core import names, spotcard, store


@pytest.mark.unit
class TestSafe:

    def test_keeps_a_real_system_name(self):
        assert names.safe("Col 285 Sector KM-V d2-36") == "Col 285 Sector KM-V d2-36"

    @pytest.mark.parametrize("bad", list(r'<>:"/\|?*'))
    def test_every_refused_character_becomes_an_underscore(self, bad):
        assert names.safe(f"a{bad}b") == "a_b"

    def test_spaces_stay_by_default(self):
        assert names.safe("Hyperion Reach") == "Hyperion Reach"

    def test_spaces_go_when_asked(self):
        assert names.safe("Hyperion Reach", spaces=False) == "Hyperion_Reach"

    def test_nothing_left_falls_back(self):
        assert names.safe("   ") == "unknown"
        assert names.safe(None) == "unknown"
        assert names.safe("", fallback="spot") == "spot"

    def test_surrounding_space_is_trimmed(self):
        # A trailing space is legal in a Python string and not in a Windows
        # directory name - Explorer silently drops it and the path stops
        # matching.
        assert names.safe("  Aramo  ") == "Aramo"


@pytest.mark.unit
class TestTheCallersAgree:
    """The cache and the cards folder have to spell a system the same way, or
    a card cannot be matched to the system it was marked in."""

    def test_cache_file_and_cards_folder_use_the_same_name(self):
        system = 'Col 285 "Sector" KM-V:d2-36'
        assert store.safe_name(system) in spotcard.card_dir(system)

    def test_a_bookmark_filename_has_no_spaces_in_it(self):
        name = spotcard.filename({"planet_name": "Hyperion Reach 4 a",
                                  "location_index": 7, "commodity": "Jadeite"})
        assert " " not in name
        assert name.endswith(".json")
