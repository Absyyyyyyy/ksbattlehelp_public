from __future__ import annotations
import copy
from dataclasses import replace

from .rosters import AccountRoster
from ..benchmark.runner import HeroBuild
from ..config.fighter import Fighter, LeaderHero, JoinerHero, TroopRoster
from ..optimizer.search_space import SearchSpace, TroopPool, LeaderSpec
from ..data.reference import (
    MYTHIC_HEROES,
    EPIC_HEROES,
    HERO_CLASS,
    NON_COMBAT_FIRST_SKILL_HEROES,
    default_skill_levels,
    hero_class,
)


def roster_to_search_space(
    roster: AccountRoster,
    base: SearchSpace | None = None,
) -> SearchSpace:
    """Translate an AccountRoster into a SearchSpace.

    - Extracts owned mythic heroes into available_mythic_inf, cav, arc.
    - Extracts eligible combat heroes into available_joiners (excluding NON_COMBAT_FIRST_SKILL_HEROES).
    - Translates builds into leader_specs.
    - Injects class_gear, bonuses, and buffs.
    - Preserves base optimizer settings (troop pool, ratio steps, march cap, min inf pct) if provided.
    """
    # 1. Available mythic leaders per class
    if "Inf" in roster.owned_heroes:
        inf_heroes = [
            h for h in roster.owned_heroes["Inf"]
            if h in MYTHIC_HEROES and HERO_CLASS.get(h) == "Inf"
        ]
    elif base is not None:
        inf_heroes = list(base.available_mythic_inf)
    else:
        inf_heroes = []

    if "Cav" in roster.owned_heroes:
        cav_heroes = [
            h for h in roster.owned_heroes["Cav"]
            if h in MYTHIC_HEROES and HERO_CLASS.get(h) == "Cav"
        ]
    elif base is not None:
        cav_heroes = list(base.available_mythic_cav)
    else:
        cav_heroes = []

    if "Arc" in roster.owned_heroes:
        arc_heroes = [
            h for h in roster.owned_heroes["Arc"]
            if h in MYTHIC_HEROES and HERO_CLASS.get(h) == "Arc"
        ]
    elif base is not None:
        arc_heroes = list(base.available_mythic_arc)
    else:
        arc_heroes = []

    # 2. Available joiners (mythic and epic heroes, excluding non-combat first skill heroes)
    if roster.owned_heroes:
        joiner_heroes: list[str] = []
        for cls in ("Inf", "Cav", "Arc"):
            for h in roster.owned_heroes.get(cls, []):
                if (h in MYTHIC_HEROES or h in EPIC_HEROES) and (
                    h not in NON_COMBAT_FIRST_SKILL_HEROES
                ) and (h not in joiner_heroes):
                    joiner_heroes.append(h)
    elif base is not None:
        joiner_heroes = [
            h for h in base.available_joiners
            if h not in NON_COMBAT_FIRST_SKILL_HEROES
        ]
    else:
        joiner_heroes = []

    # 3. Base optimizer settings
    troop_pool = copy.deepcopy(base.troop_pool) if base is not None else TroopPool()
    troop_ratio_step = base.troop_ratio_step if base is not None else 0.10
    min_inf_pct = base.min_inf_pct if base is not None else 0.30
    n_joiners = base.n_joiners if base is not None else 4
    leader_level = base.leader_level if base is not None else "MAX"
    leader_widget_level = base.leader_widget_level if base is not None else 10
    joiner_level = base.joiner_level if base is not None else "MAX"
    label_prefix = base.label_prefix if base is not None else "Cand"

    # 4. Leader specs
    leader_specs: dict[str, LeaderSpec] = dict(base.leader_specs) if base is not None else {}
    for h, b in roster.builds.items():
        existing_spec = leader_specs.get(h)
        gear_atk = existing_spec.gear_atk_pct if existing_spec else 0.0
        gear_def = existing_spec.gear_def_pct if existing_spec else 0.0
        gear_let = existing_spec.gear_let_pct if existing_spec else 0.0
        gear_hp = existing_spec.gear_hp_pct if existing_spec else 0.0
        leader_specs[h] = LeaderSpec(
            level=b.level,
            widget_level=b.widget_level,
            skill_levels=b.skill_levels,
            gear_atk_pct=gear_atk,
            gear_def_pct=gear_def,
            gear_let_pct=gear_let,
            gear_hp_pct=gear_hp,
        )

    # 5. Class gear, bonuses, buffs
    if roster.class_gear:
        class_gear = {cls: dict(slots) for cls, slots in roster.class_gear.items()}
    elif base is not None and base.class_gear:
        class_gear = {cls: dict(slots) for cls, slots in base.class_gear.items()}
    else:
        class_gear = {}

    bonuses = replace(roster.bonuses)
    buffs = replace(roster.buffs)

    return SearchSpace(
        available_mythic_inf=inf_heroes,
        available_mythic_cav=cav_heroes,
        available_mythic_arc=arc_heroes,
        available_joiners=joiner_heroes,
        troop_pool=troop_pool,
        troop_ratio_step=troop_ratio_step,
        min_inf_pct=min_inf_pct,
        n_joiners=n_joiners,
        bonuses=bonuses,
        leader_level=leader_level,
        leader_widget_level=leader_widget_level,
        joiner_level=joiner_level,
        label_prefix=label_prefix,
        leader_specs=leader_specs,
        class_gear=class_gear,
        buffs=buffs,
    )


