from __future__ import annotations
import math
from collections import defaultdict

from ..domain.enums import SquadType, RNGMode, counters as type_counters
from ..data.reference import (
    DAMAGE_DIVISOR,
    cavalry_bypass_rate as _cavalry_bypass_rate,
    archer_volley_rate as _archer_volley_rate,
    type_bonus_pct as _type_bonus_pct,
    fatigue_per_round as _fatigue_per_round,
)
from .state import FighterState, SquadState, RoundResult, TimedEffect
from .resolver import collect_active_effects, compute_skill_mod
from .section_d import section_d_factor


def compute_damage(
    attacker_state: FighterState,
    attacker_squad: SquadType,
    defender_state: FighterState,
    defender_squad: SquadType,
    army_min: int,
    round_idx: int,
    attacker_effects: list,
    defender_effects: list,
    fatigue_enabled: bool = True,
    extra_damage_up_pct: float = 0.0,
    troop_mult_override: float | None = None,
) -> float:
    sq_a = attacker_state.squad(attacker_squad)
    sq_d = defender_state.squad(defender_squad)

    if sq_a.count <= 0 or sq_d.count <= 0:
        return 0.0

    army_factor = math.sqrt(sq_a.count * army_min)

    sd_atk = section_d_factor(attacker_state.buffs, defender_state.buffs, "atk")
    sd_let = section_d_factor(attacker_state.buffs, defender_state.buffs, "let")
    sd_def = section_d_factor(defender_state.buffs, attacker_state.buffs, "def")
    sd_hp  = section_d_factor(defender_state.buffs, attacker_state.buffs, "hp")

    eff_atk = sq_a.atk_factor * sd_atk
    eff_let = sq_a.let_factor * sd_let
    eff_def = sq_d.def_factor * sd_def
    eff_hp  = sq_d.hp_factor  * sd_hp

    att_per_troop = sq_a.base_atk * eff_atk * sq_a.base_let * eff_let / 100.0
    def_per_troop = sq_d.base_def * eff_def * sq_d.base_hp  * eff_hp  / 100.0

    if def_per_troop <= 0:
        return 0.0

    type_bonus = 1.0 + (_type_bonus_pct() / 100.0) if type_counters(attacker_squad, defender_squad) else 1.0

    skill_mod = compute_skill_mod(attacker_effects, defender_effects, attacker_squad, sq_d)
    if extra_damage_up_pct != 0.0:
        skill_mod *= (1.0 + extra_damage_up_pct / 100.0)

    if troop_mult_override is not None:
        troop_mult = troop_mult_override
    else:
        from ..data.troop_skills import (
            troop_skill_outgoing_mult, troop_skill_incoming_mult,
        )
        tg_out = troop_skill_outgoing_mult(attacker_squad, sq_a.dominant_tg)
        tg_in  = troop_skill_incoming_mult(defender_squad, sq_d.dominant_tg)
        troop_mult = tg_out * tg_in

    fatigue = (1.0 - round_idx * _fatigue_per_round()) if fatigue_enabled else 1.0
    if fatigue < 0:
        fatigue = 0.0

    return army_factor * att_per_troop / def_per_troop * type_bonus * skill_mod * troop_mult * fatigue / DAMAGE_DIVISOR


def _default_target(defender_state: FighterState) -> SquadType | None:
    for t in [SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER]:
        if defender_state.squad(t).count > 0:
            return t
    return None


def resolve_target_expected(
    attacker_squad: SquadType,
    defender_state: FighterState,
) -> list[tuple[SquadType, float]]:
    default = _default_target(defender_state)
    if default is None:
        return []
    if attacker_squad == SquadType.CAVALRY and default != SquadType.ARCHER:
        if defender_state.squad(SquadType.ARCHER).count > 0:
            bypass = _cavalry_bypass_rate()
            return [
                (default, 1.0 - bypass),
                (SquadType.ARCHER, bypass),
            ]
    return [(default, 1.0)]


def resolve_target_stochastic(
    attacker_squad: SquadType,
    defender_state: FighterState,
    rng,
) -> SquadType | None:
    from .stochastic import roll_cavalry_bypass
    default = _default_target(defender_state)
    if default is None:
        return None
    if attacker_squad == SquadType.CAVALRY and default != SquadType.ARCHER:
        if defender_state.squad(SquadType.ARCHER).count > 0:
            if roll_cavalry_bypass(rng, _cavalry_bypass_rate()):
                return SquadType.ARCHER
    return default


def _volley_factor_expected(att_squad: SquadType) -> float:
    return 1.0 + _archer_volley_rate() if att_squad == SquadType.ARCHER else 1.0


def _volley_factor_stochastic(att_squad: SquadType, rng) -> float:
    from .stochastic import roll_archer_volley
    return roll_archer_volley(rng, _archer_volley_rate()) if att_squad == SquadType.ARCHER else 1.0


