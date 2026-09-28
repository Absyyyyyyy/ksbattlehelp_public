from __future__ import annotations
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero,
)
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.compile import compile_fighter
from kingshot_sim.domain.enums import RNGMode, SquadType


def _basic_troops(per_squad: int = 50_000) -> TroopRoster:
    return TroopRoster(
        infantry=(TroopGroup(tier="T10.5", count=per_squad),),
        cavalry=(TroopGroup(tier="T10.5", count=per_squad),),
        archer=(TroopGroup(tier="T10.5", count=per_squad),),
    )


def _attacker(
    joiners: tuple[JoinerHero, ...] = (),
    inf_hero: str = "Amadeus",
    inf_widget: int = 0,
    per_squad: int = 50_000,
) -> Fighter:
    return Fighter(
        label="attacker",
        leader_inf=LeaderHero(hero_name=inf_hero, level="MAX", widget_level=inf_widget),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=joiners,
        bonuses=BonusVector(),
        troops=_basic_troops(per_squad),
    )


def _defender(per_squad: int = 300_000) -> Fighter:
    return Fighter(
        label="defender",
        leader_inf=LeaderHero(hero_name="Eric",  level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=_basic_troops(per_squad),
    )


def test_battle_config_defaults_to_rally():
    cfg = BattleConfig(attacker=_attacker(), defender=_defender())
    assert cfg.is_solo_attack is False


def test_solo_attacker_compiles_no_joiner_skills():
    att_with_joiners = _attacker(joiners=(
        JoinerHero(hero_name="Chenko", level="MAX"),
        JoinerHero(hero_name="Gordon", level="MAX"),
        JoinerHero(hero_name="Howard", level="MAX"),
        JoinerHero(hero_name="Amane", level="MAX"),
    ))
    rally_state = compile_fighter(att_with_joiners, side="rally")
    solo_state  = compile_fighter(att_with_joiners, side="solo")

    assert len(rally_state.skills) > len(solo_state.skills), (
        f"Solo should drop joiner skills; "
        f"rally={len(rally_state.skills)}, "
        f"solo={len(solo_state.skills)}"
    )


def test_solo_attacker_battle_same_as_no_joiners():
    att_with_joiners = _attacker(joiners=(
        JoinerHero(hero_name="Chenko", level="MAX"),
        JoinerHero(hero_name="Gordon", level="MAX"),
        JoinerHero(hero_name="Howard", level="MAX"),
        JoinerHero(hero_name="Amane",  level="MAX"),
    ))
    att_no_joiners = _attacker(joiners=())
    defender = _defender()

    r_solo = run_battle(BattleConfig(
        attacker=att_with_joiners, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=True,
    ))
    r_rally_no_joiners = run_battle(BattleConfig(
        attacker=att_no_joiners, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=False,
    ))
    assert r_solo.score == pytest.approx(r_rally_no_joiners.score, abs=1e-9)


def test_solo_weaker_than_rally_when_joiners_present():
    att = _attacker(joiners=(
        JoinerHero(hero_name="Chenko", level="MAX"),
        JoinerHero(hero_name="Gordon", level="MAX"),
        JoinerHero(hero_name="Howard", level="MAX"),
        JoinerHero(hero_name="Amane",  level="MAX"),
    ))
    defender = _defender()

    r_rally = run_battle(BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=False,
    ))
    r_solo = run_battle(BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=True,
    ))
    assert r_rally.score > r_solo.score, (
        f"Rally should outperform solo (joiners help); "
        f"rally={r_rally.score:.4f}, solo={r_solo.score:.4f}"
    )


def test_solo_silences_rally_widget_skill():
    att_with_amadeus_widget = _attacker(
        inf_hero="Amadeus", inf_widget=10, joiners=(),
    )
    defender = _defender()

    r_rally = run_battle(BattleConfig(
        attacker=att_with_amadeus_widget, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=False,
    ))
    r_solo = run_battle(BattleConfig(
        attacker=att_with_amadeus_widget, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=True,
    ))
    assert r_rally.score > r_solo.score, (
        f"Aegis of Fate (rally Atk widget) should help in rally and not "
        f"in solo; rally={r_rally.score:.4f}, solo={r_solo.score:.4f}"
    )


def test_solo_keeps_both_scope_leader_skills():
    att = _attacker(inf_widget=0, joiners=())
    solo_state = compile_fighter(att, side="solo")
    assert len(solo_state.skills) > 0, (
        "Solo state should still compile leader sk1/sk2/sk3 (both-scope)"
    )


def test_solo_no_widgets_no_joiners_matches_rally_no_widgets_no_joiners():
    att = _attacker(inf_widget=0, joiners=())
    defender = _defender()

    r_rally = run_battle(BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=False,
    ))
    r_solo = run_battle(BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=True,
    ))
    assert r_solo.score == pytest.approx(r_rally.score, abs=1e-9)


def test_defender_widget_fires_regardless_of_attacker_mode():
    att_solo  = _attacker(joiners=())
    att_rally = _attacker(joiners=())
    defender = Fighter(
        label="defender",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=_basic_troops(per_squad=300_000),
    )
    r_solo  = run_battle(BattleConfig(
        attacker=att_solo, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=True,
    ))
    r_rally = run_battle(BattleConfig(
        attacker=att_rally, defender=defender,
        rng_mode=RNGMode.EXPECTED, is_solo_attack=False,
    ))
    assert r_solo.score == pytest.approx(r_rally.score, abs=1e-9)


def test_monte_carlo_forwards_is_solo_attack():
    from kingshot_sim.engine.montecarlo import run_monte_carlo

    att = _attacker(joiners=(
        JoinerHero(hero_name="Gordon", level="MAX"),
        JoinerHero(hero_name="Chenko", level="MAX"),
        JoinerHero(hero_name="Howard", level="MAX"),
        JoinerHero(hero_name="Amane",  level="MAX"),
    ))
    defender = _defender()
    base_cfg_solo = BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.STOCHASTIC, is_solo_attack=True, seed=0,
    )
    base_cfg_rally = BattleConfig(
        attacker=att, defender=defender,
        rng_mode=RNGMode.STOCHASTIC, is_solo_attack=False, seed=0,
    )
    mc_solo  = run_monte_carlo(base_cfg_solo,  n_trials=20, seed=0)
    mc_rally = run_monte_carlo(base_cfg_rally, n_trials=20, seed=0)
    assert mc_rally.score_mean > mc_solo.score_mean, (
        f"Rally should outperform solo on average with helpful joiners; "
        f"rally_mean={mc_rally.score_mean:.4f}, solo_mean={mc_solo.score_mean:.4f}"
    )


def test_find_best_counter_accepts_is_solo_attack():
    from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool
    from kingshot_sim.optimizer.best_counter import find_best_counter

    defender = _defender()
    space = SearchSpace(
        available_mythic_inf=["Amadeus", "Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Jaeger"],
        available_joiners=["Chenko", "Gordon"],
        troop_pool=TroopPool(
            infantry_tier="T10.5", cavalry_tier="T10.5", archer_tier="T10.5",
            march_cap=150_000,
        ),
        troop_ratio_step=0.50,
        n_joiners=2,
        leader_widget_level=10,
    )
    report = find_best_counter(
        defender=defender, space=space,
        top_k=2, screen_top_n=2, mc_trials=0,
        is_solo_attack=True,
    )
    assert report.top_k, "Search must return at least one entry"
