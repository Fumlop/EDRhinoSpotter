# E2E: minimap placing and topmost (5.6.0 - 5.6.2)

Harness: `rs_e2etest/minimap_e2e.py`. Runs the real `rs_ui.minimap` and
`rs_ui.overlay` in its own Tk process against the real desktop and the real
Elite window. Output: `rs_e2etest/out/<timestamp>/report.txt` plus screenshots.

## Isolation: what the harness replaces, and what that hides

The harness is not EDMC. Every substitution below is a way the real thing can
fail while the harness passes.

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC process | a plain `tk.Tk()` root | EDMC's own Tk version, DPI awareness, its theme; EDMC's main window being topmost and fighting the map |
| EDMC Settings dialog | a `tk.Toplevel` with `grab_set()`, like `prefs.py` | the real dialog's grab timing (`wait_visibility` then `grab_set`), its OK/Cancel/X paths, `prefs_changed()` order against the frame's `<Destroy>` |
| `config` (EDMC config.toml) | a dict with `get_str/get_bool/get_int/set` | type coercion EDMC does on read; the old `rhinospotter_minimap_pos` key still in the real config |
| live data `%LOCALAPPDATA%\RhinoSpotter` | `LOCALAPPDATA` = scratch folder, db copied from the live one | nothing about placing; map painting runs against the copy |
| Status.json from the game | `minimap.update()` fed a dict | the 1 s poll in `rs_ui/main.py`; a read landing mid-write |
| a mouse drag | `event_generate` on the canvas | Tk grab routing: generated events ignore the grab, so "Settings blocks the drag" is checked by `grab_current()`, not by a click |
| a second monitor | none, one 2048x1152 screen here | a position on a monitor left of or above the primary (negative coordinates); unplugging one |
| exclusive fullscreen Elite | none, Elite runs windowed | flicker or a mode switch when a window is raised over it every 5 s |
| journal dispatch | `minimap.srv_event()` called with the entry | `rs_ui/main.journal_entry` not forwarding it, or raising before line 430 |
| EDMC's `nb.Frame`, `nb.OptionMenu` | plain `tk.Frame`, `tk.OptionMenu` | `nb.Frame` grids a child of its own: a collision with it, or a pack/grid TclError, is not in the layout check |
| EDMC's OK button | `minimap.prefs_changed()` called, then the dialog destroyed | EDMC's call order; Cancel skipping `prefs_changed` |
| a dropdown pick | `menu.invoke("Q")` on the hotkey `OptionMenu` | the dropdown opening at all |
| hotkey registration | `hotkey.start()` never called, so `restart()` registers nothing | `RegisterHotKey` refusing the new combination (error 1409); the listener thread not coming back |
| `hotkey.config` | the same fake dict as `minimap.config` | EDMC coercing the stored combo |
| the debounced map write | 3 s of Tk pumping, then `coverstore.maps()` on the test db | a write racing EDMC's shutdown flush |
| a second SetWindowPos caller | none: the guide arrow shows only with Elite in the foreground, which takes input to get | two windows sharing one `_topmost_sent` entry |
| a failing SetWindowPos | none: a live window of the same process is not refused | the retry on the next tick; the logged error code |
| a map bigger than the monitor | none: the map side is capped at 640 px (`MAP_ZOOM_MAX_PX`), under the 1152 px screen | the clamp to the monitor's top left |

## Checks, and how each is judged

1. Place from Settings, not in the SRV: window built and visible, `_placing`
   True, Tk grab on the map, not on Settings.
2. Drag by 150 px: window moves 150 px.
3. Lock with Esc: grab back on Settings, click-through style back
   (`WS_EX_TRANSPARENT` set), map hidden (not in the SRV).
4. Position stored as screen pixels under `rhinospotter_minimap_xy`, Free
   move True.
5. Double-click without a drag stores nothing.
6. In the SRV (fed Status), Free move on: map at the stored pixels, not at
   the corner.
7. Free move off: map in the chosen corner of the Elite window.
8. Topmost: `WS_EX_TOPMOST` set after the first tick.
9. Demoted by `HWND_NOTOPMOST` behind Elite: back on top within 5 s + one
   tick, not before the interval unless moved.
10. Hidden then shown again: on top at once.
11. Settings destroyed while placing: `_lock` ran, no traceback.
12. Live db untouched: size and mtime of `rhinospotter.db` equal before and
    after.

Added when the unit tests in `rs_tests/test_minimap.py` and
`rs_tests/test_overlay.py` were retired (mapping: `coverage-minimap-overlay.md`):

0. Before any window: `place()` returns False, hint line says "no map
   window". Settings tab: every widget in a grid cell of its own, over 12
   cells; Free move unticked on a config without `rhinospotter_minimap_free`.
6. No LaunchSRV seen: taken as the Rhino, map shown.
9. No re-send inside the interval: a tick under 5 s after the last send
   leaves the demoted map not topmost.
14. Demoted, then moved (Free move, new position): on top and at the new
    pixels on the same tick.
15. Stored position `5000,5000`: clamped to the monitor's bottom right;
    `-800,-800`: top left; `""`, `left`, `10`, `10,20,30`, `a,b`: the corner.
16. LaunchSRV `testbuggy`: stored under `rhinospotter_srv_type`, map down,
    nothing saved for that body. DockSRV naming `mev_rhino` changes nothing.
17. LaunchSRV `mev_rhino`: map up, painted, saved to the test db.
18. Minimap switched off: map down, nothing saved for that body.
19. Hotkey picked in the dropdown, then OK: `rhinospotter_hotkey_*` holds
    the new combination, `hotkey.label()` returns it.
20. Settings closed without placing: no lock, stored position unchanged.
