# diamond_e2e.py - what it covers and what it hides

`python rs_e2etest/diamond_e2e.py`. LOCALAPPDATA at `out/<timestamp>/`, a
sqlite backup copy of the live db. `scan._location_map` called for real on
the location with the most bookmarks, into a withdrawn Tk frame.

## Ways it can fail, each checked

- No diamond on the card map for the picked bookmark.
- Diamond off its dot: its centre not on the pixel `coverage.picture` drew the
  bookmark's dot at (the pixel under it on the picture is not the dot colour).
- Picking another bookmark on the same map re-renders the picture (the cache
  entry `_map_picture` must stay the same object) or leaves the diamond where
  it was.
- Diamond not blue (`ACCENT`) or not outlined in `BG`.
- A bookmark on no saved map: no canvas at all (map_at only returns maps
  reaching within +-10 km, the picture's whole extent, so a diamond off the
  canvas cannot happen otherwise).

## A pick in the list (`scan._pick_record`), each checked

- The whole window rebuilt (it flickered): `_draw` called, or the rail's and
  the list's widgets replaced. Only the card pane's children may change.
- The old row still lit, or the new one not lit (PANEL background, ACCENT
  strip).
- The card, and the diamond on its map, not on the new bookmark.
- A row that is not drawn (folded away meanwhile): falls back to `_draw`.
- Printed: `_draw` time and pick time.

## Artifact

- `report.txt`: per pick, the diamond's centre and the picture's pixel there.

## Not covered

- The RhinoData window's layout around the card map: only the map is built.
