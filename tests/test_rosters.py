from pathlib import Path
import pytest
from kingshot_sim.io_pkg.rosters import (
    AccountRoster,
    BenchmarkRoster,
    roster_to_dict,
    roster_from_dict,
    roster_to_json,
    roster_from_json,
    save_roster_file,
    load_roster_file,
)
from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild


def test_account_roster_v2_roundtrip():
    r = AccountRoster(
        name="Main Account",
        generation=8,
        owned_heroes={"Inf": ["Jabel"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={"Jabel": HeroBuild(level="MAX", widget_level=8, skill_levels=(5, 5, 5))},
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100, enhance=5, forge_mastery=2)}},
        bonuses=BonusVector(squad_atk_pct=120.0, inf_atk_pct=80.0),
        buffs=Buffs(city_let=10, grizzly_level=5),
    )
    payload = roster_to_json(r)
    loaded = roster_from_json(payload)
    assert loaded.name == "Main Account"
    assert loaded.generation == 8
    assert loaded.class_gear["Inf"]["head"].level == 100
    assert loaded.class_gear["Inf"]["head"].quality == "red"
    assert loaded.class_gear["Inf"]["head"].enhance == 5
    assert loaded.class_gear["Inf"]["head"].forge_mastery == 2
    assert loaded.bonuses.squad_atk_pct == 120.0
    assert loaded.bonuses.inf_atk_pct == 80.0
    assert loaded.buffs.city_let == 10
    assert loaded.buffs.grizzly_level == 5

    # Check serialization format
    d = roster_to_dict(r)
    assert d["format"] == "ksbattlehelper-roster"
    assert d["version"] == 2


def test_account_roster_v1_backward_compatibility():
    v1_raw = '''{
        "version": 1,
        "format": "ksbattlehelper-roster",
        "name": "Legacy Roster",
        "generation": 7,
        "owned_heroes": {"Cav": ["Margot"]},
        "builds": {"Margot": {"star": 4, "sub_tier": 2, "level": "4_2", "widget_level": 4}}
    }'''
    loaded = roster_from_json(v1_raw)
    assert loaded.name == "Legacy Roster"
    assert loaded.generation == 7
    assert loaded.class_gear == {}
    assert isinstance(loaded.bonuses, BonusVector)
    assert isinstance(loaded.buffs, Buffs)
    assert loaded.bonuses.squad_atk_pct == 0.0
    assert loaded.buffs.city_let == 0
    assert BenchmarkRoster is AccountRoster


def test_account_roster_defaults():
    r = AccountRoster(name="Default Account")
    assert r.name == "Default Account"
    assert r.generation == 8
    assert r.owned_heroes == {}
    assert r.builds == {}
    assert r.class_gear == {}
    assert isinstance(r.bonuses, BonusVector)
    assert isinstance(r.buffs, Buffs)


