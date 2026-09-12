"""Which bodies in a system you have already marked.

Read from the JSON sidecars spotcard writes beside each PNG, not from the file
names. A name has had its spaces replaced and its material lowercased, so
reading a body back out of one is a guess; the sidecar holds what was actually
marked.

No tkinter and no PIL, so it can be checked without EDMC or a display. See
rs_tests/test_cards.py.
"""

import json
import os

from rs_core.logging import logger
from rs_core.spotcard import card_dir


def for_system(system, root=None):
    """Every card marked in that system, newest last.

    A PNG with no sidecar is skipped rather than guessed at - it was written
    by a version that did not keep one, and a link to the wrong body is worse
    than no link.
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
        card = record.get("card") or os.path.splitext(name)[0] + ".png"
        record["path"] = os.path.join(folder, card)
        # Kept because a bookmark is two files and only one of them can be
        # worked out from the other. Deleting one and leaving the other behind
        # is how a folder fills up with sidecars pointing at nothing.
        record["sidecar"] = path
        if os.path.isfile(record["path"]):
            found.append(record)
    return found


def delete(record):
    """Remove a bookmark: the PNG and the sidecar beside it.

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
