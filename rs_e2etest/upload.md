# E2E: bookmark upload (PR #29), blocker fixes

Harness: `rs_e2etest/upload_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, db seeded from a copy of the live one, a local HTTP
server on 127.0.0.1 as the team server, EDMC's `config` stood in by a dict.
Output: `report.txt`. No grabs. Needs the live db at
`%LOCALAPPDATA%/RhinoSpotter/db/rhinospotter.db` (copied, never written) and tkinter.

## Ways it can fail

- Import raises without LOCALAPPDATA (Linux): `pathlib.Path(None)`.
- Upload data written outside the RhinoSpotter data folder.
- Worker running while uploads are off or URL / access key are empty.
- Nothing uploaded once enabled; or a POST while disabled.
- Commander name sent while "Include CMDR name" was never set.
- The same bookmarks sent again on the next check.
- `stop()` blocks EDMC's shutdown through the retry waits (3 x 5 s) with the
  server down.
- `_on_ui` raises when `_upload_core` is None (it called
  `_upload_core.upload_bookmarks()` unconditionally).
- `_on_ui`, called from the hotkey, press and Spansh threads, runs the
  upload check and a Tk label update on that thread.
- Access key sent over plain http; the full URL (token in path or query)
  written to the log.
- Panel upload line only built when uploads were on at EDMC start: turned
  on in Settings, nothing shows until a restart.
- A broken `upload_data.json` (valid JSON but not an object, unreadable)
  raises in `UploadCore()`, which `main.start()` builds with uploads off too:
  the plugin does not start.
- A 401, non-https URL or missing URL retried 3 times 5 s apart: the answer
  cannot change within a check.
- URL pasted with a leading space: refused as not https.
- A bookmark with no system raises TypeError in the key on every check:
  nothing uploads, the panel stays blank.
- Settings OK waits for the next check (up to 5 min) before the first upload.
- Everything in one POST: no progress to show.
- One failed round (3 attempts) stops uploads until EDMC restarts.
- Panel line shows an HTTP code or "Attempt 1/3" instead of what to do.
- Settings tab shows "Include CMDR name" ticked with nothing stored (UI
  default True, core default False): OK stores True.

## Checks

1. Subprocess without LOCALAPPDATA, XDG_DATA_HOME set: import ok, path under
   `$XDG_DATA_HOME/RhinoSpotter`.
2. `UPLOAD_DATA_FILEPATH` under `out/<ts>/RhinoSpotter`.
3. Disabled 2 s: no POST, no worker thread, < 50 ms CPU.
4. Enabled: one POST per 50, together every bookmark `rs_api.bookmarks()` returns,
   access key sent, CMDR names as stored, `upload_data.json` written.
5. Next check: no second POST.
6. Fresh data, CMDR name off: commander `anonymous`.
7. Server down: `stop()` returns within 1.5 s while in a retry wait; panel
   line says to check the URL in Settings.
8. `rs_ui.main._on_ui` with `_upload_core` None: no raise.
9. `_on_ui` from a worker thread: the upload core is not called.
10. Settings tab built with nothing stored: CMDR name ticked; OK stores True.
11. `http://` URL to a non-loopback host: refused before any request, status
    says to fix it in Settings; the URL path is not in `upload.log`.
12. Server answers 401: panel line says to check the access key in Settings,
    without the HTTP code.
13. Server answers 401: one POST, no retry within the check; then accepts:
    the next check uploads.
14. Panel upload line (a Label gridded and removed as `_panel` does; `_panel`
    needs `build()` state): hidden while off, shown with the text once
    `_upload_core.enabled` is set, hidden again when turned off.
15. `upload_data.json` holding `{oops`, `[]`, or a list of checksums:
    `UploadCore()` builds with empty checksums.
16. URL saved with spaces / a newline around it: uploaded.
17. One bookmark's `system` column NULL and `system` removed from its `data`
    JSON in the test db (`planet_name` is NOT NULL): `rs_api` returns it with system None; every bookmark still uploaded.
18. Uploads on, no access key: no worker thread, panel line says set it; key
    set and `update(True)`: worker runs; URL cleared: worker stops; uploads
    off: no worker, no line.
19. Settings OK with uploads on, URL set, key empty: one warning naming the
    access key; both set: none.
20. Interval 60 s, worker asleep after its first upload; one bookmark's rigs
    changed, `update(True)` (Settings OK): that one bookmark posted within 3 s.
21. Server answering in 0.1 s: one POST per 50 bookmarks, `progress` sampled
    rising with the right total, None when done.
22. Panel bar (a ttk.Progressbar as `_panel` grids it): shown at 150 of 379,
    hidden once `progress` is None.

## Not covered

- The settings tab on screen (built hidden), the panel status line.
- A real server behind Cloudflare (502 path), https.
