from __future__ import annotations
from collections import defaultdict
from typing import Literal

from ..config.fighter import Fighter, BonusVector, TroopRoster
from ..data.reference import (
    TIER_BASE_STATS, BASE_LETHALITY, BASE_DEFENSE,
    MAX_JOINERS_WITH_SKILL,
    HERO_CLASS,
    tier_stat,
)
from ..domain.enums import SquadType, TriggerKind
from ..domain.skills import Skill
from .state import FighterState, SquadState


def _aggregate_troops(troops: TroopRoster, squad: SquadType) -> tuple[float, float, int]:
    import math
    groups = troops.squad(squad)
    total = sum(g.count for g in groups)
    if total == 0:
        return 0.0, 0.0, 0

    if squad == SquadType.INFANTRY:
        atk_key, hp_key = "inf_atk", "inf_hp"
    elif squad == SquadType.CAVALRY:
        atk_key, hp_key = "cav_atk", "cav_hp"
    else:
        atk_key, hp_key = "arc_atk", "arc_hp"

    log_atk = sum(g.count * math.log(g.base_stat(atk_key)) for g in groups) / total
    log_hp  = sum(g.count * math.log(g.base_stat(hp_key))  for g in groups) / total

    return math.exp(log_atk), math.exp(log_hp), total


def _compute_squad_factors(
    fighter: Fighter,
    squad: SquadType,
) -> tuple[float, float, float, float]:
    bv = fighter.bonuses

    atk_pct = bv.get(squad, "atk")
    def_pct = bv.get(squad, "def")
    let_pct = bv.get(squad, "let")
    hp_pct  = bv.get(squad, "hp")

    leader = fighter.leader_for_class(squad)
    leader_pct = leader.to_hero().leader_atk_def_pct()
    atk_pct += leader_pct
    def_pct += leader_pct

    g_atk, g_def, g_let, g_hp = leader.resolve_gear_contribution()
    atk_pct += g_atk
    def_pct += g_def
    let_pct += g_let
    hp_pct  += g_hp

    widget_let, widget_hp = leader.to_hero().widget_let_hp_bonus()
    let_pct += widget_let
    hp_pct += widget_hp

    appoint = fighter.buffs
    atk_pct += appoint.appoint_additive_pct("atk")
    def_pct += appoint.appoint_additive_pct("def")
    let_pct += appoint.appoint_additive_pct("let")
    hp_pct  += appoint.appoint_additive_pct("hp")

    atk_factor = 1.0 + atk_pct / 100.0
    def_factor = 1.0 + def_pct / 100.0
    let_factor = 1.0 + let_pct / 100.0
    hp_factor  = 1.0 + hp_pct  / 100.0


    return atk_factor, def_factor, let_factor, hp_factor


def _gather_skills(fighter: Fighter, side: str) -> list[Skill]:
    skills: list[Skill] = []

    for leader in fighter.all_leaders():
        hero = leader.to_hero()
        for sk in hero.skills(side):
            if not sk.effects and sk.special.value == "none":
                continue
            skills.append(sk)

    if side == "solo":
        return skills

    n_with_skill = 0
    rng_seen: set[str] = set()

    for joiner in fighter.joiners:
        if n_with_skill >= MAX_JOINERS_WITH_SKILL:
            break
        if not joiner.contributes_skill():
            continue
        first = joiner.to_hero().first_skill()
        if first is None:
            continue
        if not first.is_active_for_side(side):
            continue

        is_rng = first.trigger.kind in (TriggerKind.RNG_PER_ROUND, TriggerKind.RNG_PER_ATTACK)
        if is_rng and joiner.hero_name in rng_seen:
            n_with_skill += 1
            continue

        skills.append(first)
        if is_rng:
            rng_seen.add(joiner.hero_name)
        n_with_skill += 1

    return skills


def compile_fighter(fighter: Fighter, side: Literal["rally", "defender", "solo"]) -> FighterState:
    squads: dict[SquadType, SquadState] = {}

    for sq in SquadType.all():
        atk_factor, def_factor, let_factor, hp_factor = _compute_squad_factors(fighter, sq)
        mean_atk, mean_hp, count = _aggregate_troops(fighter.troops, sq)

        from ..data.troop_skills import (
            dominant_tg as _dominant_tg,
            TG8_INF_DEF_PCT_BONUS, TG8_ARC_ATK_PCT_BONUS,
        )
        dom_tg = _dominant_tg(fighter.troops.squad(sq))
        if dom_tg >= 8 and count > 0:
            if sq == SquadType.INFANTRY:
                def_factor += TG8_INF_DEF_PCT_BONUS / 100.0
            elif sq == SquadType.ARCHER:
                atk_factor += TG8_ARC_ATK_PCT_BONUS / 100.0

        squads[sq] = SquadState(
            squad_type=sq,
            base_atk=mean_atk,
            base_let=BASE_LETHALITY,
            base_def=BASE_DEFENSE,
            base_hp=mean_hp,
            atk_factor=atk_factor,
            let_factor=let_factor,
            def_factor=def_factor,
            hp_factor=hp_factor,
            count=count,
            initial_count=count,
            dominant_tg=dom_tg,
        )

    skills = _gather_skills(fighter, side)

    from ..domain.enums import SkillSpecial
    dodge_chance = 0.0
    for sk in skills:
        if sk.special == SkillSpecial.DODGE:
            for e in sk.effects:
                dodge_chance += e.value / 100.0
    dodge_chance = max(0.0, min(1.0, dodge_chance))

    return FighterState(
        label=fighter.label,
        side=side,
        squads=squads,
        skills=skills,
        dodge_chance=dodge_chance,
        buffs=fighter.buffs,
    )


__all__ = ["compile_fighter"]
