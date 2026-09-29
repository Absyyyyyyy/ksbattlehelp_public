# Unified Roster Manager & Account Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a unified Account & Roster Profile (`AccountRoster`) acting as a single source of truth for owned heroes, widgets, class gear, account bonuses, and buffs, with seamless bridging into Benchmark and Attack & Defense (for both player candidates and opponents) and local testing overrides.

**Architecture:** Evolve `BenchmarkRoster` into `AccountRoster` (`format: "ksbattlehelper-roster"`, `version: 2`) with backward-compatible v1 ingestion in `rosters.py`. Provide domain translation in `roster_bridge.py` (`roster_to_search_space`, `update_roster_from_search_space`, `roster_to_fighter`, `apply_roster_to_benchmark`). Integrate a consolidated Profile Manager into the Settings tab, and cross-tab profile toolbars with non-destructive local overrides into Benchmark and Attack & Defense tabs.

**Tech Stack:** Python 3.10+, dataclasses, Pydantic, Streamlit, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-29-unified-roster-manager-design.md`

## Global Constraints
- Python 3.10+ compatibility with strict type annotations (`from __future__ import annotations`).
- Format string: `"ksbattlehelper-roster"`, current version: `2`.
- Backward compatibility: All v1 JSON payloads must load without errors, defaulting missing `class_gear` to `{}`, `bonuses` to `BonusVector()`, and `buffs` to `Buffs()`.
- Backward-compatible symbol alias: `BenchmarkRoster = AccountRoster` exported from `kingshot_sim.io_pkg.rosters`.
- Clean separation: Simulator engine math and benchmark scoring logic remain untouched.
- Feature branch: All work committed to `feature/unified-roster-manager`.

## Review Focus
1. Loading legacy v1 `ksbattlehelper-roster` JSON files must gracefully default `class_gear`, `bonuses`, and `buffs` without raising `KeyError` or schema validation exceptions.
2. In-tab edits to hero widgets or gear in Benchmark and Attack & Defense must never mutate the saved disk/session profile unless the user explicitly triggers "Save Changes Back to Profile".
3. Non-combat first-skill heroes (e.g. economy heroes) must be filtered out when mapping owned heroes to `available_joiners` in `roster_to_search_space()`.
4. Opponent fighter assembly via `roster_to_fighter()` must correctly map class gear to each leader according to their respective hero class (Infantry -> Inf, Cavalry -> Cav, Archer -> Arc).
5. Application backup export (`kingshot_sim/io_pkg/backup.py`) and restore must roundtrip `AccountRoster` v2 payloads without losing gear, bonuses, or buffs.

---

### Task 1: Domain Model & Serialization (`AccountRoster` v2)

**Files:**
- Create/Modify: `kingshot_sim/io_pkg/rosters.py`
- Test: `tests/test_rosters.py`

**Interfaces:**
- Consumes: `HeroBuild` from `kingshot_sim.benchmark.runner`, `HeroGearPiece`, `BonusVector` from `kingshot_sim.config.fighter`, `Buffs` from `kingshot_sim.config.buffs`.
- Produces: `AccountRoster`, `BenchmarkRoster`, `roster_to_dict`, `roster_from_dict`, `roster_to_json`, `roster_from_json`, `save_roster_file`, `load_roster_file`.

- [ ] **Step 1: Write the failing tests in `tests/test_rosters.py`**

```python
from kingshot_sim.io_pkg.rosters import (
    AccountRoster, BenchmarkRoster, roster_to_dict, roster_from_dict,
    roster_to_json, roster_from_json,
)
from kingshot_sim.config.fighter import HeroGearPiece, BonusVector
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.benchmark.runner import HeroBuild

