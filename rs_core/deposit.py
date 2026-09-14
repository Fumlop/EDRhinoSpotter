"""How many tons a bookmarked deposit still holds, as a range.

Full deposit: 275-300 t for every rig circle the deposit draws - the working
assumption is that its reserve is built from those circles. The one
measured deposit behind that is Monazite, High Amount / Low Density, four rig
positions, mined by two commanders to Depleted on 13 Sep 2026: 782 t in one
journal and 368 t reported by the other, 1,150 t, 287.5 t a position. The
public depletion traces (Rhino Evidence Register PE-042/043/044, 1,716-1,841 t)
come to 286-307 t a position if those deposits held six, which the register
does not record.

Density is not used. The chunk bands by Density (PE-071: Low 2,600 /
Medium 1,500 / High 500 chunks) did not fit that deposit; the bookmark keeps
Density, and it stays out of the range until an effect is confirmed.

Share still in the deposit, by Amount - where the traces changed label:
  High -> Medium after 33.5-43.4 % was mined, Medium -> Low after 65.8-73.3 %.
So High is 56.6-100 % left, Medium 26.7-66.5 %, Low 0-34.2 %.

No tkinter. See rs_tests/test_deposit.py.
"""

DENSITIES = ("Low", "Medium", "High")
AMOUNTS = ("High", "Medium", "Low", "Depleted")

TONS_PER_RIG = (275, 300)

SHARE_LEFT = {
    "High": (0.566, 1.0),
    "Medium": (0.267, 0.665),
    "Low": (0.0, 0.342),
    "Depleted": (0.0, 0.0),
}


def tons_left(rigs, amount):
    """(low, high) tons still in the deposit, rounded to 10 t, or None when
    the rig count or the Amount is missing."""
    share = SHARE_LEFT.get(amount)
    if share is None or not isinstance(rigs, int) or isinstance(rigs, bool) or rigs <= 0:
        return None
    return (_round10(rigs * TONS_PER_RIG[0] * share[0]),
            _round10(rigs * TONS_PER_RIG[1] * share[1]))


def describe(rigs, amount):
    """'≈ 620-1,200 t left', 'depleted', or '' when there is nothing to say."""
    if amount == "Depleted":
        return "depleted"
    span = tons_left(rigs, amount)
    if span is None:
        return ""
    low, high = span
    if low == 0:
        return f"≈ up to {high:,} t left"
    return f"≈ {low:,}-{high:,} t left"


def _round10(value):
    return int(round(value / 10.0)) * 10
