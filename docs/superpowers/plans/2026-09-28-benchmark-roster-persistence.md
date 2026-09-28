# Benchmark Roster Persistence & Slider State Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement named roster saving, loading, and JSON import/export for the Benchmark tab while decoupling hero widget state from generation sliders to eliminate state loss when changing generations.

**Architecture:**
1. Define `BenchmarkRoster` dataclass with JSON schema and conversion utilities in `kingshot_sim/io_pkg/rosters.py`.
2. Expose file and session storage methods in `kingshot_sim/webui/persistence.py` and hook into `backup.py` and `local_storage.py`.
3. Refactor `kingshot_sim/webui/tabs/benchmark.py` to use hero-scoped widget keys (preserving builds across slider movements) and render a roster toolbar with save, load, export, and import controls.

**Tech Stack:** Python 3.10+, Streamlit, Pydantic/dataclasses, Pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-benchmark-roster-persistence-design.md`

## Global Constraints

- Python versions supported: Python 3.10 through 3.12.
- Backward compatibility: Existing profiles, search spaces, and backup JSON files without a `"rosters"` key must load without errors.
- Session storage fallback: When `kingshot_sim.io_pkg.scope.use_session_storage()` is True, roster operations must use in-memory session storage (`_ss_rosters_store`) instead of writing to disk.
- Zero extraneous external dependencies: Use existing dependencies (`json`, `dataclasses`, `pathlib`, `streamlit`).

## Review Focus

1. **Unknown Hero Names in JSON:** `roster_from_dict` must filter or ignore invalid hero names rather than crashing.
2. **Missing HeroBuild Fields:** If a JSON build entry lacks `star` or `widget_level`, default safely (`star=5`, `widget_level=0` for epic, `4` for mythic).
3. **Invalid Generation Number:** `roster_from_dict` must clamp or validate `generation` within `1..MAX_GENERATION`.
4. **Hero State Preservation on Slider Scrubbing:** Moving `_bm_gen` from 8 to 7 and back to 8 must retain customized star and widget levels.
5. **Backwards Compatible Backup Restore:** `apply_backup_payload` on a legacy payload without `"rosters"` must succeed with `report.rosters_applied == 0`.

---

### Task 1: Benchmark Roster Data Model & Serialization

**Files:**
- Create: `kingshot_sim/io_pkg/rosters.py`
- Test: `tests/test_benchmark_roster_io.py`

**Interfaces:**
- Produces:
  - `BenchmarkRoster(name: str, generation: int, owned_heroes: dict[str, list[str]], builds: dict[str, HeroBuild])`
  - `roster_to_dict(roster: BenchmarkRoster) -> dict[str, Any]`
  - `roster_from_dict(data: dict[str, Any]) -> BenchmarkRoster`
  - `roster_to_json(roster: BenchmarkRoster, indent: int = 2) -> str`
  - `roster_from_json(raw: str) -> BenchmarkRoster`
  - `save_roster_file(roster: BenchmarkRoster, path: Path) -> None`
  - `load_roster_file(path: Path) -> BenchmarkRoster`

- [ ] **Step 1: Write the failing tests in `tests/test_benchmark_roster_io.py`**

```python
from pathlib import Path
import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import (
    BenchmarkRoster, roster_to_dict, roster_from_dict,
    roster_to_json, roster_from_json, save_roster_file, load_roster_file,
)

def test_benchmark_roster_roundtrip_dict():
    roster = BenchmarkRoster(
        name="Test Roster",
        generation=7,
        owned_heroes={"Inf": ["Jabel", "Amadeus"], "Cav": ["Margot"], "Arc": ["Yang"]},
        builds={"Jabel": HeroBuild(level="MAX", widget_level=8), "Margot": HeroBuild(level="4_2", widget_level=5)},
    )
    d = roster_to_dict(roster)
    assert d["format"] == "ksbattlehelper-roster"
    assert d["generation"] == 7
    loaded = roster_from_dict(d)
    assert loaded.name == "Test Roster"
    assert loaded.generation == 7
    assert loaded.owned_heroes == roster.owned_heroes
    assert loaded.builds["Jabel"].level == "MAX"
    assert loaded.builds["Jabel"].widget_level == 8
    assert loaded.builds["Margot"].level == "4_2"
    assert loaded.builds["Margot"].widget_level == 5

