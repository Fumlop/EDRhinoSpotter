"""The bodies of the system you are in, out of the journal.

No tkinter and no network, so it can be checked without EDMC in the way. See
rs_tests/test_bodies.py.

EDMC hands every journal line to journal_entry. Three events matter:

    Scan              PlanetClass, Landable, Volcanism - everything the ground
                      classification needs. Arrives from the honk, so a
                      discovery-scanned system is already fully described.
    FSSBodySignals    how many Planetary Mining Locations a body carries, from
                      the FSS, without flying out to it.
    SAASignalsFound   the same count after a detailed surface scan, which is
                      the authoritative one.

Nothing here asks the network for anything. EDSM and Ardent are not involved:
Ardent has no body endpoints at all, and the rest is the commander's own scan
data.

Signals can arrive before or after the Scan for the same body, so counts are
kept beside the bodies and merged on the way out rather than written into a
row that may not exist yet.

The register holds one system at a time. Arriving somewhere clears it, and
what was there is handed to rs_core.store so the next visit does not need a
second honk.
"""

from rs_core import grounds

# Events that mean the commander is now somewhere else. CarrierJump is in the
# list because a carrier jump moves you without an FSDJump.
ARRIVAL_EVENTS = ('FSDJump', 'CarrierJump', 'Location')
SIGNAL_EVENTS = ('FSSBodySignals', 'SAASignalsFound')

# The signal type the game uses for a numbered surface mining POI. Its
# Type_Localised is "Planetary Mining Location", but the localised string is
# whatever language the commander plays in, so the token is what we match.
MINING_SIGNAL = '$PlanetaryMiningLocation_Name;'


def mining_locations(entry):
    """How many mining locations a signals event reports, or None.

    None rather than 0: a body with no mining signal has not been counted, and
    a body counted at zero has. The panel says "unprobed" for one and nothing
    for the other.
    """
    for signal in entry.get('Signals') or []:
        if signal.get('Type') == MINING_SIGNAL:
            return signal.get('Count')
    return None


class Register:
    """Landable bodies of the current system, keyed by name.

    Keyed by name rather than BodyID: a name is what the panel prints and what
    the system map shows, and two scans of one body must not become two rows.
    """

    def __init__(self, on_leave=None):
        """`on_leave(system, bodies)` fires when a system is left with bodies
        in it - that is where the cache write hangs, so this file never has to
        know that a cache exists."""
        self.system = None
        self.on_leave = on_leave
        self._bodies = {}
        self._locations = {}

    def clear(self, system=None):
        self.system = system
        self._bodies = {}
        self._locations = {}

    def adopt(self, system, bodies):
        """Fill the register from the cache, for a system already visited."""
        self.system = system
        self._bodies = {body['name']: dict(body) for body in bodies if body.get('name')}
        self._locations = {name: body['locations']
                           for name, body in self._bodies.items()
                           if body.get('locations') is not None}
        return len(self._bodies)

    def track(self, entry, system=None):
        """Feed one journal event. Returns True if the body list changed.

        The return value is what lets the panel refresh only when there is
        something new, rather than on every line the game writes.
        """
        if not entry:
            return False
        event = entry.get('event')

        if event in ARRIVAL_EVENTS:
            return self._arrive(entry.get('StarSystem') or system)
        if event in SIGNAL_EVENTS:
            return self._signals(entry)
        if event != 'Scan':
            return False
        return self._scan(entry, system)

    def _arrive(self, name):
        # Location fires on game start for the system you are already in, so
        # only an actual change may throw the list away.
        if name and name != self.system:
            self._leave()
            self.clear(name)
            return True
        self.system = name or self.system
        return False

    def _leave(self):
        if self.on_leave and self.system and self._bodies:
            self.on_leave(self.system, self.bodies())

    def _signals(self, entry):
        count = mining_locations(entry)
        name = entry.get('BodyName')
        if count is None or not name:
            return False
        # A detailed surface scan counts more than the FSS did, never fewer, so
        # the larger number is the one that has been looked at hardest.
        if self._locations.get(name, -1) >= count:
            return False
        self._locations[name] = count
        return name in self._bodies

    def _scan(self, entry, system):
        if system and self.system and system != self.system:
            self._leave()
            self.clear(system)
        elif system and not self.system:
            self.system = system

        ground = grounds.classify(entry)
        if ground is None:
            return False

        name = entry.get('BodyName')
        if not name:
            return False
        body = {
            'name':         name,
            'ground':       ground,
            'distance':     entry.get('DistanceFromArrivalLS'),
            'gravity':      entry.get('SurfaceGravity'),
            'volcanism':    (entry.get('Volcanism') or '').strip(),
            'planet_class': entry.get('PlanetClass'),
        }
        if {k: v for k, v in self._bodies.get(name, {}).items() if k != 'locations'} == body:
            return False
        self._bodies[name] = body
        return True

    def bodies(self):
        """Landable bodies, nearest first - arrival distance is the only cost
        that separates two bodies of the same ground."""
        out = []
        for name, body in self._bodies.items():
            row = dict(body)
            row['locations'] = self._locations.get(name)
            out.append(row)
        return sorted(out, key=lambda body: (body['distance'] is None,
                                             body['distance'] or 0.0, body['name']))

    def by_ground(self):
        """[(ground, [body, ...]), ...] in the order a system map is read.

        Grouped, because the question is not "what is body 4 a" but "is there
        anything here worth landing on" - and the answer is a ground with
        several bodies in it.
        """
        buckets = {}
        for body in self.bodies():
            buckets.setdefault(body['ground'], []).append(body)
        order = {ground: index for index, ground in enumerate(grounds.GROUND_ORDER)}
        return sorted(buckets.items(), key=lambda item: order.get(item[0], len(order)))

    def __len__(self):
        return len(self._bodies)
