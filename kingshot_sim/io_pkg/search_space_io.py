from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

from ..config.fighter import BonusVector
from ..optimizer.search_space import SearchSpace, TroopPool, LeaderSpec
from ..data.reference import (
    VALID_TIERS, MYTHIC_HEROES, EPIC_HEROES, HERO_CLASS, LEVEL_FRACTION,
    valid_tiers,
)
from .profiles import BonusVectorSchema


class TroopPoolSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    infantry_tier: str = "T10.5"
    cavalry_tier: str = "T10.5"
    archer_tier: str = "T10.5"
    march_cap: int = Field(default=300_000, ge=0)
    infantry_level: float | None = Field(default=None, ge=1.0)
    cavalry_level: float | None = Field(default=None, ge=1.0)
    archer_level: float | None = Field(default=None, ge=1.0)

    @field_validator("infantry_tier", "cavalry_tier", "archer_tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        if v not in valid_tiers():
            raise ValueError(f"Unknown tier {v!r}")
        return v

    def to_domain(self) -> TroopPool:
        return TroopPool(
            infantry_tier=self.infantry_tier,
            cavalry_tier=self.cavalry_tier,
            archer_tier=self.archer_tier,
            march_cap=self.march_cap,
            infantry_level=self.infantry_level,
            cavalry_level=self.cavalry_level,
            archer_level=self.archer_level,
        )

    @classmethod
    def from_domain(cls, t: TroopPool) -> "TroopPoolSchema":
        return cls(
            infantry_tier=t.infantry_tier,
            cavalry_tier=t.cavalry_tier,
            archer_tier=t.archer_tier,
            march_cap=t.march_cap,
            infantry_level=t.infantry_level,
            cavalry_level=t.cavalry_level,
            archer_level=t.archer_level,
        )


class LeaderSpecSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: str = "MAX"
    widget_level: int = Field(default=10, ge=0, le=10)
    gear_atk_pct: float = Field(default=0.0, ge=0.0, le=2000.0)
    gear_def_pct: float = Field(default=0.0, ge=0.0, le=2000.0)
    gear_let_pct: float = Field(default=0.0, ge=0.0, le=2000.0)
    gear_hp_pct:  float = Field(default=0.0, ge=0.0, le=2000.0)

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in LEVEL_FRACTION:
            raise ValueError(f"Unknown level {v!r}")
        return v

    def to_domain(self) -> LeaderSpec:
        return LeaderSpec(
            level=self.level,
            widget_level=self.widget_level,
            gear_atk_pct=self.gear_atk_pct,
            gear_def_pct=self.gear_def_pct,
            gear_let_pct=self.gear_let_pct,
            gear_hp_pct=self.gear_hp_pct,
        )

    @classmethod
    def from_domain(cls, s: LeaderSpec) -> "LeaderSpecSchema":
        return cls(
            level=s.level,
            widget_level=s.widget_level,
            gear_atk_pct=s.gear_atk_pct,
            gear_def_pct=s.gear_def_pct,
            gear_let_pct=s.gear_let_pct,
            gear_hp_pct=s.gear_hp_pct,
        )


class SearchSpaceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available_mythic_inf: list[str] = Field(default_factory=list)
    available_mythic_cav: list[str] = Field(default_factory=list)
    available_mythic_arc: list[str] = Field(default_factory=list)
    available_joiners: list[str] = Field(default_factory=list)
    troop_pool: TroopPoolSchema = Field(default_factory=TroopPoolSchema)
    troop_ratio_step: float = Field(default=0.10, gt=0.0, le=1.0)
    min_inf_pct: float = Field(default=0.30, ge=0.0, le=1.0)
    n_joiners: int = Field(default=4, ge=0, le=4)
    bonuses: BonusVectorSchema = Field(default_factory=BonusVectorSchema)
    leader_level: str = "MAX"
    leader_widget_level: int = Field(default=10, ge=0, le=10)
    joiner_level: str = "MAX"
    label_prefix: str = "Cand"
    leader_specs: dict[str, LeaderSpecSchema] = Field(default_factory=dict)

    @field_validator("leader_level", "joiner_level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in LEVEL_FRACTION:
            raise ValueError(f"Unknown level {v!r}")
        return v

    def to_domain(self) -> SearchSpace:
        return SearchSpace(
            available_mythic_inf=list(self.available_mythic_inf),
            available_mythic_cav=list(self.available_mythic_cav),
            available_mythic_arc=list(self.available_mythic_arc),
            available_joiners=list(self.available_joiners),
            troop_pool=self.troop_pool.to_domain(),
            troop_ratio_step=self.troop_ratio_step,
            min_inf_pct=self.min_inf_pct,
            n_joiners=self.n_joiners,
            bonuses=self.bonuses.to_domain(),
            leader_level=self.leader_level,
            leader_widget_level=self.leader_widget_level,
            joiner_level=self.joiner_level,
            label_prefix=self.label_prefix,
            leader_specs={h: s.to_domain() for h, s in self.leader_specs.items()},
        )

    @classmethod
    def from_domain(cls, s: SearchSpace) -> "SearchSpaceSchema":
        return cls(
            available_mythic_inf=list(s.available_mythic_inf),
            available_mythic_cav=list(s.available_mythic_cav),
            available_mythic_arc=list(s.available_mythic_arc),
            available_joiners=list(s.available_joiners),
            troop_pool=TroopPoolSchema.from_domain(s.troop_pool),
            troop_ratio_step=s.troop_ratio_step,
            min_inf_pct=s.min_inf_pct,
            n_joiners=s.n_joiners,
            bonuses=BonusVectorSchema.from_domain(s.bonuses),
            leader_level=s.leader_level,
            leader_widget_level=s.leader_widget_level,
            joiner_level=s.joiner_level,
            label_prefix=s.label_prefix,
            leader_specs={h: LeaderSpecSchema.from_domain(spec)
                           for h, spec in s.leader_specs.items()},
        )


def search_space_to_json(s: SearchSpace, *, indent: int | None = 2) -> str:
    return SearchSpaceSchema.from_domain(s).model_dump_json(indent=indent)


def search_space_from_json(payload: str) -> SearchSpace:
    return SearchSpaceSchema.model_validate(json.loads(payload)).to_domain()


def save_search_space(s: SearchSpace, path: str | Path) -> None:
    Path(path).write_text(search_space_to_json(s), encoding="utf-8")


def load_search_space(path: str | Path) -> SearchSpace:
    return search_space_from_json(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "SearchSpaceSchema",
    "TroopPoolSchema",
    "LeaderSpecSchema",
    "search_space_to_json",
    "search_space_from_json",
    "save_search_space",
    "load_search_space",
]
