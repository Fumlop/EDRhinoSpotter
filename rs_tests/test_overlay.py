"""set_topmost: how often HWND_TOPMOST is sent."""

import pytest

from rs_ui import overlay


class FakeUser32:
    def __init__(self):
        self.sent = []
        self.ok = 1

    def SetWindowPos(self, *args):
        self.sent.append(args)
        return self.ok


@pytest.fixture
def user32(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(overlay, "_typed_user32", fake)
    monkeypatch.setattr(overlay, "_topmost_sent", {})
    monkeypatch.setattr(overlay, "_topmost_errors", {})
    return fake


class TestSetTopmost:
    def test_a_window_standing_still_is_sent_once_per_interval(self, user32):
        for _ in range(5):
            overlay.set_topmost(1, 0, 0, 10, 10)
        assert len(user32.sent) == 1

    def test_a_move_is_sent_at_once(self, user32):
        overlay.set_topmost(1, 0, 0, 10, 10)
        overlay.set_topmost(1, 5, 0, 10, 10)
        assert len(user32.sent) == 2

    def test_sent_again_after_the_interval(self, user32, monkeypatch):
        overlay.set_topmost(1, 0, 0, 10, 10)
        clock = overlay.time.monotonic() + overlay.TOPMOST_EVERY_S
        monkeypatch.setattr(overlay.time, "monotonic", lambda: clock)
        overlay.set_topmost(1, 0, 0, 10, 10)
        assert len(user32.sent) == 2

    def test_each_window_has_its_own_interval(self, user32):
        overlay.set_topmost(1, 0, 0, 10, 10)
        overlay.set_topmost(2, 0, 0, 10, 10)
        assert len(user32.sent) == 2

    def test_a_failed_send_is_tried_again_on_the_next_tick(self, user32):
        user32.ok = 0
        overlay.set_topmost(1, 0, 0, 10, 10)
        overlay.set_topmost(1, 0, 0, 10, 10)
        assert len(user32.sent) == 2

    def test_force_sends_inside_the_interval(self, user32):
        """A window shown again may be under the game: raised at once."""
        overlay.set_topmost(1, 0, 0, 10, 10)
        overlay.set_topmost(1, 0, 0, 10, 10, force=True)
        assert len(user32.sent) == 2
