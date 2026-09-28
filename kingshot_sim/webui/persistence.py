from __future__ import annotations
from pathlib import Path

from kingshot_sim.config.fighter import Fighter
from kingshot_sim.optimizer.search_space import SearchSpace
from kingshot_sim.io_pkg.profiles import (
    save_fighter, load_fighter, fighter_to_json, fighter_from_json,
)
from kingshot_sim.io_pkg.search_space_io import (
    save_search_space, load_search_space,
    search_space_to_json, search_space_from_json,
)
from kingshot_sim.io_pkg.rosters import (
    BenchmarkRoster,
    save_roster_file, load_roster_file,
    roster_to_json, roster_from_json,
)
from kingshot_sim.io_pkg.scope import use_session_storage, session_dict


def _use_session_backend() -> bool:
    return use_session_storage()


_BASE_DIR = Path.home() / ".kingshot_sim"
_PROFILES_DIR = _BASE_DIR / "profiles"
_SEARCH_DIR = _BASE_DIR / "search_spaces"
_ROSTERS_DIR = _BASE_DIR / "rosters"

_SS_PROFILES_KEY = "_ks_profiles_store"
_SS_SEARCH_KEY = "_ks_search_store"
_SS_ROSTERS_KEY = "_ks_rosters_store"


def _ensure_dirs() -> None:
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    _SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    _ROSTERS_DIR.mkdir(parents=True, exist_ok=True)


def _list_dir_stems(directory: Path) -> tuple[str, ...]:
    if not directory.exists():
        return ()
    return tuple(sorted(p.stem for p in directory.glob("*.json")))


try:
    import streamlit as _st

    @_st.cache_data(ttl=5, show_spinner=False)
    def _cached_profile_stems(_dir_str: str) -> tuple[str, ...]:
        return _list_dir_stems(Path(_dir_str))
except Exception:
    def _cached_profile_stems(_dir_str: str) -> tuple[str, ...]:
        return _list_dir_stems(Path(_dir_str))


def _invalidate_profile_caches() -> None:
    try:
        _cached_profile_stems.clear()
    except Exception:
        pass


