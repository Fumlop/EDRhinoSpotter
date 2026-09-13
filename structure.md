# RhinoSpotter - Project Structure

## Overview

An EDMC plugin for Elite Dangerous surface mining. Two things it does: render
the patch you are standing on as a PNG card, and tell you which bodies in this
system are worth landing on.

The split that matters: **nothing in `rs_core` imports tkinter, and nothing in
`rs_ui` does real work.** That is what lets `rs_tests` run the logic under a
bare interpreter, with no EDMC, no display and no game.

## Directory Structure

```
RhinoSpotter/
├── load.py              EDMC lifecycle hooks, and nothing else
├── rs_core/             everything that is not a widget
├── rs_ui/               everything that is
├── rs_tests/            pytest suite, 239 checks
├── ground_rules.json    the mining sheet, frozen when the plugin was packaged
├── cards/               rendered cards (gitignored)
├── data/                screenshots and sidecars (gitignored)
├── lib/                 vendored, unused, gitignored - see below
├── docs/                screenshots for the README and INSTALL
├── INSTALL.md
├── pytest.ini
├── README.md
├── CHANGELOG.md
└── structure.md         this file
```

## Entry point

- **[load.py](load.py)** - the EDMC contract. `plugin_start3`, `plugin_app`,
  `journal_entry`, each forwarding to `rs_ui.main`. Kept this thin on purpose:
  EDMC reloads this file, and a file that only forwards cannot break in a way
  that needs EDMC restarted to diagnose.

## Core (`rs_core/`)

No tkinter anywhere in here.

- **[spotmark.py](rs_core/spotmark.py)** - Status.json -> one marked spot.
  Status.json is live-only: position and the targeted mining location vanish
  the moment you fly off, so it is read once, at the press.
  `location_index()`, `read_status()`, `mark()`, `on_surface()`, `MATERIALS`.
  `nearest_index()` reads the same location out of a `Touchdown` or `Liftoff`
  instead, which is where it survives the moment Status.json forgets it.
- **[spotcard.py](rs_core/spotcard.py)** - one spot -> a JSON bookmark. Looks
  nothing up. `save()`, `filename()`, `_free()` (a repeat mark is a second
  bookmark, not a replacement), `CARDS_ROOT`, and `_font()` for the map
  picture's text. It drew a PNG card until the map picture replaced it.
- **[grounds.py](rs_core/grounds.py)** - what a body is, and what that kind of
  body holds. `classify()` turns a journal Scan into one of eight grounds;
  `Sheet` reads `ground_rules.json`. The classifier mirrors the CASE in
  the classifier the sheet was measured with, so a body lands in the bucket its percentages
  were measured on.
- **[bodies.py](rs_core/bodies.py)** - `Register`, the landable bodies of the
  system you are in. Fed one journal event at a time, returns True when the
  list changed. Reads `Scan` for the ground, and `FSSBodySignals` /
  `SAASignalsFound` for how many mining locations a body carries - the FSS
  already knows, no probes needed. Counts are kept beside the bodies because a
  signal can arrive before its scan, and the system name is taken from any
  line EDMC hands over rather than only from a jump. One system at a time:
  arriving asks
  `on_arrive` what is already known and starts from that, every change goes
  straight to `on_change`, and what came off disk is never written back.
