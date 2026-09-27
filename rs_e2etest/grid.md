# E2E: the 1 km grid in dim yellow

Harness: `rs_e2etest/grid_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`. A `coverage.Coverage` painted by `add()` fixes, drawn
through `Coverage.layer` (the minimap) and `coverage.picture` (Share map, card
map). Output: `report.txt`, `minimap.png`.

Asked 2026-09-27: the grid in the RULE colour did not read on the driven area.
Dotted 1 km circles round the centre were tried and dropped; the square grid
stays, in dim yellow (`coverage.GRID`, 31.5% from BG to WARN; 45% was too much).

## Ways it can fail

- Grid still in RULE, or in full WARN (the mask edge's colour).
- Grid invisible on the driven area (too close to FILL).
- Minimap yellow, Share map still RULE (two code paths).
- Grid lines moved (no longer every GRID_M, pinned to the centre).

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| the SRV driving | `Coverage.add` on computed fixes | none for drawing |
| a person looking | pixel reads on the grid lines | whether 45% reads against every ground texture |

## Checks

1. Minimap layer: pixels on the 1 and 3 km grid lines, outside the driven area, are GRID.
2. On the driven area the 1 km grid line differs from FILL by more than 40 (sum of channels).
3. `coverage.picture`: the 3 km grid line is GRID.
4. No RULE pixel on those grid lines anywhere; GRID differs from WARN.
5. Lines at every 1 km, pinned to the centre after `recenter()` 500 m east.
