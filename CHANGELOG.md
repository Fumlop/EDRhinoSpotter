# Changelog

## 4.6.2

**Changed**

- Minimap: the SRV marker keeps its 1x size at every zoom; zooming grows the ground, not the marker.
- Minimap: the hotkey rows (set center, set border, zoom) a step smaller than the rest of the text.

## 4.6.1

**Fixed**

- Guide arrow came up top left instead of top middle of Elite when Guide was pressed with the game behind; placed through Win32 now, as the minimap is.
- RhinoData button or hotkey on an open window brings it to the front, restoring it when minimised; before, it only redrew in place.

## 4.6.0

**Added**

- Ctrl+Alt+M 4x step: the 2x window showing 6 km across instead of 12.
- Hotkeys configurable in Settings: modifier set plus key for each of the four; the minimap rows show the keys in use.
- Saved map picture circles golden groups in gold: 5+ rigs, none depleted, all within 2.5 km (2/2/1/1, 2/2/2, 2/3/1, 3/3, 2/1/1/1, 1x6).

**Fixed**

- Just-made bookmarks expired on the wrong clock since 4.5.0: unpriced ones vanished at once, others never expired.

**Changed**

- Hotkey row reads "Ctrl+Alt+M  zoom".
- Zoomed in, painted ground is drawn at 2x detail and scaled up; layer rebuild 56-105 ms instead of 205-369 ms.

## 4.5.2

**Fixed**

- Location prefilled only from a bookmark within 3 km (was 10 km); neighbouring locations no longer pull.
- Location cleared on takeoff; kept when the ship is sent away from the SRV.

## 4.5.1

**Fixed**

- Ctrl+Alt+M scales the map only; frame, header and hotkey rows keep their 1x size.
- `mining_sheet.json` regenerated from 928 mining locations (was 867, 2026-09-14).

## 4.5.0

**Added**

- Center set with Ctrl+Alt+Z shown as a blue dot, smaller than a bookmark.
- Lines between bookmarks: solid to the nearest of the same material, dotted to the nearest of the next material down in price.
- Each line carries its length, beside its middle.
- Ctrl+Alt+M toggles 1x / 2x map size, remembered across restarts, capped at 640 px.
- Lines and distances only at 2x.

**Changed**

- Only bookmarks on the map are joined up.
- Fonts are cached.

## 4.4.3

**Changed**

- Density has its own row under Amount.
- README pictures and text updated to 4.4.x.

## 4.4.2

**Added**

- Tritium in the material list.
- Setting: keep the minimap up when alt-tabbed out.

## 4.4.1

**Changed**

- Tons-left range counts Density: Low 275-300 t, Medium 370-400 t per rig position.

## 4.4.0

**Added**

- Ctrl+Alt+D opens RhinoData over the game; Escape closes it.
- Distance to each bookmark from where you stand.
- Column headings on every table.
- Material price beside its rate on the body list.
- Every body row opens that body's page.

**Changed**

- RhinoScan renamed RhinoData.
- Picking a material redraws the window in place.
- One material filter for the whole plugin.
- Volcanism column shows the kind, e.g. "major metallic magma".
- Bookmarks and Mapped are buttons.

## 4.3.7

**Changed**

- Landing note names the matched bookmark and clears after 8 s.
- README panel screenshot updated.

## 4.3.6

**Added**

- Hint shows Spansh completeness, e.g. "Spansh 31/40 bodies - FSS for the rest".

**Fixed**

- Minimap map write no longer runs on the UI thread.
- "Spansh unreachable" clears after the one-hour pause.

## 4.3.5

**Added**

- Bodies from Spansh are tagged `spansh` until your own scan replaces them.

**Changed**

- Spansh not asked again for 30 days after it answered.
- A non-system answer from Spansh counts as a failure.
- Mining no longer overrides a material picked by hand.

**Fixed**

- Your own mining location count survives a restart.

## 4.3.4

**Fixed**

- Saved map picture showed gravity in m/s² labelled "g".

## 4.3.3

**Changed**

- Spansh not asked for undiscovered systems, for 30 days after an empty answer, or for 1 h after a failure.
- Hint "New system - FSS planets" in undiscovered systems.

## 4.3.2

**Changed**

- Shorter hints under the buttons.

## 4.3.1

**Changed**

- Spansh asked on honk, once per session per system; requests send a User-Agent.
- Hint line follows the honk.

