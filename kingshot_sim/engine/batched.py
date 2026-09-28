from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from ..config.fighter import Fighter
from ..config.buffs import Buffs
from ..domain.enums import SquadType, Family, RNGMode, OP_TO_FAMILY, counters as type_counters
from ..data.reference import (
    BASE_LETHALITY, BASE_DEFENSE,
    DAMAGE_DIVISOR,
    cavalry_bypass_rate as _cavalry_bypass_rate,
    archer_volley_rate as _archer_volley_rate,
    type_bonus_pct as _type_bonus_pct,
    fatigue_per_round as _fatigue_per_round,
)
from .compile import compile_fighter
from .resolver import collect_active_effects
from .section_d import LAYERS, STATS, own_pct, enemy_down_pct


_N_LAYERS = len(LAYERS)


def _section_d_pct_arrays(buffs: Buffs) -> tuple[np.ndarray, np.ndarray]:
    own = np.zeros((4, _N_LAYERS), dtype=np.float64)
    enemy = np.zeros((4, _N_LAYERS), dtype=np.float64)
    for s_idx, stat in enumerate(STATS):
        for l_idx, layer in enumerate(LAYERS):
            own[s_idx, l_idx] = own_pct(buffs, stat, layer)
            enemy[s_idx, l_idx] = enemy_down_pct(buffs, stat, layer)
    return own, enemy


_SQUADS: tuple[SquadType, SquadType, SquadType] = tuple(SquadType.all())
INF, CAV, ARC = 0, 1, 2


def _build_type_bonus_matrix() -> np.ndarray:
    M = np.ones((3, 3), dtype=np.float64)
    bonus = 1.0 + _type_bonus_pct() / 100.0
    for asq_i, asq in enumerate(_SQUADS):
        for dsq_i, dsq in enumerate(_SQUADS):
            if type_counters(asq, dsq):
                M[asq_i, dsq_i] = bonus
    return M


def _build_volley_factors() -> np.ndarray:
    return np.array([1.0, 1.0, 1.0 + _archer_volley_rate()], dtype=np.float64)


@dataclass
class _SideArrays:
    base_atk:      np.ndarray
    base_hp:       np.ndarray
    atk_factor:    np.ndarray
    let_factor:    np.ndarray
    def_factor:    np.ndarray
    hp_factor:     np.ndarray
    initial_count: np.ndarray
    damage_up:        np.ndarray
    defense_up:       np.ndarray
    opp_damage_down:  np.ndarray
    opp_defense_down: np.ndarray
    dodge_chance:     np.ndarray
    troop_outgoing_mult: np.ndarray
    troop_incoming_mult: np.ndarray
    own_pct_all:        np.ndarray
    enemy_down_pct_all: np.ndarray


