"""What a body is, and what that kind of body has been found to hold.

No tkinter, no network, no database, so it can be checked without EDMC in the
way. See rs_tests/test_grounds.py.

Two halves:

  classify()  turns a journal Scan into one of the eight grounds the mining
              sheet measures. PlanetClass and Volcanism arrive with every
              AutoScan, so a honk is enough - no detailed surface scan.
  materials() looks that ground up in ground_rules.json, which is the sheet
              frozen at export time by EDIntel's scripts/export/rhinoscan_data.py.

What a mining location actually holds is in no game feed. These are the rates
across every location read so far, which is a reason to fly somewhere, not a
promise about what is under you.
"""

import json
import os

RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "ground_rules.json")

# The order a system map is read in: metal, then rock, then ice.
GROUND_ORDER = (
    'metal-rich',
    'high-metal-content',
    'volcanic magma',
    'volcanic silicate',
    'volcanic rocky',
    'rocky',
    'rocky-ice',
    'icy',
)

GROUND_LABEL = {
    'metal-rich':         'Metal-Rich World',
    'high-metal-content': 'High Metal Content World',
    'volcanic magma':     'Rocky World [magma]',
    'volcanic silicate':  'Rocky World [silicate]',
    'volcanic rocky':     'Rocky World [volcanic]',
    'rocky':              'Rocky World',
    'rocky-ice':          'Rocky Ice World',
    'icy':                'Icy World',
}

# Magma and silicate carry opposite materials - monazite reads 45.6% on magma
# and 7.9% on silicate - so the volcanism decides the ground before the
# composition does, for a rocky body.
_MAGMA = ('metallic', 'rocky')
_SILICATE = 'silicate'


def classify(body):
    """A journal Scan dict -> a ground key, or None if it is not landable.

    Mirrors the CASE in EDIntel's fetch_hit_rates, so the ground a body lands
    in here is the ground its percentages were measured on. Anything else is
    two tables that look alike and disagree.
    """
    if not body or not body.get('Landable'):
        return None
    planet = (body.get('PlanetClass') or '').strip().lower()
    if not planet:
        return None

    # Body class first, because the game's own word beats anything inferred.
    # "Rocky ice" is checked before "icy" only for readability - neither
    # prefix matches the other.
    if planet.startswith('metal rich') or planet.startswith('metal-rich'):
        return 'metal-rich'
    if planet.startswith('high metal'):
        return 'high-metal-content'
    if planet.startswith('rocky ice'):
        return 'rocky-ice'
    if planet.startswith('icy'):
        return 'icy'

    volcanism = (body.get('Volcanism') or '').strip().lower()
    if _SILICATE in volcanism:
        return 'volcanic silicate'
    if any(word in volcanism for word in _MAGMA):
        return 'volcanic magma'
    if volcanism:
        return 'volcanic rocky'
    return 'rocky'


def label(ground):
    """The ground said the way the system map says it."""
    return GROUND_LABEL.get(ground, ground or 'unknown')


class Sheet:
    """The exported mining sheet, read once.

    A missing or broken file is not a crash: the panel still lists the bodies
    and their types, it just cannot say what they hold. That is the honest
    failure - the body list comes from the journal and owes nothing to this.
    """

    def __init__(self, path=RULES_PATH):
        self.path = path
        self.generated = None
        self.locations = {}
        self.grounds = {}
        self.error = None
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError) as err:
            self.error = str(err)
            return
        self.generated = data.get('generated')
        self.locations = data.get('locations') or {}
        self.grounds = data.get('grounds') or {}

    @property
    def loaded(self):
        return bool(self.grounds)

    def materials(self, ground, limit=None, minimum=0.0):
        """What that ground has been found to hold, likeliest first.

        Returns [{material, pct, median, best}, ...]. `minimum` drops the long
        tail: on rocky ground sixteen materials qualify and nobody reads past
        the fourth.
        """
        rows = [row for row in self.grounds.get(ground, []) if row['pct'] >= minimum]
        return rows[:limit] if limit else rows

    def sample(self, ground):
        """How many mining locations the percentages for that ground rest on."""
        return self.locations.get(ground, 0)
