from __future__ import annotations

import json
import streamlit as st

from kingshot_sim.data import user_data as ud
from kingshot_sim.data import reference as ref


def render() -> None:
    st.subheader("Data overrides")
    st.caption(
        "Patch the simulator's reference data. Tier base stats, hero/widget "
        "max %, Helga/Amadeus passives, and engine constants. Without "
        "modifying the catalog source. Useful for: introducing new tiers "
        "before they ship in code (T11, T12), incorporating community-tested "
        "refinements (e.g. corrected cavalry bypass rate), or running "
        "what-if analyses. "
        "All changes persist to `~/.kingshot_sim/data_overrides.json` and "
        "take effect on the next battle / search."
    )

    _render_active_summary()
    st.markdown("---")
    _render_engine_constants()
    st.markdown("---")
    _render_tier_stats()
    st.markdown("---")
    _render_hero_max()
    st.markdown("---")
    _render_widget_max()
    st.markdown("---")
    _render_passives()
    st.markdown("---")
    _render_import_export()


def _render_active_summary() -> None:
    overrides = ud.list_data_overrides()
    if not overrides:
        st.info(
            "No data overrides set. The simulator is running with the "
            "embedded reference data (see *About* for sources)."
        )
        return

    st.markdown(f"**Active overrides ({len(overrides)}):**")
    for key, value in sorted(overrides.items()):
        cols = st.columns([4, 1])
        cols[0].markdown(f"- `{key}` = `{value}`")
        if cols[1].button("Remove", key=f"data_rm_{key}"):
            ud.clear_data_override(key)
            st.rerun()

    if st.button("Clear ALL data overrides", type="secondary",
                  key="data_clear_all"):
        ud.clear_all_data_overrides()
        st.rerun()


_ENGINE_CONST_SPECS: list[tuple] = [
    ("engine.cavalry_bypass_rate",  "Cavalry bypass rate",  ref.cavalry_bypass_rate, ref.CAVALRY_BYPASS_RATE,
     "%.3f", 0.01, "Per-round chance for Cav to skip frontline and strike Arc. Default: 0.20 (20%)."),
    ("engine.archer_volley_rate",   "Archer volley rate",   ref.archer_volley_rate,  ref.ARCHER_VOLLEY_RATE,
     "%.3f", 0.01, "Arc double-attack chance per round. Default: 0.10 (10%)."),
    ("engine.type_bonus_pct",       "Type bonus %",         ref.type_bonus_pct,      ref.TYPE_BONUS_PCT,
     "%.2f", 0.5,  "Extra damage % when attacker counters defender's class. Default: 10.0."),
    ("engine.fatigue_per_round",    "Fatigue per round",    ref.fatigue_per_round,   ref.FATIGUE_PER_ROUND,
     "%.5f", 0.00005, "Multiplicative damage decay per round. Default: 0.0001 (-0.01% / round)."),
]