def test_account_roster_v2_roundtrip():
    r = AccountRoster(
        name="Main Account",
        generation=8,
        owned_heroes={"Inf": ["Jabel"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={"Jabel": HeroBuild(level="MAX", widget_level=8, skill_levels=(5, 5, 5))},
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100, enhance=5, forge_mastery=2)}},
        bonuses=BonusVector(squad_atk_pct=120.0, inf_atk_pct=80.0),
        buffs=Buffs(city_let=10, grizzly_level=5),
    )
    payload = roster_to_json(r)
    loaded = roster_from_json(payload)
    assert loaded.name == "Main Account"
    assert loaded.generation == 8
    assert loaded.class_gear["Inf"]["head"].level == 100
    assert loaded.bonuses.squad_atk_pct == 120.0
    assert loaded.buffs.city_let == 10

def test_account_roster_v1_backward_compatibility():
    v1_raw = '''{
        "version": 1,
        "format": "ksbattlehelper-roster",
        "name": "Legacy Roster",
        "generation": 7,
        "owned_heroes": {"Cav": ["Margot"]},
        "builds": {"Margot": {"star": 4, "sub_tier": 2, "level": "4_2", "widget_level": 4}}
    }'''
    loaded = roster_from_json(v1_raw)
    assert loaded.name == "Legacy Roster"
    assert loaded.generation == 7
    assert loaded.class_gear == {}
    assert isinstance(loaded.bonuses, BonusVector)
    assert isinstance(loaded.buffs, Buffs)
    assert BenchmarkRoster is AccountRoster
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rosters.py -v`  
Expected: FAIL with `ImportError` or missing `AccountRoster` / missing fields.

- [ ] **Step 3: Implement `AccountRoster` and v2 serialization in `kingshot_sim/io_pkg/rosters.py`**

Define `AccountRoster` dataclass with `class_gear`, `bonuses`, `buffs`. Update `roster_to_dict` to serialize `class_gear` via `HeroGearPieceSchema`, `bonuses` via `BonusVectorSchema`, and `buffs` via `BuffsSchema`. In `roster_from_dict`, check version/presence of fields and fallback to defaults gracefully. Alias `BenchmarkRoster = AccountRoster`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_rosters.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/io_pkg/rosters.py tests/test_rosters.py
git commit -m "feat(io): implement AccountRoster v2 data model and backward-compatible serialization"
```

---

### Task 2: Domain Bridge Layer (`roster_bridge.py`)

**Files:**
- Create: `kingshot_sim/io_pkg/roster_bridge.py`
- Test: `tests/test_roster_bridge.py`

**Interfaces:**
- Consumes: `AccountRoster` from `kingshot_sim.io_pkg.rosters`, `SearchSpace`, `LeaderSpec` from `kingshot_sim.optimizer.search_space`, `Fighter`, `LeaderHero`, `JoinerHero`, `TroopRoster` from `kingshot_sim.config.fighter`.
- Produces: `roster_to_search_space`, `update_roster_from_search_space`, `roster_to_fighter`, `apply_roster_to_benchmark`, `extract_roster_from_benchmark`.

- [ ] **Step 1: Write the failing tests in `tests/test_roster_bridge.py`**

```python
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.config.fighter import HeroGearPiece, BonusVector, TroopRoster, TroopGroup
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.io_pkg.roster_bridge import (
    roster_to_search_space, update_roster_from_search_space, roster_to_fighter,
)

def test_roster_to_search_space():
    r = AccountRoster(
        name="Test Roster",
        owned_heroes={"Inf": ["Jabel", "Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={
            "Jabel": HeroBuild(level="MAX", widget_level=8),
            "Margot": HeroBuild(level="4_2", widget_level=4),
        },
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="mythic", level=50)}},
        bonuses=BonusVector(squad_atk_pct=50.0),
        buffs=Buffs(city_atk=10),
    )
    sp = roster_to_search_space(r)
    assert "Jabel" in sp.available_mythic_inf
    assert "Margot" in sp.available_mythic_cav
    assert "Yang" in sp.available_mythic_arc
    assert sp.leader_specs["Jabel"].widget_level == 8
    assert sp.class_gear["Inf"]["head"].level == 50
    assert sp.bonuses.squad_atk_pct == 50.0
    assert sp.buffs.city_atk == 10

def test_roster_to_fighter():
    r = AccountRoster(
        name="Opponent",
        builds={"Jabel": HeroBuild(level="MAX", widget_level=10), "Margot": HeroBuild(level="MAX", widget_level=8)},
        class_gear={"Inf": {"head": HeroGearPiece(slot="head", quality="red", level=100)}},
    )
    fighter = roster_to_fighter(r, inf_hero="Jabel", cav_hero="Margot", arc_hero="Yang", label="Enemy")
    assert fighter.label == "Enemy"
    assert fighter.leader_inf.hero_name == "Jabel"
    assert fighter.leader_inf.widget_level == 10
    assert fighter.leader_inf.gear["head"].level == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_roster_bridge.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'kingshot_sim.io_pkg.roster_bridge'`

