"""Bodies from Spansh: mapped to the journal's words, asked politely, and only
ever filling gaps."""

from datetime import datetime, timedelta, timezone

import pytest

from rs_core import bodies, database, spansh

ADDRESS = 3657332462290
# Trimmed from the real dump of Eme and r Velorum, 2026-09-15.
DUMP = {"system": {"name": "Eme", "id64": ADDRESS, "bodies": [
    {"name": "Eme A 1 a", "bodyId": 8, "type": "Planet", "isLandable": True, "subType": "Rocky body",
     "volcanismType": None, "gravity": 0.0528844702763332, "distanceToArrival": 471.305284,
     "signals": {"signals": {"$PlanetaryMiningLocation_Name;": 10,
                             "$SAA_SignalType_Biological;": 3}}},
    {"name": "Eme A 2 a", "bodyId": 12, "type": "Planet", "isLandable": True, "subType": "Icy body",
     "gravity": 0.1, "distanceToArrival": 900.0},
    {"name": "r Velorum 9 a", "bodyId": 40, "type": "Planet", "isLandable": True,
     "subType": "High metal content world", "volcanismType": "Major Rocky Magma",
     "gravity": 0.367236871622311, "distanceToArrival": 1300.0},
    {"name": "Eme A", "bodyId": 1, "type": "Star", "subType": "K (Yellow-Orange) Star"},
    {"name": "Eme A 3", "bodyId": 20, "type": "Planet", "isLandable": False, "subType": "Gas giant"},
]}}


@pytest.fixture(autouse=True)
def polite_state(monkeypatch):
    """The pause and the answer marks are module state; every test starts clean,
    and no test reaches the network."""
    monkeypatch.setattr(spansh, "_paused_until", 0.0)
    monkeypatch.setattr(spansh, "_answered", {})
    monkeypatch.setattr(spansh, "_warned", False)

    def no_network(*args, **kwargs):
        raise AssertionError("a test tried to reach Spansh")
    monkeypatch.setattr(spansh.requests, "get", no_network)


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code, self._payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


@pytest.fixture
def answer(monkeypatch):
    """answer(status, payload) makes requests.get return that; the calls made
    are in answer.calls."""
    calls = []

    def set_answer(status=200, payload=None, error=None):
        def get(url, **kwargs):
            calls.append((url, kwargs))
            if error:
                raise error
            return Response(status, payload)
        monkeypatch.setattr(spansh.requests, "get", get)
    set_answer.calls = calls
    return set_answer


class TestToBodies:

    def test_only_landables_in_the_journals_words(self):
        found = {b["name"]: b for b in spansh.to_bodies(DUMP, ADDRESS)}
        assert sorted(found) == ["Eme A 1 a", "Eme A 2 a", "r Velorum 9 a"]
        hmc = found["r Velorum 9 a"]
        # As the journal Scan of the same body wrote it.
        assert hmc["planet_class"] == "High metal content body"
        assert hmc["volcanism"] == "major rocky magma volcanism"
        assert hmc["ground"] == "high-metal-content"
        assert hmc["gravity"] == pytest.approx(3.601492, abs=1e-3)

    def test_no_volcanism_is_empty_and_the_count_comes_along(self):
        rock = spansh.to_bodies(DUMP, ADDRESS)[0]
        assert rock["volcanism"] == "" and rock["ground"] == "rock 80%+ [none]"
        assert rock["locations"] == 10 and rock["body_id"] == 8
        assert rock["system_address"] == ADDRESS and rock["source"] == "spansh"

    def test_a_body_without_a_count_is_unprobed(self):
        icy = [b for b in spansh.to_bodies(DUMP, ADDRESS) if b["name"] == "Eme A 2 a"][0]
        assert "locations" not in icy

    def test_a_system_without_landables_is_no_bodies(self):
        assert spansh.to_bodies({"system": {"bodies": [None, 3]}}, ADDRESS) == []

    def test_known_count_is_stars_and_planets_like_the_honk(self):
        with_barycentre = {"system": {"bodies": DUMP["system"]["bodies"]
                                      + [{"name": "Eme AB", "type": "Barycentre"}]}}
        assert spansh.known_count(with_barycentre) == 5
        assert spansh.known_count({}) == 0

    def test_an_answer_that_is_not_a_system_raises(self):
        with pytest.raises(ValueError):
            spansh.to_bodies({"error": "maintenance"}, ADDRESS)


