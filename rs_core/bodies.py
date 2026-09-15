"""The bodies of the system you are in, out of the journal.

No tkinter and no network, so it can be checked without EDMC in the way. See
rs_tests/test_bodies.py.

EDMC hands every journal line to journal_entry, and names the system it
believes you are in on each one. That name is taken as it comes: waiting for an
arrival event meant a plugin started while docked knew nothing until the next
jump.

Three events carry the rest:

    Scan              PlanetClass, Landable, Volcanism - everything the ground
                      classification needs. Emitted when the FSS resolves a
                      body, or when the auto-scan sweeps the near ones on
                      arrival. The honk itself emits none.
    FSSBodySignals    how many Planetary Mining Locations a body carries, from
                      the FSS, without flying out to it.
    SAASignalsFound   the same count after a detailed surface scan, which is
                      the authoritative one.

Nothing here asks the network for anything. rs_core/spansh.py does, and hands
what it finds to add_known(), which only fills gaps: the journal wins.

Signals can arrive before or after the Scan for the same body, so counts are
kept beside the bodies and merged on the way out rather than written into a
row that may not exist yet.

The register holds one system at a time. Arriving somewhere clears it and asks
`on_arrive` whether this system has been seen before; whatever comes back is
the starting point, and the scans that follow add to it rather than replace it.

Every change is handed straight to `on_change`, which is where the cache write
hangs - not at the point you leave. A system you never leave, because the game
crashed or EDMC was closed on the pad, is exactly the one you would rather not
scan a second time.
"""

from rs_core import grounds

# Events that mean the commander is now somewhere else. CarrierJump is in the
# list because a carrier jump moves you without an FSDJump.
ARRIVAL_EVENTS = ('FSDJump', 'CarrierJump', 'Location')
SIGNAL_EVENTS = ('FSSBodySignals', 'SAASignalsFound')

# Events that name a body together with its BodyID and SystemAddress. Scan and
# the signals events call the name BodyName, the rest call it Body. A name is
# only unique inside its system; the IDs are what the game keys a body on.
ID_EVENTS = ('Scan', 'FSSBodySignals', 'SAASignalsFound', 'ApproachBody',
             'Touchdown', 'Liftoff', 'Location', 'StartUp')

# The signal type the game uses for a numbered surface mining POI. Its
# Type_Localised is "Planetary Mining Location", but the localised string is
# whatever language the commander plays in, so the token is what we match.
MINING_SIGNAL = '$PlanetaryMiningLocation_Name;'