def test_account_roster_file_io(tmp_path: Path):
    r = AccountRoster(
        name="File Account",
        generation=8,
        owned_heroes={"Inf": ["Helga"]},
        builds={"Helga": HeroBuild(level="5_0", widget_level=0)},
        class_gear={
            "Cav": {
                "chest": HeroGearPiece(slot="chest", quality="mythic", level=80, enhance=3, forge_mastery=1),
            }
        },
        bonuses=BonusVector(cav_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )
    target_path = tmp_path / "sub" / "roster.json"
    save_roster_file(r, target_path)
    assert target_path.exists()

    loaded = load_roster_file(target_path)
    assert loaded.name == "File Account"
    assert loaded.generation == 8
    assert loaded.builds["Helga"].level == "MAX"
    assert loaded.class_gear["Cav"]["chest"].quality == "mythic"
    assert loaded.bonuses.cav_atk_pct == 50.0
    assert loaded.buffs.city_atk == 10

    # Also test passing str path to load_roster_file
    loaded_str = load_roster_file(str(target_path))
    assert loaded_str.name == "File Account"


def test_account_roster_hero_filtering_and_deduplication():
    raw = {
        "name": "Dedup and Class Test",
        "generation": 6,
        "owned_heroes": {
            "Inf": ["Helga", "Helga", "Jabel", "Amadeus", "Helga", "FakeInf"],
            "Cav": ["Jabel", "Margot", "Jabel"],
            "Arc": ["Amadeus", "Yang", "Yang"],
        },
        "builds": {
            "Amadeus": {"level": "5_0", "widget_level": 5},
            "FakeHero": {"level": "MAX"},
        },
        "class_gear": {
            "Inf": {
                "head": {"slot": "head", "quality": "mythic", "level": 50, "enhance": 0, "forge_mastery": 0},
                "invalid_slot": {"slot": "invalid_slot", "quality": "red", "level": 10},
            }
        },
    }
    loaded = roster_from_dict(raw)
    assert loaded.owned_heroes["Inf"] == ["Helga", "Amadeus"]
    assert loaded.owned_heroes["Cav"] == ["Jabel", "Margot"]
    assert loaded.owned_heroes["Arc"] == ["Yang"]
    assert "Amadeus" in loaded.builds
    assert "FakeHero" not in loaded.builds
    assert loaded.builds["Amadeus"].level == "MAX"
    assert "head" in loaded.class_gear["Inf"]
    assert "invalid_slot" not in loaded.class_gear["Inf"]


def test_account_roster_five_star_normalization():
    raw = {
        "name": "Five Star Norm Test",
        "generation": 6,
        "builds": {
            "Amadeus": {"level": "5_0", "widget_level": 5},
            "Helga": {"level": "5_3", "widget_level": 2},
            "Jabel": {"star": 5, "sub_tier": 0, "widget_level": 4},
            "Margot": {"star": 5, "sub_tier": 5, "widget_level": 4},
        },
    }
    loaded = roster_from_dict(raw)
    assert loaded.builds["Amadeus"].level == "MAX"
    assert loaded.builds["Helga"].level == "MAX"
    assert loaded.builds["Jabel"].level == "MAX"
    assert loaded.builds["Margot"].level == "MAX"


def test_account_roster_resilience_to_corrupt_data():
    raw_corrupt = {
        "name": "Bad",
        "generation": 999,
        "builds": {"NonExistentHero": {"level": "invalid"}},
        "bonuses": {"invalid_bonus": 123},
        "buffs": {"unknown_buff": True},
    }
    loaded = roster_from_dict(raw_corrupt)
    assert loaded.name == "Bad"
    assert 1 <= loaded.generation <= 8
    assert "NonExistentHero" not in loaded.builds
    assert isinstance(loaded.bonuses, BonusVector)
    assert isinstance(loaded.buffs, Buffs)


def test_account_roster_defaults_for_missing_build_fields():
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


def test_account_roster_clamping_ranges():
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


def test_account_roster_with_skill_levels():
    roster = AccountRoster(
        name="Skills Roster",
        generation=4,
        owned_heroes={"Cav": ["Margot"]},
        builds={"Margot": HeroBuild(level="4_5", widget_level=3, skill_levels=(3, 4, 5))},
    )
    d = roster_to_dict(roster)
    assert d["builds"]["Margot"]["skill_levels"] == [3, 4, 5]
    loaded = roster_from_dict(d)
    assert loaded.builds["Margot"].skill_levels == (3, 4, 5)


def test_account_roster_partial_bonuses_and_buffs():
    raw = {
        "name": "Partial Stats",
        "generation": 8,
        "bonuses": {
            "squad_atk_pct": 55.5,
            "arc_hp_pct": 22.0,
        },
        "buffs": {
            "city_atk": 20,
            "appoint_marshal": True,
        },
    }
    loaded = roster_from_dict(raw)
    assert loaded.bonuses.squad_atk_pct == 55.5
    assert loaded.bonuses.arc_hp_pct == 22.0
    assert loaded.bonuses.inf_atk_pct == 0.0
    assert loaded.buffs.city_atk == 20
    assert loaded.buffs.appoint_marshal is True
    assert loaded.buffs.city_def == 0
