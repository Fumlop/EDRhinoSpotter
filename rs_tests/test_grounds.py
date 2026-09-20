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
        ("Rocky body", "major metallic magma",          "rock 80%+ [metallic magma]"),
        ("Rocky body", "minor rocky magma",             "rock 80%+ [rocky magma]"),
        ("Rocky body", "major silicate vapour geysers", "rock 80%+ [silicate vapour geysers]"),
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
        assert grounds.classify(body) == "rock 80%+ [silicate vapour geysers]"

    def test_case_does_not_matter(self, make_scan):
        assert grounds.classify(make_scan("B", "ROCKY BODY", "MAJOR METALLIC MAGMA")) \
            == "rock 80%+ [metallic magma]"

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
        path = tmp_path / "mining_sheet.json"
        path.write_text(json.dumps({"grounds": {"high-metal-content": [
            {"material": "Copper", "pct": 55.5, "median": 0, "best": 0},
            {"material": "Osmium", "pct": 40.1, "median": 46638, "best": 273000},
            {"material": "Iridium", "pct": 19.8, "median": 182000, "best": 400000},
        ]}}), encoding="utf-8")
        rows = grounds.Sheet(str(path)).best("high-metal-content")
        assert [row["material"] for row in rows] == ["Iridium", "Osmium", "Copper"]

    def test_codes_give_the_valuable_material_the_single_letter(self, tmp_path):
        import json
        path = tmp_path / "mining_sheet.json"
        path.write_text(json.dumps({"grounds": {"rock 80%+ [none]": [
            {"material": "Titanium", "pct": 52.6, "median": 0, "best": 0},
            {"material": "Thorium", "pct": 47.6, "median": 0, "best": 0},
            {"material": "Thortveitite", "pct": 12.2, "median": 160947, "best": 1},
            {"material": "Tritium", "pct": 5.0, "median": 0, "best": 0},
        ]}}), encoding="utf-8")
        codes = grounds.Sheet(str(path)).codes()
        assert codes["thortveitite"] == "T"
        assert len(set(codes.values())) == len(codes)
        # Not the whole dict: UNSHEETED materials are priced whatever the sheet
        # holds, so every reading carries them too.
        assert {name: codes[name] for name in ("thortveitite", "thorium", "titanium", "tritium")}             == {"thortveitite": "T", "thorium": "TH", "titanium": "TI", "tritium": "TR"}

    def test_worth_drops_what_pays_under_the_line(self, sheet):
        """Olivine sits exactly on it and stays: the line is "worth the trip",
        not "worth more than the trip"."""
        assert sheet.worth(["Monazite", "Olivine", "Magnesite", "Tiny"])             == ("Monazite", "Olivine")

    def test_worth_keeps_the_order_it_was_given(self, sheet):
        assert sheet.worth(["Olivine", "Monazite"]) == ("Olivine", "Monazite")

    def test_worth_keeps_what_nothing_prices(self, sheet):
        """Neither a row nor an UNSHEETED stand-in. Hiding it would be a claim
        about a price nobody has measured."""
        assert sheet.worth(["Nothing"]) == ("Nothing",)

    def test_an_unsheeted_price_stands_in_and_is_judged(self, sheet):
        """Bromellite has no rows on any ground, so its market average is what
        values() carries - and 33k is under the line like any other 33k."""
        assert sheet.values()["bromellite"] == grounds.UNSHEETED["bromellite"]
        assert sheet.worth(["Bromellite"]) == ()

    def test_a_measured_row_beats_the_stand_in(self, tmp_path, monkeypatch):
        import json
        monkeypatch.setitem(grounds.UNSHEETED, "olivine", 1)
        path = tmp_path / "mining_sheet.json"
        path.write_text(json.dumps({"grounds": {"rock 80%+ [none]": [
            {"material": "Olivine", "pct": 50.0, "median": 60000, "best": 90000},
        ]}}), encoding="utf-8")
        assert grounds.Sheet(str(path)).values()["olivine"] == 60000

    def test_worth_takes_its_own_line(self, sheet):
        assert sheet.worth(["Magnesite"], minimum=40000) == ("Magnesite",)

    def test_worth_without_a_sheet_drops_nothing(self, empty_sheet):
        """No file, no prices, no filtering - not even the UNSHEETED stand-in.
        One price in an empty table would hide bromellite and offer copper,
        which is the filter backwards."""
        assert empty_sheet.worth(["Copper", "Water", "Bromellite"])             == ("Copper", "Water", "Bromellite")

    def test_every_shipped_material_has_its_own_code(self):
        codes = grounds.Sheet().codes()
        assert codes and len(set(codes.values())) == len(codes)
        assert all(len(code) <= 3 for code in codes.values())

    def test_a_sheet_from_before_4_1_3_reads_under_the_current_names(self, tmp_path):
        """A hand-copied older sheet can still carry the old names. Its rows
        must not vanish behind the rename."""
        import json
        path = tmp_path / "mining_sheet.json"
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

    def test_split_magma_serves_a_body_cached_as_magma(self, tmp_path):
        """A body classified before 4.1.4 says [magma]. Its rate is the two
        kinds joined from their hits: 14 of 35 and 12 of 23 is 26 of 58."""
        import json
        path = tmp_path / "mining_sheet.json"
        path.write_text(json.dumps({
            "locations": {"rock 80%+ [metallic magma]": 35, "rock 80%+ [rocky magma]": 23},
            "grounds": {
                "rock 80%+ [metallic magma]": [{"material": "Monazite", "pct": 40.0,
                                                "median": 1, "best": 1}],
                "rock 80%+ [rocky magma]": [{"material": "Monazite", "pct": 52.2,
                                             "median": 1, "best": 1}],
            },
        }), encoding="utf-8")
        sheet = grounds.Sheet(str(path))
        assert sheet.rate("rock 80%+ [rocky magma]", "monazite") == 52.2
        assert sheet.rate("volcanic magma", "monazite") == 44.8
        assert sheet.sample("rock 80%+ [magma]") == 58

    def test_a_combined_magma_sheet_answers_for_both_kinds(self, sheet):
        """An older sheet knows one [magma]; a body split by this version still
        gets that rate rather than nothing."""
        assert sheet.rate("rock 80%+ [metallic magma]", "monazite") == 45.6
        assert sheet.sample("rock 80%+ [rocky magma]") == 57

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
        path = tmp_path / "mining_sheet.json"
        path.write_text("{not json", encoding="utf-8")
        broken = grounds.Sheet(str(path))
        assert not broken.loaded
        assert broken.error

    def test_the_shipped_table_parses(self):
        """The file that actually ships, against the real classifier - a sheet
        keyed by a ground nothing classifies into would be silently empty."""
        shipped = grounds.Sheet()
        if not shipped.loaded:
            pytest.skip("mining_sheet.json not exported into this checkout")
        unknown = set(shipped.grounds) - set(grounds.GROUND_ORDER)
        assert not unknown, f"sheet has grounds the classifier never returns: {unknown}"
