from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Union

from ..io_pkg.scope import use_session_storage, session_dict

DataValue = Union[int, float, str]

_DATA_OVERRIDES: dict[str, DataValue] = {}

_SS_KEY = "_ks_data_overrides_v1"

_PERSIST_PATH = Path.home() / ".kingshot_sim" / "data_overrides.json"


def _store() -> dict[str, DataValue]:
    if use_session_storage():
        return session_dict(_SS_KEY)
    return _DATA_OVERRIDES


def set_data_override(key: str, value: DataValue) -> None:
    _validate_key(key)
    _store()[key] = value
    _save_if_disk_mode()


def clear_data_override(key: str) -> None:
    _store().pop(key, None)
    _save_if_disk_mode()


def clear_all_data_overrides() -> None:
    _store().clear()
    _save_if_disk_mode()


def list_data_overrides() -> dict[str, DataValue]:
    return dict(_store())


def get_data_override(key: str, default: Any) -> Any:
    return _store().get(key, default)


def has_data_override(key: str) -> bool:
    return key in _store()


def keys_with_prefix(prefix: str) -> list[str]:
    return sorted(k for k in _store() if k.startswith(prefix))


KNOWN_PREFIXES: tuple[str, ...] = (
    "tier_stat.",
    "hero_max.",
    "widget_max.",
    "helga_passive.",
    "amadeus_passive.",
    "engine.",
)

BLOCKED_KEYS: frozenset[str] = frozenset({
    "engine.damage_divisor",
    "engine.base_lethality",
    "engine.base_defense",
})


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or not key:
        raise ValueError(f"data-override key must be a non-empty string, got {key!r}")
    if key in BLOCKED_KEYS:
        raise ValueError(
            f"Override key {key!r} is not adjustable — it would break the engine "
            f"math or the SoS R0 validation anchor. See user_data.py docstring."
        )
    if not any(key.startswith(p) for p in KNOWN_PREFIXES):
        raise ValueError(
            f"Override key {key!r} does not match any known namespace. "
            f"Valid prefixes: {KNOWN_PREFIXES}"
        )


PERSIST_VERSION = 1


def _save_if_disk_mode() -> None:
    if use_session_storage():
        return
    _save()


def _save() -> None:
    try:
        _PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": PERSIST_VERSION,
            "overrides": dict(sorted(_DATA_OVERRIDES.items())),
        }
        _PERSIST_PATH.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _load() -> None:
    if not _PERSIST_PATH.exists():
        return
    try:
        data = json.loads(_PERSIST_PATH.read_text())
        for key, value in data.get("overrides", {}).items():
            try:
                _validate_key(key)
            except ValueError:
                continue
            _DATA_OVERRIDES[key] = value
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        _DATA_OVERRIDES.clear()


_load()


__all__ = [
    "DataValue",
    "set_data_override",
    "clear_data_override",
    "clear_all_data_overrides",
    "list_data_overrides",
    "get_data_override",
    "has_data_override",
    "keys_with_prefix",
    "KNOWN_PREFIXES",
    "BLOCKED_KEYS",
    "PERSIST_VERSION",
]
