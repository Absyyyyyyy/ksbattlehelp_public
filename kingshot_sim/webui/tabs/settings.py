from __future__ import annotations

from datetime import datetime

import streamlit as st

from kingshot_sim.webui import persistence, components
from kingshot_sim.io_pkg import backup as backup_mod


def render() -> None:
    components.render_page_header(
        title="Settings & profiles",
        sub="Save your favorite compositions, adjust advanced options, and "
            "back up everything to a single file.",
    )

    if persistence.is_session_backend():
        st.info(
            "**Public version**. Profiles, rosters and overrides you save "
            "here live in **your current browser session only**. They are "
            "private to you (other visitors of this app never see them), "
            "but they will disappear when you refresh the page or come "
            "back later. **Use the *Backup & restore* tab below to download "
            "a JSON file you can re-upload next time.** Or clone the repo "
            "and run the app locally for permanent disk storage. See the "
            "README on [GitHub](https://github.com/Absyyyyyyy/ksbattlehelper) "
            "for instructions.",
        )

    profiles = persistence.list_profiles()
    spaces = persistence.list_search_spaces()

    tab_p, tab_s, tab_adv, tab_backup = st.tabs([
        f"Saved profiles ({len(profiles)})",
        f"Saved rosters ({len(spaces)})",
        "Advanced options",
        "Backup & restore",
    ])

    with tab_p:
        _render_profiles(profiles)
    with tab_s:
        _render_search_spaces(spaces)
    with tab_adv:
        _render_advanced()
    with tab_backup:
        _render_backup_restore()


def _render_advanced() -> None:
    tab_op, tab_data = st.tabs([
        "Customize skills (op codes)",
        "Customize data (T11 stats, etc.)",
    ])
    with tab_op:
        _render_op_overrides()
    with tab_data:
        _render_data_overrides()


def _render_data_overrides() -> None:
    from kingshot_sim.webui.data_overrides_panel import render as _render_panel
    _render_panel()


