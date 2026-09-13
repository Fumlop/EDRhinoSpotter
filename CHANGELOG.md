# Changelog

## 3.5.2

**Changed**

- A body's bookmarks are grouped by location, and **Share map** sits beside
  each location rather than the planet name. It opens the map picture the
  location's bookmarks lie on, found from their coordinates; greyed when none
  of them lies on a saved map.

## 3.5.1

**Changed**

- The saved map picture leaves out the droppoints and the range rings: the
  painted ground, the bookmarks and the legend are what it is kept for. The
  minimap over the game still shows both.
- **Share map** beside the planet name on a body's bookmarks page opens the
  last map picture saved on that body. Greyed until the body has been driven.

## 3.5.0

**Changed**

- The minimap is 85% opaque: the game shows faintly through it.
- Two thin rings around the latest droppoint, at 2 and 4 km: one scan radius
  and two.
- The saved `map N.png` carries a title and a legend. Above the map: body and
  system, the planet from the honk (type, gravity, distance, locations), and
  the map with the locations its bookmarks were made at, prospected km² and
  when. Below: one row per bookmark on the map - code, material, coordinates,
  rigs.

## 3.4.0

**Changed**

- The guide stops itself ten seconds after HERE first shows, and the button
  goes back to Guide. Rolling off the spot again inside those ten seconds does
  not restart them.

## 3.3.0

**Added**

- Each bookmark dot on the minimap carries its material's code. The most
  valuable material gets its first letter, the next to want that letter gets
  two: Thortveitite T, Thorium TH, Titanium TI, Tritium TR. Every code on the
  sheet is different.

**Changed**

- Droppoints lose their numbers, on the map, in its footer and in the saved
  picture, and are drawn a fifth smaller.
- Debug lines are written only with `RHINOSPOTTER_DEBUG` set. Info and errors
  still go to EDMC's log.

**Fixed**

- The minimap could stay hidden for good after RhinoScan and Guide had been
  used, while the arrow came back. It now asks Windows every tick whether it
  is visible and shows itself again if not.

## 3.2.0

**Added**

- Bookmarks on the minimap: a red dot where each one on this body was made,
  smaller than a droppoint. On the saved `map N.png` too. The card sidecars are
  read again when the cards folder changes and every ten seconds, so a tick
  costs one stat. A bookmark made with the button is on the map at once, not
  when its card has rendered.

**Changed**

- The minimap and the guide arrow hide while Elite is not the window in front -
  alt-tabbed out, EDMC clicked, or the game not running - and come back with
  SW_SHOWNOACTIVATE, so they do not take focus from the game. Painting carries
  on while hidden. The arrow's ten-second message starts again when you come
  back from alt-tabbing, and still runs out with the game not started.
- Up to a second before the minimap hides or returns, half a second for the
  arrow: they follow the polls they already had.

## 3.1.0

**Added**

- The minimap is saved. The points that painted new ground and the
  droppoints go to `%LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map N.json.gz`,
  about 2.4 KB for an hour's drive and 1.3 ms to write, two seconds after new
  ground at most and at once when the SRV docks or EDMC closes. A launch
  within 10 km of a saved map on that body carries it on, with a new
  droppoint; loading repaints the mask from the points, 11 ms for an hour's
  drive. Plain `.json` files are read too.
- Each time the SRV docks, the whole map is saved beside it as `map N.png`:
  400 px, 50 m a pixel, north up, droppoints numbered. Drawn off the Tk
  thread, 70 to 160 ms measured. Nothing reads it back.
- The RhinoSpotter settings tab shows how many maps are saved and how much
  space they take, and opens the folder.

**Changed**

- The minimap reaches 10 km from the first droppoint, was 22, and shows 12 km
  across, was 24, with a 1 km grid, was 2. On a 1080p game that is 50 m a
  pixel, was 100. A launch more than 10 km out starts a new map.

**Not flown**

- Restarting EDMC while driving counts the first reading as a launch and adds
  a droppoint where the SRV is.

## 3.0.0

**Added**

- A minimap over the game while you are in the SRV. Every fix paints a 2 km
  disc - the scanner's community-measured range - north up, the SRV in the
  middle. Ship hops paint nothing; a launch inside 22 km of the first
  droppoint carries on the same map and adds a numbered droppoint, the latest
  bright - that is where the ship is, and the footer points to it. Another
  body or a launch further out starts a new map.
- Its size follows the game window: 22% of the height, 180 to 480 px. Hidden
  while the game is minimised.
- EDMC Settings has a RhinoSpotter tab: the minimap on (default) or off, and
  which corner.
- Cost on the Tk thread, measured: 2.0 ms a tick at 238 px and 8.2 ms at 475
  px while driving over painted ground; 17 ms and 61 ms on a tick that paints
  new ground, which rebuilds the layer.

**Changed**

