r"""EDMC's `config` for standalone.py, over %LOCALAPPDATA%\RhinoSpotter\standalone.json.

standalone.py puts this module in sys.modules["config"] before rs_ui loads, so
`from config import config` in rs_ui/minimap.py, rs_ui/hotkey.py and
rs_core/paths.py gets `config` below. No `appname` here: rs_core/logging.py
takes its outside-EDMC branch.

Keys as in EDMC (rhinospotter_*), plus `journaldir` read by rs_core/paths.py.
Every set() rewrites the file through rs_core.atomic.

No tkinter.
"""

import json
import os

from rs_core import atomic, database
from rs_core.logging import logger

PATH = os.path.join(database.ROOT, "standalone.json")


class Config:
    """get_str/get_bool/get_int/get_list/set/delete as EDMC's config has them.
    A stored value of another type reads as `default`."""

    def __init__(self, path=PATH):
        self.path = path
        self.values = {}
        try:
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                self.values = loaded
            else:
                logger.warning(f"config: {path} is not a JSON object, starting empty")
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as err:
            logger.warning(f"config: {path} unreadable, starting empty: {err}")

    def get_str(self, key, default=None):
        value = self.values.get(key)
        return value if isinstance(value, str) else default

    def get_bool(self, key, default=False):
        value = self.values.get(key)
        return value if isinstance(value, bool) else default

    def get_int(self, key, default=0):
        value = self.values.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    def get_list(self, key, default=None):
        """As EDMC 6.1: a missing key is `default`, or [] for None."""
        value = self.values.get(key)
        if isinstance(value, list):
            return list(value)
        return default if default is not None else []

    def set(self, key, value):
        self.values[key] = value
        self._write()

    def delete(self, key, suppress=False):
        """The key gone from the file; a missing key is not an error (`suppress` as EDMC)."""
        if key in self.values:
            del self.values[key]
            self._write()

    def _write(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            atomic.write_text(self.path, json.dumps(self.values, indent=2, sort_keys=True))
        except OSError as err:
            logger.warning(f"config: could not write {self.path}: {err}")


config = Config()
