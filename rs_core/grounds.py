"""Body class -> ground key, and ground key -> material rates.

No tkinter, network or database imports; testable without EDMC. Tests in
rs_tests/test_grounds.py.

classify()  journal Scan event -> one of the 11 keys in GROUND_ORDER. Reads
            PlanetClass and Volcanism, both present on any Scan event (FSS
            resolve or auto-scan on arrival). FSSDiscoveryScan carries neither.
Sheet       reads mining_sheet.json, packaged with the plugin. materials(),
            best(), rate() and sample() look a ground up in it.

The percentages are measured over mining locations already read. No game feed
reports what a location holds.
"""

import json
import os

RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "mining_sheet.json")

# Display order: metal, rock, ice.
GROUND_ORDER = (
    'metal-rich',
    'high-metal-content',
    'rock 80%+ [none]',
    'rock 80%+ [metallic magma]',
    'rock 80%+ [rocky magma]',
    'rock 80%+ [magma]',
    'rock 80%+ [silicate vapour geysers]',
    'rock 80%+ [silicate magma]',
    'rock 80%+ [other volcanism]',
    'rocky-ice',
    'icy',
)

GROUND_LABEL = {
    'metal-rich':         'Metal-Rich World',
    'high-metal-content': 'High Metal Content World',
    'rock 80%+ [metallic magma]':   'Rocky World [metallic magma]',
    'rock 80%+ [rocky magma]':      'Rocky World [rocky magma]',
    'rock 80%+ [magma]':            'Rocky World [magma]',
    'rock 80%+ [silicate vapour geysers]': 'Rocky World [silicate]',
    'rock 80%+ [silicate magma]':   'Rocky World [silicate magma]',
    'rock 80%+ [other volcanism]':  'Rocky World [volcanic]',
    'rock 80%+ [none]':             'Rocky World',
    'rocky-ice':                    'Rocky Ice World',
    'icy':                          'Icy World',
}

# Ground keys written by 4.1.3 and older, still present in the system cache and
# in hand-copied sheets. canonical() maps them to current keys. 'rock 80%+
# [magma]' covers both magma kinds: Sheet._join_magma builds it from the split
# rows, Sheet._key serves the split keys from it.
LEGACY = {
    'volcanic magma':               'rock 80%+ [magma]',
    'volcanic silicate':            'rock 80%+ [silicate vapour geysers]',
    'rock 80%+ [silicate geysers]': 'rock 80%+ [silicate vapour geysers]',
    'silicate magma':               'rock 80%+ [silicate magma]',
    'volcanic rocky':               'rock 80%+ [other volcanism]',
    'rocky':                        'rock 80%+ [none]',
}
MAGMA = 'rock 80%+ [magma]'
MAGMA_SPLIT = ('rock 80%+ [metallic magma]', 'rock 80%+ [rocky magma]')

# Fallback price in Cr/t for materials with no rows in mining_sheet.json.
# Bromellite: no location read so far has carried it, so values() gave it 0 and
# codes() skipped it. 33,396 Cr is its galaxy-wide average sell price - a market
# average, not the sheet's per-ground median, and the only figure available for
# a material with no locations.
UNSHEETED = {'bromellite': 33396}

# Low-value threshold in Cr/t, measured against values() (median, best across
# grounds). Sheet.worth() drops everything below it. Disabled by the
# rhinospotter_low_value setting.
HIGH_VALUE_MIN = 50000


def canonical(ground):
    """LEGACY key -> current key. Current and unknown keys pass through."""
    return LEGACY.get(ground, ground)

# For a rocky body, volcanism is tested before composition: monazite reads
# 45.6% on magma against 7.9% on silicate, sapphire 29% on metallic magma
# against 0% on rocky, silver 17% against 44%.
_SILICATE = 'silicate'
# Tested before _SILICATE: the sheet buckets silicate magma separately
# (geology.py sil_magma), and both strings contain "silicate".
_SILICATE_MAGMA = 'silicate magma'


def classify(body):
    """Journal Scan dict -> ground key, or None when not landable.

    Reads Landable, PlanetClass and Volcanism. Must stay identical to the
    classifier mining_sheet.json was measured with.
    """
    if not body or not body.get('Landable'):
        return None
    planet = (body.get('PlanetClass') or '').strip().lower()
    if not planet:
        return None

    # PlanetClass before Volcanism. "rocky ice" before "icy" is ordering for
    # readability only; neither prefix matches the other.
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
        return 'rock 80%+ [silicate vapour geysers]'
    if 'metallic' in volcanism:
        return 'rock 80%+ [metallic magma]'
    if 'rocky' in volcanism:
        return 'rock 80%+ [rocky magma]'
    if volcanism:
        return 'rock 80%+ [other volcanism]'
    return 'rock 80%+ [none]'


