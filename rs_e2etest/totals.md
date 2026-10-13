# totals_e2e.py

RhinoData rail header: `SYSTEMS WITH BOOKMARKS  ·  <systems>` and, under the
search box, `<n> bookmarks  ·  <n> bodies  ·  <n> maps` over the whole database
(`scan._totals`, `scan._totals_line`).

    python rs_e2etest/totals_e2e.py

Real window through `main.start` / `scan.show`, on a copy of the live db
(sqlite3 backup API, read only) under `rs_e2etest/out/<timestamp>/localappdata`.
Expected numbers come from the harness's own SQL on the scratch db, not from
`scan`. Writes `report.txt`; exit 1 on a failure, 2 without a live db.

## Ways it can fail

| # | Check | Fails when |
|---|-------|-----------|
| 1 | header reads `SYSTEMS WITH BOOKMARKS  ·  <distinct systems>` | count missing, or counts NULL systems |
| 1 | totals line equals the SQL counts | wrong column, wrong table, plural |
| 2 | same line after a jump to another system | counts only the shown system |
| 3 | line fits the rail (`winfo_reqwidth <= RAIL_WIDTH - 26`) | clipped at the rail edge (no wraplength) |
| 4 | one bookmark deleted -> 1 less on the next draw | read once and cached |
| 5 | search box still lists hits under the entry | totals line packed into the hits frame |
| 6 | no bookmarks and no maps -> no totals line, header `· 0` | "0 bookmarks · 0 bodies · 0 maps" shown |
| 7 | 1 bookmark, 1 map -> singular `1 bookmark  ·  1 body  ·  1 map` | plural on 1 |
| 0 | live db unchanged | harness writes to the live db |

## Not covered

- A read error in `_totals` (header without count, no line, warning in the log):
  `database.connect` is shared with the rest of the window and cannot fail for
  this call alone without patching `scan`.
- The look: no screen grab; `rhinoscan.png` in docs needs a regenerate run.
