# E2E: RhinoData window follows a jump

Harness: `rs_e2etest/scan_arrive_e2e.py`. One process, a withdrawn Tk root,
`rs_ui.main.journal_entry` fed FSDJump lines, a copy of the live db.
Output: `rs_e2etest/out/<timestamp>/report.txt`.

The complaint (2026-09-22): Aramo -> 43 G. Canis Minoris -> Aramo, the open
window still showed Canis. `journal_entry` only updated the panel's landable
count on arrival; the window redrew on open, filter, prefs or a Spansh answer.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | direct `main.start()` + `main.journal_entry()`; no `main.build()` | the panel, hotkeys and update check around it |
| Bookmark press | `spotcard.save` of a copied bookmark, then `main._report` | `make_card`'s Status.json read and the worker thread |
| the game | FSDJump dicts with `StarSystem` only | Location/CarrierJump arrivals (same `ARRIVAL_EVENTS` path in `bodies.Register.track`) |
| focus / z-order | `scan.show` swapped for a counter during jumps | a raise done by anything other than `scan.show` |
| the bodies cache | the live db copied via sqlite3 backup | systems not in the cache: the window shows the empty state |

## Checks

1. Window opens on the live system.
2. FSDJump redraws the open window: title names the new system.
3. The old system's picked body is gone.
4. `scan.show` not called on the jump.
5. Jump back redraws again.
6. A system browsed from the search box stays shown after a jump.
7. Back to live shows the system jumped to.
8. A bookmark saved via `spotcard.save` + `main._report`: the rail's `N bm` sum goes up by 1.
9. `scan.show` not called on the save.
10. Control: `scan.refresh` a no-op leaves the count stale.
11. Control: `scan.arrived` a no-op leaves the title stale.
12. Honk, Spansh answers with a new body (`main._add_spansh`), window open:
    `scan.show` not called (it lifts the window and takes focus from Elite),
    the rail lists the new body, and only the rail is rebuilt: no `_draw`,
    the middle pane and the card are the same widgets.
13. The same answer with the window closed: nothing opens.
14. Rail-only not possible - no body was picked before (the middle showed
    nothing): falls back to one `_draw`.
