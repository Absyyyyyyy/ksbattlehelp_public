from __future__ import annotations
import pytest

from kingshot_sim.optimizer.search_space import (
    SearchSpace, TroopPool, LeaderSpec,
)
from kingshot_sim.config.fighter import HeroGearPiece


def _full_red_set():
    return {
        slot: HeroGearPiece(slot=slot, quality="red", level=200, forge_mastery=15)
        for slot in ["head", "chest", "gloves", "boots"]
    }


def test_class_gear_default_is_empty():
    sp = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Yang"],
        troop_pool=TroopPool(march_cap=100_000),
    )
    assert sp.class_gear == {}


def test_class_gear_shared_across_heroes_of_same_class():
    cav_gear = _full_red_set()
    sp = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra", "Margot", "Sophia", "Thrud"],
        available_mythic_arc=["Yang"],
        troop_pool=TroopPool(march_cap=100_000),
        class_gear={"Cav": cav_gear},
    )
    expected = (200.0, 200.0, 500.0, 500.0)
    for hero in ["Petra", "Margot", "Sophia", "Thrud"]:
        lh = sp.build_leader_hero(hero)
        assert lh.resolve_gear_contribution() == expected, (
            f"{hero} should inherit the Cav-class gear"
        )


def test_class_gear_does_not_leak_across_classes():
    sp = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Yang"],
        troop_pool=TroopPool(march_cap=100_000),
        class_gear={"Cav": _full_red_set()},
    )
    assert sp.build_leader_hero("Eric").resolve_gear_contribution() == (0.0, 0.0, 0.0, 0.0)
    assert sp.build_leader_hero("Yang").resolve_gear_contribution() == (0.0, 0.0, 0.0, 0.0)
    petra_contrib = sp.build_leader_hero("Petra").resolve_gear_contribution()
    assert petra_contrib == (200.0, 200.0, 500.0, 500.0)


def test_per_hero_widget_level_still_independent():
    sp = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra", "Margot"],
        available_mythic_arc=["Yang"],
        troop_pool=TroopPool(march_cap=100_000),
        leader_specs={
            "Petra":  LeaderSpec(widget_level=10),
            "Margot": LeaderSpec(widget_level=5),
        },
        class_gear={"Cav": _full_red_set()},
    )
    assert sp.build_leader_hero("Petra").widget_level == 10
    assert sp.build_leader_hero("Margot").widget_level == 5
    assert (sp.build_leader_hero("Petra").resolve_gear_contribution()
            == sp.build_leader_hero("Margot").resolve_gear_contribution())


def test_class_gear_precedence_over_per_hero_manual_fields():
    sp = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Yang"],
        troop_pool=TroopPool(march_cap=100_000),
        leader_specs={
            "Petra": LeaderSpec(
                gear_atk_pct=999, gear_def_pct=999,
                gear_let_pct=999, gear_hp_pct=999,
            ),
        },
        class_gear={"Cav": _full_red_set()},
    )
    contrib = sp.build_leader_hero("Petra").resolve_gear_contribution()
    assert contrib == (200.0, 200.0, 500.0, 500.0)
