from __future__ import annotations
import os
import threading
from typing import Any


_thread_local = threading.local()


def mark_no_session_storage() -> None:
    _thread_local.no_session = True


def clear_no_session_storage() -> None:
    _thread_local.no_session = False


def _no_session_storage_here() -> bool:
    return getattr(_thread_local, "no_session", False)


def in_streamlit_context() -> bool:
    if os.environ.get("KS_PERSIST_TO_DISK", "").strip() == "1":
        return False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False
    try:
        return get_script_run_ctx() is not None
    except Exception:
        return False


def force_session_backend() -> bool:
    return os.environ.get("KS_SESSION_PROFILES", "").strip() == "1"


def use_session_storage() -> bool:
    if _no_session_storage_here():
        return False
    return in_streamlit_context() or force_session_backend()


def session_dict(key: str) -> dict:
    try:
        import streamlit as st
    except Exception as exc:
        raise RuntimeError(
            "session_dict requires Streamlit; call use_session_storage() first"
        ) from exc
    ss = st.session_state
    if key not in ss:
        ss[key] = {}
    return ss[key]


__all__ = [
    "in_streamlit_context",
    "force_session_backend",
    "use_session_storage",
    "session_dict",
    "mark_no_session_storage",
    "clear_no_session_storage",
]
