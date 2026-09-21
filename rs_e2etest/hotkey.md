# E2E: hotkeys (rs_ui/hotkey.py)

Harness: `rs_e2etest/hotkey_e2e.py`. Runs the real `rs_ui.hotkey` start /
restart / stop in its own Tk process: real `RegisterHotKey` on the
module's own thread, real `GetMessageW` loop, callbacks bounced to Tk through
the real `rs_ui.main._on_ui`. Output: `rs_e2etest/out/<timestamp>/report.txt`.
Replaces the unit tests in `rs_tests/test_hotkey.py`; mapping in
`coverage-hotkey.md`.

## Isolation: what the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC process | a plain `tk.Tk()` root, `main._frame` set to it | EDMC's mainloop being busy or gone when a press arrives; plugin_stop order (`hotkey.stop()` in `main.py` against Tk teardown) |
| `config` (EDMC config.toml) | a dict with `get_str` | EDMC's type coercion on read; a key stored by an older plugin version in another format |
| EDMC Settings dialog | `hotkey.restart()` called directly after changing the dict | `minimap.prefs_changed()` building the combo from the two OptionMenus, its `combo != label()` test, and the restart it triggers |
| a physical key press | (a) `PostThreadMessageW(WM_HOTKEY)` to the module's thread; (b) `SendInput` of the Ctrl+Alt default combos, only when a window of this process is foreground | keyboard layout effects: AltGr on a German layout is Ctrl+Alt, a physical AltGr+Z may arrive as a different vk; a keyboard hook (AutoHotkey, NVIDIA, Discord, Steam) eating the combo before `RegisterHotKey` sees it; MOD_NOREPEAT against a held key |
| the game having focus | this process's window foreground | Elite with focus, fullscreen or windowed; Elite running elevated or under a UIPI integrity level that blocks input to EDMC |
| another program holding a combo | a child python process that calls `RegisterHotKey` | a program that grabs the combo *after* EDMC started (the plugin then holds it; the other one fails, nothing to see here); a program that takes it with a low-level hook instead |
| live data `%LOCALAPPDATA%\RhinoSpotter` | `LOCALAPPDATA` = run folder | none: hotkey.py does not touch data |
| the user's session | whatever desktop the harness runs on | a locked workstation: `SendInput` goes nowhere, check 3 then fails |

## Ways the real thing can fail that no check here sees

- A combo taken by a hook-based program (not `RegisterHotKey`): the plugin
  registers it fine, logs nothing, and the press never arrives.
- The game binds the same combo: EDMC steals it, nothing says so (docstring
  of hotkey.py, Ctrl+Alt+M).
- Callbacks fire while EDMC's Tk is shutting down: `_on_ui` swallows it; not
  driven here.
- `stop()` joins for 1.0 s; a callback blocking the hotkey thread longer
  leaves the combos registered until it returns.
- `main._on_ui` swallows `RuntimeError` from `after()`; Tk raises it when the
  main thread is not in `mainloop()` (driven by `update()` only), so a press
  is dropped without a log line. The harness runs `mainloop()` on the main
  thread and the checks on a driver thread for this reason.
- `start()` waits 2.0 s for registration; a slower registration returns with
  `_thread_id` still None and a following `stop()` cannot post WM_QUIT.

## Checks

1. Defaults: all four combos held by the module after `start()` (probe:
   `RegisterHotKey` from a second thread fails with error 1409).
2. Dispatch: WM_HOTKEY posted to the module's thread, per key id: callback
   runs on `rhinospotter-hotkey`, the bounced function runs on the Tk thread.
3. Real press: `SendInput` Ctrl+Alt+<key> for each default -> the Tk function runs.
4. A callback that raises: logged, the loop keeps dispatching.
5. `start()` twice: second ignored, one thread.
6. `stop()`: all four free (probe succeeds), thread ended.
7. `restart()` with new combos in config: new ones held, old ones free.
8. Stored combos Settings could not offer: fall back to the default, held.
9. Every offered combo (4 modifier sets x 48 keys): bound to one action,
   restarted, the combo with the independent vk is held by the module or a
   warning names it as taken.
10. A combo held by another process: warning logged, no exception, the
    other three held and dispatching.
11. Two actions on one combo: warning, one of them holds it.
12. Live db untouched; no Tk callback exceptions.
