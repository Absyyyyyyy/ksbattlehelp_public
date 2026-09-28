from __future__ import annotations
import json
import hashlib
from typing import Any

import streamlit as st

from kingshot_sim.io_pkg import backup as backup_mod
from kingshot_sim.webui import theme as _theme


LOCAL_STORAGE_KEYS: tuple[str, ...] = (
    _theme.THEME_STATE_KEY,
    "_bm_view_mode",
    "_ks_active_roster",
)
_UI_PREF_KEYS: tuple[str, ...] = LOCAL_STORAGE_KEYS


SCHEMA_VERSION = 1

LS_KEY = "kingshot_sim_state_v1"

_FORM_KEY_PREFIXES: tuple[str, ...] = (
    "qf_",
    "bc_",
    "bd_",
    "sn_",
    "ad_",
    "_bm_",
)

_EXCLUDED_KEY_SUBSTRINGS: tuple[str, ...] = (
    "_attacker", "_defender",
    "_btn_",
    "_reset_",
    "_bm_run",
    "_bm_ocr_",
    "_bm_import_",
    "_bm_preset_",
)

_EXCLUDED_KEY_SUFFIXES: tuple[str, ...] = (
    "_btn",
    "_reset",
    "_confirm",
    "_edit",
    "_qf10", "_qf20",
    "_reimport",
    "_skip_btn",
    "_skip_cancel",
    "_skip_ok",
    "_drill_save",
    "_run",
    "_upload",
    "_pending_import",
    "_scroll_to_banner",
    "_ss_scroll_to_banner",
    "_table",
)

_EXCLUDED_KEY_EXACT: frozenset[str] = frozenset({
    "bc_save_def", "bc_save_sp",
    "bd_save_att", "bd_save_sp",
})


def _is_widget_key_persistable(key: str) -> bool:
    if key in _EXCLUDED_KEY_EXACT:
        return False
    if any(s in key for s in _EXCLUDED_KEY_SUBSTRINGS):
        return False
    if any(key.endswith(suf) for suf in _EXCLUDED_KEY_SUFFIXES):
        return False
    return True

_HYDRATED_FLAG = "_ks_lstorage_hydrated"
_LAST_HASH_KEY = "_ks_lstorage_last_hash"
_ATTEMPTS_KEY = "_ks_lstorage_read_attempts"

_MAX_READ_ATTEMPTS = 2


def _is_apptest_mode() -> bool:
    import sys
    return "streamlit.testing.v1.local_script_runner" in sys.modules


def _get_local_storage():
    if _is_apptest_mode():
        return None
    try:
        from streamlit_local_storage import LocalStorage
        return LocalStorage()
    except Exception:
        return None


def _is_json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_safe(v)
                   for k, v in value.items())
    return False


def _shallow_json_safe(value: Any) -> Any | None:
    if _is_json_safe(value):
        return value
    if isinstance(value, dict):
        sub: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_json_safe(v):
                sub[k] = v
        return sub if sub else None
    return None


def _collect_form_state() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        ss = st.session_state
    except Exception:
        return out
    for key in list(ss.keys()):
        if not isinstance(key, str):
            continue
        if not any(key.startswith(p) for p in _FORM_KEY_PREFIXES):
            continue
        if not _is_widget_key_persistable(key):
            continue
        try:
            value = ss[key]
        except Exception:
            continue
        safe = _shallow_json_safe(value)
        if safe is not None:
            out[key] = safe
    return out


def _collect_ui_state() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        ss = st.session_state
    except Exception:
        return out
    for key in _UI_PREF_KEYS:
        if key in ss:
            try:
                value = ss[key]
            except Exception:
                continue
            if _is_json_safe(value):
                out[key] = value
    return out


def _build_snapshot() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "backup": backup_mod.build_backup_payload(),
        "form": _collect_form_state(),
        "ui": _collect_ui_state(),
    }


def _hash_snapshot(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def hydrate_from_browser() -> None:
    if st.session_state.get(_HYDRATED_FLAG):
        return

    localS = _get_local_storage()
    if localS is None:
        st.session_state[_HYDRATED_FLAG] = True
        return

    try:
        raw = localS.getItem(LS_KEY)
    except Exception:
        raw = None

    if raw is None:
        attempts = int(st.session_state.get(_ATTEMPTS_KEY, 0)) + 1
        st.session_state[_ATTEMPTS_KEY] = attempts
        if attempts >= _MAX_READ_ATTEMPTS:
            st.session_state[_HYDRATED_FLAG] = True
        return

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        try:
            localS.deleteItem(LS_KEY, key="ks_lstorage_wipe")
        except Exception:
            pass
        st.session_state[_HYDRATED_FLAG] = True
        return

    if not isinstance(parsed, dict) or parsed.get("schema") != SCHEMA_VERSION:
        st.session_state[_HYDRATED_FLAG] = True
        return

    backup_payload = parsed.get("backup", {})
    if isinstance(backup_payload, dict):
        try:
            backup_mod.apply_backup_payload(backup_payload, replace_existing=False)
        except Exception:
            pass

    form_state = parsed.get("form", {})
    if isinstance(form_state, dict):
        for key, value in form_state.items():
            if not isinstance(key, str):
                continue
            if not any(key.startswith(p) for p in _FORM_KEY_PREFIXES):
                continue
            if not _is_widget_key_persistable(key):
                continue
            try:
                st.session_state[key] = value
            except Exception:
                continue

    ui_state = parsed.get("ui", {})
    if isinstance(ui_state, dict):
        for key, value in ui_state.items():
            if key not in _UI_PREF_KEYS or not _is_json_safe(value):
                continue
            try:
                st.session_state[key] = value
            except Exception:
                continue

    st.session_state[_LAST_HASH_KEY] = _hash_snapshot(_build_snapshot())
    st.session_state[_HYDRATED_FLAG] = True


def auto_save_to_browser() -> None:
    if not st.session_state.get(_HYDRATED_FLAG):
        return

    localS = _get_local_storage()
    if localS is None:
        return

    snapshot = _build_snapshot()
    new_hash = _hash_snapshot(snapshot)
    if new_hash == st.session_state.get(_LAST_HASH_KEY):
        return

    try:
        payload = json.dumps(snapshot, default=str)
        localS.setItem(LS_KEY, payload, key="ks_lstorage_writer")
        st.session_state[_LAST_HASH_KEY] = new_hash
    except Exception:
        pass


def clear_browser_state() -> None:
    localS = _get_local_storage()
    if localS is None:
        return
    try:
        localS.deleteItem(LS_KEY, key="ks_lstorage_clear")
    except Exception:
        pass
    st.session_state.pop(_LAST_HASH_KEY, None)


__all__ = [
    "hydrate_from_browser",
    "auto_save_to_browser",
    "clear_browser_state",
    "SCHEMA_VERSION",
    "LS_KEY",
    "LOCAL_STORAGE_KEYS",
]
