from __future__ import annotations
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.domain.enums import RNGMode, SquadType


CAV_HEROES_BY_GEN: dict[int, str] = {
    1: "Jabel",
    2: "Hilde",
    3: "Petra",
    4: "Margot",
    5: "Thrud",
    6: "Sophia",
}


def _build_attacker(cav_hero: str, widget_level: int = 10) -> Fighter:
    return Fighter(
        label=f"att-{cav_hero}",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=widget_level),
        leader_cav=LeaderHero(hero_name=cav_hero, level="MAX", widget_level=widget_level),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=widget_level),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _build_fixed_defender() -> Fighter:
    return Fighter(
        label="def-fixed",
        leader_inf=LeaderHero(hero_name="Helga",  level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Saul",   level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _score(cav_hero: str) -> float:
    f = _build_attacker(cav_hero, widget_level=10)
    cfg = BattleConfig(attacker=f, defender=_build_fixed_defender(),
                        rng_mode=RNGMode.EXPECTED)
    return run_battle(cfg).score


def test_margot_is_not_overpowered_among_cav():
    scores = {h: _score(h) for h in CAV_HEROES_BY_GEN.values()}
    sorted_by_score = sorted(scores.items(), key=lambda kv: -kv[1])
    margot_rank = next(i for i, (h, _) in enumerate(sorted_by_score) if h == "Margot")
    assert margot_rank >= 2, (
        f"Margot is suspiciously high in the Cav ladder. "
        f"Ranking: {sorted_by_score}. Margot is at rank {margot_rank} "
        f"(0-indexed); a value < 2 means she's in the top 2, which "
        f"would justify the 'OP' concern."
    )


@pytest.mark.parametrize("weaker,stronger", [
    ("Jabel", "Hilde"),
    ("Hilde", "Petra"),
    ("Margot", "Thrud"),
])
def test_cav_leader_gen_pair_orders_correctly(weaker, stronger):
    s_weaker = _score(weaker)
    s_stronger = _score(stronger)
    assert s_stronger > s_weaker, (
        f"Expected {stronger} (later gen) > {weaker} (earlier gen). "
        f"{weaker}={s_weaker:.4f}, {stronger}={s_stronger:.4f}."
    )


def test_sophia_terror_chain_activates_in_expected_mode():
    s_sophia = _score("Sophia")
    s_hilde = _score("Hilde")
    assert s_sophia > s_hilde, (
        f"V8.7-E regression: Sophia (Gen 6) should outscore Hilde "
        f"(Gen 2) once Terror chain is wired. Sophia={s_sophia:.4f}, "
        f"Hilde={s_hilde:.4f}. If Sophia is back below Hilde, check the "
        f"APPLY_TERROR_ON_HIT plumbing in resolver.py and catalog.py."
    )


@pytest.mark.parametrize("hero", list(CAV_HEROES_BY_GEN.values()))
def test_expected_score_in_stochastic_ic95(hero):
    from kingshot_sim.engine.montecarlo import run_monte_carlo

    f = _build_attacker(hero, widget_level=10)
    cfg_e = BattleConfig(attacker=f, defender=_build_fixed_defender(),
                          rng_mode=RNGMode.EXPECTED)
    cfg_s = BattleConfig(attacker=f, defender=_build_fixed_defender(),
                          rng_mode=RNGMode.STOCHASTIC)
    s_e = run_battle(cfg_e).score
    mc = run_monte_carlo(cfg_s, n_trials=200, seed=0, keep_scores=False)
    assert mc.score_ic95_low <= s_e <= mc.score_ic95_high, (
        f"{hero}: EXPECTED={s_e:.4f} outside STOCHASTIC IC95 "
        f"[{mc.score_ic95_low:.4f}, {mc.score_ic95_high:.4f}] "
        f"(median={mc.score_median:.4f}). Drift here indicates "
        f"one of the two RNG modes has a bug — drill into which "
        f"side is the outlier."
    )

def test_print_cav_leader_score_table(capsys):
    from kingshot_sim.data.reference import HERO_LEADER_MAX, HERO_WIDGET, WIDGET_MAX

    print("\n=== Cav-leader score comparison (defender held constant) ===")
    print(f"{'Hero':<10} {'Gen':<4} {'LdrMax%':<10} {'WidMax':<8} {'Score':<10}")
    print("-" * 50)
    for gen, hero in CAV_HEROES_BY_GEN.items():
        score = _score(hero)
        ldr = HERO_LEADER_MAX[hero]
        wid = WIDGET_MAX[HERO_WIDGET[hero]]
        marker = ""
        if hero == "Margot":
            marker = "  ← user-reported 'OP' check"
        if hero == "Sophia":
            marker = "  ← Gen 6, Terror chain inactive"
        print(f"{hero:<10} {gen:<4} {ldr:<10.2f} {wid:<8.2f} {score:<10.4f}{marker}")
    assert True