class TestFetch:

    def test_an_answer_says_who_is_asking(self, answer):
        answer(200, DUMP)
        found, known = spansh.fetch(ADDRESS)
        assert len(found) == 3 and known == 5
        [(url, kwargs)] = answer.calls
        assert url.endswith(f"/api/dump/{ADDRESS}")
        assert kwargs["headers"]["User-Agent"].startswith("RhinoSpotter/")
        assert kwargs["timeout"] == spansh.TIMEOUT_S

    def test_404_is_an_answer_not_a_failure(self, answer):
        answer(404)
        assert spansh.fetch(ADDRESS) == ([], 0) and not spansh.paused()

    @pytest.mark.parametrize("kind", ["offline", "http 500", "http 429", "not json", "not a system"])
    def test_every_failure_is_none_and_pauses(self, answer, kind):
        answer(**{"offline": {"error": OSError("no route")},
                  "http 500": {"status": 500},
                  "http 429": {"status": 429},
                  "not json": {"payload": ValueError("<html>")},
                  "not a system": {"payload": {"error": "maintenance"}}}[kind])
        assert spansh.fetch(ADDRESS) is None
        assert spansh.paused()

    def test_a_failure_is_a_warning_once(self, answer, caplog):
        answer(error=OSError("no route"))
        with caplog.at_level("DEBUG", logger="RhinoSpotter"):
            spansh.fetch(ADDRESS)
            spansh.fetch(ADDRESS)
        assert [r.levelname for r in caplog.records] == ["WARNING", "DEBUG"]


def honk(name="Eme", address=ADDRESS):
    return {"event": "FSSDiscoveryScan", "Progress": 1.0, "BodyCount": 19,
            "SystemName": name, "SystemAddress": address}


def arrived(saved=None):
    register = bodies.Register(on_change=(lambda system, found: saved.append(found))
                               if saved is not None else None)
    register.track({"event": "FSDJump", "StarSystem": "Eme", "SystemAddress": ADDRESS})
    return register


def scan(name, planet_class="Rocky body", volcanism="", gravity=5.0):
    return {"event": "Scan", "BodyName": name, "Landable": True, "PlanetClass": planet_class,
            "Volcanism": volcanism, "SurfaceGravity": gravity, "DistanceFromArrivalLS": 470.0,
            "SystemAddress": ADDRESS, "BodyID": 8}


def signals(name, count, event="FSSBodySignals"):
    return {"event": event, "BodyName": name, "SystemAddress": ADDRESS,
            "Signals": [{"Type": bodies.MINING_SIGNAL, "Count": count}]}


class TestShouldAsk:
    """Spansh is one person's server: ask on the honk, once, and only when needed."""

    def test_the_honk_asks(self):
        assert spansh.should_ask(honk(), arrived(), {}) == ADDRESS

    def test_a_jump_does_not(self):
        jump = {"event": "FSDJump", "StarSystem": "Eme", "SystemAddress": ADDRESS}
        assert spansh.should_ask(jump, arrived(), {}) is None

    @pytest.mark.parametrize("state", ["asking", "answered", "unreachable", "undiscovered"])
    def test_once_a_session_whatever_happened(self, state):
        assert spansh.should_ask(honk(), arrived(), {ADDRESS: state}) is None

    def test_a_honk_for_another_system_does_not(self):
        assert spansh.should_ask(honk("Loha", 42), arrived(), {}) is None

    def test_not_while_paused(self, monkeypatch):
        monkeypatch.setattr(spansh, "_paused_until", spansh.time.monotonic() + 60)
        assert spansh.should_ask(honk(), arrived(), {}) is None

    def test_an_answer_is_remembered_across_a_restart(self, monkeypatch):
        spansh.mark_answered(ADDRESS)
        monkeypatch.setattr(spansh, "_answered", {})            # EDMC restarted
        assert spansh.recently_answered(ADDRESS)
        assert spansh.should_ask(honk(), arrived(), {}) is None

    def test_an_old_answer_asks_again(self):
        old = (datetime.now(timezone.utc) - timedelta(days=spansh.ANSWER_DAYS + 1)).isoformat()
        with database.connect() as conn:
            conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (f"spansh:{ADDRESS}", old))
        assert spansh.should_ask(honk(), arrived(), {}) == ADDRESS

    def test_a_433_empty_mark_still_counts(self):
        with database.connect() as conn:
            conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)",
                         (f"spansh-empty:{ADDRESS}", datetime.now(timezone.utc).isoformat()))
        assert spansh.recently_answered(ADDRESS)


