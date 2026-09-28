from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
import heapq
import time

from ..config.fighter import Fighter
from ..domain.enums import BattleType, RNGMode
from ..engine.battle import BattleConfig, run_battle
from ..engine.batched import run_batch_expected
from ..engine.montecarlo import run_monte_carlo, MonteCarloResult
from .enumerate import enumerate_candidates, count_candidates
from .search_space import SearchSpace


class SearchCancelled(Exception):
    pass


@dataclass
class RankingEntry:
    rank: int
    attacker: Fighter
    expected_score: float
    mc: Optional[MonteCarloResult] = None

    @property
    def headline_score(self) -> float:
        return self.mc.score_median if self.mc is not None else self.expected_score

    @property
    def candidate(self) -> Fighter:
        return self.attacker


@dataclass
class BestCounterReport:
    defender_label: str
    n_candidates: int
    n_screened: int
    n_refined: int
    elapsed_s: float
    n_battles: int = 0
    top_k: list[RankingEntry] = field(default_factory=list)
    cancelled: bool = False

    def summary(self) -> str:
        lines = [
            f"Best Counter Search vs {self.defender_label!r}",
            f"  Total candidates: {self.n_candidates}",
            f"  Screened in EXPECTED: {self.n_screened}",
            f"  Refined in STOCHASTIC: {self.n_refined}",
            f"  Battles simulated: {self.n_battles}",
            f"  Elapsed: {self.elapsed_s:.1f}s",
            "",
            f"  {'#':>3}  {'score':>8}  {'win%':>6}  {'CI95':>22}  attacker",
        ]
        for e in self.top_k:
            if e.mc is not None:
                lines.append(
                    f"  {e.rank:>3}  {e.mc.score_median:+8.4f}  "
                    f"{e.mc.win_rate_attacker:>5.0%}  "
                    f"[{e.mc.score_ic95_low:+.3f}, {e.mc.score_ic95_high:+.3f}]  "
                    f"{e.attacker.label}"
                )
            else:
                lines.append(
                    f"  {e.rank:>3}  {e.expected_score:+8.4f}  "
                    f"{'(exp)':>6}  {'—':>22}  {e.attacker.label}"
                )
        return "\n".join(lines)