def _render_engine_constants() -> None:
    with st.expander("Engine constants", expanded=False):
        st.caption(
            "Override the core engine RNG / damage modifier constants. "
            "Note: `engine.damage_divisor`, `base_lethality`, and "
            "`base_defense` are intentionally **non-adjustable**. They "
            "would break the engine math or the SoS R0 validation anchor."
        )

        col_a, col_b = st.columns(2)
        for i, (key, label, accessor, raw_default, fmt, step, help_text) in enumerate(_ENGINE_CONST_SPECS):
            col = col_a if i % 2 == 0 else col_b
            with col:
                current = accessor()
                overridden = ud.has_data_override(key)
                badge = " " if overridden else ""
                new_val = st.number_input(
                    f"{label}{badge}",
                    value=float(current),
                    step=float(step),
                    format=fmt,
                    help=f"{help_text}  •  Default: {raw_default}",
                    key=f"data_eng_{key}",
                )
                btn_cols = st.columns(2)
                if btn_cols[0].button("Apply", key=f"data_eng_apply_{key}"):
                    _apply_engine_const(key, new_val, raw_default)
                if overridden and btn_cols[1].button("Reset", key=f"data_eng_reset_{key}"):
                    ud.clear_data_override(key)
                    st.rerun()

        st.markdown("##### Integer engine constants")
        col_c, col_d = st.columns(2)
        with col_c:
            key = "engine.max_joiners_with_skill"
            current = ref.max_joiners_with_skill()
            overridden = ud.has_data_override(key)
            badge = " " if overridden else ""
            new_val = st.number_input(
                f"Max joiners with skill{badge}",
                min_value=0, max_value=15,
                value=int(current), step=1,
                help=f"Number of joiner first-skills that contribute to the SkillMod. Default: {ref.MAX_JOINERS_WITH_SKILL}.",
                key="data_eng_mjs",
            )
            btn_cols = st.columns(2)
            if btn_cols[0].button("Apply", key="data_eng_mjs_apply"):
                _apply_engine_const(key, int(new_val), ref.MAX_JOINERS_WITH_SKILL)
            if overridden and btn_cols[1].button("Reset", key="data_eng_mjs_reset"):
                ud.clear_data_override(key)
                st.rerun()
        with col_d:
            key = "engine.max_rally_members"
            current = ref.max_rally_members()
            overridden = ud.has_data_override(key)
            badge = " " if overridden else ""
            new_val = st.number_input(
                f"Max rally members{badge}",
                min_value=1, max_value=50,
                value=int(current), step=1,
                help=f"Total rally roster size (only first N contribute skills). Default: {ref.MAX_RALLY_MEMBERS}.",
                key="data_eng_mrm",
            )
            btn_cols = st.columns(2)
            if btn_cols[0].button("Apply", key="data_eng_mrm_apply"):
                _apply_engine_const(key, int(new_val), ref.MAX_RALLY_MEMBERS)
            if overridden and btn_cols[1].button("Reset", key="data_eng_mrm_reset"):
                ud.clear_data_override(key)
                st.rerun()

        st.markdown("##### TG8 INF/ARC interpretation (advanced)")
        from ..data.troop_skills import tg8_always_on as _tg8_always_on
        current_always_on = _tg8_always_on()
        new_always_on = st.toggle(
            "TG8 INF / ARC skills behave as **always-on**",
            value=current_always_on,
            key="data_eng_tg8_always_on",
            help=(
                "Default (off): TG8 INF '+10% reduction' and TG8 ARC '+25% damage' "
                "fire only in rounds when the TG5+ skill procs (matches in-game "
                "wording). When ON, they apply passively every round. Higher "
                "expected damage. Matches a third-party reverse-engineered sim "
                "but contradicts the in-game tooltip. Flip if your own in-game "
                "testing confirms the always-on interpretation."
            ),
        )
        if new_always_on != current_always_on:
            if new_always_on:
                ud.set_data_override("engine.tg8_always_on", 1)
            else:
                ud.clear_data_override("engine.tg8_always_on")
            st.rerun()


def _apply_engine_const(key: str, value, raw_default) -> None:
    if value == raw_default:
        ud.clear_data_override(key)
        st.info(f"{key}: value equals default → override cleared.")
    else:
        try:
            ud.set_data_override(key, value)
            st.success(f"{key} = {value}")
        except ValueError as e:
            st.error(str(e))
    st.rerun()


_TIER_STAT_KEYS = ("inf_atk", "inf_hp", "cav_atk", "cav_hp", "arc_atk", "arc_hp")


def _render_tier_stats() -> None:
    with st.expander("Tier base stats", expanded=False):
        st.caption(
            "Per-tier per-stat base values. To **introduce a new tier** "
            "(e.g. T11 Truegold), use the *Add new tier* form at the "
            "bottom. You need to provide all 6 stats; partial entries "
            "are ignored until complete."
        )

        for tier in ref.valid_tiers():
            _render_one_tier(tier)

        st.markdown("##### Add a new tier")
        new_tier_name = st.text_input(
            "Tier name (e.g. T11, T11.1, T12)",
            value="",
            key="data_new_tier_name",
            help="Pick a name not already in use. T1..T10.5 are pre-defined.",
        )
        if new_tier_name and new_tier_name not in ref.valid_tiers():
            st.markdown(f"**Stats for {new_tier_name}** (all 6 required):")
            cols = st.columns(6)
            new_vals: dict[str, int] = {}
            for i, stat in enumerate(_TIER_STAT_KEYS):
                suggested = ref.TIER_BASE_STATS["T10.5"][stat]
                new_vals[stat] = cols[i].number_input(
                    stat,
                    min_value=0, value=int(suggested), step=1,
                    key=f"data_new_tier_{new_tier_name}_{stat}",
                )
            if st.button("Create tier", type="primary",
                          key=f"data_new_tier_create_{new_tier_name}"):
                for stat, val in new_vals.items():
                    ud.set_data_override(f"tier_stat.{new_tier_name}.{stat}", int(val))
                st.success(f"Tier {new_tier_name} created. Now available in "
                            f"all tier dropdowns and the engine.")
                st.rerun()
        elif new_tier_name in ref.valid_tiers():
            st.warning(f"{new_tier_name!r} already exists.")


