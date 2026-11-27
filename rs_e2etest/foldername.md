# foldername_e2e

The plugin logs through EDMC's handlers whatever its folder is called.

EDMC (plug.py) puts the filter that fills `%(osthreadid)s` on
`EDMarketConnector.<folder>` only; a record from another logger name reaches the
`EDMarketConnector` handler without it: `--- Logging error ---` on stderr, line lost.

Per folder `RhinoSpotter`, `EDRhinoSpotter` (git clone), `EDRhinoSpotter-main` (GitHub zip):

1. Child runs `load.plugin_start3` / `plugin_stop` from a copy, LOCALAPPDATA in the run folder: exit 0.
2. No `Logging error` on stderr.
3. `running on` in the handler's file, logged as `EDMarketConnector.<folder>`.

Premise: against the old hardcoded `EDMarketConnector.RhinoSpotter`, checks 2-3 fail
for both other folders (5/9, 4 errors each).

Not covered: EDMC's real EDMCLogging module; the stub reproduces its handler format
and filter placement only.
