"""Version comparison, a release check that never takes the plugin down, and
an installer that either lands whole or does not touch anything."""

import io
import json
import os
import zipfile

import pytest

from rs_core import update


class TestParse:
    @pytest.mark.parametrize("tag,expected", [
        ("2.0.0",       (2, 0, 0)),
        ("v2.0.0",      (2, 0, 0)),
        ("v2.1",        (2, 1, 0)),
        ("3",           (3, 0, 0)),
        ("v2.0.0-beta", (2, 0, 0)),
        ("v10.2.3.4",   (10, 2, 3)),
    ])
    def test_tags(self, tag, expected):
        assert update.parse(tag) == expected

    @pytest.mark.parametrize("tag", ["", None, "latest", "nightly"])
    def test_unreadable_tags_sort_lowest(self, tag):
        """A tag nobody can parse must never announce itself as an update."""
        assert update.parse(tag) == (0, 0, 0)
        assert not update.is_newer(tag, "1.0.0")


class TestIsNewer:
    def test_newer(self):
        assert update.is_newer("v2.1.0", "2.0.0")
        assert update.is_newer("v3.0.0", "2.9.9")

    def test_equal_is_not_an_update(self):
        assert not update.is_newer("v2.0.0", "2.0.0")

    def test_a_local_build_ahead_is_not_told_to_downgrade(self):
        assert not update.is_newer("v2.0.0", "2.1.0")

    def test_defaults_to_the_shipped_version(self):
        assert not update.is_newer(update.VERSION)


class TestFetch:
    def test_reads_the_tag(self):
        assert update.fetch_latest(opener=_serving({"tag_name": "v9.9.9"})) == "v9.9.9"

    def test_reads_the_whole_release(self):
        release = update.fetch_release(
            opener=_serving({"tag_name": "v9.9.9", "zipball_url": "https://x/z"}))
        assert release["zipball_url"] == "https://x/z"

    @pytest.mark.parametrize("boom", [
        OSError("no network"),
        ValueError("not json"),
        TimeoutError("too slow"),
    ])
    def test_every_failure_is_just_no_answer(self, boom):
        """Offline, rate limited, no releases yet: the plugin works without any
        of it, so none of them is worth a different message - or a crash."""
        def opener(url, timeout=None):
            raise boom
        assert update.fetch_latest(opener=opener) is None
        assert update.fetch_release(opener=opener) is None

    def test_a_release_without_a_tag(self):
        assert update.fetch_latest(opener=_serving({})) is None

    def test_download_returns_bytes(self):
        assert update.download("https://x/z", opener=_serving_bytes(b"zip")) == b"zip"

    def test_a_download_that_fails_is_none(self):
        def opener(url, timeout=None):
            raise OSError("reset by peer")
        assert update.download("https://x/z", opener=opener) is None


class TestReleaseRoot:
    def test_finds_the_wrapper_folder(self):
        names = ["Fumlop-EDRhinoSpotter-abc123/", "Fumlop-EDRhinoSpotter-abc123/load.py"]
        assert update.release_root(names) == "Fumlop-EDRhinoSpotter-abc123"

    def test_a_zip_from_somewhere_else_is_refused(self):
        """Matched on the prefix rather than "whatever came first": a zip that
        is not the one we asked for must fail before anything is copied over a
        working install."""
        assert update.release_root(["Someone-Else-1/load.py"]) is None
        assert update.release_root([]) is None


class TestShouldCopy:
    @pytest.mark.parametrize("name", ["load.py", "rs_core", "rs_ui", "README.md"])
    def test_code_is_replaced(self, name):
        assert update.should_copy(name)

    @pytest.mark.parametrize("name", ["ground_rules.json", "lib", "data", "cards"])
    def test_local_things_are_kept(self, name):
        """A locally refreshed sheet is newer than the one in a release, so
        the release must not overwrite it."""
        assert not update.should_copy(name)


class TestInstall:
    def test_puts_the_release_in_place(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "load.py").write_text("old", encoding="utf-8")

        payload = _zipball({"load.py": "new", "rs_core/grounds.py": "new module"})
        assert update.install(payload, str(target))

        assert (target / "load.py").read_text(encoding="utf-8") == "new"
        assert (target / "rs_core" / "grounds.py").read_text(encoding="utf-8") == "new module"

    def test_the_exported_sheet_survives(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "ground_rules.json").write_text('{"generated": "mine"}', encoding="utf-8")

        payload = _zipball({"load.py": "new", "ground_rules.json": '{"generated": "theirs"}'})
        assert update.install(payload, str(target))
        assert "mine" in (target / "ground_rules.json").read_text(encoding="utf-8")

    def test_a_directory_is_replaced_not_merged(self, tmp_path):
        """A module deleted upstream has to disappear here too, or it keeps
        being imported by something that no longer expects it."""
        target = tmp_path / "plugin"
        (target / "rs_core").mkdir(parents=True)
        (target / "rs_core" / "gone.py").write_text("stale", encoding="utf-8")

        payload = _zipball({"rs_core/kept.py": "fresh"})
        assert update.install(payload, str(target))
        assert not (target / "rs_core" / "gone.py").exists()
        assert (target / "rs_core" / "kept.py").exists()

    def test_a_zip_from_somewhere_else_changes_nothing(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "load.py").write_text("old", encoding="utf-8")

        payload = _zipball({"load.py": "new"}, root="Someone-Else-1")
        assert not update.install(payload, str(target))
        assert (target / "load.py").read_text(encoding="utf-8") == "old"

    def test_a_truncated_download_changes_nothing(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "load.py").write_text("old", encoding="utf-8")

        assert not update.install(b"not a zip at all", str(target))
        assert (target / "load.py").read_text(encoding="utf-8") == "old"

    def test_no_temporary_folder_survives(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        update.install(_zipball({"load.py": "new"}), str(target))
        assert [p.name for p in target.iterdir()] == ["load.py"]

    def test_no_temporary_folder_survives_a_failure(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        update.install(_zipball({"load.py": "new"}, root="Someone-Else-1"), str(target))
        assert list(target.iterdir()) == []


def _zipball(files, root=None):
    """A GitHub-shaped zipball: everything under one <owner>-<repo>-<sha> folder."""
    root = root or update.ZIP_PREFIX + "abc123"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(f"{root}/{name}", content)
    return buffer.getvalue()


def _serving(payload):
    return _serving_bytes(json.dumps(payload).encode())


def _serving_bytes(payload):
    """urlopen is used as a context manager; wrap the bytes to match."""
    class Wrapper:
        def __init__(self, url, timeout=None):
            self.stream = io.BytesIO(payload)

        def __enter__(self):
            return self.stream

        def __exit__(self, *args):
            return False
    return Wrapper