- The panel's once-a-second Status.json read feeds the minimap too, so there
  is still one parse a second.
- RhinoScan's three materials per ground are the ones that pay most per
  location - share of locations times median price - not the likeliest. On
  high-metal ground that was copper, haematite and titanium, all unpriced;
  it is now iridium, platinum and osmium. Unpriced materials sort last.

**Not flown**

- Whether the map coming up on launch takes focus from the game. It is built
  hidden and shown with SW_SHOWNOACTIVATE, which kept the foreground in
  desktop testing; Tk's deiconify did not.

## 2.10.0

**Changed**

- The guide arrow is a shaded shape rather than a flat triangle. PIL frames,
  one per five degrees, cached - 0.34 ms a frame against 0.42 for the polygon
  it replaces.
- The overlay says it is topmost again every tick, parks in the middle of the
  screen when the Elite window is not found, and is logged and skipped rather
  than raising when it cannot be built at all.
- The scan window measures each font once instead of once per label: 31 ms
  down to 14 on a well-scanned system.
- A honk is written once every two seconds instead of once per body. Replaying
  the 45 landable scans of Col 285 Sector LM-V d2-73: 44 writes down to 5, the
  same 23 bodies on disk. A hard crash now costs the last two seconds of
  scanning; EDMC closing normally costs nothing.

**Removed**

- The measuring wiring in the panel, which no button reached.
  `rs_core/measure.py` stays.
- `_body_names`, filled on every journal line and read by nothing.
- Two of the three copies of the filename rule. `rs_core/names.py` is the one.

## 2.9.1

**Changed**

- "completed" appears on the Bookmark button for five seconds after a card is
  written, then the button takes its own name back. It used to sit in a label
  beside the button and stay there until the next press.
- An update claiming the button while that message is up keeps it. The restore
  only ever takes back its own word.

**Fixed**

- The pending restore is cancelled at shutdown, like the two polls.

## 2.9.0

**Changed**

- Bookmark is disabled unless the ship is on the ground, 100 m altitude or
  less. Orbital cruise reports a latitude and longitude too, so the button used
  to make cards of places nobody had landed on.
- The ground table carries all 37 materials. It held the 22 above a price
  ceiling and dropped the rest, so copper - on 55% of high-metal spots - was
  not on the list at all.
- Icy ground now reads from 131 locations, was 124. High-metal-content 247,
  was 210.

**Fixed**

- The landed poll reschedules itself forever and nothing cancelled it, so at
  shutdown it fired once against a frame that had already gone. `plugin_stop`
  drops both polls.

## 2.8.2

**The window stops fighting itself.** The footer flipped between one line and
two, forever, and the list above it jumped by the difference - a scrollbar
walking up and down on a window nobody was touching.

A label that wraps is told what width to wrap at, and the thing that knows
that width is the window, so the wrapper listens for the window's resize. But
a child widget's bind tags carry its toplevel, so that listener was hearing
every widget in the window - including the label it wraps. The label's own
width set the wraplength, which changed the label's height, which was another
resize. It now answers only for the widget it was bound to.

Eleven thousand lines of debug log for one screenshot, and the window was
being torn down mid-render; both are gone. The screenshots in the README are
regenerated from the code as it stands, and the bookmark list and the guide
arrow have pictures of their own now.

## 2.8.1

**A guide that never got going says why for ten seconds, then goes.** It was
six, and six seconds is not long enough to read a line, look at the body name
and understand that you are one moon out.

**A guide that did get going stays.** Losing the fix is what taking off does,
and the arrow used to close itself six seconds into a climb - you were on your
way back down to the same patch. Only a run that never pointed anywhere counts
as a message, and only a message expires.

## 2.8.0

**Delete, behind every bookmark.** A bookmark was two files in a folder and
nothing in the plugin removed them, so a body worked twice carried both reads
for good. It asks first - it is the one button here that destroys something,
and what it destroys cannot be taken again: the patch is findable, the reading
of what was on it is not.

The PNG and its sidecar go together. The sidecar's path is carried on the
record now rather than worked out from the card's name, because that name has
had its spaces replaced and its material lowercased - deleting one file and
leaving the other is how a folder fills up with sidecars pointing at nothing.
A file that will not go, open in a viewer or on a read-only folder, says so
instead of leaving the list claiming it is gone. The last bookmark on a body
takes the view back to the body list.

**Landing fills the Loc field in.** `Touchdown` carries
`NearestDestination`, which on a mining location is the same
`$SAA_Unknown_Signal` string Status.json gives - and being in the journal it
survives the moment, where Status.json drops the number as soon as the
location stops being the selected destination. That was the one thing on a
bookmark nobody could work out afterwards and everybody had to type.

Nearest, not selected: set down between two locations and it names the closer
one. The coordinates beside it are what the bookmark is actually made of.

