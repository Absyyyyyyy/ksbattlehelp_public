from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Final

from ..benchmark.runner import HeroBuild
from ..data.reference import MYTHIC_HEROES, EPIC_HEROES, MAX_GENERATION, hero_class

MIN_GENERATION: Final[int] = 1
MAX_ROSTER_GENERATION: Final[int] = max(MAX_GENERATION, 8)
ALL_HEROES: Final[frozenset[str]] = frozenset(MYTHIC_HEROES | EPIC_HEROES)
_LEVEL_PATTERN = re.compile(r"^(?:MAX|[0-5]_[0-5])$")


@dataclass
class BenchmarkRoster:
    name: str
    generation: int
    owned_heroes: dict[str, list[str]] = field(default_factory=dict)
    builds: dict[str, HeroBuild] = field(default_factory=dict)


def _safe_star_subtier_from_level(level: str) -> tuple[int, int]:
    if level == "MAX":
        return 5, 0
    if "_" in level:
        parts = level.split("_")
        try:
            return max(0, min(5, int(parts[0]))), max(0, min(5, int(parts[1])))
        except (ValueError, IndexError):
            pass
    return 5, 0


def _is_valid_level(lvl: Any) -> bool:
    if not isinstance(lvl, str):
        return False
    return bool(_LEVEL_PATTERN.match(lvl.strip()))


def _build_to_dict(b: HeroBuild) -> dict[str, Any]:
    star, sub_tier = _safe_star_subtier_from_level(b.level)
    d: dict[str, Any] = {
        "star": star,
        "sub_tier": sub_tier,
        "level": b.level,
        "widget_level": b.widget_level,
    }
    if b.skill_levels is not None:
        d["skill_levels"] = list(b.skill_levels)
    return d


def _build_from_dict(hero_name: str, data: Any) -> HeroBuild:
    default_wl = 0 if hero_name in EPIC_HEROES else 4
    if isinstance(data, HeroBuild):
        return data
    if not isinstance(data, dict):
        return HeroBuild(level="MAX", widget_level=default_wl)

    wl_raw = data.get("widget_level")
    if wl_raw is not None:
        try:
            wl = max(0, min(10, int(wl_raw)))
        except (TypeError, ValueError):
            wl = default_wl
    else:
        wl = default_wl

    lvl_raw = data.get("level")
    if isinstance(lvl_raw, str):
        lvl_raw = lvl_raw.strip()
    if _is_valid_level(lvl_raw):
        level = "MAX" if lvl_raw.startswith("5_") else str(lvl_raw)
    else:
        star_raw = data.get("star")
        sub_raw = data.get("sub_tier")
        try:
            star = max(0, min(5, int(star_raw))) if star_raw is not None else 5
        except (TypeError, ValueError):
            star = 5
        try:
            sub = max(0, min(5, int(sub_raw))) if sub_raw is not None else 0
        except (TypeError, ValueError):
            sub = 0
        level = "MAX" if star >= 5 else f"{star}_{sub}"

    skill_levels: tuple[int, int, int] | None = None
    sl_raw = data.get("skill_levels")
    if isinstance(sl_raw, (list, tuple)) and len(sl_raw) == 3:
        try:
            skill_levels = (
                max(0, min(5, int(sl_raw[0]))),
                max(0, min(5, int(sl_raw[1]))),
                max(0, min(5, int(sl_raw[2]))),
            )
        except (TypeError, ValueError):
            skill_levels = None

    return HeroBuild(level=level, widget_level=wl, skill_levels=skill_levels)


def roster_to_dict(roster: BenchmarkRoster) -> dict[str, Any]:
    return {
        "version": 1,
        "format": "ksbattlehelper-roster",
        "name": roster.name,
        "generation": roster.generation,
        "owned_heroes": {
            cls_name: list(heroes)
            for cls_name, heroes in roster.owned_heroes.items()
        },
        "builds": {
            hero: _build_to_dict(build)
            for hero, build in roster.builds.items()
        },
    }


def roster_from_dict(data: dict[str, Any]) -> BenchmarkRoster:
    if not isinstance(data, dict):
        data = {}

    name = str(data.get("name") or "Unnamed Roster")

    raw_gen = data.get("generation")
    try:
        gen = max(MIN_GENERATION, min(int(raw_gen), MAX_ROSTER_GENERATION))
    except (TypeError, ValueError):
        gen = 1

    owned_heroes: dict[str, list[str]] = {}
    raw_owned = data.get("owned_heroes")
    if isinstance(raw_owned, dict):
        for cls_name, hero_list in raw_owned.items():
            if isinstance(hero_list, (list, tuple)):
                valid_list = [
                    h for h in hero_list
                    if isinstance(h, str) and h in ALL_HEROES and hero_class(h) == str(cls_name)
                ]
                owned_heroes[str(cls_name)] = list(dict.fromkeys(valid_list))

    builds: dict[str, HeroBuild] = {}
    raw_builds = data.get("builds")
    if isinstance(raw_builds, dict):
        for h, b_data in raw_builds.items():
            if h not in ALL_HEROES:
                continue
            builds[h] = _build_from_dict(h, b_data)

    return BenchmarkRoster(
        name=name,
        generation=gen,
        owned_heroes=owned_heroes,
        builds=builds,
    )


def roster_to_json(roster: BenchmarkRoster, indent: int = 2) -> str:
    return json.dumps(roster_to_dict(roster), indent=indent)


def roster_from_json(raw: str) -> BenchmarkRoster:
    return roster_from_dict(json.loads(raw))


def save_roster_file(roster: BenchmarkRoster, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(roster_to_json(roster), encoding="utf-8")


def load_roster_file(path: str | Path) -> BenchmarkRoster:
    p = Path(path)
    return roster_from_json(p.read_text(encoding="utf-8"))


__all__ = [
    "BenchmarkRoster",
    "roster_to_dict",
    "roster_from_dict",
    "roster_to_json",
    "roster_from_json",
    "save_roster_file",
    "load_roster_file",
]
