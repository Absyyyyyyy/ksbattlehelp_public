from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

from ..config.fighter import BonusVector, LeaderHero
from ..config.buffs import (
    Buffs,
    MOOSE_LEVEL_PCT, RHINO_LEVEL_PCT, LION_LEVEL_PCT,
    PANTHER_LEVEL_PCT, ELEPHANT_LEVEL_PCT,
    GRIZZLY_LEVEL_PCT, GRIZZLY_MAX_LEVEL,
    TURRET_LEVEL_PCT, TURRET_MAX_LEVEL,
    MOOSE_MAX_LEVEL,
    APPOINT_FIELD_COMMANDER_LET_PCT,
    APPOINT_MARSHAL_ATK_PCT,
    APPOINT_KING_PCT,
)
from ..data.reference import (
    HERO_WIDGET, hero_leader_pct, widget_stat_bonus,
    WIDGET_SKILL_MAX_PCT, WIDGET_SKILL_MULTIPLIER,
)
from ..data.catalog import WIDGET_SKILL_SPEC


APPOINTMENT_FIELD_COMMANDER_LET_PCT = APPOINT_FIELD_COMMANDER_LET_PCT
APPOINTMENT_MARSHAL_ATK_PCT         = APPOINT_MARSHAL_ATK_PCT
APPOINTMENT_KING_PCT                = APPOINT_KING_PCT


TERRITORY_BONUS_PCT: float = 10.0


_OP_TO_STAT: dict[int, str] = {
    101: "let",
    102: "atk",
    112: "def",
    113: "hp",
}

_CLASSES: tuple[str, ...] = ("inf", "cav", "arc")
_STATS: tuple[str, ...] = ("atk", "def", "let", "hp")


@dataclass(frozen=True)
class VisibleAggregate:
    inf_atk_pct: float
    inf_def_pct: float
    inf_let_pct: float
    inf_hp_pct: float
    cav_atk_pct: float
    cav_def_pct: float
    cav_let_pct: float
    cav_hp_pct: float
    arc_atk_pct: float
    arc_def_pct: float
    arc_let_pct: float
    arc_hp_pct: float

    def get(self, klass: str, stat: str) -> float:
        if klass not in _CLASSES:
            raise ValueError(f"Unknown class {klass!r}; expected one of {_CLASSES}")
        if stat not in _STATS:
            raise ValueError(f"Unknown stat {stat!r}; expected one of {_STATS}")
        return float(getattr(self, f"{klass}_{stat}_pct"))


@dataclass(frozen=True)
class EnemyScreenshotDebuffs:
    city_atk_down: int = 0
    city_def_down: int = 0
    grizzly_level: int = 0
    moose_level:   int = 0

    def __post_init__(self) -> None:
        if self.city_atk_down not in (0, 10, 20):
            raise ValueError(
                f"city_atk_down={self.city_atk_down!r} not allowed; must be 0, 10, or 20"
            )
        if self.city_def_down not in (0, 10, 20):
            raise ValueError(
                f"city_def_down={self.city_def_down!r} not allowed; must be 0, 10, or 20"
            )
        if not 0 <= self.grizzly_level <= GRIZZLY_MAX_LEVEL:
            raise ValueError(
                f"grizzly_level={self.grizzly_level!r} not allowed; must be 0..{GRIZZLY_MAX_LEVEL}"
            )
        if not 0 <= self.moose_level <= MOOSE_MAX_LEVEL:
            raise ValueError(
                f"moose_level={self.moose_level!r} not allowed; must be 0..{MOOSE_MAX_LEVEL}"
            )

    def is_empty(self) -> bool:
        return (self.city_atk_down == 0
                and self.city_def_down == 0
                and self.grizzly_level == 0
                and self.moose_level == 0)


@dataclass(frozen=True)
class PeelingContext:
    importee_role: Literal["attacking", "defending"]
    was_rally: bool
    is_garrisoning_territory: bool
    leader_inf: LeaderHero
    leader_cav: LeaderHero
    leader_arc: LeaderHero
    buffs: Buffs = field(default_factory=Buffs)
    enemy_debuffs: EnemyScreenshotDebuffs = field(default_factory=EnemyScreenshotDebuffs)

    def trio(self) -> tuple[LeaderHero, LeaderHero, LeaderHero]:
        return (self.leader_inf, self.leader_cav, self.leader_arc)

    def leader_for_class(self, klass: str) -> LeaderHero:
        if klass == "inf":
            return self.leader_inf
        if klass == "cav":
            return self.leader_cav
        if klass == "arc":
            return self.leader_arc
        raise ValueError(f"Unknown class {klass!r}")

    def active_widget_sides(self) -> frozenset[str]:
        return active_widget_sides_for(self.importee_role, self.was_rally)


def active_widget_sides_for(importee_role: str, was_rally: bool) -> frozenset[str]:
    if importee_role == "defending":
        return frozenset({"defender"})
    if importee_role == "attacking" and was_rally:
        return frozenset({"rally"})
    return frozenset()


def widget_expedition_pct_by_stat(
    trio: tuple[LeaderHero, LeaderHero, LeaderHero],
    importee_role: str,
    was_rally: bool,
) -> dict[str, float]:
    out: dict[str, float] = {"atk": 0.0, "def": 0.0, "let": 0.0, "hp": 0.0}
    active = active_widget_sides_for(importee_role, was_rally)
    if not active:
        return out
    for leader in trio:
        widget_name = HERO_WIDGET.get(leader.hero_name)
        if widget_name is None:
            continue
        spec = WIDGET_SKILL_SPEC.get(widget_name)
        if spec is None:
            continue
        side, op, _ = spec
        if side not in active:
            continue
        stat = _OP_TO_STAT.get(op)
        if stat is None:
            continue
        pct = WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[leader.widget_level]
        if pct:
            out[stat] += pct
    return out


