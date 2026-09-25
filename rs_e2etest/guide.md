# guide_e2e.py - what it covers and what it hides

`python rs_e2etest/guide_e2e.py`. One process, LOCALAPPDATA and the journal
folder at `out/<timestamp>/`, Status.json written by the harness, the real
`rs_ui.overlay` started from the real RhinoData card (`scan._toggle_guide`),
ticks pumped through Tk. `overlay.HERE_MS` and `POLL_MS` shortened.

The report (2026-09-25): at the bookmark the arrow says HERE, but the card's
"Stop the arrow" stays. `_tick` returned before the HERE clock whenever Elite
was not the window in front - which it is not while RhinoData is.

## Ways it can fail, each checked

- Arrived with RhinoData in front (game not focused): HERE never noted, the
  arrow never ends, the card keeps "Stop the arrow".
- HERE noted, then the game loses focus: the clock stops, the arrow stays.
- After HERE_MS: the card not back on "Guide me there" (on_stop -> refresh).
- Game in front and arrived: unchanged - ends after HERE_MS.
- Not arrived, game in the background: the arrow ends on its own (it must
  not: nothing reached).

## Stand-ins

- `overlay.game_focused` and `overlay._game_rect` patched: focus is set by
  the harness, not by Windows. A real alt-tab is not exercised.
- The arrow window is drawn off-screen; its picture is not checked.
