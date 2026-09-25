# E2E: data root off Windows, old ~/RhinoSpotter copied once

Harness: `rs_e2etest/datahome_e2e.py`. Each scenario is a fresh Python process
with its own environment, so each is a start. Output:
`rs_e2etest/out/<timestamp>-datahome/report.txt` plus one plugin log per process.

The complaint (issue #9, Flatpak EDMC on Bazzite): bookmarks gone after a
restart. The database was `~/RhinoSpotter/db/rhinospotter.db`, outside the
Flatpak app folder. Linux now uses `$XDG_DATA_HOME/RhinoSpotter`; Flatpak sets
`XDG_DATA_HOME` to `~/.var/app/io.edcd.EDMarketConnector/data`.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| Linux | Windows Python with `LOCALAPPDATA` removed from the environment, `USERPROFILE` (what `expanduser("~")` reads on Windows) set to the run folder | POSIX `HOME` handling; a Flatpak that does not set `XDG_DATA_HOME`; sandbox write permissions |
| `rs_ui.main.start` | `database.adopt_legacy()` then `migrate.run()`, the order `main.start` calls them (grep `rs_ui/main.py`) | something opening the database before `main.start` |
| EDMC's `config` / `myNotebook` | absent: `rs_ui.minimap` falls back to `None` | the Settings button wiring to `_open_folder` |
| `os.startfile` missing | `del os.startfile` in the child | - |
| `xdg-open` | `webbrowser.open` replaced with a recorder | whether the desktop's `xdg-open` opens a file manager or a browser |
| `ctypes.windll` missing | `del ctypes.windll` in the child | X11/Wayland click-through (not implemented) |

## Checks

1. `LOCALAPPDATA` set: `database.ROOT`, `coverstore.ROOT`, `spotcard.CARDS_ROOT` under `%LOCALAPPDATA%\RhinoSpotter` (Windows unchanged).
2. No `LOCALAPPDATA`, `XDG_DATA_HOME` set: all three under `$XDG_DATA_HOME/RhinoSpotter`.
3. No `LOCALAPPDATA`, no `XDG_DATA_HOME`: under `~/.local/share/RhinoSpotter`.
4. Old `~/RhinoSpotter` with a bookmark row and a coverage PNG, no new root: after start the bookmark reads from the new root, the PNG is there, the old folder's files are byte-identical, one info line logged.
5. Second start with the new root present: no copy; a bookmark added to the old db meanwhile does not appear.
6. `LOCALAPPDATA` set and `~/RhinoSpotter` present: nothing copied.
7. Copy fails (a file named `RhinoSpotter.tmp` blocks it): nothing copied, one warning saying "copy it by hand". The start then creates an empty new root, so the next start does not retry and logs nothing.
8. No `os.startfile`: "open folder" hands `file://<coverage root>` to `webbrowser.open`, no warning.
9. No `ctypes.windll`: `overlay._click_through` logs no warning.
10. `rs_api.bookmarks()` before the first plugin start (a companion tool started before EDMC): returns `[]` and does not create the new root (`mode=ro`), so the next start still copies.
