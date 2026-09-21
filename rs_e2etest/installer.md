# E2E: the standalone installer

Harness: `rs_e2etest/installer_e2e.py`, run after `python installer/build.py`.
Installs the built `installer/dist/RhinoSpotter-<version>-Setup.exe` silently
into the run folder, starts the installed `RhinoSpotter.exe` against a test
data folder and a fake journal folder, checks it, stops it, uninstalls it.
Output: `rs_e2etest/out/<timestamp>/report.txt`, `install.log`, a screenshot.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| a player's PC | this machine, which has Python 3.13 + Pillow installed | a DLL the exe needs that only a machine with Python happens to have (the frozen app carries its own; not proven on a clean Windows) |
| the setup wizard | `/VERYSILENT /NOICONS /DIR=<run folder>` | wizard pages, the licence page, the Start menu shortcut, the "Start RhinoSpotter" box |
| SmartScreen / Defender | nothing: a locally built file carries no Mark of the Web | the "unrecognised app" warning a downloaded unsigned Setup.exe gets |
| the live data folder | `LOCALAPPDATA` pointed at the run folder for the app | an install beside a running EDMC plugin on the same data (the lock; covered by `standalone_e2e.py`) |
| the game | a journal file and Status.json written by the harness, `journaldir` in `standalone.json` | the game's own file timing |
| Windows uninstall bookkeeping | the real HKCU uninstall key, written by the installer and removed by the uninstaller | nothing; this one is real and is checked gone afterwards |

Writes outside the run folder: the HKCU uninstall key for the length of the
run. `/NOICONS` keeps the Start menu folder from being made.

## Checks

1. Setup exits 0 and puts `RhinoSpotter.exe` and `_internal\texture` in the target folder.
2. The installed exe starts, holds `db\instance.lock` in the test data folder and logs `standalone: started`.
3. A visible window of that process within 20 s.
4. The journal is read: the fake commander's system reaches the log or the db.
5. Status.json in the SRV: `minimap: built` in the log (texture and sheet load from the bundle).
6. No `Traceback` and no missing texture or sheet in the log.
7. Uninstall exits 0, the exe is gone, the uninstall key is gone.
8. Nothing written to the live `%LOCALAPPDATA%\RhinoSpotter` (no `standalone.json`, no `instance.lock`).
