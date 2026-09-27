# E2E: RhinoData right pane grows with the window

Harness: `rs_e2etest/resize_e2e.py`. One process, a withdrawn Tk root, the
real `scan.show` window over a copy of the live db (Aramo, a body with a
bookmark on a saved map). Output: `out/<timestamp>/report.txt`. No grabs:
widget widths are what is checked.

Asked 2026-09-27: maximised, the card pane and its map use the room; the rail
stays as it is; at the default size (`SCREEN_SHARE` of the screen) nothing
changes.

## Ways it can fail

- At the default size the card is not CARD_WIDTH or the map not MAP_PX.
- Smaller than default: the card shrinks below CARD_WIDTH.
- Maximised: the card and the map stay at 310 / 240 px.
- The map grows but the picked-bookmark diamond stays at the 240 px position.
- The map picture cache hands back the 240 px picture at the new size.
- The rail changes width.
- Every <Configure> redraws the whole window (a drag rebuilds hundreds of
  labels per pixel): must redraw once the size settles, and only when the
  card width changes.
- Back to the default size: the card goes back to 310 / 240.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| dragging the frame | `geometry()` then `update()` | the OS resize loop, a maximise button |
| a person looking | widget widths + a grab | whether the larger map reads better |

## Checks

1. Default size: rail RAIL_WIDTH, card CARD_WIDTH, map canvas MAP_PX.
2. Width x 1.6: card and map x 1.6 (+-2 px), rail unchanged.
3. Diamond on the wide map at the bookmark's scaled position (+-2 px).
4. Ten geometry steps in one burst: one `_draw`, not ten.
5. A height-only change: no `_draw`.
6. Back to default: 310 / 240 again.
7. Narrower than default (MIN_WIDTH): card CARD_WIDTH, map MAP_PX.
