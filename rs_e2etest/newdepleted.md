# E2E: a new bookmark saved at Amount Depleted is greyed on the maps

Harness: `rs_e2etest/newdepleted_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, the real `main.start` + `main.build` panel and `scan.show`
window on a withdrawn Tk root, a Status.json in a scratch journal folder
(`paths.journal_dir` pointed there). The new bookmark goes through
`main.make_card`, Set active through the card's own button (`invoke()`), the
maps through `minimap._bookmarks` and `scan._map_marks`, drawn with
`coverage.render`. Run from the plugin folder:
`python rs_e2etest/newdepleted_e2e.py`. Output: `report.txt`, `minimap.png`.

Reported 2026-10-17: depleted fields scouted and bookmarked new with Amount
Depleted were not greyed on the map. `_render_card` saved a new spot without
`depleted_at`; the maps and the card button read only `depleted_at`.

## Ways it can fail

- New bookmark at Amount Depleted saved without `depleted_at`.
- `depleted_at` not the `marked_at` of the mark (a later or unparsable date).
- Bookmarks already saved that way (no `depleted_at`) stay un-greyed.
- Backfill stamps an old one (over 14 d) instead of letting `regrow()` lift it.
- Minimap and card map disagree on the flag.
- Dot drawn filled instead of the hollow MARK_DEPLETED ring.
- Set active comes back as depleted at the next `regrow()` (Amount still Depleted).
- A new bookmark at any other Amount gets `depleted_at`.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | `main.start` + `main.build` on a bare root | EDMC's theme |
| the game | Status.json on the ground | Status.json timing |
| bookmarks saved before the fix | rows written with `spotcard.save`, no `depleted_at` | other shapes of old data |
| the minimap window | `coverage.render` on `minimap._bookmarks` tuples, pixel reads | Win32 layered window, scaling |

## Checks

1. Panel Amount Depleted, new spot, `main.make_card`: row has `depleted_at` equal to `marked_at`.
1b. Panel Amount High, new spot: no `depleted_at`.
2. Old-shape rows (Amount Depleted, no `depleted_at`): 2 d old gets `depleted_at` = `marked_at` from `regrow()`; 20 d old is lifted (Amount None, `regrown` entry), not stamped. A second `regrow()` lifts nothing and leaves both rows as they were.
3. `minimap._bookmarks` and `scan._map_marks`: depleted True for the new and the 2 d one, False for the 20 d one and the High one.
4. `coverage.render` at 480 px: the new one is a hollow MARK_DEPLETED ring.
5. Card button on the new one reads Set active; pressed: `depleted_at` gone, Amount None; `regrow()` after: still not depleted.
