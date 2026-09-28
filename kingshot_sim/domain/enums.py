from __future__ import annotations
from enum import Enum
from typing import Literal


class SquadType(str, Enum):
    INFANTRY = "Inf"
    CAVALRY = "Cav"
    ARCHER = "Arc"

    @classmethod
    def all(cls) -> tuple["SquadType", ...]:
        return (cls.INFANTRY, cls.CAVALRY, cls.ARCHER)


COUNTERS: dict[SquadType, SquadType] = {
    SquadType.INFANTRY: SquadType.CAVALRY,
    SquadType.CAVALRY: SquadType.ARCHER,
    SquadType.ARCHER: SquadType.INFANTRY,
}


def counters(attacker: SquadType, target: SquadType) -> bool:
    return COUNTERS[attacker] == target


class Family(str, Enum):
    DAMAGE_UP = "DamageUp"
    DEFENSE_UP = "DefenseUp"
    OPP_DAMAGE_DOWN = "OppDamageDown"
    OPP_DEFENSE_DOWN = "OppDefenseDown"


OP_TO_FAMILY: dict[int, Family] = {
    101: Family.DAMAGE_UP,
    102: Family.DAMAGE_UP,
    103: Family.DAMAGE_UP,
    111: Family.DEFENSE_UP,
    112: Family.DEFENSE_UP,
    113: Family.DEFENSE_UP,
    201: Family.OPP_DAMAGE_DOWN,
    202: Family.OPP_DAMAGE_DOWN,
    203: Family.OPP_DAMAGE_DOWN,
    211: Family.OPP_DEFENSE_DOWN,
    212: Family.OPP_DEFENSE_DOWN,
}


def family_for_op(op: int) -> Family:
    return OP_TO_FAMILY[op]


class SkillSpecial(str, Enum):
    NONE = "none"
    TARGET_DEBUFF_ON_HIT = "target_debuff"
    PITY_PROC = "pity_proc"
    DODGE = "dodge"
    CONDITIONAL_TERROR = "conditional_terror"
    APPLY_TERROR_ON_HIT = "apply_terror"


class TriggerKind(str, Enum):
    PASSIVE = "passive"
    RNG_PER_ROUND = "rng_round"
    RNG_PER_ATTACK = "rng_attack"
    PERIODIC = "periodic"
    TIMED = "timed"
    PITY = "pity"


class BattleType(str, Enum):
    OPEN_FIELD = "open"
    RALLY_VS_GARRISON = "rally"
    OUTPOST_LV4 = "outpost"
    BEAR_HUNT = "bear"


class RNGMode(str, Enum):
    EXPECTED = "expected"
    STOCHASTIC = "stochastic"
    BEST_CASE = "best"
    WORST_CASE = "worst"


SideScope = Literal["both", "rally", "defender"]

BattleSide = Literal["rally", "defender", "solo"]
