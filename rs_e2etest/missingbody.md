# missingbody_e2e.py - bookmarks on a body the body data lacks (issue 23)

Run from the plugin folder: `python rs_e2etest/missingbody_e2e.py`.
LOCALAPPDATA at `rs_e2etest/out/<timestamp>/`, db starts empty.
Output: `report.txt`.

Rule under test: `scan._bodies()` lists every body that holds a bookmark. A
body missing from the register (Spansh / journal scan) is listed after the
known ones with ground None, label "unknown". Issue 23: HIP 61744 "5 bm" in
the search, rail "0 bookmarks", body 3 a not listed.

## Ways it can fail

- The missing body is not in the rail (the issue as filed).
- The header still counts 0 bookmarks.
- A known body is listed twice.
- Picking the missing body raises (ground None in the sheet lookups, card, map).
- Its bookmarks are not in the middle list after the pick.
- Material filter: shows it when none of its bookmarks match; hides it when one does.
- A system with 0 register bodies still lists nothing.

## What the harness replaces

| Real | Replaced by | Blind spot |
|---|---|---|
| EDMC | `main.start` + `main.build` on a bare root | EDMC's theme |
| Spansh / Scan | `bodies.Register.adopt` with 2 bodies, then 0 | a body name spelled differently by Spansh |
| the screen | window at -4000,-4000, label texts read back | layout, DPI |

## Checks

1. Register 5 b, 5 c; bookmarks: 4 Monazite + 1 Painite on 3 a, 1 Opal on 5 b.
   Rail shows "3 a" with "5 bm", 5 b once; header "6 bookmarks".
2. Pick 3 a: no exception, title ends "- 3 a", middle list holds its 5 bookmarks.
3. `_bodies` with focus Monazite: 3 a, 4 shown; focus Opal: 3 a not listed.
4. Register with 0 bodies: 3 a and 5 b both listed.
