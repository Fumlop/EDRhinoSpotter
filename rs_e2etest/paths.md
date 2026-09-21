# E2E: journal folder found after a move

Harness: `rs_e2etest/paths_e2e.py`. Each scenario is a fresh Python process,
so each is a start. It imports `rs_core.paths`, `spotmark` and `replay`
directly, not `load.py` -> `rs_ui.main`; no module there takes a path at
import (grep: `journal_dir` is only called inside functions).
Output: `rs_e2etest/out/<timestamp>/report.txt`.

The complaint: a commander moved the Saved Games folder, and the plugin found
neither Status.json nor the journals. Cause: `spotmark.STATUS_PATH` and
`replay.JOURNAL_DIR` were fixed at import, and EDMC loads plugins about 1.4 s
before its monitor starts (debug log, 2026-09-21: plugin 19:19:31.992, monitor
19:19:33.426), so the answer was the `%USERPROFILE%\Saved Games` fallback.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC's `monitor` | a module in `sys.modules` with `monitor.currentdir`, None until "started" | EDMC changing the attribute name, or setting it later than the first poll |
| EDMC's `config` | a module with `get_str("journaldir")` and `default_journal_dir` | EDMC's own known-folder code; a `journaldir` that is not a string |
| a moved Saved Games folder | a folder in the run folder given as EDMC's default | Windows redirection itself: the real known folder is only compared with the registry, never moved |
| the game | Status.json and a journal file written by the harness | the game writing Status.json mid-read. If the bug came back, check 1 would read the real `%USERPROFILE%` Status.json (read only) and fail on its body name |
| `load.py` -> `rs_ui.main` | direct `rs_core` imports | a module-level path taken in `rs_ui` or `load.py` |
| an unmoved Saved Games | this machine's: not moved, so the known folder and `%USERPROFILE%\Saved Games` are equal; check 4 asserts the known-folder call answered | a folder redirected by Explorer |

## Checks

1. Plugin imported with the monitor not started: Status.json read from EDMC's
   default folder (the moved one), not `%USERPROFILE%\Saved Games`.
2. Monitor starts on another folder: the next read follows it, no restart.
3. `journaldir` set in EDMC's settings wins over the default.
4. Outside EDMC: the Saved Games known folder, equal to the registry's
   `User Shell Folders\{4C5C32FF-...}` value, expanded.
5. `replay.journal_files()` without a root finds the journal in the moved folder.
6. `journal_dir()` with the monitor started: under 5 us a call.
7. Looked up once a start: once the monitor's answer is kept, a later change
   of `currentdir` is not read.