class TestUndiscovered:

    def test_the_arrival_star_says_so(self):
        star = {"event": "Scan", "StarType": "K", "BodyName": "Eme A",
                "DistanceFromArrivalLS": 0.0, "WasDiscovered": False, "SystemAddress": ADDRESS}
        assert spansh.undiscovered(star) == ADDRESS

    def test_a_discovered_star_or_another_body_is_not(self):
        star = {"event": "Scan", "StarType": "K", "DistanceFromArrivalLS": 0.0,
                "WasDiscovered": True, "SystemAddress": ADDRESS}
        assert spansh.undiscovered(star) is None
        assert spansh.undiscovered(dict(star, WasDiscovered=False, DistanceFromArrivalLS=5.2)) is None
        assert spansh.undiscovered(scan("Eme A 1 a")) is None


class TestAddKnown:
    """Spansh fills gaps. The journal and the cache always win."""

    def test_fills_an_empty_system_and_writes_it(self):
        saved = []
        register = arrived(saved)
        assert register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(register) == 3 and len(saved[-1]) == 3

    def test_a_body_already_scanned_is_left_alone(self):
        register = arrived()
        register.track(scan("Eme A 1 a", gravity=5.0), system="Eme")
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        mine = [b for b in register.bodies() if b["name"] == "Eme A 1 a"][0]
        assert mine["gravity"] == 5.0 and "source" not in mine

    def test_a_later_scan_replaces_the_spansh_body(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert register.track(scan("Eme A 1 a", gravity=5.0), system="Eme")
        mine = [b for b in register.bodies() if b["name"] == "Eme A 1 a"][0]
        assert mine["gravity"] == 5.0 and "source" not in mine

    def test_the_commanders_own_count_replaces_spanshs_even_if_lower(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert register.track(signals("Eme A 1 a", 7), system="Eme")
        assert [b["locations"] for b in register.bodies() if b["name"] == "Eme A 1 a"] == [7]

    def test_a_count_already_held_is_not_replaced(self):
        register = arrived()
        register.track(scan("Eme A 1 a"), system="Eme")
        register.track(signals("Eme A 1 a", 4, "SAASignalsFound"), system="Eme")
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert [b["locations"] for b in register.bodies() if b["name"] == "Eme A 1 a"] == [4]

    def test_an_answer_for_a_system_left_behind_is_dropped(self):
        register = arrived()
        register.track({"event": "FSDJump", "StarSystem": "Loha", "SystemAddress": 42})
        assert not register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(register) == 0

    def test_nothing_new_changes_nothing(self):
        saved = []
        register = arrived(saved)
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        before = len(saved)
        assert not register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))
        assert len(saved) == before


class TestWhoseCountAfterAReload:
    """Whose count it is survives the cache: found by the 4.3.x review."""

    def reload(self, register):
        again = bodies.Register(on_arrive=lambda system: register.bodies())
        again.track({"event": "FSDJump", "StarSystem": "Eme", "SystemAddress": ADDRESS})
        return again

    def test_the_commanders_count_is_not_taken_for_spanshs_after_a_reload(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))    # Spansh 10
        register.track(signals("Eme A 1 a", 12, "SAASignalsFound"), system="Eme")
        again = self.reload(register)
        again.track(signals("Eme A 1 a", 11), system="Eme")         # a smaller FSS count
        assert [b["locations"] for b in again.bodies() if b["name"] == "Eme A 1 a"] == [12]

    def test_spanshs_count_on_a_scanned_body_still_gives_way_after_a_reload(self):
        register = arrived()
        register.add_known("Eme", ADDRESS, spansh.to_bodies(DUMP, ADDRESS))    # Spansh 10
        register.track(scan("Eme A 1 a"), system="Eme")             # source gone, count still Spansh's
        again = self.reload(register)
        again.track(signals("Eme A 1 a", 5), system="Eme")
        assert [b["locations"] for b in again.bodies() if b["name"] == "Eme A 1 a"] == [5]
