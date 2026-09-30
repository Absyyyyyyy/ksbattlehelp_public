# Quick Fight & Sensitivity Account Roster Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `AccountRoster` as the primary profile loader into Quick Fight and Sensitivity tabs, clean up redundant tabs in Settings, provide a legacy profile converter, and verify all test suites.

**Architecture:** Extend `kingshot_sim.io_pkg.roster_bridge` with canonical conversion functions (`account_roster_to_fighter` and `fighter_to_roster`), wire them into `quick_fight.py` and `sensitivity.py` using Streamlit form generation versioning to refresh widget state, streamline `settings.py` to 3 tabs with a legacy fighter converter under Advanced options, and verify with unit and AppTest test suites.

**Tech Stack:** Python 3.10+, Streamlit, Plotly, Pytest (`streamlit.testing.v1.AppTest`).

**Spec:** [`docs/superpowers/specs/2026-09-29-quick-fight-sensitivity-roster-integration-design.md`](file:///home/prmohan/projects/ksbattlehelp_public/docs/superpowers/specs/2026-09-29-quick-fight-sensitivity-roster-integration-design.md)

## Global Constraints
- Python 3.10+ compatibility.
- Do not break existing public interfaces of `Fighter`, `AccountRoster`, or `SearchSpace`.
- Use `width='stretch'` instead of deprecated `use_container_width=True` on Streamlit widgets.
- Preserve troop numbers and tiers when loading an Account Profile into a fighter form.
- Keep all existing 1069+ tests passing (`.venv/bin/pytest -q`).

## Review Focus
1. Loading an Account Profile with fewer than 3 owned heroes falls back safely to default class heroes (`Eric`, `Petra`, `Jaeger`) without raising `ValueError` or `KeyError`.
2. Existing troop configurations (counts and tiers) on `current_fighter` are preserved upon loading an Account Profile rather than being wiped.
3. Form generation keys (`_form_gen`) increment on profile load to prevent stale Streamlit session state from masking updated hero stars, widgets, and gear.
4. Legacy Fighter profiles with non-standard labels or missing gear convert cleanly into valid `AccountRoster` objects without corruption.
5. Deleting or converting a legacy profile does not crash the UI or leave lingering invalid session state.

---

### Task 1: Bridge Layer Enhancements (`kingshot_sim/io_pkg/roster_bridge.py`)

**Files:**
- Modify: `kingshot_sim/io_pkg/roster_bridge.py`
- Modify: `kingshot_sim/webui/tabs/attack_defense.py`
- Modify: `tests/test_roster_bridge.py`

**Interfaces:**
- Produces:
  - `account_roster_to_fighter(roster: AccountRoster, current_fighter: Fighter | None = None, default_label: str = "Fighter") -> Fighter`
  - `fighter_to_roster(fighter: Fighter, name: str | None = None) -> AccountRoster`

- [ ] **Step 1: Write failing tests in `tests/test_roster_bridge.py`**
Add `test_account_roster_to_fighter_complete`, `test_account_roster_to_fighter_preserves_troops`, and `test_fighter_to_roster_roundtrip`.

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_roster_bridge.py -k "account_roster_to_fighter or fighter_to_roster" -v`
Expected: FAIL with `ImportError: cannot import name 'account_roster_to_fighter'`

- [ ] **Step 3: Implement `account_roster_to_fighter` and `fighter_to_roster` in `kingshot_sim/io_pkg/roster_bridge.py`**
- Implement `account_roster_to_fighter`:
  - Intelligent leader selection per class (`Inf`, `Cav`, `Arc`), checking `roster.owned_heroes` and `roster.builds`, retaining `current_fighter` leader if present, falling back to class starters (`Eric`, `Petra`, `Jaeger`).
  - Gathers up to 4 eligible combat joiners (excluding leaders and `NON_COMBAT_FIRST_SKILL_HEROES`).
  - Equips stars, widget levels (0–10), and skills from `roster.builds`.
  - Equips class gear from `roster.class_gear`.
  - Copies `roster.bonuses` and `roster.buffs`.
  - Preserves `current_fighter.troops` if provided; defaults to `TroopRoster()` if None.
  - Sets label to `roster.name or default_label`.
- Implement `fighter_to_roster`:
  - Populates `owned_heroes` and `builds` from leaders and joiners.
  - Maps leader gear into `class_gear`.
  - Copies `bonuses` and `buffs`.
  - Derives `generation` (max hero generation, default 8).
  - Sets `name = name or fighter.label`.
- Update `__all__` in `kingshot_sim/io_pkg/roster_bridge.py`.

- [ ] **Step 4: Deduplicate `attack_defense.py` to use `account_roster_to_fighter`**
Replace local `_fighter_from_roster` in `kingshot_sim/webui/tabs/attack_defense.py` with `account_roster_to_fighter`.

- [ ] **Step 5: Run tests to verify they pass**
Run: `.venv/bin/pytest tests/test_roster_bridge.py tests/test_attack_defense_tab.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add kingshot_sim/io_pkg/roster_bridge.py kingshot_sim/webui/tabs/attack_defense.py tests/test_roster_bridge.py
git commit -m "feat(bridge): add account_roster_to_fighter and fighter_to_roster converters"
```

---

### Task 2: Quick Fight Tab Integration (`kingshot_sim/webui/tabs/quick_fight.py`)

**Files:**
- Modify: `kingshot_sim/webui/tabs/quick_fight.py`
- Create: `tests/test_quick_fight_tab.py`

**Interfaces:**
- Consumes: `account_roster_to_fighter`, `persistence.list_rosters`, `persistence.load_roster`
- Produces: Account Profile loading toolbar in Quick Fight (`qf_load_att_roster`, `qf_load_def_roster`, `qf_btn_load_att`, `qf_btn_load_def`)

- [ ] **Step 1: Write failing tests in `tests/test_quick_fight_tab.py`**
Test:
- `test_quick_fight_renders_empty_rosters_no_crash`
- `test_quick_fight_loads_attacker_from_account_profile` (verifies stars, widget levels, class gear, bonuses, and preserved troops)
- `test_quick_fight_loads_defender_from_account_profile`
- `test_quick_fight_run_battle_after_loading_rosters`

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_quick_fight_tab.py -v`
Expected: FAIL (missing widgets / keys)

- [ ] **Step 3: Update `kingshot_sim/webui/tabs/quick_fight.py`**
- Replace legacy `list_profiles()` toolbar with `list_rosters()`:
  - Selectboxes: `qf_load_att_roster` and `qf_load_def_roster`
  - Load buttons: `qf_btn_load_att` and `qf_btn_load_def`
- On button click:
  - Load `AccountRoster` via `persistence.load_roster(sel)`
  - Convert via `account_roster_to_fighter(loaded_r, curr, default_label=...)`
  - Increment `qf_att_form_gen` (or `qf_def_form_gen`)
  - Set `qf_att_input_mode = "Advanced"` and radio key to `"Advanced (manual entry)"`
  - Call `st.rerun()`

- [ ] **Step 4: Run tests to verify they pass**
Run: `.venv/bin/pytest tests/test_quick_fight_tab.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add kingshot_sim/webui/tabs/quick_fight.py tests/test_quick_fight_tab.py
git commit -m "feat(quick-fight): integrate AccountRoster profile loading for attacker and defender"
```

---

### Task 3: Sensitivity Tab Integration (`kingshot_sim/webui/tabs/sensitivity.py`)

**Files:**
- Modify: `kingshot_sim/webui/tabs/sensitivity.py`
- Create: `tests/test_sensitivity_tab.py`

**Interfaces:**
- Consumes: `account_roster_to_fighter`, `persistence.list_rosters`, `persistence.load_roster`
- Produces: Account Profile loading toolbar in Sensitivity (`sn_load_att_roster`, `sn_load_def_roster`, `sn_btn_att`, `sn_btn_def`)

- [ ] **Step 1: Write failing tests in `tests/test_sensitivity_tab.py`**
Test:
- `test_sensitivity_renders_empty_rosters_no_crash`
- `test_sensitivity_loads_attacker_and_defender_from_account_profile` (verifies stats, gear, and form key generation)
- `test_sensitivity_run_sweep_with_loaded_profile`

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_sensitivity_tab.py -v`
Expected: FAIL

- [ ] **Step 3: Update `kingshot_sim/webui/tabs/sensitivity.py`**
- Replace legacy `list_profiles()` toolbar with `list_rosters()`:
  - `sn_load_att_roster` and `sn_load_def_roster`
  - Load buttons `sn_btn_att` and `sn_btn_def`
- Manage form key generations:
  - `att_gen = st.session_state.get("sn_att_gen", 0)`
  - `def_gen = st.session_state.get("sn_def_gen", 0)`
  - `fighter_form(..., key_prefix=f"sn_att_g{att_gen}", side="attacker")`
  - `fighter_form(..., key_prefix=f"sn_def_g{def_gen}", side="defender")`
- On button click:
  - Load `AccountRoster` via `persistence.load_roster(sel)`
  - Convert via `account_roster_to_fighter(loaded_r, curr, default_label=...)`
  - Increment `sn_att_gen` (or `sn_def_gen`)
  - Call `st.rerun()`

- [ ] **Step 4: Run tests to verify they pass**
Run: `.venv/bin/pytest tests/test_sensitivity_tab.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add kingshot_sim/webui/tabs/sensitivity.py tests/test_sensitivity_tab.py
git commit -m "feat(sensitivity): integrate AccountRoster profile loading for attacker and defender"
```

---

### Task 4: Settings Tab Cleanup & Legacy Profile Migration (`kingshot_sim/webui/tabs/settings.py`)

**Files:**
- Modify: `kingshot_sim/webui/tabs/settings.py`
- Modify: `tests/test_settings_tab.py`

**Interfaces:**
- Consumes: `fighter_to_roster`, `persistence.list_profiles`, `persistence.load_profile`, `persistence.save_roster`, `persistence.delete_profile`
- Produces: 3-tab layout, legacy profiles expander with conversion, updated backup metrics

- [ ] **Step 1: Write failing tests in `tests/test_settings_tab.py`**
Test:
- `test_settings_renders_three_tabs_only` (verifies `Saved rosters` tab is gone)
- `test_legacy_fighter_profiles_inspect_convert_delete` (inspects legacy profile, converts to `AccountRoster` verifying it appears in `list_rosters()`, deletes legacy profile)
- `test_backup_restore_metrics_show_account_rosters`

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/pytest tests/test_settings_tab.py -k "three_tabs or legacy_fighter or metrics" -v`
Expected: FAIL

- [ ] **Step 3: Update `kingshot_sim/webui/tabs/settings.py`**
- Change tabs in `render()` to 3 tabs:
  `Account & roster profiles ({len(rosters)})`, `Advanced options`, `Backup & restore`
- Remove `_render_search_spaces()` and the `Saved rosters` tab.
- In `_render_advanced()`, add `Legacy Fighter Profiles ({len(profiles)}) — Deprecated` expander:
  - List each profile with Inspect, Convert (`fighter_to_roster` + `persistence.save_roster`), and Delete.
- In `_render_backup_restore()`, update metrics display to show `Account Rosters`, `Legacy Profiles`, `Op overrides`, `Data overrides`.

- [ ] **Step 4: Run tests to verify they pass**
Run: `.venv/bin/pytest tests/test_settings_tab.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite across the repository**
Run: `.venv/bin/pytest -q`
Expected: 1070+ passed, 0 failures.

- [ ] **Step 6: Commit**
```bash
git add kingshot_sim/webui/tabs/settings.py tests/test_settings_tab.py
git commit -m "refactor(settings): clean up redundant tabs and add legacy fighter profile converter"
```
