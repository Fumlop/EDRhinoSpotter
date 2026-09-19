"""Where the game writes, asked of EDMC rather than assumed.

The sources are faked here rather than mocked around: a fake `monitor` module
and a fake `config` module are what EDMC actually puts in sys.modules, so the
test exercises the same import the plugin does.
"""

import os
import sys

import pytest

from rs_core import paths


def fake_module(name, **attributes):
    return type(name, (), attributes)


@pytest.fixture
def no_edmc(monkeypatch):
    """A bare interpreter: neither monitor nor config importable."""
    monkeypatch.delitem(sys.modules, "monitor", raising=False)
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.setattr(sys, "path", [p for p in sys.path])


def with_monitor(monkeypatch, currentdir):
    monkeypatch.setitem(sys.modules, "monitor",
                        fake_module("monitor", monitor=fake_module("m", currentdir=currentdir)))


def with_config(monkeypatch, journaldir):
    monkeypatch.setitem(sys.modules, "config",
                        fake_module("config", config=fake_module(
                            "c", get_str=staticmethod(lambda key: journaldir))))


class TestJournalDir:

    def test_the_folder_edmc_is_watching_wins(self, monkeypatch):
        with_monitor(monkeypatch, r"D:\Games\Elite\Journals")
        with_config(monkeypatch, r"C:\somewhere\else")
        assert paths.journal_dir() == r"D:\Games\Elite\Journals"

    def test_the_setting_answers_when_the_monitor_has_nothing_yet(self, monkeypatch):
        with_monitor(monkeypatch, None)
        with_config(monkeypatch, r"D:\Games\Elite\Journals")
        assert paths.journal_dir() == r"D:\Games\Elite\Journals"

    def test_a_proton_prefix_is_just_a_path(self, monkeypatch):
        prefix = ("/home/cmdr/.steam/steam/steamapps/compatdata/359320/pfx/"
                  "drive_c/users/steamuser/Saved Games/Frontier Developments/Elite Dangerous")
        with_monitor(monkeypatch, prefix)
        assert paths.journal_dir() == prefix

    def test_a_tilde_from_the_setting_is_expanded(self, monkeypatch):
        monkeypatch.delitem(sys.modules, "monitor", raising=False)
        with_config(monkeypatch, "~/journals")
        assert "~" not in paths.journal_dir()

    def test_without_edmc_the_windows_default_is_the_fallback(self, no_edmc, monkeypatch):
        monkeypatch.setenv("USERPROFILE", r"C:\Users\cmdr")
        found = paths.journal_dir()
        assert found.startswith(r"C:\Users\cmdr")
        assert found.endswith("Elite Dangerous")
        assert "%" not in found                   # nothing left unexpanded

    def test_a_monitor_that_raises_does_not_take_the_plugin_with_it(self, monkeypatch):
        class Angry:
            @property
            def currentdir(self):
                raise OSError("no")
        monkeypatch.setitem(sys.modules, "monitor", fake_module("monitor", monitor=Angry()))
        monkeypatch.delitem(sys.modules, "config", raising=False)
        monkeypatch.setenv("USERPROFILE", r"C:\Users\cmdr")
        assert paths.journal_dir().endswith("Elite Dangerous")


@pytest.mark.parametrize("module, attribute", [
    ("rs_core.spotmark", "STATUS_PATH"),
    ("rs_core.replay", "JOURNAL_DIR"),
])
def test_nothing_spells_the_saved_games_path_itself(module, attribute):
    """The two that used to hardcode it. Both go through paths now, so a
    commander who moved the folder is read rather than reported as not flying."""
    import importlib
    value = getattr(importlib.import_module(module), attribute)
    expected = (os.path.join(paths.journal_dir(), "Status.json")
                if attribute == "STATUS_PATH" else paths.journal_dir())
    assert "%" not in value
    assert value == expected


class TestDataRoot:

    def test_windows_uses_localappdata(self, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\cmdr\AppData\Local")
        assert paths.data_root().endswith("RhinoSpotter")
        assert paths.data_root().startswith(r"C:\Users\cmdr\AppData\Local")

    def test_linux_uses_xdg_data_home(self, monkeypatch):
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/home/cmdr/.local/share")
        assert paths.data_root() == os.path.join("/home/cmdr/.local/share", "RhinoSpotter")

    def test_linux_without_xdg_falls_back_to_the_default_share(self, monkeypatch):
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(os.path, "expanduser", lambda path: "/home/cmdr")
        assert paths.data_root() == os.path.join("/home/cmdr", ".local", "share",
                                                 "RhinoSpotter")

    def test_never_inside_the_plugin_folder(self, monkeypatch):
        """A reinstall replaces the plugin folder. The bookmarks are not in it."""
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", "/home/cmdr/.local/share")
        assert "plugins" not in paths.data_root()


class TestOpenPath:

    def test_windows_goes_through_startfile(self, monkeypatch, tmp_path):
        opened = []
        monkeypatch.setattr(os, "startfile", opened.append, raising=False)
        assert paths.open_path(tmp_path) is True
        assert opened == [tmp_path]

    def test_linux_goes_through_xdg_open(self, monkeypatch, tmp_path):
        monkeypatch.delattr(os, "startfile", raising=False)
        monkeypatch.setattr(paths.sys, "platform", "linux")
        called = []
        monkeypatch.setattr(paths.subprocess, "Popen", lambda args: called.append(args))
        assert paths.open_path(tmp_path) is True
        assert called == [["xdg-open", str(tmp_path)]]

    def test_macos_goes_through_open(self, monkeypatch, tmp_path):
        monkeypatch.delattr(os, "startfile", raising=False)
        monkeypatch.setattr(paths.sys, "platform", "darwin")
        called = []
        monkeypatch.setattr(paths.subprocess, "Popen", lambda args: called.append(args))
        assert paths.open_path(tmp_path) is True
        assert called == [["open", str(tmp_path)]]

    def test_no_viewer_falls_back_to_the_browser(self, monkeypatch, tmp_path):
        """Never a raise: it is a convenience button on a window with work to do."""
        monkeypatch.delattr(os, "startfile", raising=False)
        monkeypatch.setattr(paths.sys, "platform", "linux")
        monkeypatch.setattr(paths.subprocess, "Popen",
                            lambda args: (_ for _ in ()).throw(FileNotFoundError("xdg-open")))
        tried = []
        monkeypatch.setattr(paths.webbrowser, "open", lambda url: bool(tried.append(url)) or True)
        assert paths.open_path(tmp_path) is True
        assert tried and tried[0].startswith("file:")


class TestOnWindows:

    def test_matches_whether_windll_is_there(self):
        import ctypes
        assert paths.on_windows() is hasattr(ctypes, "windll")
