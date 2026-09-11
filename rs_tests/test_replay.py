"""Replaying recent journals, and picking the system worth standing in."""

import json
import os
import time

import pytest

from rs_core import replay


def write_journal(folder, name, events, age_days=0):
    path = folder / name
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def scan(name, planet_class, volcanism="", distance=100.0):
    return {"event": "Scan", "BodyName": name, "PlanetClass": planet_class,
            "Landable": True, "Volcanism": volcanism,
            "DistanceFromArrivalLS": distance}


class TestJournalFiles:
    def test_only_recent_files(self, tmp_path):
        write_journal(tmp_path, "Journal.new.log", [{"event": "Music"}], age_days=1)
        write_journal(tmp_path, "Journal.old.log", [{"event": "Music"}], age_days=9)
        found = replay.journal_files(str(tmp_path), days=3)
        assert [os.path.basename(p) for p in found] == ["Journal.new.log"]

    def test_oldest_first(self, tmp_path):
        """Modification time, not filename: a session running past midnight
        keeps writing to yesterday's file."""
        write_journal(tmp_path, "Journal.b.log", [{"event": "Music"}], age_days=0)
        write_journal(tmp_path, "Journal.a.log", [{"event": "Music"}], age_days=2)
        found = replay.journal_files(str(tmp_path), days=3)
        assert [os.path.basename(p) for p in found] == ["Journal.a.log", "Journal.b.log"]

    def test_other_files_are_left_alone(self, tmp_path):
        write_journal(tmp_path, "Status.json", [{"event": "Music"}])
        write_journal(tmp_path, "Journal.a.log", [{"event": "Music"}])
        found = replay.journal_files(str(tmp_path), days=3)
        assert [os.path.basename(p) for p in found] == ["Journal.a.log"]

    def test_a_missing_folder_is_empty_not_an_error(self, tmp_path):
        assert replay.journal_files(str(tmp_path / "nope")) == []


class TestReplay:
    def test_collects_bodies_per_system(self, tmp_path):
        write_journal(tmp_path, "Journal.a.log", [
            {"event": "FSDJump", "StarSystem": "Andel"},
            scan("Andel 1 a", "Rocky body", "major metallic magma"),
            {"event": "FSDJump", "StarSystem": "Loha"},
            scan("Loha 3", "Icy body"),
        ])
        systems = replay.replay(replay.journal_files(str(tmp_path)))
        assert sorted(systems) == ["Andel", "Loha"]
        assert systems["Andel"][0]["ground"] == "volcanic magma"

    def test_location_counts_come_through(self, tmp_path):
        write_journal(tmp_path, "Journal.a.log", [
            {"event": "FSDJump", "StarSystem": "Andel"},
            scan("Andel 1 a", "Rocky body"),
            {"event": "SAASignalsFound", "BodyName": "Andel 1 a",
             "Signals": [{"Type": "$PlanetaryMiningLocation_Name;", "Count": 17}]},
        ])
        systems = replay.replay(replay.journal_files(str(tmp_path)))
        assert systems["Andel"][0]["locations"] == 17

    def test_a_second_visit_does_not_lose_the_first(self, tmp_path):
        """Leaving hands the list over before it is cleared, so a system
        visited twice ends up with everything either visit found."""
        write_journal(tmp_path, "Journal.a.log", [
            {"event": "FSDJump", "StarSystem": "Andel"},
            scan("Andel 1 a", "Rocky body"),
            {"event": "FSDJump", "StarSystem": "Loha"},
            scan("Loha 3", "Icy body"),
        ], age_days=2)
        write_journal(tmp_path, "Journal.b.log", [
            {"event": "FSDJump", "StarSystem": "Andel"},
            scan("Andel 4 c", "Icy body"),
        ], age_days=0)
        systems = replay.replay(replay.journal_files(str(tmp_path)))
        assert len(systems["Andel"]) >= 1
        assert "Loha" in systems

    def test_broken_lines_are_skipped(self, tmp_path):
        path = tmp_path / "Journal.a.log"
        path.write_text('{"event": "FSDJump", "StarSystem": "Andel"}\n'
                        'not json at all\n'
                        + json.dumps(scan("Andel 1 a", "Rocky body")),
                        encoding="utf-8")
        systems = replay.replay([str(path)])
        assert systems["Andel"][0]["name"] == "Andel 1 a"

    def test_systems_with_nothing_landable_are_dropped(self, tmp_path):
        write_journal(tmp_path, "Journal.a.log", [
            {"event": "FSDJump", "StarSystem": "Empty"},
            {"event": "Scan", "BodyName": "Empty A", "StarType": "M"},
        ])
        assert replay.replay(replay.journal_files(str(tmp_path))) == {}


class TestScoring:
    def test_every_body_is_worth_its_best_rate(self, sheet):
        seen = [{"ground": "volcanic magma"}, {"ground": "rocky"}]
        assert replay.score(seen, sheet) == pytest.approx(56.1 + 43.3)

    def test_ground_the_sheet_never_measured_is_worth_nothing(self, sheet):
        """Worth nothing rather than guessed at."""
        assert replay.score([{"ground": "icy"}], sheet) == 0.0

    def test_more_of_the_same_good_ground_scores_higher(self, sheet):
        """The question is not "is there something here" but "is there enough
        here to be worth the trip"."""
        one = replay.score([{"ground": "volcanic magma"}], sheet)
        five = replay.score([{"ground": "volcanic magma"}] * 5, sheet)
        assert five > one

    def test_ranking_puts_the_best_first(self, sheet):
        systems = {
            "Thin":  [{"ground": "rocky", "locations": None}],
            "Rich":  [{"ground": "volcanic magma", "locations": None}] * 3,
        }
        assert [name for name, _, _ in replay.rank(systems, sheet)] == ["Rich", "Thin"]

    def test_counted_locations_break_a_tie(self, sheet):
        """Equal ground, so the separator is how much someone has already
        probed - a probed body is one you can fly straight to."""
        systems = {
            "Unprobed": [{"ground": "rocky", "locations": None}],
            "Probed":   [{"ground": "rocky", "locations": 20}],
        }
        assert [name for name, _, _ in replay.rank(systems, sheet)] == ["Probed", "Unprobed"]


class TestBest:
    def test_picks_the_richest_system(self, tmp_path, sheet):
        write_journal(tmp_path, "Journal.a.log", [
            {"event": "FSDJump", "StarSystem": "Thin"},
            scan("Thin 1", "Rocky body"),
            {"event": "FSDJump", "StarSystem": "Rich"},
            scan("Rich 1", "Rocky body", "major metallic magma"),
            scan("Rich 2", "Rocky body", "minor rocky magma", distance=200.0),
        ])
        system, seen = replay.best(str(tmp_path), days=3, sheet=sheet)
        assert system == "Rich"
        assert len(seen) == 2

    def test_no_journals_is_none_not_a_crash(self, tmp_path, sheet):
        assert replay.best(str(tmp_path), days=3, sheet=sheet) is None
