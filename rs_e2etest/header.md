# header_e2e.py - what it covers and what it hides

`python rs_e2etest/header_e2e.py`. One child process, LOCALAPPDATA at
`out/<timestamp>/` (empty db), `load.plugin_start3` + `main.build` on a
withdrawn Tk root, bookmarks written with `spotcard.save`, `scan.show` with the
real `mining_sheet.json` (`main._sheet`), window at -4000,-4000. The location
line is read back from the Tk labels: the "N deposits  ·  ..." label in the
row whose loc label is "loc N". Output: `report.txt` with the PASS/FAIL lines
and every location line as drawn.

Request (2026-10-15): a location line named one material per bookmark (6
Iridium bookmarks: "Iridium, Iridium, ..."). It is to name the 3 most valuable
materials, each once.

## Ways it can fail, each checked

1. A material bookmarked 6 times is named more than once (loc 4: 6 Iridium +
   1 Gold -> "Iridium, Gold").
2. The deposit count drops with the names: loc 4 must still read "7 deposits".
3. Ranked by rigs (row order) instead of Cr/t: loc 5 Silver 8 rigs, Gold 5,
   Platinum 3, Iridium 1, Osmium 2 -> "Iridium, Platinum, Osmium"
   (sheet: 181146 / 58486 / 46408 Cr/t; Gold 44707 and Silver dropped).
4. More than 3 names (loc 5 has 5 materials).
5. Same material in two casings ("iridium", "Iridium") named twice (loc 7).
6. Unpriced materials (Bauxite, a name the sheet lacks) placed above a priced
   one, or their tie not in row order: loc 6 Bauxite 6 rigs, Zzzite 2, Silver
   1 -> "Silver, Bauxite, Zzzite".
7. mining_sheet.json missing (`grounds.Sheet` on a path that does not exist,
   `.loaded` False, `values()` {}): raises or repeats names. Redrawn: loc 4
   -> "Gold, Iridium" (row order, Gold 7 rigs first), loc 5 -> "Silver,
   Gold, Platinum".
8. "worked out" suffix lost: loc 4 with one Iridium `depleted_at` set.
9. The check reads nothing: every loc 4-7 line must be found (a missing label
   fails, not skips).

## Not covered

- Truncation at `SUMMARY_W` (54 chars) with long names; 3 short names fit.
- Pixels: text is read from the widget, no screen grab. The Tk font and
  colour are unchanged by this fix.
- Bookmark with no `commodity`: shown as "unknown", as before; not checked.
