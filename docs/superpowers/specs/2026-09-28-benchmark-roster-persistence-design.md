# Benchmark Roster Persistence & State Preservation Design Spec

**Date:** 2026-09-28  
**Status:** Draft / Approved by User  
**Target Repository:** `Absyyyyyyy/ksbattlehelp_public`  
**Feature Branch:** `feature/benchmark-roster-persistence`  

---

## 1. Problem Statement & Motivation

1. **State Loss on Generation Change:** In the Benchmark tab (`kingshot_sim/webui/tabs/benchmark.py`), widget session state keys are generated with generation suffixes (`f"_bm_star_{h}_{gen}"`, `f"_bm_own_{cls}_{gen}"`, etc.). When a user moves the generation slider (e.g. from Gen 8 to Gen 7), Streamlit looks up keys with `_7`, causing previously customized hero star levels, sub-tiers, widgets, and selections to be lost or reset to defaults.
2. **Missing Save / Export / Load Capabilities:** Players frequently benchmark different roster configurations (e.g., "Current Account", "F2P Baseline", "Whale Setup"). There is currently no way to name, save, load, export (as JSON), or import roster configurations in the Benchmark tab.
3. **No Browser LocalStorage Sync:** Unlike battle configurations in other tabs, `_bm_` keys are not persisted to browser `localStorage`, making the benchmark tab vulnerable to state loss on page reloads.

---

## 2. Goals & Non-Goals

### Goals
- **Decoupled Hero State:** Hero star levels, sub-tier ascensions, and widget levels belong to the *hero* across generations, not to a single generation. Moving the generation slider must filter available hero choices without wiping configured values.
- **First-Class Benchmark Roster Entity:** Define `BenchmarkRoster` containing the roster name, selected generation level, owned hero mapping, and hero build details.
- **Persistence & Cloud Parity:** Support saving, loading, listing, and deleting named rosters in `~/.kingshot_sim/rosters/` (local) and `_ss_rosters` in session state (cloud environments where `use_session_storage()` is true).
- **Import / Export:** Provide JSON download and upload capabilities for individual benchmark rosters, and integrate benchmark rosters into the application-wide backup/restore system in `kingshot_sim/io_pkg/backup.py`.
- **LocalStorage Sync:** Include `_bm_` state in `kingshot_sim/webui/local_storage.py` so active work is preserved across browser refreshes.
- **Upstream PR Quality:** Clean separation of concerns, 100% automated test coverage, zero extraneous dependencies, full backwards compatibility.

### Non-Goals
- Changing the benchmark simulation math, scenario weights, or scoring algorithms.
- Modifying combat engine logic in `kingshot_sim/engine/`.

---

## 3. Architecture & Data Model

### 3.1 Data Schema: `BenchmarkRoster`
Location: `kingshot_sim/io_pkg/rosters.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from kingshot_sim.benchmark.runner import HeroBuild

@dataclass
class BenchmarkRoster:
    name: str
    generation: int
    owned_heroes: dict[str, list[str]] = field(default_factory=dict)
    builds: dict[str, HeroBuild] = field(default_factory=dict)
```

JSON representation (`format: "ksbattlehelper-roster"`):
```json
{
  "version": 1,
  "format": "ksbattlehelper-roster",
  "name": "Main Account",
  "generation": 8,
  "owned_heroes": {
    "Inf": ["Jabel", "Amadeus", "Helga"],
    "Cav": ["Margot", "Vivian"],
    "Arc": ["Yang", "Petra"]
  },
  "builds": {
    "Jabel": {
      "star": 5,
      "sub_tier": 0,
      "level": "MAX",
      "widget_level": 8
    },
    "Margot": {
      "star": 4,
      "sub_tier": 2,
      "level": "4_2",
      "widget_level": 4
    }
  }
}
```

Serialization API:
- `roster_to_dict(roster: BenchmarkRoster) -> dict[str, Any]`
- `roster_from_dict(data: dict[str, Any]) -> BenchmarkRoster`
- `roster_to_json(roster: BenchmarkRoster, indent: int = 2) -> str`
- `roster_from_json(raw: str) -> BenchmarkRoster`
- `save_roster_file(roster: BenchmarkRoster, path: Path) -> None`
- `load_roster_file(path: Path) -> BenchmarkRoster`

