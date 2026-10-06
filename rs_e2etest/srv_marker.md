# srv_marker_e2e: the SRV marker on the minimap is orange (#8)

Run from the plugin folder: `python rs_e2etest/srv_marker_e2e.py`.
Writes `rs_e2etest/out/<timestamp>/report.txt` and `minimap.png`. Exit code 1 on a failure.

Driven: `coverage.Coverage.add` along a 3 km track, then `coverage.render` with
bookmarks, the centre and distances on, at 180, 240 and 480 px (480 also with
`base=240`), heading 0, 135 and None.

## Ways it can fail, and the check for each

1. Marker still drawn in `palette.FG` - centre pixel of the marker is `palette.SRV`, no `FG` pixel inside the marker box on a render without bookmarks (their codes are drawn in `FG`).
2. Marker colour close to another map colour (bookmark `MARK`, `MARK_DEPLETED`, `CENTRE`, `GOLD`, `GRID`, `WARN`, `EDGE`, `FILL`) - RGB distance >= 80 to each.
3. A bookmark dot under the SRV covers it - a dot placed at the SRV position; centre pixel is still `SRV`.
4. Heading None (descent, Status.json `Heading` -1) drawn in the old colour - dot centre is `SRV`.
5. Zoom path (`base=`) or small map (180 px) loses the colour - centre pixel `SRV` at every size.

## Blind spots

- Not driven inside EDMC: the Tk label showing the image is not checked; `minimap.png` is read by eye.
- `_markers` caches sprites per process; a running EDMC keeps the old colour until restart.
- Visibility over each ground texture is judged by eye, not measured.
