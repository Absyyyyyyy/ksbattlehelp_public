from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

from ..config.buffs import Buffs
from ..domain.enums import SquadType
from ..domain.skills import Skill, SkillTrigger


@dataclass
class TimedEffect:
    skill: Skill
    remaining_rounds: int


@dataclass
class SquadState:
    squad_type: SquadType

    base_atk: float
    base_let: float
    base_def: float
    base_hp: float
    atk_factor: float
    let_factor: float
    def_factor: float
    hp_factor: float


    count: int
    initial_count: int

    dominant_tg: int = 0

    transient_opp_def_down_pct: float = 0.0

    terror_remaining_rounds: int = 0

    pending_kills: float = 0.0

    @property
    def att_per_troop(self) -> float:
        return self.base_atk * self.let_factor * self.base_let / 100 if False else \
               self.base_atk * self.base_let * self.let_factor / 100

    @property
    def def_per_troop(self) -> float:
        return self.base_def * self.def_factor * self.base_hp * self.hp_factor / 100


@dataclass
class FighterState:
    label: str
    side: str
    squads: dict[SquadType, SquadState]

    skills: list[Skill] = field(default_factory=list)

    active_timed: list[TimedEffect] = field(default_factory=list)

    pity_state: dict[int, int] = field(default_factory=dict)

    dodge_chance: float = 0.0

    buffs: Buffs = field(default_factory=Buffs)

    def total_troops(self) -> int:
        return sum(s.count for s in self.squads.values())

    def initial_total(self) -> int:
        return sum(s.initial_count for s in self.squads.values())

    def is_defeated(self) -> bool:
        return self.total_troops() <= 0

    def squad(self, st: SquadType) -> SquadState:
        return self.squads[st]


@dataclass
class RoundResult:
    round_idx: int
    kills_on_attacker: dict[SquadType, int] = field(default_factory=dict)
    kills_on_defender: dict[SquadType, int] = field(default_factory=dict)
    rng_triggers: list[str] = field(default_factory=list)


@dataclass
class BattleResult:
    rounds: list[RoundResult]
    attacker_initial: dict[SquadType, int]
    defender_initial: dict[SquadType, int]
    attacker_final: dict[SquadType, int]
    defender_final: dict[SquadType, int]
    winner: Optional[str]
    score: float

    def attacker_lost(self) -> int:
        return sum(self.attacker_initial[st] - self.attacker_final[st] for st in SquadType.all())

    def defender_lost(self) -> int:
        return sum(self.defender_initial[st] - self.defender_final[st] for st in SquadType.all())


__all__ = [
    "TimedEffect", "SquadState", "FighterState",
    "RoundResult", "BattleResult",
]