def _compile_side_arrays(fighter: Fighter, side: str) -> _SideArrays:
    fs = compile_fighter(fighter, side=side)

    base_atk = np.array([fs.squad(s).base_atk for s in _SQUADS], dtype=np.float64)
    base_hp  = np.array([fs.squad(s).base_hp  for s in _SQUADS], dtype=np.float64)
    atk_f    = np.array([fs.squad(s).atk_factor for s in _SQUADS], dtype=np.float64)
    let_f    = np.array([fs.squad(s).let_factor for s in _SQUADS], dtype=np.float64)
    def_f    = np.array([fs.squad(s).def_factor for s in _SQUADS], dtype=np.float64)
    hp_f     = np.array([fs.squad(s).hp_factor  for s in _SQUADS], dtype=np.float64)
    init_n   = np.array([fs.squad(s).count for s in _SQUADS], dtype=np.int64)

    effects = collect_active_effects(fs, round_idx=0, rng_mode=RNGMode.EXPECTED)

    def aggregate_per_pair(family: Family, is_attacker_side: bool) -> np.ndarray:
        is_dual_semantic = family in (Family.OPP_DAMAGE_DOWN, Family.OPP_DEFENSE_DOWN)
        out = np.empty((3, 3), dtype=np.float64)
        for asq_i, asq in enumerate(_SQUADS):
            for dsq_i, dsq in enumerate(_SQUADS):
                if is_attacker_side:
                    own_sq, enemy_sq = asq, dsq
                else:
                    own_sq, enemy_sq = dsq, asq
                by_op: dict[int, float] = {}
                for e in effects:
                    if OP_TO_FAMILY.get(e.op) is not family:
                        continue
                    ts_target = enemy_sq if is_dual_semantic else own_sq
                    if ts_target not in e.target_squads:
                        continue
                    if e.target_enemy_squads and enemy_sq not in e.target_enemy_squads:
                        continue
                    by_op[e.op] = by_op.get(e.op, 0.0) + e.value
                factor = 1.0
                for v in by_op.values():
                    factor *= (1.0 + v / 100.0)
                out[asq_i, dsq_i] = factor
        return out

    dmg_up   = aggregate_per_pair(Family.DAMAGE_UP,        is_attacker_side=True)
    opp_def  = aggregate_per_pair(Family.OPP_DEFENSE_DOWN, is_attacker_side=True)
    def_up   = aggregate_per_pair(Family.DEFENSE_UP,       is_attacker_side=False)
    opp_dmg  = aggregate_per_pair(Family.OPP_DAMAGE_DOWN,  is_attacker_side=False)

    own_all, enemy_all = _section_d_pct_arrays(fs.buffs)

    from ..data.troop_skills import (
        troop_skill_outgoing_mult, troop_skill_incoming_mult,
    )
    troop_out = np.array([troop_skill_outgoing_mult(s, fs.squad(s).dominant_tg)
                          for s in _SQUADS], dtype=np.float64)
    troop_in  = np.array([troop_skill_incoming_mult(s, fs.squad(s).dominant_tg)
                          for s in _SQUADS], dtype=np.float64)

    return _SideArrays(
        base_atk=base_atk.reshape(1, 3),
        base_hp=base_hp.reshape(1, 3),
        atk_factor=atk_f.reshape(1, 3),
        let_factor=let_f.reshape(1, 3),
        def_factor=def_f.reshape(1, 3),
        hp_factor=hp_f.reshape(1, 3),
        initial_count=init_n.reshape(1, 3),
        damage_up=dmg_up.reshape(1, 3, 3),
        defense_up=def_up.reshape(1, 3, 3),
        opp_damage_down=opp_dmg.reshape(1, 3, 3),
        opp_defense_down=opp_def.reshape(1, 3, 3),
        dodge_chance=np.array([fs.dodge_chance], dtype=np.float64),
        troop_outgoing_mult=troop_out.reshape(1, 3),
        troop_incoming_mult=troop_in.reshape(1, 3),
        own_pct_all=own_all.reshape(1, 4, _N_LAYERS),
        enemy_down_pct_all=enemy_all.reshape(1, 4, _N_LAYERS),
    )


def _compile_cache_key(fighter: Fighter) -> tuple:
    leader_keys = (
        (fighter.leader_inf.hero_name, fighter.leader_inf.level, fighter.leader_inf.widget_level,
         fighter.leader_inf.gear_atk_pct, fighter.leader_inf.gear_def_pct,
         fighter.leader_inf.gear_let_pct, fighter.leader_inf.gear_hp_pct),
        (fighter.leader_cav.hero_name, fighter.leader_cav.level, fighter.leader_cav.widget_level,
         fighter.leader_cav.gear_atk_pct, fighter.leader_cav.gear_def_pct,
         fighter.leader_cav.gear_let_pct, fighter.leader_cav.gear_hp_pct),
        (fighter.leader_arc.hero_name, fighter.leader_arc.level, fighter.leader_arc.widget_level,
         fighter.leader_arc.gear_atk_pct, fighter.leader_arc.gear_def_pct,
         fighter.leader_arc.gear_let_pct, fighter.leader_arc.gear_hp_pct),
    )
    joiner_keys = tuple(sorted((j.hero_name, j.level) for j in fighter.joiners))
    bonus = fighter.bonuses
    bonus_key = (
        bonus.squad_atk_pct, bonus.squad_def_pct, bonus.squad_let_pct, bonus.squad_hp_pct,
        bonus.inf_atk_pct, bonus.inf_def_pct, bonus.inf_let_pct, bonus.inf_hp_pct,
        bonus.cav_atk_pct, bonus.cav_def_pct, bonus.cav_let_pct, bonus.cav_hp_pct,
        bonus.arc_atk_pct, bonus.arc_def_pct, bonus.arc_let_pct, bonus.arc_hp_pct,
    )
    def _tier_key(groups):
        return (groups[0].tier, groups[0].level) if groups else None
    inf_tier = _tier_key(fighter.troops.infantry)
    cav_tier = _tier_key(fighter.troops.cavalry)
    arc_tier = _tier_key(fighter.troops.archer)
    return (leader_keys, joiner_keys, bonus_key, inf_tier, cav_tier, arc_tier)


