# E2E: one RhinoSpotter per data folder, plugin side (rs_core/instance.py)

Harness: `rs_e2etest/lock_e2e.py`. Child processes call the real
`load.plugin_start3` / `plugin_app` / `plugin_prefs` / `journal_entry` /
`plugin_stop` on a bare Tk root, `LOCALAPPDATA` at `out/<timestamp>/`. The
standalone side (standalone.py refusing, the dialog) is tested on the
standalone branch in `standalone_e2e.py`; here the other holder is a child
that takes the lock as "RhinoSpotter standalone" through `instance.acquire`.
Output: `report.txt`.

## Ways it can fail

- The plugin starts without the lock, or the lock file does not name it.
- A second plugin (EDMC restarted while the old one still exits) refused at
  once instead of waiting up to `main.LOCK_WAIT_S` for the first to go.
- A plugin refused by a standalone holder waits `LOCK_WAIT_S` for nothing
  (only an older plugin is waited for).
- Refused, the plugin still builds the panel, takes hotkeys, handles journal
  lines or writes the db / a backup.
- Refused, `plugin_prefs` is not an `nb.Frame` (EDMC rejects the tab).
- `plugin_stop` does not release the lock; a killed holder keeps it.
- `adopt_legacy` skipped because the lock made the data folder first (Linux
  only; not reachable on Windows, where LOCALAPPDATA is set - not checked here).

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | a child calling load.py's hooks on a bare Tk root; `myNotebook` stood in by tkinter | EDMC's loader, its nb.Frame type check |
| standalone.py | a child holding the lock as "RhinoSpotter standalone" | the standalone's own start and dialog (standalone branch) |
| a crash | `TerminateProcess` on the holder | a hang that keeps the process alive |

## Checks

1. First plugin: lock file names "the EDMC plugin"; panel built.
2. Second plugin while the first runs: refused after ~LOCK_WAIT_S (4.5-8 s),
   naming the plugin; panel is the refusal line; prefs an nb.Frame with it.
3. Second plugin, first stops within LOCK_WAIT_S: the second takes the lock.
4. Standalone holder: plugin refused in under 2 s, naming it; no hotkey
   thread, journal_entry ignored (system stays empty), no backup written.
5. Killed holder: a new plugin takes the lock.
6. plugin_stop releases it: `instance.acquire` from the harness succeeds.
