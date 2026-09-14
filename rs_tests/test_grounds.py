"""Which ground a body lands in, and what that ground is said to hold."""

import pytest

from rs_core import grounds


class TestClassify:
    """The nine buckets, matched against real PlanetClass strings.

    These have to agree with the classifier the sheet was measured with. Two
    tables that look alike and disagree are worse than one table.
    """

    @pytest.mark.parametrize("planet_class,volcanism,expected", [
        # The game's own classes win before volcanism is looked at.
        ("Metal rich body",         "metallic magma",  "metal-rich"),
        ("Metal-rich body",         "",                "metal-rich"),
        ("High metal content body", "silicate magma",  "high-metal-content"),
        ("High metal content world", "",               "high-metal-content"),
        ("Icy body",                "water geysers",   "icy"),
        ("Rocky ice body",          "",                "rocky-ice"),
        # A rocky body splits on what its volcanism is.
        ("Rocky body", "major metallic magma",          "rock 80%+ [magma]"),
        ("Rocky body", "minor rocky magma",             "rock 80%+ [magma]"),
        ("Rocky body", "major silicate vapour geysers", "rock 80%+ [silicate geysers]"),
        ("Rocky body", "minor silicate magma volcanism", "rock 80%+ [silicate magma]"),
        ("Rocky body", "major water geysers",           "rock 80%+ [other volcanism]"),
        ("Rocky body", "",                              "rock 80%+ [none]"),
    ])
    def test_buckets(self, make_scan, planet_class, volcanism, expected):
        assert grounds.classify(make_scan("B 1 a", planet_class, volcanism)) == expected

    def test_silicate_beats_rocky_in_the_same_string(self, make_scan):
        """'silicate' and 'rocky' both appear in some volcanism strings, and
        silicate is the one that changes which materials are there."""
        body = make_scan("B 1 a", "Rocky body", "minor rocky silicate vapour geysers")
        assert grounds.classify(body) == "rock 80%+ [silicate geysers]"

    def test_case_does_not_matter(self, make_scan):
        assert grounds.classify(make_scan("B", "ROCKY BODY", "MAJOR METALLIC MAGMA")) \
            == "rock 80%+ [magma]"

    @pytest.mark.parametrize("body", [
        None,
        {},
        {"event": "Scan", "PlanetClass": "Rocky body", "Landable": False},
        {"event": "Scan", "PlanetClass": "", "Landable": True},
        {"event": "Scan", "Landable": True},
    ])
    def test_not_a_landable_body(self, body):
        """A star, a gas giant, an unlandable rock: no ground, no row. The
        panel answers what you can put a ship down on."""
        assert grounds.classify(body) is None

    def test_every_bucket_has_a_label(self):
        for ground in grounds.GROUND_ORDER:
            assert grounds.label(ground) != ground

    def test_unknown_ground_labels_as_itself(self):
        assert grounds.label("something new") == "something new"
        assert grounds.label(None) == "unknown"


