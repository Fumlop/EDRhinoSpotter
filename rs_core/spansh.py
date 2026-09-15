"""The bodies of a system from Spansh, for the ones the journal has not described.

The honk finds bodies and describes none of them: only an FSS resolve or a
fly-by writes a Scan. In a system somebody else has already scanned, Spansh
has the same fields - planet class, volcanism, gravity, distance - and the
mining location count on top.

    https://spansh.co.uk/api/dump/<SystemAddress>

Spansh is one person's server, so it is asked as little as possible:

- on the honk (FSSDiscoveryScan), not on every jump - a route jumped through
  without honking costs it nothing;
- at most once a session per system;
- never for a system nobody has discovered - the star scanned on arrival says
  WasDiscovered: false;
- not again for ANSWER_DAYS after it answered for a system, bodies or none -
  kept in the database, so a restart does not ask again;
- not at all for PAUSE_S after a failed request (timeout, HTTP error, an
  answer that is not a system) - one attempt, no retries.

EDMC hands plugins only new journal lines - at startup it reads the old ones
for itself and sends a synthetic StartUp - so an EDMC restart does not replay
old honks at Spansh.

Spansh fills gaps and never overrides: see bodies.Register.add_known. Each
body from here carries "source": "spansh". Requests say who is asking.

No tkinter. See rs_tests/test_spansh.py.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

import requests             # ships inside EDMC, with its own certificates

from rs_core import bodies, database, grounds
from rs_core.logging import logger
from rs_core.update import VERSION

DUMP_URL = "https://spansh.co.uk/api/dump/{address}"
TIMEOUT_S = 15
SOURCE = bodies.SPANSH
G = 9.80665                 # Spansh gravity is in g, the journal's SurfaceGravity in m/s²
HEADERS = {"User-Agent": f"RhinoSpotter/{VERSION} (EDMC plugin; github.com/Fumlop/EDRhinoSpotter)"}

ANSWER_DAYS = 30            # a system Spansh answered for is not asked again for this long
PAUSE_S = 3600              # after a failed request, nothing is asked for this long

_warned = False             # a failure is a warning once a session, then debug
_paused_until = 0.0         # time.monotonic() before which nothing is asked
_answered = {}              # SystemAddress -> bool, recently_answered() already looked up


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


# 4.3.3 kept only empty answers, under spansh-empty:. Both count.
_KEYS = ("spansh:{address}", "spansh-empty:{address}")


def recently_answered(address, db=None):
    """Whether Spansh answered for this system less than ANSWER_DAYS ago."""
    if address in _answered:
        return _answered[address]
    try:
        with database.connect(db) as conn:
            rows = conn.execute("SELECT value FROM meta WHERE key IN (?, ?)",
                                [key.format(address=address) for key in _KEYS]).fetchall()
        newest = max((datetime.fromisoformat(value) for (value,) in rows), default=None)
    except Exception as err:                        # noqa: BLE001 - then just ask
        logger.debug(f"spansh: could not read the answer mark of {address}: {err}")
        return False
    _answered[address] = (newest is not None
                          and datetime.now(timezone.utc) - newest < timedelta(days=ANSWER_DAYS))
    return _answered[address]


def mark_answered(address, db=None):
    """Spansh answered for this system and the answer was used: not again for
    ANSWER_DAYS. A failure to keep the mark costs one more request next session."""
    _answered[address] = True
    try:
        with database.connect(db) as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         (_KEYS[0].format(address=address),
                          datetime.now(timezone.utc).isoformat(timespec="seconds")))
    except Exception as err:                        # noqa: BLE001
        logger.debug(f"spansh: could not keep the answer mark of {address}: {err}")


def should_ask(entry, register, known):
    """The SystemAddress to ask Spansh about for this journal event, or None.

    `known` is the caller's {SystemAddress: state} for this session - asked,
    answered or undiscovered; any entry means not now.
    """
    if (entry or {}).get("event") != "FSSDiscoveryScan":
        return None
    address = entry.get("SystemAddress")
    if not address or address in known:
        return None
    if entry.get("SystemName") and entry["SystemName"] != register.system:
        return None
    if paused() or recently_answered(address):
        return None
    return address


def to_bodies(dump, address):
    """Spansh's dump -> landable bodies as the register holds them. Raises
    ValueError when the answer is not a system at all."""
    system = dump.get("system") if isinstance(dump, dict) else None
    if not isinstance(system, dict):
        raise ValueError("not a Spansh system dump")
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


def fetch(address):
    """The landable bodies Spansh has for that system, or None when it could
    not be asked. [] is an answer - a system nobody sent in (404), or no
    landables. A failure pauses every request for PAUSE_S."""
    global _warned, _paused_until
    try:
        response = requests.get(DUMP_URL.format(address=address), timeout=TIMEOUT_S,
                                headers=HEADERS)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return to_bodies(response.json(), address)
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


def fetch_async(address, callback):
    """fetch() off the UI thread; callback(address, bodies or None) lands on the
    worker - a Tk caller bounces it back with after()."""
    thread = threading.Thread(target=lambda: callback(address, fetch(address)),
                              name="rhinospotter-spansh", daemon=True)
    thread.start()
    return thread
