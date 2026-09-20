"""Tons left in a bookmarked deposit, as a (low, high) range.

Model: tons = rig positions * tons-per-position * share-left. Tons-per-position
depends on Density, share-left on Amount.

TONS_PER_RIG, measured on two Monazite deposits, 4 rig positions each, High
Amount to Depleted, two commanders per deposit:

  Low Density,    13 Sep 2026:              782 t + 368 t = 1,150 t
                                            -> 287.5 t per position
  Medium Density, 15-17 Sep 2026,           1,193 t + 344 t = 1,537 t
  Eme A 1 a loc 9                           -> 384 t per position

Same material, same rig count, same method; Density is the only recorded
difference. One deposit per band, so each is that deposit +/- 4%. High is
unmeasured, so High and a missing Density take the span of both bands.

Not used: Rhino Evidence Register PE-042/043/044 (1,716-1,841 t) record neither
Density nor rig count; at 6 positions they give 286-307 t each, i.e. Low. The
PE-071 chunk bands (Low 2,600 / Medium 1,500 / High 500 chunks) rank Low above
Medium, inverting the tons measured here; chunks are not tons.

SHARE_LEFT, from the label transitions in the same traces: High -> Medium after
33.5-43.4% mined, Medium -> Low after 65.8-73.3%.

No tkinter. Tests in rs_tests/test_deposit.py.
"""

# Rig positions a deposit can hold. Six can be worked at once (register
# GA-020); a seventh position is physically confirmed (GA-021) and is a buffer -
# it can be placed, it cannot be run. The twelve rig units the Rhino carries
# (GA-023) are stock, not positions on one deposit.
MAX_RIGS = 7

DENSITIES = ("Low", "Medium", "High")
AMOUNTS = ("High", "Medium", "Low", "Depleted")

# Tons per rig position in a full deposit, by Density. See module docstring.
TONS_PER_RIG = {
    "Low": (275, 300),
    "Medium": (370, 400),
}
# High and missing Density: unmeasured, so the span of both measured bands.
TONS_PER_RIG_UNKNOWN = (TONS_PER_RIG["Low"][0], TONS_PER_RIG["Medium"][1])

SHARE_LEFT = {
    "High": (0.566, 1.0),
    "Medium": (0.267, 0.665),
    "Low": (0.0, 0.342),
    "Depleted": (0.0, 0.0),
}


def tons_left(rigs, amount, density=None):
    """(low, high) tons left, rounded to 10 t.

    None when `amount` is not in SHARE_LEFT or `rigs` is not a positive int.
    A High or missing `density` widens the range instead of returning None.
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