def update_roster_from_search_space(
    roster: AccountRoster,
    space: SearchSpace,
) -> AccountRoster:
    """Update an existing AccountRoster with overrides present in SearchSpace."""
    # 1. Update owned heroes if search space provides them
    if any([
        space.available_mythic_inf,
        space.available_mythic_cav,
        space.available_mythic_arc,
        space.available_joiners,
    ]):
        new_owned: dict[str, list[str]] = {}
        for cls, mythics in (
            ("Inf", space.available_mythic_inf),
            ("Cav", space.available_mythic_cav),
            ("Arc", space.available_mythic_arc),
        ):
            heroes = list(mythics)
            for j in space.available_joiners:
                if hero_class(j) == cls and j not in heroes:
                    heroes.append(j)
            for h in roster.owned_heroes.get(cls, []):
                if h in NON_COMBAT_FIRST_SKILL_HEROES and h not in heroes:
                    heroes.append(h)
            new_owned[cls] = heroes
    else:
        new_owned = {cls: list(h) for cls, h in roster.owned_heroes.items()}

    # 2. Update builds from leader specs
    new_builds = dict(roster.builds)
    for h, spec in space.leader_specs.items():
        new_builds[h] = HeroBuild(
            level=spec.level,
            widget_level=spec.widget_level,
            skill_levels=spec.skill_levels,
        )

    # 3. Update class gear
    if space.class_gear:
        new_gear = {cls: dict(slots) for cls, slots in space.class_gear.items()}
    else:
        new_gear = {cls: dict(slots) for cls, slots in roster.class_gear.items()}

    # 4. Update bonuses and buffs
    new_bonuses = replace(space.bonuses)
    new_buffs = replace(space.buffs)

    return AccountRoster(
        name=roster.name,
        generation=roster.generation,
        owned_heroes=new_owned,
        builds=new_builds,
        class_gear=new_gear,
        bonuses=new_bonuses,
        buffs=new_buffs,
    )


def roster_to_fighter(
    roster: AccountRoster,
    inf_hero: str,
    cav_hero: str,
    arc_hero: str,
    joiners: tuple[str, ...] = (),
    troops: TroopRoster | None = None,
    label: str = "Opponent",
) -> Fighter:
    """Assemble a Fighter from an AccountRoster by selecting specific leaders & troops.

    - Equips inf_hero, cav_hero, arc_hero with stars, widgets, and skills from roster.builds.
    - Equips class gear from roster.class_gear for each leader's class.
    - Populates joiners with their levels from roster.builds.
    - Injects roster.bonuses and roster.buffs.
    """
    def _make_leader(hero_name: str, expected_cls: str) -> LeaderHero:
        actual_cls = hero_class(hero_name)
        if actual_cls != expected_cls:
            raise ValueError(
                f"leader_{expected_cls.lower()} must be an {expected_cls}-class hero, "
                f"got {hero_name} ({actual_cls})"
            )
        gear = dict(roster.class_gear.get(actual_cls, {}))
        if hero_name in roster.builds:
            b = roster.builds[hero_name]
            return LeaderHero(
                hero_name=hero_name,
                level=b.level,
                widget_level=b.widget_level,
                skill_levels=b.skill_levels,
                gear=gear,
            )
        default_wl = 0 if hero_name in EPIC_HEROES else 10
        return LeaderHero(
            hero_name=hero_name,
            level="MAX",
            widget_level=default_wl,
            gear=gear,
        )

    leader_inf = _make_leader(inf_hero, "Inf")
    leader_cav = _make_leader(cav_hero, "Cav")
    leader_arc = _make_leader(arc_hero, "Arc")

    joiner_heroes: list[JoinerHero] = []
    for j in joiners:
        if j in roster.builds:
            level = roster.builds[j].level
        else:
            level = "MAX"
        joiner_heroes.append(JoinerHero(hero_name=j, level=level))

    return Fighter(
        label=label,
        leader_inf=leader_inf,
        leader_cav=leader_cav,
        leader_arc=leader_arc,
        joiners=tuple(joiner_heroes),
        bonuses=replace(roster.bonuses),
        troops=troops if troops is not None else TroopRoster(),
        buffs=replace(roster.buffs),
    )


def merge_benchmark_into_roster(
    roster: AccountRoster,
    generation: int,
    owned_heroes: dict[str, list[str]],
    builds: dict[str, HeroBuild],
) -> AccountRoster:
    """Apply the Benchmark tab's edits (generation, owned heroes, stars/widgets) to a roster.

    The Benchmark tab doesn't edit skills, class gear, bonuses or buffs, so those are
    carried over from ``roster``. Kept skill levels are capped at what the new star allows.
    """
    new_builds = dict(roster.builds)
    for h, b in builds.items():
        prev = roster.builds.get(h)
        skills = prev.skill_levels if prev is not None else b.skill_levels
        if skills is not None:
            cap = default_skill_levels(b.level)
            skills = (min(skills[0], cap[0]), min(skills[1], cap[1]), min(skills[2], cap[2]))
        new_builds[h] = replace(b, skill_levels=skills)
    return replace(
        roster,
        generation=generation,
        owned_heroes={cls: list(heroes) for cls, heroes in owned_heroes.items()},
        builds=new_builds,
    )


__all__ = [
    "roster_to_search_space",
    "update_roster_from_search_space",
    "roster_to_fighter",
    "merge_benchmark_into_roster",
]
