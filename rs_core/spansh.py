"""The bodies of a system from Spansh, for the ones the journal has not described.

Asked on the honk (FSSDiscoveryScan), not on every jump, and at most once a
session per system: Spansh is one person's server, and a route jumped through
without honking costs it nothing. A system whose Spansh bodies are already in
the cache is not asked again. Requests say who is asking (User-Agent).

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
import urllib.request

from rs_core import bodies, grounds
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

_warned = False             # a failure is a warning once a session, then debug


def should_ask(entry, register, asked):
    """The SystemAddress to ask Spansh about for this journal event, or None.

    Only the honk, only for the system the register holds, only once a session
    (`asked` is the set of addresses already asked - the caller adds to it), and
    not when the register already has Spansh's bodies for it from the cache.
    """
    if (entry or {}).get("event") != "FSSDiscoveryScan":
        return None
    address = entry.get("SystemAddress")
    if not address or address in asked:
        return None
    if entry.get("SystemName") and entry["SystemName"] != register.system:
        return None
    if any(body.get("source") == SOURCE for body in register.bodies()):
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
    not be asked. [] is an answer: Spansh knows the system and no landables."""
    global _warned
    url = DUMP_URL.format(address=address)
    try:
        if opener is not None:
            raw = opener(url, TIMEOUT_S)
        elif requests is not None:
            response = requests.get(url, timeout=TIMEOUT_S, headers=HEADERS)
            if response.status_code == 404:
                return []           # a system nobody has sent in
            response.raise_for_status()
            raw = response.content
        else:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS),
                                        timeout=TIMEOUT_S) as response:
                raw = response.read()
        return to_bodies(json.loads(raw), address)
    except Exception as err:                        # noqa: BLE001 - offline is normal
        if not _warned:
            logger.warning(f"spansh: no bodies for {address}: {err}; the journal still fills the list")
            _warned = True
        else:
            logger.debug(f"spansh: no bodies for {address}: {err}")
        return None


def fetch_async(address, callback):
    """fetch() off the UI thread; callback(address, bodies or None) lands on the
    worker - a Tk caller bounces it back with after()."""
    thread = threading.Thread(target=lambda: callback(address, fetch(address)),
                              name="rhinospotter-spansh", daemon=True)
    thread.start()
    return thread
