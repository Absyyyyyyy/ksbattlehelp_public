from __future__ import annotations
import math
from typing import Final


BASE_LETHALITY: Final[int] = 10
BASE_DEFENSE: Final[int] = 10

TIER_BASE_STATS: Final[dict[str, dict[str, int]]] = {
    "T1":    dict(inf_atk=63,   inf_hp=189,   cav_atk=189,   cav_hp=63,   arc_atk=252,   arc_hp=47),
    "T2":    dict(inf_atk=94,   inf_hp=283,   cav_atk=283,   cav_hp=94,   arc_atk=378,   arc_hp=71),
    "T3":    dict(inf_atk=132,  inf_hp=397,   cav_atk=397,   cav_hp=132,  arc_atk=529,   arc_hp=99),
    "T4":    dict(inf_atk=172,  inf_hp=516,   cav_atk=516,   cav_hp=172,  arc_atk=688,   arc_hp=129),
    "T5":    dict(inf_atk=206,  inf_hp=619,   cav_atk=619,   cav_hp=206,  arc_atk=825,   arc_hp=155),
    "T6":    dict(inf_atk=243,  inf_hp=730,   cav_atk=730,   cav_hp=243,  arc_atk=974,   arc_hp=183),
    "T7":    dict(inf_atk=287,  inf_hp=862,   cav_atk=862,   cav_hp=287,  arc_atk=1149,  arc_hp=215),
    "T8":    dict(inf_atk=339,  inf_hp=1017,  cav_atk=1017,  cav_hp=339,  arc_atk=1356,  arc_hp=254),
    "T9":    dict(inf_atk=400,  inf_hp=1200,  cav_atk=1200,  cav_hp=400,  arc_atk=1600,  arc_hp=300),
    "T10":   dict(inf_atk=472,  inf_hp=1416,  cav_atk=1416,  cav_hp=472,  arc_atk=1888,  arc_hp=354),
    "T11":   dict(inf_atk=566,  inf_hp=1699,  cav_atk=1699,  cav_hp=566,  arc_atk=2266,  arc_hp=390),
    "T10.1": dict(inf_atk=491, inf_hp=1473, cav_atk=1473, cav_hp=491, arc_atk=1964, arc_hp=368),
    "T10.2": dict(inf_atk=515, inf_hp=1546, cav_atk=1546, cav_hp=515, arc_atk=2062, arc_hp=387),
    "T10.3": dict(inf_atk=541, inf_hp=1624, cav_atk=1624, cav_hp=541, arc_atk=2165, arc_hp=406),
    "T10.4": dict(inf_atk=568, inf_hp=1705, cav_atk=1705, cav_hp=568, arc_atk=2273, arc_hp=426),
    "T10.5": dict(inf_atk=597, inf_hp=1790, cav_atk=1790, cav_hp=597, arc_atk=2387, arc_hp=448),
}


TG_MULTIPLIERS: Final[dict[int, float]] = {
    0: 1.000,
    1: 1.040,
    2: 1.092,
    3: 1.147,
    4: 1.204,
    5: 1.265,
    6: 1.328,
    7: 1.395,
    8: 1.464,
}

TIER_RANGE:  Final[tuple[int, int]] = (1, 11)
TG_RANGE:    Final[tuple[int, int]] = (0, 8)


def make_tier_label(tier: int, tg: int = 0) -> str:
    lo_t, hi_t = TIER_RANGE
    lo_g, hi_g = TG_RANGE
    if not (lo_t <= tier <= hi_t):
        raise ValueError(f"tier={tier} out of range [{lo_t}, {hi_t}]")
    if not (lo_g <= tg <= hi_g):
        raise ValueError(f"tg={tg} out of range [{lo_g}, {hi_g}]")
    if tg == 0:
        return f"T{tier}"
    return f"T{tier}.TG{tg}"


