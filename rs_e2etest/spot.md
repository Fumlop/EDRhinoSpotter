# spot_e2e.py - what it covers and what it hides

`python rs_e2etest/spot_e2e.py`. One child process, LOCALAPPDATA at
`out/<timestamp>/` (empty db), `load.plugin_start3` + `main.build` on a
withdrawn Tk root, bookmarks written with `spotcard.save`, `scan.show` with
window at -4000,-4000. The location lines are read back from the Tk widgets in
pack order; the buttons are pressed with `Button.invoke()`. Output:
`report.txt` with the PASS/FAIL lines, the drawn order and meta rows after each
step, and the free width on the loc 4 line at the drawn width and at
`scan.MIN_WIDTH` (900 px).

Request (2026-10-25): "Mark good" and "Mark bad" on the location line, left of
the distance and of Share map. Good: golden header, listed first. Bad: greyed
header, listed last. The rest by number. Stored as 1 / 0 / -1 (0: no row).

## Ways it can fail, each checked

1. Buttons missing, or x order not Mark good < Mark bad < distance < Share map
   (loc 4 row).
2. Order without marks not 4, 5, 6, 7, then "loc -".
3. Mark good on loc 6: order not 6, 4, 5, 7, -; arrow, "loc 6", summary not
   GOLD; button not "Unmark good"; another line coloured.
4. meta not exactly `{'spot:Aramo|Aramo A 1|6': '1'}`.
5. Mark lost on close and reopen of the window (scan.show again).
6. Mark bad on loc 4: not last (6, 5, 7, -, 4); arrow, "loc 4", summary,
   distance not MUTED; button not "Unmark bad"; meta value not '-1'.
7. Two good marks (6, 7) not by number: 6, 7, 5, -, 4.
8. Mark bad on a good loc 6: not switched (7, 5, -, 4, 6), two rows for loc 6,
   or loc 6 still GOLD.
9. Unmark bad on loc 4: row not deleted, not back at its number (7, 4, 5, -, 6),
   still MUTED.
10. A mark of another system with the same body name and index
    (`spot:Other|Aramo A 1|5` = '1') turns Aramo's loc 5 gold.
11. A meta value other than '1' / '-1' (`'2'` on loc 5): raises, or marks it;
    must be drawn unmarked and logged.
12. Unnumbered location: either button enabled.
13. Write fails (second connection holds `BEGIN EXCLUSIVE`, 5 s timeout): no
    status line saying so, or the mark shown anyway.
14. The check reads nothing: every loc line must be found (a missing row fails).

## Not covered

- Pixels: colours read from the widget `fg`, no screen grab.
- Clipping: the free width is reported, not checked. At 900 px the line is
  already overfull before these buttons; pack clips the summary first.
- A location renumbered in the Edit dialog: the mark stays with the number, not
  the deposits (key is the location_index).
- Read failure of the meta table: logged, every line drawn unmarked; not forced.
