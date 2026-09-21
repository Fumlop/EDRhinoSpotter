# E2E: in-plugin updater (rs_core/update.py)

Harness: `rs_e2etest/update_e2e.py`. Replaces `rs_tests/test_update.py`.
Runs the real `rs_core.update` against the real GitHub release page and the
real codeload zips of `Fumlop/EDRhinoSpotter`, and installs over a scratch
copy of the plugin. Output: `rs_e2etest/out/<timestamp>/report.txt`.

## Isolation: what the harness replaces, and what that hides

The harness is not EDMC and does not install over the live plugin. Every
substitution below is a way the real update can fail while the harness passes.

| Replaced | By | Failures it cannot see |
|---|---|---|
| the live plugin folder | `git archive HEAD` extracted to `out/<ts>/plugin`; `rs_core` imported from there, so `install_async`'s default target (`dirname(dirname(update.__file__))`) is the copy | files EDMC holds open: a `.pyd`/`.dll` loaded from `lib/` or a file open in an editor or AV scanner fails `shutil.copy2`/`rmtree` with `PermissionError` half way through the copy pass; the copy has no `lib/`, no `__pycache__` from EDMC's Python |
| EDMC's Python and its `requests`/certifi | the system Python 3.13 with its own `requests` 2.32 | EDMC's bundled certifi being out of date, EDMC's proxy settings, a Python without `requests` (urllib path in `_open`) |
| the Update button (`rs_ui/main.py:651`) | `update.install_async(callback)` called directly, callback on the worker thread | the Tk bounce via `_on_ui`; the button text sequence Update -> Updating... -> Restart EDMC / Retry update |
| EDMC restart after install | `import load` + `load.plugin_start3(copy)` in a fresh subprocess | EDMC's plugin loader, `plugin_app` building widgets, EDMC refusing the plugin for another reason |
| live data `%LOCALAPPDATA%\RhinoSpotter` | `LOCALAPPDATA` = scratch folder, empty | a migration in the new release failing on real data |
| an old installed version doing the install | the current `update.py` (HEAD) installing the current tag v5.6.2 over HEAD with `RHINOSPOTTER_VERSION=5.6.1` | the real installer is the *old* version's `update.py`; a release that changes the zip shape or `KEEP` only breaks for players on an older updater |
| a broken download from GitHub | a local `http.server` serving a truncated, a byte-flipped and a foreign-root copy of the real zip; `update.CODELOAD_ZIP` pointed at it | a GitHub outage mid-stream with HTTP 200 and a short body is the same bytes, so covered; a TLS interception proxy rewriting the body is not |
| unreachable GitHub | `https://127.0.0.1:9/...` (refused), `https://rhinospotter-e2e.invalid/` (no DNS), a local socket that accepts and never answers | captive portals that answer 200 with an HTML page at the release URL (lands on a non-tag URL, same path as "no releases", partly covered) |

## Ways the real update can fail that no check here sees

- Disk full or permission denied during the copy pass: `install` has already
  replaced some top-level entries; no rollback. Only the temp-extract step is
  all-or-nothing.
- A top-level file deleted upstream stays in the plugin folder forever:
  `install` copies over, it only removes stale files inside replaced folders.
  The harness records this as INFO, not as a failure.
- No hash or signature: `update.py` checks only that the zip opens, CRCs
  match and the root starts with `Fumlop-EDRhinoSpotter-`. The harness checks
  the zip against `git ls-tree v5.6.2` blob hashes, which the plugin does not.
  A repo named `Fumlop/EDRhinoSpotter-<anything>` also passes the prefix test.
- GitHub changing the releases/latest redirect or the codeload URL shape: the
  harness sees today's behaviour only.
- Rate limiting or a 429 from github.com: not reproducible on demand.
- Two EDMC instances updating the same folder at once.
- The new code running before restart: `install` replaces files under a
  running EDMC; a lazy import after install mixes old and new modules.
