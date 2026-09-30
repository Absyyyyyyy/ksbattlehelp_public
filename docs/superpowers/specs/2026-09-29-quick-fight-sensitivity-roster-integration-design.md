# Design Spec: Quick Fight & Sensitivity Account Roster Integration and Settings Cleanup

## 1. Overview & Goals
PR #3 builds on top of PR #2 (`feature/unified-roster-manager`) to establish `AccountRoster` as the unified source of truth across all tabs in the KingShot Battle Helper application.

Key Goals:
1. **Quick Fight Integration (`kingshot_sim/webui/tabs/quick_fight.py`)**: Replace legacy `Fighter` profile loading with `AccountRoster` loading for Attacker and Defender. Loading automatically pre-populates 3 leaders with exact stars, widget levels (0–10), skill levels, class gear, account stat bonuses (`BonusVector`), and buffs (`Buffs`), while preserving interactive troop sliders.
2. **Sensitivity Analysis Integration (`kingshot_sim/webui/tabs/sensitivity.py`)**: Provide the same Account Profile loader for Attacker and Defender, with form generation versioning so sweeps run directly against saved profiles.
3. **Settings Tab Cleanup (`kingshot_sim/webui/tabs/settings.py`)**: Remove the redundant `Saved rosters` (`SearchSpace`) tab, relocate legacy `Saved profiles` (`Fighter`) into an expander under `Advanced options` (with inspect, delete, and one-click conversion to `AccountRoster`), and update backup metrics.
4. **Testing & Verification**: Comprehensive unit tests and Streamlit `AppTest` coverage for Quick Fight, Sensitivity, Settings cleanup, and conversion functions, verifying full test suite passage.

---

## 2. Architecture & Data Flow

### 2.1 Bridge Layer Extensions (`kingshot_sim/io_pkg/roster_bridge.py`)

#### `account_roster_to_fighter`
A generalized converter for turning an `AccountRoster` into a `Fighter`:
```python
def account_roster_to_fighter(
    roster: AccountRoster,
    current_fighter: Fighter | None = None,
    default_label: str = "Fighter",
) -> Fighter:
```
- **Leader Selection**:
  - For each class (`Inf`, `Cav`, `Arc`), checks `roster.owned_heroes[cls]` and `roster.builds`.
  - If `current_fighter` already has a leader of that class that exists in the roster's builds or owned heroes, it retains that leader.
  - Otherwise, picks the first owned/built hero for that class, falling back to class starters (`Eric`, `Petra`, `Jaeger`).
- **Builds & Gear**:
  - Leaders receive exact star tiers (`level`), `widget_level` (0–10), and `skill_levels` from `roster.builds`.
  - Class gear from `roster.class_gear[cls]` (head, chest, gloves, boots) is attached to each leader.
- **Joiners**:
  - If `current_fighter` has joiners, retains valid combat joiners (excluding chosen leaders and non-combat heroes).
  - Otherwise, gathers up to 4 eligible combat joiners from `roster.owned_heroes`.
- **Stats & Buffs**:
  - Applies `roster.bonuses` (`BonusVector`) and `roster.buffs` (`Buffs`).
- **Troop Preservation**:
  - Preserves `current_fighter.troops` if provided; defaults to `TroopRoster()` if None.
- **Label**:
  - Set to `roster.name or default_label`.

#### `fighter_to_roster`
A migration function for converting a legacy `Fighter` profile into an `AccountRoster`:
```python
def fighter_to_roster(
    fighter: Fighter,
    name: str | None = None,
) -> AccountRoster:
```
- Maps `leader_inf`, `leader_cav`, `leader_arc` and `joiners` into `owned_heroes` and `builds`.
- Maps leader gear into `class_gear` for `Inf`, `Cav`, and `Arc`.
- Preserves `bonuses` and `buffs`.
- Derives `generation` from the highest hero generation (default 8).
- Sets `name = name or fighter.label`.

---

## 3. WebUI Integration