---

## 4. Persistence, Backup & Local Storage Integration

### 4.1 Persistence Layer (`kingshot_sim/webui/persistence.py`)
- Directory: `_ROSTERS_DIR = _BASE_DIR / "rosters"`
- Session store key: `_SS_ROSTERS_KEY = "_ks_rosters_store"`
- Methods added:
  - `list_rosters() -> list[str]`
  - `save_roster(roster: BenchmarkRoster, name: str) -> Path`
  - `load_roster(name: str) -> BenchmarkRoster`
  - `delete_roster(name: str) -> None`
  - `export_rosters_dict() -> dict[str, str]`
  - `import_roster_blob(name: str, payload: str) -> None`

### 4.2 Application Backup (`kingshot_sim/io_pkg/backup.py`)
- Export payload includes `"rosters": ps.export_rosters_dict()`.
- Import payload handles `"rosters"` section with `report.rosters_applied` counter and summary string inclusion (`"X roster(s)"`).
- Backwards compatibility: payload parsing safely defaults missing `"rosters"` key to `{}`.

### 4.3 Browser LocalStorage (`kingshot_sim/webui/local_storage.py`)
- Add `"_bm_"` to `_FORM_KEY_PREFIXES`.
- Exclude transient action keys: `"_bm_run"`, `"_bm_ocr_up"`, `"_bm_ocr_go"`, `"_bm_import_up"`, `"_bm_btn"`, etc.

---

## 5. UI & State Decoupling in Benchmark Tab

Location: `kingshot_sim/webui/tabs/benchmark.py`

### 5.1 Hero Widget Key Decoupling
- Change:
  - `f"_bm_star_{h}_{gen}"` $\to$ `f"_bm_star_{h}"`
  - `f"_bm_tier_{h}_{gen}"` $\to$ `f"_bm_tier_{h}"`
  - `f"_bm_wl_{h}_{gen}"` $\to$ `f"_bm_wl_{h}"`
  - `f"_bm_own_{cls}_{gen}"` $\to$ `f"_bm_own_{cls}"`
- When generation slider moves:
  - `options_by_cls[cls]` updates to reflect heroes valid up to `gen`.
  - The multiselect widget displays currently owned heroes intersecting with the available generation options.
  - No star, tier, or widget values are reset.

### 5.2 Roster Management Toolbar
Placed at the top of Section 2 ("Your roster"):
- **Roster Selector Dropdown:**
  - Lists saved rosters from `persistence.list_rosters()` plus an option `[Custom / Unsaved]`.
- **Action Buttons:**
  - **Save:** Overwrite/save the currently selected roster.
  - **Save As...:** Inline dialog/form to name and create a new roster.
  - **Delete:** Remove the current roster.
  - **Export JSON:** `st.download_button` downloading `<roster_name>.json`.
  - **Import JSON:** File uploader expander to read a roster JSON and load it into the active session.
- **Roster Load Execution:**
  - Updates `_bm_gen` to the roster's saved generation.
  - Sets `_bm_own_{cls}` for `"Inf"`, `"Cav"`, `"Arc"`.
  - Sets `_bm_star_{h}`, `_bm_tier_{h}`, `_bm_wl_{h}` for each hero in `roster.builds`.
  - Calls `st.rerun()` to refresh the form.

---

## 6. Testing Strategy

1. **Unit Tests for Serialization (`tests/test_benchmark_roster_io.py`):**
   - Roundtrip dict and JSON serialization.
   - Handling of level codes `"MAX"`, `"5_0"`, `"4_2"`.
   - Star level clamping (0..5), widget clamping (0..10).
   - Unknown hero handling and graceful validation.
2. **Unit Tests for Persistence (`tests/test_benchmark_roster_persistence.py`):**
   - File-based save, load, list, delete.
   - Cloud session-storage save, load, list, delete.
   - Overwrite behavior and name sanitization.
3. **Unit Tests for Backup (`tests/test_backup_rosters.py`):**
   - Backup creation includes saved rosters.
   - Backup restore restores rosters with `replace_existing=True` and `replace_existing=False`.
   - Backward compatibility with legacy backups lacking the `"rosters"` key.
4. **Full Regression Test Suite:**
   - Execute all 978 existing tests to guarantee zero regressions across the entire simulator.
