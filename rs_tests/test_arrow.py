"""The guide arrow's frames. PIL only - no display and no Tk."""

import pytest

from rs_core import arrow, palette


def pixels(image):
    """Every pixel as an (r, g, b) tuple.

    Off tobytes() rather than getdata(): Pillow is retiring getdata, and the
    replacement is not in the Pillow that ships inside EDMC.
    """
    raw = image.tobytes()
    return [tuple(raw[index:index + 3]) for index in range(0, len(raw), 3)]


@pytest.mark.unit
class TestBucket:

    def test_zero_and_a_full_turn_are_the_same_frame(self):
        assert arrow.bucket(0) == arrow.bucket(360) == 0

    def test_an_angle_snaps_to_the_nearest_frame(self):
        assert arrow.bucket(arrow.STEP * 0.4) == 0
        assert arrow.bucket(arrow.STEP * 0.6) == 1

    def test_the_last_frame_wraps_rather_than_running_past_the_end(self):
        assert arrow.bucket(359.9) == 0
        assert arrow.bucket(-1) == 0
        assert max(arrow.bucket(d) for d in range(360)) == arrow.STEPS - 1

    def test_no_heading_points_up(self):
        # guide.fix hands over None when the game has no heading to give.
        assert arrow.bucket(None) == 0


@pytest.mark.unit
class TestFrame:

    def test_it_is_the_size_it_says(self):
        assert arrow.frame(0).size == (arrow.SIZE, arrow.SIZE)
        assert arrow.frame(0, size=48).size == (48, 48)

    def test_the_corners_are_the_key_colour(self):
        # The overlay makes a hole of that colour, so every pixel the arrow
        # does not cover has to be exactly it.
        image = arrow.frame(0)
        edge = arrow.SIZE - 1
        for spot in ((0, 0), (edge, 0), (0, edge), (edge, edge)):
            assert image.getpixel(spot) == palette.rgb(arrow.KEY)

    def test_something_is_drawn(self):
        assert any(pixel != palette.rgb(arrow.KEY) for pixel in pixels(arrow.frame(0)))

    def test_the_two_faces_are_different_colours(self):
        # The fold is the whole point. One colour is a flat triangle.
        painted = {pixel for pixel in pixels(arrow.frame(0))
                   if pixel != palette.rgb(arrow.KEY)}
        assert len(painted) >= 2

    def test_no_face_lands_on_the_key_colour(self):
        # A dark bookmark colour shaded down would punch a hole through the
        # middle of its own arrow.
        for factor in (arrow.LIT, arrow.SHADE):
            assert arrow._tone("#020202", factor) != palette.rgb(arrow.KEY)

    def test_turning_it_changes_the_picture(self):
        assert arrow.frame(0).tobytes() != arrow.frame(90).tobytes()

    def test_two_angles_in_one_bucket_are_one_picture(self):
        # This is what makes the cache worth having.
        assert arrow.frame(0).tobytes() == arrow.frame(arrow.STEP * 0.4).tobytes()

    def test_the_colour_asked_for_is_the_colour_drawn(self):
        lit = arrow._tone(palette.GOOD, arrow.LIT)
        assert lit in set(pixels(arrow.frame(0, palette.GOOD)))

    def test_the_dim_arrow_is_not_the_accent_one(self):
        # north-up has to look like a different instrument, not a dimmer one.
        assert (arrow.frame(0, palette.MUTED).tobytes()
                != arrow.frame(0, palette.ACCENT).tobytes())

    def test_it_points_up_at_zero(self):
        # More of the arrow above the middle than below it, which is what
        # "points up" means for a shape with a notch in its tail.
        key = palette.rgb(arrow.KEY)
        half = arrow.SIZE // 2
        painted = [(index // arrow.SIZE, index % arrow.SIZE)
                   for index, pixel in enumerate(pixels(arrow.frame(0))) if pixel != key]
        assert min(row for row, _ in painted) < arrow.SIZE - max(row for row, _ in painted)
        assert all(abs(column - half) < half for _, column in painted)
