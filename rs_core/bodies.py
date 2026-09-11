"""The bodies of the system you are in, out of the journal.

No tkinter and no network, so it can be checked without EDMC in the way. See
rs_tests/test_bodies.py.

EDMC hands every journal line to journal_entry. Scan events carry everything
the ground classification needs - PlanetClass, Landable, Volcanism - and they
arrive from the honk, so a system you have discovery-scanned is already fully
described. Nothing here asks the network for anything.

The register keeps one system at a time. Jumping clears it, because the panel
answers "what is here", and a list that quietly still held the last system
would answer it wrongly.
"""

from rs_core import grounds

# Events that mean the commander is now somewhere else. CarrierJump is in the
# list because a carrier jump moves you without an FSDJump.
ARRIVAL_EVENTS = ('FSDJump', 'CarrierJump', 'Location')


class Register:
    """Landable bodies of the current system, keyed by name.

    Keyed by name rather than BodyID: a name is what the panel prints and what
    the system map shows, and two scans of one body must not become two rows.
    """

    def __init__(self):
        self.system = None
        self._bodies = {}

    def clear(self, system=None):
        self.system = system
        self._bodies = {}

    def track(self, entry, system=None):
        """Feed one journal event. Returns True if the body list changed.

        The return value is what lets the panel refresh only when there is
        something new, rather than on every line the game writes.
        """
        if not entry:
            return False
        event = entry.get('event')

        if event in ARRIVAL_EVENTS:
            name = entry.get('StarSystem') or system
            # Location fires on game start for the system you are already in,
            # so only an actual change may throw the list away.
            if name and name != self.system:
                self.clear(name)
                return True
            self.system = name or self.system
            return False

        if event != 'Scan':
            return False
        if system and self.system and system != self.system:
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
            'name':      name,
            'ground':    ground,
            'distance':  entry.get('DistanceFromArrivalLS'),
            'gravity':   entry.get('SurfaceGravity'),
            'volcanism': (entry.get('Volcanism') or '').strip(),
            'planet_class': entry.get('PlanetClass'),
        }
        if self._bodies.get(name) == body:
            return False
        self._bodies[name] = body
        return True

    def bodies(self):
        """Landable bodies, nearest first - arrival distance is the only cost
        that separates two bodies of the same ground."""
        return sorted(self._bodies.values(),
                      key=lambda body: (body['distance'] is None,
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