# What a body or a location count from rs_core/spansh.py is marked with.
SPANSH = 'spansh'


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
    The IDs ride along on each body, and `ids()` hands them to a bookmark or a
    map made on a body the journal has named.
    """

    def __init__(self, on_change=None, on_arrive=None):
        """`on_change(system, bodies)` fires on every scan, count and jump that
        changes the list. `on_arrive(system)` is asked for what is already
        known about a system on the way in, and returns a list of bodies or
        nothing. Both are where the cache hangs, so this file never has to know
        a cache exists."""
        self.system = None
        self.system_address = None
        self.on_change = on_change
        self.on_arrive = on_arrive
        self._bodies = {}
        self._locations = {}
        self._ids = {}
        self._guessed = set()   # names whose location count is Spansh's, not ours
        self._from_cache = False

    def clear(self, system=None):
        self.system = system
        self.system_address = None
        self._bodies = {}
        self._locations = {}
        self._ids = {}
        self._guessed = set()

    def adopt(self, system, bodies):
        """Fill the register from the cache, for a system already visited."""
        self.system = system
        self._bodies = {body['name']: dict(body, ground=grounds.reground(body))
                        for body in bodies if body.get('name')}
        self._locations = {name: body['locations']
                           for name, body in self._bodies.items()
                           if body.get('locations') is not None}
        self._ids = {name: body['body_id'] for name, body in self._bodies.items()
                     if body.get('body_id') is not None}
        # Whose count it is survives a reload: a Spansh count still gives way
        # to the commander's own after a restart, and one the commander has
        # replaced is not taken for Spansh's again.
        self._guessed = {name for name, body in self._bodies.items()
                         if body.get('locations_from') == SPANSH}
        self.system_address = next((body['system_address'] for body in self._bodies.values()
                                    if body.get('system_address') is not None),
                                   self.system_address)
        return len(self._bodies)

    def add_known(self, system, address, found):
        """Bodies from Spansh for `system`. Only the ones not already held go
        in - a journal Scan or the cache wins - and nothing at all when the
        register has moved on to another system meanwhile. True when the list
        changed; the change is written like any other."""
        if not system or system != self.system:
            return False
        if self.system_address is not None and address != self.system_address:
            return False
        changed = False
        for body in found or []:
            name = body.get('name')
            if not name or name in self._bodies:
                continue
            row = {key: value for key, value in body.items() if key != 'locations'}
            self._bodies[name] = row
            if row.get('body_id') is not None:
                self._ids.setdefault(name, row['body_id'])
            if body.get('locations') is not None and name not in self._locations:
                self._locations[name] = body['locations']
                self._guessed.add(name)
            changed = True
        if changed:
            self._persist()
        return changed

    def ids(self, system, name):
        """(system_address, body_id) of a body in this system. Either is None
        when no journal line has said it, and both are when `system` is not the
        one held."""
        if not system or system != self.system:
            return None, None
        return self.system_address, self._ids.get(name)

    def track(self, entry, system=None):
        """Feed one journal event. Returns True if the body list changed.

        The return value is what lets the panel refresh only when there is
        something new, rather than on every line the game writes.
        """
        if not entry:
            return False

        # EDMC names the system it believes you are in on every line it hands
        # over, including the StartUp it synthesises at startup. Waiting for an arrival
        # event instead meant the plugin knew nothing in a system EDMC could
        # name - start it while docked, and the next hundred journal lines were
        # Music and ShipLocker, none of which said where you were.
        changed = self._arrive(system) if system else False

        event = entry.get('event')
        if event in ARRIVAL_EVENTS:
            changed = self._arrive(entry.get('StarSystem') or system) or changed
        elif event in SIGNAL_EVENTS:
            changed = self._signals(entry) or changed
        elif event == 'Scan':
            changed = self._scan(entry, system) or changed
        elif not changed:
            self._note_ids(entry)
            return False

        # After the arrival, which empties the register: the address kept is
        # the new system's.
        self._note_ids(entry)

        # Nothing is written back on the way in. What was just read off disk
        # is already on disk, and rewriting it on every jump would turn a
        # lookup into a write.
        if changed and not self._from_cache:
            self._persist()
        self._from_cache = False
        return changed

    def _arrive(self, name):
        if not name or name == self.system:
            return False

        # Learning the name is not arriving. A signal or scan can reach us
        # before any line has named the system - clearing here would throw
        # away what those lines just told us.
        if self.system is None:
            self.system = name
            known = self.on_arrive(name) if self.on_arrive else None
            if known and not self._bodies:
                self.adopt(name, known)
                self._from_cache = True
            return True

        # An actual change of system. Everything held is about the old one.
        self.clear(name)
        known = self.on_arrive(name) if self.on_arrive else None
        if known:
            self.adopt(name, known)
            self._from_cache = True
        return True

    def _persist(self):
        """Every change goes to disk at once, so nothing is lost to a crash.

        A honk is a burst of these - one write per body, each a transaction
        rewriting the system. That is the price of never scanning a
        system twice, and it is not a price worth optimising until somebody
        notices it.
        """
        if self.on_change and self.system and self._bodies:
            self.on_change(self.system, self.bodies())

    def _note_ids(self, entry):
        # Only lines about where you are. FSDTarget and StartJump carry the
        # address of the system you are about to jump to.
        event = entry.get('event')
        address = entry.get('SystemAddress')
        if address is None or event not in ARRIVAL_EVENTS + ID_EVENTS:
            return
        if event in ARRIVAL_EVENTS or self.system_address is None:
            self.system_address = address
        elif address != self.system_address:
            return              # a line about somewhere else
        name = entry.get('BodyName') or entry.get('Body')
        if event in ID_EVENTS and name and entry.get('BodyID') is not None:
            self._ids[name] = entry['BodyID']

    def _signals(self, entry):
        count = mining_locations(entry)
        name = entry.get('BodyName')
        if count is None or not name:
            return False
        # A detailed surface scan counts more than the FSS did, never fewer, so
        # the larger number is the one that has been looked at hardest. A count
        # from Spansh gives way to the commander's own, whichever is larger.
        if name in self._guessed:
            self._guessed.discard(name)
        elif self._locations.get(name, -1) >= count:
            return False
        self._locations[name] = count
        return name in self._bodies

    def _scan(self, entry, system):
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
            'name':         name,
            'ground':       ground,
            'distance':     entry.get('DistanceFromArrivalLS'),
            'gravity':      entry.get('SurfaceGravity'),
            'volcanism':    (entry.get('Volcanism') or '').strip(),
            'planet_class': entry.get('PlanetClass'),
        }
        # Only when known, so a body from an older cache and the same body
        # scanned again differ by the IDs and get them written. A line without
        # them keeps the ones already held.
        held = self._bodies.get(name, {})
        for key, field in (('system_address', 'SystemAddress'), ('body_id', 'BodyID')):
            value = entry.get(field, held.get(key))
            if value is not None:
                body[key] = value
        if {k: v for k, v in held.items() if k not in ('locations', 'locations_from')} == body:
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
            row.pop('locations_from', None)
            if name in self._guessed:
                row['locations_from'] = SPANSH
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
            buckets.setdefault(grounds.canonical(body['ground']), []).append(body)
        order = {ground: index for index, ground in enumerate(grounds.GROUND_ORDER)}
        return sorted(buckets.items(), key=lambda item: order.get(item[0], len(order)))

    def __len__(self):
        return len(self._bodies)