- [ ] **Step 3: Implement `roster_bridge.py`**

Implement `roster_to_search_space`, `update_roster_from_search_space`, `roster_to_fighter`, `apply_roster_to_benchmark`, and `extract_roster_from_benchmark`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_roster_bridge.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/io_pkg/roster_bridge.py tests/test_roster_bridge.py
git commit -m "feat(bridge): implement bidirectional roster to search space and fighter adapters"
```

---

### Task 3: Persistence, Application Backup & Local Storage Integration

**Files:**
- Modify: `kingshot_sim/webui/persistence.py:10-250`
- Modify: `kingshot_sim/io_pkg/backup.py:10-120`
- Modify: `kingshot_sim/webui/local_storage.py:10-50`
- Test: `tests/test_persistence.py`, `tests/test_backup.py`

**Interfaces:**
- Consumes: `AccountRoster` from `kingshot_sim.io_pkg.rosters`.
- Produces: `persistence.list_rosters`, `persistence.save_roster`, `persistence.load_roster`, `persistence.delete_roster`, `backup.build_backup_payload`, `backup.parse_backup_blob`.

- [ ] **Step 1: Write the failing tests in `tests/test_persistence.py` and `tests/test_backup.py`**

```python
def test_persistence_roster_roundtrip(tmp_path, monkeypatch):
    from kingshot_sim.webui import persistence as ps
    from kingshot_sim.io_pkg.rosters import AccountRoster
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    r = AccountRoster(name="PersistTest", generation=8)
    ps.save_roster(r, "PersistTest")
    assert "PersistTest" in ps.list_rosters()
    loaded = ps.load_roster("PersistTest")
    assert loaded.name == "PersistTest"
    ps.delete_roster("PersistTest")
    assert "PersistTest" not in ps.list_rosters()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_persistence.py tests/test_backup.py -v`  
Expected: FAIL or missing v2 roster verification.

- [ ] **Step 3: Update `persistence.py`, `backup.py`, and `local_storage.py`**

1. In `persistence.py`, ensure `save_roster`, `load_roster`, and `export_rosters_dict` use `AccountRoster`.
2. In `backup.py`, verify `build_backup_payload` includes rosters in export, and `parse_backup_blob` restores them via `ps.save_roster`.
3. In `local_storage.py`, register `_ks_active_roster` in `LOCAL_STORAGE_KEYS`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_persistence.py tests/test_backup.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/persistence.py kingshot_sim/io_pkg/backup.py kingshot_sim/webui/local_storage.py tests/test_persistence.py tests/test_backup.py
git commit -m "feat(persistence): wire AccountRoster into persistence, backup, and local storage"
```

---

### Task 4: Settings Tab Account & Roster Profile Manager

**Files:**
- Modify: `kingshot_sim/webui/tabs/settings.py`
- Test: Unit/UI invocation test in `tests/test_settings_tab.py`

**Interfaces:**
- Consumes: `persistence.list_rosters`, `persistence.save_roster`, `persistence.load_roster`, `persistence.delete_roster`, `class_gear_editor`, `bonuses_form`, `buffs_form` from `kingshot_sim.webui.forms`.
- Produces: `render_account_roster_section()` rendered in `settings.render()`.

- [ ] **Step 1: Write test for Settings Roster UI helper**

