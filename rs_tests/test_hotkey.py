"""The hotkey combinations Settings can store, read back as Windows wants them."""

import pytest

from rs_ui import hotkey


@pytest.mark.unit
class TestParse:

    def test_the_defaults_parse_to_ctrl_alt_and_their_letter(self):
        assert hotkey.parse("Ctrl+Alt+Z") == (hotkey.MOD_CONTROL | hotkey.MOD_ALT, 0x5A)
        assert hotkey.parse("Ctrl+Alt+M") == (hotkey.MOD_CONTROL | hotkey.MOD_ALT, 0x4D)

    def test_shift_digits_and_function_keys(self):
        assert hotkey.parse("Ctrl+Shift+7") == (hotkey.MOD_CONTROL | hotkey.MOD_SHIFT, ord("7"))
        assert hotkey.parse("Alt+Shift+F1") == (hotkey.MOD_ALT | hotkey.MOD_SHIFT, 0x70)
        assert hotkey.parse("Ctrl+Alt+Shift+F12") == (
            hotkey.MOD_CONTROL | hotkey.MOD_ALT | hotkey.MOD_SHIFT, 0x7B)

    def test_what_settings_could_not_offer_is_refused(self):
        for combo in ("", "Z", "Alt+Z", "Ctrl+Alt+", "Ctrl+Alt+F13", "Win+Alt+Z", "Ctrl+Alt+ZZ"):
            assert hotkey.parse(combo) is None, combo

    def test_every_offered_combination_parses(self):
        for mods in hotkey.MODIFIER_SETS:
            for key in hotkey.KEY_NAMES:
                assert hotkey.parse(f"{mods}+{key}") is not None

    def test_the_four_actions_have_distinct_defaults(self):
        defaults = [default for _, _, default, _ in hotkey.ACTIONS]
        assert len(set(defaults)) == 4 and all(hotkey.parse(d) for d in defaults)


@pytest.mark.unit
class TestLabel:

    def test_without_edmc_every_key_names_its_default(self):
        for key_id, _, default, _ in hotkey.ACTIONS:
            assert hotkey.label(key_id) == default

    def test_a_stored_combination_wins_and_a_broken_one_falls_back(self, monkeypatch):
        stored = {"rhinospotter_hotkey_zoom": "Ctrl+Shift+F5",
                  "rhinospotter_hotkey_center": "nonsense"}

        class Config:
            def get_str(self, key, default=None):
                return stored.get(key, default)
        monkeypatch.setattr(hotkey, "config", Config())
        assert hotkey.label(hotkey.SIZE) == "Ctrl+Shift+F5"
        assert hotkey.label(hotkey.CENTER) == "Ctrl+Alt+Z"
        assert hotkey.label(hotkey.BORDER) == "Ctrl+Alt+B"
