r"""RhinoSpotter without EDMC:  python standalone.py

The RhinoData window is the main window; the panel EDMC hosts (Bookmark,
Material, Location, Rigs, Amount, Density) sits on its Bookmarks tab, with a
Settings button under it. Same data as the plugin, %LOCALAPPDATA%\RhinoSpotter;
the plugin and this never run together (rs_core/instance.py). Settings go to
%LOCALAPPDATA%\RhinoSpotter\standalone.json, the log to log\rhinospotter.log.
Needs Pillow and requests.

EDMC's modules are stood in for before rs_ui loads: `config` is
rs_standalone/config.py, `myNotebook` is tkinter (the five widgets minimap.py
takes from it have the same names there). The journal feed is
rs_standalone/journal.py. No update check: the updater writes a release over
this folder.
"""

import logging
import logging.handlers
import os
import sys
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OWNER = "RhinoSpotter standalone"
REDRAW_MS = 1000                # how often a register or bookmark change is looked for
LOG_BYTES = 1 << 20             # 1 MiB a log file, LOG_KEPT old ones kept
LOG_KEPT = 2

from rs_standalone import config as _config        # noqa: E402

sys.modules["config"] = _config
sys.modules["myNotebook"] = tk

from rs_core import database, palette, paths       # noqa: E402
from rs_core.logging import logger                 # noqa: E402
from rs_standalone.journal import POLL_MS, Journal  # noqa: E402
from rs_ui import main, scan                       # noqa: E402

LOG_PATH = os.path.join(database.ROOT, "log", "rhinospotter.log")


def _log_to_file():
    """rs_core.logging's logger into LOG_PATH, rotated at LOG_BYTES."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=LOG_BYTES,
                                                   backupCount=LOG_KEPT, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    logger.addHandler(handler)


def _restyle(widget):
    """The panel in the RhinoData colours, as EDMC's theme.update does for its
    own. A foreground left at the system default becomes palette.FG."""
    for child in widget.winfo_children():
        _restyle(child)
    if isinstance(widget, (tk.Entry, tk.Spinbox, tk.Menubutton)):
        scan._style_field(widget)
        return
    options = widget.keys()
    widget.config(bg=palette.BG)
    if "fg" in options and str(widget.cget("fg")).startswith("System"):
        widget.config(fg=palette.FG)
    if isinstance(widget, tk.Button):
        widget.config(bg=palette.PANEL, activebackground=palette.PANEL,
                      activeforeground=palette.ACCENT, relief="solid", borderwidth=1)


class App:
    """The root window, the panel docked in it, the journal and the Settings window."""

    def __init__(self, root):
        self.root = root
        self.settings = None
        self.redraw_key = None
        self.after_ids = {}
        self.dock = tk.Frame(root)
        main.build(self.dock, updates=False).pack(fill="x")
        tk.Button(self.dock, text="Settings", width=13, command=self.open_settings).pack(
            anchor="w", padx=4, pady=(0, 6))
        _restyle(self.dock)
        scan.host(root, self.dock)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.journal = Journal(paths.journal_dir(), main.journal_entry)
        self.journal.start()
        main.open_scan()
        self._schedule("journal", POLL_MS, self._poll_journal)
        self._schedule("redraw", REDRAW_MS, self._redraw_on_change)

    def _schedule(self, name, ms, function):
        self.after_ids[name] = self.root.after(ms, function)

    def _poll_journal(self):
        self._schedule("journal", POLL_MS, self._poll_journal)
        try:
            self.journal.poll()
        except Exception:
            logger.exception("journal poll failed")

    def _redraw_on_change(self):
        """Draw the window again when the register's system or body count, or the
        bookmark revision, moved."""
        self._schedule("redraw", REDRAW_MS, self._redraw_on_change)
        register = main._register
        key = (register.system, len(register), database.revision())
        if key != self.redraw_key:
            if self.redraw_key is not None:
                scan._refresh()
            self.redraw_key = key

    def open_settings(self):
        """main.prefs in a window with OK and Cancel; OK is EDMC's prefs_changed."""
        if self.settings is not None and self.settings.winfo_exists():
            self.settings.lift()
            return
        window = self.settings = tk.Toplevel(self.root)
        window.title("RhinoSpotter settings")
        main.prefs(window).pack(fill="both", expand=True)
        buttons = tk.Frame(window)
        buttons.pack(fill="x", padx=10, pady=10)

        def ok():
            main.prefs_changed()
            window.destroy()
        tk.Button(buttons, text="OK", width=10, command=ok).pack(side="right")
        tk.Button(buttons, text="Cancel", width=10, command=window.destroy).pack(
            side="right", padx=(0, 6))
        window.bind("<Escape>", lambda event: window.destroy())

    def close(self):
        for after_id in self.after_ids.values():
            try:
                self.root.after_cancel(after_id)
            except (ValueError, tk.TclError):
                pass
        try:
            main.stop()
        finally:
            self.root.destroy()


def open_app():
    """The running App, or None after the refusal dialog when another
    RhinoSpotter holds the data folder."""
    _log_to_file()
    root = tk.Tk()
    root.withdraw()
    root.report_callback_exception = lambda *exc: logger.error("Tk callback raised",
                                                               exc_info=exc)
    main.start(HERE, owner=OWNER)
    refusal = main.refused()
    if refusal:
        print(refusal, file=sys.stderr)
        messagebox.showerror("RhinoSpotter", refusal, parent=root)
        root.destroy()
        return None
    logger.info(f"standalone: started, data in {database.ROOT}")
    root.deiconify()
    return App(root)


def run():
    app = open_app()
    if app is None:
        return 1
    app.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