def parse_tier_label(label: str) -> tuple[int, int]:
    import re
    s = label.strip()
    m = re.fullmatch(r"T(\d+)\.TG(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"T(\d+)\.(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"T(\d+)", s)
    if m:
        return int(m.group(1)), 0
    raise ValueError(f"Cannot parse tier label {label!r}")


def _install_canonical_aliases() -> None:
    legacy_keys = [k for k in list(TIER_BASE_STATS.keys()) if "." in k and "TG" not in k]
    for legacy in legacy_keys:
        tier, tg = parse_tier_label(legacy)
        canonical = make_tier_label(tier, tg)
        if canonical not in TIER_BASE_STATS:
            TIER_BASE_STATS[canonical] = TIER_BASE_STATS[legacy]


_install_canonical_aliases()


def _seed_tg_variants() -> None:
    lo_t, hi_t = TIER_RANGE
    for tier_int in range(lo_t, hi_t + 1):
        tier0_label = f"T{tier_int}"
        if tier0_label not in TIER_BASE_STATS:
            continue
        base = TIER_BASE_STATS[tier0_label]
        for tg in range(1, 9):
            mult = TG_MULTIPLIERS.get(tg)
            if mult is None:
                continue
            canonical = make_tier_label(tier_int, tg)
            if canonical in TIER_BASE_STATS:
                continue
            TIER_BASE_STATS[canonical] = {
                stat: round(value * mult) for stat, value in base.items()
            }


_seed_tg_variants()

VALID_TIERS: Final[tuple[str, ...]] = tuple(TIER_BASE_STATS.keys())


_TIER_STAT_KEYS: Final[tuple[str, ...]] = (
    "inf_atk", "inf_hp", "cav_atk", "cav_hp", "arc_atk", "arc_hp",
)


def tier_stat(tier: str, stat: str) -> float:
    if stat not in _TIER_STAT_KEYS:
        raise KeyError(f"Unknown tier stat: {stat!r}. Expected one of {_TIER_STAT_KEYS}.")

    from .user_data import get_data_override
    key = f"tier_stat.{tier}.{stat}"

    if tier in TIER_BASE_STATS:
        raw = TIER_BASE_STATS[tier][stat]
        return float(get_data_override(key, raw))

    overridden = get_data_override(key, None)
    if overridden is None:
        raise KeyError(
            f"Unknown tier {tier!r}: not in TIER_BASE_STATS and no "
            f"'{key}' override registered. To introduce a new tier, register "
            f"all 6 stats: {_TIER_STAT_KEYS}."
        )
    return float(overridden)


def interpolated_tier_stat(level: float, tg: int, stat: str) -> float:
    lo_t, hi_t = TIER_RANGE
    level = max(float(lo_t), min(float(hi_t), float(level)))
    lo = int(math.floor(level))
    hi = int(math.ceil(level))
    stat_lo = tier_stat(make_tier_label(lo, tg), stat)
    if lo == hi:
        return stat_lo
    stat_hi = tier_stat(make_tier_label(hi, tg), stat)
    f = level - lo
    return (1.0 - f) * stat_lo + f * stat_hi


def valid_tiers() -> tuple[str, ...]:
    from .user_data import keys_with_prefix

    extra: set[str] = set()
    by_tier: dict[str, set[str]] = {}
    for k in keys_with_prefix("tier_stat."):
        suffix = k[len("tier_stat."):]
        if "." not in suffix:
            continue
        tier, _, stat = suffix.rpartition(".")
        if not tier or stat not in _TIER_STAT_KEYS:
            continue
        by_tier.setdefault(tier, set()).add(stat)

    for tier, stats in by_tier.items():
        if tier in TIER_BASE_STATS:
            continue
        if stats >= set(_TIER_STAT_KEYS):
            extra.add(tier)

    return VALID_TIERS + tuple(sorted(extra))


def valid_tier_tg_pairs() -> tuple[tuple[int, int], ...]:
    pairs: set[tuple[int, int]] = set()
    for label in valid_tiers():
        try:
            pairs.add(parse_tier_label(label))
        except ValueError:
            continue
    return tuple(sorted(pairs))


LEVEL_FRACTION: Final[dict[str, float]] = {
    "0_0": 0.1261, "0_1": 0.1379, "0_2": 0.1496, "0_3": 0.1614, "0_4": 0.1731, "0_5": 0.1849,
    "1_0": 0.2060, "1_1": 0.2224, "1_2": 0.2389, "1_3": 0.2553, "1_4": 0.2718, "1_5": 0.2882,
    "2_0": 0.3178, "2_1": 0.3407, "2_2": 0.3638, "2_3": 0.3868, "2_4": 0.4098, "2_5": 0.4328,
    "3_0": 0.4742, "3_1": 0.5065, "3_2": 0.5386, "3_3": 0.5708, "3_4": 0.6031, "3_5": 0.6353,
    "4_0": 0.6933, "4_1": 0.7384, "4_2": 0.7835, "4_3": 0.8286, "4_4": 0.8737, "4_5": 0.9189,
    "MAX": 1.0,
}

VALID_LEVELS: Final[tuple[str, ...]] = tuple(LEVEL_FRACTION.keys())

STAR_TO_MAX_SKILL_LVL: Final[dict[int, tuple[int, int, int]]] = {
    0: (1, 0, 0),
    1: (2, 2, 0),
    2: (3, 3, 3),
    3: (4, 4, 4),
    4: (5, 5, 5),
    5: (5, 5, 5),
}

_SKILL_SLOT_IDX: Final[dict[str, int]] = {"sk1": 0, "sk2": 1, "sk3": 2}

HERO_LEADER_MAX: Final[dict[str, float]] = {
    "Amadeus": 260.20,
    "Helga":   200.16,
    "Jabel":   200.16,
    "Saul":    200.16,
    "Zoe":     240.19,
    "Hilde":   240.19,
    "Marlin":  240.19,
    "Eric":    290.23,
    "Petra":   290.23,
    "Jaeger":  290.23,
    "Alcar":   370.29,
    "Margot":  370.29,
    "Rosa":    370.29,
    "Long Fei": 444.35,
    "Thrud":    444.35,
    "Vivian":   444.35,
    "Triton":  540.43,
    "Sophia":  540.43,
    "Yang":    540.43,
    "Charles":   650.52,
    "Ava":       650.52,
    "Wee & Woo": 650.52,
    "Howard":  140.11,
    "Chenko":  140.11,
    "Gordon":  140.11,
    "Fahd":    140.11,
    "Quinn":   140.11,
    "Diana":   110.08,
    "Yeonwoo": 140.11,
    "Amane":   140.11,
}

HERO_CLASS: Final[dict[str, str]] = {
    "Amadeus": "Inf", "Helga": "Inf", "Zoe": "Inf", "Eric": "Inf",
    "Alcar": "Inf", "Long Fei": "Inf", "Triton": "Inf",
    "Jabel": "Cav", "Hilde": "Cav", "Petra": "Cav", "Margot": "Cav",
    "Thrud": "Cav", "Sophia": "Cav",
    "Saul": "Arc", "Marlin": "Arc", "Jaeger": "Arc", "Rosa": "Arc",
    "Vivian": "Arc", "Yang": "Arc",
    "Charles": "Inf", "Ava": "Cav", "Wee & Woo": "Arc",
    "Howard": "Inf",
    "Chenko": "Cav", "Gordon": "Cav", "Fahd": "Cav",
    "Quinn": "Arc", "Diana": "Arc", "Yeonwoo": "Arc", "Amane": "Arc",
}

MYTHIC_HEROES: Final[frozenset[str]] = frozenset({
    "Amadeus", "Helga", "Jabel", "Saul",
    "Zoe", "Hilde", "Marlin",
    "Eric", "Petra", "Jaeger",
    "Alcar", "Margot", "Rosa",
    "Long Fei", "Thrud", "Vivian",
    "Triton", "Sophia", "Yang",
    "Charles", "Ava", "Wee & Woo",
})

EPIC_HEROES: Final[frozenset[str]] = frozenset({
    "Howard", "Chenko", "Gordon", "Fahd",
    "Quinn", "Diana", "Yeonwoo", "Amane",
})

NON_COMBAT_FIRST_SKILL_HEROES: Final[frozenset[str]] = frozenset({"Diana"})


HERO_GENERATION: Final[dict[str, int]] = {
    "Amadeus": 1, "Helga": 1, "Jabel": 1, "Saul": 1,
    "Zoe": 2, "Hilde": 2, "Marlin": 2,
    "Eric": 3, "Petra": 3, "Jaeger": 3,
    "Alcar": 4, "Margot": 4, "Rosa": 4,
    "Long Fei": 5, "Thrud": 5, "Vivian": 5,
    "Triton": 6, "Sophia": 6, "Yang": 6,
    "Charles": 7, "Ava": 7, "Wee & Woo": 7,
}

MAX_GENERATION: Final[int] = 7


def heroes_up_to_generation(max_gen: int) -> frozenset[str]:
    return frozenset(h for h, g in HERO_GENERATION.items() if g <= max_gen)


BENCHMARK_DUMMY_CLASS: Final[dict[str, str]] = {
    "_BM_Inf": "Inf", "_BM_Cav": "Cav", "_BM_Arc": "Arc",
}
BENCHMARK_DUMMY_LEADER_MAX: Final[dict[str, float]] = {
    "_BM_Inf": 200.0, "_BM_Cav": 200.0, "_BM_Arc": 200.0,
}
BENCHMARK_DUMMIES: Final[frozenset[str]] = frozenset(BENCHMARK_DUMMY_CLASS)

BENCHMARK_DUMMY_SKILL: tuple[tuple[int, float], ...] = ((102, 30.0), (211, 15.0))


def hero_class(hero: str) -> str:
    if hero in HERO_CLASS:
        return HERO_CLASS[hero]
    if hero in BENCHMARK_DUMMY_CLASS:
        return BENCHMARK_DUMMY_CLASS[hero]
    raise KeyError(f"Unknown hero: {hero!r}")


def hero_leader_max(hero: str) -> float:
    if hero in BENCHMARK_DUMMY_LEADER_MAX:
        return BENCHMARK_DUMMY_LEADER_MAX[hero]
    if hero not in HERO_LEADER_MAX:
        raise KeyError(f"Unknown hero: {hero!r}")
    from .user_data import get_data_override
    raw = HERO_LEADER_MAX[hero]
    return float(get_data_override(f"hero_max.{hero}", raw))


def hero_leader_pct(hero: str, level: str) -> float:
    if level not in LEVEL_FRACTION:
        raise KeyError(f"Unknown level: {level!r}")
    return hero_leader_max(hero) * LEVEL_FRACTION[level]


HELGA_PASSIVE: Final[dict[int, float]] = {
    0: 0.0,
    1: 0.02,
    2: 0.04,
    3: 0.06,
    4: 0.08,
    5: 0.10,
}

AMADEUS_PASSIVE: Final[dict[int, float]] = {
    0: 0.0,
    1: 0.03,
    2: 0.06,
    3: 0.09,
    4: 0.12,
    5: 0.15,
}


def star_from_level(level: str) -> int:
    if level == "MAX":
        return 5
    return int(level.split("_")[0])


def max_skill_level(level: str, slot: str) -> int:
    return STAR_TO_MAX_SKILL_LVL[star_from_level(level)][_SKILL_SLOT_IDX[slot]]


def default_skill_levels(level: str) -> tuple[int, int, int]:
    return STAR_TO_MAX_SKILL_LVL[star_from_level(level)]


def helga_passive_value(level: str) -> float:
    star = star_from_level(level)
    from .user_data import get_data_override
    raw = HELGA_PASSIVE[star]
    return float(get_data_override(f"helga_passive.{star}", raw))


def amadeus_passive_value(level: str) -> float:
    star = star_from_level(level)
    from .user_data import get_data_override
    raw = AMADEUS_PASSIVE[star]
    return float(get_data_override(f"amadeus_passive.{star}", raw))


WIDGET_MAX: Final[dict[str, float]] = {
    "Aegis of Fate":        62.50,
    "Bands of Tyre":        55.50,
    "Greaves of Faith":     50.00,
    "Rabbitgear Cannon":    50.00,
    "The Unrighteous":      60.00,
    "Revelation":           60.00,
    "Mistweaver":           60.00,
    "Anvil of Truth":       70.00,
    "Fate's Writ":          70.00,
    "Wanderwail":           70.00,
    "Praetorian Guard":     92.50,
    "Revel Fang":           92.50,
    "Aeolian":              92.50,
    "Immortal's Flask":    111.00,
    "Bloodfang":           111.00,
    "Lucky Spinner":       111.00,
    "Tidal Scepter":       133.50,
    "Scarlet Rose":        133.50,
    "Frostkin":            133.50,
    "Justice Fist":        160.50,
    "Chameleos":           160.50,
    "Mortar":              160.50,
}

HERO_WIDGET: Final[dict[str, str]] = {
    "Amadeus": "Aegis of Fate",
    "Helga":   "Bands of Tyre",
    "Jabel":   "Greaves of Faith",
    "Saul":    "Rabbitgear Cannon",
    "Zoe":     "The Unrighteous",
    "Hilde":   "Revelation",
    "Marlin":  "Mistweaver",
    "Eric":    "Anvil of Truth",
    "Petra":   "Fate's Writ",
    "Jaeger":  "Wanderwail",
    "Alcar":   "Praetorian Guard",
    "Margot":  "Revel Fang",
    "Rosa":    "Aeolian",
    "Long Fei": "Immortal's Flask",
    "Thrud":   "Bloodfang",
    "Vivian":  "Lucky Spinner",
    "Triton":  "Tidal Scepter",
    "Sophia":  "Scarlet Rose",
    "Yang":    "Frostkin",
    "Charles":   "Justice Fist",
    "Ava":       "Chameleos",
    "Wee & Woo": "Mortar",
}


def widget_max(widget_name: str) -> float:
    if widget_name not in WIDGET_MAX:
        raise KeyError(f"Unknown widget: {widget_name!r}")
    from .user_data import get_data_override
    raw = WIDGET_MAX[widget_name]
    return float(get_data_override(f"widget_max.{widget_name}", raw))


def widget_stat_bonus(widget_name: str, level: int) -> tuple[float, float]:
    if not (0 <= level <= 10):
        raise ValueError(f"widget level must be 0..10, got {level}")
    bonus = (level / 10.0) * widget_max(widget_name)
    return bonus, bonus


WIDGET_SKILL_MULTIPLIER: Final[dict[int, float]] = {
    0: 0.0,
    1: 0.0,
    2: 0.333,
    3: 0.333,
    4: 0.500,
    5: 0.500,
    6: 0.666,
    7: 0.666,
    8: 0.833,
    9: 0.833,
    10: 1.0,
}

WIDGET_SKILL_MAX_PCT: Final[float] = 15.0


CAVALRY_BYPASS_RATE: Final[float] = 0.20
ARCHER_VOLLEY_RATE: Final[float] = 0.10
TYPE_BONUS_PCT: Final[float] = 10.0
FATIGUE_PER_ROUND: Final[float] = 0.0001
DAMAGE_DIVISOR: Final[float] = 100.0

MAX_JOINERS_WITH_SKILL: Final[int] = 4
MAX_RALLY_MEMBERS: Final[int] = 15


def cavalry_bypass_rate() -> float:
    from .user_data import get_data_override
    return float(get_data_override("engine.cavalry_bypass_rate", CAVALRY_BYPASS_RATE))


def archer_volley_rate() -> float:
    from .user_data import get_data_override
    return float(get_data_override("engine.archer_volley_rate", ARCHER_VOLLEY_RATE))


def type_bonus_pct() -> float:
    from .user_data import get_data_override
    return float(get_data_override("engine.type_bonus_pct", TYPE_BONUS_PCT))


def fatigue_per_round() -> float:
    from .user_data import get_data_override
    return float(get_data_override("engine.fatigue_per_round", FATIGUE_PER_ROUND))


def max_joiners_with_skill() -> int:
    from .user_data import get_data_override
    return int(get_data_override("engine.max_joiners_with_skill", MAX_JOINERS_WITH_SKILL))


def max_rally_members() -> int:
    from .user_data import get_data_override
    return int(get_data_override("engine.max_rally_members", MAX_RALLY_MEMBERS))


__all__ = [
    "BASE_LETHALITY",
    "BASE_DEFENSE",
    "TIER_BASE_STATS",
    "VALID_TIERS",
    "tier_stat",
    "valid_tiers",
    "LEVEL_FRACTION",
    "VALID_LEVELS",
    "HERO_LEADER_MAX",
    "HERO_CLASS",
    "hero_class",
    "BENCHMARK_DUMMY_CLASS",
    "BENCHMARK_DUMMY_LEADER_MAX",
    "BENCHMARK_DUMMIES",
    "MYTHIC_HEROES",
    "EPIC_HEROES",
    "NON_COMBAT_FIRST_SKILL_HEROES",
    "HERO_GENERATION",
    "MAX_GENERATION",
    "heroes_up_to_generation",
    "hero_leader_max",
    "hero_leader_pct",
    "HELGA_PASSIVE",
    "AMADEUS_PASSIVE",
    "star_from_level",
    "STAR_TO_MAX_SKILL_LVL",
    "max_skill_level",
    "default_skill_levels",
    "helga_passive_value",
    "amadeus_passive_value",
    "WIDGET_MAX",
    "HERO_WIDGET",
    "widget_max",
    "widget_stat_bonus",
    "WIDGET_SKILL_MULTIPLIER",
    "WIDGET_SKILL_MAX_PCT",
    "CAVALRY_BYPASS_RATE",
    "ARCHER_VOLLEY_RATE",
    "TYPE_BONUS_PCT",
    "FATIGUE_PER_ROUND",
    "DAMAGE_DIVISOR",
    "MAX_JOINERS_WITH_SKILL",
    "MAX_RALLY_MEMBERS",
    "cavalry_bypass_rate",
    "archer_volley_rate",
    "type_bonus_pct",
    "fatigue_per_round",
    "max_joiners_with_skill",
    "max_rally_members",
]
