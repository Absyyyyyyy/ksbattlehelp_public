# Unified Roster Manager & Account Profile Design Spec

**Date:** 2026-09-29  
**Status:** Draft / Approved by User  
**Target Repository:** `Absyyyyyyy/ksbattlehelp_public`  
**Feature Branch:** `feature/unified-roster-manager` (branched off `main`)  

---

## 1. Problem Statement & Motivation

Currently in `ksbattlehelp_public`, roster and hero collection data are fractured across different tabs and representations:
1. **Benchmark Tab:** Uses `BenchmarkRoster` (`kingshot_sim/io_pkg/rosters.py`) to manage owned heroes, star tiers, ascensions, and widget levels.
2. **Attack & Defense Optimizer:** Uses `SearchSpace` (`kingshot_sim/optimizer/search_space.py`), which manages available hero pools, per-hero `leader_specs` (stars, widgets, skill levels), class gear (`class_gear` for Infantry, Cavalry, Archer), account stat bonuses (`BonusVector`), and buffs (`Buffs`).

Because these representations are decoupled, players must re-enter hero levels, widgets, and gear in multiple places. Changes made while experimenting in the Benchmark tab do not inform the Attack & Defense optimizer, and vice versa.

There is a need for a unified **"Roster Manager" / Account Profile** that acts as a single source of truth across the entire application while supporting local, non-destructive experimentation in individual solver tabs.

---

## 2. Goals & Non-Goals

### Goals
- **Unified Source of Truth (`AccountRoster`):** Establish a single canonical profile encompassing:
  1. Owned heroes (classes, star tiers, ascensions, skill levels).
  2. Hero widgets (levels 0–10).
  3. Class gear pieces (head, chest, gloves, boots, forge mastery, enhance for Inf, Cav, Arc).
  4. Account stat bonuses (`BonusVector`: squad and class ATK/DEF/LET/HP %).
  5. Account buffs (`Buffs`: city combat buffs, pet levels, title appointments).
- **Consolidated Profile Management in Settings:** Centralize profile creation, renaming, saving, deletion, JSON import/export, and OCR screenshot scanning inside an "Account & Roster Profile" section in the **Settings** tab.
- **Cross-Tab Synchronization with Local Overrides:** Provide a standard profile toolbar in **Benchmark** and **Attack & Defense** tabs:
  - Selecting an active profile pre-fills tab inputs.
  - Players can freely customize inputs for specific simulations.
  - An explicit **"Save changes back to Profile"** button writes overrides back to the active profile.
- **Bi-directional Bridge Layer (`roster_bridge.py`):** Clean domain adapters that convert between `AccountRoster` and `SearchSpace` or Benchmark state.
- **Full Backward Compatibility:** Evolve the existing `ksbattlehelper-roster` JSON schema from `version: 1` to `version: 2`. Loading legacy v1 files must succeed seamlessly with empty/zero defaults for new fields. Maintain `BenchmarkRoster = AccountRoster` as an alias.
- **Persistence & Cloud Parity:** Support file-based persistence (`~/.kingshot_sim/rosters/`) and session-storage parity (`_ss_rosters`), alongside full inclusion in application backups (`kingshot_sim/io_pkg/backup.py`) and browser localStorage sync (`kingshot_sim/webui/local_storage.py`).

### Non-Goals
- Altering core combat simulation mechanics, formulas, or tick loops in `kingshot_sim/engine/`.
- Changing benchmark scoring weights or evaluation scenarios.
- Forcing strict read-only lockouts on solver tabs (local experimentation remains frictionless).

---

## 3. Architecture & Data Model

### 3.1 Domain Schema: `AccountRoster`
Location: `kingshot_sim/io_pkg/rosters.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Final

from ..benchmark.runner import HeroBuild
from ..config.fighter import HeroGearPiece, BonusVector
from ..config.buffs import Buffs
from ..data.reference import MAX_GENERATION

@dataclass
class AccountRoster:
    name: str
    generation: int = 8
    # Class ("Inf", "Cav", "Arc") -> list of owned hero names
    owned_heroes: dict[str, list[str]] = field(default_factory=dict)
    # Hero name -> HeroBuild(level="MAX"|"star_sub", widget_level=0..10, skill_levels=(1..5, 1..5, 1..5))
    builds: dict[str, HeroBuild] = field(default_factory=dict)
    # Class ("Inf", "Cav", "Arc") -> Slot ("head", "chest", "gloves", "boots") -> HeroGearPiece
    class_gear: dict[str, dict[str, HeroGearPiece]] = field(default_factory=dict)
    # Account stat bonuses (squad and per-class atk/def/let/hp %)
    bonuses: BonusVector = field(default_factory=BonusVector)
    # Account buffs (city combat buffs, pet levels, appointments)
    buffs: Buffs = field(default_factory=Buffs)

# Backward-compatible alias for existing imports
BenchmarkRoster = AccountRoster
```

