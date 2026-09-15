"""A file written whole or not at all."""

import os

import pytest

from rs_core import atomic


class TestWrite:
    def test_writes_text_and_bytes(self, tmp_path):
        atomic.write_text(str(tmp_path / "a.json"), '{"rigs": 6}')
        atomic.write_bytes(str(tmp_path / "b.gz"), b"\x1f\x8b")
        assert (tmp_path / "a.json").read_text(encoding="utf-8") == '{"rigs": 6}'
        assert (tmp_path / "b.gz").read_bytes() == b"\x1f\x8b"

    def test_replaces_what_is_there(self, tmp_path):
        path = str(tmp_path / "a.json")
        atomic.write_text(path, "old")
        atomic.write_text(path, "new")
        assert os.listdir(str(tmp_path)) == ["a.json"]
        assert (tmp_path / "a.json").read_text(encoding="utf-8") == "new"

    def test_a_failed_move_keeps_the_old_file_and_no_temp(self, tmp_path, monkeypatch):
        """The crash between writing and moving: the bookmark on disk is still
        the one that was there, and no .tmp is left beside it."""
        path = str(tmp_path / "a.json")
        atomic.write_text(path, "old")

        def refuse(src, dst):
            raise OSError("disk full")
        monkeypatch.setattr(atomic.os, "replace", refuse)

        with pytest.raises(OSError):
            atomic.write_text(path, "new")
        assert os.listdir(str(tmp_path)) == ["a.json"]
        assert (tmp_path / "a.json").read_text(encoding="utf-8") == "old"

    def test_a_file_held_open_for_a_moment_is_still_replaced(self, tmp_path, monkeypatch):
        """Windows refuses the move while the minimap has the bookmark open;
        the reader is gone a moment later."""
        path = str(tmp_path / "a.json")
        atomic.write_text(path, "old")
        real, refusals = os.replace, [PermissionError("in use")] * 2
        monkeypatch.setattr(atomic.time, "sleep", lambda s: None)

        def busy(src, dst):
            if refusals:
                raise refusals.pop()
            real(src, dst)
        monkeypatch.setattr(atomic.os, "replace", busy)

        atomic.write_text(path, "new")
        assert (tmp_path / "a.json").read_text(encoding="utf-8") == "new"

    def test_a_file_held_open_for_good_gives_up(self, tmp_path, monkeypatch):
        path = str(tmp_path / "a.json")
        atomic.write_text(path, "old")
        calls = []
        monkeypatch.setattr(atomic.time, "sleep", lambda s: None)

        def busy(src, dst):
            calls.append(src)
            raise PermissionError("in use")
        monkeypatch.setattr(atomic.os, "replace", busy)

        with pytest.raises(PermissionError):
            atomic.write_text(path, "new")
        assert len(calls) == atomic.REPLACE_TRIES
        assert os.listdir(str(tmp_path)) == ["a.json"]

    def test_a_failed_write_keeps_the_old_file_and_no_temp(self, tmp_path):
        path = str(tmp_path / "a.gz")
        atomic.write_bytes(path, b"old")
        with pytest.raises(TypeError):
            atomic.write_bytes(path, "not bytes")
        assert os.listdir(str(tmp_path)) == ["a.gz"]
        assert (tmp_path / "a.gz").read_bytes() == b"old"
