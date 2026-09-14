"""What a deposit's Density and Amount say about the tons still in it.

Both are read off the HUD when the deposit is targeted, and neither is in any
journal event, so the commander picks them in the panel. This turns the pair
into a range of tons left. A range, not a number: the public data behind it is
a handful of deposits, and the two sources disagree.

Full-deposit tons, by Density:
  Low     1,716-1,841 t mined to Depleted on three deposits (Rhino Evidence
          Register PE-042/043/044); 2,600 ± 100 chunks (PE-071) at 0.90-0.99 t
          a chunk (PE-072) is 2,250-2,673 t.
  Medium  1,013 t on one deposit (PE-004); 1,500 ± 100 chunks is 1,260-1,584 t.
  High    no trace mined to Depleted; 500 ± 100 chunks is 360-594 t.
The range runs from the lowest to the highest of the two.

Share still in the deposit, by Amount - where the same traces changed label:
  High -> Medium after 33.5-43.4 % was mined, Medium -> Low after 65.8-73.3 %.
So High is 56.6-100 % left, Medium 26.7-66.5 %, Low 0-34.2 %.

Neither says how many rigs fit: High-Amount deposits have held one to five
(PE-045). No tkinter. See rs_tests/test_deposit.py.
"""

DENSITIES = ("Low", "Medium", "High")
AMOUNTS = ("High", "Medium", "Low", "Depleted")

FULL_TONS = {
    "Low": (1716, 2673),
    "Medium": (1013, 1584),
    "High": (360, 594),
}

SHARE_LEFT = {
    "High": (0.566, 1.0),
    "Medium": (0.267, 0.665),
    "Low": (0.0, 0.342),
    "Depleted": (0.0, 0.0),
}


def tons_left(density, amount):
    """(low, high) tons still in the deposit, rounded to 10 t, or None when
    either reading is missing or not one the HUD shows."""
    full = FULL_TONS.get(density)
    share = SHARE_LEFT.get(amount)
    if full is None or share is None:
        return None
    return (_round10(full[0] * share[0]), _round10(full[1] * share[1]))


def describe(density, amount):
    """'≈ 980-2,670 t left', 'depleted', or '' when there is nothing to say."""
    if amount == "Depleted":
        return "depleted"
    span = tons_left(density, amount)
    if span is None:
        return ""
    low, high = span
    if low == 0:
        return f"≈ up to {high:,} t left"
    return f"≈ {low:,}-{high:,} t left"


def _round10(value):
    return int(round(value / 10.0)) * 10
