# rs_tests/test_update.py -> rs_e2etest/update_e2e.py

Check numbers are the prefixes in `report.txt`. Last run: 46/46,
`rs_e2etest/out/20260921-185050`.

| Unit test | E2E check |
|---|---|
| TestParse.test_tags ("2.0.0", "v2.1", "3", "v2.0.0-beta", "v10.2.3.4") | 2 "every published release tag parses" + "parse order matches git's version order", over the 76 real release tags. Not covered: the shapes "v2.1", "3", "-beta", 4-part tags - no release carries one |
| TestParse.test_unreadable_tags_sort_lowest | 2 "unparsable tags never count as newer" (same inputs, direct call) |
| TestVersion.test_the_changelog_leads_with_the_shipped_version | 1 "changelog leads with update.VERSION" |
| TestVersion.test_the_plugin_exposes_it | 1 "load.py exposes VERSION and __version__ before the update"; 6 "updated plugin reports v5.6.2" (subprocess, `import load`) |
| TestVersion.test_the_version_is_three_numbers | 1 "VERSION is three numbers" |
| TestIsNewer.test_newer | 2 "check_async with RUNNING older reports the release as new" |
| TestIsNewer.test_equal_is_not_an_update | 2 "the same tag against VERSION is not an update" |
| TestIsNewer.test_a_local_build_ahead_is_not_told_to_downgrade | 2 "a local build ahead is not told to downgrade" |
| TestIsNewer.test_defaults_to_the_running_version | 2 check_async (calls `is_newer(tag)` with the default) |
| TestIsNewer.test_the_override_makes_the_current_release_look_new | 1 "RHINOSPOTTER_VERSION read at import" + 2 check_async |
| TestFetch.test_reads_the_tag_off_the_redirect | 2 "fetch_latest = newest release (API) = newest local tag" |
| TestFetch.test_the_zip_comes_from_codeload_for_that_tag | 3 "download returns bytes" from `CODELOAD_ZIP.format(tag)` |
| TestFetch.test_every_failure_is_just_no_answer (OSError, TimeoutError) | 5 connection refused, no DNS, host that never answers |
| TestFetch.test_every_failure_is_just_no_answer (ValueError "not json") | not covered: nothing parses JSON since the API was dropped; no real path raises ValueError |
| TestFetch.test_a_page_that_does_not_land_on_a_tag | 5 "a page that lands off a tag is None" (real /releases page) |
| TestFetch.test_a_failure_warns_once_a_session | 5 "three failures log one warning" |
| TestFetch.test_download_returns_bytes | 3 "download returns bytes" |
| TestFetch.test_a_download_that_fails_is_none | 5 "install_async with codeload unreachable"; 4 HTTP 404, empty body |
| TestReleaseRoot.test_finds_the_wrapper_folder | 3 "one wrapper folder with the repo prefix" |
| TestReleaseRoot.test_a_zip_from_somewhere_else_is_refused | 4 "zip with root Someone-Else-abc1234"; `[]` by 4 "valid zip with no entries" |
| TestShouldCopy.test_code_is_replaced | 6 "every file of v5.6.2 is in the copy byte for byte". `should_copy()` itself is not called by `install()` (it uses `keep`); no production caller |
| TestShouldCopy.test_local_things_are_kept | 6 "lib/, data/, cards/ kept" |
| TestShouldCopy.test_the_mining_sheet_is_replaced | 6 byte for byte, after a local edit to `mining_sheet.json` |
| TestInstall.test_puts_the_release_in_place | 6 "install_async installs the release" + byte for byte |
| TestInstall.test_the_release_sheet_replaces_the_local_one | 6 byte for byte, after a local edit to `mining_sheet.json` |
| TestInstall.test_a_directory_is_replaced_not_merged | 6 "stale file inside a replaced folder removed" |
| TestInstall.test_a_zip_from_somewhere_else_changes_nothing | 4 foreign root: refused + copy unchanged |
| TestInstall.test_a_truncated_download_changes_nothing | 4 truncated zip, 64 bytes flipped: refused + copy unchanged |
| TestInstall.test_no_temporary_folder_survives | 6 "no rs_update_ temp folder left" |
| TestInstall.test_no_temporary_folder_survives_a_failure | 4 "copy unchanged, no rs_update_ folder" (every file hashed) |

Added beyond the unit tests: zip checked blob for blob against `git ls-tree v5.6.2`;
updated plugin started in a subprocess (`plugin_start3`, mining sheet loaded);
live plugin folder and live `%LOCALAPPDATA%\RhinoSpotter` checked untouched.
`rs_tests/test_update.py` is not deleted by this change.
