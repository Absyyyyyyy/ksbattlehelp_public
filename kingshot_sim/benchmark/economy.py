from __future__ import annotations
from typing import Final, Optional

from ..data.reference import HERO_GENERATION, star_from_level
from .reference import CASH_ONLY_HEROES, SCENARIOS

STAR_SHARD_CUMULATIVE: Final[dict[int, int]] = {
    0: 0, 1: 10, 2: 50, 3: 165, 4: 465, 5: 1065,
}

SKILL_COMPLETE_STAR: Final[int] = 4
MAX_STAR: Final[int] = 5

PROFILE_TARGET_STAR: Final[dict[str, int]] = {
    "f2p": SKILL_COMPLETE_STAR, "spender": SKILL_COMPLETE_STAR, "whale": MAX_STAR,
}

PROFILE_WEIGHTS: Final[dict[str, dict[str, float]]] = {
    "f2p":     {"defense": 0.40, "solo_atk": 0.30, "garrison": 0.20, "rally_atk": 0.10},
    "spender": {"defense": 0.30, "solo_atk": 0.30, "garrison": 0.30, "rally_atk": 0.10},
    "whale":   {"defense": 0.10, "solo_atk": 0.20, "garrison": 0.35, "rally_atk": 0.35},
}
PLAY_WEIGHTS: Final[dict[str, dict[str, float]]] = {
    "defense":  {"defense": 0.60, "solo_atk": 0.20, "garrison": 0.15, "rally_atk": 0.05},
    "attack":   {"defense": 0.20, "solo_atk": 0.55, "garrison": 0.10, "rally_atk": 0.15},
    "garrison": {"defense": 0.20, "solo_atk": 0.10, "garrison": 0.55, "rally_atk": 0.15},
    "rally":    {"defense": 0.10, "solo_atk": 0.20, "garrison": 0.25, "rally_atk": 0.45},
}
PROFILE_INCOME: Final[dict[str, int]] = {"f2p": 450, "spender": 1000, "whale": 2500}
PROFILE_WIDGET: Final[dict[str, int]] = {"f2p": 0, "spender": 4, "whale": 10}

for _p, _w in (*PROFILE_WEIGHTS.items(), *PLAY_WEIGHTS.items()):
    assert set(_w) == set(SCENARIOS), f"weights[{_p}] keys != SCENARIOS"


def player_profile(widget_target: int, shard_income: int) -> str:
    if widget_target <= 2 and shard_income <= 450:
        return "f2p"
    if widget_target >= 8 and shard_income >= 2000:
        return "whale"
    return "spender"

F2P_SHARDS_PER_GEN: Final[int] = 450

ROULETTE_HERO_BY_GEN: Final[dict[int, str]] = {
    1: "Saul", 2: "Zoe", 3: "Petra", 4: "Rosa",
    5: "Long Fei", 6: "Sophia", 7: "Wee & Woo",
}


def acquisition_tier(hero: str) -> str:
    if hero in CASH_ONLY_HEROES:
        return "cash"
    g = HERO_GENERATION.get(hero)
    if g is not None and ROULETTE_HERO_BY_GEN.get(g) == hero:
        return "roulette"
    return "generic"


def shards_to_star(from_level: str, target_star: int) -> int:
    cur = star_from_level(from_level)
    if cur >= target_star:
        return 0
    return STAR_SHARD_CUMULATIVE[target_star] - STAR_SHARD_CUMULATIVE[cur]


def shards_to_skill_complete(from_level: str) -> int:
    return shards_to_star(from_level, SKILL_COMPLETE_STAR)


def gens_to_afford(shards: int) -> float:
    return shards / F2P_SHARDS_PER_GEN if shards > 0 else 0.0


def gens_to_save(cost: int, income: int, have: int = 0) -> Optional[int]:
    import math
    need = max(0, int(cost) - int(have))
    if need <= 0:
        return 0
    if income <= 0:
        return None
    return math.ceil(need / income)


__all__ = [
    "STAR_SHARD_CUMULATIVE", "SKILL_COMPLETE_STAR", "MAX_STAR",
    "F2P_SHARDS_PER_GEN", "ROULETTE_HERO_BY_GEN", "PROFILE_TARGET_STAR",
    "PROFILE_WEIGHTS", "PLAY_WEIGHTS", "PROFILE_INCOME", "PROFILE_WIDGET",
    "player_profile", "acquisition_tier", "shards_to_star",
    "shards_to_skill_complete", "gens_to_afford", "gens_to_save",
]
