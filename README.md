# RhinoSpotter

EDMC plugin for Elite Dangerous surface mining. Two buttons.

<p align="center">
  <img src="docs/plugin.png" alt="The RhinoSpotter panel in EDMC">
</p>

## RhinoScan - which bodies here are worth landing on

Press **RhinoScan**. A window opens listing the landable bodies of the system
you are in, grouped by what kind of body they are, with what that kind has
been found to hold above it.

<p align="center">
  <img src="docs/rhinoscan.png" width="620"
       alt="The scan window over an example system, four grounds and ten landable bodies">
</p>

*Example system. Percentages are the share of that ground's mining locations
that carried the material; `unprobed` means nobody has counted that body yet,
and those rows are dimmed. A body you have already marked shows how many
bookmarks it has - click and a page of them opens in your browser.*

### The bookmarks page

Clicking `3 bookmarks` writes a page beside the cards and opens it: one row
per bookmark with the location, material, rigs, heading, coordinates and when
it was marked, and the card itself alongside. Sorted by location, which is the
number on the target panel and the order a body gets worked in.

It is written fresh every time it is opened. The bookmarks are the truth and
the page is a view of them, so a stale one would be a bug waiting rather than
a cache.

### Filtering to one material

The **Material** dropdown does two jobs. It names what goes on a card, and it
decides what RhinoScan shows.

Leave it on **All** and the window answers "what is here". Pick a material and
it answers "where is the monazite" instead: only the ground that has ever
carried it is listed, and that material leads every group in blue, with its
rate for that ground.

<p align="center">
  <img src="docs/rhinoscan-filtered.png" width="600"
       alt="The same system filtered to Monazite: the metal ground is gone, and every remaining group leads with its monazite rate">
</p>

The metal-rich ground has gone - no monazite has ever been read on it. What is
left reads 45.6% on magma, 7.9% on silicate and 2.4% on quiet rocky ground,
which is the whole reason those three are separate groups rather than one
"rocky".

A ground listed because it carries something still says so at 2.4%. The rate is
what you decide on, and a low one you can see beats a low one that was hidden
for being low. A system where nothing carries it tells you that, rather than
opening empty.

**All** puts everything back.

### Where the data comes from

The bodies come from the journal. **The honk alone is not enough**: it finds
the bodies but does not describe them, and only a body the FSS has resolved
carries the planet class and volcanism this reads. Honk, then work the FSS - or
fly in and let the auto-scan sweep the near ones.

The location count comes from the journal too: the FSS reports it without you
flying out there, and a detailed surface scan confirms it. A body nobody has
counted says `unprobed` rather than `0 loc` - none found and none looked for
are not the same thing.

Systems are remembered. Every scan, count and jump is written to
`%LOCALAPPDATA%\RhinoSpotter\data\<System>.json` the moment it happens, so a
crash costs nothing. Jump back in later and the system arrives already filled;
anything you scan after that is added to it. Nothing is asked of EDSM or
anyone else's server - this is your own scan data going to disk and coming
back.

The percentages come from `ground_rules.json`, the mining sheet shipped beside
`load.py`. Neither half touches the network. Losing the JSON costs the
percentages, not the body list.

**These are rates, not contents.** What a mining location actually holds is in
no journal event and on no feed. This says where to prospect; it cannot say
what you will find.

## Bookmark - the patch you are standing on, as a PNG

<p align="center">
  <img src="docs/miningcard.png" width="620"
       alt="A mining card: body, material, rigs, location, heading, altitude and coordinates">
</p>

*Example card. Everything on it was read from `Status.json` at the press.*

1. Land and put the rigs down.
2. Pick the **Material**, set **Rigs**. `Location` fills itself when a mining
   location is the selected destination; otherwise type the signal number.
3. Press **Bookmark**. `completed` appears beside the button once the PNG is
   on disk.

Coordinates, body and location are read out of `Status.json` at the press - it
is live-only, so make the card before you fly off. Marking the same location
for the same material twice gives you two cards, not one overwritten.

Bookmarks land in `%LOCALAPPDATA%\RhinoSpotter\cards\<System>\`. The
**bookmarks** link in the panel header opens the folder in Explorer.

## Install

See [INSTALL.md](INSTALL.md). Short version: unpack into
`%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter\` so that `load.py`
sits directly inside, and restart EDMC.

When a newer release is out, **Bookmark** reads **Update** instead and the
status line names the version. Press it and the release is fetched and
unpacked in place, then it reads **Restart EDMC**. There is no third button:
the panel stays the same width in every state.

Your exported `ground_rules.json` is kept, and cards and scans are never
touched - they live under `%LOCALAPPDATA%\RhinoSpotter\`, not in the plugin
folder.

## Seeing it without flying anywhere

    python -m rs_core.replay --days 3

Ranks the systems in your recent journals by how much good ground they hold,
so you can argue with the scoring before it ends up on a panel.

    python -m rs_core.replay --days 3 --testmode

Writes the best of them into the cache, so the next EDMC start arrives in it
and RhinoScan has something real to draw.

    python -m rs_core.replay --days 7 --rebuild

Writes **every** system it finds into the cache. EDMC replays the journal file
it is watching and nothing older, so bodies you scanned in an earlier session
never reached the plugin - they are in a file EDMC will never read. This is how
they get in, and it is what to run after installing.

## Tests

    pytest

164 checks, no network, no game, no display. See `structure.md` for how the
code is laid out and why.
