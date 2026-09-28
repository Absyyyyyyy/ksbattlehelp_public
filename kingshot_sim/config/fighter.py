from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from ..data.reference import (
    VALID_TIERS, MYTHIC_HEROES, EPIC_HEROES, NON_COMBAT_FIRST_SKILL_HEROES,
    BENCHMARK_DUMMIES, hero_class,
    valid_tiers, default_skill_levels, max_skill_level,
    TIER_RANGE, tier_stat, parse_tier_label, interpolated_tier_stat,
)
from ..domain.heroes import Hero
from ..domain.enums import SquadType


@dataclass
class BonusVector:
    squad_atk_pct: float = 0.0
    squad_def_pct: float = 0.0
    squad_let_pct: float = 0.0
    squad_hp_pct: float = 0.0
    inf_atk_pct: float = 0.0
    inf_def_pct: float = 0.0
    inf_let_pct: float = 0.0
    inf_hp_pct: float = 0.0
    cav_atk_pct: float = 0.0
    cav_def_pct: float = 0.0
    cav_let_pct: float = 0.0
    cav_hp_pct: float = 0.0
    arc_atk_pct: float = 0.0
    arc_def_pct: float = 0.0
    arc_let_pct: float = 0.0
    arc_hp_pct: float = 0.0

    def get(self, squad: SquadType, stat: Literal["atk", "def", "let", "hp"]) -> float:
        squad_field = f"squad_{stat}_pct"
        if squad == SquadType.INFANTRY:
            class_field = f"inf_{stat}_pct"
        elif squad == SquadType.CAVALRY:
            class_field = f"cav_{stat}_pct"
        else:
            class_field = f"arc_{stat}_pct"
        return getattr(self, squad_field) + getattr(self, class_field)


@dataclass(frozen=True)
class TroopGroup:
    tier: str
    count: int
    level: float | None = None

    def __post_init__(self) -> None:
        live_tiers = valid_tiers()
        if self.tier not in live_tiers:
            raise ValueError(f"Unknown tier {self.tier!r} (valid: {live_tiers})")
        if self.count < 0:
            raise ValueError(f"count must be non-negative, got {self.count}")
        if self.level is not None:
            lo_t, hi_t = TIER_RANGE
            if not (lo_t <= self.level <= hi_t):
                raise ValueError(
                    f"level {self.level} out of range [{lo_t}, {hi_t}]"
                )

    def base_stat(self, stat: str) -> float:
        if self.level is None:
            return tier_stat(self.tier, stat)
        _, tg = parse_tier_label(self.tier)
        return interpolated_tier_stat(self.level, tg, stat)


@dataclass(frozen=True)
class TroopRoster:
    infantry: tuple[TroopGroup, ...] = ()
    cavalry:  tuple[TroopGroup, ...] = ()
    archer:   tuple[TroopGroup, ...] = ()

    def squad(self, st: SquadType) -> tuple[TroopGroup, ...]:
        if st == SquadType.INFANTRY:
            return self.infantry
        if st == SquadType.CAVALRY:
            return self.cavalry
        return self.archer

    def squad_count(self, st: SquadType) -> int:
        return sum(g.count for g in self.squad(st))

    def total_count(self) -> int:
        return sum(self.squad_count(st) for st in SquadType.all())


@dataclass(frozen=True)
class HeroGearPiece:
    slot: Literal["head", "chest", "gloves", "boots"]
    quality: Literal["mythic", "red"]
    level: int
    enhance: int = 0
    forge_mastery: int = 0

    def __post_init__(self) -> None:
        from ..data.gear import validate_piece
        validate_piece(self.slot, self.quality, self.level,
                       forge_mastery=self.forge_mastery,
                       strict_mastery=False)
        if not (0 <= self.enhance <= 20):
            raise ValueError(f"enhance must be 0..20, got {self.enhance}")


