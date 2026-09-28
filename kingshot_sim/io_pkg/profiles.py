from __future__ import annotations
from typing import Literal
import json
from pathlib import Path

from pydantic import BaseModel, Field, ConfigDict, field_validator

from ..config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero, HeroGearPiece,
)
from ..data.reference import (
    VALID_TIERS, MYTHIC_HEROES, EPIC_HEROES, LEVEL_FRACTION, valid_tiers,
    max_skill_level,
)


class HeroGearPieceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: Literal["head", "chest", "gloves", "boots"]
    quality: Literal["mythic", "red"]
    level: int = Field(ge=0, le=200)
    enhance: int = Field(default=0, ge=0, le=20)
    forge_mastery: int = Field(default=0, ge=0)

    def to_domain(self) -> HeroGearPiece:
        return HeroGearPiece(slot=self.slot, quality=self.quality,
                             level=self.level, enhance=self.enhance,
                             forge_mastery=self.forge_mastery)

    @classmethod
    def from_domain(cls, g: HeroGearPiece) -> "HeroGearPieceSchema":
        return cls(slot=g.slot, quality=g.quality, level=g.level,
                   enhance=g.enhance, forge_mastery=g.forge_mastery)


class LeaderHeroSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hero_name: str
    level: str = "MAX"
    widget_level: int = Field(default=0, ge=0, le=10)
    skill_levels: list[int] | None = None
    gear: dict[str, HeroGearPieceSchema] = Field(default_factory=dict)
    forge_mastery: int = Field(default=0, ge=0)

    @field_validator("hero_name")
    @classmethod
    def _validate_mythic(cls, v: str) -> str:
        if v not in MYTHIC_HEROES and v not in EPIC_HEROES:
            raise ValueError(f"Unknown leader hero: {v!r}")
        return v

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in LEVEL_FRACTION:
            raise ValueError(f"Unknown level {v!r} (valid: e.g. '0_0'..'4_5' or 'MAX')")
        return v

    @field_validator("skill_levels")
    @classmethod
    def _validate_skill_levels_shape(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        if len(v) != 3:
            raise ValueError(f"skill_levels must have length 3, got {v!r}")
        for lvl in v:
            if not 0 <= int(lvl) <= 5:
                raise ValueError(f"each skill level must be 0..5, got {lvl}")
        return [int(x) for x in v]

    def _resolved_skill_levels(self) -> tuple[int, int, int] | None:
        if self.skill_levels is None:
            return None
        sl = self.skill_levels
        for slot, lvl in zip(("sk1", "sk2", "sk3"), sl):
            cap = max_skill_level(self.level, slot)
            if lvl > cap:
                raise ValueError(
                    f"{slot} level {lvl} exceeds cap {cap} for hero "
                    f"level {self.level!r}"
                )
        return (sl[0], sl[1], sl[2])

    def to_domain(self) -> LeaderHero:
        return LeaderHero(
            hero_name=self.hero_name,
            level=self.level,
            widget_level=self.widget_level,
            skill_levels=self._resolved_skill_levels(),
            gear={k: g.to_domain() for k, g in self.gear.items()},
            forge_mastery=self.forge_mastery,
        )

    @classmethod
    def from_domain(cls, h: LeaderHero) -> "LeaderHeroSchema":
        return cls(
            hero_name=h.hero_name,
            level=h.level,
            widget_level=h.widget_level,
            skill_levels=list(h.skill_levels) if h.skill_levels is not None else None,
            gear={k: HeroGearPieceSchema.from_domain(g) for k, g in h.gear.items()},
            forge_mastery=h.forge_mastery,
        )


class JoinerHeroSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hero_name: str
    level: str = "MAX"

    @field_validator("hero_name")
    @classmethod
    def _validate_known_hero(cls, v: str) -> str:
        if v not in MYTHIC_HEROES and v not in EPIC_HEROES:
            raise ValueError(f"Unknown hero {v!r}")
        return v

    @field_validator("level")
    @classmethod
    def _validate_level(cls, v: str) -> str:
        if v not in LEVEL_FRACTION:
            raise ValueError(f"Unknown level {v!r}")
        return v

    def to_domain(self) -> JoinerHero:
        return JoinerHero(hero_name=self.hero_name, level=self.level)

    @classmethod
    def from_domain(cls, h: JoinerHero) -> "JoinerHeroSchema":
        return cls(hero_name=h.hero_name, level=h.level)


class TroopGroupSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: str
    count: int = Field(ge=0)
    level: float | None = None

    @field_validator("tier")
    @classmethod
    def _validate_tier(cls, v: str) -> str:
        live = valid_tiers()
        if v not in live:
            raise ValueError(f"Unknown tier {v!r} (valid: {sorted(live)})")
        return v

    def to_domain(self) -> TroopGroup:
        return TroopGroup(tier=self.tier, count=self.count, level=self.level)

    @classmethod
    def from_domain(cls, g: TroopGroup) -> "TroopGroupSchema":
        return cls(tier=g.tier, count=g.count, level=g.level)


class TroopRosterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    infantry: list[TroopGroupSchema] = Field(default_factory=list)
    cavalry:  list[TroopGroupSchema] = Field(default_factory=list)
    archer:   list[TroopGroupSchema] = Field(default_factory=list)

    def to_domain(self) -> TroopRoster:
        return TroopRoster(
            infantry=tuple(g.to_domain() for g in self.infantry),
            cavalry=tuple(g.to_domain() for g in self.cavalry),
            archer=tuple(g.to_domain() for g in self.archer),
        )

    @classmethod
    def from_domain(cls, r: TroopRoster) -> "TroopRosterSchema":
        return cls(
            infantry=[TroopGroupSchema.from_domain(g) for g in r.infantry],
            cavalry=[TroopGroupSchema.from_domain(g) for g in r.cavalry],
            archer=[TroopGroupSchema.from_domain(g) for g in r.archer],
        )


class BonusVectorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    squad_atk_pct: float = 0.0
    squad_def_pct: float = 0.0
    squad_let_pct: float = 0.0
    squad_hp_pct:  float = 0.0
    inf_atk_pct:   float = 0.0
    inf_def_pct:   float = 0.0
    inf_let_pct:   float = 0.0
    inf_hp_pct:    float = 0.0
    cav_atk_pct:   float = 0.0
    cav_def_pct:   float = 0.0
    cav_let_pct:   float = 0.0
    cav_hp_pct:    float = 0.0
    arc_atk_pct:   float = 0.0
    arc_def_pct:   float = 0.0
    arc_let_pct:   float = 0.0
    arc_hp_pct:    float = 0.0

    def to_domain(self) -> BonusVector:
        return BonusVector(**self.model_dump())

    @classmethod
    def from_domain(cls, b: BonusVector) -> "BonusVectorSchema":
        return cls(**{f: getattr(b, f) for f in cls.model_fields})


class BuffsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city_let: int = 0
    city_atk: int = 0
    city_def: int = 0
    city_hp:  int = 0
    city_enemy_atk_down: int = 0
    city_enemy_def_down: int = 0
    moose_level:    int = 0
    grizzly_level:  int = 0
    rhino_level:    int = 0
    panther_level:  int = 0
    elephant_level: int = 0
    lion_level:     int = 0
    appoint_field_commander: bool = False
    appoint_marshal:         bool = False
    appoint_king:            bool = False
    ocr_own_atk_pct: float = 0.0
    ocr_own_def_pct: float = 0.0
    ocr_own_let_pct: float = 0.0
    ocr_own_hp_pct:  float = 0.0
    ocr_enemy_atk_down_pct: float = 0.0
    ocr_enemy_def_down_pct: float = 0.0
    ocr_enemy_let_down_pct: float = 0.0
    ocr_enemy_hp_down_pct:  float = 0.0

    def to_domain(self) -> "Buffs":
        from ..config.buffs import Buffs
        return Buffs(
            city_let=self.city_let, city_atk=self.city_atk,
            city_def=self.city_def, city_hp=self.city_hp,
            city_enemy_atk_down=self.city_enemy_atk_down,
            city_enemy_def_down=self.city_enemy_def_down,
            moose_level=self.moose_level,
            grizzly_level=self.grizzly_level,
            rhino_level=self.rhino_level,
            panther_level=self.panther_level,
            elephant_level=self.elephant_level,
            lion_level=self.lion_level,
            appoint_field_commander=self.appoint_field_commander,
            appoint_marshal=self.appoint_marshal,
            appoint_king=self.appoint_king,
            ocr_own_atk_pct=self.ocr_own_atk_pct,
            ocr_own_def_pct=self.ocr_own_def_pct,
            ocr_own_let_pct=self.ocr_own_let_pct,
            ocr_own_hp_pct=self.ocr_own_hp_pct,
            ocr_enemy_atk_down_pct=self.ocr_enemy_atk_down_pct,
            ocr_enemy_def_down_pct=self.ocr_enemy_def_down_pct,
            ocr_enemy_let_down_pct=self.ocr_enemy_let_down_pct,
            ocr_enemy_hp_down_pct=self.ocr_enemy_hp_down_pct,
        )

    @classmethod
    def from_domain(cls, b) -> "BuffsSchema":
        return cls(
            city_let=b.city_let, city_atk=b.city_atk,
            city_def=b.city_def, city_hp=b.city_hp,
            city_enemy_atk_down=b.city_enemy_atk_down,
            city_enemy_def_down=b.city_enemy_def_down,
            moose_level=b.moose_level, grizzly_level=b.grizzly_level,
            rhino_level=b.rhino_level, panther_level=b.panther_level,
            elephant_level=b.elephant_level, lion_level=b.lion_level,
            appoint_field_commander=b.appoint_field_commander,
            appoint_marshal=b.appoint_marshal,
            appoint_king=b.appoint_king,
            ocr_own_atk_pct=b.ocr_own_atk_pct,
            ocr_own_def_pct=b.ocr_own_def_pct,
            ocr_own_let_pct=b.ocr_own_let_pct,
            ocr_own_hp_pct=b.ocr_own_hp_pct,
            ocr_enemy_atk_down_pct=b.ocr_enemy_atk_down_pct,
            ocr_enemy_def_down_pct=b.ocr_enemy_def_down_pct,
            ocr_enemy_let_down_pct=b.ocr_enemy_let_down_pct,
            ocr_enemy_hp_down_pct=b.ocr_enemy_hp_down_pct,
        )


class FighterSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    leader_inf: LeaderHeroSchema
    leader_cav: LeaderHeroSchema
    leader_arc: LeaderHeroSchema
    joiners: list[JoinerHeroSchema] = Field(default_factory=list)
    bonuses: BonusVectorSchema = Field(default_factory=BonusVectorSchema)
    troops: TroopRosterSchema = Field(default_factory=TroopRosterSchema)
    buffs: BuffsSchema = Field(default_factory=BuffsSchema)

    def to_domain(self) -> Fighter:
        return Fighter(
            label=self.label,
            leader_inf=self.leader_inf.to_domain(),
            leader_cav=self.leader_cav.to_domain(),
            leader_arc=self.leader_arc.to_domain(),
            joiners=tuple(j.to_domain() for j in self.joiners),
            bonuses=self.bonuses.to_domain(),
            troops=self.troops.to_domain(),
            buffs=self.buffs.to_domain(),
        )

    @classmethod
    def from_domain(cls, f: Fighter) -> "FighterSchema":
        return cls(
            label=f.label,
            leader_inf=LeaderHeroSchema.from_domain(f.leader_inf),
            leader_cav=LeaderHeroSchema.from_domain(f.leader_cav),
            leader_arc=LeaderHeroSchema.from_domain(f.leader_arc),
            joiners=[JoinerHeroSchema.from_domain(j) for j in f.joiners],
            bonuses=BonusVectorSchema.from_domain(f.bonuses),
            troops=TroopRosterSchema.from_domain(f.troops),
            buffs=BuffsSchema.from_domain(f.buffs),
        )


def fighter_to_json(fighter: Fighter, *, indent: int | None = 2) -> str:
    return FighterSchema.from_domain(fighter).model_dump_json(indent=indent)


def fighter_from_json(payload: str) -> Fighter:
    data = json.loads(payload)
    return FighterSchema.model_validate(data).to_domain()


def save_fighter(fighter: Fighter, path: str | Path) -> None:
    Path(path).write_text(fighter_to_json(fighter), encoding="utf-8")


def load_fighter(path: str | Path) -> Fighter:
    return fighter_from_json(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "FighterSchema",
    "BonusVectorSchema",
    "TroopRosterSchema",
    "TroopGroupSchema",
    "LeaderHeroSchema",
    "JoinerHeroSchema",
    "HeroGearPieceSchema",
    "fighter_to_json",
    "fighter_from_json",
    "save_fighter",
    "load_fighter",
]
