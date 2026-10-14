# rigradar_e2e.py

Mouse press tracker (`rs_ui/press.py`) and rig radar (`rs_ui/rigradar.py`)
through `main.start` / `main.build`: the real press thread, `_on_ui`, Status.json
read from a scratch journal folder, the CSV, the radar window over a stand-in
Elite window (title `Elite - Dangerous (CLIENT)`). Refuses to run while the real
game is open: it takes the foreground back and sits under the click-through radar.

    python rs_e2etest/rigradar_e2e.py

Writes `rs_e2etest/out/<timestamp>/report.txt`, `presses.csv` (copy) and
`radar-*.png` grabs; exit 1 on a failure. `LOCALAPPDATA` points at the run
folder and `RHINOSPOTTER_DEBUG` is set before rs_core loads; the db starts empty.

Real input: `mouse_event` presses and releases the buttons with the cursor on
the stand-in (top left, clear of the radar) or, for check 8, on the harness
window; focus moves by the same clicks; the cursor is put back after. GetAsyncKeyState and everything after it
are the shipped code. Moves the mouse for about 40 s.

## Ways it can fail

| # | Check | Fails when |
|---|-------|-----------|
| 1 | 0.3 s right press in the SRV -> CSV row, rig 0, no radar | every click is a rig |
| 2 | 1.3 s right press -> rig 1, `ms` 1300 +-80, radar visible, right learned | threshold, thread, `_on_ui` or window broken |
| 2 | text `Next rig: drive 80 m on`, no border | distance from the wrong point |
| 2 | hide line `To hide: double click right mouse` | the close gesture is not on screen |
| 2 | 10 m raster: 25-26 lines each way | raster missing or wrong step |
| 2 | ring thin dashed ALERT while inside it | ring gives no "too close" cue |
| 3 | SRV 50 m north -> `drive 30 m on`; 90 m -> `OK here`, rings thick solid GOOD, no border | projection or poll broken |
| 4 | x centred on the game rect, y = top + max(24, 4%) + 190 + 8 | overlaps the guide arrow |
| 5 | second long press -> 2 rings, text from the nearest | rings replaced, not added |
| 6 | 1.3 s left press after right was learned -> row button left, rig 0 | a long hold on the scan button places a rig |
| 7 | Elite not in front -> radar hidden; back in front -> shown | radar over the desktop |
| 8 | long press with Elite not in front -> no CSV row, rings unchanged | clicks in other windows logged or counted as rigs |
| 9 | LaunchSRV `testbuggy` -> long press rig 0, rhino 0 | rigs from another SRV |
| 10 | radar ex-style has WS_EX_TRANSPARENT | radar eats game clicks |
| 11 | out of the SRV -> radar closed, rigs forgotten, press not logged | radar stays after docking |
| 12 | `main.stop()` -> press thread ended | thread left running at EDMC exit |
| 13 | no Tk callback exceptions during the run | an `after` callback raised and was swallowed |
| 14 | Settings `Rig radar` off: saved, open radar closed, long press neither logged nor a rig; on again: rig placed | toggle not wired |
| 15 | new session (`_rig_button` reset to None, as at EDMC start): long left press -> rig, left learned, hide line names left; long right -> rig 0 | players with deploy on the left button get no radar |
| 16 | double click on the other button, or two rig-button taps 1.0 s apart -> radar stays; double click on the rig button -> closed, rigs forgotten | radar cannot be put away, or closes on scans |
| 17 | `press.DEBUG` False (RHINOSPOTTER_DEBUG unset, as in a release): long press -> no CSV row, rig placed | a release writes trace files |
| 18 | Settings `Rig button` Mouse 2: saved `right`, long left -> rig 0, long right -> rig, hide line names right, `_rig_button` stays left, double click right closes; First long press: saved `""`, 0.6 s left -> rig | config ignored, or it overwrites the learned button |
| 0 | CSV under the run folder, live `trace\` untouched | harness writes live data |

## Not covered

- How long a rig deploy is held: one measured, right button, 3052 ms
  (`presses-20261013.csv`); scans 30-187 ms. 0.5 s `RIG_PRESS_S` sits between.
- Check 15 resets `_rig_button` by hand: a real EDMC restart is a new import.
- GetAsyncKeyState while Elite holds raw input: only the game can show it.
- The look over a real game frame; grabs are over the stand-in window.