class TestSheet:
    def test_reads_the_table(self, sheet):
        assert sheet.loaded
        assert sheet.generated == "2026-01-01 00:00 UTC"
        assert sheet.sample("rock 80%+ [magma]") == 57

    def test_materials_come_back_likeliest_first(self, sheet):
        rows = sheet.materials("rock 80%+ [magma]")
        assert [row["material"] for row in rows] == ["Olivine", "Monazite", "Tiny"]

    def test_limit_and_minimum_trim_the_tail(self, sheet):
        assert len(sheet.materials("rock 80%+ [magma]", limit=2)) == 2
        kept = sheet.materials("rock 80%+ [magma]", minimum=2.0)
        assert [row["material"] for row in kept] == ["Olivine", "Monazite"]

    def test_best_puts_what_pays_first(self, sheet):
        # Monazite 45.6% x 400k beats Olivine 56.1% x 50k.
        rows = sheet.best("rock 80%+ [magma]", minimum=2.0)
        assert [row["material"] for row in rows] == ["Monazite", "Olivine"]

    def test_best_sorts_unpriced_last_and_keeps_them(self, tmp_path):
        """The high-metal case: copper is likeliest and has no price."""
        import json
        path = tmp_path / "ground_rules.json"
        path.write_text(json.dumps({"grounds": {"high-metal-content": [
            {"material": "Copper", "pct": 55.5, "median": 0, "best": 0},
            {"material": "Osmium", "pct": 40.1, "median": 46638, "best": 273000},
            {"material": "Iridium", "pct": 19.8, "median": 182000, "best": 400000},
        ]}}), encoding="utf-8")
        rows = grounds.Sheet(str(path)).best("high-metal-content")
        assert [row["material"] for row in rows] == ["Iridium", "Osmium", "Copper"]

    def test_codes_give_the_valuable_material_the_single_letter(self, tmp_path):
        import json
        path = tmp_path / "ground_rules.json"
        path.write_text(json.dumps({"grounds": {"rock 80%+ [none]": [
            {"material": "Titanium", "pct": 52.6, "median": 0, "best": 0},
            {"material": "Thorium", "pct": 47.6, "median": 0, "best": 0},
            {"material": "Thortveitite", "pct": 12.2, "median": 160947, "best": 1},
            {"material": "Tritium", "pct": 5.0, "median": 0, "best": 0},
        ]}}), encoding="utf-8")
        codes = grounds.Sheet(str(path)).codes()
        assert codes["thortveitite"] == "T"
        assert len(set(codes.values())) == len(codes)
        assert codes == {"thortveitite": "T", "thorium": "TH", "titanium": "TI", "tritium": "TR"}

    def test_every_shipped_material_has_its_own_code(self):
        codes = grounds.Sheet().codes()
        assert codes and len(set(codes.values())) == len(codes)
        assert all(len(code) <= 3 for code in codes.values())

    def test_a_sheet_from_before_4_1_3_reads_under_the_current_names(self, tmp_path):
        """An update keeps the local ground_rules.json, which can still carry
        the old names. Its rows must not vanish behind the rename."""
        import json
        path = tmp_path / "ground_rules.json"
        path.write_text(json.dumps({
            "locations": {"volcanic magma": 58, "rocky": 164},
            "grounds": {"volcanic magma": [{"material": "Monazite", "pct": 44.8,
                                            "median": 1, "best": 1}],
                        "rocky": [{"material": "Copper", "pct": 66.5,
                                   "median": 1, "best": 1}]},
        }), encoding="utf-8")
        sheet = grounds.Sheet(str(path))
        assert sheet.rate("rock 80%+ [magma]", "monazite") == 44.8
        assert sheet.sample("rock 80%+ [none]") == 164
        # And a body classified under an old name still finds its rows.
        assert sheet.rate("volcanic magma", "monazite") == 44.8
        assert grounds.label("volcanic silicate") == "Rocky World [silicate]"

    def test_unknown_ground_is_empty_not_an_error(self, sheet):
        assert sheet.materials("rock 80%+ [silicate geysers]") == []
        assert sheet.sample("rock 80%+ [silicate geysers]") == 0

    def test_missing_file_still_gives_a_usable_object(self, empty_sheet):
        """The body list comes from the journal and owes nothing to this file.
        Losing it must cost the percentages, not the panel."""
        assert not empty_sheet.loaded
        assert empty_sheet.error
        assert empty_sheet.materials("rock 80%+ [none]") == []
        assert empty_sheet.sample("rock 80%+ [none]") == 0

    def test_broken_json_is_the_same_as_missing(self, tmp_path):
        path = tmp_path / "ground_rules.json"
        path.write_text("{not json", encoding="utf-8")
        broken = grounds.Sheet(str(path))
        assert not broken.loaded
        assert broken.error

    def test_the_shipped_table_parses(self):
        """The file that actually ships, against the real classifier - a sheet
        keyed by a ground nothing classifies into would be silently empty."""
        shipped = grounds.Sheet()
        if not shipped.loaded:
            pytest.skip("ground_rules.json not exported into this checkout")
        unknown = set(shipped.grounds) - set(grounds.GROUND_ORDER)
        assert not unknown, f"sheet has grounds the classifier never returns: {unknown}"
