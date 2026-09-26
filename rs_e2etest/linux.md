# E2E: Linux chat commands (#12), arrow position (#11), material pick (#10)

Harness: `rs_e2etest/linux_e2e.py`. Runs on Windows with the Win32 paths
switched off in-process (`hotkey.available`, `overlay.win32` -> False,
`overlay._game_rect` -> None). Drives the real `main.journal_entry`,
`minimap.prefs`, `overlay.start` / `_tick` and the arrow's Tk drag bindings.
Seeded from a read-only copy of the live db (real bookmarks).
Output: `rs_e2etest/out/<timestamp>/report.txt`. No screenshot: the arrow's
transparent colour shows the desktop behind it (screenshot rule).

## Ways it can fail end to end

Chat commands (#12):

1. `SendText` with `!rs center` never reaches the callback (event name,
   field name `Message`, prefix match, case, surrounding spaces).
2. A callback fires on Windows too (chat must stay Linux only).
3. A message that only starts with the prefix (`!rs centerx`, `!rsc`) or
   ordinary chat fires a callback.
4. The callback runs off the Tk thread (must go through `_on_ui`).
5. Settings still shows OptionMenus off Windows, or prefs_changed writes a
   bogus combo from the chat label (`rsplit("+")` on `!rs center`).
6. The map's hint rows still name Ctrl+Alt keys off Windows.
7. `hotkey.start` off Windows logs nothing a user can find.

Arrow position (#11):

8. No stored position: arrow not at the old default (centre of virtual screen).
9. Stored position ignored by `_place()`.
10. Drag does not move the window, or `_tick` pulls it back mid-drag.
11. Drop not stored in `rhinospotter_arrow_xy`.
12. Stored position off every screen not clamped back on.
13. Right-click reset leaves the old position in place.
14. Windows path changed: with `_game_rect()` a rect, the arrow goes top
    middle of the game as before and drag bindings are absent.

Material pick (#10):

15. Never picked: the list is not the old default (worth, 5.7.12 switch off).
16. Old switch `rhinospotter_low_value` on: not all 38.
17. Select dialog opens with ticks not matching what the list shows.
18. OK in the dialog writes config before Settings OK (Settings Cancel must drop it).
19. Settings OK does not store the pick, or the dropdown is not refilled from it.
20. The pick is not exact: a bookmarked but unticked material still listed
    (seen on the owner's db: 16 bookmarked materials kept), or the material
    in the box dropped (it must stay).
    Unticking must only hide: every bookmark row stays as it was.
21. Dialog closed with X counts as a pick.
22. Never picked read as "picked nothing": EDMC's `get_list` returns [] for a
    missing key (seen in 5.8.0 pre-release: the dialog opened all unticked).
    None ticked on OK: key removed, default again.
23. A list that still comes out empty (broken config) gives a dropdown with
    nothing in it and no word on why: needs the disabled
    `scan.NO_MATERIALS` hint in the panel and the RhinoData picker.
24. The update drops bookmarked materials from the lists: the first start
    with an empty `rhinospotter_materials` must store the 18 over 50,000
    Cr/t plus every bookmarked material, once; never over a stored pick.

## What the harness replaces, and what that hides

| Replaced | By | Hidden |
|---|---|---|
| Linux / Flatpak / XWayland | Windows with Win32 calls patched off | X11 `overrideredirect` window not taking mouse events; KWin/Wayland refusing a client-set position; real multi-monitor coordinates |
| Elite writing SendText | a dict handed to `journal_entry` | whether local chat with `!rs` is broadcast to other commanders; whether the game logs it when chat is sent in the SRV |
| EDMC config | dict with `get_str`/`set` | EDMC type coercion |
| mouse drag | `event_generate` on the canvas | real pointer grab under a WM |
| EDMC Settings dialog | `main.prefs(root)` in a Tk frame, `main.prefs_changed()` for OK | EDMC Cancel path; myNotebook styling; EDMC's own grab fighting the dialog's `grab_set` |
| EDMC `config.get_list` / `set(list)` | dict; `get_list` copies EDMC 6.1's missing-key rule (bytecode of `config/__init__.pyc`) | registry REG_MULTI_SZ round-trip of the stored list |

Acceptance for the hidden rows: the reporter on #11 / #12.
