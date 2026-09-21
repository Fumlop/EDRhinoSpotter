"""Where the game writes, asked of EDMC rather than assumed.

The sources are faked here rather than mocked around: a fake `monitor` module
and a fake `config` module are what EDMC actually puts in sys.modules, so the
test exercises the same import the plugin does.
"""

import sys

import pytest

from rs_core import paths


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """journal_dir() keeps its answer for the process; each test is a start."""
    monkeypatch.setattr(paths, "_found", None)


def fake_module(name, **attributes):
    return type(name, (), attributes)


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

    def test_a_monitor_that_raises_does_not_take_the_plugin_with_it(self, monkeypatch):
        class Angry:
            @property
            def currentdir(self):
                raise OSError("no")
        monkeypatch.setitem(sys.modules, "monitor", fake_module("monitor", monitor=Angry()))
        monkeypatch.delitem(sys.modules, "config", raising=False)
        assert paths.journal_dir().endswith("Elite Dangerous")
