"""One palette, and the single place it is converted."""

import pytest

from rs_core import palette, spotcard
from rs_ui import scan


class TestRgb:
    @pytest.mark.parametrize("colour,expected", [
        ("#87ceeb", (135, 206, 235)),
        ("#000000", (0, 0, 0)),
        ("#ffffff", (255, 255, 255)),
        ("87ceeb",  (135, 206, 235)),
    ])
    def test_converts(self, colour, expected):
        assert palette.rgb(colour) == expected

    @pytest.mark.parametrize("bad", ["#fff", "", "#12345", "#1234567"])
    def test_refuses_anything_else(self, bad):
        """Loudly, because a colour that silently becomes black is a card
        nobody can read and a bug nobody can see."""
        with pytest.raises(ValueError):
            palette.rgb(bad)


class TestOnePalette:
    """The card and the window drew from two schemes and looked like two
    tools. These pin them together."""

    def test_the_card_uses_the_window_colours(self):
        assert spotcard.PAPER == palette.rgb(palette.BG)
        assert spotcard.INK == palette.rgb(palette.FG)
        assert spotcard.ACCENT == palette.rgb(palette.ACCENT)

    def test_the_window_uses_the_palette(self):
        assert scan.BG == palette.BG
        assert scan.ACCENT == palette.ACCENT
        assert scan.GOOD == palette.GOOD

    def test_the_card_ground_matches_the_window_ground(self):
        """Side by side, the same black. This is the one that a screenshot
        beside a card would fail on first."""
        assert spotcard.PAPER == palette.rgb(scan.BG)

    def test_every_colour_is_a_real_hex(self):
        names = [name for name in dir(palette)
                 if name.isupper() and isinstance(getattr(palette, name), str)]
        assert len(names) >= 8
        for name in names:
            assert palette.rgb(getattr(palette, name))
