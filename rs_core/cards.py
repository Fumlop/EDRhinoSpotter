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
        if os.path.isfile(record["path"]):
            found.append(record)
    return found


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
