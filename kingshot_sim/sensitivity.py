from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Callable, Optional, Literal
import math

from .config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from .domain.enums import RNGMode, SquadType
from .engine.battle import BattleConfig, run_battle
from .engine.montecarlo import run_monte_carlo, MonteCarloResult


SideLiteral = Literal["attacker", "defender"]


@dataclass(frozen=True)
class SensitivityParam:
    key: str
    label: str
    side: SideLiteral
    apply: Callable[[Fighter, float], Fighter]
    default_min: float
    default_max: float
    default_step: float
    value_format: Callable[[float], str] = field(default=lambda v: f"{v:.1f}")
    group: str = "Other"


@dataclass
class SweepPoint:
    value: float
    score: float
    score_ci_low: Optional[float] = None
    score_ci_high: Optional[float] = None


@dataclass
class SweepResult:
    param: SensitivityParam
    values: list[float]
    points: list[SweepPoint]
    mode: Literal["expected", "mc"]
    elapsed_s: float


def run_sweep(
    attacker: Fighter,
    defender: Fighter,
    param: SensitivityParam,
    values: list[float],
    *,
    mode: Literal["expected", "mc"] = "expected",
    mc_trials: int = 100,
    mc_seed: int = 0,
    fatigue_enabled: bool = True,
    max_rounds: int = 200,
    progress: Optional[Callable[[int, int], None]] = None,
) -> SweepResult:
    import time
    t0 = time.time()
    points: list[SweepPoint] = []

    for i, v in enumerate(values):
        if param.side == "attacker":
            try:
                att = param.apply(attacker, v)
                cfg = BattleConfig(
                    attacker=att, defender=defender,
                    rng_mode=RNGMode.STOCHASTIC if mode == "mc" else RNGMode.EXPECTED,
                    fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                )
            except Exception:
                points.append(SweepPoint(value=v, score=float("nan")))
                if progress: progress(i + 1, len(values))
                continue
        else:
            try:
                dfn = param.apply(defender, v)
                cfg = BattleConfig(
                    attacker=attacker, defender=dfn,
                    rng_mode=RNGMode.STOCHASTIC if mode == "mc" else RNGMode.EXPECTED,
                    fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                )
            except Exception:
                points.append(SweepPoint(value=v, score=float("nan")))
                if progress: progress(i + 1, len(values))
                continue

        if mode == "mc":
            mc = run_monte_carlo(cfg, n_trials=mc_trials, seed=mc_seed,
                                  keep_scores=False)
            points.append(SweepPoint(
                value=v,
                score=mc.score_median,
                score_ci_low=mc.score_ic95_low,
                score_ci_high=mc.score_ic95_high,
            ))
        else:
            res = run_battle(cfg)
            points.append(SweepPoint(value=v, score=res.score))

        if progress:
            progress(i + 1, len(values))

    return SweepResult(
        param=param,
        values=values,
        points=points,
        mode=mode,
        elapsed_s=time.time() - t0,
    )


def _set_leader_widget(klass: SquadType) -> Callable[[Fighter, float], Fighter]:
    def apply(f: Fighter, v: float) -> Fighter:
        new_widget = max(0, min(10, int(round(v))))
        if klass == SquadType.INFANTRY:
            return replace(f, leader_inf=replace(f.leader_inf, widget_level=new_widget))
        if klass == SquadType.CAVALRY:
            return replace(f, leader_cav=replace(f.leader_cav, widget_level=new_widget))
        return replace(f, leader_arc=replace(f.leader_arc, widget_level=new_widget))
    return apply


def _set_leader_gear(klass: SquadType, stat: str) -> Callable[[Fighter, float], Fighter]:
    field_name = f"gear_{stat}_pct"
    def apply(f: Fighter, v: float) -> Fighter:
        v = max(0.0, float(v))
        if klass == SquadType.INFANTRY:
            return replace(f, leader_inf=replace(f.leader_inf, **{field_name: v}))
        if klass == SquadType.CAVALRY:
            return replace(f, leader_cav=replace(f.leader_cav, **{field_name: v}))
        return replace(f, leader_arc=replace(f.leader_arc, **{field_name: v}))
    return apply