### 3.2 JSON Serialization (`ksbattlehelper-roster` v2)
```json
{
  "version": 2,
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
      "widget_level": 8,
      "skill_levels": [5, 5, 5]
    },
    "Margot": {
      "star": 4,
      "sub_tier": 2,
      "level": "4_2",
      "widget_level": 4,
      "skill_levels": [5, 4, 3]
    }
  },
  "class_gear": {
    "Inf": {
      "head": {
        "slot": "head",
        "quality": "red",
        "level": 100,
        "enhance": 5,
        "forge_mastery": 2
      }
    }
  },
  "bonuses": {
    "squad_atk_pct": 120.0,
    "squad_def_pct": 110.0,
    "inf_atk_pct": 80.0
  },
  "buffs": {
    "city_let": 10,
    "grizzly_level": 5,
    "appoint_marshal": true
  }
}
```

### 3.3 Backward Compatibility & Migration
- **v1 Ingestion:** When parsing JSON with `version: 1` (or missing fields), `roster_from_dict()` assigns default instances:
  - `class_gear` -> `{}`
  - `bonuses` -> `BonusVector()`
  - `buffs` -> `Buffs()`
- **v2 Emission:** All save and export operations write `version: 2`.
- **Validation:** Serialization delegates to `HeroGearPieceSchema`, `BonusVectorSchema`, and `BuffsSchema` in [`kingshot_sim/io_pkg/profiles.py`](file:///home/prmohan/projects/ksbattlehelp_public/kingshot_sim/io_pkg/profiles.py) for strict validation and consistent serialization structure.

---

## 4. Bridge & Adapter Layer (`roster_bridge.py`)

Location: `kingshot_sim/io_pkg/roster_bridge.py`

This module decouples the storage model (`AccountRoster`) from the optimizer (`SearchSpace`) and benchmark runner (`BenchmarkRunner`).

### 4.1 Interface Contract
```python
def roster_to_search_space(
    roster: AccountRoster,
    base: SearchSpace | None = None,
) -> SearchSpace:
    """Translate an AccountRoster into a SearchSpace.
    
    - Extracts owned mythic heroes into available_mythic_inf, cav, arc.
    - Extracts eligible combat heroes into available_joiners.
    - Translates builds into leader_specs.
    - Injects class_gear, bonuses, and buffs.
    - Preserves base optimizer settings (troop pool, ratio steps, march cap) if provided.
    """
    ...

def update_roster_from_search_space(
    roster: AccountRoster,
    space: SearchSpace,
) -> AccountRoster:
    """Update an existing AccountRoster with overrides present in SearchSpace."""
    ...

def roster_to_fighter(
    roster: AccountRoster,
    inf_hero: str,
    cav_hero: str,
    arc_hero: str,
    joiners: tuple[str, ...] = (),
    troops: TroopRoster | None = None,
    label: str = "Opponent",
) -> Fighter:
    """Assemble a Fighter from an AccountRoster by selecting specific leaders & troops.
    
    - Equips inf_hero, cav_hero, arc_hero with stars, widgets, and skills from roster.builds.
    - Equips class gear from roster.class_gear for each leader's class.
    - Populates joiners with their levels from roster.builds.
    - Injects roster.bonuses and roster.buffs.
    """
    ...

def apply_roster_to_benchmark(roster: AccountRoster) -> None:
    """Hydrate Benchmark tab session state from an AccountRoster."""
    ...

def extract_roster_from_benchmark(roster: AccountRoster) -> AccountRoster:
    """Extract modified hero builds and owned states from Benchmark session state."""
    ...
```

### 4.2 Benchmark Gear Integration
The Benchmark tab runner already supports class gear:
`BenchmarkRunner.run(..., class_gear=roster.class_gear)` passes gear directly into `build_trio()`, equipping each leader hero with their respective class gear pieces automatically.

---

## 5. UI Architecture & User Workflow

### 5.1 Settings Tab: "Account & Roster Profile" Section
Located in [`kingshot_sim/webui/tabs/settings.py`](file:///home/prmohan/projects/ksbattlehelp_public/kingshot_sim/webui/tabs/settings.py).

* **Management Toolbar:**
  * Active profile selector: dropdown populated via `persistence.list_rosters()`.
  * Actions: `[New Profile]`, `[Save]`, `[Save As]`, `[Delete]`.
  * Import/Export: `[Download JSON]`, `[Upload JSON]`.
  * OCR Hero Roster Scanner: upload screenshots of in-game hero screens to automatically identify owned heroes and star tiers.
* **Component Editors:**
  * **Generation Selector:** Slider (Gen 1–8).
  * **Owned Heroes & Widgets:** Class tabs (Infantry, Cavalry, Archer, Joiners) to toggle owned status, select star levels (`0_0`..`MAX`), widget levels (`0`–`10`), and skill levels.
  * **Class Gear:** Standard 4-piece grid per class using `class_gear_editor()`.
  * **Account Bonuses:** Squad and class stat multipliers using `bonuses_form()`.
  * **Account Buffs:** City combat buffs, pet levels, and title appointments using `buffs_form()`.

### 5.2 Cross-Tab Profile Toolbar & Local Testing Overrides
Placed at the top of [`kingshot_sim/webui/tabs/benchmark.py`](file:///home/prmohan/projects/ksbattlehelp_public/kingshot_sim/webui/tabs/benchmark.py) and [`kingshot_sim/webui/tabs/attack_defense.py`](file:///home/prmohan/projects/ksbattlehelp_public/kingshot_sim/webui/tabs/attack_defense.py):

```
Active Profile: [ Main Account ▼ ]   [ 🔄 Reload from Profile ]   [ 💾 Save Changes Back to Profile ]
```

* **Non-Destructive Local Overrides (What-If Experimentation):**
  1. **Pre-fill:** When a profile is loaded, it populates all local form inputs (owned heroes, star tiers, widget sliders, class gear levels, account stat bonuses, city/pet buffs).
  2. **Unconstrained In-Tab Overrides:** All widgets, sliders, number inputs, and selectors remain fully interactive. Players can freely modify values (e.g. bumping a hero from W4 to W10, testing an unowned hero, testing Red Gear +10, adjusting troop levels) to test "what-if" scenarios.
  3. **Immediate Simulation Effect:** These overrides take effect immediately in the solver run (ranking benchmark candidates or running Monte Carlo battle simulations).
  4. **Isolation:** Changes made inside the tab do **not** mutate the saved `AccountRoster` file or session store.
  5. **Persistence Options:**
     - To discard overrides and return to the baseline account profile, the user clicks **`[ 🔄 Reload from Profile ]`**.
     - To commit the modified configuration permanently back into the profile, the user clicks **`[ 💾 Save Changes Back to Profile ]`**.

### 5.3 Opponent Roster & Fighter Setup Workflow
In [`kingshot_sim/webui/tabs/attack_defense.py`](file:///home/prmohan/projects/ksbattlehelp_public/kingshot_sim/webui/tabs/attack_defense.py) (§1 Opponent Setup):

* **Populate Opponent from Profile:**
  - Adds an option to load an opponent directly from any saved `AccountRoster`:
    `Load Opponent from Account Profile: [ Enemy Whale (S120) ▼ ]  [ 🔄 Apply ]`
  - Populates opponent-side account stat bonuses (`BonusVector`), city/pet buffs (`Buffs`), and class gear pieces.
  - When picking the opponent's 3 leader heroes and joiners, their star tiers, ascensions, skill levels, and widget levels are automatically defaulted from the opponent's `builds`.
* **Opponent Local Overrides:**
  - Just like the player roster, opponent values remain fully adjustable in the tab (e.g. testing an opponent with higher buffs or alternative troops).
* **Cross-Tool Integration:**
  - Works seamlessly with Quick Fight and Sensitivity analysis via `roster_to_fighter()`.


---

## 6. Persistence, Backup & Local Storage Integration

1. **Persistence Layer (`kingshot_sim/webui/persistence.py`):**
   - Retains `~/.kingshot_sim/rosters/` (disk) and `_ss_rosters` (session).
   - Functions `list_rosters()`, `save_roster()`, `load_roster()`, and `delete_roster()` operate on `AccountRoster`.
2. **Application Backup System (`kingshot_sim/io_pkg/backup.py`):**
   - `build_backup_payload()` continues to include `rosters: ps.export_rosters_dict()`, capturing full v2 rosters.
   - `parse_backup_blob()` restores rosters using `roster_from_json()`, correctly importing both v1 and v2 rosters.
3. **Browser Local Storage (`kingshot_sim/webui/local_storage.py`):**
   - Tracks the active roster name (`_ks_active_roster`) in `LOCAL_STORAGE_KEYS` to restore the active profile across browser refreshes.

---

## 7. Testing & Verification Plan

### 7.1 Unit Tests
* **Data Model & Serialization (`tests/test_rosters.py`):**
  - Full roundtrip serialization of `AccountRoster` with gear, bonuses, and buffs.
  - Ingestion of legacy v1 JSON fixture, asserting graceful default fallbacks.
  - Bounds and type validation on widget levels, gear pieces, and skill levels.
  - Verifying `BenchmarkRoster = AccountRoster` backward-compatible alias.
* **Bridge Adapters (`tests/test_roster_bridge.py`):**
  - Verify `roster_to_search_space` maps mythic pools, joiners, leader specs, class gear, bonuses, and buffs accurately.
  - Verify `update_roster_from_search_space` correctly updates `AccountRoster`.
  - Verify `roster_to_fighter` constructs a full `Fighter` equipped with correct hero levels, widgets, skills, and class gear.
  - Verify benchmark runner equips class gear onto leaders in `build_trio`.
* **Persistence & Backup (`tests/test_persistence.py`, `tests/test_backup.py`):**
  - Save, list, load, and delete operations in both filesystem and session storage modes.
  - Application backup roundtrip with v2 roster payloads.

### 7.2 Integration & Regression Verification
* Execute the complete project test suite (`pytest`) to ensure zero regressions across combat formulas, optimizer runs, and UI forms.
* Syntax and import check across all modified Streamlit tabs.
