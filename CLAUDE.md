# CLAUDE.md — Operating guide for the KingShot Battle Helper

Read §1–§3 always. Skim §4–§6 once. Treat §7 (footguns) as a checklist before
any non-trivial change. 🔒 = invariant, ⚠️ = footgun.

The code has **no comments and no docstrings, by design**. The rationale for
every non-obvious rule lives in this file. Don't add comments or docstrings:
when a rule changes, update this file instead.

---

## 0. Tooling (graphify + plugins)

This project uses a graphify knowledge graph at `graphify-out/` (git-ignored;
the SessionStart hook installs graphify and rebuilds it).

- For codebase questions, first run `graphify query "<question>"` when
  `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for
  relationships and `graphify explain "<concept>"` for focused concepts. They
  return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw
  grep output.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of
  raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when
  query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current
  (AST-only, no API cost).

**Plugin priority:** if Ponytail conflicts with agent-skills (or any other
skill), Ponytail wins: simplest solution, YAGNI, stdlib and native first.

---

## 1. What this project is

**KingShot Battle Helper**: a Python + Streamlit PvP combat simulator for the
mobile game **KingShot** (KingsGroup, same engine lineage as State of Survival).

| Tab | File | What it does |
|---|---|---|
| Attack & Defense | `tabs/attack_defense.py` | Marquee feature. **Best Counter** ranks top-K attacker comps against a defender garrison; **Best Defense** is the mirror. One body parametrized by `_ModeCfg` (`_ATTACK`/`_DEFENSE`); session prefixes `bc_*`/`bd_*`. |
| Quick Fight | `tabs/quick_fight.py` | One matchup, round by round, deterministic or Monte Carlo. |
| Sensitivity | `tabs/sensitivity.py` | Sweep one parameter and chart the outcome. |
| Benchmark | `tabs/benchmark.py` | Training-dummy benchmark + roadmap advisor over 4 scenarios (solo atk / rally / defense / garrison) with a shard-budget develop/hold/set plan. Rule of thumb, not a matchup oracle. Backed by `benchmark/`. |
| SkillMod | `tabs/skillmod.py` | Two-sided SkillMod calculator (expected mode only) + greedy best-counter. |

Plus **Settings** (profiles, overrides, backup). Navigation lives in the
**sidebar**, grouped by area; `app._NAV_GROUPS` is `(slug, label, fn)` and the
slug is the `_ks_active_tab` routing key (labels are display-only).

EXPECTED mode is deterministic; STOCHASTIC mode is Monte Carlo (default 200
trials, 95% CI). Public deploy: https://absy-simulator.streamlit.app/.

---

## 2. Integrity contracts

### 2.1 🔒 The SoS Round-0 anchor

`tests/test_damage_formula.py::test_sos_round_zero_example` reproduces the
canonical State of Survival round-0 example (188.7 → 189 deaths). It is the
load-bearing validation of the whole engine. Any refactor of the damage
formula, per-troop atk/def, the SkillMod resolver, family aggregation or
stat-bonus aggregation **must keep it green**.

### 2.2 🔒 The damage formula (`engine/round.py::compute_damage`)

```
damage = army_factor × att_per_troop / def_per_troop × type_bonus
       × SkillMod × fatigue_factor / DAMAGE_DIVISOR (=100)
