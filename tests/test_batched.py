from __future__ import annotations
import random
import numpy as np
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.batched import run_batch_expected
from kingshot_sim.domain.enums import RNGMode


def _defender() -> Fighter:
    return Fighter(
        label="Def",
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=BonusVector(squad_atk_pct=180, squad_def_pct=220,
                            squad_let_pct=100, squad_hp_pct=180),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _make_candidate(
    inf_h: str, cav_h: str, arc_h: str,
    inf_pct: float, cav_pct: float, arc_pct: float,
    march: int = 300_000,
    joiners: tuple = (),
) -> Fighter:
    return Fighter(
        label=f"{inf_h[:3]}/{cav_h[:3]}/{arc_h[:3]}",
        leader_inf=LeaderHero(hero_name=inf_h, level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name=cav_h, level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name=arc_h, level="MAX", widget_level=10),
        joiners=joiners,
        bonuses=BonusVector(squad_atk_pct=200, squad_def_pct=180,
                            squad_let_pct=120, squad_hp_pct=140),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=int(march * inf_pct)),),
            cavalry=(TroopGroup(tier="T10.5", count=int(march * cav_pct)),),
            archer=(TroopGroup(tier="T10.5", count=int(march * arc_pct)),),
        ),
    )


def test_batched_matches_sequential_on_single_candidate():
    cand = _make_candidate("Helga", "Margot", "Yang", 0.30, 0.30, 0.40,
                            joiners=(JoinerHero(hero_name="Chenko", level="MAX"),))
    defender = _defender()

    cfg = BattleConfig(attacker=cand, defender=defender,
                        rng_mode=RNGMode.EXPECTED, max_rounds=200)
    seq = run_battle(cfg).score
    batch = run_batch_expected([cand], defender, max_rounds=200)
    assert batch.score[0] == pytest.approx(seq, abs=1e-9)


def test_batched_matches_sequential_on_50_random_candidates():
    random.seed(0)
    inf = ["Helga", "Eric", "Triton", "Amadeus", "Long Fei"]
    cav = ["Petra", "Margot", "Sophia", "Jabel", "Hilde"]
    arc = ["Jaeger", "Yang", "Vivian", "Saul", "Marlin"]
    joiner_pool = ["Chenko", "Howard", "Quinn", "Yeonwoo", "Amane", "Gordon"]

    candidates = []
    for _ in range(50):
        i_h, c_h, a_h = random.choice(inf), random.choice(cav), random.choice(arc)
        ip = random.uniform(0.30, 0.80)
        cp = random.uniform(0.0, 1.0 - ip)
        js = tuple(JoinerHero(hero_name=h, level="MAX")
                    for h in random.sample(joiner_pool, 2))
        candidates.append(_make_candidate(i_h, c_h, a_h, ip, cp, 1.0 - ip - cp, joiners=js))

    defender = _defender()
    seq = np.array([
        run_battle(BattleConfig(attacker=c, defender=defender,
                                rng_mode=RNGMode.EXPECTED, max_rounds=200)).score
        for c in candidates
    ])
    batch = run_batch_expected(candidates, defender, max_rounds=200)

    diff = np.abs(seq - batch.score)
    assert diff.max() < 1e-9, f"Max diff = {diff.max():.2e}"
    assert np.argsort(-seq).tolist()[:10] == np.argsort(-batch.score).tolist()[:10]


def test_batched_handles_zero_squad():
    cand = _make_candidate("Helga", "Margot", "Jaeger", 0.50, 0.50, 0.0)
    batch = run_batch_expected([cand], _defender(), max_rounds=200)
    assert np.isfinite(batch.score[0])
    assert -1.0 <= batch.score[0] <= 1.0


def test_batched_winner_codes_consistent():
    cand = _make_candidate("Helga", "Petra", "Jaeger", 0.40, 0.30, 0.30)
    defender = _defender()
    cfg = BattleConfig(attacker=cand, defender=defender,
                        rng_mode=RNGMode.EXPECTED, max_rounds=200)
    seq_result = run_battle(cfg)
    batch = run_batch_expected([cand], defender, max_rounds=200)

    expected_code = {"attacker": 0, "defender": 1, None: 2}[seq_result.winner]
    assert batch.winner_code[0] == expected_code


def test_batched_empty_input():
    result = run_batch_expected([], _defender(), max_rounds=200)
    assert result.score.shape == (0,)
    assert result.attacker_final.shape == (0, 3)


def test_batched_uses_compile_cache():
    from kingshot_sim.engine.batched import _compile_cache_key

    a = _make_candidate("Helga", "Margot", "Yang", 0.40, 0.30, 0.30)
    b = _make_candidate("Helga", "Margot", "Yang", 0.50, 0.20, 0.30)
    assert _compile_cache_key(a) == _compile_cache_key(b)

    c = _make_candidate("Eric", "Margot", "Yang", 0.40, 0.30, 0.30)
    assert _compile_cache_key(a) != _compile_cache_key(c)


def test_batched_throughput_above_2000_per_sec():
    import time
    candidates = [
        _make_candidate("Helga", "Margot", "Yang", 0.30 + 0.05 * (i % 10),
                        0.10 + 0.05 * (i % 7), 0.10 + 0.05 * (i % 5))
        for i in range(200)
    ]
    t0 = time.time()
    run_batch_expected(candidates, _defender(), max_rounds=200)
    elapsed = time.time() - t0
    rate = len(candidates) / elapsed
    assert rate > 2000, f"Throughput too low: {rate:.0f} fights/sec"
