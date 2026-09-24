# share_e2e.py - what it covers and what it hides

`python rs_e2etest/share_e2e.py`. Two child processes, each with its own
LOCALAPPDATA under `out/<timestamp>/` - A shares, B imports - over the real
Windows clipboard. The clipboard text found at the start is put back at the end.
The RhinoData window is drawn off-screen (-4000, -4000), mapped but not visible.

## Ways it can fail end to end

1. Share bookmark puts nothing, or not a `RhinoData:` line, on the clipboard.
2. The code carries personal data: `commander`, `marked_at`, `yield`.
3. The sharer's own poll imports its code back as a second bookmark.
4. Same, after the sharer deleted the bookmark (only the digest stops it).
5. The code does not survive the sharing process exiting.
6. B does not import it, or imports it with fields changed.
7. B imports it again on every poll, or again when it arrives inside chat text.
8. A mangled, oversized or tampered code creates a row or raises in the poll.
9. The four card buttons under Guide me there are not the same width.
10. The poll costs enough per second to matter.
11. An imported code comes back after its bookmark was deleted.

## Checked

All of 1-11. 8 includes NaN and zero radius, a 5,000-char body name, an int
over 2^63 and an unknown Amount. 10 is timed: 1,000 `_check_clipboard()` calls
on an unchanged clipboard (Windows sequence number unchanged).

## Not covered

- Non-text clipboard content (an image): `clipboard_get` raises TclError and
  the poll returns; no scenario puts an image there.
- A code pasted through Discord or a browser that rewraps or trims it.
- EDMC itself: the panel is built by `main.build` on a withdrawn Tk root, not
  inside EDMC's window.
- The standalone build.
