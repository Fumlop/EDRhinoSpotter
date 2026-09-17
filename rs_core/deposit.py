"""How many tons a bookmarked deposit still holds, as a range.

Full deposit: a number of tons for every rig circle the deposit draws - the
working assumption is that its reserve is built from those circles - and that
number depends on Density. Two deposits measured, both Monazite, both four rig
positions, both High Amount at the start and mined to Depleted by two
commanders:

  Low Density,    13 Sep 2026: 782 t in one journal + 368 t reported by
                  the other = 1,150 t, 287.5 t a position.
  Medium Density, 15-17 Sep 2026, Eme A 1 a loc 9: 1,193 t in one journal
                  + 344 t reported by the other = 1,537 t, 384 t a position.

Same material, same size, mined the same way; Density is the one recorded
difference, and Medium held a third more. One deposit each, so each band is
that deposit give or take four percent. Nothing yet says whether High holds
more again, so High - and a bookmark with no Density read - get the span of
both bands: a range that admits not knowing, rather than one that is wrong.

The public depletion traces (Rhino Evidence Register PE-042/043/044,
1,716-1,841 t) record neither Density nor rig count. At six positions they come
to 286-307 t each, which is Low.

The chunk bands by Density (PE-071: Low 2,600 / Medium 1,500 / High 500 chunks)
rank Low above Medium, the opposite of the tons measured here. Chunks are not
tons, and they are not used.

Share still in the deposit, by Amount - where the traces changed label:
  High -> Medium after 33.5-43.4 % was mined, Medium -> Low after 65.8-73.3 %.
So High is 56.6-100 % left, Medium 26.7-66.5 %, Low 0-34.2 %.

No tkinter. See rs_tests/test_deposit.py.
"""

DENSITIES = ("Low", "Medium", "High")
AMOUNTS = ("High", "Medium", "Low", "Depleted")

# Tons a rig position holds in a full deposit, by Density.
TONS_PER_RIG = {
    "Low": (275, 300),
    "Medium": (370, 400),
}
# High, or no Density read: nothing measured, so the span of what was.
TONS_PER_RIG_UNKNOWN = (TONS_PER_RIG["Low"][0], TONS_PER_RIG["Medium"][1])

SHARE_LEFT = {
    "High": (0.566, 1.0),
    "Medium": (0.267, 0.665),
    "Low": (0.0, 0.342),
    "Depleted": (0.0, 0.0),
}


def tons_left(rigs, amount, density=None):
    """(low, high) tons still in the deposit, rounded to 10 t, or None when
    the rig count or the Amount is missing. A High or missing Density widens
    the range rather than refusing one."""
    share = SHARE_LEFT.get(amount)
    if share is None or not isinstance(rigs, int) or isinstance(rigs, bool) or rigs <= 0:
        return None
    per_rig = TONS_PER_RIG.get(density, TONS_PER_RIG_UNKNOWN)
    return (_round10(rigs * per_rig[0] * share[0]),
            _round10(rigs * per_rig[1] * share[1]))


def describe(rigs, amount, density=None):
    """'≈ 620-1,200 t left', 'depleted', or '' when there is nothing to say."""
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
