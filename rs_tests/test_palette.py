"""One palette, and the single place it is converted."""

import pytest

from rs_core import palette
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
    """The window and the map drew from one scheme; these pin it."""

    def test_the_window_uses_the_palette(self):
        assert scan.BG == palette.BG
        assert scan.ACCENT == palette.ACCENT
        assert scan.GOOD == palette.GOOD

    def test_every_colour_is_a_real_hex(self):
        names = [name for name in dir(palette)
                 if name.isupper() and isinstance(getattr(palette, name), str)]
        assert len(names) >= 8
        for name in names:
            assert palette.rgb(getattr(palette, name))
