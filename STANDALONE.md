# RhinoSpotter standalone

RhinoSpotter without EDMC. Users install `Standalone_RhinoSpotter-<version>-Setup.exe`
from the release (see README, Install). This file is for running and building
it from this branch.

## From source

    pip install pillow requests
    python standalone.py

Tested with Python 3.13 on Windows. One window: RhinoData, with the panel EDMC
shows (Location, Rigs, Material, Amount, Density, Bookmark) on its Bookmarks
tab, and a **Settings** button under it. It reads the newest journal and
Status.json in `Saved Games\Frontier Developments\Elite Dangerous` (wherever
Windows has Saved Games); another folder is picked in Settings, Journal folder.

Same data as the plugin; the two never run together (`rs_core/instance.py`).
No update check: install the next Setup.exe over it, or pull the branch.
Uninstalling leaves the data.

| What | Where |
|---|---|
| Settings | `%LOCALAPPDATA%\RhinoSpotter\standalone.json` (EDMC's are not read) |
| Log | `%LOCALAPPDATA%\RhinoSpotter\log\rhinospotter.log` |
| Lock | `%LOCALAPPDATA%\RhinoSpotter\db\instance.lock` |

## Build the Setup.exe

    python installer/build.py
    python rs_e2etest/installer_e2e.py

`build.py` makes `installer/.venv` from `installer/requirements.txt` (pinned)
and needs Inno Setup 6. The Setup.exe goes on the main release as
`Standalone_RhinoSpotter-<version>-Setup.exe` (edmc.md, step 5).

## Branch

`standalone` = `main` + the files only the standalone uses: `standalone.py`,
`rs_standalone/`, `installer/`, `rs_e2etest/standalone*`, `rs_e2etest/installer*`,
this file. Shared code (the lock, `scan.host`) lives on `main`. Before a
release: merge `main` in, run `standalone_e2e.py` and `installer_e2e.py`.

## Files

```
standalone.py        the plugin without EDMC
rs_standalone/       what EDMC provides, for standalone.py
installer/           Setup.exe: build.py (PyInstaller + Inno Setup), RhinoSpotter.iss
```

- **standalone.py** - the non-EDMC entry. Puts `rs_standalone/config.py` in
  `sys.modules["config"]` and tkinter in `sys.modules["myNotebook"]` before
  rs_ui loads, so rs_ui runs unchanged. The Tk root is the RhinoData window
  (`scan.host`); the panel `main.build` makes is packed on its Bookmarks tab
  with a Settings button (a Toplevel with the Journal folder row and
  `main.prefs`; OK is `main.prefs_changed`, a new folder restarts the tail via
  `paths.forget`). Redraws the window when `len(register)`, `register.system`
  or `database.revision()` move (1 s). No update check.
- **rs_standalone/config.py** - EDMC's `config` interface
  (get_str/get_bool/get_int/get_list/set/delete) over `standalone.json`,
  rewritten through `atomic` on every change. Also `journaldir`, read by `paths`.
- **rs_standalone/journal.py** - the journal_entry feed: newest
  `Journal.*.log` by ctime, caught up at start without delivering, then a
  synthesised `StartUp` unless the file ends in `Shutdown`; polled every 1 s,
  a new file read after the old one is drained. State kept: cmdr, system,
  SystemAddress, Body, BodyID (what main.journal_entry and bodies read).
- **rs_e2etest/standalone_e2e.py** - standalone.py on a fake Saved Games folder:
  catch-up and StartUp, appended lines, a half line, rotation, Status.json,
  Bookmark, SRV map, hotkeys, Settings (materials, Journal folder), the docked
  panel; the lock between two standalones, a killed one, and the EDMC hooks.
- **rs_e2etest/installer_e2e.py** - the built Setup.exe installed silently into
  the run folder, the installed exe run on test data, uninstalled; nothing
  bundled from outside the venv.

## Changes (not yet in a release)

- Settings: Journal folder (Browse..., Default); the tail moves to it on OK, no restart.
- Fixed: crashed at start on 5.8.0+, its config had no get_list/delete.
- Journal feed keeps only what the plugin reads (cmdr, system, body ids).
- Setup.exe built from a pinned venv: 18.7 MB, was 28 MB with numpy, psutil, pywin32, yaml.
