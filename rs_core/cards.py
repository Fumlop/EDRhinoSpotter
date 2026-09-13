"""Which bodies in a system you have already marked.

Read from the JSON bookmarks spotcard writes, not from the file names. A name
has had its spaces replaced and its material lowercased, so reading a body
back out of one is a guess; the JSON holds what was actually marked.

No tkinter and no PIL, so it can be checked without EDMC or a display. See
rs_tests/test_cards.py.
"""

import json
import os
import tempfile
from datetime import datetime, timezone

from rs_core.logging import logger
from rs_core.spotcard import card_dir


def for_system(system, root=None):
    """Every bookmark marked in that system, newest last.

    The JSON is the bookmark. Older versions wrote a PNG card beside it; that
    card's path is kept in `path` when it is still there, so Delete takes it
    too, and None otherwise. A PNG with no JSON is skipped rather than guessed
    at - a link to the wrong body is worse than no link.
    """
    folder = card_dir(system) if root is None else root
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []

    found = []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or not record.get("planet_name"):
            continue
        card = os.path.join(folder, record.get("card") or os.path.splitext(name)[0] + ".png")
        record["path"] = card if os.path.isfile(card) else None
        record["sidecar"] = path
        found.append(record)
    return found


def delete(record):
    """Remove a bookmark: its JSON, and an old card's PNG if it has one.

    True when something was removed. A file that is already gone is the state
    the caller asked for and not a failure; a file that will not go - open in
    a viewer, on a read-only folder - is, and says so rather than leaving the
    list claiming it is deleted.
    """
    removed = False
    for key in ("path", "sidecar"):
        target = record.get(key)
        if not target:
            continue
        try:
            os.remove(target)
            removed = True
        except FileNotFoundError:
            continue
        except OSError as err:
            logger.warning(f"could not delete {target}: {err}")
            return False
    return removed


def set_depleted(record, depleted, when=None):
    """Mark a bookmark as mined out, or take the mark off. True when written.

    Written into the bookmark's own JSON as `depleted_at` - when it was marked,
    not a yes/no - so the day the community knows how long a patch takes to
    come back, the time is already there to count from. No mark, no key.
    The record in hand is updated to match.
    """
    path = record.get("sidecar")
    if not path:
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if depleted:
            data["depleted_at"] = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
        else:
            data.pop("depleted_at", None)
        folder = os.path.dirname(path) or "."
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder,
                                             suffix=".tmp", delete=False)
        try:
            json.dump(data, handle, indent=1)
        finally:
            handle.close()
        os.replace(handle.name, path)
    except (OSError, ValueError) as err:
        logger.warning(f"could not mark {path} depleted: {err}")
        return False
    if depleted:
        record["depleted_at"] = data["depleted_at"]
    else:
        record.pop("depleted_at", None)
    return True


def by_body(system, root=None):
    """{body name: [card, ...]} for one system.

    Keyed by the body exactly as the journal names it, which is what the scan
    window has in hand - no normalising on either side, so a match is a match.
    """
    grouped = {}
    for record in for_system(system, root):
        grouped.setdefault(record["planet_name"], []).append(record)
    return grouped


def newest(records):
    """The card most recently marked, for a link that has to pick one."""
    if not records:
        return None
    return max(records, key=lambda record: str(record.get("marked_at") or ""))


def ordered(records):
    """The bookmarks of one body, most rigs first, then by location.

    Rigs first because that is the question a list of them answers: of the
    patches you marked on this body, which one was worth the most. Location is
    the order you worked the body in, which is history rather than a decision.

    A bookmark with no rig count sorts last rather than as zero - it was not
    counted, which is not the same as having been counted at none.
    """
    def key(record):
        rigs = record.get("rigs")
        index = record.get("location_index")
        return (rigs is None, -(rigs or 0), index is None, index or 0)

    return sorted(records, key=key)
