# border_e2e.py - what it covers and what it hides

`python rs_e2etest/border_e2e.py`. One child, LOCALAPPDATA at `out/<timestamp>/`
(empty db), the real `rs_ui.minimap` fed Status readings through
`minimap.update`, the hotkeys called as `hotkey` does (`center_here`,
`border_here`) with `_here` set to the fix.

## Ctrl+Alt+B before Ctrl+Alt+Z: the border point is kept, each checked

- Nothing kept, "set center first" only: the old behaviour.
- Painted ground changed by the early press (nothing may be clipped or
  deleted while there is no centre): mask pixel count before == after.
- No rings or border drawn from a guessed centre: `border_m` stays None.
- The hint line not saying the point was kept.
- The kept point lost on the way to disk: `border_at` in the saved map,
  back after `Coverage.from_dict`.
- Ctrl+Alt+Z later: border not set to the distance centre -> kept point,
  or the kept point not cleared.
- A second Ctrl+Alt+B before Z: the later point wins.
- With a centre already set: behaviour unchanged (border from that centre).
- Ctrl+Alt+Z again after the border: centre moves, border keeps its radius.

## Not covered

- The real hotkey thread (`RegisterHotKey`); the handlers are called directly.
