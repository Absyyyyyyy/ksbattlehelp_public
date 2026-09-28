from __future__ import annotations
from typing import Final

SCENARIOS: Final[tuple[str, ...]] = ("solo_atk", "rally_atk", "defense", "garrison")

SCENARIO_ROLE: Final[dict[str, tuple[bool, bool]]] = {
    "solo_atk":  (True, True),
    "rally_atk": (True, False),
    "defense":   (False, False),
    "garrison":  (False, False),
}

_BALANCED: Final[tuple[float, float, float]] = (1 / 3, 1 / 3, 1 / 3)
_ATK_STD:  Final[tuple[float, float, float]] = (0.5, 0.2, 0.3)
_ATK_ARC:  Final[tuple[float, float, float]] = (0.5, 0.1, 0.4)
_WALL_STD: Final[tuple[float, float, float]] = (0.6, 0.2, 0.2)
_WALL_CAV: Final[tuple[float, float, float]] = (0.6, 0.4, 0.0)
_ARCHER_META_GENS: Final[frozenset[int]] = frozenset({4, 5, 6})


def scenario_formations(gen: int) -> dict[str, tuple[
        tuple[float, float, float], tuple[float, float, float]]]:
    arc = gen in _ARCHER_META_GENS
    atk = _ATK_ARC if arc else _ATK_STD
    wall = _WALL_CAV if arc else _WALL_STD
    return {
        "solo_atk":  (_ATK_STD, _BALANCED),
        "rally_atk": (atk, wall),
        "defense":   (_BALANCED, _ATK_STD),
        "garrison":  (wall, atk),
    }

CASH_ONLY_HEROES: Final[frozenset[str]] = frozenset({"Amadeus", "Helga"})

GEN_TROOP_TIER: Final[dict[int, str]] = {
    1: "T10",
    2: "T10.TG3",
    3: "T10.TG4",
    4: "T10.TG5",
    5: "T10.TG5",
    6: "T10.TG8",
    7: "T10.TG8",
}

GEN_BONUS_PCT: Final[dict[int, float]] = {
    1: 100.0,
    2: 150.0,
    3: 200.0,
    4: 250.0,
    5: 300.0,
    6: 350.0,
    7: 400.0,
}

GEN_TROOP_COUNT: Final[dict[int, int]] = {g: 100_000 for g in range(1, 8)}

GEN_LEADER_MAX: Final[dict[int, float]] = {
    1: 200.0, 2: 240.0, 3: 290.0, 4: 370.0, 5: 444.0, 6: 540.0, 7: 650.0,
}

GEN_LINEUPS: Final[dict[int, dict[str, tuple[str, str, str]]]] = {
    1: {
        "solo_atk":  ("Amadeus", "Jabel", "Saul"),
        "rally_atk": ("Amadeus", "Jabel", "Saul"),
        "defense":   ("Amadeus", "Jabel", "Saul"),
    },
    2: {
        "solo_atk":  ("Amadeus", "Hilde", "Marlin"),
        "rally_atk": ("Amadeus", "Hilde", "Marlin"),
        "defense":   ("Zoe", "Hilde", "Saul"),
    },
    3: {
        "solo_atk":  ("Amadeus", "Petra", "Jaeger"),
        "rally_atk": ("Amadeus", "Petra", "Marlin"),
        "defense":   ("Eric", "Hilde", "Jaeger"),
    },
    4: {
        "solo_atk":  ("Alcar", "Margot", "Rosa"),
        "rally_atk": ("Amadeus", "Petra", "Rosa"),
        "defense":   ("Alcar", "Margot", "Jaeger"),
    },
    5: {
        "solo_atk":  ("Long Fei", "Thrud", "Vivian"),
        "rally_atk": ("Long Fei", "Thrud", "Rosa"),
        "defense":   ("Alcar", "Margot", "Vivian"),
    },
    6: {
        "solo_atk":  ("Triton", "Sophia", "Yang"),
        "rally_atk": ("Triton", "Thrud", "Yang"),
        "defense":   ("Triton", "Sophia", "Vivian"),
    },
    7: {
        "solo_atk":  ("Charles", "Ava", "Wee & Woo"),
        "rally_atk": ("Charles", "Ava", "Yang"),
        "defense":   ("Charles", "Sophia", "Wee & Woo"),
    },
}

__all__ = [
    "SCENARIOS", "SCENARIO_ROLE", "scenario_formations", "CASH_ONLY_HEROES",
    "GEN_TROOP_TIER", "GEN_BONUS_PCT", "GEN_TROOP_COUNT", "GEN_LEADER_MAX",
    "GEN_LINEUPS",
]
