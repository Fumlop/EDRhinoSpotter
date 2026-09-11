# Changelog

## 2.0.0

**RhinoScan.** A second button. It lists the landable bodies of the system you
are in, grouped by what kind of body they are, with what that kind of body has
been found to hold. Bodies come from journal `Scan` events, so a honk is
enough and a later detailed scan updates the row it already wrote. The rates
come from `ground_rules.json`, exported from the EDIntel mining sheet. Neither
half touches the network, and losing the JSON costs the percentages rather
than the body list.

**Repacked.** `rs_core` for everything that is not a widget, `rs_ui` for
everything that is, `rs_tests` for pytest. `load.py` is now the EDMC contract
and nothing else. Nothing in `rs_core` imports tkinter, which is what lets the
suite run under a bare interpreter with no EDMC, no game and no display.

**Mining location counts, and a memory.** FSSBodySignals reports how many
Planetary Mining Locations a body carries straight from the FSS, and
SAASignalsFound confirms it after a surface scan, so the count is in the
journal and no external service is asked for it. A body nobody counted reads
unprobed, not 0 loc.

Each system is written to %LOCALAPPDATA%\RhinoSpotter\data\ on every scan,
count and jump - the moment it happens, not when you leave, so a crash on the
pad costs nothing. Jump back in and the system arrives already filled, with
anything scanned afterwards added to it. Beside the cards and outside the
plugin folder, for the same reason the cards are: a reinstall replaces the
plugin and should not take your scans with it.

**Tests.** 136 of them, replacing the one hand-rolled script. Two that were
easy to get wrong and are now pinned: `Location` on game start must not empty
the body list, and a scan from another system must reset it even if the
arrival event was missed.

**Panel layout.** Location and Rigs share a row, Material stretches under them
to the same right edge - the names are long enough that a narrow dropdown cut
Low Temp Diamonds in half. Both buttons sit on one line.

**Update button.** The third button says the version until there is something
to do, then becomes "Update to vX.Y.Z". One press fetches the release, unpacks
it in place and reads "Restart EDMC". The zipball goes to a temp folder first
and is copied in a second pass, so a truncated download cannot leave half a
plugin behind, and a zip that is not ours is refused before anything is
touched. ground_rules.json is kept: you exported it from your own EDIntel, so
the local copy is fresher than any release's.

## 1.1.0

Marking the same location for the same material twice gives you two cards now.
It used to give you one, silently replacing the first, which is the wrong way
round: the reason to mark a patch twice is that something about it differed.

## 1.0.0

MiningCard. Screenshot conversion with sidecars.