deaths = ceil(damage)
```

- `army_factor = sqrt(N_squad_attacker × armyMin)`, `armyMin = min(N_total_att, N_total_def)` fixed at fight start
- `att_per_troop = base_atk × eff_atk × base_let × eff_let / 100`
- `def_per_troop = base_def × eff_def × base_hp × eff_hp / 100`
- `eff_*` = squad factor × the Section D factor (§2.5)
- `type_bonus = 1 + type_bonus_pct/100` (default 10%) when attacker counters target (Inf > Cav > Arc > Inf)
- `fatigue_factor = max(0, 1 − round_idx × fatigue_per_round)` (default 0.0001)

`type_bonus_pct`, `fatigue_per_round`, `cavalry_bypass_rate`,
`archer_volley_rate` are read via accessors that honor user overrides; never
inline the raw constants. `BASE_LETHALITY = BASE_DEFENSE = 10` and
`DAMAGE_DIVISOR = 100` are part of the math identity and are **not**
overridable.

### 2.3 🔒 SkillMod and op codes

`SkillMod = (DamageUp × OppDefenseDown) / (OppDamageDown × DefenseUp)`.
Single source of truth: `domain/enums.py::OP_TO_FAMILY`.

| Family | Ops |
|---|---|
| DamageUp (num.) | 101 Let%, 102 Atk% / generic damage up, 103 Skill damage % |
| DefenseUp (den.) | 111 Dmg taken down, 112 Def%, 113 HP% |
| OppDamageDown (den.) | 201 Dmg dealt down, 202 Atk% down, 203 Dmg down |
| OppDefenseDown (num.) | 211 Dmg taken up on enemy, 212 Def% down on enemy |

Stacking: same op → additive sum then `(1 + sum/100)`; distinct ops in a family
→ multiplicative. `engine/resolver.py::aggregate_family` is the only
implementation. `Effect.target_enemy_squads` (default empty = no filter) gates
an effect on the enemy squad class; honored in both `aggregate_family` and the
2D matrices of `engine/batched.py`.

### 2.4 🔒 BonusVector vs hidden layers

`BonusVector` (`config/fighter.py`) = 16 fields (4 stats × Squad/Inf/Cav/Arc).
It contains tech, governor gear, charm, pets' stat bonuses, masters, alliance
tech, outposts, skin, VIP, island, hero gear + widget stat bonuses, minister
appointments (additive, via `Buffs.appoint_additive_pct`), and the Helga /
Amadeus unique passives (additive, account-wide).

It does **not** contain: leader Atk/Def% (added per leader at compile time),
hero/joiner skill effects (SkillMod), Section D buffs (§2.5).

The in-game "Stat Bonuses" panel shows the total after all of those.
`easy_mode/peeling.py` reverses each layer to recover the BonusVector.

### 2.5 🔒 Section D buffs (city, pet, turret, ocr)

Not in the BonusVector, not in SkillMod: a separate layer applied
multiplicatively at the per-troop factor stage via
`engine/section_d.py::section_d_factor`:

```
∏ over LAYERS (city, pet, turret, ocr):
    1 + (own_pct_attacker_in_layer − enemy_down_pct_defender_in_layer) / 100
