from pathlib import Path
import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import (
    BenchmarkRoster,
    roster_to_dict,
    roster_from_dict,
    roster_to_json,
    roster_from_json,
    save_roster_file,
    load_roster_file,
)


def test_benchmark_roster_roundtrip_dict():
    roster = BenchmarkRoster(
        name="Test Roster",
        generation=7,
        owned_heroes={"Inf": ["Jabel", "Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Jabel": HeroBuild(level="MAX", widget_level=8),
            "Margot": HeroBuild(level="4_2", widget_level=5),
        },
    )
    d = roster_to_dict(roster)
    assert d["format"] == "ksbattlehelper-roster"
    assert d["generation"] == 7
    loaded = roster_from_dict(d)
    assert loaded.name == "Test Roster"
    assert loaded.generation == 7
    assert loaded.owned_heroes == roster.owned_heroes
    assert loaded.builds["Jabel"].level == "MAX"
    assert loaded.builds["Jabel"].widget_level == 8
    assert loaded.builds["Margot"].level == "4_2"
    assert loaded.builds["Margot"].widget_level == 5


def test_benchmark_roster_roundtrip_json(tmp_path: Path):
    roster = BenchmarkRoster(
        name="JSON Roster",
        generation=8,
        owned_heroes={"Inf": ["Helga"]},
        builds={"Helga": HeroBuild(level="5_0", widget_level=0)},
    )
    raw = roster_to_json(roster)
    loaded = roster_from_json(raw)
    assert loaded.name == "JSON Roster"
    assert loaded.builds["Helga"].level == "5_0"

    p = tmp_path / "test.json"
    save_roster_file(roster, p)
    assert p.exists()
    from_file = load_roster_file(p)
    assert from_file.name == "JSON Roster"


def test_benchmark_roster_resilience_to_corrupt_data():
    raw_corrupt = {
        "name": "Bad",
        "generation": 999,
        "builds": {"NonExistentHero": {"level": "invalid"}},
    }
    loaded = roster_from_dict(raw_corrupt)
    assert loaded.name == "Bad"
    assert 1 <= loaded.generation <= 8
    assert "NonExistentHero" not in loaded.builds


def test_benchmark_roster_defaults_for_missing_build_fields():
    raw = {
        "name": "Defaults Test",
        "generation": 5,
        "builds": {
            "Amadeus": {},  # Mythic hero with missing fields
            "Diana": {},    # Epic hero with missing fields
            "Helga": {"star": 4, "sub_tier": 2},  # Missing level and widget_level
        },
    }
    loaded = roster_from_dict(raw)
    # Mythic default: star 5, MAX, widget 4
    assert loaded.builds["Amadeus"].level == "MAX"
    assert loaded.builds["Amadeus"].widget_level == 4

    # Epic default: star 5, MAX, widget 0
    assert loaded.builds["Diana"].level == "MAX"
    assert loaded.builds["Diana"].widget_level == 0

    # Helga with star=4, sub_tier=2 -> level="4_2", widget default 4 for mythic
    assert loaded.builds["Helga"].level == "4_2"
    assert loaded.builds["Helga"].widget_level == 4


def test_benchmark_roster_clamping_ranges():
    raw = {
        "name": "Clamping Test",
        "generation": -10,  # Below 1 -> clamped to 1
        "builds": {
            "Amadeus": {
                "star": 99,
                "sub_tier": -5,
                "widget_level": 999,
            },
            "Diana": {
                "star": -3,
                "sub_tier": 10,
                "widget_level": -5,
            },
        },
    }
    loaded = roster_from_dict(raw)
    assert loaded.generation == 1

    # Amadeus: star clamped to 5 -> level MAX, widget clamped to 10
    assert loaded.builds["Amadeus"].level == "MAX"
    assert loaded.builds["Amadeus"].widget_level == 10

    # Diana: star clamped to 0, sub clamped to 5 -> level "0_5", widget clamped to 0
    assert loaded.builds["Diana"].level == "0_5"
    assert loaded.builds["Diana"].widget_level == 0


def test_benchmark_roster_filters_unknown_heroes():
    raw = {
        "name": "Filtered",
        "generation": 3,
        "owned_heroes": {
            "Inf": ["Amadeus", "FakeHeroOne"],
            "Cav": ["FakeHeroTwo"],
        },
        "builds": {
            "Amadeus": {"widget_level": 5},
            "FakeHeroThree": {"widget_level": 10},
        },
    }
    loaded = roster_from_dict(raw)
    assert loaded.owned_heroes["Inf"] == ["Amadeus"]
    assert loaded.owned_heroes["Cav"] == []
    assert "Amadeus" in loaded.builds
    assert "FakeHeroThree" not in loaded.builds


def test_benchmark_roster_with_skill_levels():
    roster = BenchmarkRoster(
        name="Skills Roster",
        generation=4,
        owned_heroes={"Cav": ["Margot"]},
        builds={"Margot": HeroBuild(level="4_5", widget_level=3, skill_levels=(3, 4, 5))},
    )
    d = roster_to_dict(roster)
    assert d["builds"]["Margot"]["skill_levels"] == [3, 4, 5]
    loaded = roster_from_dict(d)
    assert loaded.builds["Margot"].skill_levels == (3, 4, 5)


def test_benchmark_roster_file_io_string_path_and_nested_dir(tmp_path: Path):
    roster = BenchmarkRoster(
        name="Nested File Roster",
        generation=2,
    )
    nested_path = tmp_path / "subdir" / "nested" / "roster.json"
    save_roster_file(roster, str(nested_path))
    assert nested_path.exists()
    loaded = load_roster_file(str(nested_path))
    assert loaded.name == "Nested File Roster"
    assert loaded.generation == 2
