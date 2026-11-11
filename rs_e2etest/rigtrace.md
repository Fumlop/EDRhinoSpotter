# rigtrace_e2e.py - plan rigs from a driven border, guide to each

Run from the plugin folder: `python rs_e2etest/rigtrace_e2e.py`.
LOCALAPPDATA at `rs_e2etest/out/<timestamp>/`, `RHINOSPOTTER_DEBUG` cleared.
Output: `report.txt`. Input: `rs_e2etest/data/trace-20260929-095343.csv`
(a real lap, 91 fixes at 1 Hz, 3.1 m start-to-end, a known 4-rig spot).

Drives the real `rs_ui/tracelog.py`, `rs_ui/overlay.py`, `rs_core/rigplan.py`,
`rs_ui/press.py` -> `rs_ui/rigradar.py`, `rs_ui/hotkey.py` and `rs_ui/minimap.py`
with Status.json written into the run folder.

## Ways it can fail end to end

| # | Failure | Check |
|---|---|---|
| K1 | Keys still lab-only: not in Settings without `RHINOSPOTTER_DEBUG` | `hotkey.ACTIONS` names "Plan rigs (drive the border)", "Next rig" |
| K2 | Linux chat commands still lab-only | `!rs trace`, `!rs placed` |
| B1 | Trace CSV/TXT written for every user | no `trace/` folder after all laps |
| F1 | Lap never snaps shut | real lap closes by itself |
| F2 | Lap snaps before 60 m of driving | 40 m out-and-back stays open |
| F3 | Lap snaps on a near miss (> 10 m from start) | square ending 15 m off stays open |
| F4 | Key press does not close the lap / plan | toggle mid-lap closes and plans |
| F5 | Planner hangs or crashes in the worker thread | plan within 30 s |
| F6 | Spots closer than `rigplan.SPACING_M` (80 m) | every pair >= 79.5 m |
| F7 | Spot outside the outline | point-in-polygon |
| F16 | Known 4-rig spot planned with fewer | 4 rigs |
| F15 | Too-small outline guides nowhere silently | "no rig fits here / trace the whole border" |
| F8 | Overlay not guiding, no distance | target rig 1, metres text = guide.distance |
| F18 | Caption does not say what to do | "rig 1 of 4: place it here, or Ctrl+Alt+P to skip" |
| F10 / F11 | HERE outside 3 m / missed inside 3 m | 4 m: none, 2 m: HERE |
| F17 | Arrow moves on before a rig is down | HERE held past `HERE_MS` |
| G1 | A rig press far from the spot advances | 60 m off: step 0 |
| G2 | A rig press on another body advances | step 0 |
| G3 | A short press advances | 1 s press: step 0 |
| G4 | The rig placed in the game does not advance | 10 m off, 2.5 s: arrow on rig 2 |
| G5 | Advancing steals the press from the rig radar | radar holds the rig |
| F12 | Ctrl+Alt+P does not skip | arrow on rig 3 |
| F13 | Chain does not end after the last rig | plan empty, overlay down |
| F19 | Key or rig press with no plan misbehaves | nothing guides, nothing raises |
| M1 | Minimap does not name the key | 1080 px window: "Ctrl+Alt+R  plan rigs" right of the zoom row |
| M2 | Hint drawn over the zoom row on a small map | 720 px window (180 px map): hint dropped |

Not covered: what the game really writes (1 Hz on one lap), arrow pixels,
RegisterHotKey on EDMC's hotkey thread, the mouse polling thread in
`press.py` (released() is called directly), exclusive fullscreen, the
`RHINOSPOTTER_DEBUG` CSV/TXT content (was F14 in `lab/rigtrace_replay.md`).
