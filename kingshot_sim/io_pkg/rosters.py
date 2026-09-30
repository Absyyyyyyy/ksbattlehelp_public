from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Final

from ..benchmark.runner import HeroBuild
from ..config.fighter import HeroGearPiece, BonusVector
from ..config.buffs import Buffs
from ..data.reference import MYTHIC_HEROES, EPIC_HEROES, MAX_GENERATION, hero_class
from .profiles import HeroGearPieceSchema, BonusVectorSchema, BuffsSchema

MIN_GENERATION: Final[int] = 1
ALL_HEROES: Final[frozenset[str]] = frozenset(MYTHIC_HEROES | EPIC_HEROES)
_LEVEL_PATTERN = re.compile(r"^(?:MAX|[0-5]_[0-5])$")


@dataclass
class AccountRoster:
    name: str
    generation: int = MAX_GENERATION
    owned_heroes: dict[str, list[str]] = field(default_factory=dict)
    builds: dict[str, HeroBuild] = field(default_factory=dict)
    class_gear: dict[str, dict[str, HeroGearPiece]] = field(default_factory=dict)
    bonuses: BonusVector = field(default_factory=BonusVector)
    buffs: Buffs = field(default_factory=Buffs)



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


def roster_to_dict(roster: AccountRoster) -> dict[str, Any]:
    gear_dict: dict[str, dict[str, Any]] = {}
    if isinstance(roster.class_gear, dict):
        for cls_name, slot_map in roster.class_gear.items():
            if not isinstance(slot_map, dict):
                continue
            cleaned_slot_map: dict[str, Any] = {}
            for slot, piece in slot_map.items():
                if isinstance(piece, HeroGearPiece):
                    cleaned_slot_map[slot] = HeroGearPieceSchema.from_domain(piece).model_dump()
                elif isinstance(piece, dict):
                    valid_keys = set(HeroGearPieceSchema.model_fields.keys())
                    filtered = {k: v for k, v in piece.items() if k in valid_keys}
                    cleaned_slot_map[slot] = HeroGearPieceSchema(**filtered).model_dump()
            if cleaned_slot_map:
                gear_dict[cls_name] = cleaned_slot_map

    bonuses_dict: dict[str, Any]
    if isinstance(roster.bonuses, BonusVector):
        bonuses_dict = BonusVectorSchema.from_domain(roster.bonuses).model_dump()
    elif isinstance(roster.bonuses, dict):
        valid_keys = set(BonusVectorSchema.model_fields.keys())
        filtered = {k: v for k, v in roster.bonuses.items() if k in valid_keys}
        bonuses_dict = BonusVectorSchema(**filtered).model_dump()
    else:
        bonuses_dict = BonusVectorSchema().model_dump()

    buffs_dict: dict[str, Any]
    if isinstance(roster.buffs, Buffs):
        buffs_dict = BuffsSchema.from_domain(roster.buffs).model_dump()
    elif isinstance(roster.buffs, dict):
        valid_keys = set(BuffsSchema.model_fields.keys())
        filtered = {k: v for k, v in roster.buffs.items() if k in valid_keys}
        buffs_dict = BuffsSchema(**filtered).model_dump()
    else:
        buffs_dict = BuffsSchema().model_dump()

    return {
        "version": 2,
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
        "class_gear": gear_dict,
        "bonuses": bonuses_dict,
        "buffs": buffs_dict,
    }


def roster_from_dict(data: dict[str, Any]) -> AccountRoster:
    if not isinstance(data, dict):
        data = {}

    name = str(data.get("name") or "Unnamed Roster")

    raw_gen = data.get("generation")
    if raw_gen is not None:
        try:
            gen = max(MIN_GENERATION, min(int(raw_gen), MAX_GENERATION))
        except (TypeError, ValueError):
            gen = MAX_GENERATION
    else:
        gen = MAX_GENERATION

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

    class_gear: dict[str, dict[str, HeroGearPiece]] = {}
    raw_gear = data.get("class_gear")
    if isinstance(raw_gear, dict):
        for cls_name, slots in raw_gear.items():
            if not isinstance(slots, dict):
                continue
            cleaned_slots: dict[str, HeroGearPiece] = {}
            for slot_name, p_data in slots.items():
                if isinstance(p_data, HeroGearPiece):
                    cleaned_slots[slot_name] = p_data
                elif isinstance(p_data, dict):
                    valid_keys = set(HeroGearPieceSchema.model_fields.keys())
                    filtered = {k: v for k, v in p_data.items() if k in valid_keys}
                    try:
                        cleaned_slots[slot_name] = HeroGearPieceSchema(**filtered).to_domain()
                    except Exception:
                        pass
            if cleaned_slots:
                class_gear[str(cls_name)] = cleaned_slots

    raw_bonuses = data.get("bonuses")
    if isinstance(raw_bonuses, BonusVector):
        bonuses = raw_bonuses
    elif isinstance(raw_bonuses, dict):
        valid_keys = set(BonusVectorSchema.model_fields.keys())
        filtered = {k: v for k, v in raw_bonuses.items() if k in valid_keys}
        try:
            bonuses = BonusVectorSchema(**filtered).to_domain()
        except Exception:
            bonuses = BonusVector()
    else:
        bonuses = BonusVector()

    raw_buffs = data.get("buffs")
    if isinstance(raw_buffs, Buffs):
        buffs = raw_buffs
    elif isinstance(raw_buffs, dict):
        valid_keys = set(BuffsSchema.model_fields.keys())
        filtered = {k: v for k, v in raw_buffs.items() if k in valid_keys}
        try:
            buffs = BuffsSchema(**filtered).to_domain()
        except Exception:
            buffs = Buffs()
    else:
        buffs = Buffs()

    return AccountRoster(
        name=name,
        generation=gen,
        owned_heroes=owned_heroes,
        builds=builds,
        class_gear=class_gear,
        bonuses=bonuses,
        buffs=buffs,
    )


def roster_to_json(roster: AccountRoster, indent: int = 2) -> str:
    return json.dumps(roster_to_dict(roster), indent=indent)


def roster_from_json(raw: str) -> AccountRoster:
    return roster_from_dict(json.loads(raw))


def save_roster_file(roster: AccountRoster, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(roster_to_json(roster), encoding="utf-8")


def load_roster_file(path: str | Path) -> AccountRoster:
    p = Path(path)
    return roster_from_json(p.read_text(encoding="utf-8"))


__all__ = [
    "AccountRoster",
    "roster_to_dict",
    "roster_from_dict",
    "roster_to_json",
    "roster_from_json",
    "save_roster_file",
    "load_roster_file",
]
