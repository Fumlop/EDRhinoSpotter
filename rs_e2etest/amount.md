# E2E: the panel's Amount starts at High

Harness: `rs_e2etest/amount_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, the real `main.build` panel on a withdrawn Tk root, a
Status.json on the ground written to a scratch journal folder
(`paths.journal_dir` pointed there), the real `main.make_card` press.
Output: `report.txt`.

Asked 2026-09-27: a deposit is always High when first found, so Amount starts
at High instead of `-` (not read). `-` stays in the menu.

## Ways it can fail

- Amount still starts at `-`.
- The bookmark saved from an untouched panel has no amount, or not "High".
- `-` gone from the menu: a deposit not read can no longer be saved without one.
- Picking `-` still saves "High".

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | `main.start` + `main.build` on a bare root | EDMC's theme over the panel |
| the game | a Status.json on the ground | Status.json timing |
| the card worker thread | waited for through the db (5 s) | nothing: the real thread runs |

## Checks

1. After `main.build`, the Amount box reads "High".
2. Bookmark pressed with only a material picked: the row's amount is "High".
3. The Amount menu offers `-` first, then High, Medium, Low, Depleted.
4. Amount set to `-`, pressed again 300 m away: the row's amount is None.