def find_best_counter(
    defender: Fighter,
    space: SearchSpace,
    top_k: int = 10,
    screen_top_n: int = 50,
    mc_trials: int = 200,
    mc_seed: int = 0,
    fatigue_enabled: bool = True,
    max_rounds: int = 200,
    progress: Optional[Callable[[int, int], None]] = None,
    screen_chunk_size: int = 5000,
    use_batched_screen: bool = True,
    is_solo_attack: bool = False,
) -> BestCounterReport:
    if top_k > screen_top_n:
        raise ValueError("top_k must be <= screen_top_n")

    n_candidates = count_candidates(space)
    t0 = time.time()

    top_heap: list[tuple[float, int, Fighter]] = []
    n_screened_total = 0
    tiebreaker = 0
    cancelled = False
    n_done = 0
    chunk: list[Fighter] = []

    def _push_screened(score: float, cand: Fighter) -> None:
        nonlocal tiebreaker, n_screened_total
        n_screened_total += 1
        item = (score, tiebreaker, cand)
        tiebreaker += 1
        if len(top_heap) < screen_top_n:
            heapq.heappush(top_heap, item)
        elif score > top_heap[0][0]:
            heapq.heapreplace(top_heap, item)

    def _report_progress() -> None:
        if progress:
            progress(n_done, n_candidates)

    def _flush_chunk() -> None:
        nonlocal chunk, n_done
        if not chunk:
            return
        if use_batched_screen:
            try:
                result = run_batch_expected(
                    chunk, defender,
                    fatigue_enabled=fatigue_enabled,
                    max_rounds=max_rounds,
                    is_solo_attack=is_solo_attack,
                )
                for i, cand in enumerate(chunk):
                    _push_screened(float(result.score[i]), cand)
            except Exception:
                for cand in chunk:
                    cfg = BattleConfig(
                        attacker=cand, defender=defender,
                        rng_mode=RNGMode.EXPECTED,
                        fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                        is_solo_attack=is_solo_attack,
                    )
                    try:
                        _push_screened(run_battle(cfg).score, cand)
                    except Exception:
                        pass
        else:
            for cand in chunk:
                cfg = BattleConfig(
                    attacker=cand, defender=defender,
                    rng_mode=RNGMode.EXPECTED,
                    fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                    is_solo_attack=is_solo_attack,
                )
                try:
                    _push_screened(run_battle(cfg).score, cand)
                except Exception:
                    pass
        n_done += len(chunk)
        _report_progress()
        chunk.clear()

    try:
        for cand in enumerate_candidates(space):
            chunk.append(cand)
            if len(chunk) >= screen_chunk_size:
                _flush_chunk()
        _flush_chunk()
    except SearchCancelled:
        cancelled = True

    top_screened: list[tuple[float, Fighter]] = [
        (s, c) for (s, _, c) in sorted(top_heap, key=lambda x: -x[0])
    ]
    top_heap.clear()

    refined: list[RankingEntry] = []
    if mc_trials > 0 and not cancelled:
        for i, (exp_score, cand) in enumerate(top_screened):
            if progress:
                try:
                    progress(n_done, n_candidates)
                except SearchCancelled:
                    cancelled = True
                    break
            cfg = BattleConfig(
                attacker=cand,
                defender=defender,
                rng_mode=RNGMode.STOCHASTIC,
                fatigue_enabled=fatigue_enabled,
                max_rounds=max_rounds,
                is_solo_attack=is_solo_attack,
            )
            mc = run_monte_carlo(cfg, n_trials=mc_trials, seed=mc_seed, keep_scores=False)
            refined.append(RankingEntry(
                rank=0,
                attacker=cand,
                expected_score=exp_score,
                mc=mc,
            ))
        if refined and refined[0].mc is not None:
            refined.sort(key=lambda e: -e.mc.score_median)
    else:
        for exp_score, cand in top_screened:
            refined.append(RankingEntry(
                rank=0,
                attacker=cand,
                expected_score=exp_score,
                mc=None,
            ))
        refined.sort(key=lambda e: -e.expected_score)

    for i, e in enumerate(refined[:top_k], start=1):
        e.rank = i

    n_mc_refined = sum(1 for e in refined if e.mc is not None)
    n_battles = n_screened_total + n_mc_refined * mc_trials

    elapsed = time.time() - t0
    return BestCounterReport(
        defender_label=defender.label,
        n_candidates=n_candidates,
        n_screened=n_screened_total,
        n_refined=len(refined),
        n_battles=n_battles,
        elapsed_s=elapsed,
        top_k=refined[:top_k],
        cancelled=cancelled,
    )


@dataclass
class BestDefenseReport:
    attacker_label: str
    n_candidates: int
    n_screened: int
    n_refined: int
    elapsed_s: float
    n_battles: int = 0
    top_k: list[RankingEntry] = field(default_factory=list)
    cancelled: bool = False

    def summary(self) -> str:
        lines = [
            f"Best Defense Search vs attacker {self.attacker_label!r}",
            f"  Total candidates: {self.n_candidates}",
            f"  Screened in EXPECTED: {self.n_screened}",
            f"  Refined in STOCHASTIC: {self.n_refined}",
            f"  Battles simulated: {self.n_battles}",
            f"  Elapsed: {self.elapsed_s:.1f}s",
            "",
            f"  {'#':>3}  {'def-score':>9}  {'def win%':>8}  {'CI95 (def)':>22}  defender",
        ]
        for e in self.top_k:
            if e.mc is not None:
                def_score = -e.mc.score_median
                def_win = 1.0 - e.mc.win_rate_attacker
                ci_low = -e.mc.score_ic95_high
                ci_hi  = -e.mc.score_ic95_low
                lines.append(
                    f"  {e.rank:>3}  {def_score:+9.4f}  "
                    f"{def_win:>7.0%}  "
                    f"[{ci_low:+.3f}, {ci_hi:+.3f}]  "
                    f"{e.attacker.label}"
                )
            else:
                lines.append(
                    f"  {e.rank:>3}  {-e.expected_score:+9.4f}  "
                    f"{'(exp)':>8}  {'—':>22}  {e.attacker.label}"
                )
        return "\n".join(lines)


