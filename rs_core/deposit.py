"""Tons left in a bookmarked deposit, as a (low, high) range.

Model: tons = rig positions * tons-per-position * share-left. Tons-per-position
depends on Density, share-left on Amount.

TONS_PER_RIG = TONS_BASE (110-175 t a rig position) * DENSITY_FACTOR
(High 1, Medium 2, Low 3), set 11 Nov 2026 from nine deposits mined High Amount
to Depleted; "guide" rows are Rhino Field Guide v0.7 5.1, rigs used:

  High    Aramo AB 1 a loc 10 Alexandrite  4 positions    538 t  134 t/pos
  High    Aramo AB 1 a loc 11 Monazite     4 positions    612 t  153 t/pos
  High    Dunn Actual Iridium (guide)      6 rigs         675 t  112 t/pos
  Medium  Eme A 1 a loc 9 Monazite         4 positions  1,537 t  384 t/pos
  Medium  Kaadan77 Iridium A (guide)       6 rigs       1,539 t  257 t/pos
  Medium  Kaadan77 Iridium B (guide)       6 rigs       1,312 t  219 t/pos
  Low     Monazite, 13 Sep                 4 positions  1,150 t  288 t/pos
  Low     Col 285 XT-Q c5-21 6 a loc 13    1 position     446 t  446 t/pos
  Low     Col 285 XT-Q c5-21 6 a loc 13    4 positions  1,892 t  473 t/pos

Outside the bands: Medium 384 and 219 t/pos (band 220-350), Low 288 t/pos
(band 330-525). Order matches Rhino Evidence Register PE-071 (Low ~2,600 / Medium
~1,500 / High ~500 chunks a deposit). A missing Density takes High's low end
to Low's high end.

SHARE_LEFT, from the label transitions in the same traces and guide v0.7
5.1 / 12.6 (Dunn Iridium 632 t, zrice03 Thortveitite 2,500 t): High -> Medium
after 32.0-43.4% mined, Medium -> Low after 64.4-73.3%.

No tkinter. Tests in rs_tests/test_deposit.py.
"""

# Rig positions a deposit can hold. Six can be worked at once (register
# GA-020); a seventh position is physically confirmed (GA-021) and is a buffer -
# it can be placed, it cannot be run. The twelve rig units the Rhino carries
# (GA-023) are stock, not positions on one deposit.
MAX_RIGS = 7

DENSITIES = ("Low", "Medium", "High")
AMOUNTS = ("High", "Medium", "Low", "Depleted")

# Tons per rig position in a full deposit. See module docstring.
TONS_BASE = (110, 175)
DENSITY_FACTOR = {"High": 1, "Medium": 2, "Low": 3}
TONS_PER_RIG = {density: (TONS_BASE[0] * factor, TONS_BASE[1] * factor)
                for density, factor in DENSITY_FACTOR.items()}
# Missing or unknown Density: High's low end to Low's high end.
TONS_PER_RIG_UNKNOWN = (TONS_PER_RIG["High"][0], TONS_PER_RIG["Low"][1])

SHARE_LEFT = {
    "High": (0.566, 1.0),
    "Medium": (0.267, 0.680),
    "Low": (0.0, 0.356),
    "Depleted": (0.0, 0.0),
}


def tons_left(rigs, amount, density=None):
    """(low, high) tons left, rounded to 10 t.

    None when `amount` is not in SHARE_LEFT or `rigs` is not a positive int.
    A missing or unknown `density` widens the range instead of returning None.
    """
    share = SHARE_LEFT.get(amount)
    if share is None or not isinstance(rigs, int) or isinstance(rigs, bool) or rigs <= 0:
        return None
    per_rig = TONS_PER_RIG.get(density, TONS_PER_RIG_UNKNOWN)
    return (_round10(rigs * per_rig[0] * share[0]),
            _round10(rigs * per_rig[1] * share[1]))


def describe(rigs, amount, density=None):
    """'≈ 620-1,200 t left', 'depleted', or '' when tons_left() is None."""
    if amount == "Depleted":
        return "depleted"
    span = tons_left(rigs, amount, density)
    if span is None:
        return ""
    low, high = span
    if low == 0:
        return f"≈ up to {high:,} t left"
    return f"≈ {low:,}-{high:,} t left"


def _round10(value):
    return int(round(value / 10.0)) * 10
