# E2E: the panel above the RhinoData bookmark list (plugin)

Harness: `rs_e2etest/scanpanel_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, the real `main.build` panel on a withdrawn Tk root, the real
`main.open_scan` RhinoData window, a Status.json in the SRV on a body written to
a scratch journal folder, the real `main.make_card` press. Output: `report.txt`
with the widget tree of the copy.

Asked 2026-09-27: the plugin's RhinoData window shows the panel above the table
like the standalone does, so the Bookmark window's hotkey (Ctrl+Alt+D) is enough
without going to EDMC. Behind a setting, `rhinospotter_scan_panel`, on by default (asked the same day).

## Ways it can fail

- Setting never touched: no copy (the default is on).
- Setting off: a copy appears anyway.
- Setting on: no copy, or it is built but not packed, or packed under the list.
- The copy has its own variables: Location, Rigs, Material, Amount, Density typed
  in RhinoData do not reach the bookmark, or the EDMC panel shows other values.
- The copy's Bookmark saves nothing, or is enabled off the ground / disabled on it.
- Status line, landable count, hint or Update state differ between the two panels.
- Window closed with Esc and opened again: TclError on the dead copy, or no copy.
- Setting switched off with the window open: the copy stays.
- Copy shown on the Mapped tab.
- Copy carries the RhinoData button, version label or landable count, or EDMC's panel loses them.
- Settings refill (materials picked) leaves the copy's Material menu stale.
- Standalone: the setting row shows, or a second panel is built next to the docked one.
- Every draw builds a new copy (widgets pile up).

## What the harness replaces, and what that hides

| Replaced | By | Failures it cannot see |
|---|---|---|
| EDMC | `main.start` + `main.build` on a bare root | EDMC's theme over the EDMC panel; the real Settings OK path |
| EDMC config | a dict `Config` on `minimap.config` | persistence of `rhinospotter_scan_panel` |
| `myNotebook` | tkinter widgets (`minimap.nb`) | EDMC's notebook styling of the row |
| the game | Status.json files | Status.json timing |
| mainloop | `root.update()` pumps; `main._report` called on the Tk thread after the save | the worker's `_on_ui` bounce (drops without a mainloop) |
| the eye | widget tree in report.txt | colours and layout as seen; no screen grab taken |

## Checks

1. Setting unset: `minimap.panel_in_scan()` is True. Setting off: open_scan builds no copy, `scan._dock` None.
2. Setting on, open_scan again: the copy is a child of the RhinoData window, mapped, above the list, at its natural width (narrower than the pane), without the RhinoData button, version label or landable count (EDMC's panel keeps them).
3. Copy's Location spinbox typed 7, Rigs 4, Density picked High: `main._loc` / `_rigs` / `_density` read them; EDMC's Amount set Low shows in the copy's menu text.
4. Status.json on the ground: after a poll the copy's Bookmark is normal; off the ground: disabled.
5. Material picked through the copy's menu, copy's Bookmark invoked: one bookmark saved with location 7, rigs 4, amount Low, density High.
6. `_set_status` and the hint show the same text in both panels; EDMC's landable count still set with no copy of it.
7. `_show_update`: the copy's button reads Update, fg WARN.
8. Ten redraws: one copy, same widget.
9. Window destroyed, open_scan: a new copy in the new window, no exception.
10. Mapped tab drawn: the copy is not mapped.
11. Materials refill (`_fill_menu`): the copy's Material menu has the same entries as the EDMC one.
12. Setting off with the window open, open_scan: the copy destroyed, `scan._dock` None.
13. Settings tab: the row is there in the plugin, absent with `scan.host` set (standalone). With `scan.host` set and the setting on, the pre-draw dock fetch keeps the host's dock and builds no copy.
