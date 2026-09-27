# rs_api - read access to RhinoSpotter data

`rs_api.py` in the plugin folder. Read-only, four calls, `SCHEMA = 1`.

## Import

Inside EDMC (another plugin):

```python
import rs_api
```

Outside EDMC:

```python
import os, sys
sys.path.append(os.path.join(os.environ["LOCALAPPDATA"],
                             "EDMarketConnector", "plugins", "RhinoSpotter"))
import rs_api
```

Linux plugin folder: `~/.local/share/EDMarketConnector/plugins/RhinoSpotter`.

- No EDMC, tkinter or Pillow imports; runs in a plain interpreter.
- sqlite opened `mode=ro`: never locks the plugin out, never writes, never
  creates an empty database.
- `bookmarks`, `bodies` and `revision` take an optional `path=` to a database
  file (default: the live one).
- Unreadable rows are skipped, not raised.

## Calls

| Call | Returns |
|---|---|
| `bookmarks(system=None, body=None)` | list of bookmark dicts, oldest first, optionally filtered |
| `bodies(system=None)` | `[{system, body, bookmarks, depleted}]` - bodies carrying bookmarks, counts only |
| `revision()` | int; changes on any insert, delete, depleted flip or edit. 0 = no bookmarks or db unreadable |
| `version()` | plugin version string |

### Bookmark keys

| Key | Type | Notes |
|---|---|---|
| `system` | str | journal spelling |
| `body` | str | full body name, e.g. `Aramo A 1` |
| `location` | int / None | mining location number |
| `material` | str | e.g. `Monazite` |
| `rigs` | int / None | rig positions of the deposit |
| `latitude`, `longitude` | number | 6 decimals |
| `heading` | number / None | degrees |
| `planet_radius` | number / None | metres; `None` on bookmarks made before Sept 2026 |
| `amount`, `density` | str / None | HUD reading at marking |
| `depleted` | bool | `depleted_at` is set |
| `depleted_at` | str / None | ISO 8601; cleared automatically 14 days later (assumed regen time) |
| `marked_at` | str | ISO 8601 |
| `commander` | str | |
| `id` | int | stable while the bookmark exists |

Distance between two marks: great-circle over `planet_radius`, as the plugin
does it. No radius = no metric distance.

### `revision()` cost

CRC32 over `id`, `depleted_at` and `data` of every row. 0.6 ms at 62 bookmarks,
11 ms at 5,062. Computed from the rows, so a separate process polling it sees
the change.

## Compatibility

While `SCHEMA == 1`: keys are added, never removed, never repurposed. A breaking
change bumps `SCHEMA` to 2 and is listed here.

Not covered: database schema, table names, file layout, any stored field not
listed above. Storage has changed before (JSON per bookmark up to 4.4.x, sqlite
from 5.0).

## Not exposed

- Map / painted ground.
- Permissions: none. The database lives in the commander's folder; anything that
  can import this can read it. Uploading a commander's bookmarks anywhere is
  the reading tool's responsibility to ask about.
