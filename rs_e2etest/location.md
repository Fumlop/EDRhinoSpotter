# location_e2e.py - what it covers and what it hides

`python rs_e2etest/location_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/` (empty db), `main.start` + `main.build` on a withdrawn Tk
root, Status.json written to a scratch journal folder, `main.make_card()` run
as the Bookmark button runs it; the No location popup is answered from a Tk
`after` (spinbox typed, button invoked).

Request (2026-09-28): no bookmark without a location. Location is a spinbox
0-50 like Rigs; empty Loc with nothing targeted opens a warning popup with a
spinbox; left at 0 the bookmark is saved at loc 0, which never ties a map and
is fixed later with Edit.

## Ways it can fail, each checked

1. Location still an Entry, or the spinbox not 0-50.
2. `tk.Spinbox` writes `from_` ("0") into an empty variable: Loc reads 0 and
   the popup never opens (caught on the first run).
3. No popup with Loc empty and no `Destination` in Status.json; popup text
   without the loc 0 / no map warning; popup spinbox not 0-50 or not at 0.
4. Cancel still saves a bookmark, or leaves the status line empty.
5. Popup left at 0: not saved at loc 0, or Loc filled with 0 (the next press
   would then skip the popup).
6. Popup answered 7: not saved at 7, or Loc not set to 7.
7. Popup when Loc is typed, or when Status.json targets `#index=12`.
8. Popup or bookmark when Status.json has no coordinates.
9. `coverage.mapped_locations` ties a map to loc 0 (control: loc 7 on a map
   ties it, so the check is not passing on an empty result).
10. `cards.location_at` returns loc 0, so Touchdown fills Loc with 0
    (control: loc 7 found at 0 m).
11. Edit: Location not a spinbox 0-50; saving 3 on a loc 0 bookmark fails.
12. Edit of a bookmark with no location: the spinbox writes 0 and Save turns
    `None` into loc 0.
13. The RhinoData copy of the panel (`_dock_panel`), built after Loc is typed,
    wipes the typed Loc; or fills an empty one with 0.
14. Pressed in RhinoData, the popup opens over EDMC (behind the game).
    `root.winfo_containing` is replaced to return the RhinoData Bookmark
    button, then None (popup must fall back to EDMC's window).

## Not covered

- The real pointer: `winfo_containing` is stubbed, the mouse is not moved.
- Spinbox arrow clicks: values are typed into the spinbox, not stepped.
- EDMC's theme on the popup: plain Tk colours, not checked.
- Minimap caption list without loc 0 (`minimap._about` path): not drawn here.
