# layer_e2e.py - what it covers and what it hides

`python rs_e2etest/layer_e2e.py`. LOCALAPPDATA pointed at `out/<timestamp>/`,
seeded with a copy of the live db. Every saved map is replayed stamp by stamp
through `Coverage.add`; after each stamp `Coverage.layer()` (patched in place
around the new disc) is compared pixel by pixel with a full `_draw_layer` of
the same mask. Any differing pixel fails.

## Ways the patch can fail, each checked

- Seam at the patch edge: bilinear resize of a mask crop, `FIND_EDGES` at the
  crop border, `reduce(SS)` off the SS grid.
- Grid lines, mask-edge rectangle, rings, border drawn with an offset land a
  pixel off the full draw.
- Disc at the mask edge (clamped box): patch box clipped wrong. Forced with
  `EDGE_M`: stamps at 9.9 km on each side, a corner, and 1 m inside the
  opposite corner, on every map without a harness border.
- Several stamps between two `layer()` calls: every dirty box redrawn, not
  just the last.
- `_repaint` (load, `recenter`, `set_border`) changes the whole mask: full
  redraw, not a patch.
- Any other key part changing (side, view, rings anchor, border, ground):
  full redraw.
- Border set: the clip applies inside the patch.
- No texture (`ground=None`) and a texture.
- Layer sizes: 180 px (fractional mask scale, 600 over 400 px) and 640 px
  (largest; 4x at 320 px / view 3000 draws the same 1067 px layer).
- Old vs new: the committed coverage.py (git HEAD) replays the same points;
  mask, `render()` and `picture()` must match it exactly.

## Timings

Full redraw vs patch, per stamp, printed per size to `report.txt`.

## Not covered

- Tk: the patched layer is only compared as a PIL image; `render()` crops it
  the same way as before.
- Live driving: stamps come from saved maps, i.e. only stamps that painted new
  ground. A stamp that painted nothing never reaches `layer()` as a change.
