# Changelog

## 5.7.13-beta.1

**Fixed**

- Linux: data moved from `~/RhinoSpotter` to `$XDG_DATA_HOME/RhinoSpotter`
  (`~/.local/share`; Flatpak EDMC `~/.var/app/io.edcd.EDMarketConnector/data`).
  In the Flatpak, bookmarks written to `~/RhinoSpotter` did not survive a restart
  (issue #9). An existing `~/RhinoSpotter` is copied once on the first start and
  left in place. Windows unchanged.
- Linux: the minimap's "open folder" opens the coverage folder through the
  desktop (`webbrowser` -> `xdg-open`) instead of logging
  `module 'os' has no attribute 'startfile'`.
- Linux: no more `overlay: not click-through here: ... windll` warning on every
  overlay build. Click-through is still Win32-only.

## 5.7.12

**Fixed**

- The update check ran every hour and turned the Bookmark button into Update
  mid-session; a press meant to bookmark updated the plugin instead, and the
  bookmark was not saved. The check now runs once, when EDMC starts.

## 5.7.11

**Fixed**

- The guide arrow stayed up after HERE, and the card kept "Stop the arrow",
  while Elite was not the window in front (RhinoData open, say): `overlay._tick`
  returned before the HERE clock. Arrival and the 10 s clock now run with the
  game in the background; only the drawing waits for focus.

**Changed**

- README: a Features list at the end.

## 5.7.10

**Changed**

- Bookmark on a spot that already has a bookmark within 100 m
  (`cards.SAME_SPOT_M`) updates it whatever its material: the material is
  taken too (`cards.nearby(any_material=True)`). Changing the material and
  pressing again gave a second bookmark at 0 m. Position, marked_at, location
  and counted tons stay; the status line says "Monazite -> Alexandrite".
  A shared code still merges only with the same material.

## 5.7.9

**Fixed**

- A bookmark filed under a mistyped Location number stayed folded away when
  you came back to it. RhinoData now also unfolds, on open, every location
  with a bookmark within 5 km (`scan.UNFOLD_M`) of the Status.json position,
  whatever number it carries. Live system only, needs a position; bringing
  the window to the front does not unfold, so a hand fold stays.

## 5.7.8

**Fixed**

- A Spansh answer after the honk brought RhinoData to the front and took the
  focus from the game (`main._add_spansh` went through `scan.show`). Now only
  the rail is rebuilt in place (`scan.refresh_rail`); a full redraw only when
  the picked body changes with it. Nothing opens when the window is closed.
- Docs pictures re-rendered.

## 5.7.7

**Added**

- RhinoData's Mined column and the card's tons line update 5 s
  (`main.QUIET_S`) after the last ton counted into a bookmark; by-products
  and unplaced tons do not restart the wait. Set in place (3 ms measured),
  not a redraw.

**Fixed**

- Picking a bookmark rebuilt the whole window and flickered: now two rows are
  relit and the card pane rebuilt (35 ms against 176-212 ms for the window).

## 5.7.6

**Added**

- The map above a bookmark's card marks the picked bookmark with a blue diamond,
  drawn on a Tk canvas over the cached picture: a pick costs no re-render.

**Changed**

- RhinoData opens with every location folded but the one you are at: the
  panel's Location, and the location of a bookmark within 175 m of the SRV.
  Was every location unfolded. `scan._state["opened"]` replaces `"collapsed"`.

## 5.7.5

**Added**

- Material menus (panel, RhinoData filter, Edit dialog): with the menu open, a
  letter highlights the first material starting with it (Enter picks it), or
  picks it when only one does. Windows menu mnemonics (`scan.letter_jump`); the
  panel's "select material" takes none.

**Changed**

- Ctrl+Alt+B before Ctrl+Alt+Z keeps the point (`border_at`, saved with the map)
  instead of refusing: nothing is clipped, the hint says "border kept - set
  center", and Ctrl+Alt+Z turns it into the border measured from the centre.

## 5.7.4

**Added**

- Settings: Golden circle radius, 500-2500 m in 250 m steps (`rhinospotter_golden_m`),
  default 1250. Applied at start and on OK, to the gold circles and to RhinoData's order.

**Changed**

- RhinoData lists a location's bookmarks in clusters: the one with the most rigs,
  then every one within the golden radius of it by rigs, repeated on the rest;
  worked out last. Was marking order.
- Golden groups are those clusters (`coverage.clusters`): 5+ rigs, or 4+ when no
  cluster on the map reaches 5. The circle sits on the spot with the most rigs.
  Was any point within 1.5 km; groups overlapped and counted spots twice.
- Default golden radius 1.5 -> 1.25 km: at 1.5 km the ship dropped out of sight.
- The picked body in the RhinoData rail: name bold in gold, the accent bar gone.

**Fixed**

- The map above a bookmark's card and the dock picture fed every bookmark on the
  body to the golden groups, not only the ones the map reaches: another location's
  5-rig cluster kept this map's circles off it. Now as Share map.

## 5.7.3

**Added**

- RhinoData marks the bookmark the SRV is at (SRV only): within 175 m
  (`yields.ATTRIBUTE_M`) its row gets a ◉, its location unfolds and the card
  shows it, so Mark depleted is one click. Checked when the window opens and
  when it comes to the front (`<Activate>`); redrawn only when that bookmark
  changed, and a bookmark picked by hand in the meantime stays picked.
- A Depleted mark 14 days old (`yields.REGEN_DAYS`, assumed) comes off on its
  own, at start and on every jump; an Amount of Depleted (also one read off
  the HUD at marking) becomes unread. The mark's date is kept in `regrown`,
  and the log names each bookmark it took off.

**Changed**

- An open cycle ends as `expired` 14 days after its first ton if nobody
  marked the deposit depleted; the next ton opens a new cycle. Expired cycles
  never count as a measurement.
- Mined column: the tons of the current cycle. The card keeps what the
  deposit held - min-max over measured cycles, or at least the largest cycle.
- `rs_tests/make_docs_images.py` refuses a grab when another program's window
  covers it.
- Minimap: a disc of new ground redraws only the layer around it, not the
  whole 20 x 20 km layer. Median per disc 93 -> 19 ms at 640 px, 53 -> 11 ms
  at 480, 8 -> 2 ms at 180. Pixel-identical to a full redraw and to 5.7.2
  (`rs_e2etest/layer_e2e.py`, 26 saved maps).
- README shorter, one screenshot a feature; `docs/API.md` technical only.

## 5.7.2

**Fixed**

- Share bookmark and Copy coords set the status line in place instead of
  redrawing the whole RhinoData window: the window flickered on every press.
- The clipboard import retries on the next 1 s poll when another program has
  the clipboard open; that change was skipped for good before.

## 5.7.1

**Added**

- Card: **Share bookmark** in place of Share map (Share map stays on the
  location line). Puts `RhinoData:<code>` on the clipboard; a running
  RhinoSpotter that finds a code on its clipboard imports it. Not imported:
  codes shared or imported before by this install (SHA-256 digests in `meta`)
  and bookmarks already here (same material within 100 m). No commander, dates
  or tons in the code. The clipboard text is read only when Windows'
  clipboard sequence number moves.
- Bookmark table: Brg and Dist columns - bearing and distance from the centre
  of the saved map the bookmark lies on, set with Ctrl+Alt+Z. `-` with no map
  there or no centre set.

**Changed**

- Tons count only into a bookmark of the material refined, within 175 m.
  By-products are no longer written to the bookmark; they are counted and
  logged at shutdown as `t by-product not counted`. Cycles written by 5.6.9
  keep their by-product tons in Mined.
- Bookmark table: Material column 22 -> 17 characters, and Edit is packed
  before the labels, so a narrow pane clips Est. left instead of the button.
- Bookmark table header in Consolas 9, as the rows: at 8 it drifted left of
  the columns it names.
- The four card buttons under Guide me there are one width (2 x 2 grid).
- Copy coords and Share bookmark write the clipboard through Win32: Tk's
  clipboard text was gone once EDMC closed.
- `mining_sheet.json`: 1005 locations (was 992; 13 more rock 80%+ metallic
  magma) and the prices of 2026-09-24.
- Docs pictures re-rendered.

**Fixed**

- A list's scroll restore is scheduled on the Tk root, not its canvas. Two
  redraws back to back raised `TypeError: <lambda>() missing ... 'event'`.

## 5.6.9

**Added**

- Tons collected at a bookmark, from `MiningRefined`: 1 event = 1 t, to the
  nearest bookmark within 175 m on that body, material match before distance.
  By-products under their own name. Tons with no bookmark in range, or no
  Status.json reading, are counted and logged at shutdown.
- Cycles: first ton to the Depleted mark, holding the rigs, Density and Amount
  at the open. One opened at Amount High and closed depleted is the deposit's
  capacity; two give its min-max. A depleted spot mined again opens a new one.
- Bookmark table: Mined column - the best measured cycle, or ≥ the tons so far.
- Card: tons collected, capacity, and days since the Depleted mark against
  `yields.REGEN_DAYS` = 14, assumed, not measured.
- `python -m rs_core.yields`: t/rig per Density band against
  `deposit.TONS_PER_RIG`. Prints, never writes.

**Changed**

- The location map's picture cache keys on the bookmark fields it draws, not
  `database.revision()`: a yield write every 30 s threw the 70-160 ms repaint
  away.
- `spotcard.save` keeps dict and list values instead of `str()`-ing them. An
  Edit or a re-mark turned `yield` into a string every later read raised on.
- `cards.edited` / `cards.updated` re-read `yield` off the row; Amount Depleted
  set there closes the cycle, as the Depleted button does.

## 5.6.8

**Fixed**

- An open RhinoData window did not show a bookmark just made until it was clicked. It redraws after every saved or updated bookmark, without coming to the front.

## 5.6.7

**Changed**

- Golden circles are at most 1.5 km in radius. The 2.5 km limit picked the members but not the circle, which sits on their centroid and was drawn up to 3.4 km (HIP 44291 4 a). A group whose circle would exceed 1.5 km is dropped; a smaller one inside it can still show.

## 5.6.6

**Fixed**

- An open RhinoData window kept showing the system it was opened in after a jump. It redraws on FSDJump, CarrierJump and Location now, without coming to the front; a system picked in the search box stays shown.

## 5.6.5

**Fixed**

- The map on the Bookmarks page circled every golden group; it shows the best 3 by Cr/h now, as Share map and the minimap do.

## 5.6.4

**Fixed**

- A moved Saved Games folder was not found: Status.json and the journals were looked for under `%USERPROFILE%\Saved Games`. The path was fixed at import, ~1.4 s before EDMC's monitor starts. Now looked up once a start, in order: the folder EDMC watches, the one typed in EDMC's settings, EDMC's default (the Saved Games known folder), then `%USERPROFILE%`. Kept once EDMC's monitor answers.

## 5.6.3

**Fixed**

- `replay.py --rebuild` replaced each cached body with the journal's, dropping Spansh's location counts; it merges now, journal fields over the cache.
- `replay.py --testmode` replaced the whole system, dropping cached bodies the journals did not name; merged the same way.
- `replay.py` with the database locked read an empty cache and saved over it, wiping the system, then printed "rebuilt N" and exited 0. The system is left as it was, printed as FAILED, exit code 1.
- `rs_api.revision()` did not move when a depleted mark was taken off or a bookmark edited unless it was the newest row. It is a CRC over every row now: 0.6 ms at 62 bookmarks, 11 ms at 5,062.

**Changed**

- UI and flow tests are end to end in `rs_e2etest/` (minimap, hotkeys, update, migrate/replay/API); the unit tests they replaced are gone.

## 5.6.2

**Changed**

- Minimap and guide arrow re-send `HWND_TOPMOST` at most every 5 s while standing still; at once on a move, a re-show or after a failed send. The arrow's Tk `-topmost` + `lift()` every 500 ms is gone. Mitigation until exclusive fullscreen is tested against a window raised over it every tick.

## 5.6.1

**Fixed**

- Minimap fell behind Elite after another window (e.g. a shared map picture) took the front, and stayed there. `SetWindowPos(HWND_TOPMOST)` was sent untyped and refused with error 1400 on every tick since it was written; it is typed now, and the lift that ordered the map against Elite's window - putting it behind - is gone. Same fix for the guide arrow.

## 5.6.0

**Changed**

- **Place the map** shows the map with Settings open, in the SRV or not. Drag it anywhere, any monitor; double-click or Esc locks it.
- Free move: position saved as screen pixels, clamped to the nearest monitor. No longer follows the game window. Free move off: game-window corner as before.

## 5.5.1

**Added**

- **The ground under the map is lit.** One heightfield a ground family, shaded by a sun at 315 degrees, 34 degrees up: craters with rims and ejecta apron, fracture networks, snow lying on the flat and in the hollows with blue ice in the wind scours, ore veins on the metal grounds. Made in EDIntel's `lab/radar_backgrounds/hifi.py` with numpy and scipy; what ships is a picture, so the plugin still loads it with PIL alone.
- **The saved map picture is drawn on that ground too**, where it was a plain dark field before.
- **The picture carries the three best golden groups, priced.** Every group of bookmarks within 2.5 km whose rigs add up to five was circled; now the best three by credits an hour are, each labelled with what a trip takes out - 11 t a rig position at that spot's median price. The hour is 300 s a spot (12 pieces, one every 25 s, the rigs at a spot running together) plus the drive round its members at 25 km/h.

**Changed**

- **Share map** draws the picture again on every press. It opened the saved PNG before, so a location marked or worked out since kept the picture it was saved with.
- Textures ship as JPEG at quality 90, no chroma subsampling: 2.3 MB against 15.1 as PNG, within 3 of 255 a pixel at the size the map draws them, and 19 ms to decode against 80. The PNG set from before is deleted at startup once the JPEG is in place - the in-plugin update replaces the whole folder anyway, this is for an install unzipped by hand.
- The settings tab lays its rows out by counter, and a test builds it. Two widgets went into the same row when one was inserted by hand.
- 5.5.0 was withdrawn minutes after it went up; this is that release with the textures at a tenth of the size and the Ground switch dropped.

## 5.4.0

**Added**

- **Search a system** in RhinoData. A box at the top of the rail, over the system name, listing the systems you hold bookmarks in - three letters before it answers, three matches at most, most recently marked first. Picking one shows that system's bodies and bookmarks, read from the body cache, so it works with the ship parked anywhere. A green **Back to \<system\>** under the name returns to the one you are in. Bookmark is untouched by it: marking always lands in the system the journal says you are in, never the one being looked at.

**Fixed**

- **Share map** on a location whose map had no picture did nothing visible. The PNG is written when the SRV goes back in the ship, so a drive that ended any other way left the points in the database and nothing to open - and the only sign was a line at the foot of the middle pane. The picture is now drawn from those points on the press, saved, and opened.
- **The minimap blinked once a second when the game was over it.** Getting back above a borderless Elite was two calls, out of HWND_NOTOPMOST and back in, and between them the map is not topmost - so the game was composited over it for that frame. It is one `SetWindowPos` against the game's own window now, which also fixes it not sticking: re-entering the topmost band does not put you at the front of it, ordering against a named window does.
- That lift logged at INFO on every tick - 2,010 lines in one day. It is debug, and only when the state changes.

## 5.3.1

**Fixed**

- The panel's **Material** box and RhinoData's material filter were one control. Picking a material to bookmark refiltered the window, and mining anything on the ground refiltered it again through the prefill - the window jumped to gold because a by-product was refined. They are two variables now: the box names the next bookmark, the picker under the system name narrows the window, and neither touches the other.
- **All** is gone from the panel's Material box. It was only ever the way back out of the filter; a bookmark cannot be named "All", and pressing Bookmark with it selected was refused anyway. The RhinoData picker still carries it.

**Changed**

- `mining_sheet.json` refreshed: 992 mining locations, up from 928. Scorpii Sector MC-V a2-3 8 a, an icy body, added 19 of them. No material crossed the 50,000 Cr/t line, so the default dropdown is the same 18.

## 5.3.0

**Added**

- **Edit** at the end of a deposit row opens the bookmark for correction: material, rigs, amount, density and location. Coordinates, heading and the time it was marked are readings taken at the press and stay as they were; the dialog shows the coordinates but does not offer them. Closes #4.

**Changed**

- Standing on a deposit and pressing Bookmark again now updates the rig count as well as Amount and Density. Rigs is the field guessed at the first mark - you set 4 and the deposit turns out to hold 3 - and until now a re-mark could not correct it. Each field is only taken when set, so an empty Rigs box or a picker left at "-" still wipes nothing.
- Comments and docstrings converted to a technical register in `grounds`, `palette`, `names`, `atomic`, `logging`, `paths`, `deposit`, `spotcard`, `guide` and `cards`. The rule is in `CLAUDE.md`; the remaining modules follow.

## 5.2.1

**Changed**

- The settings switch reads **Show materials under 50,000 Cr/t**. It was "Offer the low value ones too - under 50k Cr a tonne at their best ground", which described the idea rather than the control.

## 5.2.0

**Added**

- **Offer the low value ones too**, on the settings tab. Off by default: the Material dropdown, the picker in RhinoData and the rates line under a body carry only materials worth 50k Cr a tonne or more at their best ground - 18 of them. On, all 38. The switch never touches a bookmark that already names a cheap material, its card, or its code on the minimap; it decides what can be picked, not what was.
- Picking a bookmark draws the saved map it lies on over its card, above the buttons: the ground driven around it with every bookmark of the body on it, no title and no legend. Of the maps that reach the bookmark it is the one whose centre is nearest - the same tie the Mapped tab counts with. A bookmark on no saved map leaves the card as it was.

**Fixed**

- Bromellite had no price and so no code on the minimap: its dots were the only unlabelled ones. No mining location read so far has carried it, so the sheet has no rows to take a median from; its galaxy-wide average sell price, 33,396 Cr, stands in until one does. That puts it in the low value half.
- Palladium was missing from the Material dropdown. It pays 53k and could not be bookmarked at all. The list is now every material the mining sheet prices plus bromellite, which is minable and has no rows yet, instead of a short list kept by hand beside it.

**Changed**

- Deuterium, jadeite, magnesite, olivine, osmium and quartz pyroxenite were in the dropdown and are under 50k, so they are hidden until the new switch is on - unless you already have a bookmark naming one, or are mining it right now. Both stay pickable whatever they pay: a second mark is matched to the first on the material's name, so a name the dropdown cannot produce is a bookmark that can never be refreshed, only duplicated.
- Long names are shortened where a column cannot hold them: Methanol Monohydrate Crystals reads Monohydrate. Low Temp Diamonds now abbreviates to LTD as it always said it would - the short-name table knew two older spellings of it and not the one in use.
- A ground whose every material is under the line says so, instead of "nothing measured on this ground yet", which was a measured ground calling itself unmeasured.

## 5.1.1

**Added**

- `rs_api.bookmarks()` carries `planet_radius`, asked for by ED Hotspots Finder: with it a reader can measure the distance between two marks the way this plugin does, in metres over the sphere, instead of in degrees. `None` on bookmarks made before the plugin recorded it - about a third of an older commander's marks.

**Changed**

- The Rigs box stops at 10. It went to 12, which is not a number anyone can enter in the game; 6 is the standard deposit and 7 is rare.

## 5.1.0

**Added**

- **Free move** for the minimap: Settings -> Place the map takes the mouse for a moment, you drag it where you want it, then double-click or press Esc. The position is kept as an offset from the game window, so moving or resizing Elite takes the map with it, and it is pulled back inside if the window shrinks. The corner setting still rules when Free move is off. A hover handle was the obvious design and cannot work: the window is click-through, so the mouse passes through it to the game and it never feels a hover.
- `rs_api.py`, a read-only interface for other tools: `bookmarks()`, `bodies()`, `revision()`, `version()`. Works inside EDMC and from a separate program, imports neither EDMC nor Pillow, and opens the database `mode=ro` so a reader cannot lock the plugin out, change anything or create a database by reading too early. `rs_api.SCHEMA` is 1: keys are added, never removed. See docs/API.md. Two projects were reading the plugin's storage directly and broke when it moved from JSON files to a database; this is the part that does not move.
- The settings tab has a picture in the README.

**Fixed**

- The journal folder is EDMC's answer, not a path spelled out here. `monitor.currentdir` first, then the `journaldir` setting, then the Windows default. A moved journal folder, a second install or a synced profile used to read as "not flying".

## 5.0.1

**Fixed**

- The minimap went behind the game on the way back from an alt-tab and stayed there. The map and a borderless game are both topmost, the last window raised wins that group, and asking for HWND_TOPMOST while already topmost does not reorder inside it. The map now checks every tick whether Elite sits above it and drops out of topmost and back in when it does.

**Changed**

- The plugin logs at info rather than warning. The nine info lines are once-per-event - the map going down and coming back with the reason, a guide starting and closing, a migration - and "the map vanished and I do not know why" used to need RHINOSPOTTER_DEBUG=1 and a restart to answer, by which time the state that hid it was gone.

## 5.0.0

**Changed**

- RhinoData is one window with three panes instead of three pages with a Back button: the bodies of the system on the left, the bookmarks of the picked body in the middle, the picked bookmark on a card to the right. Nothing navigates away, so there is no Back anywhere.
- The window opens at 60% of the screen and keeps that size; it no longer measures its content and resizes on every step.
- Bookmarks fold into their mining locations. A location line says how many deposits it holds, which materials, how many are worked out, how far the nearest one is, and carries its Share map. Fold all / Open all sits over the table.
- The card holds what the row used to: coordinates, heading, distance, the HUD reading, the tons-left estimate, what the material is worth on that ground, and the buttons - Guide, Share map, Mark depleted, Copy coords, Delete. Copy coords is new.
- The card follows what is open: the picked bookmark while its location is unfolded, otherwise the first deposit of the first open location, otherwise nothing.
- Bookmarks and Mapped are tabs on the body, not separate pages. Every map row is selectable on its own, including maps tied to no location.
- The rail carries each body's distance in Ls, its location count and its bookmark count; the material filter drives all three.
- The materials line under a body is green for a material that body already has a bookmark for. A picked material leads the line whatever its rate.
- Long material names are shortened where a column or a sentence cannot hold them: Low Temperature Diamonds to LTD, Periclase Dunite to P. Dunite.
- The bookmark rows lost their Distance column - the location line carries the nearest, and Guide answers the rest.

**Fixed**

- The wheel scrolls whichever list the pointer is over, and puts back whatever EDMC had bound to it.
- A click no longer sends either list back to the top.
- The material filter no longer changes what counts as mapped: a map is driven ground, not a material.
- Stop the arrow is reachable from the body heading whenever an arrow is up, whatever the card is showing.
- The window gives up being topmost as soon as the game is clicked back into. It used to stay in front until it was closed: the FocusOut that was meant to release it lands on whatever button inside the window had the focus, not on the window.

## 4.7.2

**Changed**

- Only the Rhino paints and shows the minimap; the Scarab and Scorpion paint nothing. The SRV type comes from LaunchSRV and is kept in EDMC's config for a login inside the SRV; with none known the SRV counts as the Rhino.
- Minimap switched off in Settings: not shown and nothing recorded. Switching it on is a new launch: a map within reach carries on, otherwise a new one starts.

## 4.7.1

**Fixed**

- Settings tab missing since 4.6.0: the hotkey rows mixed pack and grid inside EDMC's frame, Tk refused, and EDMC dropped the whole tab.

## 4.7.0

**Added**

- Minimap ground textures by body type: icy, rocky ice (half ice, half rock), rocky (rock 80%+), high metal content (35% metal on rock), metal-rich. Bodies with no known ground keep the plain background.
- Textures ship as PNGs in `texture/`; loaded once per body and zoom (75-89 ms), redraws stay at 14-15 ms.

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
