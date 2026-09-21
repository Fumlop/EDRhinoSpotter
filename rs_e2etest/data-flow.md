# E2E: data flow - migrate, replay, rs_api

Harness: `rs_e2etest/data_e2e.py`. Replaces `rs_tests/test_migrate.py`,
`rs_tests/test_replay.py`, `rs_tests/test_api.py`. Output:
`rs_e2etest/out/<timestamp>/report.txt`, one folder per scenario, one log file
per plugin process. Unit test -> check mapping: `coverage-data.md`.

One harness, not three: the three modules share one file,
`db\rhinospotter.db`. `replay.main()` calls `migrate.run()` before it writes;
`rs_api` reads what migrate, replay and the plugin wrote, from another process.
The failures that matter are at those hand-offs.

## Flow under test

    old JSON tree --plugin_start3--> migrate.run() --> rhinospotter.db
    journal copies --python -m rs_core.replay [--rebuild|--testmode]--> rhinospotter.db
    rhinospotter.db --separate python process, sys.path.append + import rs_api--> dicts

Every scenario runs in its own process with its own `LOCALAPPDATA`, set in the
environment before the interpreter starts, so `database.ROOT`,
`coverstore.ROOT` and `spotcard.CARDS_ROOT` point into the run folder.

## Inputs

| Input | Source |
|---|---|
| database | copy of the live `db\rhinospotter.db` (+ `-wal`, `-shm`, `migrate.done`) |
| journals | copies of the user's `Journal.*.log` from the last 7 days, mtime kept, plus `Status.json` and one journal older than the window |
| old JSON tree | written from the live db copy in the 4.1 layout: `data\<System>.json`, `cards\<System>\*.json` (+ PNG siblings), `coverage\<Body>\map N.json[.gz]` |
| broken inputs | truncated JSON, `{not json`, bad gzip, version 0, a list where `rigs` goes, a body without a name, a truncated journal line, invalid UTF-8 bytes in a journal |

## Substitutions, and what each hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC process | `load.plugin_start3(plugin_dir)` in a bare `python` | EDMC's logger handlers; EDMC's plugin load order; another plugin that imports `rs_api` before RhinoSpotter's folder is on `sys.path` |
| `coverage.clear_old_textures()` inside `main.start` | no-op | deletion of `texture\*.png` in the plugin folder (skipped: the harness deletes no plugin files) |
| EDMC logger | a `logging.FileHandler` per process on `RhinoSpotter` | message format EDMC writes; a warning that only reaches EDMC's log |
| "Delete migrated JSON" button | `minimap._delete_migrated(frame, label)` with `messagebox.askyesno` returning True | the Settings dialog, the real Yes/No click, the label layout |
| another EDMC plugin | a separate `python -c` that does `sys.path.append(plugin); import rs_api` | EDMC's embedded interpreter; Linux paths |
| a second program holding the db | a child process with `PRAGMA locking_mode=EXCLUSIVE` and an open write | antivirus or backup software opening the file without sqlite (share-mode lock) |
| a crash mid-write of a journal | a truncated line appended to a journal copy | the game writing while replay reads the same file |

## Ways the real flow fails that the harness cannot see

migrate
- `migrate.done` cannot be written after the commit (disk full, ACL): not
  reproducible without mocking `atomic.write_text`; the meta-row recovery is
  checked only via a marker that is moved away.
- A folder that cannot be listed: checked by an ACL deny on `cards\` via
  `icacls`; a network drive or OneDrive placeholder that fails differently is not.
- Old JSON written by versions other than the fixture layout (pre-4.1 keys,
  cp1252 files) - fixtures come from what the db holds now, not from real 4.1 files,
  which are gone from this machine.
- Two EDMC instances starting at once, both importing.
- A db of a newer schema (`user_version` > 2).

replay
- EDMC's live replay of the journal it watches (plugin `journal_entry`) - replay
  here only runs its own CLI.
- Journals in another folder resolved by `paths.journal_dir()` from EDMC's
  `monitor.currentdir`: `--root` is always given.
- Scores against `mining_sheet.json` are checked for order only; the numbers
  move when the sheet is regenerated.
- A journal file still being written by a running game.

rs_api
- A reader holding a read transaction open for a long time (WAL growth,
  checkpoint starvation on the plugin side).
- A read-only medium or folder: `mode=ro` on a WAL db needs to create `-shm`.
- Python versions other than 3.13 in the other application.

All
- Any Windows-specific file locking beyond sqlite's own locks.
- Performance: no timing is asserted except the 5 s sqlite timeout under a lock.
