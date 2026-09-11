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
├── rs_tests/            pytest suite, 116 checks
├── ground_rules.json    the EDIntel mining sheet, frozen at export time
├── cards/               rendered cards (gitignored)
├── data/                screenshots and sidecars (gitignored)
├── lib/                 vendored, unused, gitignored - see below
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
- **[spotcard.py](rs_core/spotcard.py)** - one spot -> a PNG card. Looks
  nothing up, so it renders with the database down and EDIntel unmounted.
  `render()`, `filename()`, `_free()` (a repeat mark is a second card, not a
  replacement), `CARDS_ROOT`.
- **[screenshots.py](rs_core/screenshots.py)** - the game's .bmp -> a cropped
  .jpg of the target panel plus a sidecar naming where it was taken. The panel
  lists a location's materials, which is in no journal event and on no feed.
- **[grounds.py](rs_core/grounds.py)** - what a body is, and what that kind of
  body holds. `classify()` turns a journal Scan into one of eight grounds;
  `Sheet` reads `ground_rules.json`. The classifier mirrors the CASE in
  EDIntel's `fetch_hit_rates`, so a body lands in the bucket its percentages
  were measured on.
- **[bodies.py](rs_core/bodies.py)** - `Register`, the landable bodies of the
  system you are in. Fed one journal event at a time, returns True when the
  list changed. Reads `Scan` for the ground, and `FSSBodySignals` /
  `SAASignalsFound` for how many mining locations a body carries - the FSS
  already knows, no probes needed. Counts are kept beside the bodies because a
  signal can arrive before its scan. One system at a time: arriving asks
  `on_arrive` what is already known and starts from that, every change goes
  straight to `on_change`, and what came off disk is never written back.
- **[store.py](rs_core/store.py)** - one JSON file per system under
  `%LOCALAPPDATA%\RhinoSpotter\data\`, beside the cards and outside the
  plugin folder for the same reason they are. EDMC replays the journal file it
  is watching and nothing older, so a system honked last week is otherwise
  gone. Written through a temp file and a rename: EDMC can be closed at any
  moment, and a half-written cache that still parses is worse than none.
- **[update.py](rs_core/update.py)** - is there a newer release. Checks and
  reports, never downloads: a plugin that replaces its own files while EDMC
  holds them open fails in ways nobody can debug afterwards.
- **[logging.py](rs_core/logging.py)** - one logger, named so EDMC picks it up.

## UI (`rs_ui/`)

Everything in here imports tkinter.

- **[main.py](rs_ui/main.py)** - the panel EDMC draws, and the handful of
  variables that only make sense while a window is open. Both buttons live
  here. The card render and the update check run off the UI thread and come
  back through `_frame.after`, because Tk is not thread-safe and a widget
  written from a worker fails minutes later somewhere unrelated.
- **[scan.py](rs_ui/scan.py)** - the RhinoScan window. Read-only and
  disposable: nothing is saved from it, so pressing the button twice costs
  nothing.

## Tests (`rs_tests/`)

`pytest` from the plugin folder. 116 checks, no network, no game, no display.

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
- **test_store.py** - round trip, system names Explorer refuses, an older
  cache shape, and that no temporary file survives a save.
- **test_update.py** - version comparison, and that every network failure is
  the same silent no-answer.

## Where the data comes from

| What | Source | Refreshed by |
|---|---|---|
| Bodies in this system | journal `Scan` events, via EDMC | the game, live |
| Mining locations on a body | journal `FSSBodySignals` / `SAASignalsFound` | the FSS, then a surface scan |
| Systems visited before | `%LOCALAPPDATA%\RhinoSpotter\data\<System>.json` | written on every change |
| What a ground holds | `ground_rules.json` | `python scripts/export/rhinoscan_data.py` in EDIntel |
| What a location holds | nothing - it is in no feed | screenshot and read by eye |

The last row is the whole reason this plugin exists.

## lib/

`pg8000` and friends, vendored for a database path that no longer exists.
Nothing imports it. Gitignored rather than deleted until someone is sure.
