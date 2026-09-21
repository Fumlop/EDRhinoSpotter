# E2E: standalone (standalone.py, rs_standalone/, rs_core/instance.py)

Harness: `rs_e2etest/standalone_e2e.py`. Part A runs the real `standalone.py`
app in the harness process: real Tk root drawn as the RhinoData window (`rs_ui.scan.host`) with the
panel from `rs_ui.main.build` docked on its Bookmarks tab,
real `rs_standalone.journal` tailing a fake Saved Games folder, real
`main._poll_landed` reading the fake Status.json, real database under the run
folder. Part B starts `standalone.py` and the EDMC hooks in `load.py` as child
processes for the lock. Output: `rs_e2etest/out/<timestamp>/report.txt`.

`LOCALAPPDATA` = `<run>/localappdata`, `USERPROFILE` = `<run>/profile`, so the
journal folder is the default path under the run folder. Real journals are
read from the user's Saved Games folder and copied; nothing is written there.

## Isolation: what the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| the game writing the journal | the harness appending lines to a copied journal, and creating a new `Journal.*.log` for rotation | the game holding the file open with a share mode that blocks reads (EDMC reads the same way, so unlikely); a line flushed in two writes across a poll (covered only by the half-line check); ctime ordering on a file restored from backup |
| the game writing Status.json | the harness rewriting it whole with `os.replace` | a read landing mid-write (spotmark handles it; rs_tests/test_spotmark covers the parse, not the timing) |
| the game running | `Shutdown` absent from the newest journal | the process check EDMC does: a crashed game without `Shutdown` gets a `StartUp` here and none in EDMC |
| EDMC's config.toml | `standalone.json` | nothing on the standalone side; EDMC's own type coercion is not exercised |
| a physical hotkey press | none: registration checked by probing `RegisterHotKey` from the harness; dispatch covered by hotkey_e2e | the standalone Tk loop receiving a press from the hotkey thread (same `main._on_ui` path hotkey_e2e drives) |
| the Elite window | none | minimap and guide arrow placement over the game; the minimap is checked through its state and the saved map row, not on screen (minimap_e2e covers the window) |
| the user clicking OK in Settings | the harness invoking the OK button | keyboard focus and window stacking of the Settings Toplevel |
| a second instance started by the user | a child `python standalone.py` | a double-click launch through `pythonw` (no stderr; the messagebox is the only message) |
| EDMC loading the plugin | a child process calling `load.plugin_start3` and `load.plugin_app` on a bare Tk root | EDMC's own plugin loader, its `nb.Frame` type check on `plugin_prefs`, EDMC's log handler |

## Ways the real thing can fail that no check here sees

- Two data folders: the lock is per `%LOCALAPPDATA%\RhinoSpotter`; an EDMC
  run under another Windows user is not seen, and does not share the data.
- A live EDMC with a plugin older than this branch takes no lock: standalone
  and that plugin can run together on the same db.
- `pythonw standalone.py` refused: the messagebox is the only trace besides
  the log file; no console.
- The journal folder moved in EDMC Settings: standalone does not read EDMC's
  `journaldir`; it needs `journaldir` in `standalone.json`.
- Journal files larger than memory: catch-up reads the newest file line by
  line on the Tk thread at start; a 50 MB file blocks the window for that read.
- The dock is unmapped and mapped again on every redraw: a redraw while
  typing in Location or with a dropdown open takes the keyboard focus away.
  The harness checks the dock is packed after redraws, not typing across one.
- Spansh and the update check hit the network; the harness runs with the
  update check off (as standalone does) and does not honk.

## Checks

1. Start: lock file holds "RhinoSpotter standalone"; log file under `log\`.
2. Catch-up: nothing dispatched from the existing lines; one synthesised
   `StartUp`; `main._system` and the register name the file's last system; cmdr from the file.
3. Appended `Scan` of a landable body: panel count label reads "N landable";
   the body row reaches the db after the 2 s debounce.
4. A half line is not dispatched until its newline arrives.
5. Rotation: a new journal with Fileheader, LoadGame, Location in another
   system -> `main._system` moves; lines left in the old file are dispatched first.
6. Status.json on the ground -> Bookmark enabled within 2 s; docked -> disabled.
7. Bookmark press with a material -> a bookmark row in the db.
8. LaunchSRV (mev_rhino) + Status.json in the SRV -> minimap in the SRV and
   painting; SRV docked -> the map row in the db.
9. Hotkeys: the four combos held while standalone runs, free after stop
   (skipped per combo when another process already held it before the run).
10a. Dock: the panel is packed inside the middle pane on the Bookmarks tab,
    with and without bodies; gone on the Mapped tab; the same widget objects
    after a redraw (not rebuilt).
10. Settings: window opens with the minimap tab widgets; toggling the
    materials switch and OK writes `rhinospotter_low_value` to standalone.json
    and refills the Material menu.
11. Stop: lock released, db backup written.
12. Lock, standalone first: a second `standalone.py` exits 1 with the holder in
    its message and a visible dialog.
13. Lock, standalone killed: a new one starts (the OS dropped the lock).
14. Lock, plugin first: `load.plugin_start3` holds it; `standalone.py` refuses naming the plugin.
15. Lock, standalone first: `load.plugin_start3` + `plugin_app` in a child
    show the refusal in the panel, take no hotkeys, write nothing.
16. Live data untouched: no `standalone.json` or `db\instance.lock` in the live folder, no
    `E2E Rotated System` row in the live db (size/mtime reported only: a running EDMC writes it).