def _section_d_multiplier(
    ctx: PeelingContext,
    klass: str,
    stat: str,
) -> float:
    from ..engine.section_d import (
        section_d_factor_from_pcts,
        own_pct as _own_pct,
        enemy_down_pct as _enemy_down_pct,
        LAYERS,
    )

    own_by_layer = {layer: _own_pct(ctx.buffs, stat, layer) for layer in LAYERS}

    ed = ctx.enemy_debuffs
    opp_buffs = Buffs(
        city_enemy_atk_down=ed.city_atk_down,
        city_enemy_def_down=ed.city_def_down,
        grizzly_level=ed.grizzly_level,
        moose_level=ed.moose_level,
    )
    enemy_by_layer = {layer: _enemy_down_pct(opp_buffs, stat, layer) for layer in LAYERS}

    factor = section_d_factor_from_pcts(own_by_layer, enemy_by_layer)

    active_sides = ctx.active_widget_sides()
    if active_sides:
        for leader in ctx.trio():
            widget_name = HERO_WIDGET[leader.hero_name]
            side, op, _ = WIDGET_SKILL_SPEC[widget_name]
            if side not in active_sides:
                continue
            widget_stat = _OP_TO_STAT.get(op)
            if widget_stat != stat:
                continue
            pct = WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[leader.widget_level]
            if pct > 0:
                factor *= 1.0 + pct / 100.0

    return factor


def _territory_forward(a: float, stat: str, is_garrisoning: bool) -> float:
    if not is_garrisoning:
        return a
    if stat not in ("atk", "def"):
        return a
    return a * (1.0 + TERRITORY_BONUS_PCT / 100.0) + TERRITORY_BONUS_PCT


def _territory_reverse(b: float, stat: str, is_garrisoning: bool) -> float:
    if not is_garrisoning:
        return b
    if stat not in ("atk", "def"):
        return b
    return (b - TERRITORY_BONUS_PCT) / (1.0 + TERRITORY_BONUS_PCT / 100.0)


def _leader_contributions_for_class(
    leader: LeaderHero,
    stat: str,
) -> float:
    out = 0.0

    if stat in ("atk", "def"):
        out += hero_leader_pct(leader.hero_name, leader.level)

    if stat in ("let", "hp") and leader.widget_level > 0:
        widget_name = HERO_WIDGET[leader.hero_name]
        let_pct, hp_pct = widget_stat_bonus(widget_name, leader.widget_level)
        out += let_pct if stat == "let" else hp_pct

    gear_atk, gear_def, gear_let, gear_hp = leader.resolve_gear_contribution()
    out += {"atk": gear_atk, "def": gear_def, "let": gear_let, "hp": gear_hp}[stat]

    return out


def build_visible_from_bonus_vector(
    bv: BonusVector,
    ctx: PeelingContext,
) -> VisibleAggregate:
    cells: dict[str, float] = {}
    for klass in _CLASSES:
        for stat in _STATS:
            from ..domain.enums import SquadType
            squad = {"inf": SquadType.INFANTRY,
                     "cav": SquadType.CAVALRY,
                     "arc": SquadType.ARCHER}[klass]
            a = bv.get(squad, stat)

            a += _leader_contributions_for_class(ctx.leader_for_class(klass), stat)

            a += ctx.buffs.appoint_additive_pct(stat)

            b = _territory_forward(a, stat, ctx.is_garrisoning_territory)

            c = b * _section_d_multiplier(ctx, klass, stat)

            cells[f"{klass}_{stat}_pct"] = c

    return VisibleAggregate(**cells)


def peel_visible_to_bonus_vector(
    visible: VisibleAggregate,
    ctx: PeelingContext,
) -> BonusVector:
    out_kwargs: dict[str, float] = {}
    for stat in _STATS:
        out_kwargs[f"squad_{stat}_pct"] = 0.0

    for klass in _CLASSES:
        for stat in _STATS:
            c = visible.get(klass, stat)

            d_factor = _section_d_multiplier(ctx, klass, stat)
            if d_factor <= 0:
                raise ValueError(
                    f"Non-positive Section D factor for ({klass}, {stat}): "
                    f"{d_factor}. Check buff/pet/appointment values."
                )
            b = c / d_factor

            a = _territory_reverse(b, stat, ctx.is_garrisoning_territory)

            a -= _leader_contributions_for_class(ctx.leader_for_class(klass), stat)

            a -= ctx.buffs.appoint_additive_pct(stat)

            out_kwargs[f"{klass}_{stat}_pct"] = a

    return BonusVector(**out_kwargs)


__all__ = [
    "VisibleAggregate",
    "PeelingContext",
    "EnemyScreenshotDebuffs",
    "peel_visible_to_bonus_vector",
    "build_visible_from_bonus_vector",
    "active_widget_sides_for",
    "widget_expedition_pct_by_stat",
    "TERRITORY_BONUS_PCT",
    "APPOINTMENT_FIELD_COMMANDER_LET_PCT",
    "APPOINTMENT_MARSHAL_ATK_PCT",
    "APPOINTMENT_KING_PCT",
]
