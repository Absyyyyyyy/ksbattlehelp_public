from __future__ import annotations
from dataclasses import dataclass, field
from statistics import median, mean, pstdev, quantiles
from typing import Optional

from ..domain.enums import RNGMode
from .battle import BattleConfig, run_battle


@dataclass
class MonteCarloResult:
    n_trials: int
    win_rate_attacker: float
    win_rate_defender: float
    draw_rate: float
    score_mean: float
    score_median: float
    score_std: float
    score_ic95_low: float
    score_ic95_high: float
    score_min: float
    score_max: float
    scores: list[float] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"MC[n={self.n_trials}]: "
            f"score median={self.score_median:+.4f} "
            f"(95% CI [{self.score_ic95_low:+.4f}, {self.score_ic95_high:+.4f}]) "
            f"win={self.win_rate_attacker:.1%} draw={self.draw_rate:.1%} "
            f"loss={self.win_rate_defender:.1%}"
        )


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (q / 100.0) * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def run_monte_carlo(
    base_config: BattleConfig,
    n_trials: int = 500,
    seed: Optional[int] = None,
    keep_scores: bool = True,
) -> MonteCarloResult:
    if n_trials <= 0:
        raise ValueError("n_trials must be positive")

    scores: list[float] = []
    n_att_win = 0
    n_def_win = 0
    n_draw = 0

    base_seed = seed if seed is not None else 0

    for i in range(n_trials):
        trial_cfg = BattleConfig(
            attacker=base_config.attacker,
            defender=base_config.defender,
            battle_type=base_config.battle_type,
            rng_mode=RNGMode.STOCHASTIC,
            seed=base_seed + i,
            fatigue_enabled=base_config.fatigue_enabled,
            max_rounds=base_config.max_rounds,
            is_solo_attack=base_config.is_solo_attack,
        )
        result = run_battle(trial_cfg)
        scores.append(result.score)
        if result.winner == "attacker":
            n_att_win += 1
        elif result.winner == "defender":
            n_def_win += 1
        else:
            n_draw += 1

    sorted_scores = sorted(scores)
    return MonteCarloResult(
        n_trials=n_trials,
        win_rate_attacker=n_att_win / n_trials,
        win_rate_defender=n_def_win / n_trials,
        draw_rate=n_draw / n_trials,
        score_mean=mean(scores),
        score_median=median(scores),
        score_std=pstdev(scores) if n_trials > 1 else 0.0,
        score_ic95_low=_percentile(sorted_scores, 2.5),
        score_ic95_high=_percentile(sorted_scores, 97.5),
        score_min=sorted_scores[0],
        score_max=sorted_scores[-1],
        scores=scores if keep_scores else [],
    )


__all__ = ["MonteCarloResult", "run_monte_carlo"]