def _compile_side_arrays_cached(fighter: Fighter, side: str, cache: dict) -> _SideArrays:
    key = (side, _compile_cache_key(fighter))
    cached = cache.get(key)
    if cached is None:
        cached = _compile_side_arrays(fighter, side)
        cache[key] = cached

    count = np.array(
        [fighter.troops.squad_count(s) for s in _SQUADS],
        dtype=np.int64,
    ).reshape(1, 3)

    return _SideArrays(
        base_atk=cached.base_atk,
        base_hp=cached.base_hp,
        atk_factor=cached.atk_factor,
        let_factor=cached.let_factor,
        def_factor=cached.def_factor,
        hp_factor=cached.hp_factor,
        initial_count=count,
        damage_up=cached.damage_up,
        defense_up=cached.defense_up,
        opp_damage_down=cached.opp_damage_down,
        opp_defense_down=cached.opp_defense_down,
        dodge_chance=cached.dodge_chance,
        troop_outgoing_mult=cached.troop_outgoing_mult,
        troop_incoming_mult=cached.troop_incoming_mult,
        own_pct_all=cached.own_pct_all,
        enemy_down_pct_all=cached.enemy_down_pct_all,
    )


def _stack_sides(sides: Sequence[_SideArrays]) -> _SideArrays:
    cat = lambda field: np.concatenate([getattr(s, field) for s in sides], axis=0)
    cat1 = lambda field: np.concatenate([getattr(s, field) for s in sides], axis=0)
    return _SideArrays(
        base_atk=cat("base_atk"),
        base_hp=cat("base_hp"),
        atk_factor=cat("atk_factor"),
        let_factor=cat("let_factor"),
        def_factor=cat("def_factor"),
        hp_factor=cat("hp_factor"),
        initial_count=cat("initial_count"),
        damage_up=cat("damage_up"),
        defense_up=cat("defense_up"),
        opp_damage_down=cat("opp_damage_down"),
        opp_defense_down=cat("opp_defense_down"),
        dodge_chance=cat1("dodge_chance"),
        troop_outgoing_mult=cat("troop_outgoing_mult"),
        troop_incoming_mult=cat("troop_incoming_mult"),
        own_pct_all=cat("own_pct_all"),
        enemy_down_pct_all=cat("enemy_down_pct_all"),
    )


def _att_per_troop(side: _SideArrays) -> np.ndarray:
    return side.base_atk * side.atk_factor * BASE_LETHALITY * side.let_factor / 100.0


def _def_per_troop(side: _SideArrays) -> np.ndarray:
    raw = BASE_DEFENSE * side.def_factor * side.base_hp * side.hp_factor / 100.0
    return np.maximum(raw, 1e-9)


def _skill_mod_pair(att: _SideArrays, dfn: _SideArrays) -> np.ndarray:
    num = att.damage_up * att.opp_defense_down
    den = dfn.opp_damage_down * dfn.defense_up
    den = np.where(den <= 0, 1e-9, den)
    skill_mod = num / den
    troop_mult = att.troop_outgoing_mult[:, :, None] * dfn.troop_incoming_mult[:, None, :]
    return skill_mod * troop_mult


