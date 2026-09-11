# Changelog

## 2.0.1

**The card carries coordinates instead of altitude.** You are landed when you
press the button, so altitude was the ship's height above a patch of ground
measured from that same patch of ground - always about zero, and it never told
anyone anything. The latitude and longitude take its place, one per line,
because a lat and a lon on one line is a single long number that has to be
read twice to be split. They are the one thing on the card that cannot be
worked out again afterwards.

**The plugin knows where you are as soon as EDMC does.** Start EDMC with the
game already running and it replays the journal, naming the system on every
line it hands over - but the register only learned the name from a jump or a
scan, so a session started while docked knew nothing until the next jump. The
name is taken from any line now. Learning it is not the same as arriving:
arriving throws away what was held, and a location count can reach us before
any line names the system.

**The material picks what the scan window shows.** The dropdown carries an
"All" under the placeholder; choose anything else and RhinoScan lists only the
ground that has ever carried it, each group leading with its rate for that
material in the accent colour. A ground listed because it carries jadeite has
to say what it carries it at, even when three likelier things sit under it. A
system where nothing carries it says so rather than opening empty.

**The material dropdown looks like the rest of the panel.** Tk gives a
Menubutton a two-pixel raised border and centred text, and with an empty value
in it the whole thing drew as a blank sunken box with a marker floating in the
middle - it read as a broken text field. It has a one-pixel solid border and
left-aligned text now, and says "select material" until you pick one.

**A worker thread could throw a traceback into the log on shutdown.** Every
hop from a thread back to the panel goes through one guarded helper. `after`
raises once the mainloop has gone, which is exactly what happens when EDMC is
closed while an update check is still in flight - and there is nothing left to
update by then anyway.

**The empty scan window leads with the instruction.** "FSS the system, or the
planet you are heading for", then the reason under it.

## 2.0.0

**RhinoScan.** A second button. It lists the landable bodies of the system you
are in, grouped by what kind of body they are, with what that kind of body has
been found to hold. Bodies come from journal `Scan` events, so a honk is
enough and a later detailed scan updates the row it already wrote. The rates
come from `ground_rules.json`, the mining sheet shipped with it. Neither
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

**Test mode.** python -m rs_core.replay ranks the systems in the last three
days of journals by how much good ground they hold; --testmode writes the
winner into the cache, so the next EDMC start arrives in it and RhinoScan can
be looked at over a system with four grounds in it.

**Scan window layout.** The footer packed into the same box as the scrolling
list and landed beside it instead of underneath. Material lines were clipped
rather than wrapped, because the wrap width was a guess at a window that is
resizable. And every body row repeated the system name, which pushed the
distance and the location count off the right edge - the name is in the title
and the header already.

**One palette.** The cards kept a warm olive-and-orange scheme from the
notebook they were prototyped in, while the scan window used a cold
blue. Side by side they looked like two tools, which is exactly what a card
dropped into a chat next to a screenshot is not. Both draw from
rs_core/palette.py now - hex for tkinter, RGB for PIL, one conversion between
them so they cannot drift.

**Tests.** 164 of them, replacing the one hand-rolled script. Two that were
easy to get wrong and are now pinned: `Location` on game start must not empty
the body list, and a scan from another system must reset it even if the
arrival event was missed.

**Panel layout.** Location and Rigs share a row, Material stretches under them
to the same right edge - the names are long enough that a narrow dropdown cut
Low Temp Diamonds in half. Both buttons sit on one line.

**Update button.** MiningCard reads "Update" when a release is out, with the
version in the status line. One press fetches it, unpacks it in place and the
button reads "Restart EDMC". No third button and no version label: the panel
measures the same 250px in every state, which a permanent version button did
not. The zipball goes to a temp folder first
and is copied in a second pass, so a truncated download cannot leave half a
plugin behind, and a zip that is not ours is refused before anything is
touched. ground_rules.json is kept: a locally refreshed sheet is newer
than the one in a release.

## 1.1.0

Marking the same location for the same material twice gives you two cards now.
It used to give you one, silently replacing the first, which is the wrong way
round: the reason to mark a patch twice is that something about it differed.

## 1.0.0

MiningCard. Screenshot conversion with sidecars.