def _render_op_overrides() -> None:
    from kingshot_sim.data.op_overrides import (
        set_op_override, clear_op_override, clear_all_overrides,
        list_op_overrides,
    )
    from kingshot_sim.data.reference import MYTHIC_HEROES, EPIC_HEROES
    from kingshot_sim.domain.enums import OP_TO_FAMILY, Family
    from kingshot_sim.config.fighter import LeaderHero, JoinerHero

    components.render_subheading("Op-code overrides")
    if persistence.is_session_backend():
        st.caption(
            "Override the op code of a specific skill effect. Useful when an "
            "in-game skill mechanic is interpreted differently from this "
            "simulator's catalog (some op assignments are *probable* in the "
            "spec, not *confirmed*). **Overrides you add here are private "
            "to your current browser session** and reset on refresh. Use "
            "*Backup & restore* to keep them across sessions."
        )
    else:
        st.caption(
            "Override the op code of a specific skill effect. Useful when an "
            "in-game skill mechanic is interpreted differently from this "
            "simulator's catalog (some op assignments are *probable* in the "
            "spec, not *confirmed*). All changes are persisted to "
            "`~/.kingshot_sim/op_overrides.json` and take effect immediately."
        )

    overrides = list_op_overrides()
    if overrides:
        st.markdown(f"**Active overrides ({sum(len(v) for v in overrides.values())}):**")
        for (hero, slot), rules in sorted(overrides.items()):
            for orig, new in rules:
                cols = st.columns([4, 1])
                cols[0].markdown(
                    f"- **{hero}** {slot}: op `{orig}` ({OP_TO_FAMILY[orig].value}) "
                    f"→ op `{new}` ({OP_TO_FAMILY[new].value})"
                )
                if cols[1].button("Remove", key=f"adv_rm_{hero}_{slot}_{orig}"):
                    clear_op_override(hero, slot, orig)
                    st.rerun()
        if st.button("Clear ALL overrides", type="secondary", key="adv_clear_all"):
            clear_all_overrides()
            st.rerun()
        st.markdown("---")
    else:
        st.info("No overrides set. Use the form below to add one.")

    st.markdown("##### Add a new override")
    all_heroes = sorted(MYTHIC_HEROES | EPIC_HEROES)
    cols = st.columns([2, 1, 1])
    with cols[0]:
        hero_pick = st.selectbox("Hero", all_heroes, key="adv_hero")
    with cols[1]:
        if hero_pick in MYTHIC_HEROES:
            slot_choices = ["sk1", "sk2", "sk3", "widget"]
        else:
            slot_choices = ["sk1", "sk2"]
        slot_pick = st.selectbox("Slot", slot_choices, key="adv_slot")

    try:
        if hero_pick in MYTHIC_HEROES:
            hero_obj = LeaderHero(hero_name=hero_pick, level="MAX",
                                    widget_level=10).to_hero()
        else:
            hero_obj = JoinerHero(hero_name=hero_pick, level="MAX").to_hero()
        from kingshot_sim.data import catalog as _catalog
        if hero_obj.is_mythic:
            raw = _catalog._mythic_skills(hero_obj)
            if slot_pick == "widget":
                w = _catalog._widget_skill(hero_obj)
                raw = [w] if w is not None else []
        else:
            raw = _catalog._epic_skills(hero_obj)
        match = next((s for s in raw if s.slot == slot_pick), None)
    except Exception:
        match = None

    if match is None or not match.effects:
        st.warning(f"{hero_pick} has no overridable effect at slot {slot_pick}.")
        return

    st.caption(f"**{match.name}**. {match.description or '(no description)'}")
    eff_options = [
        f"op {e.op} ({OP_TO_FAMILY[e.op].value}). Value {e.value:+.1f}%"
        for e in match.effects
    ]
    eff_idx = st.selectbox(
        "Effect to override",
        list(range(len(match.effects))),
        format_func=lambda i: eff_options[i],
        key=f"adv_effidx_{hero_pick}_{slot_pick}",
    )
    chosen_effect = match.effects[eff_idx]

    valid_ops = sorted(OP_TO_FAMILY.keys())
    new_op_default_idx = valid_ops.index(chosen_effect.op)
    new_op = st.selectbox(
        f"New op code (current: {chosen_effect.op})",
        valid_ops,
        index=new_op_default_idx,
        format_func=lambda o: f"op {o} ({OP_TO_FAMILY[o].value})",
        key=f"adv_newop_{hero_pick}_{slot_pick}_{eff_idx}",
    )
    if st.button("Apply override", type="primary", key="adv_apply"):
        try:
            set_op_override(hero_pick, slot_pick, chosen_effect.op, int(new_op))
            if int(new_op) == chosen_effect.op:
                st.info("New op equals original op → override cleared (no-op).")
            else:
                st.success(
                    f"Override set: {hero_pick} {slot_pick} op {chosen_effect.op} → {new_op}"
                )
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def _render_profiles(profiles: list[str]) -> None:
    components.render_subheading("Saved compositions")
    st.caption(
        "Compositions saved from Quick Fight or Attack & Defense "
        "appear here. You can inspect them or delete the ones you no longer need."
    )
    if not profiles:
        st.info(
            "No saved compositions yet. Go to **Attack & Defense** or "
            "**Quick Fight**, set up a fighter, and save it from there."
        )
        return

    for p in profiles:
        cols = st.columns([4, 1, 1])
        cols[0].markdown(f"**{p}**")
        if cols[1].button("Inspect", key=f"insp_{p}"):
            fighter = persistence.load_profile(p)
            st.session_state.set_inspect_profile = (p, fighter)
        if cols[2].button("Delete", key=f"del_{p}"):
            persistence.delete_profile(p)
            st.rerun()

    if "set_inspect_profile" in st.session_state:
        name, fighter = st.session_state.set_inspect_profile
        st.markdown("---")
        components.render_subheading(f"Inspecting: {name}")
        with st.expander("Composition details", expanded=True):
            rows = [
                ("Label", fighter.label),
                ("Inf leader", f"{fighter.leader_inf.hero_name} ★{fighter.leader_inf.level} "
                               f"(W{fighter.leader_inf.widget_level})"),
                ("Cav leader", f"{fighter.leader_cav.hero_name} ★{fighter.leader_cav.level} "
                               f"(W{fighter.leader_cav.widget_level})"),
                ("Arc leader", f"{fighter.leader_arc.hero_name} ★{fighter.leader_arc.level} "
                               f"(W{fighter.leader_arc.widget_level})"),
                ("Joiners", ", ".join(j.hero_name for j in fighter.joiners) or "—"),
                ("Inf troops", f"{sum(g.count for g in fighter.troops.infantry):,}"),
                ("Cav troops", f"{sum(g.count for g in fighter.troops.cavalry):,}"),
                ("Arc troops", f"{sum(g.count for g in fighter.troops.archer):,}"),
            ]
            body = "".join(
                '<div style="display:flex;justify-content:space-between;gap:16px;'
                'padding:6px 0;border-top:1px solid var(--ks-border);">'
                f'<span style="color:var(--ks-text-muted);font-size:12.5px;">{k}</span>'
                f'<span style="color:var(--ks-text);font-size:13px;font-weight:500;'
                f'text-align:right;">{v}</span></div>'
                for k, v in rows
            )
            st.markdown(
                '<div style="background:var(--ks-surface);border:1px solid var(--ks-border);'
                'border-radius:8px;padding:6px 14px;box-shadow:var(--ks-shadow);">'
                + body + '</div>',
                unsafe_allow_html=True,
            )
        if st.button("Close inspection", key="set_close_inspect"):
            st.session_state.pop("set_inspect_profile", None)
            st.rerun()


