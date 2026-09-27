# E2E: RhinoData rail folds by ground, sorted by the picked material

Harness: `rs_e2etest/railfold_e2e.py`. One process, a withdrawn Tk root,
`rs_ui.main.journal_entry` fed an FSDJump, a copy of the live db.
Output: `rs_e2etest/out/<timestamp>/report.txt` (checks + the rail text of each state).

Asked 2026-09-27: ground groups in the rail fold; with a material picked the
group with the highest % of it on top; with all materials GROUND_ORDER; only the
group of the body under the ship open (in space: of the picked body).

## Ways it can fail

- Every group open, or none, on open.
- Clicking a header leaves the previously open group open (two open).
- The open group is not the one of `here` (Status.json body) but of the old pick.
- In space (`here` None) no group open, so the gold picked row is hidden.
- Material picked: groups in GROUND_ORDER, or sorted ascending, or a ground
  with no sheet row sorted above one with a row.
- All materials: groups re-sorted instead of GROUND_ORDER.
- A click on a header does not fold / unfold, or triggers a full `_draw`
  (middle pane and card flicker).
- A fold is lost on the next redraw (bookmark saved, Spansh answer).
- Picking a body elsewhere (`_mark_here`, jump) leaves its group folded.
- A jump keeps the old system's open grounds.
- Collapsed header hides how many bodies / bookmarks sit under it.

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | `main.start()` + `main.journal_entry()`; no `main.build()` | the panel's picker widget |
| Status.json | `here=` argument to `scan.show` | `main.open_scan` reading `BodyName` |
| a mouse click | the header's `<Button-1>` binding invoked | hit area of the row |
| the game | FSDJump with `StarSystem` only | Location / CarrierJump arrival |

## Checks

1. Open with `here` = a body: only its ground is open.
2. Open with `here` None: only the picked body's ground is open.
3. All materials: header order == GROUND_ORDER order.
4. Material picked: header order == sheet rate descending, None last.
5. Header click unfolds a ground and folds the one that was open: exactly it open;
   only the rail rebuilt.
6. Header click again folds it: none open.
7. Fold state survives a `scan.refresh()` redraw: exactly it open.
8. Collapsed header text carries the body count.
9. Jump: open grounds reset to the new picked body's.
10. Control: with the header binding a no-op, check 5 fails.
11. In the SRV at a bookmark (Status.json `Flags & IN_SRV`) on a body of a third
    ground, `here` given: only the SRV body's ground open (`_mark_here` wins).
