import pytest

from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.config.fighter import (
    HeroGearPiece, BonusVector, TroopRoster, TroopGroup,
)
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool, LeaderSpec
from kingshot_sim.io_pkg.roster_bridge import (
    roster_to_search_space,
    update_roster_from_search_space,
    roster_to_fighter,
    merge_benchmark_into_roster,
)


def test_roster_to_search_space():
    r = AccountRoster(
        name="Test Roster",
        owned_heroes={"Inf": ["Amadeus", "Helga"], "Cav": ["Margot", "Jabel"], "Arc": ["Yang"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=8),
            "Margot": HeroBuild(level="4_2", widget_level=4),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=50)}},
        bonuses=BonusVector(squad_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )
    sp = roster_to_search_space(r)
    assert "Amadeus" in sp.available_mythic_inf
    assert "Helga" in sp.available_mythic_inf
    assert "Margot" in sp.available_mythic_cav
    assert "Jabel" in sp.available_mythic_cav
    assert "Yang" in sp.available_mythic_arc
    assert sp.leader_specs["Amadeus"].widget_level == 8
    assert sp.class_gear["Inf"]["head"].level == 50
    assert sp.bonuses.squad_atk_pct == 50.0
    assert sp.buffs.city_atk == 10


def test_roster_to_search_space_filters_non_combat_joiners():
    r = AccountRoster(
        name="Filter Test",
        owned_heroes={
            "Inf": ["Amadeus"],
            "Cav": ["Margot", "Diana"],  # Diana is non-combat first skill hero
            "Arc": ["Yang", "Saul"],    # Saul is epic
        },
    )
    sp = roster_to_search_space(r)
    assert "Diana" not in sp.available_joiners
    assert "Amadeus" in sp.available_joiners
    assert "Margot" in sp.available_joiners
    assert "Yang" in sp.available_joiners
    assert "Saul" in sp.available_joiners


def test_roster_to_search_space_preserves_base_settings():
    base = SearchSpace(
        troop_pool=TroopPool(march_cap=450_000, infantry_tier="T11"),
        troop_ratio_step=0.05,
        min_inf_pct=0.40,
        n_joiners=3,
        label_prefix="CustomPrefix",
        leader_specs={"Saul": LeaderSpec(gear_atk_pct=15.0)},
    )
    r = AccountRoster(
        name="Base Preserved",
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={"Saul": HeroBuild(level="MAX", widget_level=0)},
        bonuses=BonusVector(squad_atk_pct=75.0),
    )
    sp = roster_to_search_space(r, base=base)
    assert sp.troop_pool.march_cap == 450_000
    assert sp.troop_pool.infantry_tier == "T11"
    assert sp.troop_ratio_step == 0.05
    assert sp.min_inf_pct == 0.40
    assert sp.n_joiners == 3
    assert sp.label_prefix == "CustomPrefix"
    assert sp.bonuses.squad_atk_pct == 75.0
    # Preserves existing gear bonus from base spec if not overridden
    assert sp.leader_specs["Saul"].gear_atk_pct == 15.0
    assert sp.leader_specs["Saul"].widget_level == 0


def test_update_roster_from_search_space():
    r = AccountRoster(
        name="Original",
        owned_heroes={"Inf": ["Helga"], "Cav": ["Margot", "Diana"], "Arc": ["Yang"]},
        builds={"Helga": HeroBuild(level="MAX", widget_level=5)},
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=40)}},
        bonuses=BonusVector(squad_atk_pct=30.0),
        buffs=Buffs(city_atk=10),
    )
    sp = SearchSpace(
        available_mythic_inf=["Helga", "Amadeus"],
        available_mythic_cav=["Margot"],
        available_mythic_arc=["Yang"],
        available_joiners=["Saul", "Helga", "Margot", "Yang"],
        leader_specs={
            "Helga": LeaderSpec(level="MAX", widget_level=10, skill_levels=(5, 5, 5)),
            "Amadeus": LeaderSpec(level="4_0", widget_level=2),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100)}},
        bonuses=BonusVector(squad_atk_pct=150.0),
        buffs=Buffs(city_atk=20, grizzly_level=5),
    )
    updated = update_roster_from_search_space(r, sp)
    assert updated.name == "Original"
    assert "Amadeus" in updated.owned_heroes["Inf"]
    assert "Margot" in updated.owned_heroes["Cav"]
    assert "Diana" in updated.owned_heroes["Cav"]  # Preserved non-combat hero
    assert "Saul" in updated.owned_heroes["Arc"]  # Saul is Arc epic
    assert updated.builds["Helga"].widget_level == 10
    assert updated.builds["Helga"].skill_levels == (5, 5, 5)
    assert updated.builds["Amadeus"].level == "4_0"
    assert updated.builds["Amadeus"].widget_level == 2
    assert updated.class_gear["Inf"]["head"].level == 100
    assert updated.class_gear["Inf"]["head"].quality == "red"
    assert updated.bonuses.squad_atk_pct == 150.0
    assert updated.buffs.city_atk == 20
    assert updated.buffs.grizzly_level == 5