def _render_search_spaces(spaces: list[str]) -> None:
    components.render_subheading("Saved search spaces")
    if not spaces:
        st.info("No search spaces yet. Build one in Attack & Defense and save it.")
    else:
        for s in spaces:
            cols = st.columns([4, 1])
            cols[0].markdown(f"**{s}**")
            if cols[1].button("Delete", key=f"del_sp_{s}"):
                persistence.delete_search(s)
                st.rerun()


def _render_backup_restore() -> None:
    components.render_subheading("Backup & restore")
    if persistence.is_session_backend():
        st.markdown(
            "Anything you save in this app (compositions, rosters, "
            "skill overrides, data overrides) lives in your **current "
            "browser session only**. Use this panel to download a single "
            "JSON file you can re-upload next time you visit. The file "
            "stays on your computer. Nothing is sent anywhere."
        )
    else:
        st.markdown(
            "You're running in **disk-backed** mode (saves persist to "
            "`~/.kingshot_sim/`). Use this panel to export everything as "
            "one JSON file. Handy for moving your setup to another "
            "machine or sharing it with a teammate."
        )

    payload = backup_mod.build_backup_payload()
    n_profiles = len(payload.get("profiles", {}))
    n_searches = len(payload.get("search_spaces", {}))
    n_op = len(payload.get("op_overrides", []))
    n_data = len(payload.get("data_overrides", {}))

    cols = st.columns(4)
    cols[0].metric("Profiles",   n_profiles)
    cols[1].metric("Rosters",    n_searches)
    cols[2].metric("Op overrides", n_op)
    cols[3].metric("Data overrides", n_data)

    st.markdown("---")

    st.markdown("##### Download backup")
    if n_profiles + n_searches + n_op + n_data == 0:
        st.caption("Nothing to back up yet. Save a composition or change an "
                   "override first.")
    else:
        import json as _json
        blob = _json.dumps(payload, indent=2)
        fname = (
            "ksbattlehelper_backup_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        )
        st.download_button(
            "Download my data (.json)",
            data=blob,
            file_name=fname,
            mime="application/json",
            type="primary",
            key="backup_download_btn",
        )
        st.caption(
            f"Filename `{fname}`. Keep it on your computer. Uploading it "
            "later restores everything exactly as it is right now."
        )

    st.markdown("---")

    st.markdown("##### Restore from a backup file")
    uploaded = st.file_uploader(
        "Upload a previously-downloaded backup JSON",
        type=["json"],
        key="backup_upload_uploader",
        help="Drop a `ksbattlehelper_backup_*.json` file here. "
              "Per-section import errors are reported but won't abort "
              "the rest of the load.",
    )
    if uploaded is None:
        return

    raw = uploaded.getvalue().decode("utf-8", errors="replace")
    parsed, error = backup_mod.parse_backup_blob(raw)
    if error:
        st.error(f"Couldn't parse this file: {error}")
        return

    p_in = parsed.get("profiles", {}) or {}
    s_in = parsed.get("search_spaces", {}) or {}
    o_in = parsed.get("op_overrides", []) or []
    d_in = parsed.get("data_overrides", {}) or {}
    st.success(
        f"File looks valid. Contents: **{len(p_in)} profile(s)**, "
        f"**{len(s_in)} roster(s)**, **{len(o_in)} op override(s)**, "
        f"**{len(d_in)} data override(s)**."
    )

    mode = st.radio(
        "Import mode",
        [
            "Merge. Keep existing entries; overwrite on name conflict",
            "Replace. Wipe my current data first, then load the file",
        ],
        key="backup_import_mode",
    )

    if st.button("Apply restore", type="primary", key="backup_apply_btn"):
        report = backup_mod.apply_backup_payload(
            parsed,
            replace_existing=mode.startswith("Replace"),
        )
        if report.errors:
            st.warning(
                f"{report.summary()} \n\n"
                f"**{len(report.errors)} entry/entries had issues and were "
                f"skipped:**\n"
                + "\n".join(f"- {e}" for e in report.errors[:20])
                + ("\n- …" if len(report.errors) > 20 else "")
            )
        else:
            st.success(report.summary())
        st.rerun()
