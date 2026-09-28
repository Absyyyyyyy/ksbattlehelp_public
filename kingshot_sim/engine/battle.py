from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..config.fighter import Fighter
from ..domain.enums import SquadType, BattleType, RNGMode
from .compile import compile_fighter
from .state import FighterState, BattleResult
from .round import (
    run_round, apply_round_kills, tick_timed_effects, reset_transient_debuffs,
)


@dataclass
class BattleConfig:
    attacker: Fighter
    defender: Fighter
    battle_type: BattleType = BattleType.RALLY_VS_GARRISON
    rng_mode: RNGMode = RNGMode.EXPECTED
    seed: Optional[int] = None
    fatigue_enabled: bool = True
    max_rounds: int = 9999
    is_solo_attack: bool = False


def run_battle(config: BattleConfig) -> BattleResult:
    attacker_side = "solo" if config.is_solo_attack else "rally"
    att_state = compile_fighter(config.attacker, side=attacker_side)
    def_state = compile_fighter(config.defender, side="defender")

    army_min = min(att_state.total_troops(), def_state.total_troops())

    initial_att = {st: att_state.squad(st).count for st in SquadType.all()}
    initial_def = {st: def_state.squad(st).count for st in SquadType.all()}

    rng = None
    if config.rng_mode == RNGMode.STOCHASTIC:
        from .stochastic import BattleRng
        rng = BattleRng(seed=config.seed)

    rounds = []
    round_idx = 0
    while not att_state.is_defeated() and not def_state.is_defeated():
        if round_idx >= config.max_rounds:
            break
        result = run_round(
            att_state, def_state, army_min, round_idx,
            rng_mode=config.rng_mode,
            fatigue_enabled=config.fatigue_enabled,
            rng=rng,
        )
        rounds.append(result)
        apply_round_kills(att_state, result.kills_on_attacker)
        apply_round_kills(def_state, result.kills_on_defender)
        tick_timed_effects(att_state)
        tick_timed_effects(def_state)
        reset_transient_debuffs(att_state)
        reset_transient_debuffs(def_state)
        round_idx += 1

    final_att = {st: att_state.squad(st).count for st in SquadType.all()}
    final_def = {st: def_state.squad(st).count for st in SquadType.all()}

    if att_state.is_defeated() and def_state.is_defeated():
        winner = None
    elif att_state.is_defeated():
        winner = "defender"
    elif def_state.is_defeated():
        winner = "attacker"
    else:
        winner = None

    att_lost = sum(initial_att[st] - final_att[st] for st in SquadType.all())
    def_lost = sum(initial_def[st] - final_def[st] for st in SquadType.all())
    att_total = max(att_state.initial_total(), 1)
    def_total = max(def_state.initial_total(), 1)
    score = def_lost / def_total - att_lost / att_total

    return BattleResult(
        rounds=rounds,
        attacker_initial=initial_att,
        defender_initial=initial_def,
        attacker_final=final_att,
        defender_final=final_def,
        winner=winner,
        score=score,
    )


__all__ = ["BattleConfig", "run_battle"]