### 3.1 Quick Fight (`kingshot_sim/webui/tabs/quick_fight.py`)
- Query `rosters = persistence.list_rosters()`.
- Display a 4-column toolbar:
  - `sel_a = st.selectbox("Load attacker from Account Profile", ["—"] + rosters, key="qf_load_att_roster")`
  - Button `→ Attacker` (`key="qf_btn_load_att"`)
  - `sel_d = st.selectbox("Load defender from Account Profile", ["—"] + rosters, key="qf_load_def_roster")`
  - Button `→ Defender` (`key="qf_btn_load_def"`)
- On loading Attacker:
  - `st.session_state.qf_attacker = account_roster_to_fighter(loaded_r, curr, default_label="Attacker")`
  - Increment `qf_att_form_gen` counter.
  - Set `qf_att_input_mode = "Advanced"` and `qf_att_input_mode_radio = "Advanced (manual entry)"`.
  - Call `st.rerun()`.
- On loading Defender:
  - Same logic with `qf_defender` and `qf_def_form_gen`.
- Keep troop sliders interactive and preserved across profile loads.

### 3.2 Sensitivity Analysis (`kingshot_sim/webui/tabs/sensitivity.py`)
- Query `rosters = persistence.list_rosters()` and display Attacker and Defender Account Profile loaders.
- Maintain `sn_att_gen` and `sn_def_gen` counters in session state.
- Render fighter forms with generation-scoped key prefixes:
  - `fighter_form(st.session_state.sn_attacker, key_prefix=f"sn_att_g{att_gen}", side="attacker")`
  - `fighter_form(st.session_state.sn_defender, key_prefix=f"sn_def_g{def_gen}", side="defender")`
- On loading:
  - Call `account_roster_to_fighter(...)` preserving troops.
  - Increment `sn_att_gen` / `sn_def_gen`.
  - Call `st.rerun()`.

### 3.3 Attack & Defense Tab Deduplication (`kingshot_sim/webui/tabs/attack_defense.py`)
- Replace the local `_fighter_from_roster(...)` with the shared `account_roster_to_fighter(...)` from `kingshot_sim.io_pkg.roster_bridge`.

### 3.4 Settings Tab Cleanup (`kingshot_sim/webui/tabs/settings.py`)
- Tab structure streamlined from 5 tabs to 3 tabs:
  1. `Account & roster profiles ({len(rosters)})`
  2. `Advanced options`
  3. `Backup & restore`
- Remove the redundant `Saved rosters (SearchSpace)` tab.
- In `Advanced options`, add an expander:
  `Legacy Fighter Profiles ({len(profiles)}) — Deprecated`
  - Lists each legacy profile with:
    - Profile name
    - `Inspect` button (reveals composition details)
    - `Convert to Account Profile` button: converts via `fighter_to_roster(...)` and saves to `persistence.save_roster(...)`
    - `Delete` button: removes legacy profile via `persistence.delete_profile(...)`
- In `Backup & restore`, update metric cards to reflect `Account Rosters`, `Legacy Profiles`, `Op overrides`, and `Data overrides`.

---

## 4. Verification & Testing

1. **`tests/test_roster_bridge.py`**:
   - Verify `account_roster_to_fighter`: star levels, widget levels, skill levels, class gear, bonuses, buffs, joiners, and troop preservation.
   - Verify `fighter_to_roster`: roundtrip conversion of all fighter properties into an `AccountRoster`.
2. **`tests/test_quick_fight_tab.py`**:
   - `AppTest` verifying empty state.
   - `AppTest` verifying attacker and defender loading from saved `AccountRoster`.
   - `AppTest` verifying running a battle simulation with loaded fighters.
3. **`tests/test_sensitivity_tab.py`**:
   - `AppTest` verifying empty state.
   - `AppTest` verifying attacker and defender loading from saved `AccountRoster`.
4. **`tests/test_settings_tab.py`**:
   - `AppTest` verifying 3-tab layout.
   - `AppTest` verifying legacy fighter profile inspection, deletion, and conversion to `AccountRoster`.
5. **Full Suite**:
   - Execute `.venv/bin/pytest -q` to confirm all 1069+ tests pass.
