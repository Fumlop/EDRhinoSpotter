# Coverage: rs_tests/test_hotkey.py -> rs_e2etest/hotkey_e2e.py

| Unit test | E2E check |
|---|---|
| `TestParse::test_the_defaults_parse_to_ctrl_alt_and_their_letter` | 1 (defaults held with WinUser.h flags/vk), 3 (SendInput Ctrl+Alt+Z/B/M/D reaches the callback) |
| `TestParse::test_shift_digits_and_function_keys` | 9 (every Shift, digit and F1-F12 combo held with the WinUser.h vk), 7 (Ctrl+Alt+Shift+F9..F12) |
| `TestParse::test_what_settings_could_not_offer_is_refused` | 8 (same 7 strings plus `nonsense` stored in config: label falls back, Ctrl+Alt+Z held) |
| `TestParse::test_every_offered_combination_parses` | 9 (192 combos: held by the module, or reported taken; 0 unaccounted) |
| `TestParse::test_the_four_actions_have_distinct_defaults` | 0 + 1 (four defaults, each free before and held after start; a duplicate would fail one probe with the check-11 warning) |
| `TestLabel::test_without_edmc_every_key_names_its_default` | 1 (empty config -> defaults registered); not covered as `config is None`: the harness always injects a config dict, EDMC always has one |
| `TestLabel::test_a_stored_combination_wins_and_a_broken_one_falls_back` | 7 (stored combos win: label() and registration), 8 (broken ones fall back) |

Not covered by either:

- `start()` on a non-Windows interpreter (`ctypes.windll` missing): no such host here.
- `minimap.prefs_changed()` -> `hotkey.restart()` from the real Settings OptionMenus: restart is called directly.
- A physical key press on a non-US layout (AltGr = Ctrl+Alt): SendInput sends vk codes, not scan codes.