def _build_target_pmf(alive: np.ndarray, cavalry_bypass: float) -> np.ndarray:
    N = alive.shape[0]
    pmf = np.zeros((N, 3, 3), dtype=np.float64)

    has_any = alive.any(axis=1)
    default = alive.argmax(axis=1)
    default_safe = np.where(has_any, default, 0)

    idx = np.arange(N)
    pmf[idx, INF, default_safe] = has_any.astype(np.float64)
    pmf[idx, ARC, default_safe] = has_any.astype(np.float64)

    arc_alive = alive[:, ARC]
    default_is_arc = (default == ARC)
    bypass_active = has_any & ~default_is_arc & arc_alive
    no_bypass     = has_any & ~bypass_active

    pmf[idx, CAV, default_safe] = np.where(bypass_active, 1.0 - cavalry_bypass, no_bypass.astype(np.float64))
    pmf[bypass_active, CAV, ARC] = cavalry_bypass
    return pmf


@dataclass
class BatchedExpectedResult:
    score: np.ndarray
    rounds_elapsed: np.ndarray
    attacker_final: np.ndarray
    defender_final: np.ndarray
    winner_code: np.ndarray


def _run_loop_core(
    att: _SideArrays,
    dfn: _SideArrays,
    fatigue_enabled: bool,
    max_rounds: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    N = att.initial_count.shape[0]

    _type_bonus_matrix = _build_type_bonus_matrix()
    _volley = _build_volley_factors()
    _cavalry_bypass = _cavalry_bypass_rate()
    _fatigue = _fatigue_per_round()

    att_apt = _att_per_troop(att)
    att_dpt = _def_per_troop(att)
    dfn_apt = _att_per_troop(dfn)
    dfn_dpt = _def_per_troop(dfn)

    net_att = att.own_pct_all - dfn.enemy_down_pct_all
    net_def = dfn.own_pct_all - att.enemy_down_pct_all
    factor_att = np.prod(1.0 + net_att / 100.0, axis=2)
    factor_def = np.prod(1.0 + net_def / 100.0, axis=2)
    factor_att = np.maximum(factor_att, 0.0)
    factor_def = np.maximum(factor_def, 0.0)

    _AT, _DF, _LE, _HP = 0, 1, 2, 3
    att_apt = att_apt * factor_att[:, _AT][:, None] * factor_att[:, _LE][:, None]
    att_dpt = att_dpt * factor_att[:, _DF][:, None] * factor_att[:, _HP][:, None]
    dfn_apt = dfn_apt * factor_def[:, _AT][:, None] * factor_def[:, _LE][:, None]
    dfn_dpt = dfn_dpt * factor_def[:, _DF][:, None] * factor_def[:, _HP][:, None]

    skill_mod_att_to_def = _skill_mod_pair(att, dfn)
    skill_mod_def_to_att = _skill_mod_pair(dfn, att)

    att_total_init = att.initial_count.sum(axis=1).astype(np.float64)
    dfn_total_init = dfn.initial_count.sum(axis=1).astype(np.float64)
    army_min = np.minimum(att_total_init, dfn_total_init)

    att_dodge_factor = (1.0 - att.dodge_chance)[:, None]
    dfn_dodge_factor = (1.0 - dfn.dodge_chance)[:, None]

    att_count = att.initial_count.copy().astype(np.float64)
    dfn_count = dfn.initial_count.copy().astype(np.float64)
    rounds_elapsed = np.zeros(N, dtype=np.int64)
    done = (att_count.sum(axis=1) <= 0) | (dfn_count.sum(axis=1) <= 0)

    damage_a2d = np.empty((N, 3, 3), dtype=np.float64)
    damage_d2a = np.empty((N, 3, 3), dtype=np.float64)
    type_bonus_3x3 = _type_bonus_matrix[None, :, :]
    volley_1x3x1   = _volley[None, :, None]

    for round_idx in range(max_rounds):
        active = ~done
        if not active.any():
            break

        att_alive = (att_count > 0)
        dfn_alive = (dfn_count > 0)
        att_target_pmf = _build_target_pmf(dfn_alive, _cavalry_bypass)
        def_target_pmf = _build_target_pmf(att_alive, _cavalry_bypass)

        att_army_factor = np.sqrt(np.maximum(att_count * army_min[:, None], 0.0))
        np.divide(
            (att_army_factor * att_apt)[:, :, None],
            dfn_dpt[:, None, :],
            out=damage_a2d,
        )
        np.multiply(damage_a2d, type_bonus_3x3,        out=damage_a2d)
        np.multiply(damage_a2d, skill_mod_att_to_def,  out=damage_a2d)
        np.multiply(damage_a2d, volley_1x3x1,          out=damage_a2d)
        np.multiply(damage_a2d, att_target_pmf,        out=damage_a2d)
        np.multiply(damage_a2d, dfn_dodge_factor[:, :, None], out=damage_a2d)
        if fatigue_enabled:
            damage_a2d *= max(0.0, 1.0 - round_idx * _fatigue)
        damage_a2d /= DAMAGE_DIVISOR
        dmg_on_def = damage_a2d.sum(axis=1)

        def_army_factor = np.sqrt(np.maximum(dfn_count * army_min[:, None], 0.0))
        np.divide(
            (def_army_factor * dfn_apt)[:, :, None],
            att_dpt[:, None, :],
            out=damage_d2a,
        )
        np.multiply(damage_d2a, type_bonus_3x3,        out=damage_d2a)
        np.multiply(damage_d2a, skill_mod_def_to_att,  out=damage_d2a)
        np.multiply(damage_d2a, volley_1x3x1,          out=damage_d2a)
        np.multiply(damage_d2a, def_target_pmf,        out=damage_d2a)
        np.multiply(damage_d2a, att_dodge_factor[:, :, None], out=damage_d2a)
        if fatigue_enabled:
            damage_d2a *= max(0.0, 1.0 - round_idx * _fatigue)
        damage_d2a /= DAMAGE_DIVISOR
        dmg_on_att = damage_d2a.sum(axis=1)

        kills_def = np.minimum(np.ceil(dmg_on_def), dfn_count).astype(np.int64)
        kills_att = np.minimum(np.ceil(dmg_on_att), att_count).astype(np.int64)
        kills_def[done] = 0
        kills_att[done] = 0

        dfn_count = np.maximum(dfn_count - kills_def, 0.0)
        att_count = np.maximum(att_count - kills_att, 0.0)

        rounds_elapsed[active] += 1

        att_total = att_count.sum(axis=1)
        def_total = dfn_count.sum(axis=1)
        done = done | (att_total <= 0) | (def_total <= 0)

    return att_count, dfn_count, rounds_elapsed, att_total_init, dfn_total_init


def _build_result(
    att_count: np.ndarray,
    dfn_count: np.ndarray,
    rounds_elapsed: np.ndarray,
    att_initial: np.ndarray,
    dfn_initial: np.ndarray,
    att_total_init: np.ndarray,
    dfn_total_init: np.ndarray,
) -> "BatchedExpectedResult":
    att_lost = (att_initial - att_count.astype(np.int64)).sum(axis=1)
    def_lost = (dfn_initial - dfn_count.astype(np.int64)).sum(axis=1)
    att_tot = np.maximum(att_total_init, 1.0)
    dfn_tot = np.maximum(dfn_total_init, 1.0)
    score = def_lost / dfn_tot - att_lost / att_tot

    att_alive_final = att_count.sum(axis=1) > 0
    def_alive_final = dfn_count.sum(axis=1) > 0
    winner = np.where(
        ~att_alive_final & def_alive_final, 1,
        np.where(att_alive_final & ~def_alive_final, 0, 2),
    ).astype(np.int64)

    return BatchedExpectedResult(
        score=score,
        rounds_elapsed=rounds_elapsed,
        attacker_final=att_count.astype(np.int64),
        defender_final=dfn_count.astype(np.int64),
        winner_code=winner,
    )


def _empty_result() -> "BatchedExpectedResult":
    empty1 = np.zeros((0,), dtype=np.float64)
    empty2 = np.zeros((0, 3), dtype=np.int64)
    return BatchedExpectedResult(
        score=empty1, rounds_elapsed=empty1.astype(np.int64),
        attacker_final=empty2, defender_final=empty2,
        winner_code=np.zeros((0,), dtype=np.int64),
    )


def _tile_to_n(one: _SideArrays, N: int) -> _SideArrays:
    return _SideArrays(
        base_atk=np.tile(one.base_atk, (N, 1)),
        base_hp=np.tile(one.base_hp, (N, 1)),
        atk_factor=np.tile(one.atk_factor, (N, 1)),
        let_factor=np.tile(one.let_factor, (N, 1)),
        def_factor=np.tile(one.def_factor, (N, 1)),
        hp_factor=np.tile(one.hp_factor, (N, 1)),
        initial_count=np.tile(one.initial_count, (N, 1)),
        damage_up=np.tile(one.damage_up, (N, 1, 1)),
        defense_up=np.tile(one.defense_up, (N, 1, 1)),
        opp_damage_down=np.tile(one.opp_damage_down, (N, 1, 1)),
        opp_defense_down=np.tile(one.opp_defense_down, (N, 1, 1)),
        dodge_chance=np.tile(one.dodge_chance, (N,)),
        troop_outgoing_mult=np.tile(one.troop_outgoing_mult, (N, 1)),
        troop_incoming_mult=np.tile(one.troop_incoming_mult, (N, 1)),
        own_pct_all=np.tile(one.own_pct_all, (N, 1, 1)),
        enemy_down_pct_all=np.tile(one.enemy_down_pct_all, (N, 1, 1)),
    )


def run_batch_expected(
    candidates: list[Fighter],
    defender: Fighter,
    fatigue_enabled: bool = True,
    max_rounds: int = 200,
    is_solo_attack: bool = False,
) -> "BatchedExpectedResult":
    N = len(candidates)
    if N == 0:
        return _empty_result()

    compile_cache: dict = {}
    attacker_side = "solo" if is_solo_attack else "rally"
    att_sides = [_compile_side_arrays_cached(c, attacker_side, compile_cache) for c in candidates]
    att = _stack_sides(att_sides)
    att_sides.clear()
    compile_cache.clear()
    del att_sides, compile_cache

    def_one = _compile_side_arrays(defender, side="defender")
    dfn = _tile_to_n(def_one, N)
    del def_one

    final_att, final_dfn, rounds, att_init_tot, dfn_init_tot = _run_loop_core(
        att, dfn, fatigue_enabled, max_rounds
    )
    return _build_result(final_att, final_dfn, rounds,
                         att.initial_count, dfn.initial_count,
                         att_init_tot, dfn_init_tot)


def run_batch_expected_defense(
    candidates: list[Fighter],
    attacker: Fighter,
    fatigue_enabled: bool = True,
    max_rounds: int = 200,
    is_solo_attack: bool = False,
) -> "BatchedExpectedResult":
    N = len(candidates)
    if N == 0:
        return _empty_result()

    compile_cache: dict = {}
    def_sides = [_compile_side_arrays_cached(c, "defender", compile_cache) for c in candidates]
    dfn = _stack_sides(def_sides)
    def_sides.clear()
    compile_cache.clear()
    del def_sides, compile_cache

    attacker_side = "solo" if is_solo_attack else "rally"
    att_one = _compile_side_arrays(attacker, side=attacker_side)
    att = _tile_to_n(att_one, N)
    del att_one

    final_att, final_dfn, rounds, att_init_tot, dfn_init_tot = _run_loop_core(
        att, dfn, fatigue_enabled, max_rounds
    )
    return _build_result(final_att, final_dfn, rounds,
                         att.initial_count, dfn.initial_count,
                         att_init_tot, dfn_init_tot)


__all__ = [
    "BatchedExpectedResult",
    "run_batch_expected",
    "run_batch_expected_defense",
]
