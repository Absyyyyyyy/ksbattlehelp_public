import pytest
import math

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.montecarlo import run_monte_carlo
from kingshot_sim.engine.stochastic import BattleRng
from kingshot_sim.domain.enums import BattleType, RNGMode, SquadType


def _fighter(label: str, n: int = 100_000, leader_inf="Eric") -> Fighter:
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name=leader_inf, level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(
            JoinerHero(hero_name="Chenko", level="MAX"),
            JoinerHero(hero_name="Howard", level="MAX"),
        ),
        bonuses=BonusVector(
            squad_atk_pct=200, squad_def_pct=180,
            squad_let_pct=120, squad_hp_pct=140,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=n),),
            cavalry=(TroopGroup(tier="T10.5", count=n),),
            archer=(TroopGroup(tier="T10.5", count=n),),
        ),
    )


def test_rng_reproducibility():
    r1 = BattleRng(seed=42)
    r2 = BattleRng(seed=42)
    out1 = [r1.bernoulli(0.5) for _ in range(100)]
    out2 = [r2.bernoulli(0.5) for _ in range(100)]
    assert out1 == out2


def test_rng_bernoulli_empirical_rate():
    r = BattleRng(seed=12345)
    n_proc = sum(r.bernoulli(0.4) for _ in range(10_000))
    rate = n_proc / 10_000
    assert 0.38 <= rate <= 0.42, f"Expected ~0.40, got {rate}"


def test_rng_edge_cases():
    r = BattleRng(seed=0)
    assert r.bernoulli(0.0) is False
    assert r.bernoulli(-0.5) is False
    assert r.bernoulli(1.0) is True
    assert r.bernoulli(2.0) is True


def test_battle_with_seed_reproducible():
    cfg1 = BattleConfig(
        attacker=_fighter("A"),
        defender=_fighter("B", n=80_000),
        rng_mode=RNGMode.STOCHASTIC,
        seed=42,
    )
    cfg2 = BattleConfig(
        attacker=_fighter("A"),
        defender=_fighter("B", n=80_000),
        rng_mode=RNGMode.STOCHASTIC,
        seed=42,
    )
    r1 = run_battle(cfg1)
    r2 = run_battle(cfg2)
    assert r1.score == r2.score
    assert r1.winner == r2.winner
    assert len(r1.rounds) == len(r2.rounds)


def test_different_seeds_give_different_results():
    scores = []
    for s in range(5):
        cfg = BattleConfig(
            attacker=_fighter("A"),
            defender=_fighter("B", n=80_000),
            rng_mode=RNGMode.STOCHASTIC,
            seed=s,
        )
        scores.append(run_battle(cfg).score)
    assert len(set(scores)) > 1


def test_montecarlo_returns_valid_stats():
    cfg = BattleConfig(
        attacker=_fighter("A"),
        defender=_fighter("B", n=80_000),
        rng_mode=RNGMode.STOCHASTIC,
    )
    r = run_monte_carlo(cfg, n_trials=100, seed=0)
    assert r.n_trials == 100
    assert 0.0 <= r.win_rate_attacker <= 1.0
    assert 0.0 <= r.win_rate_defender <= 1.0
    assert 0.0 <= r.draw_rate <= 1.0
    assert abs(r.win_rate_attacker + r.win_rate_defender + r.draw_rate - 1.0) < 1e-9
    assert r.score_min <= r.score_median <= r.score_max
    assert r.score_ic95_low <= r.score_median <= r.score_ic95_high
    assert len(r.scores) == 100


def test_montecarlo_strong_attacker_wins_majority():
    cfg = BattleConfig(
        attacker=_fighter("Strong", n=120_000),
        defender=_fighter("Weak", n=50_000),
        rng_mode=RNGMode.STOCHASTIC,
    )
    r = run_monte_carlo(cfg, n_trials=50, seed=1)
    assert r.win_rate_attacker > 0.80, \
        f"Expected attacker win >80%, got {r.win_rate_attacker:.0%}"


def test_montecarlo_seed_makes_run_reproducible():
    cfg = BattleConfig(
        attacker=_fighter("A"),
        defender=_fighter("B", n=80_000),
        rng_mode=RNGMode.STOCHASTIC,
    )
    r1 = run_monte_carlo(cfg, n_trials=30, seed=42)
    r2 = run_monte_carlo(cfg, n_trials=30, seed=42)
    assert r1.scores == r2.scores
    assert r1.score_median == r2.score_median


def test_margot_dodge_reduces_damage_taken(monkeypatch):
    from kingshot_sim.engine import compile as compile_mod

    defender = Fighter(
        label="Defender",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )
    attacker = _fighter("Att", n=80_000)
    cfg = BattleConfig(attacker=attacker, defender=defender, rng_mode=RNGMode.STOCHASTIC)

    r_dodge = run_monte_carlo(cfg, n_trials=80, seed=0)

    real_compile = compile_mod.compile_fighter

    def compile_no_dodge(fighter, side):
        state = real_compile(fighter, side)
        if side == "defender":
            state.dodge_chance = 0.0
        return state

    monkeypatch.setattr("kingshot_sim.engine.battle.compile_fighter", compile_no_dodge)
    r_no_dodge = run_monte_carlo(cfg, n_trials=80, seed=0)

    assert r_dodge.score_median < r_no_dodge.score_median, (
        f"Margot dodge should reduce attacker score: "
        f"dodge={r_dodge.score_median:.4f} vs no_dodge={r_no_dodge.score_median:.4f}"
    )


def test_dodge_chance_compiled_from_margot():
    from kingshot_sim.engine.compile import compile_fighter
    margot_fighter = Fighter(
        label="M",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX"),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX"),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX"),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=1000),),
            cavalry=(TroopGroup(tier="T10.5", count=1000),),
            archer=(TroopGroup(tier="T10.5", count=1000),),
        ),
    )
    state = compile_fighter(margot_fighter, side="rally")
    assert state.dodge_chance == pytest.approx(0.20)


def test_dodge_chance_zero_without_margot():
    from kingshot_sim.engine.compile import compile_fighter
    state = compile_fighter(_fighter("nope"), side="rally")
    assert state.dodge_chance == 0.0


def test_yang_pity_empirical_rate():
    from kingshot_sim.engine.stochastic import BattleRng
    from kingshot_sim.engine.state import FighterState, TimedEffect
    from kingshot_sim.domain.heroes import Hero
    from kingshot_sim.data.catalog import get_hero_skills
    from kingshot_sim.engine.stochastic import stochastic_round_effects

    yang = Hero(name="Yang", level="MAX", widget_level=0)
    skills = [s for s in get_hero_skills(yang) if s.slot == "sk3"]
    assert len(skills) == 1
    state = FighterState(
        label="Yang", side="rally",
        squads={st: None for st in SquadType.all()},
        skills=skills,
    )

    rng = BattleRng(seed=99)
    n_proc = 0
    for r in range(10_000):
        effects, _ = stochastic_round_effects(state, r, rng, target_terror=False)
        if effects:
            n_proc += 1
    rate = n_proc / 10_000
    assert 0.55 <= rate <= 0.62, f"Expected ~0.58, got {rate:.3f}"
