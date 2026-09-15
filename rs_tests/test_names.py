"""The one filename rule, which three places used to each have their own."""

import pytest

from rs_core import names


@pytest.mark.unit
class TestSafe:

    def test_keeps_a_real_system_name(self):
        assert names.safe("Col 285 Sector KM-V d2-36") == "Col 285 Sector KM-V d2-36"

    @pytest.mark.parametrize("bad", list(r'<>:"/\|?*'))
    def test_every_refused_character_becomes_an_underscore(self, bad):
        assert names.safe(f"a{bad}b") == "a_b"

    def test_spaces_stay_by_default(self):
        assert names.safe("Hyperion Reach") == "Hyperion Reach"

    def test_nothing_left_falls_back(self):
        assert names.safe("   ") == "unknown"
        assert names.safe(None) == "unknown"
        assert names.safe("", fallback="spot") == "spot"

    def test_surrounding_space_is_trimmed(self):
        # A trailing space is legal in a Python string and not in a Windows
        # directory name - Explorer silently drops it and the path stops
        # matching.
        assert names.safe("  Aramo  ") == "Aramo"
