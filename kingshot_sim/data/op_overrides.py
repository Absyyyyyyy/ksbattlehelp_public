from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path

from ..domain.skills import Skill, Effect
from ..io_pkg.scope import use_session_storage, session_dict


_OVERRIDES: dict[tuple[str, str], list[tuple[int, int]]] = {}

_SS_KEY = "_ks_op_overrides_v1"

_PERSIST_PATH = Path.home() / ".kingshot_sim" / "op_overrides.json"


def _encode_key(hero: str, slot: str) -> str:
    return f"{hero}|{slot}"


def _decode_key(s: str) -> tuple[str, str]:
    hero, _, slot = s.partition("|")
    return (hero, slot)


def _store_snapshot() -> dict[tuple[str, str], list[tuple[int, int]]]:
    if use_session_storage():
        raw = session_dict(_SS_KEY)
        return {_decode_key(k): [tuple(t) for t in v] for k, v in raw.items()}
    return {k: list(v) for k, v in _OVERRIDES.items()}


def _set_in_store(hero: str, slot: str, rules: list[tuple[int, int]]) -> None:
    if use_session_storage():
        raw = session_dict(_SS_KEY)
        raw[_encode_key(hero, slot)] = [list(t) for t in rules]
    else:
        _OVERRIDES[(hero, slot)] = list(rules)


def _del_in_store(hero: str, slot: str) -> None:
    if use_session_storage():
        session_dict(_SS_KEY).pop(_encode_key(hero, slot), None)
    else:
        _OVERRIDES.pop((hero, slot), None)


def _clear_store() -> None:
    if use_session_storage():
        session_dict(_SS_KEY).clear()
    else:
        _OVERRIDES.clear()


def _get_rules(hero: str, slot: str) -> list[tuple[int, int]]:
    if use_session_storage():
        raw = session_dict(_SS_KEY).get(_encode_key(hero, slot), [])
        return [tuple(t) for t in raw]
    return list(_OVERRIDES.get((hero, slot), []))


def set_op_override(hero: str, slot: str, original_op: int, new_op: int) -> None:
    _validate_op(new_op)
    if new_op == original_op:
        clear_op_override(hero, slot, original_op)
        return
    existing = _get_rules(hero, slot)
    existing = [(o, n) for (o, n) in existing if o != original_op]
    existing.append((int(original_op), int(new_op)))
    _set_in_store(hero, slot, existing)
    _save_if_disk_mode()


def clear_op_override(hero: str, slot: str, original_op: int) -> None:
    existing = _get_rules(hero, slot)
    if not existing:
        return
    remaining = [(o, n) for (o, n) in existing if o != original_op]
    if remaining:
        _set_in_store(hero, slot, remaining)
    else:
        _del_in_store(hero, slot)
    _save_if_disk_mode()


def clear_all_overrides() -> None:
    _clear_store()
    _save_if_disk_mode()


def list_op_overrides() -> dict[tuple[str, str], list[tuple[int, int]]]:
    return _store_snapshot()


def apply_overrides_to_skill(hero_name: str, slot: str, skill: Skill) -> Skill:
    rules = _get_rules(hero_name, slot)
    if not rules:
        return skill
    rules_dict = dict(rules)
    rewritten: list[Effect] = []
    changed = False
    for eff in skill.effects:
        if eff.op in rules_dict:
            rewritten.append(replace(eff, op=rules_dict[eff.op]))
            changed = True
        else:
            rewritten.append(eff)
    if not changed:
        return skill
    return replace(skill, effects=tuple(rewritten))


def _validate_op(op: int) -> None:
    from ..domain.enums import OP_TO_FAMILY
    if op not in OP_TO_FAMILY:
        raise ValueError(
            f"Op code {op} is not in any known family. "
            f"Valid op codes: {sorted(OP_TO_FAMILY.keys())}"
        )


def _save_if_disk_mode() -> None:
    if use_session_storage():
        return
    _save()


def _save() -> None:
    try:
        _PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        flat = []
        for (hero, slot), rules in sorted(_OVERRIDES.items()):
            for orig, new in rules:
                flat.append({"hero": hero, "slot": slot,
                              "original_op": orig, "new_op": new})
        _PERSIST_PATH.write_text(json.dumps({"version": 1, "overrides": flat}, indent=2))
    except OSError:
        pass


def _load() -> None:
    if not _PERSIST_PATH.exists():
        return
    try:
        data = json.loads(_PERSIST_PATH.read_text())
        for entry in data.get("overrides", []):
            key = (entry["hero"], entry["slot"])
            _OVERRIDES.setdefault(key, []).append(
                (int(entry["original_op"]), int(entry["new_op"]))
            )
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        _OVERRIDES.clear()


_load()


__all__ = [
    "set_op_override",
    "clear_op_override",
    "clear_all_overrides",
    "list_op_overrides",
    "apply_overrides_to_skill",
]