def _render_one_tier(tier: str) -> None:
    is_overridden_any = any(
        ud.has_data_override(f"tier_stat.{tier}.{stat}") for stat in _TIER_STAT_KEYS
    )
    is_new_tier = tier not in ref.TIER_BASE_STATS
    badge = ""
    if is_new_tier:
        badge = " "
    elif is_overridden_any:
        badge = " "

    with st.container():
        st.markdown(f"##### {tier}{badge}")
        cols = st.columns(6)
        for i, stat in enumerate(_TIER_STAT_KEYS):
            key = f"tier_stat.{tier}.{stat}"
            current = int(ref.tier_stat(tier, stat))
            if tier in ref.TIER_BASE_STATS:
                raw_default = ref.TIER_BASE_STATS[tier][stat]
                placeholder_help = f"Default: {raw_default}"
            else:
                placeholder_help = "User-introduced tier (no embedded default)."
            new_val = cols[i].number_input(
                stat,
                min_value=0, value=current, step=1,
                key=f"data_tier_{tier}_{stat}",
                help=placeholder_help,
            )
            if new_val != current:
                if tier in ref.TIER_BASE_STATS and new_val == ref.TIER_BASE_STATS[tier][stat]:
                    ud.clear_data_override(key)
                else:
                    ud.set_data_override(key, int(new_val))
                st.rerun()

        if is_overridden_any:
            if st.button(f"Reset {tier} to defaults", key=f"data_tier_reset_{tier}"):
                for stat in _TIER_STAT_KEYS:
                    ud.clear_data_override(f"tier_stat.{tier}.{stat}")
                st.rerun()
        if is_new_tier:
            if st.button(f"Delete {tier}", key=f"data_tier_delete_{tier}"):
                for stat in _TIER_STAT_KEYS:
                    ud.clear_data_override(f"tier_stat.{tier}.{stat}")
                st.rerun()


def _render_hero_max() -> None:
    with st.expander("Hero leader max %", expanded=False):
        st.caption(
            "Per-hero Atk%/Def% at ★5 (Max). All other levels scale "
            "automatically via the universal LEVEL_FRACTION curve."
        )
        from kingshot_sim.data.reference import HERO_GENERATION, MAX_GENERATION

        for gen in range(1, MAX_GENERATION + 1):
            heroes_in_gen = sorted(
                h for h, g in HERO_GENERATION.items() if g == gen
            )
            if not heroes_in_gen:
                continue
            st.markdown(f"**Gen {gen}**")
            _render_hero_max_row(heroes_in_gen)

        st.markdown("**Epics**")
        epics = sorted(h for h in ref.HERO_LEADER_MAX if h in ref.EPIC_HEROES)
        _render_hero_max_row(epics)


def _render_hero_max_row(heroes: list[str]) -> None:
    cols = st.columns(min(len(heroes), 4))
    for i, hero in enumerate(heroes):
        col = cols[i % len(cols)]
        with col:
            key = f"hero_max.{hero}"
            current = ref.hero_leader_max(hero)
            raw_default = ref.HERO_LEADER_MAX[hero]
            overridden = ud.has_data_override(key)
            badge = " " if overridden else ""
            new_val = st.number_input(
                f"{hero}{badge}",
                min_value=0.0, value=float(current), step=1.0,
                format="%.2f",
                help=f"Default: {raw_default:.2f}",
                key=f"data_heromax_{hero}",
            )
            if abs(new_val - current) > 1e-9:
                if abs(new_val - raw_default) < 1e-9:
                    ud.clear_data_override(key)
                else:
                    ud.set_data_override(key, float(new_val))
                st.rerun()


def _render_widget_max() -> None:
    with st.expander("Widget max %", expanded=False):
        st.caption(
            "Per-widget Lethality%/Health% bonus at level 10 (Max). Lower "
            "widget levels scale linearly."
        )
        from kingshot_sim.data.reference import HERO_WIDGET, HERO_GENERATION, MAX_GENERATION

        widget_to_hero = {w: h for h, w in HERO_WIDGET.items()}

        for gen in range(1, MAX_GENERATION + 1):
            widgets_in_gen = sorted(
                w for w in ref.WIDGET_MAX
                if widget_to_hero.get(w) in HERO_GENERATION
                and HERO_GENERATION[widget_to_hero[w]] == gen
            )
            if not widgets_in_gen:
                continue
            st.markdown(f"**Gen {gen}**")
            cols = st.columns(min(len(widgets_in_gen), 3))
            for i, widget in enumerate(widgets_in_gen):
                col = cols[i % len(cols)]
                with col:
                    key = f"widget_max.{widget}"
                    current = ref.widget_max(widget)
                    raw_default = ref.WIDGET_MAX[widget]
                    overridden = ud.has_data_override(key)
                    badge = " " if overridden else ""
                    owner = widget_to_hero.get(widget, "?")
                    new_val = st.number_input(
                        f"{widget} ({owner}){badge}",
                        min_value=0.0, value=float(current), step=1.0,
                        format="%.2f",
                        help=f"Default: {raw_default:.2f}",
                        key=f"data_widmax_{widget}",
                    )
                    if abs(new_val - current) > 1e-9:
                        if abs(new_val - raw_default) < 1e-9:
                            ud.clear_data_override(key)
                        else:
                            ud.set_data_override(key, float(new_val))
                        st.rerun()


