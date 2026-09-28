from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..data.reference import (
    HERO_LEADER_MAX, HERO_CLASS, MYTHIC_HEROES, EPIC_HEROES,
    NON_COMBAT_FIRST_SKILL_HEROES, BENCHMARK_DUMMIES, hero_class,
    hero_leader_pct, helga_passive_value, amadeus_passive_value,
    HERO_WIDGET, widget_stat_bonus, WIDGET_SKILL_MULTIPLIER, WIDGET_SKILL_MAX_PCT,
    default_skill_levels, max_skill_level,
)
from .skills import Skill


_SLOT_BY_INDEX = ("sk1", "sk2", "sk3")


@dataclass(frozen=True)
class Hero:
    name: str
    level: str
    widget_level: int
    skill_levels: Optional[tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        if self.name not in HERO_LEADER_MAX and self.name not in BENCHMARK_DUMMIES:
            raise ValueError(f"Unknown hero: {self.name!r}")
        if self.is_epic and self.widget_level != 0:
            object.__setattr__(self, "widget_level", 0)
        if self.skill_levels is None:
            object.__setattr__(self, "skill_levels", default_skill_levels(self.level))
        else:
            sl = tuple(int(x) for x in self.skill_levels)
            if len(sl) != 3:
                raise ValueError(f"skill_levels must have length 3, got {sl!r}")
            for i, lvl in enumerate(sl):
                cap = max_skill_level(self.level, _SLOT_BY_INDEX[i])
                if not 0 <= lvl <= cap:
                    raise ValueError(
                        f"{_SLOT_BY_INDEX[i]} level {lvl} exceeds cap {cap} "
                        f"for hero level {self.level!r}"
                    )
            object.__setattr__(self, "skill_levels", sl)

    @property
    def is_mythic(self) -> bool:
        return self.name in MYTHIC_HEROES

    @property
    def is_epic(self) -> bool:
        return self.name in EPIC_HEROES

    @property
    def squad_class(self) -> str:
        return hero_class(self.name)

    @property
    def first_skill_is_combat(self) -> bool:
        return self.name not in NON_COMBAT_FIRST_SKILL_HEROES

    def skill_level(self, slot: str) -> int:
        return self.skill_levels[_SLOT_BY_INDEX.index(slot)]

    def leader_atk_def_pct(self) -> float:
        return hero_leader_pct(self.name, self.level)

    def helga_passive_factor(self) -> float:
        if self.name != "Helga":
            return 0.0
        return helga_passive_value(self.level)

    def amadeus_passive_factor(self) -> float:
        if self.name != "Amadeus":
            return 0.0
        return amadeus_passive_value(self.level)

    def widget_let_hp_bonus(self) -> tuple[float, float]:
        if not self.is_mythic or self.widget_level == 0:
            return 0.0, 0.0
        wname = HERO_WIDGET[self.name]
        return widget_stat_bonus(wname, self.widget_level)

    def widget_skill_pct(self) -> float:
        if not self.is_mythic or self.widget_level == 0:
            return 0.0
        return WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[self.widget_level]

    def skills(self, side: str) -> tuple[Skill, ...]:
        from ..data.catalog import get_hero_skills
        return tuple(s for s in get_hero_skills(self) if s.is_active_for_side(side))

    def first_skill(self) -> Optional[Skill]:
        if not self.first_skill_is_combat:
            return None
        from ..data.catalog import get_hero_skills
        for s in get_hero_skills(self):
            if s.slot == "sk1":
                return s
        return None


__all__ = ["Hero"]
