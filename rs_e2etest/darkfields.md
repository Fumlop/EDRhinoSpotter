# darkfields_e2e

Location and Rigs Spinboxes readable under EDMC's dark theme (issue #28).

EDMC's `theme.register` has no Spinbox branch: it compares fg/bg with a Label's
defaults. Tk unix: Label and Spinbox fg both `#000000` -> fg recoloured to the
dark theme's light colour; bg `#ffffff` vs `#d9d9d9` -> counted as set, kept white.

Child per case: stub `config` (`theme`, `dark_text`), stub `theme` with EDMC's
register / _update_widget / apply, `load.plugin_start3` + `plugin_app`, then
`theme.register(frame)` + `apply` as EDMarketConnector.py does. Linux cases set
Tk's unix defaults through the option database.

| Case | Expect |
|---|---|
| linux dark, linux transparent, windows dark | Location luminance gap fg/bg >= 0.5, bg luminance < 0.3 |
| linux default | gap >= 0.5, bg Tk default (luminance > 0.7) |
| linux dark -> default on Settings OK | Tk default colours back |
| linux default -> dark on Settings OK | dark box |

Premise: on the old code linux dark is white on white (gap 0.00), 11/18.

Not covered: real EDMC theme.py (the stub copies its branches); real X11 Tk
defaults (option database stands in); the dark theme's real `highlight` colour.
