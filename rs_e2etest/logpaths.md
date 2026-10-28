# logpaths_e2e.py - what it covers and what it hides

`python rs_e2etest/logpaths_e2e.py`. One child process, LOCALAPPDATA at
`out/<timestamp>/` (under the home folder, so every plugin path is one to
hide). A FileHandler on the `RhinoSpotter` logger writes `plugin.log`; the
check reads that file back. Output: `report.txt` with PASS/FAIL lines and
every log line written.

Covers: the title of the window in front (e.g. a browser tab) and the home
folder (`C:\Users\<account>\...`) are kept out of the plugin log.

## Ways it can fail, each checked

1. `instance: the EDMC plugin holds <PATH>` (INFO, every start,
   `load.plugin_start3`) still names the home folder.
2. An OSError message (`{err}`) names it: `coverstore.save_png` with `root`
   a file, so `os.makedirs` raises with the full path in the text, in repr
   form with doubled backslashes (`'C:\\Users\\<account>\\...'`). The leak
   check matches `users<one or more \ or />account`, case-insensitive.
3. A traceback names it: `main.open_scan` with `scan.show` raising;
   `logger.exception("RhinoData failed")` prints frames from
   `rs_ui/main.py` under the home folder.
4. The scrub drops the line instead of rewriting it: each of 1-3 must be in
   the log, with `~` where the home folder was.
5. Forward-slash form `C:/Users/<account>` passes: a message logged with
   the slash form of the home folder.
6. Different casing passes: home folder logged upper-cased.
7. `minimap: down, Elite not in front` still carries the foreground window
   title: `minimap._show_map` run with this terminal in front (Elite not
   running); the line must be exactly `minimap: down, Elite not in front`.
8. The check reads nothing: `plugin.log` empty or missing fails.

## Not covered

- EDMC's own handler and formatter: the run attaches a plain FileHandler.
  The filter sits on the plugin logger, before propagation, so any handler
  gets the scrubbed record; a formatter that overrides `formatException`
  is bypassed (exc_text is set by the filter). Not run inside EDMC.
- Lines EDMC itself writes (plugin load path, its own config) - not ours.
- Linux home (`/home/<account>`): same code path, not run here.
