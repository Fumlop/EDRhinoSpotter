# bookmark_e2e.py - what it covers and what it hides

`python rs_e2etest/bookmark_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/` (empty db), `main.start` + `main.build` on a withdrawn Tk
root, the Bookmark press run as the button runs it: `main._render_card(spot,
token)`, its `_on_ui` report pumped through Tk.

The report (2026-09-25, HIP 37645 4 a loc 1): Monazite marked, material
changed to Alexandrite on the same spot, Bookmark pressed - two bookmarks at
0 m instead of one Alexandrite.

## Ways it can fail, each checked

- Another material within `cards.SAME_SPOT_M` (100 m): a second bookmark.
- The update keeps the old material, or loses position, marked_at, location,
  or the tons already counted (`yield` cycles).
- Another material 150 m away: merged into it instead of a new bookmark.
- The same material within 100 m: anything other than the old update
  (Rigs/Amount/Density taken, material the same).
- Two bookmarks within 100 m: not the nearest one updated.
- The status line not saying which material became which.
- A shared code (`share.take`) of another material within 100 m:
  merged. Import dedupes on the same material only; share_e2e covers it.
- The update check booked again after start: an hourly look turned the
  Bookmark button into Update mid-session, and a press there updated instead
  of saving (reported 2026-09-25 as "not saved"). One `update.check_async` at
  `main.build`, no Tk `after` left that calls `_check_updates`.

## Not covered

- The panel's widgets filling `spot`: the spot dict is built here.
- The card image worker: `_render_card` is called on this thread.