def test_benchmark_roster_roundtrip_json(tmp_path: Path):
    roster = BenchmarkRoster(
        name="JSON Roster",
        generation=8,
        owned_heroes={"Inf": ["Helga"]},
        builds={"Helga": HeroBuild(level="5_0", widget_level=0)},
    )
    raw = roster_to_json(roster)
    loaded = roster_from_json(raw)
    assert loaded.name == "JSON Roster"
    assert loaded.builds["Helga"].level == "5_0"

    p = tmp_path / "test.json"
    save_roster_file(roster, p)
    assert p.exists()
    from_file = load_roster_file(p)
    assert from_file.name == "JSON Roster"

def test_benchmark_roster_resilience_to_corrupt_data():
    raw_corrupt = {"name": "Bad", "generation": 999, "builds": {"NonExistentHero": {"level": "invalid"}}}
    loaded = roster_from_dict(raw_corrupt)
    assert loaded.name == "Bad"
    assert 1 <= loaded.generation <= 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_benchmark_roster_io.py -v`
Expected: FAIL with ModuleNotFoundError or import error for `kingshot_sim.io_pkg.rosters`.

- [ ] **Step 3: Implement `kingshot_sim/io_pkg/rosters.py`**

Implement `BenchmarkRoster` dataclass, dictionary serializer/deserializer, JSON serializer/deserializer, and file I/O methods. Handle star/tier/widget level clamping and sanitize invalid data.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_benchmark_roster_io.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/io_pkg/rosters.py tests/test_benchmark_roster_io.py
git commit -m "feat(io): add BenchmarkRoster data model and serialization"
```

---

### Task 2: Roster Persistence Layer

**Files:**
- Modify: `kingshot_sim/webui/persistence.py`
- Test: `tests/test_benchmark_roster_persistence.py`

**Interfaces:**
- Consumes: `BenchmarkRoster`, `roster_to_json`, `roster_from_json` from `kingshot_sim.io_pkg.rosters`
- Produces:
  - `list_rosters() -> list[str]`
  - `save_roster(roster: BenchmarkRoster, name: str) -> Path`
  - `load_roster(name: str) -> BenchmarkRoster`
  - `delete_roster(name: str) -> None`
  - `export_rosters_dict() -> dict[str, str]`
  - `import_roster_blob(name: str, payload: str) -> None`

- [ ] **Step 1: Write the failing tests in `tests/test_benchmark_roster_persistence.py`**

```python
from pathlib import Path
import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg.scope import set_session_storage, clear_session_storage

def test_file_roster_persistence(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ps, "_ROSTERS_DIR", tmp_path / "rosters")
    set_session_storage(False)

    r = BenchmarkRoster(name="Alpha", generation=6, owned_heroes={"Inf": ["Helga"]}, builds={"Helga": HeroBuild(level="MAX", widget_level=0)})
    ps.save_roster(r, "Alpha")

    assert "Alpha" in ps.list_rosters()
    loaded = ps.load_roster("Alpha")
    assert loaded.name == "Alpha"
    assert loaded.generation == 6

    ps.delete_roster("Alpha")
    assert "Alpha" not in ps.list_rosters()

def test_session_roster_persistence():
    set_session_storage(True)
    clear_session_storage()
    try:
        r = BenchmarkRoster(name="Beta", generation=8, owned_heroes={}, builds={})
        ps.save_roster(r, "Beta")
        assert "Beta" in ps.list_rosters()
        loaded = ps.load_roster("Beta")
        assert loaded.name == "Beta"

        exported = ps.export_rosters_dict()
        assert "Beta" in exported

        ps.delete_roster("Beta")
        assert "Beta" not in ps.list_rosters()
    finally:
        set_session_storage(False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_benchmark_roster_persistence.py -v`
Expected: FAIL with AttributeError (`list_rosters` not found in `persistence`).

- [ ] **Step 3: Implement roster persistence functions in `kingshot_sim/webui/persistence.py`**

