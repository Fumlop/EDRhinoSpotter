# gear_e2e.py - what it covers and what it hides

`python rs_e2etest/gear_e2e.py`. One Tk process: `main.start` / `main.build`
on a copy of the live db, RhinoData opened through `main.open_scan`, EDMC's
`config` replaced by a dict stand-in. Puts the RhinoData window and the
material dialog on screen for ~5 s; leave the mouse alone.

## Ways it can fail, each checked

- No gear on the MATERIAL FILTER row, or it is disabled (`_on_select` not
  passed through `scan.show`).
- A gear drawn without EDMC config (`minimap.config` None): a pick it cannot
  save. Must be absent, the filter still drawn.
- Gear right edge not flush with the filter box right edge, px.
- Gear not on the label row: below or overlapping the filter box, or the
  label's vertical middle outside the gear's height.
- Tooltip missing, wrong text, shown before 500 ms, or left on screen after
  <Leave> / a click.
- Click opens no dialog, or a dialog not owned by the RhinoData window.
- Dialog ticks differ from what the lists offer now (`materials_shown`).
- OK does not write `rhinospotter_materials`, or writes other names.
- OK writes the key but the panel Material dropdown or the RhinoData picker
  still offers the old list.
- RhinoData redraw after OK loses the gear (dead after the first use).
- OK with nothing ticked leaves an empty key instead of deleting it: lists
  must fall back to the over-50,000 Cr/t default.
- Settings tab path broken by the shared dialog: the tab's Select... button
  (`minimap.prefs`) opens no dialog, or OK writes the key before Settings OK
  instead of keeping the ticks in `minimap._picked`.

## Not covered

- EDMC's real `config` backend (registry on Windows): stand-in dict.
- The standalone build: not in this repo.
- Mouse hover with a real pointer: <Enter>/<Leave> are generated.
