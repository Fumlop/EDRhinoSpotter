# texture_e2e.py - what it covers and what it hides

`python rs_e2etest/texture_e2e.py`. LOCALAPPDATA pointed at `out/<timestamp>/`,
seeded with a copy of the live db. Two child processes, PYTHONHASHSEED 1 and 2.
Writes `report.txt` and `sheet-<family>.png` (the 6 files of each family, 240 px).

## Ways the pick can fail, each checked

- A variant file missing, unreadable, not 1920 x 1920 RGB: every
  `texture/<family>.jpg` and `<family>-2..6.jpg` is opened.
- Pick not stable across restarts (salted `hash()`, set order): both children
  print the file of every cached body; the lists must be identical.
- Pick skewed or stuck on one file: per family, count of cached bodies on each
  variant; a family with 24+ bodies with a variant never picked fails.
- Live minimap and saved picture on different ground: every saved map is drawn
  through `Coverage.layer()` and `picture()` with `_texture` spied; both must
  load the same file, and it must be the body's pick.
- No body name: `texture_name(ground, None)` gives variant 1, `<family>.jpg`.
- Formula and naming: for 40 cached bodies the pick is recomputed here as
  `zlib.crc32(name) % 6 + 1`, variant 1 = `<family>.jpg`, else `<family>-N.jpg`.
- Variant file missing (hand-unzip of an old zip over a new one): a texture
  folder holding only `rocky.jpg`; a body picked for `rocky-N` must get
  `rocky.jpg`'s pixels, not plain ground.

## Not covered

- Tk: the layer is drawn as a PIL image, not shown in the minimap window.
- The UI call sites: `minimap.py` (saved picture) and `scan.py` (Share map)
  call `picture(..., ground, body)`; this harness calls `picture()` directly
  with `Coverage.body`. A dropped `body` there falls back to variant 1 and
  would not fail here.
- Families with under 24 cached bodies (metallic 17, rocky-ice 3 in the live db
  of 2026-11-28) are listed but not held to all 6 variants.
- What the textures look like: `sheet-<family>.png` is for the eye.
