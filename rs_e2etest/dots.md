# E2E: bookmark dots - pale dot, hollow ring once depleted

Harness: `rs_e2etest/dots_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, an empty scratch db. Four bookmarks on one body written
with `spotcard.save`; two get tons through `yields.TALLY.refined` (the
MiningRefined path), one of them is marked with `cards.set_depleted`. The
dots are read back through `minimap._bookmarks` (minimap) and
`scan._map_marks` (card map, Share map) and drawn with `coverage.render` /
`coverage.picture`. Output: `report.txt`, `minimap.png`, `picture.png`.

Asked 2026-09-27: dots pale #b8d4f0 (FG_SOFT) whether mined or not; depleted a
hollow ring #8a96a3; the code letter FG for every dot, clear of the ring; no
credits label over a golden circle. Red against green is gone: red-green blind.

## Ways it can fail

- A depleted bookmark still red, or filled (the ring's centre not the ground).
- The ring's right edge covered by the code letter's 2 px BG stroke.
- A bookmark with tons this cycle drawn differently from an untouched one.
- The minimap and the card map disagree on depleted (two code paths build the tuple).
- The letter takes the dot's colour.
- Golden groups count a depleted bookmark.
- Leftover tons after Depleted turn the ring back into a dot.
- The gold credits label still drawn over a golden circle.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| the game | Status.json dict handed to `TALLY.refined` | Status.json torn reads |
| the minimap window | `coverage.render` on the tuples `minimap._bookmarks` returns | Win32 layered window, scaling |
| a person looking | pixel reads at the dots and rings | whether the ring reads on painted ground |

## Checks

1. `minimap._bookmarks`: depleted True for the marked one only; mined and untouched False.
2. `scan._map_marks` gives the same flags.
3. Untouched and mined dot centres: MARK. Depleted at 480 px and 240 px: centre
   not MARK_DEPLETED, a MARK_DEPLETED pixel radius - 3 .. radius px on both the
   left and the right of centre.
4. Letters: FG beside every dot; no dot or ring colour in the letter box.
5. Leftover ton after Depleted: still depleted.
6. Golden spots: the depleted bookmark left out; control: counted, the groups differ.
7. Share map picture with a golden group: no GOLD pixel above the circle
   (where the label was); control: GOLD on the circle itself.
