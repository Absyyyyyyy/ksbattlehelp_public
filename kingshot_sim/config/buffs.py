from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


MOOSE_LEVEL_PCT: dict[int, float] = {
    0: 0.0, 1: 1.5, 2: 2.0, 3: 2.5, 4: 3.0, 5: 3.5, 6: 4.0, 7: 5.0,
}
MOOSE_MAX_LEVEL = 7

GRIZZLY_LEVEL_PCT: dict[int, float] = {
    0: 0.0, 1: 1.5, 2: 2.0, 3: 2.5, 4: 3.0, 5: 3.5, 6: 4.0, 7: 4.5, 8: 5.0,
}
GRIZZLY_MAX_LEVEL = 8

_TIER1_PETS_LEVEL_PCT: dict[int, float] = {
    0:  0.0, 1: 2.5, 2: 3.0, 3: 3.5, 4: 4.0, 5: 5.0,
    6:  6.0, 7: 7.0, 8: 8.0, 9: 9.0, 10: 10.0,
}
RHINO_LEVEL_PCT    = _TIER1_PETS_LEVEL_PCT
PANTHER_LEVEL_PCT  = _TIER1_PETS_LEVEL_PCT
ELEPHANT_LEVEL_PCT = _TIER1_PETS_LEVEL_PCT
LION_LEVEL_PCT     = _TIER1_PETS_LEVEL_PCT
TIER1_PET_MAX_LEVEL = 10


APPOINT_FIELD_COMMANDER_LET_PCT: float = 15.0
APPOINT_MARSHAL_ATK_PCT:         float = 5.0
APPOINT_KING_PCT:                float = 5.0


TURRET_LEVEL_PCT: dict[int, float] = {
    0: 0.0, 1: 8.0, 2: 12.0, 3: 15.0, 4: 20.0,
}
TURRET_MAX_LEVEL = 4


CityBuffLevel = Literal[0, 10, 20]


@dataclass(frozen=True)
class Buffs:
    city_let:  CityBuffLevel = 0
    city_atk:  CityBuffLevel = 0
    city_def:  CityBuffLevel = 0
    city_hp:   CityBuffLevel = 0
    city_enemy_atk_down: CityBuffLevel = 0
    city_enemy_def_down: CityBuffLevel = 0
    moose_level:    int = 0
    grizzly_level:  int = 0
    rhino_level:    int = 0
    panther_level:  int = 0
    elephant_level: int = 0
    lion_level:     int = 0
    appoint_field_commander: bool = False
    appoint_marshal:         bool = False
    appoint_king:            bool = False
    turrets: int = 0
    ocr_own_atk_pct: float = 0.0
    ocr_own_def_pct: float = 0.0
    ocr_own_let_pct: float = 0.0
    ocr_own_hp_pct:  float = 0.0
    ocr_enemy_atk_down_pct: float = 0.0
    ocr_enemy_def_down_pct: float = 0.0
    ocr_enemy_let_down_pct: float = 0.0
    ocr_enemy_hp_down_pct:  float = 0.0

    def __post_init__(self) -> None:
        for fld in ("city_let", "city_atk", "city_def", "city_hp",
                    "city_enemy_atk_down", "city_enemy_def_down"):
            v = getattr(self, fld)
            if v not in (0, 10, 20):
                raise ValueError(
                    f"Buffs.{fld}={v!r} not allowed; must be 0, 10, or 20"
                )
        for fld, mx in (("moose_level", MOOSE_MAX_LEVEL),
                         ("grizzly_level", GRIZZLY_MAX_LEVEL),
                         ("rhino_level", TIER1_PET_MAX_LEVEL),
                         ("panther_level", TIER1_PET_MAX_LEVEL),
                         ("elephant_level", TIER1_PET_MAX_LEVEL),
                         ("lion_level", TIER1_PET_MAX_LEVEL),
                         ("turrets", TURRET_MAX_LEVEL)):
            v = getattr(self, fld)
            if not (0 <= v <= mx):
                raise ValueError(
                    f"Buffs.{fld}={v!r} out of range [0, {mx}]"
                )


    def appoint_additive_pct(self, stat: str) -> float:
        total = 0.0
        if self.appoint_king:
            total += APPOINT_KING_PCT
        if stat == "atk" and self.appoint_marshal:
            total += APPOINT_MARSHAL_ATK_PCT
        elif stat == "let" and self.appoint_field_commander:
            total += APPOINT_FIELD_COMMANDER_LET_PCT
        return total


    def own_atk_multiplier(self) -> float:
        return ((1.0 + self.city_atk / 100.0)
                * (1.0 + RHINO_LEVEL_PCT[self.rhino_level] / 100.0))

    def own_def_multiplier(self) -> float:
        return ((1.0 + self.city_def / 100.0)
                * (1.0 + LION_LEVEL_PCT[self.lion_level] / 100.0))

    def own_let_multiplier(self) -> float:
        return ((1.0 + self.city_let / 100.0)
                * (1.0 + PANTHER_LEVEL_PCT[self.panther_level] / 100.0)
                * (1.0 + TURRET_LEVEL_PCT[self.turrets] / 100.0))

    def own_hp_multiplier(self) -> float:
        return ((1.0 + self.city_hp / 100.0)
                * (1.0 + ELEPHANT_LEVEL_PCT[self.elephant_level] / 100.0))


    def enemy_atk_down_multiplier(self) -> float:
        return 1.0 - self.city_enemy_atk_down / 100.0

    def enemy_def_down_multiplier(self) -> float:
        return 1.0 - self.city_enemy_def_down / 100.0

    def enemy_let_down_multiplier(self) -> float:
        return 1.0 - GRIZZLY_LEVEL_PCT[self.grizzly_level] / 100.0

    def enemy_hp_down_multiplier(self) -> float:
        return 1.0 - MOOSE_LEVEL_PCT[self.moose_level] / 100.0


    def is_empty(self) -> bool:
        return (self.city_let == 0 and self.city_atk == 0 and self.city_def == 0
                  and self.city_hp == 0 and self.city_enemy_atk_down == 0
                  and self.city_enemy_def_down == 0 and self.moose_level == 0
                  and self.grizzly_level == 0 and self.rhino_level == 0
                  and self.panther_level == 0 and self.elephant_level == 0
                  and self.lion_level == 0
                  and not self.appoint_field_commander
                  and not self.appoint_marshal
                  and not self.appoint_king
                  and self.turrets == 0
                  and self.ocr_own_atk_pct == 0.0 and self.ocr_own_def_pct == 0.0
                  and self.ocr_own_let_pct == 0.0 and self.ocr_own_hp_pct == 0.0
                  and self.ocr_enemy_atk_down_pct == 0.0
                  and self.ocr_enemy_def_down_pct == 0.0
                  and self.ocr_enemy_let_down_pct == 0.0
                  and self.ocr_enemy_hp_down_pct == 0.0)


__all__ = [
    "Buffs",
    "MOOSE_LEVEL_PCT", "GRIZZLY_LEVEL_PCT",
    "RHINO_LEVEL_PCT", "PANTHER_LEVEL_PCT",
    "ELEPHANT_LEVEL_PCT", "LION_LEVEL_PCT",
    "MOOSE_MAX_LEVEL", "GRIZZLY_MAX_LEVEL", "TIER1_PET_MAX_LEVEL",
    "TURRET_LEVEL_PCT", "TURRET_MAX_LEVEL",
    "APPOINT_FIELD_COMMANDER_LET_PCT",
    "APPOINT_MARSHAL_ATK_PCT",
    "APPOINT_KING_PCT",
]