## 4.3.0

**Added**

- Landable bodies from Spansh; your own scans and counts take precedence.
- Mining a material picks it in the dropdown.

**Fixed**

- Two writes within two seconds no longer drop the first.
- EDMC closing waits for a write in progress.
- A briefly locked database no longer hides the bookmark dots.
- A lost `migrate.done` is rebuilt instead of re-importing JSON.

## 4.2.2

**Fixed**

- With a material picked, bookmark counts and lists show only that material.

**Changed**

- README shortened.

## 4.2.1

**Fixed**

- Picking a material no longer moves the RhinoScan window.

## 4.2.0

**Changed**

- Bookmarks, bodies and map points in one SQLite file, `%LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db`.
- First start imports the old JSON and writes `db\migrate.done`.
- EDMC closing backs up the database; newest two copies kept.
- Settings: "Delete migrated JSON".
- Records keep SystemAddress and BodyID.
- Panel "bookmarks" link removed.

## 4.1.13

**Changed**

- Landing within 10 km of a bookmark sets Location from that bookmark.
- Dropping the SRV from a hover fills Location.

## 4.1.12

**Changed**

- Drive rings counted out from the center: 3.75 km, then every 1.75 km.

## 4.1.11

**Fixed**

- The once-a-second poll no longer stops for good on one error.

## 4.1.10

**Changed**

- Amount before Density, as on the HUD.

## 4.1.9

**Added**

- On or over a body, RhinoScan opens on that body's bookmarks.
- Three best-paying materials for the body's ground under the bookmark count.
- Material filter beside the body name.

## 4.1.8

**Changed**

- Tons-left range by rig positions: 275-300 t each, times the Amount share.
- Same material within 100 m updates the existing bookmark.
- Bookmarks save the planet radius.

## 4.1.7

**Added**

- Density and Amount pickers; bookmarks show a tons-left range.

**Fixed**

- Mining sheet no longer counts one body's reads twice.

## 4.1.6

**Changed**

- RhinoScan opens wide enough for every row.
- Picked material leads its ground's line in bold.
- Mapped page note moved above the list.

## 4.1.5

**Added**

- "Mapped N/M" per body, with a page listing mapped locations and their maps.

## 4.1.4

**Changed**

- Metallic and rocky magma are separate grounds.
- Mining sheet is `mining_sheet.json`, replaced on every update.

## 4.1.3

**Changed**

- Rocky grounds named composition first, e.g. `rock 80%+ [magma]`; old names still read.

## 4.1.2

**Changed**

- Rocky body with silicate magma is its own ground.
- Mining sheet refreshed with prices for cheap materials.

## 4.1.1

**Changed**

- Bookmark dots green when active, red when depleted.

## 4.1.0

**Added**

- Bookmarks can be marked depleted; saved as `depleted_at`.

## 4.0.2

**Changed**

- Status line names the Update button when a release is out.

## 4.0.1

**Fixed**

- Update button could not be pressed when EDMC started off the ground.
- Update check runs hourly.

**Changed**

- Update check no longer uses the GitHub API.
- A failed check is logged once per session.

## 4.0.0

**Added**

- Ctrl+Alt+B sets the location border; needs a center.
- With a border, drive rings run from the center out to it.

**Changed**

- Setting a border deletes painted ground outside it.
- README shows the minimap three ways.

## 3.7.0

**Added**

- Ctrl+Alt+Z sets the map center.

**Removed**

- Droppoints as map marks and in saved maps.

## 3.6.1

**Changed**

- Droppoint rings at 3 and 5 km (were 2 and 4).

## 3.6.0

**Removed**

- Bookmark card PNG and the Card button.

**Changed**

- Only warnings and errors go to EDMC's log; `RHINOSPOTTER_DEBUG=1` for everything.
- README shows a shared map picture.

## 3.5.2

**Changed**

- Bookmarks grouped by location, Share map per location.

## 3.5.1

**Changed**

- Saved map picture without droppoints and rings.
- Share map opens the last map picture of the body.

## 3.5.0

**Changed**

- Minimap 85% opaque.
- Rings at 2 and 4 km around the latest droppoint.
- Saved `map N.png` has a title and a legend.

## 3.4.0

**Changed**

- Guide stops 10 s after HERE.

## 3.3.0

**Added**