Add `_ROSTERS_DIR = _BASE_DIR / "rosters"`, `_SS_ROSTERS_KEY = "_ks_rosters_store"`, and implement `list_rosters`, `save_roster`, `load_roster`, `delete_roster`, `export_rosters_dict`, and `import_roster_blob`. Update `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_benchmark_roster_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/persistence.py tests/test_benchmark_roster_persistence.py
git commit -m "feat(persistence): add roster persistence operations"
```

---

### Task 3: Global Backup & Restore Integration

**Files:**
- Modify: `kingshot_sim/io_pkg/backup.py`
- Test: `tests/test_backup_rosters.py`

**Interfaces:**
- Consumes: `export_rosters_dict`, `import_roster_blob`, `list_rosters`, `delete_roster` from `kingshot_sim.webui.persistence`
- Modifies: `build_backup_payload`, `apply_backup_payload`, `ImportReport`

- [ ] **Step 1: Write the failing tests in `tests/test_backup_rosters.py`**

```python
import pytest
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.io_pkg.rosters import BenchmarkRoster
from kingshot_sim.webui import persistence as ps
from kingshot_sim.io_pkg import backup
from kingshot_sim.io_pkg.scope import set_session_storage, clear_session_storage

def test_backup_roundtrip_with_rosters():
    set_session_storage(True)
    clear_session_storage()
    try:
        r = BenchmarkRoster(name="SavedRoster", generation=7, builds={"Helga": HeroBuild(level="MAX", widget_level=0)})
        ps.save_roster(r, "SavedRoster")

        blob = backup.make_backup_blob()
        payload, err = backup.parse_backup_blob(blob)
        assert err is None
        assert "rosters" in payload
        assert "SavedRoster" in payload["rosters"]

        ps.delete_roster("SavedRoster")
        assert "SavedRoster" not in ps.list_rosters()

        rep = backup.apply_backup_payload(payload, replace_existing=False)
        assert rep.rosters_applied == 1
        assert "SavedRoster" in ps.list_rosters()
        assert "roster(s)" in rep.summary()
    finally:
        set_session_storage(False)

def test_backup_backwards_compatibility_without_rosters():
    set_session_storage(True)
    clear_session_storage()
    try:
        legacy_payload = {
            "version": 1,
            "format": "ksbattlehelper-backup",
            "profiles": {},
            "search_spaces": {},
        }
        rep = backup.apply_backup_payload(legacy_payload, replace_existing=False)
        assert rep.rosters_applied == 0
        assert not rep.errors
    finally:
        set_session_storage(False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backup_rosters.py -v`
Expected: FAIL with `AssertionError: assert 'rosters' in payload`.

- [ ] **Step 3: Update `kingshot_sim/io_pkg/backup.py`**

1. In `build_backup_payload()`: include `"rosters": ps.export_rosters_dict()`.
2. In `ImportReport`: add field `rosters_applied: int = 0`, update `total_applied` and `summary()` to report rosters.
3. In `apply_backup_payload()`: handle `payload.get("rosters", {})`, process `replace_existing`, and call `ps.import_roster_blob(name, blob)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_backup_rosters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/io_pkg/backup.py tests/test_backup_rosters.py
git commit -m "feat(backup): include benchmark rosters in backup export and restore"
```

---

### Task 4: Local Storage Sync

**Files:**
- Modify: `kingshot_sim/webui/local_storage.py`
- Test: `tests/test_local_storage_benchmark.py`

**Interfaces:**
- Updates `_FORM_KEY_PREFIXES` in `local_storage.py` to persist `_bm_` keys.
- Adds `_bm_run`, `_bm_ocr_up`, `_bm_ocr_go`, `_bm_import_up` to excluded suffixes/substrings.

- [ ] **Step 1: Write the failing tests in `tests/test_local_storage_benchmark.py`**

```python
from kingshot_sim.webui.local_storage import _is_widget_key_persistable

def test_benchmark_widget_key_persistence():
    assert _is_widget_key_persistable("_bm_star_Jabel")
    assert _is_widget_key_persistable("_bm_wl_Jabel")
    assert _is_widget_key_persistable("_bm_tier_Jabel")
    assert _is_widget_key_persistable("_bm_own_Inf")
    assert _is_widget_key_persistable("_bm_active_roster")

def test_benchmark_transient_keys_excluded():
    assert not _is_widget_key_persistable("_bm_run")
    assert not _is_widget_key_persistable("_bm_ocr_up")
    assert not _is_widget_key_persistable("_bm_ocr_go")
    assert not _is_widget_key_persistable("_bm_ocr_msg")
    assert not _is_widget_key_persistable("_bm_import_upload")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_local_storage_benchmark.py -v`
