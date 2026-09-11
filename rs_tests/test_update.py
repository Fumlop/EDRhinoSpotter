"""Version comparison, and a release check that never takes the plugin down."""

import json
import io

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
        def opener(url, timeout=None):
            return io.BytesIO(json.dumps({"tag_name": "v9.9.9"}).encode())
        assert update.fetch_latest(opener=_ctx(opener)) == "v9.9.9"

    @pytest.mark.parametrize("boom", [
        OSError("no network"),
        ValueError("not json"),
        TimeoutError("too slow"),
    ])
    def test_every_failure_is_just_no_answer(self, boom):
        """Offline, rate limited, repo not published: the plugin works without
        any of it, so none of them is worth a different message - or a crash."""
        def opener(url, timeout=None):
            raise boom
        assert update.fetch_latest(opener=opener) is None

    def test_a_release_without_a_tag(self):
        def opener(url, timeout=None):
            return io.BytesIO(b"{}")
        assert update.fetch_latest(opener=_ctx(opener)) is None


def _ctx(opener):
    """urlopen is used as a context manager; wrap a plain BytesIO to match."""
    class Wrapper:
        def __init__(self, url, timeout=None):
            self.stream = opener(url, timeout)

        def __enter__(self):
            return self.stream

        def __exit__(self, *args):
            return False
    return Wrapper
