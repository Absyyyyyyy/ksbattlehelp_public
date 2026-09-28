from __future__ import annotations
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import streamlit as st


INITIAL_COUNT = 131

INITIAL_BATTLES = 558_846_600


@dataclass(frozen=True)
class _CounterSpec:
    redis_key: str
    file_key: str
    floor: int


_SIMS = _CounterSpec("ksbattlehelper:total_sims", "count", INITIAL_COUNT)
_BATTLES = _CounterSpec("ksbattlehelper:total_battles", "battles", INITIAL_BATTLES)

_COUNTER_FILE = Path(__file__).parent.parent / ".sim_counter.json"

_GET_CACHE_TTL_S = 5.0

_NETWORK_TIMEOUT_S = 2.0


class _FileBackend:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _read_all_locked(self) -> dict:
        try:
            if _COUNTER_FILE.exists():
                data = json.loads(_COUNTER_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _write_all_locked(self, data: dict) -> None:
        try:
            _COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _COUNTER_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, _COUNTER_FILE)
        except Exception:
            pass

    def _value(self, data: dict, spec: _CounterSpec) -> int:
        try:
            return max(int(data.get(spec.file_key, spec.floor)), spec.floor)
        except (TypeError, ValueError):
            return spec.floor

    def get(self, spec: _CounterSpec) -> int:
        with self._lock:
            return self._value(self._read_all_locked(), spec)

    def increment(self, spec: _CounterSpec, amount: int = 1) -> int:
        with self._lock:
            data = self._read_all_locked()
            n = self._value(data, spec) + int(amount)
            data[spec.file_key] = n
            self._write_all_locked(data)
            return n


class _UpstashBackend:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._lock = threading.Lock()
        self._cache: Dict[str, tuple[int, float]] = {}
        self._seeded: set = set()


    def _call(self, *command_parts: object) -> object:
        path = "/".join(urllib.parse.quote(str(p), safe="") for p in command_parts)
        url = f"{self._url}/{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "ksbattlehelper-runtime-stats/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=_NETWORK_TIMEOUT_S) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Upstash HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"Upstash network error: {e!r}") from e
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise RuntimeError("Upstash response not JSON") from e
        if "error" in data:
            raise RuntimeError(f"Upstash error: {data['error']}")
        return data.get("result")

    def _ensure_baseline(self, spec: _CounterSpec) -> None:
        if spec.floor <= 0 or spec.redis_key in self._seeded:
            return
        try:
            self._call("setnx", spec.redis_key, spec.floor)
            self._seeded.add(spec.redis_key)
        except RuntimeError:
            pass


    def get(self, spec: _CounterSpec) -> int:
        key = spec.redis_key
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and (time.time() - hit[1]) < _GET_CACHE_TTL_S:
                return hit[0]

        try:
            self._ensure_baseline(spec)
            raw = self._call("get", key)
            val = int(raw) if raw is not None else spec.floor
            val = max(val, spec.floor)
        except (RuntimeError, ValueError, TypeError):
            with self._lock:
                hit = self._cache.get(key)
                if hit is not None:
                    return hit[0]
                return spec.floor

        with self._lock:
            self._cache[key] = (val, time.time())
            return val

    def increment(self, spec: _CounterSpec, amount: int = 1) -> int:
        key = spec.redis_key
        amount = int(amount)
        try:
            self._ensure_baseline(spec)
            if amount == 1:
                new_val = int(self._call("incr", key))
            else:
                new_val = int(self._call("incrby", key, amount))
        except (RuntimeError, ValueError, TypeError):
            with self._lock:
                hit = self._cache.get(key)
                base = hit[0] if hit is not None else spec.floor
                new_val = base + amount
                self._cache[key] = (new_val, time.time())
                return new_val

        with self._lock:
            self._cache[key] = (new_val, time.time())
            return new_val


def _read_secret(name: str) -> Optional[str]:
    try:
        if name in st.secrets:
            v = st.secrets[name]
            if isinstance(v, str) and v.strip():
                return v.strip()
    except Exception:
        pass
    v = os.environ.get(name, "").strip()
    return v or None


@st.cache_resource
def _backend() -> object:
    url = _read_secret("UPSTASH_REDIS_REST_URL")
    token = _read_secret("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return _UpstashBackend(url, token)
    return _FileBackend()


def get_total_sims() -> int:
    try:
        return int(_backend().get(_SIMS))
    except Exception:
        return INITIAL_COUNT


def increment_total_sims() -> int:
    try:
        return int(_backend().increment(_SIMS, 1))
    except Exception:
        return INITIAL_COUNT + 1


def get_total_battles() -> int:
    try:
        return int(_backend().get(_BATTLES))
    except Exception:
        return INITIAL_BATTLES


def add_total_battles(n: int) -> int:
    try:
        n = int(n)
        if n <= 0:
            return get_total_battles()
        return int(_backend().increment(_BATTLES, n))
    except Exception:
        return INITIAL_BATTLES


def backend_name() -> str:
    b = _backend()
    if isinstance(b, _UpstashBackend):
        return "upstash"
    return "file"


@st.cache_resource
def _queue_state() -> Dict[str, object]:
    return {"queued": 0, "running": 0, "lock": threading.Lock()}


def queue_enter() -> None:
    s = _queue_state()
    with s["lock"]:
        s["queued"] = int(s["queued"]) + 1


def queue_to_running() -> None:
    s = _queue_state()
    with s["lock"]:
        s["queued"] = max(0, int(s["queued"]) - 1)
        s["running"] = int(s["running"]) + 1


def queue_exit_running() -> None:
    s = _queue_state()
    with s["lock"]:
        s["running"] = max(0, int(s["running"]) - 1)


def queue_exit_unstarted() -> None:
    s = _queue_state()
    with s["lock"]:
        s["queued"] = max(0, int(s["queued"]) - 1)


def get_queue_count() -> int:
    s = _queue_state()
    with s["lock"]:
        return int(s["queued"])


def get_running_count() -> int:
    s = _queue_state()
    with s["lock"]:
        return int(s["running"])


__all__ = [
    "INITIAL_COUNT",
    "INITIAL_BATTLES",
    "backend_name",
    "get_total_sims",
    "increment_total_sims",
    "get_total_battles",
    "add_total_battles",
    "queue_enter",
    "queue_to_running",
    "queue_exit_running",
    "queue_exit_unstarted",
    "get_queue_count",
    "get_running_count",
]
