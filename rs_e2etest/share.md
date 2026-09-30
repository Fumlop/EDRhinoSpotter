# share_e2e.py - what it covers and what it hides

`python rs_e2etest/share_e2e.py`. Two child processes, each with its own
LOCALAPPDATA under `out/<timestamp>/` - A shares to the real Windows
clipboard, B types the code into the import box under the bookmarks in
RhinoData and presses Import. B's window has no bodies (the empty view).
The clipboard text found at the start is put back at the end.
The RhinoData window is drawn off-screen (-4000, -4000), mapped but not visible.

## Ways it can fail end to end

1. Share bookmark puts nothing, or not a `RhinoData:` line, on the clipboard.
2. The code carries personal data: `commander`, `marked_at`, `yield`.
3. The sharer pastes its own code and gets a second bookmark.
4. Same, after the sharer deleted the bookmark (only the digest stops it).
5. The code does not survive the sharing process exiting.
6. B does not import it, or imports it with fields changed.
7. B imports it again on a second paste, or again when it arrives inside chat text.
8. A mangled, oversized or tampered code creates a row, raises, or says nothing.
9. The four card buttons under Guide me there are not the same width.
10. Plain text creates a row or says nothing.
11. An imported code comes back after its bookmark was deleted.
12. Share bookmark redraws the whole window (visible flicker) to set one line.
13. The panel still imports from the clipboard on its own (1 s landed poll).
14. The success line does not read `<System> <Planet> Location <n> <Material> <n> rigs
    bookmark imported`, or the box keeps the code.
15. The EDMC panel still has an Import row.
16. The import row is taller than one line, or not below the bookmark list.
17. Text typed into the box is lost when the window redraws.

## Checked

All of 1-17. 8 includes NaN and zero radius, a 5,000-char body name, an int
over 2^63 and an unknown Amount. The Import button is found in the RhinoData window
and pressed with `invoke()`; the text goes in with `Entry.insert`. 16: row
under 30 px, top edge below every bookmark row.

## Not covered

- Key events: Ctrl+V and Enter are not sent; `insert` and `invoke()` stand in.
- The box in a window with bodies but no bookmarks.
- A code pasted through Discord or a browser that rewraps or trims it.
- EDMC itself: the panel is built by `main.build` on a withdrawn Tk root, not
  inside EDMC's window.
- The standalone build.
