# Unit test -> E2E check: migrate, replay, rs_api

Harness `rs_e2etest/data_e2e.py`, failure summary `data-flow.md`. Check IDs
are the prefixes in `report.txt`.

## rs_tests/test_migrate.py

| Unit test | E2E check |
|---|---|
| TestImport.test_everything_readable_comes_in | M1 counts, bodies, bookmarks, maps (fixtures written from the live-db copy) |
| TestImport.test_the_old_files_are_left_exactly_as_they_were | M1 old files byte for byte |
| TestImport.test_migrate_done_says_what_came_in | M1 migrate.done written, counts |
| TestImport.test_nothing_there_is_still_done | N1 |
| TestImport.test_a_bookmark_without_a_card_key_finds_its_png_by_name | M1 bookmarks record as written (`card` expected from the PNG name for even ids) |
| TestImport.test_a_plain_json_map_is_read_and_a_gzipped_one_wins | M1 maps |
| TestImport.test_temp_files_and_pictures_are_not_maps | M1 maps; M1 skipped list has no .tmp/.png |
| TestBadFiles.test_a_broken_file_is_listed_logged_and_the_rest_come_in | M1 skipped list = the broken files; one log warning per entry |
| TestBadFiles.test_a_value_sqlite_will_not_store_skips_that_file_only | M1 (`E2E_rigs_list.json` skipped; map with `body: null` imported) |
| TestBadFiles.test_a_folder_that_cannot_be_listed_leaves_no_marker | U1 (ACL deny on `cards\` via icacls), U3 |
| TestBadFiles.test_a_database_that_cannot_be_written_leaves_no_marker | C1, C2 (db held by another process instead of a patched `write_bookmark`) |
| TestOnce.test_with_migrate_done_no_folder_is_looked_at | M3 (db and marker untouched, new file not imported); R1. "no folder listed" itself: not observed |
| TestOnce.test_a_lost_marker_is_written_again_without_importing | M4 |
| TestOnce.test_a_marker_that_cannot_be_written_leaves_the_record | not covered: needs `atomic.write_text` to fail after the commit while the same folder stays writable for the db |
| TestOnce.test_a_second_run_with_no_record_adds_nothing_and_keeps_newer_rows | M5 |
| TestLeftovers.test_nothing_before_the_import | U2 (Settings button handler) |
| TestLeftovers.test_the_imported_json_and_temp_files_go_pictures_stay | M6 |
| TestLeftovers.test_a_lost_database_deletes_nothing | D1 |
| TestLeftovers.test_a_bookmark_deleted_after_the_import_keeps_its_file | not covered: M5 re-imports the deleted bookmark before M6 runs the button |
| TestLeftovers.test_a_skipped_file_is_kept | M6 |
| TestLeftovers.test_a_file_written_after_the_import_is_kept | M6 (`E2E Late.json`, mtime = migrate.done + 60 s) |

## rs_tests/test_replay.py

| Unit test | E2E check |
|---|---|
| TestJournalFiles.test_only_recent_files | R2 journal count (one copy older than 7 days left out) |
| TestJournalFiles.test_oldest_first | R2 body values = last Scan in mtime order (indirect) |
| TestJournalFiles.test_other_files_are_left_alone | R2 journal count (`Status.json` copied, left out) |
| TestJournalFiles.test_a_missing_folder_is_empty_not_an_error | R5 |
| TestReplay.test_collects_bodies_per_system | R2 every landable Scan body in the db |
| TestReplay.test_location_counts_come_through | not covered: no oracle for per-visit signal counts; R2 checks only that counts are not lost |
| TestReplay.test_a_second_visit_does_not_lose_the_first | R2 every body in the db (21 journals, systems visited more than once); R2 no cached body dropped |
| TestReplay.test_a_later_visit_updates_a_body_it_rescanned | R2 body_id, system_address, distance = last Scan |
| TestReplay.test_broken_lines_are_skipped | R2 truncated last line, line after invalid UTF-8 bytes |
| TestReplay.test_systems_with_nothing_landable_are_dropped | R2 systems rebuilt = systems with a landable Scan; R4 every system listed |
| TestScoring.test_every_body_is_worth_its_best_rate | not covered: score values depend on `mining_sheet.json`, regenerated from live data |
| TestScoring.test_ground_the_sheet_never_measured_is_worth_nothing | not covered: same reason |
| TestScoring.test_more_of_the_same_good_ground_scores_higher | not covered: same reason |
| TestScoring.test_ranking_puts_the_best_first | R4 order |
| TestScoring.test_counted_locations_break_a_tie | R4 order rule; not exercised: 0 score ties in the real journals |
| TestBest.test_picks_the_richest_system | T1 picks the first system of the ranking |
| TestBest.test_no_journals_is_none_not_a_crash | R5 |

## rs_tests/test_api.py

| Unit test | E2E check |
|---|---|
| TestBookmarks.test_the_names_are_the_ones_a_stranger_would_guess | A1 values = stored record; M2 |
| TestBookmarks.test_one_system | A2 |
| TestBookmarks.test_one_body | A2 |
| TestBookmarks.test_depleted_is_a_flag_and_a_time | A1 (`depleted` = bool(`depleted_at`)); A7 depleted read back |
| TestBookmarks.test_the_plugins_own_storage_does_not_leak_through | A1 keys = the table in docs/API.md |
| TestBookmarks.test_a_broken_row_is_skipped_not_raised_on | A10 |
| TestBookmarks.test_no_database_is_no_bookmarks | A11 |
| TestBodies.test_counts_per_body | A3 |
| TestBodies.test_one_system | A3 |
| TestRevision.test_it_moves_when_a_bookmark_is_added | A7 insert |
| TestRevision.test_it_moves_when_one_is_marked_depleted | A7 depleted (x2) |
| TestRevision.test_it_moves_when_one_is_deleted | A7 delete |
| TestRevision.test_it_stands_still_while_nothing_changes | A4 |
| TestRevision.test_it_does_not_come_from_this_process | A7 (every revision read from a separate process) |
| TestRevision.test_no_database_is_zero | A11 |
| TestTheContract.test_the_surface_is_the_four_calls_and_the_schema | A5 |
| TestTheContract.test_reading_needs_neither_edmc_nor_pillow | A5 |
| TestTheContract.test_reading_never_creates_a_database | A11 |

## E2E checks with no unit test

R2 no body loses its counted locations; T1 cached bodies kept; L1 rebuild under
a lock; A6 reads leave the db alone; A7 un-deplete and edit move revision; A8
read during a write; A9 locked db; A12 corrupt db file; M2 migrated bookmarks
read through rs_api; Z live folder untouched.
