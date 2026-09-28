from __future__ import annotations
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from ..domain.enums import SquadType


_TG3_INF_PROC   = 0.25
_TG3_INF_RED    = 0.36
_TG3_CAV_PROC   = 0.10
_TG3_CAV_BONUS  = 1.00
_TG3_ARC_PROC   = 0.20
_TG3_ARC_BONUS  = 0.50

_TG5_INF_PROC   = 0.375
_TG5_INF_RED    = 0.36
_TG5_CAV_PROC   = 0.15
_TG5_CAV_BONUS  = 1.00
_TG5_ARC_PROC   = 0.30
_TG5_ARC_BONUS  = 0.50

_TG8_INF_EXTRA_RED   = 0.10
_TG8_ARC_EXTRA_BONUS = 0.25
_TG8_CAV_DEF_PROC    = 0.10
_TG8_CAV_DEF_RED     = 0.50

TG8_INF_DEF_PCT_BONUS: float = 4.0
TG8_ARC_ATK_PCT_BONUS: float = 4.0


def tg8_always_on() -> bool:
    from .user_data import get_data_override
    raw = get_data_override("engine.tg8_always_on", 0)
    return bool(int(raw))


def _skill_set_for_tg(tg: int) -> str:
    if tg < 3:
        return "none"
    if tg < 5:
        return "tg3"
    return "tg5plus"


def troop_skill_outgoing_mult(squad: "SquadType", tg: int) -> float:
    from ..domain.enums import SquadType
    skill = _skill_set_for_tg(tg)
    if skill == "none":
        return 1.0

    if squad == SquadType.INFANTRY:
        return 1.0

    if squad == SquadType.CAVALRY:
        if skill == "tg3":
            return 1.0 + _TG3_CAV_PROC * _TG3_CAV_BONUS
        return 1.0 + _TG5_CAV_PROC * _TG5_CAV_BONUS

    if skill == "tg3":
        return 1.0 + _TG3_ARC_PROC * _TG3_ARC_BONUS
    base = 1.0 + _TG5_ARC_PROC * _TG5_ARC_BONUS
    if tg < 8:
        return base
    if tg8_always_on():
        return base * (1.0 + _TG8_ARC_EXTRA_BONUS)
    p = _TG5_ARC_PROC
    return (1.0 - p) * 1.0 + p * (1.0 + _TG5_ARC_BONUS + _TG8_ARC_EXTRA_BONUS)


def troop_skill_incoming_mult(squad: "SquadType", tg: int) -> float:
    from ..domain.enums import SquadType
    skill = _skill_set_for_tg(tg)
    if skill == "none" and not (squad == SquadType.CAVALRY and tg >= 8):
        return 1.0

    if squad == SquadType.CAVALRY:
        if tg < 8:
            return 1.0
        return 1.0 - _TG8_CAV_DEF_PROC * _TG8_CAV_DEF_RED

    if squad == SquadType.ARCHER:
        return 1.0

    if skill == "tg3":
        return 1.0 - _TG3_INF_PROC * _TG3_INF_RED
    base = 1.0 - _TG5_INF_PROC * _TG5_INF_RED
    if tg < 8:
        return base
    if tg8_always_on():
        return base * (1.0 - _TG8_INF_EXTRA_RED)
    p = _TG5_INF_PROC
    return (1.0 - p) * 1.0 + p * (1.0 - _TG5_INF_RED - _TG8_INF_EXTRA_RED)


def roll_tg_outgoing(rng, squad: "SquadType", tg: int) -> float:
    from ..domain.enums import SquadType
    skill = _skill_set_for_tg(tg)
    if skill == "none":
        return 1.0
    if squad == SquadType.INFANTRY:
        return 1.0

    if squad == SquadType.CAVALRY:
        proc = _TG3_CAV_PROC if skill == "tg3" else _TG5_CAV_PROC
        bonus = _TG3_CAV_BONUS if skill == "tg3" else _TG5_CAV_BONUS
        if rng.random() < proc:
            return 1.0 + bonus
        return 1.0

    if skill == "tg3":
        if rng.random() < _TG3_ARC_PROC:
            return 1.0 + _TG3_ARC_BONUS
        return 1.0
    proc_fired = rng.random() < _TG5_ARC_PROC
    if tg < 8:
        return (1.0 + _TG5_ARC_BONUS) if proc_fired else 1.0
    if tg8_always_on():
        base = (1.0 + _TG5_ARC_BONUS) if proc_fired else 1.0
        return base * (1.0 + _TG8_ARC_EXTRA_BONUS)
    if proc_fired:
        return 1.0 + _TG5_ARC_BONUS + _TG8_ARC_EXTRA_BONUS
    return 1.0


def roll_tg_incoming(rng, squad: "SquadType", tg: int) -> float:
    from ..domain.enums import SquadType
    skill = _skill_set_for_tg(tg)

    if squad == SquadType.CAVALRY:
        if tg >= 8 and rng.random() < _TG8_CAV_DEF_PROC:
            return 1.0 - _TG8_CAV_DEF_RED
        return 1.0

    if squad == SquadType.ARCHER:
        return 1.0

    if skill == "none":
        return 1.0
    if skill == "tg3":
        if rng.random() < _TG3_INF_PROC:
            return 1.0 - _TG3_INF_RED
        return 1.0
    proc_fired = rng.random() < _TG5_INF_PROC
    if tg < 8:
        return (1.0 - _TG5_INF_RED) if proc_fired else 1.0
    if tg8_always_on():
        base = (1.0 - _TG5_INF_RED) if proc_fired else 1.0
        return base * (1.0 - _TG8_INF_EXTRA_RED)
    if proc_fired:
        return 1.0 - _TG5_INF_RED - _TG8_INF_EXTRA_RED
    return 1.0


def dominant_tg(groups: Iterable) -> int:
    from .reference import parse_tier_label
    best_count = -1
    best_tg = 0
    for g in groups:
        try:
            _, tg = parse_tier_label(g.tier)
        except ValueError:
            continue
        if g.count > best_count or (g.count == best_count and tg > best_tg):
            best_count = g.count
            best_tg = tg
    return best_tg


__all__ = [
    "tg8_always_on",
    "troop_skill_outgoing_mult",
    "troop_skill_incoming_mult",
    "roll_tg_outgoing",
    "roll_tg_incoming",
    "dominant_tg",
    "TG8_INF_DEF_PCT_BONUS",
    "TG8_ARC_ATK_PCT_BONUS",
]