def test_roster_to_fighter():
    r = AccountRoster(
        name="Opponent",
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=10),
            "Margot": HeroBuild(level="MAX", widget_level=8),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100)}},
    )
    fighter = roster_to_fighter(r, inf_hero="Amadeus", cav_hero="Margot", arc_hero="Yang", label="Enemy")
    assert fighter.label == "Enemy"
    assert fighter.leader_inf.hero_name == "Amadeus"
    assert fighter.leader_inf.widget_level == 10
    assert fighter.leader_inf.gear["head"].level == 100
    assert fighter.leader_cav.hero_name == "Margot"
    assert fighter.leader_cav.widget_level == 8
    assert fighter.leader_arc.hero_name == "Yang"
    # Unspecified leader gets defaults
    assert fighter.leader_arc.widget_level == 10


def test_roster_to_fighter_class_gear_mapping():
    r = AccountRoster(
        name="Gear Test",
        class_gear={
            "Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=50)},
            "Cav": {"chest": HeroGearPiece(slot="chest", quality="red", level=100)},
            "Arc": {"boots": HeroGearPiece(slot="boots", quality="red", level=100)},
        },
        bonuses=BonusVector(squad_def_pct=40.0),
        buffs=Buffs(appoint_marshal=True),
    )
    fighter = roster_to_fighter(
        r,
        inf_hero="Amadeus",
        cav_hero="Margot",
        arc_hero="Yang",
        joiners=("Saul", "Amanitore"),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10", count=50_000),),
            cavalry=(TroopGroup(tier="T10", count=50_000),),
            archer=(TroopGroup(tier="T10", count=50_000),),
        ),
        label="GearFighter",
    )
    assert fighter.leader_inf.gear["head"].level == 50
    assert fighter.leader_cav.gear["chest"].level == 100
    assert fighter.leader_arc.gear["boots"].level == 100
    assert fighter.bonuses.squad_def_pct == 40.0
    assert fighter.buffs.appoint_marshal is True
    assert len(fighter.joiners) == 2
    assert fighter.joiners[0].hero_name == "Saul"
    assert fighter.joiners[1].hero_name == "Amanitore"
    assert fighter.troops.total_count() == 150_000


def test_roster_to_fighter_invalid_classes():
    r = AccountRoster(name="Invalid Trio")
    # Margot is Cav, passed as Inf
    with pytest.raises(ValueError, match="leader_inf"):
        roster_to_fighter(r, inf_hero="Margot", cav_hero="Margot", arc_hero="Yang")


def _profile_with_account_data() -> AccountRoster:
    return AccountRoster(
        name="Sync Profile",
        generation=7,
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=9, skill_levels=(5, 4, 3)),
            "Margot": HeroBuild(level="4_2", widget_level=5),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=60)}},
        bonuses=BonusVector(squad_atk_pct=100.0),
        buffs=Buffs(city_atk=10),
    )