@dataclass(frozen=True)
class LeaderHero:
    hero_name: str
    level: str
    widget_level: int = 0
    skill_levels: tuple[int, int, int] | None = None
    gear_atk_pct: float = 0.0
    gear_def_pct: float = 0.0
    gear_let_pct: float = 0.0
    gear_hp_pct:  float = 0.0
    gear: dict[str, HeroGearPiece] = field(default_factory=dict)
    forge_mastery: int = 0

    def __post_init__(self) -> None:
        if self.hero_name not in (
                MYTHIC_HEROES | EPIC_HEROES | BENCHMARK_DUMMIES):
            raise ValueError(f"Unknown leader hero: {self.hero_name!r}")
        for f, v in (("gear_atk_pct", self.gear_atk_pct),
                     ("gear_def_pct", self.gear_def_pct),
                     ("gear_let_pct", self.gear_let_pct),
                     ("gear_hp_pct",  self.gear_hp_pct)):
            if v < 0:
                raise ValueError(f"{f} cannot be negative, got {v}")
        if self.skill_levels is None:
            object.__setattr__(self, "skill_levels", default_skill_levels(self.level))
        else:
            sl = tuple(int(x) for x in self.skill_levels)
            if len(sl) != 3:
                raise ValueError(f"skill_levels must have length 3, got {sl!r}")
            for slot, lvl in zip(("sk1", "sk2", "sk3"), sl):
                cap = max_skill_level(self.level, slot)
                if not 0 <= lvl <= cap:
                    raise ValueError(
                        f"{slot} level {lvl} exceeds cap {cap} for "
                        f"hero level {self.level!r}"
                    )
            object.__setattr__(self, "skill_levels", sl)

    def to_hero(self) -> Hero:
        return Hero(
            name=self.hero_name,
            level=self.level,
            widget_level=self.widget_level,
            skill_levels=self.skill_levels,
        )

    def resolve_gear_contribution(self) -> tuple[float, float, float, float]:
        if not self.gear:
            return (self.gear_atk_pct, self.gear_def_pct,
                    self.gear_let_pct, self.gear_hp_pct)
        from ..data.gear import gearset_contribution
        bonus = gearset_contribution(self.gear)
        return bonus.as_tuple()


@dataclass(frozen=True)
class JoinerHero:
    hero_name: str
    level: str = "MAX"

    def __post_init__(self) -> None:
        pass

    def to_hero(self) -> Hero:
        return Hero(name=self.hero_name, level=self.level, widget_level=0)

    def contributes_skill(self) -> bool:
        if self.hero_name in NON_COMBAT_FIRST_SKILL_HEROES:
            return False
        return self.level == "MAX"


@dataclass(frozen=True)
class Fighter:
    label: str
    leader_inf: LeaderHero
    leader_cav: LeaderHero
    leader_arc: LeaderHero
    joiners: tuple[JoinerHero, ...]
    bonuses: BonusVector
    troops: TroopRoster
    buffs: "Buffs" = field(default_factory=lambda: _default_buffs())

    def __post_init__(self) -> None:
        if hero_class(self.leader_inf.hero_name) != "Inf":
            raise ValueError(f"leader_inf must be an Inf-class hero, got {self.leader_inf.hero_name}")
        if hero_class(self.leader_cav.hero_name) != "Cav":
            raise ValueError(f"leader_cav must be a Cav-class hero, got {self.leader_cav.hero_name}")
        if hero_class(self.leader_arc.hero_name) != "Arc":
            raise ValueError(f"leader_arc must be an Arc-class hero, got {self.leader_arc.hero_name}")
        names = {self.leader_inf.hero_name, self.leader_cav.hero_name, self.leader_arc.hero_name}
        if len(names) != 3:
            raise ValueError("Leader trio must have 3 distinct heroes")

    def leader_for_class(self, st: SquadType) -> LeaderHero:
        if st == SquadType.INFANTRY:
            return self.leader_inf
        if st == SquadType.CAVALRY:
            return self.leader_cav
        return self.leader_arc

    def all_leaders(self) -> tuple[LeaderHero, LeaderHero, LeaderHero]:
        return (self.leader_inf, self.leader_cav, self.leader_arc)

    def has_helga(self) -> bool:
        return any(l.hero_name == "Helga" for l in self.all_leaders())

    def has_amadeus(self) -> bool:
        return any(l.hero_name == "Amadeus" for l in self.all_leaders())


def _default_buffs() -> "Buffs":
    from .buffs import Buffs
    return Buffs()


__all__ = [
    "BonusVector",
    "TroopGroup",
    "TroopRoster",
    "HeroGearPiece",
    "LeaderHero",
    "JoinerHero",
    "Fighter",
]
