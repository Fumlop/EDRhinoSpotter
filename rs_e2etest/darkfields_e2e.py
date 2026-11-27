"""E2E harness: Location and Rigs readable under EDMC's dark theme (issue #28). Checks: darkfields.md.

Run from the plugin folder:  python rs_e2etest/darkfields_e2e.py
Writes rs_e2etest/out/<timestamp>-darkfields/report.txt. Exit code 1 on a failure.

Each case is a child process: LOCALAPPDATA in the run folder, a stub `config`,
and a stub `theme` whose register/_update_widget are EDMC 6.x theme.py's
(EDCD/EDMarketConnector main), cut to the branches a panel reaches.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
# Tk's unix defaults (tkUnixDefault.h): Label fg #000000 bg #d9d9d9, Spinbox/Entry fg #000000 bg #ffffff.
LINUX = {"*Label.foreground": "#000000", "*Label.background": "#d9d9d9",
         "*Spinbox.foreground": "#000000", "*Spinbox.background": "#ffffff",
         "*Entry.foreground": "#000000", "*Entry.background": "#ffffff",
         "*Frame.background": "#d9d9d9"}
DARK_TEXT = "#ff8c00"
CASES = [  # name, option db, theme at start, theme after Settings OK
    ("linux dark", LINUX, 1, None),
    ("linux transparent", LINUX, 2, None),
    ("windows dark", {}, 1, None),
    ("linux default", LINUX, 0, None),
    ("windows default", {}, 0, None),
    ("linux dark -> default on OK", LINUX, 1, 0),
    ("linux default -> dark on OK", LINUX, 0, 1),
]


def child():
    import tkinter as tk
    import types
    options, start_theme, after_theme = json.loads(sys.argv[2])

    class Config(dict):
        def get_str(self, key, default=None): return self.get(key, default)
        def get_bool(self, key, default=False): return self.get(key, default)
        def get_int(self, key, default=0): return self.get(key, default)
        def get_list(self, key, default=None): return self.get(key, default)
        def set(self, key, value): self[key] = value
        def delete(self, key, *args, **kwargs): self.pop(key, None)
    config = Config(theme=start_theme, dark_text=DARK_TEXT)
    sys.modules["config"] = types.SimpleNamespace(appname="EDMarketConnector", config=config)

    class Theme:
        """EDMC theme.py register / _update_widget / apply, Label/Button/Entry/Frame/cursor branches."""
        def __init__(self):
            self.widgets, self.defaults, self.current = {}, {}, {}

        def colors(self, which):
            self.current = ({"background": "grey4", "foreground": config.get_str("dark_text"),
                             "activebackground": config.get_str("dark_text"), "activeforeground": "grey4",
                             "disabledforeground": "#aa5500", "highlight": "#ffffff", "font": "TkDefaultFont"}
                            if which else
                            {"background": "#d9d9d9", "foreground": "#000000", "activebackground": "#ececec",
                             "activeforeground": "#000000", "disabledforeground": "#a3a3a3",
                             "highlight": "blue", "font": "TkDefaultFont"})

        def register(self, widget):
            if not self.defaults:
                self.defaults = {"fg": tk.Label()["foreground"], "bg": tk.Label()["background"],
                                 "font": tk.Label()["font"], "entryfg": tk.Entry()["foreground"],
                                 "entrybg": tk.Entry()["background"], "entryfont": tk.Entry()["font"],
                                 "frame": tk.Frame()["background"]}
            if widget not in self.widgets:
                attribs = set()
                if isinstance(widget, tk.Entry):
                    if widget["foreground"] not in ["", self.defaults["entryfg"]]:
                        attribs.add("fg")
                    if widget["background"] not in ["", self.defaults["entrybg"]]:
                        attribs.add("bg")
                    if "font" in widget.keys() and str(widget["font"]) not in ["", self.defaults["entryfont"]]:
                        attribs.add("font")
                elif isinstance(widget, (tk.Canvas, tk.Frame)):
                    if widget["background"] not in ["", self.defaults["frame"]]:
                        attribs.add("bg")
                elif isinstance(widget, tk.Menu):
                    pass
                else:
                    if "foreground" in widget.keys() and widget["foreground"] not in ["", self.defaults["fg"]]:
                        attribs.add("fg")
                    if "background" in widget.keys() and widget["background"] not in ["", self.defaults["bg"]]:
                        attribs.add("bg")
                    if "font" in widget.keys() and widget["font"] not in ["", self.defaults["font"]]:
                        attribs.add("font")
                self.widgets[widget] = attribs
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    self.register(child)

        def _update_widget(self, widget):
            attribs = self.widgets.get(widget, set())
            keys = widget.keys()
            if "cursor" in keys and str(widget["cursor"]) not in ["", "arrow"]:
                if "fg" not in attribs:
                    widget["foreground"] = self.current["highlight"]
                    if "insertbackground" in keys:
                        widget["insertbackground"] = self.current["foreground"]
                if "bg" not in attribs:
                    widget["background"] = self.current["background"]
                    if "highlightbackground" in keys:
                        widget["highlightbackground"] = self.current["background"]
                if "font" not in attribs:
                    widget["font"] = self.current["font"]
            elif "activeforeground" in keys:
                if "fg" not in attribs:
                    widget["foreground"] = self.current["foreground"]
                    widget["activeforeground"] = self.current["activeforeground"]
                    widget["disabledforeground"] = self.current["disabledforeground"]
                if "bg" not in attribs:
                    widget["background"] = self.current["background"]
                    widget["activebackground"] = self.current["activebackground"]
                if "font" not in attribs:
                    widget["font"] = self.current["font"]
            elif "foreground" in keys:
                if "fg" not in attribs:
                    widget["foreground"] = self.current["foreground"]
                if "bg" not in attribs:
                    widget["background"] = self.current["background"]
                if "font" not in attribs:
                    widget["font"] = self.current["font"]
            elif "background" in keys or isinstance(widget, tk.Canvas):
                if "bg" not in attribs:
                    widget["background"] = self.current["background"]
                    widget["highlightbackground"] = self.current["disabledforeground"]

        def update(self, widget):
            if not self.current:
                return
            self.register(widget)
            self._update_widget(widget)

        def apply(self):
            self.colors(config.get_int("theme"))
            for widget in list(self.widgets):
                if widget.winfo_exists():
                    self._update_widget(widget)
    theme = Theme()
    sys.modules["theme"] = types.SimpleNamespace(theme=theme)

    root = tk.Tk()
    for pattern, value in options.items():
        root.option_add(pattern, value)
    sys.path.insert(0, PLUGIN)
    import load
    from rs_ui import main
    load.plugin_start3(PLUGIN)
    # EDMarketConnector.py: _config_plugins -> plugin_app, then theme.register(frame), theme.apply.
    frame = tk.Frame(root)
    load.plugin_app(frame).grid()
    theme.register(frame)
    theme.apply()
    if after_theme is not None:
        config.set("theme", after_theme)
        theme.apply()                    # EDMC applies the theme on Settings OK, then prefs_changed
        load.prefs_changed("cmdr", False)
    root.update()
    def spins(widget):
        for child in widget.winfo_children():
            yield from ([child] if isinstance(child, tk.Spinbox) else spins(child))
    boxes = list(spins(frame))
    loc = next(w for w in boxes if str(w.cget("textvariable")) == str(main._loc))
    rgb = lambda c: tuple(v // 257 for v in root.winfo_rgb(c))
    print(json.dumps({"fg": rgb(loc.cget("fg")), "bg": rgb(loc.cget("bg")), "fields": len(boxes),
                      "theme": config.get_int("theme")}))
    load.plugin_stop()
    root.destroy()


def luminance(rgb):
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255


def main():
    out = os.path.join(HERE, "out", datetime.now().strftime("%Y%m%d-%H%M%S") + "-darkfields")
    os.makedirs(out)
    lines, failed = [], 0

    def check(name, ok, detail=""):
        nonlocal failed
        failed += not ok
        lines.append(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
        print(lines[-1])

    for name, options, start, after in CASES:
        env = dict(os.environ, LOCALAPPDATA=os.path.join(out, name.replace(" ", "_").replace(">", "")))
        run = subprocess.run([sys.executable, os.path.abspath(__file__), "--child",
                              json.dumps([options, start, after])],
                             cwd=out, env=env, capture_output=True, text=True, timeout=120)
        result = next((json.loads(l) for l in run.stdout.splitlines() if l.startswith("{")), None)
        if result is None:
            check(f"{name}: child ran", False, run.stderr.strip()[-300:])
            continue
        fg, bg = result["fg"], result["bg"]
        contrast = abs(luminance(fg) - luminance(bg))
        dark = result["theme"] != 0
        check(f"{name}: Location text readable (luminance gap >= 0.5)", contrast >= 0.5,
              f"fg {fg} bg {bg} gap {contrast:.2f}")
        if dark:
            check(f"{name}: box dark (bg luminance < 0.3)", luminance(bg) < 0.3, f"bg {bg}")
        else:
            check(f"{name}: box Tk default (bg luminance > 0.7)", luminance(bg) > 0.7, f"bg {bg}")
        check(f"{name}: two Spinboxes in the panel", result["fields"] == 2, str(result["fields"]))

    lines.append(f"{sum(l.startswith('PASS') for l in lines)}/{len(lines)} passed  ->  {out}")
    print(lines[-1])
    with open(os.path.join(out, "report.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child()
    else:
        raise SystemExit(main())