def _safe_name(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    return safe or "unnamed"


def _ss_profiles() -> dict[str, str]:
    return session_dict(_SS_PROFILES_KEY)


def _ss_searches() -> dict[str, str]:
    return session_dict(_SS_SEARCH_KEY)


def _ss_rosters() -> dict[str, str]:
    return session_dict(_SS_ROSTERS_KEY)


def list_profiles() -> list[str]:
    if _use_session_backend():
        return sorted(_ss_profiles().keys())
    _ensure_dirs()
    return list(_cached_profile_stems(str(_PROFILES_DIR)))


def list_search_spaces() -> list[str]:
    if _use_session_backend():
        return sorted(_ss_searches().keys())
    _ensure_dirs()
    return list(_cached_profile_stems(str(_SEARCH_DIR)))


def list_rosters() -> list[str]:
    if _use_session_backend():
        return sorted(_ss_rosters().keys())
    _ensure_dirs()
    return list(_cached_profile_stems(str(_ROSTERS_DIR)))


def save_profile(fighter: Fighter, name: str) -> Path:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_profiles()[safe] = fighter_to_json(fighter)
        return Path("/session/profiles") / f"{safe}.json"
    _ensure_dirs()
    path = _PROFILES_DIR / f"{safe}.json"
    save_fighter(fighter, path)
    _invalidate_profile_caches()
    return path


def load_profile(name: str) -> Fighter:
    safe = _safe_name(name)
    if _use_session_backend():
        store = _ss_profiles()
        if safe not in store:
            raise FileNotFoundError(f"Profile not found in session: {name}")
        return fighter_from_json(store[safe])
    path = _PROFILES_DIR / f"{safe}.json"
    return load_fighter(path)


def delete_profile(name: str) -> None:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_profiles().pop(safe, None)
        return
    path = _PROFILES_DIR / f"{safe}.json"
    if path.exists():
        path.unlink()
        _invalidate_profile_caches()


def save_search(space: SearchSpace, name: str) -> Path:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_searches()[safe] = search_space_to_json(space)
        return Path("/session/search_spaces") / f"{safe}.json"
    _ensure_dirs()
    path = _SEARCH_DIR / f"{safe}.json"
    save_search_space(space, path)
    _invalidate_profile_caches()
    return path


def load_search(name: str) -> SearchSpace:
    safe = _safe_name(name)
    if _use_session_backend():
        store = _ss_searches()
        if safe not in store:
            raise FileNotFoundError(f"Search space not found in session: {name}")
        return search_space_from_json(store[safe])
    path = _SEARCH_DIR / f"{safe}.json"
    return load_search_space(path)


def delete_search(name: str) -> None:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_searches().pop(safe, None)
        return
    path = _SEARCH_DIR / f"{safe}.json"
    if path.exists():
        path.unlink()
        _invalidate_profile_caches()


def save_roster(roster: BenchmarkRoster, name: str) -> Path:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_rosters()[safe] = roster_to_json(roster)
        return Path("/session/rosters") / f"{safe}.json"
    _ensure_dirs()
    path = _ROSTERS_DIR / f"{safe}.json"
    save_roster_file(roster, path)
    _invalidate_profile_caches()
    return path


def load_roster(name: str) -> BenchmarkRoster:
    safe = _safe_name(name)
    if _use_session_backend():
        store = _ss_rosters()
        if safe not in store:
            raise FileNotFoundError(f"Roster not found in session: {name}")
        return roster_from_json(store[safe])
    path = _ROSTERS_DIR / f"{safe}.json"
    return load_roster_file(path)


def delete_roster(name: str) -> None:
    safe = _safe_name(name)
    if _use_session_backend():
        _ss_rosters().pop(safe, None)
        return
    path = _ROSTERS_DIR / f"{safe}.json"
    if path.exists():
        path.unlink()
        _invalidate_profile_caches()


def is_session_backend() -> bool:
    return _use_session_backend()


def export_profiles_dict() -> dict[str, str]:
    if _use_session_backend():
        return dict(_ss_profiles())
    _ensure_dirs()
    out: dict[str, str] = {}
    for stem in _cached_profile_stems(str(_PROFILES_DIR)):
        try:
            out[stem] = (_PROFILES_DIR / f"{stem}.json").read_text(encoding="utf-8")
        except OSError:
            pass
    return out


def export_searches_dict() -> dict[str, str]:
    if _use_session_backend():
        return dict(_ss_searches())
    _ensure_dirs()
    out: dict[str, str] = {}
    for stem in _cached_profile_stems(str(_SEARCH_DIR)):
        try:
            out[stem] = (_SEARCH_DIR / f"{stem}.json").read_text(encoding="utf-8")
        except OSError:
            pass
    return out


def export_rosters_dict() -> dict[str, str]:
    if _use_session_backend():
        return dict(_ss_rosters())
    _ensure_dirs()
    out: dict[str, str] = {}
    for stem in _cached_profile_stems(str(_ROSTERS_DIR)):
        try:
            out[stem] = (_ROSTERS_DIR / f"{stem}.json").read_text(encoding="utf-8")
        except OSError:
            pass
    return out


def import_profile_blob(name: str, payload: str) -> None:
    fighter = fighter_from_json(payload)
    save_profile(fighter, name)


def import_search_blob(name: str, payload: str) -> None:
    space = search_space_from_json(payload)
    save_search(space, name)


def import_roster_blob(name: str, payload: str) -> None:
    roster = roster_from_json(payload)
    save_roster(roster, name)


__all__ = [
    "list_profiles", "list_search_spaces", "list_rosters",
    "save_profile", "load_profile", "delete_profile",
    "save_search", "load_search", "delete_search",
    "save_roster", "load_roster", "delete_roster",
    "fighter_to_json", "fighter_from_json",
    "roster_to_json", "roster_from_json",
    "is_session_backend",
    "export_profiles_dict", "export_searches_dict", "export_rosters_dict",
    "import_profile_blob", "import_search_blob", "import_roster_blob",
]
