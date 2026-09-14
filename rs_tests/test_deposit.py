"""Density and Amount into a range of tons left."""

import pytest

from rs_core import deposit


class TestTonsLeft:
    def test_a_fresh_low_density_deposit_spans_both_sources(self):
        # 1,716 t is the smallest deposit mined dry, 2,673 t the top of the
        # chunk band; High Amount can already be 43 % mined.
        assert deposit.tons_left("Low", "High") == (970, 2670)

    def test_low_amount_can_be_nearly_empty(self):
        low, high = deposit.tons_left("Medium", "Low")
        assert low == 0
        assert high == 540

    def test_depleted_is_nothing(self):
        assert deposit.tons_left("High", "Depleted") == (0, 0)

    @pytest.mark.parametrize("density,amount", [
        (None, "High"), ("Low", None), ("", ""), ("Dense", "High"), ("Low", "Plenty"),
    ])
    def test_a_missing_or_unknown_reading_gives_no_range(self, density, amount):
        assert deposit.tons_left(density, amount) is None

    def test_higher_density_holds_less(self):
        """The ordering the reserve bands claim, Low > Medium > High."""
        tops = [deposit.tons_left(d, "High")[1] for d in deposit.DENSITIES]
        assert tops == sorted(tops, reverse=True)


class TestDescribe:
    def test_range(self):
        assert deposit.describe("Low", "High") == "≈ 970-2,670 t left"

    def test_open_lower_end(self):
        assert deposit.describe("High", "Low") == "≈ up to 200 t left"

    def test_depleted_needs_no_density(self):
        assert deposit.describe(None, "Depleted") == "depleted"

    def test_nothing_to_say(self):
        assert deposit.describe(None, None) == ""
