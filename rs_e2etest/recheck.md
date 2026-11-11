# E2E: still depleted vs depleted again (issue 21)

Harness: `rs_e2etest/recheck_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, the real `main.start` + `main.build` panel and the real
`scan.show` window on a withdrawn Tk root, a Status.json written to a scratch
journal folder (`paths.journal_dir` pointed there). Presses go through the
card's own "Mark depleted" button (`invoke()`), tons through
`main.journal_entry` MiningRefined, the HUD re-mark through `main.make_card`.
Run from the plugin folder: `python rs_e2etest/recheck_e2e.py`.
Output: `report.txt`.

Rule under test: Mark depleted after `yields.regrow()` took the mark off, with
no ton refined at the bookmark since, puts the old `depleted_at` back and logs
the look in `rechecks`; `regrow()` lifts it again `RECHECK_DAYS` (7 d) after
the last look. With tons since, it is a new depletion. A mark under
`RETURN_DAYS` (40 d) stays; from `REGEN_DAYS` (14 d) the card says it may be
back at Low.

## Ways it can fail

- The press after the lift writes a new `depleted_at` (the issue as filed).
- Tons refined after the lift and the press still counted as "still depleted".
- `regrow()` lifts a rechecked mark on its `depleted_at` (> 40 d old) at the
  next jump, not 7 d after the look; or never lifts it.
- A second lift/recheck round loses the original date.
- The HUD path (Amount Depleted re-marked from the panel) bypasses the rule.
- Undo (Set active, then Mark depleted) on a fresh depletion is taken as a
  recheck of an older lift and restores an old date.
- Undo of a "still depleted" press loses the original date.
- A 14-40 d mark lifted, or its card line missing, wrong or wider than the card.
- Card does not say "still depleted", says it wrong, or the line is wider than
  the card; status line still says "marked depleted."

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | `main.start` + `main.build` on a bare root | EDMC's theme |
| the game | Status.json on the ground, MiningRefined dicts | journal timing |
| 41-50 d of game time | rows seeded with past `depleted_at` / `rechecks` stamps, then the real `regrow()` | a clock change between lift and press |
| the screen | window at -4000,-4000, label `winfo_reqwidth` vs card width | DPI scaling other than this machine's |
- A ton 14 d+ after the mark leaves `depleted_at` set: the next Depleted press
  restores the old date as "still depleted" and the depleted-tons line is lost.
- A ton under 14 d after the mark lifts it instead of counting as leftovers.

## Checks

1. Depleted 41 d ago, `regrow()` lifts it, card button pressed with no tons
   since: `depleted_at` is the original, 1 entry in `rechecks`, `regrown`
   entry kept, status "still depleted, look again in 7 d.", card line
   "still depleted at 41 d, look again in 7 d" fits the card.
2. Same seed, lifted, 3 t refined at the bookmark, button pressed:
   `depleted_at` is today, no `rechecks`, status "marked depleted.".
3. Marks 50 d old. Last look 8 d ago: `regrow()` lifts it, `regrown` keeps the original date;
   last look 6 d ago: stays. The lifted one pressed again: original date back,
   2 entries in `rechecks`.
1b. The look pressed in 1: `regrow()` 6 d later keeps the mark, 8 d later
    lifts it with the original date in `regrown` (2 entries).
1c. Pressed again, Set active, Mark depleted: the original date is back.
4. Depleted 41 d ago, lifted, panel Amount Depleted re-marked on it with
   `main.make_card`: original date back, 1 recheck.
5. Undo: lifted 41 d bookmark mined (3 t) and pressed (new depletion), Set
   active, Mark depleted: `depleted_at` is today, no `rechecks`.
6. Depleted 20 d ago: `regrow()` keeps the mark, card line "20 d: may be Low
   (unlikely), back at 40 d" fits the card, button Set active.
7. Depleted 3 d ago: card line "3 d since, back after 40 d (assumed)" fits.
8. Depleted 30 d ago, look 8 d ago: `regrow()` keeps it (day 40 not reached),
   card line "still depleted at 22 d, look again in 10 d" fits.
9. Edges: 13.9 d countdown line, 14.01 d hint line, 39.9 d kept with the hint
   ("40 d: ...") fitting the card, 40.01 d lifted.
10. Depleted 20 d ago, 3 t refined at it: mark lifted (original date in
    `regrown`), the 3 t in a new open cycle, closed 50 t cycle untouched; the
    Depleted press after it sets today's date, no look, status "marked depleted.".
11. Depleted 10 d ago, 3 t refined: mark stays, tons go into the closed cycle (53 t).
