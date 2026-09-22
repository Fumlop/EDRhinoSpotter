# yield_e2e.py - what it covers and what it hides

`python rs_e2etest/yield_e2e.py`. One child process, LOCALAPPDATA pointed at
`out/<timestamp>/`, the real `load.journal_entry` over the real MiningRefined
lines of a copy of `Journal.2026-09-21T211951.01.log` (171 t: 127 Diamond +
44 Ruby), against a Status.json the harness writes at the bookmarks'
coordinates.

## Checked

- 171 real lines counted into one open cycle, the by-product under its own name.
- The cycle keeps the rigs, density and Amount it was opened at.
- 5 km off every bookmark: counted in `unplaced`, not onto the nearest one.
- A Status.json read that lands mid-write: counted in `unread`.
- Refined 2 km up: not placed, and not counted as a loss.
- Material beats distance - ruby at 120 m to the Ruby bookmark, alexandrite at
  0 m to the Alexandrite one.
- A line older than the plugin start (EDMC replaying the journal at startup):
  skipped, counted in `main._replayed`, no tons added.
- Depleted closes the cycle and takes the tons still pending at the press with
  it - `cards.set_depleted` flushes the tally first.
- Mining after the close opens a second cycle; the closed one does not move.
- `capacity()` after one measured cycle; `regenerated()` at 0 and 15 days.
- `python -m rs_core.yields` prints t/rig for the measured cycle.
- The Mined column: the measured cycle, the floor before one, header and row
  the same width.
- Edit and re-mark (`cards.edited` / `cards.updated` -> `spotcard.save`) keep
  the cycles a dict and take the tons pending at the time with them.
- Amount Depleted set through the Edit dialog closes the cycle and stamps
  depleted_at, as the Depleted button does.

## Not covered

- The game writing Status.json. The harness writes it whole; the real file is
  rewritten constantly and the torn read above is a hand-made one.
- The real Depleted button. `cards.set_depleted` is called directly, not
  through `rs_ui.scan`.
- Position lag. The ton is placed by the Status.json read when the event
  arrives, up to ~1 s of driving after it - about 15 m at 55 km/h. Nothing here
  moves the SRV between the ton and the read.
- Two bookmarks of the same material within ATTRIBUTE_M of each other. The
  nearest wins; no scenario has two.
- EDMC restarted mid-session. Tons refined while it is down are lost, and the
  replay skip is what makes that so rather than a double count.
- A failed row write. `Tally._write` re-arms the debounce on a failure; no
  scenario locks the database mid-session to prove the retry lands.
- A bookmark deleted while its tons are pending - the "dropping N t" branch.
- `load.plugin_stop()`: the child never calls it, so main.stop()'s flush and
  `database.backup()` ordering is untested here.
- Timing. FLUSH_S is 0.05 s here, not 30 s, so nothing tests what 30 s of
  mining costs on a hard crash (up to 30 s of tons).
