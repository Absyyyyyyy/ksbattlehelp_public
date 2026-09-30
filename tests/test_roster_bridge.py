import pytest
import streamlit as st

from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.config.fighter import (
    HeroGearPiece, BonusVector, TroopRoster, TroopGroup,
    Fighter, LeaderHero, JoinerHero,
)
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool, LeaderSpec
from kingshot_sim.io_pkg.roster_bridge import (
    account_roster_to_fighter,
    fighter_to_roster,
    roster_to_search_space,
    update_roster_from_search_space,
    roster_to_fighter,
    apply_roster_to_benchmark,
    extract_roster_from_benchmark,
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


def test_benchmark_synchronization(monkeypatch):
    mock_ss: dict = {}
    monkeypatch.setattr(st, "session_state", mock_ss)

    r = AccountRoster(
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

    apply_roster_to_benchmark(r)
    assert mock_ss["_bm_master_gen"] == 7
    assert mock_ss["_bm_gen"] == 7
    assert "Amadeus" in mock_ss["_bm_own_Inf"]
    assert mock_ss["_bm_star_Amadeus"] == 5
    assert mock_ss["_bm_wl_Amadeus"] == 9
    assert mock_ss["_bm_star_Margot"] == 4
    assert mock_ss["_bm_tier_Margot"] == 2
    assert mock_ss["_bm_wl_Margot"] == 5

    # Simulate user tweaking values in benchmark tab
    mock_ss["_bm_wl_Amadeus"] = 10
    mock_ss["_bm_star_Margot"] = 5
    mock_ss["_bm_tier_Margot"] = 0
    mock_ss["_bm_master_gen"] = 8

    extracted = extract_roster_from_benchmark(r)
    assert extracted.name == "Sync Profile"
    assert extracted.generation == 8
    assert extracted.builds["Amadeus"].widget_level == 10
    assert extracted.builds["Amadeus"].skill_levels == (5, 4, 3)
    assert extracted.builds["Margot"].level == "MAX"
    assert extracted.class_gear["Inf"]["head"].level == 60
    assert extracted.bonuses.squad_atk_pct == 100.0


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


def test_extract_roster_from_benchmark_without_session_state(monkeypatch):
    class NoSessionState:
        @property
        def session_state(self):
            raise RuntimeError("Streamlit not running")

    monkeypatch.setattr(st, "session_state", NoSessionState())
    r = AccountRoster(
        name="No SS",
        owned_heroes={"Inf": ["Amadeus"]},
        bonuses=BonusVector(inf_atk_pct=25.0),
    )
    extracted = extract_roster_from_benchmark(r)
    assert extracted.name == "No SS"
    assert extracted.owned_heroes == {"Inf": ["Amadeus"]}
    assert extracted.bonuses.inf_atk_pct == 25.0


def test_roundtrip_search_space_consistency():
    r = AccountRoster(
        name="Roundtrip",
        generation=8,
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


def test_account_roster_to_fighter_complete():
    roster = AccountRoster(
        name="CompleteRoster",
        generation=7,
        owned_heroes={
            "Inf": ["Amadeus", "Helga"],
            "Cav": ["Margot", "Diana"],  # Diana is non-combat
            "Arc": ["Yang", "Saul"],
        },
        builds={
            "Amadeus": HeroBuild(level="MAX", widget_level=9, skill_levels=(5, 5, 5)),
            "Margot": HeroBuild(level="4_2", widget_level=5, skill_levels=(4, 4, 3)),
            "Yang": HeroBuild(level="MAX", widget_level=10, skill_levels=(5, 5, 4)),
            "Helga": HeroBuild(level="4_0", widget_level=2),
            "Saul": HeroBuild(level="MAX", widget_level=0),
        },
        class_gear={
            "Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=60)},
            "Cav": {"chest": HeroGearPiece(slot="chest", quality="red", level=100)},
            "Arc": {"boots": HeroGearPiece(slot="boots", quality="red", level=100)},
        },
        bonuses=BonusVector(squad_atk_pct=40.0, inf_def_pct=20.0),
        buffs=Buffs(city_atk=20, appoint_marshal=True),
    )

    fighter = account_roster_to_fighter(roster)

    assert fighter.label == "CompleteRoster"
    # Leaders
    assert fighter.leader_inf.hero_name == "Amadeus"
    assert fighter.leader_inf.level == "MAX"
    assert fighter.leader_inf.widget_level == 9
    assert fighter.leader_inf.skill_levels == (5, 5, 5)
    assert fighter.leader_inf.gear["head"].level == 60

    assert fighter.leader_cav.hero_name == "Margot"
    assert fighter.leader_cav.level == "4_2"
    assert fighter.leader_cav.widget_level == 5
    assert fighter.leader_cav.skill_levels == (4, 4, 3)
    assert fighter.leader_cav.gear["chest"].level == 100

    assert fighter.leader_arc.hero_name == "Yang"
    assert fighter.leader_arc.level == "MAX"
    assert fighter.leader_arc.widget_level == 10
    assert fighter.leader_arc.skill_levels == (5, 5, 4)
    assert fighter.leader_arc.gear["boots"].level == 100

    # Joiners: should pick up to 4 eligible combat joiners (excluding leaders and Diana)
    joiner_names = [j.hero_name for j in fighter.joiners]
    assert "Diana" not in joiner_names
    assert "Amadeus" not in joiner_names
    assert "Margot" not in joiner_names
    assert "Yang" not in joiner_names
    assert "Helga" in joiner_names
    assert "Saul" in joiner_names
    assert len(fighter.joiners) <= 4

    # Check joiner build levels
    helga_joiner = next(j for j in fighter.joiners if j.hero_name == "Helga")
    assert helga_joiner.level == "4_0"

    # Bonuses & Buffs
    assert fighter.bonuses.squad_atk_pct == 40.0
    assert fighter.bonuses.inf_def_pct == 20.0
    assert fighter.buffs.city_atk == 20
    assert fighter.buffs.appoint_marshal is True

    # Troops default
    assert fighter.troops == TroopRoster()


def test_account_roster_to_fighter_preserves_troops():
    custom_troops = TroopRoster(
        infantry=(TroopGroup(tier="T10", count=60_000),),
        cavalry=(TroopGroup(tier="T10", count=40_000),),
        archer=(TroopGroup(tier="T10", count=50_000),),
    )
    existing_fighter = Fighter(
        label="Existing",
        leader_inf=LeaderHero(hero_name="Helga", level="MAX"),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX"),
        leader_arc=LeaderHero(hero_name="Yang", level="MAX"),
        joiners=(JoinerHero(hero_name="Saul"),),
        bonuses=BonusVector(),
        troops=custom_troops,
    )

    roster = AccountRoster(
        name="NewProfile",
        owned_heroes={
            "Inf": ["Amadeus", "Helga"],
            "Cav": ["Margot"],
            "Arc": ["Yang"],
        },
        builds={
            "Helga": HeroBuild(level="MAX", widget_level=8),
        },
    )

    # Calling with current_fighter should preserve troops and retain current_fighter's leader "Helga"
    fighter = account_roster_to_fighter(roster, current_fighter=existing_fighter)
    assert fighter.troops == custom_troops
    assert fighter.troops.total_count() == 150_000
    assert fighter.leader_inf.hero_name == "Helga"
    assert fighter.leader_inf.widget_level == 8
    # Joiner from current_fighter preserved
    assert [j.hero_name for j in fighter.joiners] == ["Saul"]


def test_fighter_to_roster_roundtrip():
    gear_inf = {"head": HeroGearPiece(slot="head", quality="mythic", level=70)}
    gear_cav = {"chest": HeroGearPiece(slot="chest", quality="red", level=100)}
    gear_arc = {"boots": HeroGearPiece(slot="boots", quality="red", level=100)}

    fighter = Fighter(
        label="OriginalFighter",
        leader_inf=LeaderHero(
            hero_name="Charles",  # Gen 7
            level="MAX",
            widget_level=10,
            skill_levels=(5, 5, 5),
            gear=gear_inf,
        ),
        leader_cav=LeaderHero(
            hero_name="Petra",  # Gen 3
            level="4_3",
            widget_level=6,
            skill_levels=(4, 3, 2),
            gear=gear_cav,
        ),
        leader_arc=LeaderHero(
            hero_name="Jaeger",  # Gen 3
            level="MAX",
            widget_level=8,
            skill_levels=(5, 4, 3),
            gear=gear_arc,
        ),
        joiners=(
            JoinerHero(hero_name="Saul", level="MAX"),
            JoinerHero(hero_name="Chenko", level="4_1"),
        ),
        bonuses=BonusVector(squad_atk_pct=65.0, cav_let_pct=15.0),
        buffs=Buffs(city_atk=20, appoint_marshal=True),
        troops=TroopRoster(infantry=(TroopGroup(tier="T10", count=50_000),)),
    )

    # 1. Test fighter_to_roster with custom name
    roster = fighter_to_roster(fighter, name="ExportedProfile")
    assert roster.name == "ExportedProfile"
    assert roster.generation == 7  # Derived from Charles (Gen 7)
    assert "Charles" in roster.owned_heroes["Inf"]
    assert "Petra" in roster.owned_heroes["Cav"]
    assert "Jaeger" in roster.owned_heroes["Arc"]
    assert "Saul" in roster.owned_heroes["Arc"]
    assert "Chenko" in roster.owned_heroes["Cav"]

    assert roster.builds["Charles"].widget_level == 10
    assert roster.builds["Charles"].skill_levels == (5, 5, 5)
    assert roster.builds["Petra"].level == "4_3"
    assert roster.builds["Petra"].widget_level == 6
    assert roster.builds["Saul"].level == "MAX"
    assert roster.builds["Chenko"].level == "4_1"
    assert roster.builds["Chenko"].widget_level == 0  # Chenko is epic

    assert roster.class_gear["Inf"]["head"].level == 70
    assert roster.class_gear["Cav"]["chest"].level == 100
    assert roster.class_gear["Arc"]["boots"].level == 100
    assert roster.bonuses.squad_atk_pct == 65.0
    assert roster.bonuses.cav_let_pct == 15.0
    assert roster.buffs.city_atk == 20
    assert roster.buffs.appoint_marshal is True

    # 2. Test fighter_to_roster default name fallback to fighter.label
    roster_no_name = fighter_to_roster(fighter)
    assert roster_no_name.name == "OriginalFighter"

    # 3. Roundtrip back to fighter preserving current_fighter troops
    roundtrip_fighter = account_roster_to_fighter(roster, current_fighter=fighter)
    assert roundtrip_fighter.label == "ExportedProfile"
    assert roundtrip_fighter.leader_inf.hero_name == "Charles"
    assert roundtrip_fighter.leader_inf.widget_level == 10
    assert roundtrip_fighter.leader_inf.gear["head"].level == 70
    assert roundtrip_fighter.leader_cav.hero_name == "Petra"
    assert roundtrip_fighter.leader_cav.widget_level == 6
    assert roundtrip_fighter.leader_arc.hero_name == "Jaeger"
    assert roundtrip_fighter.leader_arc.widget_level == 8
    assert roundtrip_fighter.troops == fighter.troops
    assert roundtrip_fighter.bonuses == fighter.bonuses
    assert roundtrip_fighter.buffs == fighter.buffs

