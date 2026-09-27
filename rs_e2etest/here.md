# here_e2e.py - what it covers and what it hides

`python rs_e2etest/here_e2e.py`. One process, LOCALAPPDATA and the journal
folder pointed at `out/<timestamp>/`, the real `scan.show` window off-screen,
Status.json written by the harness, `<Activate>` sent with `event_generate`.
The failure list and checks are in the harness docstring (1-9).

## Not covered

- The real game writing Status.json while driving; each position is written whole.
- A real alt-tab: `<Activate>` is generated, not raised by Windows focus.
- Two bookmarks at the same distance.