Verify that roster management sub-components render and handle CRUD without throwing exceptions.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_tab.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `render_account_roster_section()` in `settings.py`**

Add an expander/section in `settings.py` with:
- Profile selector, New Profile, Save, Delete, Export/Import JSON.
- Generation slider.
- Hero class tabs with owned hero checkboxes, star tiers, and widget sliders.
- Embedded `class_gear_editor`, `bonuses_form`, and `buffs_form`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_tab.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/tabs/settings.py tests/test_settings_tab.py
git commit -m "feat(ui): add Account & Roster Profile section to Settings tab"
```

---

### Task 5: Benchmark Tab Profile Integration & Class Gear Support

**Files:**
- Modify: `kingshot_sim/webui/tabs/benchmark.py`
- Modify: `kingshot_sim/benchmark/runner.py:120-150`
- Test: `tests/test_benchmark_tab.py`

**Interfaces:**
- Consumes: `apply_roster_to_benchmark`, `extract_roster_from_benchmark` from `roster_bridge`.
- Produces: Benchmark Profile Toolbar with active profile dropdown, Reload, and Save Back.

- [ ] **Step 1: Write test for benchmark roster integration**

Verify `BenchmarkRunner.run()` propagates `class_gear` to `build_trio()`, and benchmark session state accurately synchronizes with `AccountRoster`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_benchmark_tab.py -v`  
Expected: FAIL

- [ ] **Step 3: Update `benchmark.py` and `runner.py`**

1. In `benchmark.py`, replace the legacy toolbar with the unified Profile Toolbar (`[ Profile Dropdown ] [ 🔄 Reload ] [ 💾 Save Changes Back ]`).
2. Pass active profile's `class_gear` to `BenchmarkRunner.run()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_benchmark_tab.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/tabs/benchmark.py kingshot_sim/benchmark/runner.py tests/test_benchmark_tab.py
git commit -m "feat(benchmark): integrate unified AccountRoster toolbar and class gear simulation"
```

---

### Task 6: Attack & Defense Tab Candidate & Opponent Profile Integration

**Files:**
- Modify: `kingshot_sim/webui/tabs/attack_defense.py`
- Test: `tests/test_attack_defense_tab.py`

**Interfaces:**
- Consumes: `roster_to_search_space`, `update_roster_from_search_space`, `roster_to_fighter` from `roster_bridge`.
- Produces: Opponent setup from profile in §1, Candidate search space pre-fill and local overrides in §2.

- [ ] **Step 1: Write test for Attack & Defense profile loading**

Verify that loading an `AccountRoster` into candidate `SearchSpace` populates heroes/widgets/gear/bonuses, that local in-tab edits remain non-destructive, and that loading an opponent profile correctly initializes opponent bonuses and gear.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_attack_defense_tab.py -v`  
Expected: FAIL

- [ ] **Step 3: Update `attack_defense.py`**

1. In §1 (Opponent Setup): Add "Load Opponent from Account Profile" selector calling `roster_to_fighter()`.
2. In §2 (Candidate Setup): Add Profile Toolbar calling `roster_to_search_space()` to pre-fill inputs while preserving local interactive overrides, and a "Save Changes Back to Profile" button calling `update_roster_from_search_space()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_attack_defense_tab.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/tabs/attack_defense.py tests/test_attack_defense_tab.py
git commit -m "feat(optimizer): wire AccountRoster into Attack & Defense candidate and opponent setups"
```

---

### Task 7: Full Test Suite Regression & End-to-End Verification

**Files:**
- Test: `tests/` (entire suite)

- [ ] **Step 1: Execute complete pytest test suite**

Run: `pytest`  
Expected: All tests pass with 0 failures, 0 errors.

- [ ] **Step 2: Verify Streamlit application launch syntax**

Run: `python -m py_compile kingshot_sim/webui/app.py kingshot_sim/webui/tabs/*.py`  
Expected: Exit code 0, no syntax or compile errors.

- [ ] **Step 3: Final Commit & Tag**

```bash
git commit --allow-empty -m "chore: verify test suite health and complete unified roster manager integration"
```