**A state with no arrow in it closes the overlay.** Six seconds, then it takes
itself down and the button says Guide again. Pressing Guide on the wrong body
answered with a message you then had to press Stop to clear, which is a
message charging rent.

**Retargeting booked a second timer.** Guide on another bookmark while one was
already running left the first tick in place beside the new one, so every
press doubled the poll rate.

## 2.7.0

**The bookmarks of a body stay in the window.** Clicking the count behind a
body wrote an HTML page and opened a browser; now the same window shows the
list, with **Back** at the top left. Reading three numbers off a patch is not
worth leaving the game for, and the page was a second place for the bookmarks
to live.

One row per bookmark, most rigs first, on two lines: location, material, rigs
and heading on top, the coordinates and when it was marked dim underneath. Two
lines because one did not fit - six decimals of latitude and longitude beside
a material name ran the row past the right edge and took the buttons with it.

The four columns are named above the list rather than in it, because the list
scrolls and a header that scrolls away is one you have to scroll back for.

**Card** opens that bookmark's PNG in whatever shows PNGs here - the thing
that can zoom it, save it and send it to somebody, which is what the card is
for.

**Guide puts an arrow over the game.** A borderless, click-through window at
the top middle of the Elite window, following it if it moves: the direction to
the patch and how far. It reads Status.json twice a second and turns the
position and heading into one angle, great circle rather than flat, because
guiding starts in orbital cruise and over a hundred kilometres flat is wrong.

Elite has to run borderless or windowed. Nothing draws over an exclusive
fullscreen, and no plugin can change that.

The arrow points relative to the nose while the game gives a heading, which is
low down and in the SRV. Higher up there is none, and it then points north-up,
dimmed and labelled with the compass point - a different instrument, so it has
to look like one rather than quietly lying about which way to turn.

No arrow on the wrong body, in orbit, or away from a body at all: a short line
saying which, because sitting on the wrong moon and sitting too high look the
same from the cockpit and want opposite actions. Under 50 m it says HERE.

A bookmark from before the coordinates went into the sidecar has nothing to
point at, and its Guide is greyed out rather than silently dead.

`rs_core/page.py` and its tests are gone with the page. The one thing worth
keeping from it, the order the bookmarks are read in, moved to
`cards.ordered()`.

## 2.6.1

**The bookmarks page sorts by rig count, most first.** It sorted by location,
which is the order you worked the body in - history rather than a decision.
Rigs is the question the page answers: of the patches you bookmarked here,
which one was worth the most. Equal counts fall back to location, and a
bookmark with no count at all sorts last rather than as zero.

## 2.6.0

**Bookmarks open as a page.** Clicking the count behind a body used to put
Explorer's cursor on the newest card. Now it writes a table beside the cards
and opens it in the browser: a row per bookmark with location, material, rigs,
heading, coordinates and when it was marked, and the card itself alongside.

Eleven bookmarks on one body were eleven files to open one at a time, and the
sidecar holding the coordinates was not readable at all.

Written fresh on every open, and beside the cards on purpose - the images are
then one relative path away and the page works from a file:// URL with nothing
serving it. A folder that cannot be written falls back to the old Explorer
behaviour: a read-only folder should cost the table, not the bookmarks.

## 2.5.0

**Create Card is called Bookmark**, and so is everything around it: the link
in the header, and the count behind a body in the scan window. It is what the
thing is - a place you want to come back to - and it is the word the game uses
for that.

**MeasureSpot has no button.** The measuring works, is tested and is reachable
in the code; nothing in the panel calls it, until there is a decision about
where it belongs. Its logging went down to debug with it: nothing starts a
measurement, so nothing it has to say belongs in EDMC's log by default.

## 2.4.1

**The panel stopped second-guessing how you drove.** It flagged an open border
in red, which is a panel telling you something you already know: you placed a
rig, you drove round it, and how well you drove it is yours to judge. The
closure figure stays in the log, where it is there when a number looks wrong
rather than in the way when it does not.

## 2.4.0

**A measurement can be checked now.** The panel says how far the border was
left open, in red, when you did not come back to the starting rig. That is the
number that matters: a shape which does not close still gets an area, because
the formula joins the last point to the first and measures a side nobody drove
- and the figure looks perfectly reasonable.

EDMC's log gets a line when a measurement starts and a summary when it stops:
body, radius, points, perimeter, closure, area, rigs and the spacing used. With
RHINOSPOTTER_DEBUG=1 it also logs every point in degrees and in metres. The
area is derived, and a derived number nobody can re-derive is a number nobody
can check.

## 2.3.2

**The panel says how to measure.** Place a rig where you start, drive the
border slowly, come back to it, then Stop. The rig is the only marker for
where the border began, and slowly matters because Status.json is read once a
second - at speed the corners get cut off and the shape comes out smaller than
it is.

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