def run_round(
    attacker: FighterState,
    defender: FighterState,
    army_min: int,
    round_idx: int,
    rng_mode: RNGMode = RNGMode.EXPECTED,
    fatigue_enabled: bool = True,
    rng=None,
) -> RoundResult:
    if rng_mode == RNGMode.STOCHASTIC and rng is None:
        raise ValueError("STOCHASTIC mode requires a BattleRng instance")

    att_terror_map = {st: defender.squad(st).terror_remaining_rounds > 0 for st in SquadType.all()}
    def_terror_map = {st: attacker.squad(st).terror_remaining_rounds > 0 for st in SquadType.all()}

    att_new_timed: list[TimedEffect] = []
    def_new_timed: list[TimedEffect] = []
    att_effects = collect_active_effects(
        attacker, round_idx, rng_mode, target_terror_map=att_terror_map,
        rng=rng, out_new_timed=att_new_timed,
    )
    def_effects = collect_active_effects(
        defender, round_idx, rng_mode, target_terror_map=def_terror_map,
        rng=rng, out_new_timed=def_new_timed,
    )

    kills_on_def: dict[SquadType, float] = {st: 0.0 for st in SquadType.all()}
    kills_on_att: dict[SquadType, float] = {st: 0.0 for st in SquadType.all()}

    if rng_mode == RNGMode.STOCHASTIC:
        _resolve_attacks_stochastic(
            attacker, defender, army_min, round_idx, fatigue_enabled,
            att_effects, def_effects, rng, kills_on_def,
        )
        _resolve_attacks_stochastic(
            defender, attacker, army_min, round_idx, fatigue_enabled,
            def_effects, att_effects, rng, kills_on_att,
        )
    else:
        _resolve_attacks_expected(
            attacker, defender, army_min, round_idx, fatigue_enabled,
            att_effects, def_effects, kills_on_def,
        )
        _resolve_attacks_expected(
            defender, attacker, army_min, round_idx, fatigue_enabled,
            def_effects, att_effects, kills_on_att,
        )

    attacker.active_timed.extend(att_new_timed)
    defender.active_timed.extend(def_new_timed)

    res = RoundResult(round_idx=round_idx)
    for st in SquadType.all():
        if kills_on_def[st] > 0:
            d = math.ceil(kills_on_def[st])
            d = min(d, defender.squad(st).count)
            res.kills_on_defender[st] = d
        if kills_on_att[st] > 0:
            d = math.ceil(kills_on_att[st])
            d = min(d, attacker.squad(st).count)
            res.kills_on_attacker[st] = d

    return res


def _resolve_attacks_expected(
    attacker: FighterState,
    defender: FighterState,
    army_min: int,
    round_idx: int,
    fatigue_enabled: bool,
    att_effects: list,
    def_effects: list,
    out_kills: dict[SquadType, float],
) -> None:
    for asq in SquadType.all():
        if attacker.squad(asq).count <= 0:
            continue
        targets = resolve_target_expected(asq, defender)
        if not targets:
            continue
        volley = _volley_factor_expected(asq)
        for tgt, frac in targets:
            dmg = compute_damage(
                attacker, asq, defender, tgt, army_min, round_idx,
                att_effects, def_effects, fatigue_enabled,
            )
            if defender.dodge_chance > 0:
                dmg *= (1.0 - defender.dodge_chance)
            out_kills[tgt] += dmg * frac * volley


def _resolve_attacks_stochastic(
    attacker: FighterState,
    defender: FighterState,
    army_min: int,
    round_idx: int,
    fatigue_enabled: bool,
    att_effects: list,
    def_effects: list,
    rng,
    out_kills: dict[SquadType, float],
) -> None:
    from .stochastic import (
        roll_dodge,
        roll_petra_evil_eye_on_target,
        roll_per_attack_special_effects,
        roll_sophia_terror_application,
    )
    from ..data.troop_skills import roll_tg_outgoing, roll_tg_incoming

    att_tg_out = {sq: roll_tg_outgoing(rng, sq, attacker.squad(sq).dominant_tg)
                  for sq in SquadType.all()}
    def_tg_in  = {sq: roll_tg_incoming(rng, sq, defender.squad(sq).dominant_tg)
                  for sq in SquadType.all()}

    for asq in SquadType.all():
        if attacker.squad(asq).count <= 0:
            continue
        tgt = resolve_target_stochastic(asq, defender, rng)
        if tgt is None:
            continue
        target_squad = defender.squad(tgt)

        roll_petra_evil_eye_on_target(attacker, target_squad, rng)
        terror_extras = roll_sophia_terror_application(attacker, asq, target_squad, rng)
        per_attack_buffs = roll_per_attack_special_effects(attacker, asq, rng) + terror_extras

        extra_pct = 0.0
        if per_attack_buffs:
            by_op: dict[int, float] = defaultdict(float)
            for e in per_attack_buffs:
                if asq in e.target_squads:
                    by_op[e.op] += e.value
            factor = 1.0
            for v in by_op.values():
                factor *= (1.0 + v / 100.0)
            extra_pct = (factor - 1.0) * 100.0

        volley = _volley_factor_stochastic(asq, rng)

        if defender.dodge_chance > 0 and roll_dodge(rng, defender.dodge_chance):
            continue

        troop_mult = att_tg_out[asq] * def_tg_in[tgt]

        dmg = compute_damage(
            attacker, asq, defender, tgt, army_min, round_idx,
            att_effects, def_effects, fatigue_enabled,
            extra_damage_up_pct=extra_pct,
            troop_mult_override=troop_mult,
        )
        out_kills[tgt] += dmg * volley


def apply_round_kills(state: FighterState, kills: dict[SquadType, int]) -> None:
    for st, k in kills.items():
        sq = state.squad(st)
        sq.count = max(0, sq.count - k)


def tick_timed_effects(state: FighterState) -> None:
    state.active_timed = [
        TimedEffect(skill=te.skill, remaining_rounds=te.remaining_rounds - 1)
        for te in state.active_timed
        if te.remaining_rounds > 1
    ]


def reset_transient_debuffs(state: FighterState) -> None:
    for sq in state.squads.values():
        sq.transient_opp_def_down_pct = 0.0
        if sq.terror_remaining_rounds > 0:
            sq.terror_remaining_rounds -= 1


def resolve_target(asq, defender_state, rng_mode):
    return resolve_target_expected(asq, defender_state)


__all__ = [
    "compute_damage",
    "resolve_target_expected",
    "resolve_target_stochastic",
    "resolve_target",
    "run_round",
    "apply_round_kills",
    "tick_timed_effects",
    "reset_transient_debuffs",
]