```

Own buff and enemy debuff net additively within a layer, compose
multiplicatively across layers (+20% city atk vs −20% city enemy-atk-down →
1.00, not 0.96). This within-layer additive netting is unverified in-game and
flagged in `section_d.py`. The `ocr` layer carries the net aggregate from the
"Special Bonuses" popup; it is all-zero for manually built fighters.

Keep the raw `Buffs` on `FighterState.buffs`: `compute_damage` needs both sides'
Buffs. Don't bake Section D into squad factors at compile time.

### 2.6 🔒 Rally / garrison / solo

- Leaders: 3 heroes, one per class, no duplicates. Epics can lead.
- Joiners: up to 4 contribute their **first skill only**, at MAX (⭐5); Diana is
  excluded (non-combat sk1). The real game uses the 4 highest-level joiner
  skills; the ⭐5-only model is a deliberate simplification
  (`JoinerHero.contributes_skill`).
- Joiners bring only sk1 + troops: no gear, stats or widget.
- Chance-based joiner skills don't stack across joiners (first roll counts);
  non-RNG joiner skills stack additively.
- Solo march (`BattleConfig.is_solo_attack=True`, default False): no joiners,
  no own rally-scoped widget skills. Defender unaffected.

### 2.7 🔒 RNG skills scale chance OR value, never both

`data/catalog.py`: `_scale(value, lvl)` (value scales, chance fixed) vs
`_scale_chance(p_max, lvl)` (chance scales, value fixed). A `10/20/30/40/50%`
progression in the in-game upgrade preview tells you which one scales; read the
skill text, not just the trigger column. Pinned by `tests/test_rng_scaling.py`.

### 2.8 🔒 Gear mastery → Let/HP only, multiplicative on the base

`contribution = base × (1 + 0.10 × mastery)`, routed to the base channel
(Head + Boots → Lethality, Chest + Gloves → Health). Never `base + 10 × mastery`
(agrees only at base 100%, so full red L200 sets can't catch the bug). Mastery
never adds Atk/Def; those come from red-gear imbuement milestones
(120/160/200). See `data/gear.py::piece_contribution`.

---

## 3. Repo map

```
repo root (importable package: kingshot_sim)
├── run_app.py            Streamlit entry. Always `streamlit run run_app.py`.
├── conftest.py           pytest sys.path setup
├── kingshot_sim/
│   ├── data/             reference.py (tier stats, leader max, accessors), catalog.py (every hero skill),
│   │                     gear.py (per-piece math), op_overrides.py, user_data.py (numeric overrides)
│   ├── domain/           enums.py (OP_TO_FAMILY…), skills.py, heroes.py — immutable types
│   ├── config/           fighter.py (Fighter, BonusVector, rosters, gear), buffs.py (Buffs + tables)
│   ├── engine/           state.py, compile.py, resolver.py, section_d.py, round.py, battle.py,
│   │                     stochastic.py, montecarlo.py, batched.py (NumPy, optimizer screening)
│   ├── optimizer/        search_space.py, enumerate.py, best_counter.py (vectorized screen + MC refine)
│   ├── benchmark/        reference.py (per-gen data, scenarios), runner.py, economy.py, advisor.py
│   ├── easy_mode/        peeling.py + OCR: ocr.py (stat panel), ocr_troops.py, ocr_heroes.py,
│   │                     ocr_hero_roster.py, ocr_gear.py, ocr_gear_roster.py, ocr_buffs.py
│   ├── io_pkg/           profiles.py (Pydantic I/O), scope.py (session vs disk), backup.py
│   ├── webui/            app.py, theme.py, components.py, forms.py, easy_mode_form.py,
│   │                     local_storage.py, search_runner.py, tabs/ (one file per tab)
│   └── sensitivity.py    1-D sweep harness
└── tests/                pytest suite: engine, optimizer, benchmark, peeling
```

Where to start: math → `engine/round.py::compute_damage`; skills →
`data/catalog.py`, `engine/resolver.py`, `engine/compile.py::_gather_skills`;
wrong result → the SoS R0 test then `test_v8_buffs.py` / `test_v8_gear.py`;
UI → `webui/app.py`, each tab's `render()` is self-contained.

---

## 4. Override layers

- **Op-code overrides** (`data/op_overrides.py`): re-route a skill effect to
  another op. API: `set_op_override`, `clear_op_override`,
  `clear_all_overrides`, `list_op_overrides`, `apply_overrides_to_skill`.
- **Numeric overrides** (`data/user_data.py`): flat key→value registry
  (`tier_stat.<tier>.<stat>`, `hero_max.<hero>`, `widget_max.<widget>`,
  `helga_passive.<star>`, `amadeus_passive.<star>`, `engine.*`). Not
  overridable: `BASE_LETHALITY`, `BASE_DEFENSE`, `DAMAGE_DIVISOR`,
  `LEVEL_FRACTION`, `HERO_GENERATION`.
- **Scoping**: both stores use `io_pkg.scope.use_session_storage()` →
  `st.session_state` inside Streamlit (no cross-user leak on the public host),
  `~/.kingshot_sim/*.json` otherwise. `KS_PERSIST_TO_DISK=1` forces disk.

---

## 5. Special mechanics outside op codes

| Mechanic | Hero | Rule |
|---|---|---|
| Per-attack target debuff | Petra sk1 | EXPECTED: union over troop types `1−(1−p)^3` (+43.75% at ⭐5). STOCHASTIC: Bernoulli per attacking squad, accumulates for the round. The two modes intentionally diverge here. Roll once per attack, never mid-round. |
| Pity proc | Yang sk3 | `effective = base × (1 + n_failed)`; EXPECTED uses the steady-state rate (~0.581 for base 0.40). |
| Dodge | Margot sk2 | `FighterState.dodge_chance`; EXPECTED damage × (1 − dodge), STOCHASTIC Bernoulli. Not folded into op 111. |
| Conditional Terror | Sophia sk2 + sk3 | sk2 applies its bonus and marks Terror; sk3 counts only on Terror'd targets (EXPECTED scales by `target_terror_prob`). |
| Periodic buffs | Yang sk1, Alcar sk1, Thrud sk3, Vivian sk2/sk3… | `round_idx % period == period_offset`. Vivian's "every 4 attacks" ≈ every 4 rounds. |
| Timed RNG buffs | Jaeger, Zoe, Marlin… | EXPECTED: Markov occupancy `1 − (1 − p)^duration`; STOCHASTIC: per-round Bernoulli with duration. |

---

## 6. Tests

`pytest tests/ -q` (~10 min, CPU-bound benchmark sims). The public suite
covers engine, optimizer, benchmark and peeling only: no OCR image tests, no UI
tests, no Tesseract needed. Everything must pass.

Key files: `test_damage_formula.py` (SoS anchor, never skip), `test_v8_buffs.py`
(Section D), `test_v8_gear.py` / `test_v8_class_gear.py` (gear math, no class
leak), `test_v8_hero_skill_battery.py` (every hero's compiled skills),
`test_v8_sign_convention.py` (defensive skills reduce enemy damage),
`test_rng_scaling.py`, `test_solo_vs_rally.py`, `test_batched.py`
(vectorized ≡ sequential), `test_optimizer.py`, `test_easy_mode_peeling.py` /
`test_easy_mode_roundtrip.py` (Advanced → peel → Easy is bit-identical),
`test_v8_9_session_scoping.py` (no cross-user leak on the shared host).

Adding behavior → test first. Never delete or skip a test to get green; if a
test encodes an outdated rule, update it with a docstring explaining why.

---

## 7. Footguns

1. **Mastery** routes to Let/HP and is multiplicative on the base (§2.8).
2. **Helga/Amadeus passives** are additive and account-wide, in the
   BonusVector. Don't add a per-troop multiplier: peeling never removes them,
   so re-applying double-counts every Easy import. The benchmark re-credits
   them in `runner._unique_passive_pool`.
3. **Sidebar HTML cards** (Ko-fi, Discord) use `st.html`, never `st.markdown`
   (markdown breaks `<a>` wrapping block elements).
4. **`streamlit run run_app.py`**, never a file inside the package (relative
   imports break).
5. **`conftest.py`** exists because the repo dir name differs from the package
   name. Never name the repo dir `kingshot_sim`.
6. **No damage redirection** when a target line dies mid-round: targeting is
   resolved at round start; surplus damage misses (SoS parity).
7. **Diana** is never a skill-contributing joiner.
8. **EXPECTED vs STOCHASTIC** agree in expectation but not in variance; the
   optimizer's MC refinement exists to surface it. Petra sk1 is the known
   intentional divergence (§5).
9. **New Section D buff source** touches: `config/buffs.py`,
   `engine/section_d.py`, `engine/round.py`, `engine/batched.py` (4 sites:
   `_SideArrays`, `_compile_side_arrays_cached`, `_stack_sides`, `_tile_to_n` +
   per-round compute), `easy_mode/peeling.py::_section_d_multiplier`, the UI
   form, and tests in `test_v8_buffs.py` + `test_easy_mode_peeling.py`. A new
   **layer** is cheaper: append it LAST to `section_d.LAYERS` (everything
   iterates it; don't hardcode the layer count).
10. **No module-level mutable globals** on any Streamlit-importable path; go
    through `io_pkg.scope`.
11. **Backward-compat defaults**: `is_solo_attack=False`,
    `fatigue_enabled=True`, new `Buffs` fields 0/False/empty,
    `forge_mastery=0`. Saved profiles must round-trip across schema bumps.
12. **OCR**: Tesseract's full-page scan doesn't read text over busy art; keep
    the targeted crops (`ocr_troops._recover_level_for_count`,
    `ocr_heroes.extract_level`). Upscaling can't recover sub-800px shares; show
    a resolution error instead. Never set `pytesseract.tesseract_cmd` at
    import time (process-wide). `face_score=-2.0` is the no-detection sentinel.
13. **Widget GC during async search**: forms not rendered while a search runs
    lose their widget keys. Re-hydrate multi-row forms from the source-of-truth
    Fighter on every render (see `troops_form`).
14. **`BattleResult.score`** = `def_lost/def_total − att_lost/att_total`
    ∈ [−1, 1]. Don't normalize by `max(att, def)`. The benchmark uses its own
    metric.
15. **Persisted UI values** (`_UI_PREF_KEYS` in localStorage) must be remapped
    when a radio/select option is renamed, or returning browsers crash.

---

## 8. Playbook

Before: capture the test baseline; find the test that pins the behavior; list
the surfaces (§7.9 for buffs).

While:
- No `streamlit` imports in `engine/`, `domain/`, `config/`, `data/`. The
  engine is pure Python + numpy (`engine/batched.py`).
- Canonical reference data lives in `data/reference.py` and `data/catalog.py`,
  never JSON-only. Overrides sit on top.
- Never invent skill mechanics. If a description is ambiguous, flag it and
  take the conservative reading.
- Vectorize only in `engine/batched.py`, with `test_batched.py` green.

After: `pytest tests/ -q` (no new failures), smoke-test every tab with
`streamlit run run_app.py`.

| Ask | Start in |
|---|---|
| New hero | `data/catalog.py` + `data/reference.py` (`HERO_LEADER_MAX`, `HERO_CLASS`, `HERO_WIDGET`, `HERO_GENERATION`) + `test_v8_hero_skill_battery.py` |
| New troop tier | `data/reference.py::TIER_BASE_STATS` |
| Peeling drift | `easy_mode/peeling.py` + `test_easy_mode_roundtrip.py` |
| Faster Best Counter | `engine/batched.py` + `optimizer/best_counter.py` |
| Skill value looks wrong | `data/catalog.py`, active op overrides, `test_rng_scaling.py` |

---

## 9. Commands

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -q
streamlit run run_app.py      # http://localhost:8501; screenshot import needs tesseract-ocr
```

---

## 10. Communication style

Direct, terse, technically dense. French is fine in chat when the user writes
French; code comments, docstrings and repo docs stay in English. Show your work
for math changes (worked example, before/after) and list affected surfaces for
cross-cutting changes. No comments, docstrings or emojis in code.
