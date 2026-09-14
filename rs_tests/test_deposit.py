"""Rig positions and Amount into a range of tons left."""

import pytest

from rs_core import deposit


class TestTonsLeft:
    def test_the_measured_deposit_sits_inside_its_own_range(self):
        """Four positions, High Amount, 1,150 t mined to Depleted."""
        low, high = deposit.tons_left(4, "High")
        assert (low, high) == (620, 1200)
        assert low <= 1150 <= high

    def test_six_positions_reach_the_public_traces(self):
        """1,716 t falls inside six positions; 1,841 t is 41 t over the top -
        307 t a position, just past the range."""
        low, high = deposit.tons_left(6, "High")
        assert low <= 1716 <= high
        assert 1841 - high == 41

    def test_low_amount_can_be_nearly_empty(self):
        assert deposit.tons_left(6, "Low") == (0, 620)

    def test_depleted_is_nothing(self):
        assert deposit.tons_left(4, "Depleted") == (0, 0)

    @pytest.mark.parametrize("rigs,amount", [
        (None, "High"), (0, "High"), (-2, "High"), ("4", "High"), (True, "High"),
        (4, None), (4, "Plenty"),
    ])
    def test_a_missing_or_unknown_reading_gives_no_range(self, rigs, amount):
        assert deposit.tons_left(rigs, amount) is None


class TestDescribe:
    def test_range(self):
        assert deposit.describe(4, "High") == "≈ 620-1,200 t left"

    def test_open_lower_end(self):
        assert deposit.describe(2, "Low") == "≈ up to 210 t left"

    def test_depleted_needs_no_rigs(self):
        assert deposit.describe(None, "Depleted") == "depleted"

    def test_nothing_to_say(self):
        assert deposit.describe(None, None) == ""
