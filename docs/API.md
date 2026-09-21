# Reading RhinoSpotter's data from somewhere else

`rs_api.py`, in the plugin folder. One import, four calls, read-only.

It exists because two projects were reading the plugin's storage directly and
found out the hard way that it moved - JSON files per bookmark up to 4.4.x, one
sqlite database from 5.0. This module is the part that does not move.

---

## Using it

Inside EDMC, from another plugin:

```python
import rs_api

for mark in rs_api.bookmarks():
    print(mark["body"], mark["location"], mark["material"], mark["depleted"])
```

Outside EDMC, from a separate application - the same module, the folder added to
the path:

```python
import os, sys
sys.path.append(os.path.join(os.environ["LOCALAPPDATA"],
                             "EDMarketConnector", "plugins", "RhinoSpotter"))
import rs_api
```

On Linux the plugin folder is `~/.local/share/EDMarketConnector/plugins/RhinoSpotter`.

Nothing in `rs_api` imports EDMC, tkinter or Pillow, so it works in a plain
interpreter. The database is opened `mode=ro`: a reader cannot lock the plugin
out, cannot change anything, and cannot create an empty database beside the real
one by reading too early.

---

## The calls

### `bookmarks(system=None, body=None)`

Every bookmark the commander made, oldest first, or those of one system or one
body. A list of dicts, and these keys only:

| Key | What |
|---|---|
| `system` | system name, as the journal spells it |
| `body` | full body name, e.g. `Aramo A 1` |
| `location` | the mining location number the panel showed, or `None` |
| `material` | what was mined there - `Monazite`, `Low Temperature Diamonds`, … |
| `rigs` | how many rig positions the deposit held, or `None` |
| `latitude`, `longitude` | where the commander stood, six decimals |
| `heading` | degrees, or `None` |
| `planet_radius` | metres, from Status.json when the mark was made, or `None` |
| `amount`, `density` | the HUD reading when the bookmark was made, or `None` |
| `depleted` | `True` once it was marked worked out |
| `depleted_at` | when it was marked, ISO 8601, or `None` |
| `marked_at` | when the bookmark was made, ISO 8601 |
| `commander` | who made it |
| `id` | the row, stable for as long as the bookmark exists |

`planet_radius` is there so two marks can be compared the way the plugin does
it: a great-circle distance in metres over that sphere, rather than a
difference in degrees that means different things at different latitudes.
**It is `None` on bookmarks made before it was recorded** - the plugin started
keeping it in September 2026, and nothing can fill it in afterwards, so treat
a missing radius as "cannot compare across bodies" rather than as zero.

`depleted_at` is the field worth having. It is a timestamped "this deposit was
empty at this moment", which is what any work on deposits reforming needs, and
nothing else in the game records it.

### `bodies(system=None)`

The bodies that carry bookmarks: `system`, `body`, `bookmarks`, `depleted`. The
cheap question - is there anything of mine on this body - without reading every
bookmark on it.

### `revision()`

A number that changes when the bookmarks do - an insert, a delete, a depleted
flip or an edit of any row. Poll it, and read again when it moves. 0: no
bookmarks, or the database not readable. It reads every row: 0.6 ms at 62
bookmarks, 11 ms at 5,062. It is computed from the rows themselves rather
than from a counter in memory, because a counter belongs to the process that
did the writing - a separate application polling one would see the same value
for ever.

### `version()`

Which plugin version wrote the data.

---

## The promise

`rs_api.SCHEMA` reads `1`.

While it reads 1: keys are added, never removed, never repurposed. A key that
has to change meaning gets a new name and the old one keeps answering. If that
becomes impossible, `SCHEMA` becomes 2 and this page says what moved.

What is deliberately **not** promised: the database schema, the table names, the
file layout, and anything the plugin stores beside the keys above. Read them if
you like - they are the commander's own files - but they have moved before and
they will move again. `rs_api` is what gets kept.

---

## What is not here

**The map.** The painted ground is a mask built from the SRV's track and it is
drawn, not described. If the exploration layer is useful to you, ask - it can be
added to this page rather than reverse-engineered out of the database.

**Permissions.** There is no flag in here granting or refusing anything. The
database sits in the commander's own folder and anything that can import this
can read it, so a permission in this module would be a lie in code. Bookmarks
are somebody's flight log: showing a commander their own marks is one thing, and
sending them anywhere else is a decision that belongs to that commander, made in
your application, in words they can read, before you upload anything.