def reground(body):
    """Cached body dict -> ground key under the current classifier.

    Reclassifies from the stored planet_class and volcanism when present, so a
    body cached under a pre-4.1.4 key is split without a rescan. Falls back to
    canonical(body['ground']).
    """
    if body.get('planet_class'):
        ground = classify({'Landable': True, 'PlanetClass': body['planet_class'],
                           'Volcanism': body.get('volcanism') or ''})
        if ground:
            return ground
    return canonical(body.get('ground'))


def label(ground):
    """Ground key -> GROUND_LABEL text, or the key itself, or 'unknown'."""
    ground = canonical(ground)
    return GROUND_LABEL.get(ground, ground or 'unknown')


class Sheet:
    """mining_sheet.json, parsed once at construction.

    A missing or unparsable file sets .error, leaves .grounds empty and .loaded
    False; every lookup then returns empty. Callers must not depend on it: the
    body list comes from the journal.
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
        self._join_magma()

    def _join_magma(self):
        """Build self.grounds[MAGMA] from the two MAGMA_SPLIT keys.

        No-op when the sheet already carries MAGMA or neither split key. Hits
        are recovered as pct * locations / 100, then re-divided by the combined
        location count. Needed for cached bodies with no stored planet_class,
        which reground() cannot split.
        """
        split = [g for g in MAGMA_SPLIT if g in self.grounds]
        if MAGMA in self.grounds or not split:
            return
        total = sum(self.locations.get(g, 0) for g in split)
        if not total:
            return
        hits, meta = {}, {}
        for ground in split:
            n = self.locations.get(ground, 0)
            for row in self.grounds[ground]:
                hits[row['material']] = hits.get(row['material'], 0) + row['pct'] * n / 100
                meta[row['material']] = row
        rows = [dict(meta[m], pct=round(100 * h / total, 1)) for m, h in hits.items()]
        self.grounds[MAGMA] = sorted(rows, key=lambda row: -row['pct'])
        self.locations[MAGMA] = total

    def _key(self, ground):
        """Ground key -> the key to look up. A split magma key falls back to
        MAGMA when the sheet carries only the combined rows."""
        ground = canonical(ground)
        if ground not in self.grounds and ground in MAGMA_SPLIT and MAGMA in self.grounds:
            return MAGMA
        return ground

    @property
    def loaded(self):
        return bool(self.grounds)

    def codes(self):
        """{lowercased material: 1-3 letter code} for minimap dot labels.

        Codes are unique. Assigned by descending values(), ties by name: first
        letter, else first letter plus the first free letter of the name, else
        first letter plus a digit. Thortveitite T, Thorium TH, Titanium TI.

        Upper case throughout: lowercase l reads as 1 at 12 px. A sheet refresh
        that re-ranks prices can reassign codes.
        """
        price = {name: value for name, value in self.values().items()}
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

    def values(self):
        """{lowercased material: Cr/t} - the median price, best across grounds.

        0 for a material the sheet carries with median 0 or null. Seeded from
        UNSHEETED when .loaded; a sheet row always overrides the seed. Not
        seeded on an unloaded sheet, where it would be the only price and would
        invert worth().

        The single value ranking: codes(), worth() and the minimap's
        next-material-down join all read it.
        """
        price = dict(UNSHEETED) if self.loaded else {}
        for rows in self.grounds.values():
            for row in rows:
                name = row['material'].lower()
                price[name] = max(price.get(name, 0), row.get('median') or 0)
        return price

    def worth(self, materials, minimum=HIGH_VALUE_MIN):
        """`materials` without those priced under `minimum`. Order kept.

        A material values() prices at 0 is kept: unpriced is not cheap. An
        unloaded sheet prices nothing, so nothing is dropped.
        """
        price = self.values()
        return tuple(name for name in materials
                     if not price.get((name or '').lower(), 0)
                     or price[name.lower()] >= minimum)

    def materials(self, ground, limit=None, minimum=0.0):
        """[{material, pct, median, best}, ...] for `ground`, pct descending.

        `minimum` is a percentage floor, `limit` a row count. Rocky ground has
        16 rows above 2%.
        """
        rows = [row for row in self.grounds.get(self._key(ground), []) if row['pct'] >= minimum]
        return rows[:limit] if limit else rows

    def best(self, ground, limit=None, minimum=0.0):
        """materials() re-sorted by pct * median descending.

        Sorting by pct alone put copper, haematite and titanium at the top of
        high-metal ground. Rows with median 0 sort last but are kept.
        """
        rows = sorted(self.materials(ground, minimum=minimum),
                      key=lambda row: -row['pct'] * (row.get('median') or 0))
        return rows[:limit] if limit else rows

    def rate(self, ground, material):
        """pct for one material on `ground`, or None when it has no row.

        None, not 0: no row means unmeasured, a row of 0 means measured at 0.
        """
        for row in self.grounds.get(self._key(ground), []):
            if row['material'].lower() == (material or '').lower():
                return row['pct']
        return None

    def sample(self, ground):
        """Mining locations the ground's percentages were measured over."""
        return self.locations.get(self._key(ground), 0)