- **[store.py](rs_core/store.py)** - one JSON file per system under
  `%LOCALAPPDATA%\RhinoSpotter\data\`, beside the cards and outside the
  plugin folder for the same reason they are. EDMC replays the journal file it
  is watching and nothing older, so a system honked last week is otherwise
  gone. Written through a temp file and a rename: EDMC can be closed at any
  moment, and a half-written cache that still parses is worse than none.
  `Debounced` is what the panel hands the register instead of `save`: a honk
  is one change per body and all of them rewrite the same file, so the first
  starts a two-second timer and the last one before it fires is what gets
  written. The timer is not restarted by the changes after it - a sweep longer
  than the delay is written as it goes rather than held until it ends - and
  `flush()` at plugin_stop means a normal shutdown loses nothing.
- **[coverstore.py](rs_core/coverstore.py)** - the minimap's maps under
  `%LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map N.json.gz`, a folder per
  body and a file per map, so a save never merges. The points that painted new
  ground, and the center once one is set, lat/lon to six decimals, gzipped: an hour's drive
  is about 2.4 KB. Plain `.json` is read too. A file that will not parse is
  skipped and logged. `map N.png` beside it is written, never read.
- **[replay.py](rs_core/replay.py)** - recent journals through the same
  Register the live plugin uses, and a score for what they found. Every
  landable body is worth the best rate its ground has ever shown and the
  system is worth the sum, because the question is not "is there something
  here" but "is there enough here". `--testmode` writes the winner to the
  cache - see below.
- **[update.py](rs_core/update.py)** - the version number, and whether there
  is a newer release. `VERSION` here is the one source; the changelog repeats
  it as its top heading and a test fails if the two drift. Releases are tagged
  on GitHub, and the update check compares against the newest tag there - read
  from the releases/latest redirect, not the API, and repeated hourly. Also
  puts a release in place, if there is one. The zipball is extracted to a temp folder inside the
  plugin and copied in a second pass, so a truncated download cannot leave
  half a plugin behind. `KEEP` names what an update may not overwrite -
  `ground_rules.json` above all, because a locally refreshed sheet is newer
  than the one in a release.
- **[coverage.py](rs_core/coverage.py)** - the minimap's painting. Every
  Status.json fix in the SRV stamps a 2 km disc onto a 400 x 400 mask, 50 m
  a pixel, anchored at the first droppoint and reaching 10 km either way.
  `recenter()` moves the anchor to where the player pressed the hotkey and
  repaints the mask from the saved points. `follow()` decides when a launch is
  the same map (same body, inside the mask) and moves the droppoint, and when
  it is a new map. A disc that paints nothing new does not move `version`, and
  the drawn layer is only rebuilt when `version` or the ring centre changes -
  a tick is a crop of that layer and
  a cached chevron. Longitude is wrapped, so a body across the 180th meridian
  is one map. Painted means driven within range: nothing the game writes says
  a scan happened.
- **[arrow.py](rs_core/arrow.py)** - the guide arrow, as a picture. Two faces
  either side of a fold, drawn with PIL at four times the size and resized
  down, which is where the smooth edge comes from - the Tk canvas has no
  anti-aliasing and a shaded triangle drawn there reads as a broken shape
  rather than as depth. One frame per five degrees, rendered the first time
  that angle comes up and kept: 3.8 ms for a new angle, 0.34 ms for one
  already seen.
- **[names.py](rs_core/names.py)** - the one filename rule. The cards folder,
  the card itself and the system cache all need a name Windows will take, and
  they used to have three copies of the loop that makes one.
- **[cards.py](rs_core/cards.py)** - which bodies in a system have been
  marked, read from the JSON bookmarks rather than the file names. A name has
  had its spaces replaced and its material lowercased, so reading a body back
  out of one is a guess; a PNG without JSON is skipped rather than guessed at.
  An old card's PNG is kept on the record as `path` when it is still there.
  `ordered()` is the order a body's bookmarks are read in: most rigs first,
  uncounted ones last; `delete()` removes one, JSON and any old PNG at once;
  `set_depleted()` writes or removes `depleted_at` in the bookmark's JSON.
- **[measure.py](rs_core/measure.py)** - area and rig count for a border
  driven in the SRV. Shoelace for the area, ray casting for what is inside,
  and a 76 m grid for the rigs. Flat earth on purpose: a spot is a few hundred
  metres across on a body a thousand kilometres in radius, and that error is
  smaller than the error of having driven the border by eye. `closure()` is
  what says whether a reading is worth anything - a border that does not close
  still gets a plausible-looking area. Nothing calls it: the code works and is
  tested and has no caller until there is a decision about where it belongs.
  Kept because the minimap wants the same projection.
- **[guide.py](rs_core/guide.py)** - one Status.json and one bookmark into one
  arrow: `bearing()`, `distance()`, and `fix()` which says what the overlay
  can draw. Great circle, not the flat earth measure.py uses - a patch is
  metres across and flat is right for that, but guiding starts in orbital
  cruise. Every case that is not an arrow is its own state, because "wrong
  body" and "too high for coordinates" look identical from the cockpit and
  want opposite actions.
- **[palette.py](rs_core/palette.py)** - the colours, once. Hex for tkinter,
  RGB tuples for PIL, one conversion function between them so the window and
  the cards cannot drift apart. They used to be two schemes and looked like
  two tools.
- **[logging.py](rs_core/logging.py)** - one logger, named so EDMC picks it up.

## UI (`rs_ui/`)

Everything in here imports tkinter.

- **[main.py](rs_ui/main.py)** - the panel EDMC draws, and the handful of
  variables that only make sense while a window is open. Both buttons live
  here. Create Card doubles as the update button: it reads "Update" when a
  release is out, then "Restart EDMC" once it is in. A third button would
  widen the panel on the one day it matters, and a permanent one every day. The bookmark write and the update check run off the UI thread and come
  back through `_frame.after`, because Tk is not thread-safe and a widget
  written from a worker fails minutes later somewhere unrelated.
- **[hotkey.py](rs_ui/hotkey.py)** - Ctrl+Alt+Z and Ctrl+Alt+B, registered
  with RegisterHotKey on a thread with its own message loop, since the game
  holds the focus while you drive. A press is bounced to Tk and sets the map's
  center or border. A combination already held elsewhere is a logged warning;
  the other still registers.
- **[overlay.py](rs_ui/overlay.py)** - the arrow over the game. A borderless
  always-on-top window keyed to a colour it then makes a hole of, so only what
  is drawn shows, and click-through on top of that - a shape over the cockpit
  that eats a click will eat the wrong one. Parked at the top middle of the
  Elite window and re-placed every tick, because the game gets moved, and told
  it is topmost again on every one of those, because a game going fullscreen
  takes the top of the Z-order with it. Hidden while Elite is not the
  foreground window (`game_focused`, shared with the minimap), shown again with
  SW_SHOWNOACTIVATE so coming back does not take the game's focus; a message's
  ten seconds start again after an alt-tab, and run out with no game at all.
  Foreground is matched on the title prefix `Elite - Dangerous`, as EDMC does. Polls Status.json twice a second; guiding
  outlives the scan window, which is why it hangs off the root and not off the
  window that started it. It draws `rs_core.arrow`'s frames through PNG bytes
  rather than PIL's ImageTk, which is the one part of PIL that EDMC's build
  cannot be relied on to carry. A window it cannot build is logged and
  skipped - the bookmark list works without an arrow over the game.
- **[scan.py](rs_ui/scan.py)** - the RhinoScan window, in two views: the
  body list, and the bookmarks of one body with Back at the top left. One
  window, rebuilt rather than stacked - the bookmarks are a step into the row
  you clicked, not a second thing on the screen. Read-only and disposable:
  nothing is saved from it, so pressing the button twice costs
  nothing. Given a material it lists only the ground that has ever carried it,
  and that material leads every group whatever its rate - the question has
  changed from "what is here" to "where is the jadeite", and a ground that
  answers at 4% still answers.
- **[minimap.py](rs_ui/minimap.py)** - the minimap window and its settings
  tab. No timer of its own: `main._poll_landed` hands it the Status.json it
  already read, and nothing raises back into that poll. Shown while the InSRV
  flag is set, hidden otherwise and while the game is minimised, sized from
  the game window's height and parked in the corner picked under EDMC
  Settings (`rhinospotter_minimap_enabled`, `rhinospotter_minimap_corner`).
  Built once, hidden, and made click-through and no-activate before it is
  first shown; then shown, moved and hidden with Win32 calls that do not take
  the foreground, because it comes up mid-game on its own. A draw that raises
  keeps it down until the next launch. Saves through `coverstore`: new ground
  goes to a two-second `store.Debounced`, flushed when the map changes, when
  the SRV docks and at plugin_stop; docking also draws `coverage.picture` on a
  thread. The settings tab counts the saved maps and opens their folder.
  Bookmarks on the body are drawn as dots, read from the card sidecars again
  when the cards folder's modified time moves, and every ten seconds.

## Tests (`rs_tests/`)

`pytest` from the plugin folder. 351 checks, no network, no game, no display.

- **conftest.py** - puts the plugin folder on `sys.path`, and builds Scan
  events carrying only the fields the code reads. The `sheet` fixture is a
  small hand-written table, never the shipped `ground_rules.json` - that file
  is regenerated from live data and its numbers move.
- **test_grounds.py** - every bucket against real PlanetClass strings, and a
  Sheet whose file is missing or broken.
- **test_bodies.py** - tracking, arrival, ordering. Includes the two that are
  easy to get wrong: `Location` on game start must not empty the list, and a
  later detailed scan must replace what the honk recorded.
- **test_spotmark.py** - Status.json parsing, including a read landing
  mid-write.
- **test_bodies.py** also covers arriving: a known system arrives filled, new
  scans add to it rather than replace it, and what came off disk is not
  written straight back.
- **test_measure.py** - a square of known size, an L to prove the shape is
  the shape and not its bounding box, and a parked SRV adding nothing.
- **test_guide.py** - the four compass corners, a degree of latitude against
  the number measure.py uses for the same thing, a heading turned into a left
  turn rather than a bearing, and every state a reading can end in.
- **test_arrow.py** - that an angle lands on the nearest frame and wraps, that
  the frame is the key colour everywhere the arrow is not, that the two faces
  are two colours, and that no colour shaded down can land on the key colour
  and punch a hole through its own arrow.
- **test_coverage.py** - one stamp is one disc, a drive is a strip, driving
  back over it moves nothing, the mask edge clips without counting as new
  ground, the 180th meridian, when a launch keeps the map and moves the
  droppoint and when it is a new map, centring and its round trip, a ship hop painting nothing, the
  window-height clamp, north up, and the layer kept until new ground is
  painted. Saved maps: the points repaint the same mask, a launch within reach
  carries the last saved map on (nearest on a tie), one out of reach starts a new one.
- **test_coverstore.py** - gzipped round trip, plain JSON read, a broken or
  other-version file skipped, `map N` numbering, and the settings-tab count.
- **test_names.py** - every character Windows refuses, spaces kept for a folder
  and replaced for a file, and that the cache and the cards folder spell one
  system the same way.
- **test_palette.py** - that the window draws from the one palette, and
  that a colour which is not six hex digits raises rather than silently
  becoming black.
- **test_replay.py** - which files count as recent, that a second visit does
  not lose the first, and that a ground the sheet never measured is worth
  nothing rather than guessed at.
- **test_store.py** - round trip, system names Explorer refuses, an older
  cache shape, that no temporary file survives a save, and the debounce: a
  burst is one write, the last change is the one written, flush takes the
  pending write with it, and a burst longer than the delay still reaches disk.
- **test_update.py** - version comparison, that every network failure is the
  same silent no-answer, and the installer: a zip from somewhere else and a
  truncated download both change nothing, a replaced directory loses the
  module deleted upstream, and the exported sheet survives.

## Where the data comes from

| What | Source | Refreshed by |
|---|---|---|
| Bodies in this system | journal `Scan` events, via EDMC | the game, live |
| Mining locations on a body | journal `FSSBodySignals` / `SAASignalsFound` | the FSS, then a surface scan |
| Systems visited before | `%LOCALAPPDATA%\RhinoSpotter\data\<System>.json` | written on every change |
| What a ground holds | `ground_rules.json` | shipped with the release |
| What a location holds | nothing - it is in no feed | screenshot and read by eye |
| Where you are, while guiding | `Status.json` | the game, twice a second |

The last row is the whole reason this plugin exists.

## Test mode

    python -m rs_core.replay --days 3 --top 5              rank them
    python -m rs_core.replay --days 3 --testmode           stand in the best

The flag writes the winning system into the cache, so the next EDMC start
arrives in it without anyone flying anywhere. It is the only way to look at
the scan window over a system with four grounds in it rather than whichever
one you happen to be sitting in.

It writes the same cache the plugin writes, and the data is the commander's
own scans, so there is nothing to undo afterwards - the next real jump
replaces what is in the register anyway.

## lib/

`pg8000` and friends, vendored for a database path that no longer exists.
Nothing imports it. Gitignored rather than deleted until someone is sure.
