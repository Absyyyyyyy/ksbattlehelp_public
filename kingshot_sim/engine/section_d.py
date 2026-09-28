from __future__ import annotations

from typing import Iterable

from ..config.buffs import (
    Buffs,
    RHINO_LEVEL_PCT, LION_LEVEL_PCT, PANTHER_LEVEL_PCT,
    ELEPHANT_LEVEL_PCT, MOOSE_LEVEL_PCT, GRIZZLY_LEVEL_PCT,
    TURRET_LEVEL_PCT,
)


LAYERS: tuple[str, ...] = ("city", "pet", "turret", "ocr")
STATS:  tuple[str, ...] = ("atk", "def", "let", "hp")

_OCR_OWN_FIELD = {
    "atk": "ocr_own_atk_pct", "def": "ocr_own_def_pct",
    "let": "ocr_own_let_pct", "hp": "ocr_own_hp_pct",
}
_OCR_ENEMY_FIELD = {
    "atk": "ocr_enemy_atk_down_pct", "def": "ocr_enemy_def_down_pct",
    "let": "ocr_enemy_let_down_pct", "hp": "ocr_enemy_hp_down_pct",
}


def own_pct(buffs: Buffs, stat: str, layer: str) -> float:
    if layer == "ocr":
        return float(getattr(buffs, _OCR_OWN_FIELD[stat], 0.0))
    if stat == "atk":
        if layer == "city":
            return float(buffs.city_atk)
        if layer == "pet":
            return RHINO_LEVEL_PCT[buffs.rhino_level]
        if layer == "turret":
            return 0.0
    elif stat == "def":
        if layer == "city":
            return float(buffs.city_def)
        if layer == "pet":
            return LION_LEVEL_PCT[buffs.lion_level]
        if layer == "turret":
            return 0.0
    elif stat == "let":
        if layer == "city":
            return float(buffs.city_let)
        if layer == "pet":
            return PANTHER_LEVEL_PCT[buffs.panther_level]
        if layer == "turret":
            return TURRET_LEVEL_PCT[buffs.turrets]
    elif stat == "hp":
        if layer == "city":
            return float(buffs.city_hp)
        if layer == "pet":
            return ELEPHANT_LEVEL_PCT[buffs.elephant_level]
        if layer == "turret":
            return 0.0
    return 0.0


def enemy_down_pct(buffs: Buffs, stat: str, layer: str) -> float:
    if layer == "ocr":
        return float(getattr(buffs, _OCR_ENEMY_FIELD[stat], 0.0))
    if stat == "atk" and layer == "city":
        return float(buffs.city_enemy_atk_down)
    if stat == "def" and layer == "city":
        return float(buffs.city_enemy_def_down)
    if stat == "let" and layer == "pet":
        return GRIZZLY_LEVEL_PCT[buffs.grizzly_level]
    if stat == "hp"  and layer == "pet":
        return MOOSE_LEVEL_PCT[buffs.moose_level]
    return 0.0


def section_d_factor(own_buffs: Buffs, opp_buffs: Buffs, stat: str) -> float:
    factor = 1.0
    for layer in LAYERS:
        own = own_pct(own_buffs, stat, layer)
        enemy = enemy_down_pct(opp_buffs, stat, layer)
        net = own - enemy
        if net != 0.0:
            factor *= 1.0 + net / 100.0
    return factor


def section_d_factor_from_pcts(
    own_pct_by_layer: dict[str, float],
    enemy_down_pct_by_layer: dict[str, float] | None = None,
) -> float:
    enemy = enemy_down_pct_by_layer or {}
    factor = 1.0
    for layer in LAYERS:
        net = own_pct_by_layer.get(layer, 0.0) - enemy.get(layer, 0.0)
        if net != 0.0:
            factor *= 1.0 + net / 100.0
    return factor


__all__ = [
    "LAYERS", "STATS",
    "own_pct", "enemy_down_pct",
    "section_d_factor",
    "section_d_factor_from_pcts",
]
