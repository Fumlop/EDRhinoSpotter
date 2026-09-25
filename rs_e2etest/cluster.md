# cluster_e2e.py - what it covers and what it hides

`python rs_e2etest/cluster_e2e.py`. LOCALAPPDATA pointed at `out/<timestamp>/`,
a sqlite backup copy of the live db. Real data: the location with the most
bookmarks (Aramo AB 1 a, loc 10, 21 on 2026-09-25).

## Ways it can fail, each checked

- A cluster member further than `GOLDEN_RADIUS_M` (1250 m) from its seed.
- A seed with fewer rigs than a later seed (clusters not most rigs first).
- A member with more rigs than an earlier member of its cluster.
- A worked-out bookmark (`depleted_at` or Amount Depleted) above a live one.
- A bookmark lost or doubled by the reorder.
- Golden groups that are not exactly the clusters of 5+ rigs.
- A golden circle wider than 1250 m.
- Fallback (`GOLDEN_RIGS_LOW` = 4): a map with no 5+ cluster must circle its
  4-rig clusters; a map with one 5+ cluster must not circle 4-rig ones.
  Checked on the location with the most bookmarks (has 5+) and on the first
  saved map whose best cluster holds exactly 4 rigs (Aramo AB 1 a map 2 on
  2026-09-25: 2+2). None found fails the run, not skips it.

- The card map above a bookmark (`scan._draw_location_map`) and Share map
  (`scan._map_marks`) circling different groups for the same saved map: the
  card map fed every bookmark on the body, so another map's 5-rig cluster
  kept this map's 4-rig fallback off. Both must draw the same groups.

## Settings: golden radius (`rhinospotter_golden_m`), each checked

- No key stored: the spinbox shows 1250 and `coverage.golden_m` is 1250.
- The spinbox offers exactly 500-2500 m in 250 m steps; its up arrow goes
  1250 -> 1500, no free typing.
- OK (`prefs_changed`) stores the value and applies it at once:
  `coverage.golden_m`, `clusters()` and `golden_groups()` on the densest
  location all use it (no member further than it from its seed).
- A stored value off the steps (1300) or not a number: 1250, not a crash.
- Start (`minimap.apply_golden`, called from `main.start`) applies a stored
  value before anything is drawn.
- Stand-ins, as in minimap_e2e: EDMC's `config` is a dict, `nb` is plain Tk;
  the real Settings dialog and EDMC's type coercion are not exercised.

## Artifact

- `report.txt`: the list in `scan._clustered` order - cluster, rigs, metres
  to the seed, material - and the golden groups before (git HEAD) and after.
- `<tag>-before.png`, `<tag>-after.png` (tag `densest`, `fallback`, `r1500`): the saved map picture with HEAD's and the new
  golden circles, for the eye.

## Not covered

- The RhinoData window itself: `_clustered` is called directly, not through Tk.
- Cr/h ranking of the golden groups: `golden_best` is unchanged.
