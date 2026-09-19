"""Version comparison, a release check that never takes the plugin down, and
an installer that either lands whole or does not touch anything."""

import io
import json
import os
import re
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


class TestVersion:
    """The number lives in rs_core/update.py and is repeated as the top
    heading of the changelog. Two places drift; this notices."""

    def test_the_changelog_leads_with_the_shipped_version(self):
        changelog = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "CHANGELOG.md")
        with open(changelog, encoding="utf-8") as handle:
            headings = [line.strip() for line in handle if line.startswith("## ")]
        assert headings, "changelog has no version headings"
        assert headings[0] == f"## {update.VERSION}", (
            f"changelog leads with {headings[0]!r}, code says {update.VERSION}")

    def test_the_plugin_exposes_it(self):
        """The registry reads a VERSION constant or a __version__ dunder off
        the plugin, and the plugin is load.py - not the module three imports
        down where it happens to be defined."""
        import load
        assert load.VERSION == update.VERSION
        assert load.__version__ == update.VERSION

    def test_the_version_is_three_numbers_and_maybe_a_beta(self):
        """"5.1.0", or "5.1.0-beta.1" on a branch that is not for everyone.

        parse() reads the first three numbers either way, so a beta compares
        as its own release and never announces itself to a stable install.
        """
        assert update.parse(update.VERSION) != (0, 0, 0)
        numbers, _, pre = update.VERSION.partition("-")
        assert len(numbers.split(".")) == 3
        assert all(part.isdigit() for part in numbers.split("."))
        assert pre == "" or re.fullmatch(r"(alpha|beta|rc)\.\d+", pre)


class TestIsNewer:
    def test_newer(self):
        assert update.is_newer("v2.1.0", "2.0.0")
        assert update.is_newer("v3.0.0", "2.9.9")

    def test_equal_is_not_an_update(self):
        assert not update.is_newer("v2.0.0", "2.0.0")

    def test_a_local_build_ahead_is_not_told_to_downgrade(self):
        assert not update.is_newer("v2.0.0", "2.1.0")

    def test_defaults_to_the_running_version(self):
        assert not update.is_newer(update.VERSION)
        assert update.RUNNING == update.VERSION or os.environ.get("RHINOSPOTTER_VERSION")

    def test_the_override_makes_the_current_release_look_new(self, monkeypatch):
        """The only way to exercise the update button without publishing a
        throwaway release."""
        monkeypatch.setattr(update, "RUNNING", "1.0.0")
        assert update.is_newer(update.VERSION)


class TestFetch:
    def test_reads_the_tag_off_the_redirect(self):
        assert update.fetch_latest(opener=_landing(
            "https://github.com/Fumlop/EDRhinoSpotter/releases/tag/v9.9.9")) == "v9.9.9"

    def test_the_zip_comes_from_codeload_for_that_tag(self):
        assert update.CODELOAD_ZIP.format(tag="v9.9.9") == \
            "https://codeload.github.com/Fumlop/EDRhinoSpotter/legacy.zip/refs/tags/v9.9.9"

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

    def test_a_page_that_does_not_land_on_a_tag(self):
        """No releases yet: releases/latest lands on the releases list."""
        assert update.fetch_latest(opener=_landing(
            "https://github.com/Fumlop/EDRhinoSpotter/releases")) is None

    def test_a_failure_warns_once_a_session(self, monkeypatch):
        warnings = []
        monkeypatch.setattr(update, "_warned", False)
        monkeypatch.setattr(update.logger, "warning", warnings.append)

        def opener(url, timeout=None):
            raise OSError("offline")
        update.fetch_latest(opener=opener)
        update.fetch_latest(opener=opener)
        assert len(warnings) == 1

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

    @pytest.mark.parametrize("name", ["lib", "data", "cards"])
    def test_local_things_are_kept(self, name):
        assert not update.should_copy(name)

    def test_the_mining_sheet_is_replaced(self):
        """A release carries the current sheet; keeping the local one left
        every updated install on the sheet it was first installed with."""
        assert update.should_copy("mining_sheet.json")


class TestInstall:
    def test_puts_the_release_in_place(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "load.py").write_text("old", encoding="utf-8")

        payload = _zipball({"load.py": "new", "rs_core/grounds.py": "new module"})
        assert update.install(payload, str(target))

        assert (target / "load.py").read_text(encoding="utf-8") == "new"
        assert (target / "rs_core" / "grounds.py").read_text(encoding="utf-8") == "new module"

    def test_the_release_sheet_replaces_the_local_one(self, tmp_path):
        target = tmp_path / "plugin"
        target.mkdir()
        (target / "mining_sheet.json").write_text('{"generated": "mine"}', encoding="utf-8")

        payload = _zipball({"load.py": "new", "mining_sheet.json": '{"generated": "theirs"}'})
        assert update.install(payload, str(target))
        assert "theirs" in (target / "mining_sheet.json").read_text(encoding="utf-8")

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


def _landing(final_url):
    """An opener whose response ended at final_url after redirects."""
    class Response:
        def __init__(self, url, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self):
            return final_url
    return Response


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
