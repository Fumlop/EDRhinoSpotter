<h1 align="center">
  <img src="docs/logo.png" width="300" alt="RhinoSpotter, EDMC Plugin - a rhino seen through binoculars">
</h1>

EDMC plugin for Elite Dangerous surface mining with the Rhino.

| | |
|---|---|
| **RhinoData** | Which bodies in the system are worth landing on, and for which material |
| **Bookmarks** | Save the deposit you are on: material, rigs, amount, density, position |
| **Guide** | Arrow over the game back to any bookmark, from orbit down to the SRV |
| **Minimap** | Ground you have driven in the SRV, with your bookmarks on it |
| **Tons** | Tons mined per bookmark, from the journal |

## Install

Unpack into `%LOCALAPPDATA%\EDMarketConnector\plugins\RhinoSpotter\` (`load.py`
directly inside), restart EDMC. Details: [INSTALL.md](INSTALL.md).

Updates: when a release is out, **Bookmark** reads **Update**. Press it, restart
EDMC. Your data lives outside the plugin folder.

## The panel

<p align="center">
  <img src="docs/plugin.png?v=5.7.3" alt="The RhinoSpotter panel in EDMC">
</p>

1. Land, put the rigs down.
2. Set **Material** and **Rigs**. **Location** fills itself on landing; type over it if wrong.
   Leaving the location clears it.
   **Amount** / **Density** from the HUD are optional.
3. Press **Bookmark** before you drive off - the position is read at the press.

The same material within 100 m updates the existing bookmark instead of adding one.

## RhinoData

**RhinoData** button or **Ctrl+Alt+D**.

<p align="center">
  <img src="docs/bookmarks.png?v=5.7.3" width="720"
       alt="RhinoData: bodies of the system on the left, one body's bookmarks by location in the middle, the picked bookmark's card on the right">
</p>

- **Left:** landable bodies by ground type, with distance, mining locations and your bookmark count.
  Honk to load them from Spansh; FSS when the line under the panel asks for it.
- **Middle:** the body's best materials (share of locations, median Cr/t), then its bookmarks
  folded by location: rigs, bearing/distance from the location center, tons mined, estimated tons left.
- **Right:** the saved map around the bookmark and its card:
  **Guide me there**, **Share bookmark**, **Mark depleted**, **Copy coords**, **Delete**.
- In the SRV, the bookmark you stand at (175 m) is marked and preselected - Mark depleted is one click.
- A depleted mark comes off by itself after 14 days.
- **Systems with bookmarks:** type three letters to jump to another system.

<table align="center">
  <tr>
    <td align="center"><img src="docs/rhinoscan-filtered.png?v=5.7.3" width="360"
         alt="RhinoData filtered to one material"></td>
    <td align="center"><img src="docs/mapped.png?v=5.7.3" width="360"
         alt="The Mapped tab of one body"></td>
    <td align="center"><img src="docs/edit.png?v=5.7.3" width="200"
         alt="The Edit bookmark dialog"></td>
  </tr>
  <tr>
    <td align="center"><em>Material filter: only grounds that carry it</em></td>
    <td align="center"><em>Mapped tab: saved maps per location</em></td>
    <td align="center"><em>Edit: fix material, rigs, amount, density</em></td>
  </tr>
</table>

**Share bookmark** puts one `RhinoData:...` line on the clipboard for Discord or a DM.
Another RhinoSpotter that sees it on its clipboard imports it, unless it made the line itself or
already has that material within 100 m. No commander name, dates or tons in it.

Rates are where to prospect, not what a location holds - no journal says that.

## Guide

<p align="center">
  <img src="docs/guide.png?v=5.0.0" width="200" alt="The guide arrow with distance">
</p>

Arrow top middle over the game with distance to the bookmark. Borderless or windowed only.
Linux: top middle of the screen; drag it where you want it, right-click puts it back.

## Minimap

<table align="center">
  <tr>
    <td align="center"><img src="docs/minimap.png?v=5.7.3" width="230" alt="Minimap, no center"></td>
    <td align="center"><img src="docs/minimap-center.png?v=5.7.3" width="230" alt="Minimap, center set"></td>
    <td align="center"><img src="docs/minimap-big.png?v=5.7.3" width="300" alt="Minimap at 2x with distances"></td>
  </tr>
  <tr>
    <td align="center"><em>Driving</em></td>
    <td align="center"><em>Center set</em></td>
    <td align="center"><em>Border set, 2x zoom</em></td>
  </tr>
</table>

- Shown in the SRV while Elite is in front. Paints 2 km (scanner range) around your track; 12 km across, north up.
- Bookmarks are dots with material codes: green active, red depleted.
- At 2x: solid line to the nearest same material, dotted to the next cheaper one, with distances.
- Saved per body; relaunching within 10 km continues the same map.
- "Painted" means driven within 2 km, not proven scanned - the game logs no scan.

| Key | Does |
|---|---|
| Ctrl+Alt+Z | Set the location center where you stand |
| Ctrl+Alt+B | Set the border (needs a center); shows drive rings, drops ground outside |
| Ctrl+Alt+M | Zoom 1x / 2x / 4x |
| Ctrl+Alt+D | Open RhinoData |

Keys are changeable in Settings.

Each dock saves a map picture; **Share map** on a location line opens it.
Gold circles mark the best 3 golden groups: 5+ rigs within 1.25 km of the spot with the most
rigs (4+ when the map has no 5), one Rhino stop. RhinoData lists a location's bookmarks in
the same groups, most rigs first.

<p align="center">
  <img src="docs/mapshare.png?v=5.0.0" width="440" alt="A saved map picture with bookmarks and legend">
</p>

## Settings

<p align="center">
  <img src="docs/settings.png?v=5.7.3" width="480" alt="The RhinoSpotter settings tab">
</p>

- Minimap on/off, keep it up when alt-tabbed, corner, or **Free move** (drag it anywhere, any monitor).
- **Golden circle radius:** 500-2500 m in 250 m steps, default 1250. Also sets how RhinoData groups a location's bookmarks.
- **Materials in the lists: Select...** tick the materials the dropdowns offer, any of 38.
  Default: the 18 over 50,000 Cr/t. Bookmarked materials stay in the list either way.
- Hotkeys: modifier + key for each of the four. Windows only; on Linux type
  `!rs center`, `!rs border`, `!rs zoom` or `!rs data` in chat. It is sent as chat:
  others on that channel see it.

## Data

Local only. Network: Spansh on honk (once a session per system, not again for 30 days, never for
undiscovered systems, paused 1 h after a failed request), GitHub for updates.

| What | Where |
|---|---|
| Bookmarks, bodies, maps | `%LOCALAPPDATA%\RhinoSpotter\db\rhinospotter.db` |
| Backups (last 2) | `%LOCALAPPDATA%\RhinoSpotter\db\backups\` |
| Map pictures | `%LOCALAPPDATA%\RhinoSpotter\coverage\<Body>\map N.png` |
| Material rates | `mining_sheet.json` in the plugin folder |

Linux: `$XDG_DATA_HOME/RhinoSpotter` instead of `%LOCALAPPDATA%\RhinoSpotter`
(`~/.local/share`, Flatpak EDMC `~/.var/app/io.edcd.EDMarketConnector/data`).
An older `~/RhinoSpotter` is copied there once, on the first start without that folder.

Other plugins and tools read bookmarks through `rs_api.py`: [docs/API.md](docs/API.md).

## Tools

    python -m rs_core.replay --days 7 --rebuild    # load bodies from older journals - run once after installing

Debug log: `RHINOSPOTTER_DEBUG=1` before starting EDMC. Code layout: [structure.md](structure.md).

## Features

- **Where to land:** every landable body of the system with its mining locations and the materials its ground carries.
- **Material filter:** only grounds that ever carried it; type a letter in the menu to jump to it.
- **Bookmarks:** material, rigs, amount, density and position of the deposit you stand on; a second press on the spot updates it, material too.
- **Clusters:** a location's bookmarks grouped by the spot with the most rigs and everything within the golden radius.
- **Golden circles:** the best 3 one-stop groups (5+ rigs, else 4+) circled on the maps, radius set in Settings.
- **Guide:** an arrow over the game back to any bookmark, from orbit down to the SRV.
- **Minimap:** the ground you drove in the SRV, your bookmarks on it, center, border and drive rings, 3 zoom steps.
- **Map pictures:** saved per body, shareable with a legend and the golden circles.
- **Tons mined:** counted per bookmark from the journal, refreshed 5 s after the last ton.
- **Depleted marks:** set on the card, taken off after 14 days.
- **You are here:** the bookmark within 175 m of the SRV marked and picked; locations within 5 km unfolded.
- **Share bookmark:** one line for Discord; another RhinoSpotter imports it from the clipboard.
- **Spansh:** bodies of a new system filled in on the honk.
- **Updates:** from inside EDMC; your data stays outside the plugin folder.

<p align="center">
  <img src="docs/running.png" width="140" alt="">
</p>
