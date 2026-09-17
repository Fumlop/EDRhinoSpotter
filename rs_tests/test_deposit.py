"""Rig positions, Amount and Density into a range of tons left."""

import pytest

from rs_core import deposit


class TestTonsLeft:
    def test_the_low_density_deposit_sits_inside_its_own_range(self):
        """Four positions, High Amount, Low Density, 1,150 t mined to Depleted."""
        low, high = deposit.tons_left(4, "High", "Low")
        assert (low, high) == (620, 1200)
        assert low <= 1150 <= high

    def test_the_medium_density_deposit_sits_inside_its_own_range(self):
        """Eme A 1 a loc 9: four positions, High Amount, Medium Density,
        1,537 t mined to Depleted."""
        low, high = deposit.tons_left(4, "High", "Medium")
        assert (low, high) == (840, 1600)
        assert low <= 1537 <= high

    def test_the_medium_deposit_does_not_fit_the_low_band(self):
        """The reason Density is in the range at all: without it, this deposit
        gave 337 t more than the most the estimate allowed."""
        assert 1537 - deposit.tons_left(4, "High", "Low")[1] == 337

    @pytest.mark.parametrize("density", ["High", None, "Plenty"])
    def test_high_or_unread_density_spans_both_bands(self, density):
        """Nothing measured at High: the range covers both measured deposits
        rather than guessing which one it is like."""
        low, high = deposit.tons_left(4, "High", density)
        assert (low, high) == (620, 1600)
        assert low <= 1150 and 1537 <= high

    def test_six_low_density_positions_reach_the_public_traces(self):
        """1,716 t falls inside six Low positions; 1,841 t is 41 t over the top -
        307 t a position, just past the range."""
        low, high = deposit.tons_left(6, "High", "Low")
        assert low <= 1716 <= high
        assert 1841 - high == 41

    def test_the_public_traces_fit_when_density_is_unknown(self):
        """The register does not record Density, so neither trace is ruled out."""
        low, high = deposit.tons_left(6, "High")
        assert low <= 1716 and 1841 <= high

    def test_low_amount_can_be_nearly_empty(self):
        assert deposit.tons_left(6, "Low", "Low") == (0, 620)

    def test_depleted_is_nothing(self):
        assert deposit.tons_left(4, "Depleted", "Medium") == (0, 0)

    @pytest.mark.parametrize("rigs,amount", [
        (None, "High"), (0, "High"), (-2, "High"), ("4", "High"), (True, "High"),
        (4, None), (4, "Plenty"),
    ])
    def test_a_missing_or_unknown_reading_gives_no_range(self, rigs, amount):
        assert deposit.tons_left(rigs, amount, "Medium") is None


class TestDescribe:
    def test_range(self):
        assert deposit.describe(4, "High", "Low") == "≈ 620-1,200 t left"

    def test_density_moves_the_range(self):
        assert deposit.describe(4, "High", "Medium") == "≈ 840-1,600 t left"

    def test_open_lower_end(self):
        assert deposit.describe(2, "Low", "Low") == "≈ up to 210 t left"

    def test_depleted_needs_no_rigs(self):
        assert deposit.describe(None, "Depleted") == "depleted"

    def test_nothing_to_say(self):
        assert deposit.describe(None, None) == ""
