import math
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.sensitivity import (
    build_param_catalog, run_sweep, linspace, SensitivityParam,
)


def _attacker() -> Fighter:
    return Fighter(
        label="att",
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=5),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=5),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=5),
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=BonusVector(squad_atk_pct=100, squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )


def _defender() -> Fighter:
    return Fighter(
        label="def",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=5),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=5),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=5),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=100, squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )


def test_catalog_has_all_expected_params():
    cat = build_param_catalog()
    keys = {p.key for p in cat}
    assert "attacker_leader_inf_widget" in keys
    assert "defender_leader_arc_gear_atk" in keys
    assert "attacker_bonus_squad_atk_pct" in keys
    assert "defender_troops_mul" in keys


def test_mutators_do_not_change_input_fighter():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_leader_inf_widget")
    f = _attacker()
    original_widget = f.leader_inf.widget_level
    f2 = p.apply(f, 9.0)
    assert f.leader_inf.widget_level == original_widget
    assert f2.leader_inf.widget_level == 9


def test_widget_mutator_clamps_out_of_range():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_leader_inf_widget")
    f = _attacker()
    assert p.apply(f, 15.0).leader_inf.widget_level == 10
    assert p.apply(f, -5.0).leader_inf.widget_level == 0


def test_gear_mutator_targets_correct_class():
    cat = build_param_catalog()
    p_inf_atk = next(p for p in cat if p.key == "attacker_leader_inf_gear_atk")
    f = _attacker()
    f2 = p_inf_atk.apply(f, 75.0)
    assert f2.leader_inf.gear_atk_pct == 75.0
    assert f2.leader_cav.gear_atk_pct == 0.0
    assert f2.leader_arc.gear_atk_pct == 0.0


def test_troops_multiplier_scales_all_squads():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_troops_mul")
    f = _attacker()
    f2 = p.apply(f, 0.5)
    inf_total = sum(g.count for g in f2.troops.infantry)
    assert inf_total == 40_000


def test_linspace_inclusive():
    assert linspace(0, 10, 1) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_linspace_caps_at_200():
    out = linspace(0, 1000, 0.001)
    assert len(out) == 200


def test_linspace_handles_zero_step():
    assert linspace(5, 10, 0) == [5]


def test_sweep_monotonic_with_attacker_buff():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_leader_inf_gear_atk")
    values = linspace(0, 200, 50)
    res = run_sweep(_attacker(), _defender(), p, values, mode="expected")
    scores = [pt.score for pt in res.points]
    for i in range(0, len(scores) - 5):
        assert scores[i] <= scores[i + 5] + 1e-9, (
            f"Score should be non-decreasing as attacker buffs gear: "
            f"position {i}-{i+5}: {scores[i]} -> {scores[i+5]}"
        )


def test_sweep_monotonic_with_defender_buff():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "defender_leader_inf_gear_def")
    values = linspace(0, 200, 50)
    res = run_sweep(_attacker(), _defender(), p, values, mode="expected")
    scores = [pt.score for pt in res.points]
    for i in range(0, len(scores) - 5):
        assert scores[i] >= scores[i + 5] - 1e-9, (
            f"Score should be non-increasing as defender buffs gear: "
            f"{i}-{i+5}: {scores[i]} -> {scores[i+5]}"
        )


def test_sweep_mc_returns_ci_bands():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_leader_inf_widget")
    values = [0.0, 5.0, 10.0]
    res = run_sweep(_attacker(), _defender(), p, values,
                      mode="mc", mc_trials=20, mc_seed=42)
    for pt in res.points:
        assert pt.score_ci_low is not None
        assert pt.score_ci_high is not None
        assert pt.score_ci_low <= pt.score <= pt.score_ci_high + 1e-9


def test_sweep_progress_callback():
    cat = build_param_catalog()
    p = next(p for p in cat if p.key == "attacker_leader_inf_widget")
    values = list(range(0, 11))
    progress_calls: list[tuple[int, int]] = []
    run_sweep(_attacker(), _defender(), p,
                [float(v) for v in values],
                mode="expected",
                progress=lambda done, total: progress_calls.append((done, total)))
    assert len(progress_calls) == len(values)
    assert progress_calls[-1] == (len(values), len(values))
