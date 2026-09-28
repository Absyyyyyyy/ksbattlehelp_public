import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.domain.enums import SquadType, RNGMode
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.compile import compile_fighter
from kingshot_sim.data.reference import (
    HERO_GENERATION, MAX_GENERATION, heroes_up_to_generation,
)


def test_hero_generation_mapping_complete():
    expected = {
        "Amadeus": 1, "Helga": 1, "Jabel": 1, "Saul": 1,
        "Zoe": 2, "Hilde": 2, "Marlin": 2,
        "Eric": 3, "Petra": 3, "Jaeger": 3,
        "Alcar": 4, "Margot": 4, "Rosa": 4,
        "Long Fei": 5, "Thrud": 5, "Vivian": 5,
        "Triton": 6, "Sophia": 6, "Yang": 6,
        "Charles": 7, "Ava": 7, "Wee & Woo": 7,
    }
    assert HERO_GENERATION == expected


def test_max_generation_constant():
    assert MAX_GENERATION == 7


def test_heroes_up_to_generation_1():
    g1 = heroes_up_to_generation(1)
    assert g1 == frozenset({"Amadeus", "Helga", "Jabel", "Saul"})


def test_heroes_up_to_generation_3():
    g3 = heroes_up_to_generation(3)
    assert len(g3) == 10
    assert "Petra" in g3
    assert "Hilde" in g3
    assert "Saul" in g3
    assert "Alcar" not in g3


def test_heroes_up_to_generation_6_is_all_mythics():
    g6 = heroes_up_to_generation(6)
    assert len(g6) == 19


def test_heroes_up_to_generation_7_includes_gen7():
    g7 = heroes_up_to_generation(7)
    assert len(g7) == 22
    assert "Charles" in g7
    assert "Ava" in g7
    assert "Wee & Woo" in g7


def test_leader_gear_default_zero():
    leader = LeaderHero(hero_name="Eric", level="MAX")
    assert leader.gear_atk_pct == 0.0
    assert leader.gear_def_pct == 0.0
    assert leader.gear_let_pct == 0.0
    assert leader.gear_hp_pct == 0.0


def test_leader_gear_negative_rejected():
    with pytest.raises(ValueError, match="gear_atk_pct"):
        LeaderHero(hero_name="Eric", level="MAX", gear_atk_pct=-5)


def test_leader_gear_applied_to_own_class_only():
    bonuses = BonusVector()
    fighter_no_gear = Fighter(
        label="no gear",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=(),
        bonuses=bonuses,
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    fighter_with_gear = Fighter(
        label="inf gear only",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=0,
                                gear_atk_pct=100.0),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=(),
        bonuses=bonuses,
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    s_no = compile_fighter(fighter_no_gear, side="rally")
    s_yes = compile_fighter(fighter_with_gear, side="rally")
    inf_no  = s_no.squad(SquadType.INFANTRY)
    inf_yes = s_yes.squad(SquadType.INFANTRY)
    cav_no  = s_no.squad(SquadType.CAVALRY)
    cav_yes = s_yes.squad(SquadType.CAVALRY)

    assert inf_yes.atk_factor > inf_no.atk_factor + 0.5
    assert cav_yes.atk_factor == pytest.approx(cav_no.atk_factor)


def test_four_sauls_stacking_in_fighter():
    f = Fighter(
        label="quad-saul",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX"),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX"),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX"),
        joiners=(
            JoinerHero(hero_name="Saul", level="MAX"),
            JoinerHero(hero_name="Saul", level="MAX"),
            JoinerHero(hero_name="Saul", level="MAX"),
            JoinerHero(hero_name="Saul", level="MAX"),
        ),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(),
            archer=(),
        ),
    )
    assert len(f.joiners) == 4


def test_four_sauls_stack_defense_factor_per_spec():
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    troops = TroopRoster(
        infantry=(TroopGroup(tier="T10.5", count=80_000),),
        cavalry=(TroopGroup(tier="T10.5", count=80_000),),
        archer=(TroopGroup(tier="T10.5", count=80_000),),
    )
    bonuses = BonusVector()
    common = dict(
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        bonuses=bonuses, troops=troops,
    )
    defender_4saul = Fighter(label="def_4saul",
        joiners=tuple(JoinerHero(hero_name="Saul", level="MAX") for _ in range(4)),
        **common)
    defender_1saul = Fighter(label="def_1saul",
        joiners=(JoinerHero(hero_name="Saul", level="MAX"),),
        **common)
    attacker = Fighter(label="att",
        joiners=(),
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        bonuses=BonusVector(squad_atk_pct=200, squad_let_pct=120),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=120_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )

    res4 = run_battle(BattleConfig(attacker=attacker, defender=defender_4saul,
                                       rng_mode=RNGMode.EXPECTED))
    res1 = run_battle(BattleConfig(attacker=attacker, defender=defender_1saul,
                                       rng_mode=RNGMode.EXPECTED))

    assert res4.score < res1.score, (
        f"4 Sauls should defend better than 1 Saul. "
        f"Got 4-Saul score={res4.score}, 1-Saul score={res1.score}"
    )


def test_find_best_defender_returns_top_k():
    from kingshot_sim.optimizer.best_counter import find_best_defender
    from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool

    attacker = Fighter(
        label="threat",
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=BonusVector(squad_atk_pct=200, squad_def_pct=180),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=120_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    space = SearchSpace(
        available_mythic_inf=["Helga", "Eric"],
        available_mythic_cav=["Petra", "Margot"],
        available_mythic_arc=["Jaeger", "Yang"],
        available_joiners=["Chenko", "Howard", "Quinn"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.20,
        n_joiners=2,
        bonuses=BonusVector(squad_atk_pct=180, squad_def_pct=200),
    )
    report = find_best_defender(attacker, space, top_k=3, screen_top_n=10,
                                  mc_trials=20, mc_seed=42)
    assert len(report.top_k) == 3
    assert [e.rank for e in report.top_k] == [1, 2, 3]


def test_find_best_defender_orders_by_ascending_raw_score():
    from kingshot_sim.optimizer.best_counter import find_best_defender
    from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool

    attacker = Fighter(
        label="threat",
        leader_inf=LeaderHero(hero_name="Helga", level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Jabel", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Saul",  level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T9", count=50_000),),
            cavalry=(TroopGroup(tier="T9", count=50_000),),
            archer=(TroopGroup(tier="T9", count=50_000),),
        ),
    )
    space = SearchSpace(
        available_mythic_inf=["Helga", "Eric"],
        available_mythic_cav=["Petra", "Margot"],
        available_mythic_arc=["Jaeger"],
        available_joiners=["Chenko", "Howard"],
        troop_pool=TroopPool(infantry_tier="T10.5", cavalry_tier="T10.5",
                              archer_tier="T10.5", march_cap=300_000),
        troop_ratio_step=0.25, n_joiners=1,
    )
    report = find_best_defender(attacker, space, top_k=3, screen_top_n=10,
                                  mc_trials=20, mc_seed=0)
    raws = [e.mc.score_median for e in report.top_k]
    assert raws == sorted(raws), \
        f"Expected ascending raw scores (best defense first), got {raws}"
