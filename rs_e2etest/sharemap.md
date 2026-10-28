# E2E: Share map draws the bookmarks of the system on screen

Harness: `rs_e2etest/sharemap_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, an empty scratch db. One body cached with `store.save`,
three bookmarks on it with `spotcard.save`, one map saved with
`coverstore.save`. The real `scan.show` window on a withdrawn Tk root; the
Share map button pressed with `invoke()`; `scan._open_card` replaced to record
the path instead of opening a viewer. Run from the plugin folder:
`python rs_e2etest/sharemap_e2e.py`. Output: `report.txt`, `<case>.png`.

Reported 2026-10-23: Share map opened a map with no bookmarks. `_drawn_now`
read the system from `_scan[0]` (the live register): `_scan[0]` is falsy when
it holds no bodies (`Register.__len__`), and it is the wrong system while a
searched one is shown.

## Ways it can fail

- The live register has no bodies: system None, no bookmark drawn.
- A searched system shown, live register in another system: that system's bookmarks read, none on this body.
- The press opens nothing (draw raised, no saved PNG to fall back on).
- The press opens an older saved PNG instead of a fresh draw.
- The dots drawn at the wrong place, or the legend left out.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| the journal | `Register.adopt` / an empty `Register` with `system` set | registers built from live events |
| the image viewer | `_open_card` records the path | os.startfile failures |
| a person looking | centre pixel = `coverage.MARK` per bookmark, legend row count | dots hidden under a golden circle |

## Checks

Per case: `live` (control, register holds the body), `browsed-empty` (live
register in another system, no bodies), `browsed-other` (live register in
another system with one body).

1. The Share map button is enabled and the press opens a path.
2. The opened PNG was written by this press (mtime after the press began).
3. The centre pixel of each of the 3 bookmarks is `coverage.MARK`.
4. The legend has 3 rows (`minimap.picture_text` on the shown system).

Control: a picture of the same map with no marks has no `MARK` at those 3 centres.
