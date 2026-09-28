from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from ..domain.enums import SquadType


MYTHIC_BASE_OFFSET = 0.15
MYTHIC_LEVEL_COEF  = 0.0035
MYTHIC_MIN_LEVEL   = 0
MYTHIC_MAX_LEVEL   = 100

RED_BASE_OFFSET    = 0.50
RED_LEVEL_COEF     = 0.005
RED_MIN_LEVEL      = 100
RED_MAX_LEVEL      = 200

MASTERY_REQ_RED_ASCENSION = 10
MASTERY_REQ_RED_LVL_200    = 15

MASTERY_PCT_PER_LEVEL = 10.0

SLOT_HEAD    = "head"
SLOT_CHEST   = "chest"
SLOT_GLOVES  = "gloves"
SLOT_BOOTS   = "boots"

HELM_CHEST_SLOTS:    frozenset[str] = frozenset({SLOT_HEAD, SLOT_CHEST})
GLOVES_BOOTS_SLOTS:  frozenset[str] = frozenset({SLOT_GLOVES, SLOT_BOOTS})

VALID_SLOTS: frozenset[str] = HELM_CHEST_SLOTS | GLOVES_BOOTS_SLOTS

VALID_QUALITIES: frozenset[str] = frozenset({"mythic", "red"})


def base_bonus_pct(quality: str, level: int) -> float:
    if quality == "mythic":
        if not (MYTHIC_MIN_LEVEL <= level <= MYTHIC_MAX_LEVEL):
            raise ValueError(
                f"Mythic gear level must be in [{MYTHIC_MIN_LEVEL}, "
                f"{MYTHIC_MAX_LEVEL}], got {level}"
            )
        return 100.0 * (MYTHIC_BASE_OFFSET + level * MYTHIC_LEVEL_COEF)
    if quality == "red":
        if not (RED_MIN_LEVEL <= level <= RED_MAX_LEVEL):
            raise ValueError(
                f"Red gear level must be in [{RED_MIN_LEVEL}, "
                f"{RED_MAX_LEVEL}], got {level}"
            )
        return 100.0 * (RED_BASE_OFFSET + (level - RED_MIN_LEVEL) * RED_LEVEL_COEF)
    raise ValueError(
        f"Unknown gear quality {quality!r}; expected one of {VALID_QUALITIES}"
    )


_HELM_CHEST_IMBUEMENT: tuple[tuple[int, str, float], ...] = (
    (120, "ATK", 20.0),
    (160, "DEF", 30.0),
    (200, "ATK", 50.0),
)
_GLOVES_BOOTS_IMBUEMENT: tuple[tuple[int, str, float], ...] = (
    (120, "DEF", 20.0),
    (160, "ATK", 30.0),
    (200, "DEF", 50.0),
)


def _imbuement_for_slot(slot: str) -> tuple[tuple[int, str, float], ...]:
    if slot in HELM_CHEST_SLOTS:
        return _HELM_CHEST_IMBUEMENT
    if slot in GLOVES_BOOTS_SLOTS:
        return _GLOVES_BOOTS_IMBUEMENT
    raise ValueError(f"Unknown gear slot {slot!r}; expected one of {VALID_SLOTS}")


def imbuement_bonus(slot: str, quality: str, level: int) -> tuple[float, float]:
    if quality != "red":
        return 0.0, 0.0
    atk = 0.0
    def_ = 0.0
    for milestone, stat, value in _imbuement_for_slot(slot):
        if level >= milestone:
            if stat == "ATK":
                atk += value
            else:
                def_ += value
    return atk, def_


_BASE_TO_LET_SLOTS:  frozenset[str] = frozenset({SLOT_HEAD, SLOT_BOOTS})
_BASE_TO_HP_SLOTS:   frozenset[str] = frozenset({SLOT_CHEST, SLOT_GLOVES})


@dataclass(frozen=True)
class PieceBonus:
    atk_pct: float = 0.0
    def_pct: float = 0.0
    let_pct: float = 0.0
    hp_pct:  float = 0.0

    def add(self, other: "PieceBonus") -> "PieceBonus":
        return PieceBonus(
            atk_pct=self.atk_pct + other.atk_pct,
            def_pct=self.def_pct + other.def_pct,
            let_pct=self.let_pct + other.let_pct,
            hp_pct=self.hp_pct + other.hp_pct,
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.atk_pct, self.def_pct, self.let_pct, self.hp_pct)


def piece_contribution(
    slot: str, quality: str, level: int, forge_mastery: int = 0,
) -> PieceBonus:
    if slot not in VALID_SLOTS:
        raise ValueError(f"Unknown slot {slot!r}; expected one of {VALID_SLOTS}")
    base = base_bonus_pct(quality, level)
    mastery_mult = 1.0 + max(0, int(forge_mastery)) * (MASTERY_PCT_PER_LEVEL / 100.0)
    channel = base * mastery_mult
    if slot in _BASE_TO_LET_SLOTS:
        base_let = channel
        base_hp = 0.0
    else:
        base_let = 0.0
        base_hp = channel
    imb_atk, imb_def = imbuement_bonus(slot, quality, level)
    return PieceBonus(
        atk_pct=imb_atk,
        def_pct=imb_def,
        let_pct=base_let,
        hp_pct=base_hp,
    )


def gearset_contribution(
    pieces: dict[str, "_AnyPiece"]
) -> PieceBonus:
    total = PieceBonus()
    for slot, p in pieces.items():
        mastery = getattr(p, "forge_mastery", 0) or 0
        total = total.add(piece_contribution(slot, p.quality, p.level, mastery))
    return total


def validate_piece(
    slot: str,
    quality: str,
    level: int,
    forge_mastery: int = 0,
    *,
    strict_mastery: bool = False,
) -> None:
    if slot not in VALID_SLOTS:
        raise ValueError(f"Unknown slot {slot!r}; expected one of {VALID_SLOTS}")
    if quality not in VALID_QUALITIES:
        raise ValueError(
            f"Unknown quality {quality!r}; expected one of {VALID_QUALITIES}"
        )
    base_bonus_pct(quality, level)
    if strict_mastery and quality == "red":
        if level > RED_MIN_LEVEL and forge_mastery < MASTERY_REQ_RED_ASCENSION:
            raise ValueError(
                f"Red gear above level {RED_MIN_LEVEL} requires forge_mastery "
                f"≥ {MASTERY_REQ_RED_ASCENSION}, got {forge_mastery}"
            )
        if level > 150 and forge_mastery < MASTERY_REQ_RED_LVL_200:
            raise ValueError(
                f"Red gear above level 150 requires forge_mastery "
                f"≥ {MASTERY_REQ_RED_LVL_200}, got {forge_mastery}"
            )


class _AnyPiece:
    quality: str
    level: int


__all__ = [
    "MYTHIC_BASE_OFFSET", "MYTHIC_LEVEL_COEF",
    "MYTHIC_MIN_LEVEL", "MYTHIC_MAX_LEVEL",
    "RED_BASE_OFFSET", "RED_LEVEL_COEF",
    "RED_MIN_LEVEL", "RED_MAX_LEVEL",
    "MASTERY_REQ_RED_ASCENSION", "MASTERY_REQ_RED_LVL_200",
    "SLOT_HEAD", "SLOT_CHEST", "SLOT_GLOVES", "SLOT_BOOTS",
    "HELM_CHEST_SLOTS", "GLOVES_BOOTS_SLOTS",
    "VALID_SLOTS", "VALID_QUALITIES",
    "base_bonus_pct", "imbuement_bonus", "piece_contribution",
    "gearset_contribution", "validate_piece",
    "PieceBonus",
]
