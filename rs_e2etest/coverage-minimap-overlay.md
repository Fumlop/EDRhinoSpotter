# Unit tests -> E2E checks: minimap and overlay

Unit files: `rs_tests/test_minimap.py`, `rs_tests/test_overlay.py`.
Harness: `rs_e2etest/minimap_e2e.py`; check names as printed in `report.txt`.
Failure modes the harness cannot see: `minimap-place-topmost.md`.
First all-pass run with these checks: `out/20260921-184952`, 56/56.

## rs_tests/test_minimap.py

| Unit test | E2E check |
|---|---|
| TestRhino::test_an_srv_never_named_counts_as_the_rhino | 6 no LaunchSRV seen: taken as the Rhino, painted |
| TestRhino::test_the_rhino | 17 LaunchSRV mev_rhino: map up |
| TestRhino::test_the_scarab_is_not | 16 LaunchSRV testbuggy stored under rhinospotter_srv_type; 16 Scarab: map down |
| TestRhino::test_other_events_leave_it | 16 DockSRV naming mev_rhino: still the Scarab, map down |
| TestRhino::test_the_rhino_paints | 17 Rhino: painted; 17 Rhino map saved to the test db |
| TestRhino::test_switched_off_paints_nothing | 18 switched off: map down; 18 switched off: the Rhino map untouched; 18 switched off: nothing saved |
| TestRhino::test_another_srv_paints_nothing | 16 Scarab: nothing saved |
| TestFreeMove::test_off_by_default | 0 Free move unticked by default |
| TestFreeMove::test_the_position_is_screen_pixels | 4 position stored under rhinospotter_minimap_xy as screen pixels; 6 free move: at the stored pixels |
| TestFreeMove::test_a_position_on_a_second_monitor_stays_there | not covered: one monitor (2048x1152) on the test machine |
| TestFreeMove::test_a_position_past_the_edge_is_pulled_back_onto_the_monitor | 15 5000,5000 pulled back to the monitor's bottom right |
| TestFreeMove::test_a_negative_position_stops_at_the_top_left | 15 -800,-800 stops at the monitor's top left |
| TestFreeMove::test_a_window_bigger_than_the_monitor_still_starts_on_it | not covered: map side capped at 640 px (`coverage.MAP_ZOOM_MAX_PX`), window stays under the 1152 px screen |
| TestFreeMove::test_nonsense_in_the_setting_is_no_position_at_all | 15 stored '' / 'left' / '10' / '10,20,30' / 'a,b': back in the corner |
| TestFreeMove::test_no_config_no_position | not covered: `config` is None only when `from config import config` fails (`rs_ui/minimap.py:36-38`), i.e. outside EDMC |
| TestPlaceMode::test_placing_without_a_window_says_so_and_does_not_raise | 0 place() without a window returns False; 0 place() without a window says so on the hint line |
| TestPlaceMode::test_locking_when_nothing_is_being_placed_is_a_no_op | 20 settings closed without placing: no lock; 20 settings closed without placing: position unchanged |
| TestPrefsLayout::test_every_widget_gets_a_cell_of_its_own | 0 settings tab: every widget in a grid cell of its own (+ `0-settings.png`) |
| TestPrefsSaving::test_hotkeys_are_saved | 19 hotkey dropdown found for rhinospotter_hotkey_center; 19 OK stores Ctrl+Alt+Q under rhinospotter_hotkey_center; 19 hotkey.label() returns the new combination |

## rs_tests/test_overlay.py

| Unit test | E2E check |
|---|---|
| TestSetTopmost::test_a_window_standing_still_is_sent_once_per_interval | 9 not re-sent inside 5 s of the last send |
| TestSetTopmost::test_a_move_is_sent_at_once | 14 moved inside the interval: at the new pixels; 14 moved inside the interval: topmost on the same tick |
| TestSetTopmost::test_sent_again_after_the_interval | 9 back on top within 5 s + 1 tick |
| TestSetTopmost::test_each_window_has_its_own_interval | not covered: needs the guide arrow up beside the map; `overlay._tick` shows it only with Elite in the foreground (`game_focused`), which the harness cannot take without input |
| TestSetTopmost::test_a_failed_send_is_tried_again_on_the_next_tick | not covered: SetWindowPos on a live window of the same process is not refused; no way to make it fail without replacing user32 |
| TestSetTopmost::test_force_sends_inside_the_interval | 10 shown again: visible and topmost on the same tick |
