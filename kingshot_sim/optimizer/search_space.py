from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from ..config.buffs import Buffs
from ..data.reference import (
    MYTHIC_HEROES, EPIC_HEROES, HERO_CLASS, NON_COMBAT_FIRST_SKILL_HEROES,
)


@dataclass(frozen=True)
class LeaderSpec:
    level: str = "MAX"
    widget_level: int = 10
    skill_levels: tuple[int, int, int] | None = None
    gear_atk_pct: float = 0.0
    gear_def_pct: float = 0.0
    gear_let_pct: float = 0.0
    gear_hp_pct:  float = 0.0


@dataclass
class TroopPool:
    infantry_tier: str = "T10.5"
    cavalry_tier: str = "T10.5"
    archer_tier: str = "T10.5"
    march_cap: int = 300_000
    infantry_level: float | None = None
    cavalry_level: float | None = None
    archer_level: float | None = None

    def build_roster(self, inf_pct: float, cav_pct: float, arc_pct: float) -> TroopRoster:
        inf_n = int(self.march_cap * inf_pct)
        cav_n = int(self.march_cap * cav_pct)
        arc_n = self.march_cap - inf_n - cav_n
        return TroopRoster(
            infantry=(TroopGroup(tier=self.infantry_tier, count=inf_n,
                                 level=self.infantry_level),) if inf_n > 0 else (),
            cavalry=(TroopGroup(tier=self.cavalry_tier,   count=cav_n,
                                 level=self.cavalry_level),) if cav_n > 0 else (),
            archer=(TroopGroup(tier=self.archer_tier,     count=arc_n,
                                level=self.archer_level),) if arc_n > 0 else (),
        )


@dataclass
class SearchSpace:
    available_mythic_inf: list[str] = field(default_factory=list)
    available_mythic_cav: list[str] = field(default_factory=list)
    available_mythic_arc: list[str] = field(default_factory=list)
    available_joiners: list[str] = field(default_factory=list)
    troop_pool: TroopPool = field(default_factory=TroopPool)
    troop_ratio_step: float = 0.10
    min_inf_pct: float = 0.30
    n_joiners: int = 4
    bonuses: BonusVector = field(default_factory=BonusVector)
    leader_level: str = "MAX"
    leader_widget_level: int = 10
    joiner_level: str = "MAX"
    label_prefix: str = "Cand"
    leader_specs: dict[str, LeaderSpec] = field(default_factory=dict)
    class_gear: dict[str, dict[str, "HeroGearPiece"]] = field(default_factory=dict)
    buffs: Buffs = field(default_factory=Buffs)

    def __post_init__(self) -> None:
        for h in self.available_mythic_inf:
            if h not in MYTHIC_HEROES or HERO_CLASS[h] != "Inf":
                raise ValueError(f"{h!r} is not a mythic Inf hero")
        for h in self.available_mythic_cav:
            if h not in MYTHIC_HEROES or HERO_CLASS[h] != "Cav":
                raise ValueError(f"{h!r} is not a mythic Cav hero")
        for h in self.available_mythic_arc:
            if h not in MYTHIC_HEROES or HERO_CLASS[h] != "Arc":
                raise ValueError(f"{h!r} is not a mythic Arc hero")
        for h in self.available_joiners:
            if h not in MYTHIC_HEROES and h not in EPIC_HEROES:
                raise ValueError(f"{h!r} is not a known hero")
        self.available_joiners = [h for h in self.available_joiners
                                  if h not in NON_COMBAT_FIRST_SKILL_HEROES]

    def n_leader_trios(self) -> int:
        return (len(self.available_mythic_inf)
                * len(self.available_mythic_cav)
                * len(self.available_mythic_arc))

    def n_ratio_grid_points(self) -> int:
        n = 0
        steps = round(1.0 / self.troop_ratio_step)
        for i in range(steps + 1):
            for c in range(steps + 1):
                inf_pct = i / steps
                cav_pct = c / steps
                arc_pct = 1.0 - inf_pct - cav_pct
                if arc_pct < -1e-9:
                    continue
                if inf_pct < self.min_inf_pct - 1e-9:
                    continue
                n += 1
        return n

    def get_leader_spec(self, hero_name: str) -> LeaderSpec:
        if hero_name in self.leader_specs:
            return self.leader_specs[hero_name]
        return LeaderSpec(
            level=self.leader_level,
            widget_level=self.leader_widget_level,
            gear_atk_pct=0.0, gear_def_pct=0.0,
            gear_let_pct=0.0, gear_hp_pct=0.0,
        )

    def build_leader_hero(self, hero_name: str) -> LeaderHero:
        spec = self.get_leader_spec(hero_name)
        klass = HERO_CLASS[hero_name]
        gear_dict = self.class_gear.get(klass, {})
        return LeaderHero(
            hero_name=hero_name,
            level=spec.level,
            widget_level=spec.widget_level,
            skill_levels=spec.skill_levels,
            gear_atk_pct=spec.gear_atk_pct,
            gear_def_pct=spec.gear_def_pct,
            gear_let_pct=spec.gear_let_pct,
            gear_hp_pct=spec.gear_hp_pct,
            gear=gear_dict,
        )


__all__ = ["SearchSpace", "TroopPool", "LeaderSpec"]
