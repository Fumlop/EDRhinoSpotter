# E2E: bookmark upload (PR #29), blocker fixes

Harness: `rs_e2etest/upload_e2e.py`. One process, LOCALAPPDATA at
`out/<timestamp>/`, db seeded from a copy of the live one, a local HTTP
server on 127.0.0.1 as the team server, EDMC's `config` stood in by a dict.
Output: `report.txt`. No grabs. Needs the live db at
`%LOCALAPPDATA%/RhinoSpotter/db/rhinospotter.db` (copied, never written) and tkinter.

## Ways it can fail

- Import raises without LOCALAPPDATA (Linux): `pathlib.Path(None)`.
- Upload data written outside the RhinoSpotter data folder.
- Worker busy while uploads are off: wakes every 10 ms instead of blocking.
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
- Panel line shows an HTTP code or "Attempt 1/3" instead of what to do.
- Settings tab shows "Include CMDR name" ticked with nothing stored (UI
  default True, core default False): OK stores True.

## Checks

1. Subprocess without LOCALAPPDATA, XDG_DATA_HOME set: import ok, path under
   `$XDG_DATA_HOME/RhinoSpotter`.
2. `UPLOAD_DATA_FILEPATH` under `out/<ts>/RhinoSpotter`.
3. Disabled 2 s: no POST, worker parked in `Event.wait`, < 50 ms CPU.
4. Enabled: one POST with every bookmark `rs_api.bookmarks()` returns,
   access key sent, commander `anonymous`, `upload_data.json` written.
5. Next check: no second POST.
6. Fresh data, CMDR name on: names sent as stored.
7. Server down: `stop()` returns within 1.5 s while in a retry wait; panel
   line says to check the URL in Settings.
8. `rs_ui.main._on_ui` with `_upload_core` None: no raise.
9. `_on_ui` from a worker thread: the upload core is not called.
10. Settings tab built with nothing stored: CMDR name unticked; OK stores False.
11. `http://` URL to a non-loopback host: refused before any request, status
    says to fix it in Settings; the URL path is not in `upload.log`.
12. Server answers 401: panel line says to check the access key in Settings,
    without the HTTP code.

## Not covered

- The settings tab on screen (built hidden), the panel status line.
- A real server behind Cloudflare (502 path), https.
