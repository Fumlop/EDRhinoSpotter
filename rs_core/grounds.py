"""What a body is, and what that kind of body has been found to hold.

No tkinter, no network, no database, so it can be checked without EDMC in the
way. See rs_tests/test_grounds.py.

Two halves:

  classify()  turns a journal Scan into one of the nine grounds the mining
              sheet measures. PlanetClass and Volcanism arrive with any Scan
              event - the FSS resolving a body, or the auto-scan on arrival.
              The honk itself emits none: it finds the bodies, it does not
              describe them.
  materials() looks that ground up in ground_rules.json, the mining sheet
              frozen at the time the plugin was packaged.

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
    'rock 80%+ [magma]',
    'rock 80%+ [silicate geysers]',
    'rock 80%+ [silicate magma]',
    'rock 80%+ [other volcanism]',
    'rock 80%+ [none]',
    'rocky-ice',
    'icy',
)

GROUND_LABEL = {
    'metal-rich':         'Metal-Rich World',
    'high-metal-content': 'High Metal Content World',
    'rock 80%+ [magma]':            'Rocky World [magma]',
    'rock 80%+ [silicate geysers]': 'Rocky World [silicate]',
    'rock 80%+ [silicate magma]':   'Rocky World [silicate magma]',
    'rock 80%+ [other volcanism]':  'Rocky World [volcanic]',
    'rock 80%+ [none]':             'Rocky World',
    'rocky-ice':                    'Rocky Ice World',
    'icy':                          'Icy World',
}

# The names before 4.1.3. An update keeps the local ground_rules.json (see
# update.KEEP) and the system cache holds bodies classified back then, so both
# can still say 'volcanic magma'. canonical() reads them as the current key.
LEGACY = {
    'volcanic magma':    'rock 80%+ [magma]',
    'volcanic silicate': 'rock 80%+ [silicate geysers]',
    'silicate magma':    'rock 80%+ [silicate magma]',
    'volcanic rocky':    'rock 80%+ [other volcanism]',
    'rocky':             'rock 80%+ [none]',
}


def canonical(ground):
    """A ground key as this version names it, whichever version wrote it."""
    return LEGACY.get(ground, ground)

# Magma and silicate carry opposite materials - monazite reads 45.6% on magma
# and 7.9% on silicate - so the volcanism decides the ground before the
# composition does, for a rocky body.
_MAGMA = ('metallic', 'rocky')
_SILICATE = 'silicate'
# Silicate magma is not a geyser. The sheet keeps it apart (geology.py buckets it
# as sil_magma), so it must not fall into silicate geysers here on the word.
_SILICATE_MAGMA = 'silicate magma'


def classify(body):
    """A journal Scan dict -> a ground key, or None if it is not landable.

    Mirrors the classifier the sheet was measured with, so the ground a body
    lands in here is the ground its percentages came from. Anything else is
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

    volcanism = ' '.join((body.get('Volcanism') or '').lower().split())
    if _SILICATE_MAGMA in volcanism:
        return 'rock 80%+ [silicate magma]'
    if _SILICATE in volcanism:
        return 'rock 80%+ [silicate geysers]'
    if any(word in volcanism for word in _MAGMA):
        return 'rock 80%+ [magma]'
    if volcanism:
        return 'rock 80%+ [other volcanism]'
    return 'rock 80%+ [none]'


def label(ground):
    """The ground said the way the system map says it."""
    ground = canonical(ground)
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
        self.locations = {canonical(k): v for k, v in (data.get('locations') or {}).items()}
        self.grounds = {canonical(k): v for k, v in (data.get('grounds') or {}).items()}

    @property
    def loaded(self):
        return bool(self.grounds)

    def codes(self):
        """{material, lowercased: short code} for labels on the minimap.

        Every code is different. The most valuable material gets its first
        letter, the next one to want that letter gets it plus the first of its
        own letters still free: Thortveitite T, Thorium TH, Titanium TI. Capitals
        throughout - a lowercase l beside a dot at 12 px reads as a 1. Value
        is the median price, best across grounds; a refreshed sheet that
        re-ranks prices can move a code.
        """
        price = {}
        for rows in self.grounds.values():
            for row in rows:
                price[row['material']] = max(price.get(row['material'], 0), row.get('median') or 0)
        taken, codes = set(), {}
        for name in sorted(price, key=lambda n: (-price[n], n)):
            first = name[0].upper()
            wanted = [first] + [first + ch.upper() for ch in name[1:] if ch.isalpha()]
            code = next((c for c in wanted if c not in taken), None)
            n = 2
            while code is None:
                if f"{first}{n}" not in taken:
                    code = f"{first}{n}"
                n += 1
            taken.add(code)
            codes[name.lower()] = code
        return codes

    def materials(self, ground, limit=None, minimum=0.0):
        """What that ground has been found to hold, likeliest first.

        Returns [{material, pct, median, best}, ...]. `minimum` drops the long
        tail: on rocky ground sixteen materials qualify and nobody reads past
        the fourth.
        """
        rows = [row for row in self.grounds.get(canonical(ground), []) if row['pct'] >= minimum]
        return rows[:limit] if limit else rows

    def best(self, ground, limit=None, minimum=0.0):
        """What that ground pays, most per location first: pct times median.

        Likeliest-first put copper, haematite and titanium at the top of
        high-metal ground once the sheet carried the cheap half - common and
        worth nothing. A median of 0 is unpriced; those sort last rather than
        vanish, so a ground with nothing priced still says what it holds.
        """
        rows = sorted(self.materials(ground, minimum=minimum),
                      key=lambda row: -row['pct'] * (row.get('median') or 0))
        return rows[:limit] if limit else rows

    def rate(self, ground, material):
        """What that ground reads for one material, or None if it never has.

        None, not zero: a material nobody has found on a ground and a material
        found on none of its locations are different claims, and only the
        second one is a measurement.
        """
        for row in self.grounds.get(canonical(ground), []):
            if row['material'].lower() == (material or '').lower():
                return row['pct']
        return None

    def sample(self, ground):
        """How many mining locations the percentages for that ground rest on."""
        return self.locations.get(canonical(ground), 0)
