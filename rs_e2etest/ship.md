# E2E: minimap in the ship over a mapped hotspot (#16)

Harness: `rs_e2etest/ship_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, the real `minimap.update` fed Status.json dicts, a
stand-in game window as in minimap_e2e (Elite in front). Output:
`report.txt`. No grabs: visibility is read with IsWindowVisible.

Asked 2026-09-27 (issue #16): a Settings switch, off by default. In the ship,
under 2 km altitude, the map of the location is shown with the ship's
position; nothing is painted or saved. Above 2 km or off the map it goes away.

## Ways it can fail

- Shown in the ship with the switch off (the default).
- Painted from the ship: `coverage.version` moves, the mask changes, a
  launch is recorded, or a write reaches the map file.
- A new, empty map created for a body with no saved map (a map of nothing
  over the hotspot).
- Shown above 2000 m altitude, or with no altitude in Status.json.
- Shown on an Altitude from the average radius (Flags AltitudeFromAverageRadius,
  glide / orbital cruise): not height over the ground.
- Shown once the ship is off the map (`reaches` false).
- Shown on foot, or in the SRV path taken from the ship branch (the SRV must
  still paint).
- Right after docking the SRV, the map goes down (the case the request is
  about): the SRV's map must stay up in the ship.
- After a restart (no map in memory) the saved map of the body is not found.
- The switch not stored by Settings OK (`prefs_changed`).
- The marker not moving with the ship (the map drawn once and frozen).

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| the game | Status.json dicts | real Flags combinations in flight (supercruise, glide) |
| Elite's window | a Tk stand-in titled like the game | the game's own z-order |
| EDMC config | a dict stand-in shared with overlay | EDMC's own settings storage |

Known, not covered: the map over the main menu after a disconnect
(plan/todo.md, Next). A stale in-ship Status.json under 2 km over a map is a
second way into it once the switch is on.

## Checks

1. Switch off: ship at 500 m over the SRV's map: not shown.
2. Switch on (via `prefs_changed`): stored under `rhinospotter_minimap_ship`.
3. SRV drives 3 fixes (paints), docks: ship at 30 m on the same spot: shown,
   same map, `version` and launches unchanged after 5 ship fixes.
4. Ship moves 1 km: marker (drawn state) moves; still not painted.
5. Ship at 2100 m: down. Back at 1900 m: up. No Altitude: down. 500 m with
   AltitudeFromAverageRadius: down.
6. Ship 12 km off the map: down.
7. Fresh process state (`_coverage` None), ship over the saved map: shown, from
   the saved file; no new map file written.
8. Ship over a body with no saved map: not shown, no map file created.
9. On foot (Flags2 OnFoot) at the spot: not shown.
10. SRV again after the ship: paints (`version` moves).
11. Control: with `ship_fix` returning None, check 3 fails.