- Material codes on bookmark dots: T, TH, TI, TR by value.

**Changed**

- Droppoints unnumbered and smaller.
- Debug lines only with `RHINOSPOTTER_DEBUG`.

**Fixed**

- Minimap could stay hidden after RhinoScan and Guide.

## 3.2.0

**Added**

- Bookmarks on the minimap and the saved map.

**Changed**

- Minimap and guide arrow hide while Elite is not in front.

## 3.1.0

**Added**

- Minimap saved per body in `coverage\<Body>\map N.json.gz`; a launch within 10 km continues it.
- `map N.png` saved on docking.
- Settings show saved map count and size.

**Changed**

- Minimap reach 10 km, 12 km across, 1 km grid.

## 3.0.0

**Added**

- Minimap over the game in the SRV, painting a 2 km scan disc per fix.
- Map size 22% of game window height, 180-480 px.
- Settings tab: minimap on/off and corner.

**Changed**

- RhinoScan's top three materials by pay per location, not likelihood.

## 2.10.0

**Changed**

- Guide arrow drawn as a shaded shape.
- Overlay stays topmost and centers when the Elite window is not found.
- Scan window measures fonts once.
- Honk written once every two seconds.

**Removed**

- Unused measuring wiring and dead code.

## 2.9.1

**Changed**

- "completed" shows on the Bookmark button for 5 s.

**Fixed**

- Pending restore cancelled at shutdown.

## 2.9.0

**Changed**

- Bookmark only enabled on the ground (100 m or less).
- Ground table carries all 37 materials.

**Fixed**

- Landed poll cancelled at shutdown.

## 2.8.2

**Fixed**

- Scan window footer no longer flips between one and two lines.
- README screenshots regenerated.

## 2.8.1

**Changed**

- Guide error message shows for 10 s; a working guide survives taking off.

## 2.8.0

**Added**

- Delete button on every bookmark, with confirmation.
- Landing fills Location from `Touchdown`.

**Fixed**

- A guide state with no arrow closes the overlay after 6 s.
- Retargeting Guide no longer doubles the poll.

## 2.7.0

**Added**

- Bookmark list inside the scan window, with Back.
- Guide: arrow over the game pointing to the bookmark.
- Card opens the bookmark PNG.

**Removed**

- HTML bookmarks page.

## 2.6.1

**Changed**

- Bookmarks page sorted by rig count.

## 2.6.0

**Added**

- Bookmarks open as an HTML page.

## 2.5.0

**Changed**

- Create Card renamed Bookmark.
- MeasureSpot button removed.

## 2.4.1

**Changed**

- Open-border warning removed from the panel; logged instead.

## 2.4.0

**Added**

- Measurement closure shown; summary logged.

## 2.3.2

**Changed**

- Panel explains how to measure.

## 2.3.1

**Fixed**

- Small patches measured as zero rigs.

## 2.3.0

**Added**

- MeasureSpot: drive a patch border, get area and rig count.

## 2.2.1

**Fixed**

- Replaying two visits to one system merges them.

**Added**

- `--rebuild` fills the cache from all journals.

## 2.2.0

**Changed**

- Screenshot conversion moved to the RhinoAnalysis plugin.

## 2.1.1

**Added**

- GPL-3.0 licence.
- `VERSION` readable from `load.py`.

## 2.1.0

**Added**

- Card count per body, opening the newest card.
- JSON sidecar per card.
- Material picker in the scan window.

**Changed**

- MiningCard renamed Create Card.

## 2.0.2

**Changed**

- System known from the first journal line EDMC hands over.
- Material filter for RhinoScan.
- Material dropdown restyled.
- Landable count moved to the top row.

**Fixed**

- No traceback from worker threads at shutdown.

## 2.0.1

**Changed**

- Card shows coordinates instead of altitude.

## 2.0.0

**Added**

- RhinoScan: landable bodies of the system by ground type, with material rates.
- Mining location counts from the journal, cached per system.
- Test mode: `python -m rs_core.replay`.
- Update button.
- 164 tests.

**Changed**

- Code split into `rs_core`, `rs_ui`, `rs_tests`.
- One palette for cards and windows.
- Panel layout: Location and Rigs on one row.

## 1.1.0

**Changed**

- Marking a location twice keeps both cards.

## 1.0.0

- MiningCard. Screenshot conversion with sidecars.
