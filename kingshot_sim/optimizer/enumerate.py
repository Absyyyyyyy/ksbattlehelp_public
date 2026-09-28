from __future__ import annotations
from itertools import combinations_with_replacement
from typing import Iterator, Sequence

from ..config.fighter import (
    Fighter, BonusVector, TroopRoster, JoinerHero, LeaderHero,
)
from ..data.catalog import get_hero_skills
from ..domain.heroes import Hero
from .search_space import SearchSpace


def _joiner_first_skill_signature(hero_name: str, level: str) -> tuple:
    skills = get_hero_skills(Hero(name=hero_name, level=level, widget_level=0))
    sk1 = next((s for s in skills if s.slot == "sk1"), None)
    if sk1 is None:
        return ("none",)
    eff_tuple = tuple(
        (e.op, round(e.value, 4), tuple(sorted(s.value for s in e.target_squads)))
        for e in sk1.effects
    )
    trig = sk1.trigger
    return (
        trig.kind.value,
        round(trig.chance or 0.0, 4),
        trig.duration,
        trig.period or 0,
        trig.period_offset or 0,
        eff_tuple,
        sk1.special.value,
    )


def deduplicate_joiner_pool(joiners: Sequence[str], level: str) -> list[str]:
    seen: dict[tuple, str] = {}
    result: list[str] = []
    for h in joiners:
        sig = _joiner_first_skill_signature(h, level)
        if sig not in seen:
            seen[sig] = h
            result.append(h)
    return result


def enumerate_candidates(space: SearchSpace) -> Iterator[Fighter]:
    inf_list = space.available_mythic_inf
    cav_list = space.available_mythic_cav
    arc_list = space.available_mythic_arc
    if not inf_list or not cav_list or not arc_list:
        return

    joiner_pool = deduplicate_joiner_pool(space.available_joiners, space.joiner_level)

    if joiner_pool and space.n_joiners > 0:
        joiner_combos = list(combinations_with_replacement(joiner_pool, space.n_joiners))
    else:
        joiner_combos = [()]

    ratio_grid: list[tuple[float, float, float]] = []
    steps = round(1.0 / space.troop_ratio_step)
    for i in range(steps + 1):
        for c in range(steps + 1):
            inf_pct = i / steps
            cav_pct = c / steps
            arc_pct = 1.0 - inf_pct - cav_pct
            if arc_pct < -1e-9:
                continue
            if inf_pct < space.min_inf_pct - 1e-9:
                continue
            ratio_grid.append((inf_pct, cav_pct, arc_pct))

    counter = 0
    for inf_h in inf_list:
        for cav_h in cav_list:
            for arc_h in arc_list:
                if len({inf_h, cav_h, arc_h}) != 3:
                    continue
                leader_inf = space.build_leader_hero(inf_h)
                leader_cav = space.build_leader_hero(cav_h)
                leader_arc = space.build_leader_hero(arc_h)
                for combo in joiner_combos:
                    joiners = tuple(
                        JoinerHero(hero_name=h, level=space.joiner_level) for h in combo
                    )
                    for inf_pct, cav_pct, arc_pct in ratio_grid:
                        roster = space.troop_pool.build_roster(inf_pct, cav_pct, arc_pct)
                        if roster.total_count() == 0:
                            continue
                        counter += 1
                        label = (f"{space.label_prefix}-{counter}: "
                                 f"{inf_h[:3]}/{cav_h[:3]}/{arc_h[:3]} "
                                 f"({inf_pct:.0%}/{cav_pct:.0%}/{arc_pct:.0%})")
                        yield Fighter(
                            label=label,
                            leader_inf=leader_inf,
                            leader_cav=leader_cav,
                            leader_arc=leader_arc,
                            joiners=joiners,
                            bonuses=space.bonuses,
                            troops=roster,
                            buffs=space.buffs,
                        )


def count_candidates(space: SearchSpace) -> int:
    n_trios = 0
    for inf_h in space.available_mythic_inf:
        for cav_h in space.available_mythic_cav:
            for arc_h in space.available_mythic_arc:
                if len({inf_h, cav_h, arc_h}) == 3:
                    n_trios += 1

    pool = deduplicate_joiner_pool(space.available_joiners, space.joiner_level)
    if pool and space.n_joiners > 0:
        from math import comb
        n_combos = comb(len(pool) + space.n_joiners - 1, space.n_joiners)
    else:
        n_combos = 1

    n_ratios = space.n_ratio_grid_points()
    return n_trios * n_combos * n_ratios


__all__ = [
    "enumerate_candidates",
    "deduplicate_joiner_pool",
    "count_candidates",
    "_joiner_first_skill_signature",
]
