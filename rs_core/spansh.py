"""The bodies of a system from Spansh, for the ones the journal has not described.

Spansh is one person's server, so it is asked as little as possible:

- on the honk (FSSDiscoveryScan), not on every jump - a route jumped through
  without honking costs it nothing;
- at most once a session per system;
- never for a system whose Spansh bodies are already in the cache;
- never for a system nobody has discovered - the star scanned on arrival says
  WasDiscovered: false, and Spansh cannot know what nobody has sent;
- not again for EMPTY_DAYS after Spansh had nothing for a system - kept in
  the database, so a restart does not ask again;
- not at all for PAUSE_S after a failed request (timeout, 429, 5xx, garbage) -
  one attempt, no retries.

Requests say who is asking (User-Agent).

The honk finds bodies and describes none of them: only an FSS resolve or a
fly-by writes a Scan. In a system somebody else has already scanned, Spansh
has the same fields - planet class, volcanism, gravity, distance - and the
mining location count on top.

    https://spansh.co.uk/api/dump/<SystemAddress>

Spansh fills gaps and never overrides. A body the journal or the cache already
holds is left alone, and a Scan of a Spansh body replaces it. Offline, a
timeout or a bad answer is logged and changes nothing - the classic way goes
on as before.

Each body from here carries "source": "spansh".

No tkinter. See rs_tests/test_spansh.py.
"""

import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from rs_core import bodies, database, grounds
from rs_core.logging import logger
from rs_core.update import VERSION

try:
    import requests         # ships inside EDMC, with its own certificates
except ImportError:         # pragma: no cover - bare interpreter
    requests = None

DUMP_URL = "https://spansh.co.uk/api/dump/{address}"
TIMEOUT_S = 15
SOURCE = "spansh"
G = 9.80665                 # Spansh gravity is in g, the journal's SurfaceGravity in m/s²

HEADERS = {"User-Agent": f"RhinoSpotter/{VERSION} (EDMC plugin; github.com/Fumlop/EDRhinoSpotter)"}

EMPTY_DAYS = 30             # a system Spansh had nothing for is not asked again for this long
PAUSE_S = 3600              # after a failed request, nothing is asked for this long

_warned = False             # a failure is a warning once a session, then debug
_paused_until = 0.0         # time.monotonic() before which nothing is asked
_empty = {}                 # SystemAddress -> bool, known_empty() answers already looked up


def undiscovered(entry):
    """The SystemAddress of a system nobody has discovered, from the arrival
    auto-scan of its main star (WasDiscovered: false), or None."""
    if (entry or {}).get("event") != "Scan" or "StarType" not in entry:
        return None
    if entry.get("DistanceFromArrivalLS") != 0 or entry.get("WasDiscovered") is not False:
        return None
    return entry.get("SystemAddress")


def paused():
    return time.monotonic() < _paused_until


def _meta_key(address):
    return f"spansh-empty:{address}"


def known_empty(address, db=None):
    """Whether Spansh had nothing for this system less than EMPTY_DAYS ago."""
    if address in _empty:
        return _empty[address]
    try:
        with database.connect(db) as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?",
                               (_meta_key(address),)).fetchone()
        when = datetime.fromisoformat(row[0]) if row else None
    except Exception as err:                        # noqa: BLE001 - then just ask
        logger.debug(f"spansh: could not read the empty mark of {address}: {err}")
        return False
    _empty[address] = bool(when) and datetime.now(timezone.utc) - when < timedelta(days=EMPTY_DAYS)
    return _empty[address]


def _mark_empty(address, db=None):
    _empty[address] = True
    try:
        with database.connect(db) as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         (_meta_key(address),
                          datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except Exception as err:                        # noqa: BLE001 - asked again next session
        logger.debug(f"spansh: could not keep the empty mark of {address}: {err}")


def should_ask(entry, register, asked, undiscovered_systems=()):
    """The SystemAddress to ask Spansh about for this journal event, or None.

    Only the honk, only for the system the register holds, only once a session
    (`asked` is the set of addresses already asked - the caller adds to it),
    and never when any rule in the module docstring says not to.
    """
    if (entry or {}).get("event") != "FSSDiscoveryScan":
        return None
    address = entry.get("SystemAddress")
    if not address or address in asked or address in undiscovered_systems:
        return None
    if entry.get("SystemName") and entry["SystemName"] != register.system:
        return None
    if any(body.get("source") == SOURCE for body in register.bodies()):
        return None
    if paused() or known_empty(address):
        return None
    return address


def to_bodies(dump, address):
    """Spansh's dump -> landable bodies as the register holds them."""
    system = (dump or {}).get("system") or {}
    found = []
    for body in system.get("bodies") or []:
        if not isinstance(body, dict) or not body.get("isLandable") or not body.get("name"):
            continue
        # The journal's words: "High metal content body", not "... world", and
        # "major rocky magma volcanism" rather than "Major Rocky Magma".
        planet_class = body.get("subType") or ""
        if planet_class.endswith(" world"):
            planet_class = planet_class[:-len(" world")] + " body"
        volcanism = (body.get("volcanismType") or "").strip()
        volcanism = "" if volcanism.lower() in ("", "no volcanism") else volcanism.lower() + " volcanism"
        ground = grounds.classify({"Landable": True, "PlanetClass": planet_class,
                                  "Volcanism": volcanism})
        if ground is None:
            continue
        gravity = body.get("gravity")
        signals = (body.get("signals") or {}).get("signals") or {}
        row = {
            "name": body["name"],
            "ground": ground,
            "distance": body.get("distanceToArrival"),
            "gravity": gravity * G if isinstance(gravity, (int, float)) else None,
            "volcanism": volcanism,
            "planet_class": planet_class,
            "system_address": address,
            "source": SOURCE,
        }
        if body.get("bodyId") is not None:
            row["body_id"] = body["bodyId"]
        count = signals.get(bodies.MINING_SIGNAL)
        if isinstance(count, int):
            row["locations"] = count
        found.append(row)
    return found


def fetch(address, opener=None):
    """The landable bodies Spansh has for that system, or None when it could
    not be asked. [] is an answer - nothing known, or no landables - and is
    remembered for EMPTY_DAYS. A failure pauses every request for PAUSE_S."""
    global _warned, _paused_until
    url = DUMP_URL.format(address=address)
    try:
        if opener is not None:
            raw = opener(url, TIMEOUT_S)
        elif requests is not None:
            response = requests.get(url, timeout=TIMEOUT_S, headers=HEADERS)
            if response.status_code == 404:
                _mark_empty(address)    # a system nobody has sent in
                return []
            response.raise_for_status()
            raw = response.content
        else:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                        timeout=TIMEOUT_S) as response:
                raw = response.read()
        found = to_bodies(json.loads(raw), address)
    except Exception as err:                        # noqa: BLE001 - offline is normal
        _paused_until = time.monotonic() + PAUSE_S
        message = (f"spansh: no bodies for {address}: {err}; not asked again for "
                   f"{PAUSE_S // 60} min, the journal still fills the list")
        if not _warned:
            logger.warning(message)
            _warned = True
        else:
            logger.debug(message)
        return None
    if not found:
        _mark_empty(address)
    return found


def fetch_async(address, callback):
    """fetch() off the UI thread; callback(address, bodies or None) lands on the
    worker - a Tk caller bounces it back with after()."""
    thread = threading.Thread(target=lambda: callback(address, fetch(address)),
                              name="rhinospotter-spansh", daemon=True)
    thread.start()
    return thread