def find_best_defender(
    attacker: Fighter,
    space: SearchSpace,
    top_k: int = 10,
    screen_top_n: int = 50,
    mc_trials: int = 200,
    mc_seed: int = 0,
    fatigue_enabled: bool = True,
    max_rounds: int = 200,
    progress: Optional[Callable[[int, int], None]] = None,
    screen_chunk_size: int = 5000,
    use_batched_screen: bool = True,
    is_solo_attack: bool = False,
) -> BestDefenseReport:
    if top_k > screen_top_n:
        raise ValueError("top_k must be <= screen_top_n")

    n_candidates = count_candidates(space)
    t0 = time.time()

    top_heap: list[tuple[float, int, Fighter]] = []
    n_screened_total = 0
    tiebreaker = 0
    cancelled = False
    n_done = 0
    chunk: list[Fighter] = []

    def _push_screened(score: float, cand: Fighter) -> None:
        nonlocal tiebreaker, n_screened_total
        n_screened_total += 1
        item = (-score, tiebreaker, cand)
        tiebreaker += 1
        if len(top_heap) < screen_top_n:
            heapq.heappush(top_heap, item)
        elif -score > top_heap[0][0]:
            heapq.heapreplace(top_heap, item)

    def _flush_chunk() -> None:
        nonlocal chunk, n_done
        if not chunk:
            return
        if use_batched_screen:
            from ..engine.batched import run_batch_expected_defense
            try:
                batch = run_batch_expected_defense(
                    chunk, attacker,
                    fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                    is_solo_attack=is_solo_attack,
                )
                for cand, sc in zip(chunk, batch.score):
                    _push_screened(float(sc), cand)
            except Exception:
                for cand in chunk:
                    cfg = BattleConfig(
                        attacker=attacker, defender=cand,
                        rng_mode=RNGMode.EXPECTED,
                        fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                        is_solo_attack=is_solo_attack,
                    )
                    try:
                        _push_screened(run_battle(cfg).score, cand)
                    except Exception:
                        pass
        else:
            for cand in chunk:
                cfg = BattleConfig(
                    attacker=attacker, defender=cand,
                    rng_mode=RNGMode.EXPECTED,
                    fatigue_enabled=fatigue_enabled, max_rounds=max_rounds,
                    is_solo_attack=is_solo_attack,
                )
                try:
                    _push_screened(run_battle(cfg).score, cand)
                except Exception:
                    pass
        n_done += len(chunk)
        if progress:
            progress(n_done, n_candidates)
        chunk.clear()

    try:
        for cand in enumerate_candidates(space):
            chunk.append(cand)
            if len(chunk) >= screen_chunk_size:
                _flush_chunk()
        _flush_chunk()
    except SearchCancelled:
        cancelled = True

    top_screened: list[tuple[float, Fighter]] = sorted(
        ((-neg, c) for (neg, _, c) in top_heap),
        key=lambda x: x[0],
    )
    top_heap.clear()

    refined: list[RankingEntry] = []
    if mc_trials > 0 and not cancelled:
        for exp_score, cand in top_screened:
            if progress:
                try:
                    progress(n_done, n_candidates)
                except SearchCancelled:
                    cancelled = True
                    break
            cfg = BattleConfig(
                attacker=attacker,
                defender=cand,
                rng_mode=RNGMode.STOCHASTIC,
                fatigue_enabled=fatigue_enabled,
                max_rounds=max_rounds,
                is_solo_attack=is_solo_attack,
            )
            mc = run_monte_carlo(cfg, n_trials=mc_trials, seed=mc_seed, keep_scores=False)
            refined.append(RankingEntry(
                rank=0,
                attacker=cand,
                expected_score=exp_score,
                mc=mc,
            ))
        if refined and refined[0].mc is not None:
            refined.sort(key=lambda e: e.mc.score_median)
    else:
        for exp_score, cand in top_screened:
            refined.append(RankingEntry(
                rank=0,
                attacker=cand,
                expected_score=exp_score,
                mc=None,
            ))
        refined.sort(key=lambda e: e.expected_score)

    for i, e in enumerate(refined[:top_k], start=1):
        e.rank = i

    n_mc_refined = sum(1 for e in refined if e.mc is not None)
    n_battles = n_screened_total + n_mc_refined * mc_trials

    elapsed = time.time() - t0
    return BestDefenseReport(
        attacker_label=attacker.label,
        n_candidates=n_candidates,
        n_screened=n_screened_total,
        n_refined=len(refined),
        n_battles=n_battles,
        elapsed_s=elapsed,
        top_k=refined[:top_k],
        cancelled=cancelled,
    )


__all__ = [
    "find_best_counter", "BestCounterReport",
    "find_best_defender", "BestDefenseReport",
    "RankingEntry",
    "SearchCancelled",
]
