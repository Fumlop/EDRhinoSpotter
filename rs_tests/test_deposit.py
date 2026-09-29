"""Rig positions, Amount and Density into a range of tons left."""

import pytest

from rs_core import deposit


class TestTonsLeft:
    # (rig positions, Density, tons mined High Amount -> Depleted); deposit.py docstring
    MEASURED = [(4, "High", 538), (4, "High", 612), (4, "Low", 1150),
                (1, "Low", 446), (4, "Low", 1892)]

    @pytest.mark.parametrize("rigs,density,tons", MEASURED)
    def test_measured_deposits_sit_inside_their_range(self, rigs, density, tons):
        low, high = deposit.tons_left(rigs, "High", density)
        assert low <= tons <= high

    def test_the_medium_deposit_is_over_its_band(self):
        """Eme A 1 a loc 9, 1,537 t: 137 t over Medium's top (350 t/pos * 4)."""
        assert 1537 - deposit.tons_left(4, "High", "Medium")[1] == 137

    def test_density_factor_orders_the_bands(self):
        high, medium, low = (deposit.tons_left(4, "High", d) for d in ("High", "Medium", "Low"))
        assert high == (280, 700) and medium == (570, 1400) and low == (850, 2100)

    @pytest.mark.parametrize("density", [None, "Plenty"])
    def test_unread_density_spans_all_bands(self, density):
        assert deposit.tons_left(4, "High", density) == (280, 2100)

    def test_six_low_density_positions_hold_the_public_traces(self):
        """Register PE-042/043/044: 1,716-1,841 t, Density not recorded."""
        low, high = deposit.tons_left(6, "High", "Low")
        assert low <= 1716 and 1841 <= high

    def test_low_amount_can_be_nearly_empty(self):
        assert deposit.tons_left(6, "Low", "Low") == (0, 1080)

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
        assert deposit.describe(4, "High", "Low") == "≈ 850-2,100 t left"

    def test_density_moves_the_range(self):
        assert deposit.describe(4, "High", "Medium") == "≈ 570-1,400 t left"

    def test_open_lower_end(self):
        assert deposit.describe(2, "Low", "Low") == "≈ up to 360 t left"

    def test_depleted_needs_no_rigs(self):
        assert deposit.describe(None, "Depleted") == "depleted"

    def test_nothing_to_say(self):
        assert deposit.describe(None, None) == ""