def test_merge_benchmark_into_roster_applies_edits():
    r = _profile_with_account_data()
    merged = merge_benchmark_into_roster(
        r,
        generation=5,
        owned_heroes={"Inf": ["Amadeus", "Helga"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=10),
            "Margot": HeroBuild(level="MAX", widget_level=6),
            "Helga": HeroBuild(level="3_1", widget_level=4),
        },
    )
    assert merged.name == "Sync Profile"
    assert merged.generation == 5
    assert merged.owned_heroes["Inf"] == ["Amadeus", "Helga"]
    assert merged.builds["Amadeus"].widget_level == 10
    assert merged.builds["Margot"].level == "MAX"
    assert merged.builds["Helga"] == HeroBuild(level="3_1", widget_level=4)


def test_merge_benchmark_into_roster_keeps_account_data():
    r = _profile_with_account_data()
    merged = merge_benchmark_into_roster(
        r, generation=7, owned_heroes=r.owned_heroes,
        builds={"Amadeus": HeroBuild(level="MAX", widget_level=10)},
    )
    assert merged.builds["Amadeus"].skill_levels == (5, 4, 3)
    assert merged.builds["Margot"] == r.builds["Margot"]
    assert merged.class_gear["Inf"]["head"].level == 60
    assert merged.bonuses.squad_atk_pct == 100.0
    assert merged.buffs.city_atk == 10


def test_merge_benchmark_into_roster_caps_skills_at_new_star():
    r = _profile_with_account_data()
    merged = merge_benchmark_into_roster(
        r, generation=7, owned_heroes=r.owned_heroes,
        builds={"Amadeus": HeroBuild(level="1_0", widget_level=9)},
    )
    assert merged.builds["Amadeus"].skill_levels == (2, 2, 0)


def test_roster_to_search_space_fallback_to_base_mythics():
    base = SearchSpace(
        available_mythic_inf=["Amadeus"],
        available_mythic_cav=["Margot"],
        available_mythic_arc=["Yang"],
        available_joiners=["Saul"],
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=70)}},
    )
    r = AccountRoster(name="Empty Heroes Roster")
    sp = roster_to_search_space(r, base=base)
    assert sp.available_mythic_inf == ["Amadeus"]
    assert sp.available_mythic_cav == ["Margot"]
    assert sp.available_mythic_arc == ["Yang"]
    assert sp.available_joiners == ["Saul"]
    assert sp.class_gear["Inf"]["head"].level == 70


def test_update_roster_from_search_space_empty_space_preserves_owned():
    r = AccountRoster(
        name="Keep Owned",
        owned_heroes={"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
    )
    sp = SearchSpace()
    updated = update_roster_from_search_space(r, sp)
    assert updated.owned_heroes == {"Inf": ["Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]}


def test_roster_to_fighter_defaults():
    r = AccountRoster(name="Minimal")
    fighter = roster_to_fighter(r, inf_hero="Amadeus", cav_hero="Margot", arc_hero="Yang")
    assert fighter.label == "Opponent"
    assert fighter.troops == TroopRoster()
    assert fighter.joiners == ()
    assert fighter.leader_inf.level == "MAX"
    assert fighter.leader_inf.widget_level == 10


def test_roundtrip_search_space_consistency():
    r = AccountRoster(
        name="Roundtrip",
        generation=7,
        owned_heroes={"Inf": ["Amadeus", "Helga"], "Cav": ["Margot", "Jabel"], "Arc": ["Yang"]},
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=10, skill_levels=(5, 5, 5)),
            "Margot": HeroBuild(level="4_1", widget_level=3, skill_levels=(4, 4, 3)),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=80)}},
        bonuses=BonusVector(squad_atk_pct=60.0, inf_def_pct=30.0),
        buffs=Buffs(city_atk=20, appoint_marshal=True),
    )
    sp = roster_to_search_space(r)
    updated = update_roster_from_search_space(r, sp)
    assert updated.name == r.name
    assert updated.generation == r.generation
    assert updated.builds["Amadeus"].skill_levels == (5, 5, 5)
    assert updated.builds["Margot"].level == "4_1"
    assert updated.builds["Margot"].widget_level == 3
    assert updated.builds["Margot"].skill_levels == (4, 4, 3)
    assert updated.class_gear["Inf"]["head"].level == 80
    assert updated.bonuses.squad_atk_pct == 60.0
    assert updated.bonuses.inf_def_pct == 30.0
    assert updated.buffs.city_atk == 20
    assert updated.buffs.appoint_marshal is True
