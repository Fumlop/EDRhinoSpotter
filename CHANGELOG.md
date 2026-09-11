# Changelog

## 2.3.1

**A patch too small for the grid read as room for no rigs.** 4,000 m2 is 63 m
square and obviously holds one. The grid was laid from the shape's corner, a
corner sits on the boundary, and a point on the boundary counts as outside -
so the only point a small patch got was thrown away.

The grid is offset half a cell now, which is where a rig would stand anyway:
in the middle of its square rather than on the fence. And a shape with area in
it reports at least one rig whatever the grid says, because a long thin patch
can miss every grid point and still be somewhere you can put one down.

## 2.3.0

**MeasureSpot.** Press it, drive the border of a patch in the SRV, press Stop.
It reads the area and how many rigs will fit, live, on a line of its own above
the note.

The shape is whatever you drove. Not a circle, not a rectangle, and usually
neither - which is the whole reason for driving it rather than pacing a radius.
Area by the shoelace formula, rigs by laying a 76 m grid over the shape and
throwing away everything outside it.

It is an estimate and reads as one. The ground is not flat, nobody drives a
border exactly, and two rigs 76 m apart on a map are not 76 m apart on a slope.

Position comes from Status.json once a second. Two samples closer than four
metres are the same place, so parking at the fence does not add a hundred
points that say nothing, and a sample from another body is refused rather than
bending the shape across a planet.

## 2.2.1

**Replaying two visits to one system kept only the last.** Two sessions
describe different parts of a system - one honk resolved A 1 to A 7, the next
only the AB bodies - and the later visit threw the earlier away. The
docstring had claimed the union all along, which is how it went unnoticed.
They are merged now, with a rescan of the same body winning over the older
answer.

**`--rebuild` fills the cache from every journal in the window.** EDMC replays
the file it is watching and nothing older, so bodies scanned before the plugin
was installed, or while it was not running, were in a file EDMC will never
read. Run it once after installing.

## 2.2.0

**Screenshot conversion has moved out**, into RhinoAnalysis - its own plugin,
with a settings page and nothing in the main window. It converted the game's
.bmp into a cropped .jpg and filed it by system and body, which is a different
job from "which body here is worth landing on" and was only ever in the same
folder because it was written on the same afternoon. Splitting it means
RhinoSpotter bundles only what it needs, which the plugin registry asks for,
and the conversion gets settings instead of constants.

Nothing you have is touched. Cards, scanned systems and ground_rules.json all
stay where they are; only the .bmp conversion left.

## 2.1.1

**GPL-3.0.** There was no licence file at all, which is the one thing the EDMC
plugin registry will not list a plugin without - it treats plugins as
derivative works of EDMC, so GPL v2 or later compatible is the floor.

**VERSION is readable from load.py.** It is defined in rs_core/update.py,
where it is compared against a release, and re-exported here because the
registry reads it off the plugin and the plugin is load.py. A test pins the
two together.

## 2.1.0

**Cards are linked from the bodies they were taken on.** A body you have
already marked shows "2 cards" behind it; clicking opens Explorer with the
newest one selected, rather than the folder for you to hunt through. Only
bodies that have one say so - a zero on every other row would be nine pieces
of nothing in a ten-body system.

**Every card gets a JSON sidecar.** A picture cannot be searched, and reading
a body back out of a filename is a guess: the spaces were replaced and the
material was lowercased. The sidecar holds what was actually marked, and a PNG
without one is skipped rather than guessed at.

**The material picker sits in the scan window too**, under the system name,
bound to the panel's own variable. Choosing in one place is the same act as
choosing in the other.

**MiningCard is called Create Card.** It says what pressing it does, and the
panel already says "cards folder" while the window says "2 cards" - one word
for one thing.

## 2.0.2

**The plugin knows where you are as soon as EDMC does.** The game writes a
Location event when you load in, and EDMC reads the journal from the top on
startup, so it can name the system straight away. The register waited for a
jump or a scan instead, and a session started with the game already running
knew nothing until the next jump - the lines in between are Music and
ShipLocker, and none of them say where you are. The name is taken from any
line EDMC hands over now. Learning it is not the same as arriving: arriving
throws away what is held, and a location count can reach us before any line
names the system.

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

**The landable count moved to the top row.** It sat beside RhinoScan, which
read as a fact about the button. It is a fact about the system.

**A worker thread could throw a traceback into the log on shutdown.** Every hop
from a thread back to the panel goes through one guarded helper. `after` raises
once the mainloop has gone, which is exactly what happens when EDMC is closed
while an update check is still in flight.

**The empty scan window leads with the instruction.** "FSS the system, or the
planet you are heading for", then the reason under it.

## 2.0.1

**The card carries coordinates instead of altitude.** You are landed when you
press the button, so altitude was the ship's height above a patch of ground
measured from that same patch of ground - always about zero, and it never told
anyone anything. The latitude and longitude take its place, one per line,
because a lat and a lon on one line is a single long number that has to be
read twice to be split. They are the one thing on the card that cannot be
worked out again afterwards.

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

**Update button.** Create Card reads "Update" when a release is out, with the
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
