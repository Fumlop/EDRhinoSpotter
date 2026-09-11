# RhinoSpotter

EDMC plugin for Elite Dangerous surface mining. Two buttons.

## RhinoScan - which bodies here are worth landing on

Press **RhinoScan**. A window opens listing the landable bodies of the system
you are in, grouped by what kind of body they are, with what that kind has
been found to hold underneath.

```
Rocky World [magma]          3 of them
  Olivine 56.1%  Monazite 45.6%  Bastnasite 42.1%  Serendibite 31.6%
  across 57 locations read
   Andel 1 a    412 Ls   16 loc     major metallic magma
   Andel 1 b    418 Ls   unprobed   minor metallic magma
   Andel 4 a   1016 Ls   9 loc      major rocky magma
```

The bodies come from the journal, so a system you have honked is already fully
described - `PlanetClass` and `Volcanism` arrive with the discovery scan, no
detailed surface scan needed. Scan a body properly later and its row updates
itself.

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

The percentages come from `ground_rules.json`, exported from the EDIntel
mining sheet. Neither half touches the network. Losing the JSON costs the
percentages, not the body list.

**These are rates, not contents.** What a mining location actually holds is in
no journal event and on no feed. This says where to prospect; it cannot say
what you will find.

## MiningCard - the patch you are standing on, as a PNG

1. Land and put the rigs down.
2. Pick the **Material**, set **Rigs**. `Location` fills itself when a mining
   location is the selected destination; otherwise type the signal number.
3. Press **MiningCard**. `completed` appears beside the button once the PNG is
   on disk.

Coordinates, body and location are read out of `Status.json` at the press - it
is live-only, so make the card before you fly off. Marking the same location
for the same material twice gives you two cards, not one overwritten.

Cards land in `%LOCALAPPDATA%\RhinoSpotter\cards\<System>\`. The **cards
folder** link in the panel header opens it in Explorer.

## Screenshots

Screenshots taken while the plugin is loaded are cropped to the target panel
and filed under `data/planetScreener/<System>/<Body>/`, each with a JSON
sidecar holding the body, the coordinates and the selected mining location.
The target panel is the only place a location's materials are written down.

## Install

Drop the folder into `%LOCALAPPDATA%\EDMarketConnector\plugins\` and restart
EDMC.

When a newer release is out, **MiningCard** reads **Update** instead and the
status line names the version. Press it and the release is fetched and
unpacked in place, then it reads **Restart EDMC**. There is no third button:
the panel stays the same width in every state.

Your exported `ground_rules.json` is kept, and cards and scans are never
touched - they live under `%LOCALAPPDATA%\RhinoSpotter\`, not in the plugin
folder.

## Refreshing the rates

From an EDIntel checkout:

    python scripts/export/rhinoscan_data.py

That rewrites `ground_rules.json` in this folder from the current mining sheet.

## Seeing it without flying anywhere

    python -m rs_core.replay --days 3

Ranks the systems in your recent journals by how much good ground they hold,
so you can argue with the scoring before it ends up on a panel.

    python -m rs_core.replay --days 3 --testmode

Writes the best of them into the cache, so the next EDMC start arrives in it
and RhinoScan has something real to draw.

## Tests

    pytest

152 checks, no network, no game, no display. See `structure.md` for how the
code is laid out and why.
