# grabcheck_e2e.py - what it covers and what it hides

`python rs_e2etest/grabcheck_e2e.py`. Needs the screen: two small windows at
(60, 60) for ~3 s. The failure list is in the harness docstring (1-3).

## Not covered

- Click-through (WS_EX_TRANSPARENT) windows of other programs: WindowFromPoint
  skips them, so an overlay that ignores the mouse is not reported.
- Other monitors and DPI scales than the one the run is on.
