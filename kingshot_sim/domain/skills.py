from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .enums import SquadType, SkillSpecial, TriggerKind, SideScope


@dataclass(frozen=True)
class SkillTrigger:
    kind: TriggerKind = TriggerKind.PASSIVE
    chance: Optional[float] = None
    period: Optional[int] = None
    duration: int = 0
    period_offset: int = 0

    @classmethod
    def passive(cls) -> "SkillTrigger":
        return cls(kind=TriggerKind.PASSIVE)

    @classmethod
    def rng_round(cls, p: float, duration: int = 0) -> "SkillTrigger":
        return cls(kind=TriggerKind.RNG_PER_ROUND, chance=p, duration=duration)

    @classmethod
    def rng_attack(cls, p: float, duration: int = 0) -> "SkillTrigger":
        return cls(kind=TriggerKind.RNG_PER_ATTACK, chance=p, duration=duration)

    @classmethod
    def periodic(cls, period: int, duration: int = 1, offset: int = 0) -> "SkillTrigger":
        return cls(kind=TriggerKind.PERIODIC, period=period, duration=duration, period_offset=offset)

    @classmethod
    def pity(cls, base_chance: float, duration: int = 1) -> "SkillTrigger":
        return cls(kind=TriggerKind.PITY, chance=base_chance, duration=duration)


@dataclass(frozen=True)
class Effect:
    op: int
    value: float
    target_squads: frozenset[SquadType] = field(
        default_factory=lambda: frozenset({SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER})
    )
    target_enemy_squads: frozenset[SquadType] = field(default_factory=frozenset)

    @classmethod
    def all_squads(cls, op: int, value: float) -> "Effect":
        return cls(op=op, value=value)


@dataclass(frozen=True)
class Skill:
    name: str
    trigger: SkillTrigger
    effects: tuple[Effect, ...]
    special: SkillSpecial = SkillSpecial.NONE
    side_scope: SideScope = "both"
    hero: str = ""
    slot: str = ""
    description: str = ""

    def is_active_for_side(self, side: str) -> bool:
        if self.side_scope == "both":
            return True
        return self.side_scope == side


@dataclass(frozen=True)
class CompiledSkill:
    skill: Skill
    pity_state_id: str = ""


__all__ = ["SkillTrigger", "Effect", "Skill", "CompiledSkill"]