def _set_bonus_field(field_name: str) -> Callable[[Fighter, float], Fighter]:
    def apply(f: Fighter, v: float) -> Fighter:
        v = max(0.0, float(v))
        new_bonus = replace(f.bonuses, **{field_name: v})
        return replace(f, bonuses=new_bonus)
    return apply


def _set_troop_multiplier() -> Callable[[Fighter, float], Fighter]:
    def apply(f: Fighter, v: float) -> Fighter:
        mul = max(0.0, float(v))
        new_inf = tuple(TroopGroup(tier=g.tier, count=int(g.count * mul))
                          for g in f.troops.infantry)
        new_cav = tuple(TroopGroup(tier=g.tier, count=int(g.count * mul))
                          for g in f.troops.cavalry)
        new_arc = tuple(TroopGroup(tier=g.tier, count=int(g.count * mul))
                          for g in f.troops.archer)
        return replace(f, troops=TroopRoster(infantry=new_inf, cavalry=new_cav, archer=new_arc))
    return apply


def build_param_catalog() -> list[SensitivityParam]:
    out: list[SensitivityParam] = []
    int_fmt = lambda v: f"{int(round(v))}"
    pct_fmt = lambda v: f"{v:.0f}%"
    mul_fmt = lambda v: f"{v:.2f}×"

    klass_labels = [(SquadType.INFANTRY, "Inf"), (SquadType.CAVALRY, "Cav"),
                     (SquadType.ARCHER, "Arc")]
    stats = [("atk", "Attack"), ("def", "Defense"), ("let", "Lethality"), ("hp", "Health")]

    for side in ("attacker", "defender"):
        for klass, kl in klass_labels:
            out.append(SensitivityParam(
                key=f"{side}_leader_{kl.lower()}_widget",
                label=f"{kl} leader widget level",
                side=side,
                apply=_set_leader_widget(klass),
                default_min=0, default_max=10, default_step=1,
                value_format=int_fmt,
                group=f"{kl} Leader",
            ))
        for klass, kl in klass_labels:
            for stat_key, stat_lbl in stats:
                out.append(SensitivityParam(
                    key=f"{side}_leader_{kl.lower()}_gear_{stat_key}",
                    label=f"{kl} leader gear {stat_lbl} %",
                    side=side,
                    apply=_set_leader_gear(klass, stat_key),
                    default_min=0, default_max=300, default_step=20,
                    value_format=pct_fmt,
                    group=f"{kl} Leader",
                ))

        bonus_rows = (("squad", "All Squads"), ("inf", "Infantry"),
                       ("cav", "Cavalry"), ("arc", "Archer"))
        for r_key, r_lbl in bonus_rows:
            for stat_key, stat_lbl in stats:
                field_name = f"{r_key}_{stat_key}_pct"
                out.append(SensitivityParam(
                    key=f"{side}_bonus_{field_name}",
                    label=f"{r_lbl} {stat_lbl} %",
                    side=side,
                    apply=_set_bonus_field(field_name),
                    default_min=0, default_max=400, default_step=25,
                    value_format=pct_fmt,
                    group="Account bonuses",
                ))

        out.append(SensitivityParam(
            key=f"{side}_troops_mul",
            label="Troop count multiplier",
            side=side,
            apply=_set_troop_multiplier(),
            default_min=0.5, default_max=1.5, default_step=0.1,
            value_format=mul_fmt,
            group="Troops",
        ))

    return out


def linspace(a: float, b: float, step: float) -> list[float]:
    if step <= 0 or b < a:
        return [a]
    n = int(math.floor((b - a) / step + 1e-9)) + 1
    n = min(n, 200)
    return [round(a + i * step, 6) for i in range(n)]


__all__ = [
    "SensitivityParam", "SweepPoint", "SweepResult", "SideLiteral",
    "run_sweep", "build_param_catalog", "linspace",
]