def _render_passives() -> None:
    with st.expander("Helga / Amadeus unique passives", expanded=False):
        st.caption(
            "Multiplicative bonuses applied **only when the hero is in the "
            "leader trio**. Helga's passive boosts Atk/Def factors; "
            "Amadeus's boosts Let/HP factors. Values are fractions (e.g. "
            "0.10 = +10%)."
        )

        st.markdown("**Helga. Power of the Deer** (Atk + Def)")
        _render_passive_row(
            namespace="helga_passive",
            table=ref.HELGA_PASSIVE,
            accessor_by_star=lambda s: ref.HELGA_PASSIVE[s] if not ud.has_data_override(
                f"helga_passive.{s}"
            ) else ud.get_data_override(f"helga_passive.{s}", ref.HELGA_PASSIVE[s]),
        )

        st.markdown("**Amadeus. Born Leader** (Let + HP)")
        _render_passive_row(
            namespace="amadeus_passive",
            table=ref.AMADEUS_PASSIVE,
            accessor_by_star=lambda s: ref.AMADEUS_PASSIVE[s] if not ud.has_data_override(
                f"amadeus_passive.{s}"
            ) else ud.get_data_override(f"amadeus_passive.{s}", ref.AMADEUS_PASSIVE[s]),
        )


def _render_passive_row(namespace: str, table: dict, accessor_by_star) -> None:
    cols = st.columns(6)
    for star in range(6):
        with cols[star]:
            key = f"{namespace}.{star}"
            raw_default = float(table[star])
            current = float(accessor_by_star(star))
            overridden = ud.has_data_override(key)
            badge = " " if overridden else ""
            new_val = st.number_input(
                f"★{star}{badge}",
                min_value=0.0, max_value=1.0,
                value=current, step=0.01,
                format="%.3f",
                help=f"Default: {raw_default:.3f}",
                key=f"data_passive_{namespace}_{star}",
            )
            if abs(new_val - current) > 1e-9:
                if abs(new_val - raw_default) < 1e-9:
                    ud.clear_data_override(key)
                else:
                    ud.set_data_override(key, float(new_val))
                st.rerun()


def _parse_import_payload(raw_text: str) -> tuple[dict, str | None]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return {}, f"Malformed JSON: {e}"

    if not isinstance(parsed, dict):
        return {}, "Top-level JSON must be an object."
    if "overrides" not in parsed:
        return {}, "Missing 'overrides' top-level key."

    imported = parsed["overrides"]
    if not isinstance(imported, dict):
        return {}, "'overrides' must be an object mapping key to value."

    return imported, None


def _apply_imported_overrides(
    imported: dict,
    *,
    replace_existing: bool,
) -> tuple[int, list[str]]:
    if replace_existing:
        ud.clear_all_data_overrides()
    applied = 0
    skipped: list[str] = []
    for key, value in imported.items():
        try:
            ud.set_data_override(key, value)
            applied += 1
        except ValueError as e:
            skipped.append(f"{key}: {e}")
    return applied, skipped


def _render_import_export() -> None:
    with st.expander("Import / export overrides as JSON", expanded=False):
        st.caption(
            "Share a configured override set across machines, or back up "
            "your customizations. Same file format as "
            "`~/.kingshot_sim/data_overrides.json`."
        )

        overrides = ud.list_data_overrides()
        if overrides:
            payload = {
                "version": ud.PERSIST_VERSION,
                "overrides": dict(sorted(overrides.items())),
            }
            blob = json.dumps(payload, indent=2)
            st.download_button(
                "Download current overrides",
                data=blob,
                file_name="data_overrides.json",
                mime="application/json",
                key="data_export_btn",
            )
        else:
            st.caption("(No overrides to export.)")

        st.markdown("##### Import")
        uploaded = st.file_uploader(
            "Upload a `data_overrides.json` file",
            type=["json"],
            key="data_import_uploader",
        )
        if uploaded is not None:
            raw = uploaded.getvalue().decode("utf-8")
            imported, error = _parse_import_payload(raw)
            if error:
                st.error(error)
                return

            mode = st.radio(
                "Import mode",
                ["Merge (keep existing, overwrite on conflict)", "Replace (clear then load)"],
                key="data_import_mode",
            )
            if st.button("Apply import", type="primary", key="data_import_apply"):
                applied, skipped = _apply_imported_overrides(
                    imported, replace_existing=mode.startswith("Replace"),
                )
                if skipped:
                    st.warning(
                        f"Applied {applied} overrides; skipped {len(skipped)} invalid:\n"
                        + "\n".join(f"- {s}" for s in skipped)
                    )
                else:
                    st.success(f"Imported {applied} override(s).")
                st.rerun()
