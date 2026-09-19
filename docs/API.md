# Reading RhinoSpotter's data from somewhere else

`rs_api.py`, in the plugin folder. One import, four calls, read-only.

It exists because two projects were reading the plugin's storage directly and
found out the hard way that it moved - JSON files per bookmark up to 4.4.x, one
sqlite database from 4.2/5.0. This module is the part that does not move.

---

## Using it

Inside EDMC, from another plugin:

```python
import rs_api

for mark in rs_api.bookmarks():
    print(mark["body"], mark["location"], mark["material"], mark["depleted"])
```

Outside EDMC, from a separate application - the same module, the folder added
to the path:

```python
import os, sys
sys.path.append(os.path.join(os.environ["LOCALAPPDATA"],
                             "EDMarketConnector", "plugins", "RhinoSpotter"))
import rs_api
```

On Linux the plugin folder is `~/.local/share/EDMarketConnector/plugins/RhinoSpotter`.

Nothing in `rs_api` imports EDMC, tkinter or Pillow, so it works in a plain
interpreter. The database is opened `mode=ro`: a reader cannot lock the plugin
out, cannot change anything, and cannot create an empty database beside the
real one by reading too early.

---

## The calls

### `bookmarks(system=None, body=None)`

Every bookmark the commander made, oldest first, or those of one system or one
body. A list of dicts:

| Key | What |
|---|---|
| `system` | system name, as the journal spells it |
| `body` | full body name, e.g. `Aramo A 1` |
| `location` | the mining location number the panel showed, or `None` |
| `material` | what was mined there - `Monazite`, `Low Temperature Diamonds`, … |
| `rigs` | how many rig positions the deposit held, or `None` |
| `latitude`, `longitude` | where the commander stood, six decimals |
| `heading` | degrees, or `None` |
| `amount`, `density` | the HUD reading when the bookmark was made, or `None` |
| `depleted` | `True` once it was marked worked out |
| `depleted_at` | when it was marked, ISO 8601, or `None` |
| `marked_at` | when the bookmark was made, ISO 8601 |
| `commander` | who made it |
| `id` | the row, stable for as long as the bookmark exists |
| `raw` | the whole record as the plugin stored it |

`depleted_at` is the field worth having. It is a timestamped "this deposit was
empty at this moment", which is what any work on deposits reforming needs, and
nothing else in the game records it.

### `bodies(system=None)`

The bodies that carry bookmarks: `system`, `body`, `bookmarks`, `depleted`.
The cheap question - is there anything of mine on this body - without reading
every bookmark on it.

### `explored(body)`

What the plugin knows that a radar does not: how much ground the SRV has
actually driven over.

| Key | What |
|---|---|
| `body` | the body asked for |
| `maps` | the saved maps on it, `["map 1", "map 2"]` |
| `km2` | square kilometres inside scanner range of the track, `None` without Pillow |
| `locations` | the mining locations those maps were driven on |

`None` when no map was ever saved there. The pictures themselves are PNGs in
`<data folder>/coverage/<body>/<map name>.png` - see `data_dir()`.

### `version()`, `database_path()`, `data_dir()`

Which plugin version wrote the data, where the database is (watch it for
changes if you want to react), and the folder holding the database, the map
pictures and the backups.

---

## The promise

`rs_api.SCHEMA` reads `1`.

While it reads 1: keys are added, never removed, never repurposed. A key that
has to change meaning gets a new name and the old one keeps answering. If that
becomes impossible, `SCHEMA` becomes 2 and this page says what moved.

What is deliberately **not** promised: the database schema, the table names,
the JSON inside `raw`, and the file layout. Read them if you like - they are
the commander's own files - but they have moved before and they will move
again. `rs_api` is what gets kept.

---

## What is not here

The map itself. The painted ground is a mask built from the SRV's track and it
is drawn, not described - `explored()` gives you the number and the pictures,
not a geometry. If you want to render it yourself, the points are in the
database and `rs_core.coverage` will rebuild the mask from them, but that is
the plugin's internals and it is not covered by the promise above.

Bookmarks are the part that travels: a point, a material, a rig count and a
flag. Any radar can draw those.
