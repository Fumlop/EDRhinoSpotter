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
├── rs_tests/            pytest suite, 164 checks
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
- **[spotcard.py](rs_core/spotcard.py)** - one spot -> a PNG card. Looks
  nothing up, so it renders with nothing else running and no network.
  `render()`, `filename()`, `_free()` (a repeat mark is a second card, not a
  replacement), `CARDS_ROOT`.
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
- **[replay.py](rs_core/replay.py)** - recent journals through the same
  Register the live plugin uses, and a score for what they found. Every
  landable body is worth the best rate its ground has ever shown and the
  system is worth the sum, because the question is not "is there something
  here" but "is there enough here". `--testmode` writes the winner to the
  cache - see below.
- **[update.py](rs_core/update.py)** - the version number, and whether there
  is a newer release. `VERSION` here is the one source; the changelog repeats
  it as its top heading and a test fails if the two drift. Releases are tagged
  on GitHub, and the update check compares against the newest tag there. Also
  puts a release in place, if there is one. The zipball is extracted to a temp folder inside the
  plugin and copied in a second pass, so a truncated download cannot leave
  half a plugin behind. `KEEP` names what an update may not overwrite -
  `ground_rules.json` above all, because a locally refreshed sheet is newer
  than the one in a release.
- **[cards.py](rs_core/cards.py)** - which bodies in a system have been
  marked, read from the JSON sidecars rather than the file names. A name has
  had its spaces replaced and its material lowercased, so reading a body back
  out of one is a guess; a PNG without a sidecar is skipped rather than
  guessed at.
- **[measure.py](rs_core/measure.py)** - area and rig count for a border
  driven in the SRV. Shoelace for the area, ray casting for what is inside,
  and a 76 m grid for the rigs. Flat earth on purpose: a spot is a few hundred
  metres across on a body a thousand kilometres in radius, and that error is
  smaller than the error of having driven the border by eye. `closure()` is
  what says whether a reading is worth anything - a border that does not close
  still gets a plausible-looking area. Nothing in the panel starts a
  measurement: the code works and is tested, and has no button until there is
  a decision about where it belongs.
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
  widen the panel on the one day it matters, and a permanent one every day. The card render and the update check run off the UI thread and come
  back through `_frame.after`, because Tk is not thread-safe and a widget
  written from a worker fails minutes later somewhere unrelated.
- **[scan.py](rs_ui/scan.py)** - the RhinoScan window. Read-only and
  disposable: nothing is saved from it, so pressing the button twice costs
  nothing. Given a material it lists only the ground that has ever carried it,
  and that material leads every group whatever its rate - the question has
  changed from "what is here" to "where is the jadeite", and a ground that
  answers at 4% still answers.

## Tests (`rs_tests/`)

`pytest` from the plugin folder. 164 checks, no network, no game, no display.

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
- **test_palette.py** - that the card and the window draw the same black, and
  that a colour which is not six hex digits raises rather than silently
  becoming black.
- **test_replay.py** - which files count as recent, that a second visit does
  not lose the first, and that a ground the sheet never measured is worth
  nothing rather than guessed at.
- **test_store.py** - round trip, system names Explorer refuses, an older
  cache shape, and that no temporary file survives a save.
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
