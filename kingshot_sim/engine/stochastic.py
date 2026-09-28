from __future__ import annotations
import random
from typing import Iterable

from ..domain.enums import SquadType, RNGMode, TriggerKind, SkillSpecial
from ..domain.skills import Skill, Effect
from .state import FighterState, SquadState, TimedEffect


class BattleRng:
    __slots__ = ("_rng",)

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def bernoulli(self, p: float) -> bool:
        if p <= 0.0:
            return False
        if p >= 1.0:
            return True
        return self._rng.random() < p

    def random(self) -> float:
        return self._rng.random()


def stochastic_round_effects(
    fstate: FighterState,
    round_idx: int,
    rng: BattleRng,
    target_terror: bool,
) -> tuple[list[Effect], list[TimedEffect]]:
    effects: list[Effect] = []
    new_timed: list[TimedEffect] = []

    for sk in fstate.skills:
        if sk.special == SkillSpecial.CONDITIONAL_TERROR and not target_terror:
            continue

        if sk.special == SkillSpecial.DODGE:
            continue

        trig = sk.trigger
        if trig.kind == TriggerKind.PASSIVE:
            effects.extend(sk.effects)

        elif trig.kind == TriggerKind.RNG_PER_ROUND:
            if rng.bernoulli(trig.chance or 0.0):
                if trig.duration > 1:
                    effects.extend(sk.effects)
                    new_timed.append(TimedEffect(skill=sk, remaining_rounds=trig.duration - 1))
                else:
                    effects.extend(sk.effects)

        elif trig.kind == TriggerKind.RNG_PER_ATTACK:
            pass

        elif trig.kind == TriggerKind.PERIODIC:
            period = trig.period or 1
            offset = trig.period_offset or 0
            if (round_idx % period) == offset:
                effects.extend(sk.effects)
                if trig.duration > 1:
                    new_timed.append(TimedEffect(skill=sk, remaining_rounds=trig.duration - 1))

        elif trig.kind == TriggerKind.PITY:
            sid = id(sk)
            n_failed = fstate.pity_state.get(sid, 0)
            base = trig.chance or 0.0
            eff_chance = min(1.0, base * (1 + n_failed))
            if rng.bernoulli(eff_chance):
                effects.extend(sk.effects)
                fstate.pity_state[sid] = 0
                if trig.duration > 1:
                    new_timed.append(TimedEffect(skill=sk, remaining_rounds=trig.duration - 1))
            else:
                fstate.pity_state[sid] = n_failed + 1

    return effects, new_timed


def roll_cavalry_bypass(rng: BattleRng, bypass_rate: float) -> bool:
    return rng.bernoulli(bypass_rate)


def roll_archer_volley(rng: BattleRng, volley_rate: float) -> float:
    return 2.0 if rng.bernoulli(volley_rate) else 1.0


def roll_dodge(rng: BattleRng, dodge_chance: float) -> bool:
    return rng.bernoulli(dodge_chance)


def roll_per_attack_special_effects(
    fstate: FighterState,
    own_squad: SquadType,
    rng: BattleRng,
) -> list[Effect]:
    out: list[Effect] = []
    for sk in fstate.skills:
        if sk.trigger.kind != TriggerKind.RNG_PER_ATTACK:
            continue
        if sk.special == SkillSpecial.TARGET_DEBUFF_ON_HIT:
            continue
        if sk.special == SkillSpecial.APPLY_TERROR_ON_HIT:
            continue
        if not any(own_squad in e.target_squads for e in sk.effects):
            continue
        if rng.bernoulli(sk.trigger.chance or 0.0):
            out.extend(sk.effects)
    return out


def roll_petra_evil_eye_on_target(
    fstate: FighterState,
    target_squad: SquadState,
    rng: BattleRng,
) -> None:
    for sk in fstate.skills:
        if sk.special != SkillSpecial.TARGET_DEBUFF_ON_HIT:
            continue
        if rng.bernoulli(sk.trigger.chance or 0.0):
            for e in sk.effects:
                if e.op == 211:
                    target_squad.transient_opp_def_down_pct += e.value


def roll_sophia_terror_application(
    fstate: FighterState,
    own_squad: SquadType,
    target_squad: SquadState,
    rng: BattleRng,
) -> list[Effect]:
    out: list[Effect] = []
    for sk in fstate.skills:
        if sk.special != SkillSpecial.APPLY_TERROR_ON_HIT:
            continue
        if sk.trigger.kind != TriggerKind.RNG_PER_ATTACK:
            continue
        if not any(own_squad in e.target_squads for e in sk.effects):
            continue
        if rng.bernoulli(sk.trigger.chance or 0.0):
            target_squad.terror_remaining_rounds = max(target_squad.terror_remaining_rounds, 1)
            out.extend(sk.effects)
    return out


__all__ = [
    "BattleRng",
    "stochastic_round_effects",
    "roll_cavalry_bypass",
    "roll_archer_volley",
    "roll_dodge",
    "roll_per_attack_special_effects",
    "roll_petra_evil_eye_on_target",
    "roll_sophia_terror_application",
]
