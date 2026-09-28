from __future__ import annotations
from collections import defaultdict
from typing import Iterable

from ..domain.enums import SquadType, Family, family_for_op
from ..domain.skills import Effect, Skill
from ..domain.enums import TriggerKind, RNGMode, SkillSpecial
from .state import FighterState, SquadState


def aggregate_family(
    effects: Iterable[Effect],
    family: Family,
    target_squad: SquadType,
    enemy_squad: SquadType | None = None,
) -> float:
    by_op: dict[int, float] = defaultdict(float)
    for eff in effects:
        if eff.op == 0:
            continue
        if family_for_op(eff.op) != family:
            continue
        if target_squad not in eff.target_squads:
            continue
        if eff.target_enemy_squads:
            if enemy_squad is None or enemy_squad not in eff.target_enemy_squads:
                continue
        by_op[eff.op] += eff.value

    factor = 1.0
    for op_sum in by_op.values():
        factor *= (1.0 + op_sum / 100.0)
    return factor


def _expected_value_effect(
    skill: Skill,
    target_terror_prob: float = 0.0,
) -> list[Effect]:
    trig = skill.trigger
    out: list[Effect] = []

    terror_scale = 1.0
    if skill.special == SkillSpecial.CONDITIONAL_TERROR:
        if target_terror_prob <= 0.0:
            return []
        terror_scale = float(target_terror_prob)

    if trig.kind == TriggerKind.PASSIVE:
        for e in skill.effects:
            if terror_scale != 1.0:
                out.append(Effect(op=e.op, value=e.value * terror_scale,
                                    target_squads=e.target_squads))
            else:
                out.append(e)
    elif trig.kind == TriggerKind.RNG_PER_ROUND:
        p = trig.chance or 0.0
        d = trig.duration or 0
        if d <= 0:
            eff_rate = p
        else:
            eff_rate = 1.0 - (1.0 - p) ** d
        eff_rate *= terror_scale
        for e in skill.effects:
            out.append(Effect(op=e.op, value=e.value * eff_rate,
                                target_squads=e.target_squads))
    elif trig.kind == TriggerKind.RNG_PER_ATTACK:
        p_per_round = trig.chance or 0.0
        d = trig.duration or 0
        k = (len(SquadType.all())
             if skill.special == SkillSpecial.TARGET_DEBUFF_ON_HIT else 1)
        for e in skill.effects:
            if d <= 0:
                eff_rate = 1.0 - (1.0 - p_per_round) ** k
            else:
                eff_rate = 1.0 - (1.0 - p_per_round) ** d
            eff_rate *= terror_scale
            out.append(Effect(op=e.op, value=e.value * eff_rate,
                                target_squads=e.target_squads))
    elif trig.kind == TriggerKind.PERIODIC:
        period = trig.period or 1
        duration = max(trig.duration, 1)
        scale = (duration / period) * terror_scale
        for e in skill.effects:
            out.append(Effect(op=e.op, value=e.value * scale,
                                target_squads=e.target_squads))
    elif trig.kind == TriggerKind.PITY:
        p = trig.chance or 0.0
        eff_rate = _pity_effective_rate(p) * terror_scale
        for e in skill.effects:
            out.append(Effect(op=e.op, value=e.value * eff_rate,
                                target_squads=e.target_squads))

    return out


def _pity_effective_rate(base_chance: float) -> float:
    if base_chance <= 0:
        return 0.0
    if base_chance >= 1.0:
        return 1.0
    survival = 1.0
    expected_length = 0.0
    for k in range(1, 1000):
        p_k = min(k * base_chance, 1.0)
        proc_prob = survival * p_k
        expected_length += k * proc_prob
        survival *= (1.0 - p_k)
        if survival < 1e-12:
            break
    return 1.0 / expected_length if expected_length > 0 else 0.0


def collect_active_effects(
    fstate: FighterState,
    round_idx: int,
    rng_mode: RNGMode,
    target_terror_map: dict[SquadType, bool] | None = None,
    rng=None,
    out_new_timed: list | None = None,
) -> list[Effect]:
    if target_terror_map is None:
        target_terror_map = {st: False for st in SquadType.all()}

    out: list[Effect] = []

    if rng_mode == RNGMode.EXPECTED:
        terror_survive = 1.0
        for sk in fstate.skills:
            if sk.special != SkillSpecial.APPLY_TERROR_ON_HIT:
                continue
            trig = sk.trigger
            if trig.kind != TriggerKind.RNG_PER_ATTACK:
                terror_survive = 0.0
                break
            p_per_attack = trig.chance or 0.0
            n_rolls = max(1, len(sk.effects[0].target_squads)) if sk.effects else 1
            p_per_round = 1.0 - (1.0 - p_per_attack) ** n_rolls
            terror_survive *= (1.0 - p_per_round)
        target_terror_prob = 1.0 - terror_survive

        for sk in fstate.skills:
            if sk.special == SkillSpecial.DODGE:
                continue
            out.extend(_expected_value_effect(sk, target_terror_prob=target_terror_prob))

    elif rng_mode == RNGMode.STOCHASTIC:
        if rng is None:
            raise ValueError("STOCHASTIC mode requires a BattleRng instance")
        from .stochastic import stochastic_round_effects
        any_terror = any(target_terror_map.values())
        rolled, new_timed = stochastic_round_effects(
            fstate, round_idx, rng, target_terror=any_terror
        )
        out.extend(rolled)
        if out_new_timed is not None:
            out_new_timed.extend(new_timed)

    else:
        terror_survive = 1.0
        for sk in fstate.skills:
            if sk.special == SkillSpecial.APPLY_TERROR_ON_HIT:
                trig = sk.trigger
                if trig.kind == TriggerKind.RNG_PER_ATTACK:
                    p = trig.chance or 0.0
                    n = max(1, len(sk.effects[0].target_squads)) if sk.effects else 1
                    terror_survive *= (1.0 - (1.0 - (1.0 - p) ** n))
        target_terror_prob = 1.0 - terror_survive
        for sk in fstate.skills:
            if sk.special == SkillSpecial.DODGE:
                continue
            out.extend(_expected_value_effect(sk, target_terror_prob=target_terror_prob))

    for te in fstate.active_timed:
        out.extend(te.skill.effects)

    return out


def compute_skill_mod(
    attacker_effects: list[Effect],
    defender_effects: list[Effect],
    attacker_squad: SquadType,
    defender_squad: SquadState,
) -> float:
    dsq = defender_squad.squad_type
    dmg_up = aggregate_family(
        attacker_effects, Family.DAMAGE_UP, attacker_squad, enemy_squad=dsq,
    )
    opp_def_down = aggregate_family(
        attacker_effects, Family.OPP_DEFENSE_DOWN, dsq, enemy_squad=dsq,
    )
    def_up = aggregate_family(
        defender_effects, Family.DEFENSE_UP, dsq, enemy_squad=attacker_squad,
    )
    opp_dmg_down = aggregate_family(
        defender_effects, Family.OPP_DAMAGE_DOWN, attacker_squad, enemy_squad=attacker_squad,
    )

    if defender_squad.transient_opp_def_down_pct > 0:
        opp_def_down *= (1.0 + defender_squad.transient_opp_def_down_pct / 100.0)

    denom = opp_dmg_down * def_up
    if denom <= 0:
        denom = 1e-9
    return (dmg_up * opp_def_down) / denom


__all__ = [
    "aggregate_family",
    "collect_active_effects",
    "compute_skill_mod",
    "_pity_effective_rate",
]