Expected: FAIL because `_is_widget_key_persistable` currently filters keys not starting with known form prefixes or exclusions.

- [ ] **Step 3: Update `kingshot_sim/webui/local_storage.py`**

Add `"_bm_"` to `_FORM_KEY_PREFIXES`. Add action buttons and transient uploader keys to `_EXCLUDED_KEY_SUBSTRINGS` or `_EXCLUDED_KEY_SUFFIXES`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_local_storage_benchmark.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/local_storage.py tests/test_local_storage_benchmark.py
git commit -m "feat(local-storage): persist benchmark roster widget keys to browser storage"
```

---

### Task 5: Decouple Generation Slider & Add Roster UI in Benchmark Tab

**Files:**
- Modify: `kingshot_sim/webui/tabs/benchmark.py`
- Test: `tests/test_benchmark_ui_state.py`

**Interfaces:**
- Consumes: `BenchmarkRoster`, `roster_to_json`, `roster_from_json` from `kingshot_sim.io_pkg.rosters`
- Consumes: `list_rosters`, `save_roster`, `load_roster`, `delete_roster` from `kingshot_sim.webui.persistence`
- Modifies: `_roster_input`, `_ocr_import`, `render` in `kingshot_sim/webui/tabs/benchmark.py`

- [ ] **Step 1: Write integration tests for benchmark roster state behavior in `tests/test_benchmark_ui_state.py`**

Test helper functions that extract active roster state from `session_state` and load a `BenchmarkRoster` into `session_state`.
Verify:
1. Loading a roster restores `_bm_gen`, `_bm_own_*`, `_bm_star_*`, `_bm_tier_*`, `_bm_wl_*`.
2. Extracting active roster yields accurate `BenchmarkRoster`.
3. Changing generation preserves existing hero builds.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_benchmark_ui_state.py -v`
Expected: FAIL.

- [ ] **Step 3: Refactor `benchmark.py`**

1. Remove `_{gen}` suffix from `_bm_star_{h}`, `_bm_tier_{h}`, `_bm_wl_{h}`, and `_bm_own_{cls}` so hero stats stay constant across generations.
2. In `_roster_input(gen)`: filter `options_by_cls[cls]` to heroes valid up to `gen`, while keeping hero builds preserved in `st.session_state`.
3. Add `_render_roster_manager(gen, builds, owned)` right above Section 2:
   - Roster selector dropdown with `[Custom / Unsaved]` and saved roster names from `persistence.list_rosters()`.
   - **Save** / **Save As...** / **Delete** action buttons.
   - **Export JSON** using `st.download_button`.
   - **Import JSON** using `st.file_uploader`.
   - Loading a roster updates `_bm_gen`, `_bm_own_{cls}`, `_bm_star_{h}`, `_bm_tier_{h}`, `_bm_wl_{h}`, and reruns.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_benchmark_ui_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kingshot_sim/webui/tabs/benchmark.py tests/test_benchmark_ui_state.py
git commit -m "feat(benchmark): decouple hero state from generation slider and add roster toolbar"
```

---

### Task 6: Full Verification & Upstream PR Readiness

**Files:**
- None (verification & branch health)

- [ ] **Step 1: Run all new tests**

Run: `.venv/bin/pytest tests/test_benchmark_roster_io.py tests/test_benchmark_roster_persistence.py tests/test_backup_rosters.py tests/test_local_storage_benchmark.py tests/test_benchmark_ui_state.py -v`
Expected: ALL PASS.

- [ ] **Step 2: Run the complete test suite to ensure zero regressions**

Run: `.venv/bin/pytest tests/ -q`
Expected: ALL PASS (all 978 existing tests + new tests).

- [ ] **Step 3: Review git status and diff**

Run: `git status && git diff origin/main`
Verify clean, readable changes without leftover debug prints, temporary files, or lint errors.
