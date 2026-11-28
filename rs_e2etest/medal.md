# medal_e2e.py - what it covers and what it hides

`python rs_e2etest/medal_e2e.py`. LOCALAPPDATA pointed at `out/<timestamp>/`,
seeded with a copy of the live db. Real RhinoData window (`scan.show`, withdrawn
root), system Aramo. Through the Edit dialog's save (`scan._save_edit`):
Aramo A 1 six bookmarks to 6, 7, 2, 4, 5, 7, the first 7 marked depleted
(`cards.set_depleted`); Aramo AB 3 a one to 4; Aramo AB 1 a its 6 to 5, its 4s
to 3. Rail then: gold 7, bronze 4, silver 5. Precondition: the live db holds
those three bodies with 6+, 1+ and a 6-rig bookmark. Writes `report.txt` and `medals.png` (4-7 at 8x).

## Ways it can fail, each checked

- Rail tiers: bronze 4, silver 5 and a live gold 7 each on a rail row.
- Rail medal on the wrong body, wrong count, or a depleted spot counted: every
  body row of all 7 grounds (each opened in turn) against the max rigs of its
  not-depleted bookmarks, computed in the harness, not by `scan._best_rigs`.
- Medal blocks the row text (user report, first build): the slot sits between
  name and distance; the distance label at one x on every row, with and
  without a medal (34 rows). The "N loc" label is gone from the row.
- Location header medal wrong: each location of Aramo A 1 against its group.
- Deposit row rigs colour: 4 BRONZE, 5 SILVER, 6/7 GOLD, under 4 ACCENT,
  depleted DIM; every row of the body.
- Medal image: disc colour per count, none under 4 or for unknown rigs.
- Other rail harnesses: `railfold_e2e.py` reads body rows by label count; it
  skips image labels now and still passes.

## Not covered

- What it looks like in the window: no screen grab (project rule: grabs need
  a cleared screen). `medals.png` is the image alone; checked in game.
- Panel colours other than PANEL and BG; EDMC dark/transparent themes.
- Bookmarks with rigs None or a non-int: no medal, not exercised here (the Edit
  dialog keeps the old value on an unparsable Rigs).
- Premise written after the first build of the code, revised with it.
