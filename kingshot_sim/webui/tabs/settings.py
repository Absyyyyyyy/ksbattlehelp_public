from __future__ import annotations
import html

from datetime import datetime

import streamlit as st

from kingshot_sim.webui import persistence, components
from kingshot_sim.io_pkg import backup as backup_mod
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.benchmark.runner import HeroBuild
from kingshot_sim.config.fighter import BonusVector, HeroGearPiece
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.data.reference import (
    MYTHIC_HEROES, EPIC_HEROES, HERO_CLASS, HERO_GENERATION,
    default_skill_levels,
)
from kingshot_sim.webui.forms import (
    class_gear_editor, bonuses_form, buffs_form,
    _skill_levels_subform, _LEVEL_KEYS,
)


def create_empty_roster(name: str = "New Profile") -> AccountRoster:
    return AccountRoster(
        name=name,
        generation=8,
        owned_heroes={"Inf": [], "Cav": [], "Arc": []},
        builds={},
        class_gear={},
        bonuses=BonusVector(),
        buffs=Buffs(),
    )


def load_active_roster(name: str) -> AccountRoster:
    return persistence.load_roster(name)


def save_active_roster(roster: AccountRoster, name: str) -> None:
    persistence.save_roster(roster, name)


def delete_active_roster(name: str) -> None:
    persistence.delete_roster(name)


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
            "README on [GitHub](https://github.com/Absyyyyyyy/ksbattlehelp_public) "
            "for instructions.",
        )

    rosters = persistence.list_rosters()
    profiles = persistence.list_profiles()
    spaces = persistence.list_search_spaces()

    tab_r, tab_p, tab_s, tab_adv, tab_backup = st.tabs([
        f"Account & roster profiles ({len(rosters)})",
        f"Saved profiles ({len(profiles)})",
        f"Saved rosters ({len(spaces)})",
        "Advanced options",
        "Backup & restore",
    ])

    with tab_r:
        render_account_roster_section()
    with tab_p:
        _render_profiles(profiles)
    with tab_s:
        _render_search_spaces(spaces)
    with tab_adv:
        _render_advanced()
    with tab_backup:
        _render_backup_restore()


def render_account_roster_section() -> None:
    components.render_subheading("Account & Roster Profiles")
    st.caption(
        "Configure your account-wide hero roster, star tiers, widget levels, "
        "class gear, account bonuses, and buffs. Profiles saved here can be "
        "shared across benchmark, optimizer, and battle tabs."
    )

    saved_rosters = persistence.list_rosters()
    create_new_label = "[Create New Profile]"
    options = [create_new_label] + saved_rosters

    active_pref = st.session_state.get("_ks_active_roster")
    if active_pref and active_pref in saved_rosters:
        default_idx = options.index(active_pref)
    elif saved_rosters and "_ks_active_roster" not in st.session_state:
        default_idx = 1
    else:
        default_idx = 0

    col_sel, col_save, col_del = st.columns([3, 1, 1])
    with col_sel:
        selected_profile = st.selectbox(
            "Select Profile",
            options,
            index=default_idx,
            key="settings_roster_select",
        )

    is_new = (selected_profile == create_new_label)

    # Detect profile switch and synchronize session state
    last_loaded = st.session_state.get("_settings_active_roster_loaded")
    if last_loaded != selected_profile:
        for k in list(st.session_state.keys()):
            if (k.startswith("settings_roster_") or k.startswith("settings_roster_gear_") or
                k.startswith("settings_roster_bonuses_") or k.startswith("settings_roster_buffs_")):
                if k != "settings_roster_select":
                    st.session_state.pop(k, None)

        if is_new:
            roster_obj = create_empty_roster("New Profile")
            st.session_state["_ks_active_roster"] = ""
        else:
            try:
                roster_obj = persistence.load_roster(selected_profile)
                st.session_state["_ks_active_roster"] = selected_profile
            except Exception:
                roster_obj = create_empty_roster(selected_profile)

        st.session_state["_settings_active_roster_loaded"] = selected_profile
        st.session_state["_settings_roster_obj"] = roster_obj

    if "_settings_roster_obj" not in st.session_state:
        if is_new:
            roster_obj = create_empty_roster("New Profile")
        else:
            try:
                roster_obj = persistence.load_roster(selected_profile)
            except Exception:
                roster_obj = create_empty_roster(selected_profile)
        st.session_state["_settings_roster_obj"] = roster_obj
        st.session_state["_settings_active_roster_loaded"] = selected_profile

    roster_obj = st.session_state["_settings_roster_obj"]

    with col_save:
        save_clicked = st.button(
            "Save Profile",
            type="primary",
            key="settings_roster_save_btn",
            use_container_width=True,
        )
    with col_del:
        del_clicked = st.button(
            "Delete Profile",
            type="secondary",
            key="settings_roster_del_btn",
            disabled=is_new,
            use_container_width=True,
        )

    profile_name = st.text_input(
        "Profile Name",
        value=roster_obj.name,
        key="settings_roster_name_input",
    )

    with st.expander("Save As...", expanded=False):
        sa_cols = st.columns([3, 1])
        with sa_cols[0]:
            save_as_name = st.text_input(
                "New profile name",
                value=f"{profile_name} (Copy)",
                key="settings_roster_save_as_input",
            )
        with sa_cols[1]:
            save_as_clicked = st.button("Save Copy", key="settings_roster_save_as_btn")

    # Download & Upload JSON
    down_col, up_col = st.columns([1, 1])
    with down_col:
        json_blob = persistence.roster_to_json(roster_obj)
        safe_fname = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile_name.strip()) or "roster"
        st.download_button(
            "Download JSON (v2)",
            data=json_blob,
            file_name=f"{safe_fname}_roster.json",
            mime="application/json",
            key="settings_roster_download_json",
            use_container_width=True,
        )
    with up_col:
        uploaded_file = st.file_uploader(
            "Upload JSON (v2)",
            type=["json"],
            key="settings_roster_upload_json",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            raw_content = uploaded_file.getvalue().decode("utf-8", errors="replace")
            try:
                imported_roster = persistence.roster_from_json(raw_content)
                persistence.save_roster(imported_roster, imported_roster.name)
                st.session_state["_ks_active_roster"] = imported_roster.name
                st.session_state["_settings_active_roster_loaded"] = imported_roster.name
                st.session_state["_settings_roster_obj"] = imported_roster
                for k in list(st.session_state.keys()):
                    if (k.startswith("settings_roster_") or k.startswith("settings_roster_gear_") or
                        k.startswith("settings_roster_bonuses_") or k.startswith("settings_roster_buffs_")):
                        if k != "settings_roster_select":
                            st.session_state.pop(k, None)
                st.success(f"Successfully imported profile '{imported_roster.name}'!")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not import JSON: {exc}")

    # OCR Screenshot Scanner
    with st.expander("OCR screenshot scanner (Heroes grid)", expanded=False):
        st.caption(
            "Upload a screenshot of your in-game 'Heroes' collection screen (4-column grid, sorted by Quality). "
            "Heroes and star tiers will be auto-detected and populated into this profile."
        )
        ocr_img_file = st.file_uploader(
            "Heroes screenshot",
            type=["png", "jpg", "jpeg"],
            key="settings_roster_ocr_uploader",
        )
        if ocr_img_file is not None and st.button("Scan screenshot", key="settings_roster_ocr_scan_btn", type="primary"):
            try:
                from PIL import Image
                from kingshot_sim.easy_mode.ocr_hero_roster import ocr_hero_roster
                res = ocr_hero_roster(Image.open(ocr_img_file))
                if res.error:
                    st.warning(res.error)
                elif not res.cells:
                    st.warning("No hero cards detected in the screenshot.")
                else:
                    count = 0
                    for cell in res.cells:
                        h = cell.hero_name
                        star = max(0, min(5, int(cell.star)))
                        sub = max(0, min(5, int(getattr(cell, "sub_tier", 0))))
                        lvl = "MAX" if star >= 5 else f"{star}_{sub}"
                        st.session_state[f"settings_roster_owned_{h}"] = True
                        st.session_state[f"settings_roster_lvl_{h}"] = lvl
                        kl = cell.klass or HERO_CLASS.get(h)
                        if kl:
                            cur_list = roster_obj.owned_heroes.setdefault(kl, [])
                            if h not in cur_list:
                                cur_list.append(h)
                        eb = roster_obj.builds.get(h)
                        wl = eb.widget_level if eb else (0 if h in EPIC_HEROES else 4)
                        sl = eb.skill_levels if eb else None
                        roster_obj.builds[h] = HeroBuild(level=lvl, widget_level=wl, skill_levels=sl)
                        count += 1
                    st.session_state["_settings_roster_obj"] = roster_obj
                    st.success(f"Detected {count} heroes from screenshot!")
                    st.rerun()
            except Exception as exc:
                st.error(f"OCR error: {exc}")

    # Sub-editors: Generation slider
    st.markdown("---")
    gen_val = st.slider(
        "Hero Generation",
        min_value=1,
        max_value=8,
        value=max(1, min(8, int(roster_obj.generation))),
        key="settings_roster_generation",
        help="Include heroes up to this generation.",
    )

    # Sub-editors: Hero Class Tabs
    tab_inf, tab_cav, tab_arc = st.tabs(["Infantry Heroes", "Cavalry Heroes", "Archer Heroes"])
    collected_owned: dict[str, list[str]] = {"Inf": [], "Cav": [], "Arc": []}
    collected_builds: dict[str, HeroBuild] = dict(roster_obj.builds)

    for klass, tab_elem in [("Inf", tab_inf), ("Cav", tab_cav), ("Arc", tab_arc)]:
        with tab_elem:
            all_class_heroes = [h for h, c in HERO_CLASS.items() if c == klass]
            avail_heroes = [
                h for h in all_class_heroes
                if HERO_GENERATION.get(h) is None or HERO_GENERATION[h] <= gen_val
            ]

            def _hero_sort_key(hero_key: str):
                is_epic = hero_key in EPIC_HEROES
                gen = HERO_GENERATION.get(hero_key, 0)
                return (is_epic, gen, hero_key)

            avail_heroes.sort(key=_hero_sort_key)

            hdr = st.columns([2, 2, 2, 3])
            hdr[0].markdown("**Hero**")
            hdr[1].markdown("**Level / Stars**")
            hdr[2].markdown("**Widget**")
            hdr[3].markdown("**Skills (Sk1 / Sk2 / Sk3)**")

            for h in avail_heroes:
                is_mythic = h in MYTHIC_HEROES
                owned_default = h in roster_obj.owned_heroes.get(klass, [])
                existing_build = roster_obj.builds.get(h)
                lvl_default = existing_build.level if existing_build else "MAX"
                lvl_idx = _LEVEL_KEYS.index(lvl_default) if lvl_default in _LEVEL_KEYS else len(_LEVEL_KEYS) - 1
                wdg_default = existing_build.widget_level if existing_build else (10 if is_mythic else 0)
                sl_default = (
                    existing_build.skill_levels
                    if (existing_build and existing_build.skill_levels is not None)
                    else default_skill_levels(lvl_default)
                )

                row_cols = st.columns([2, 2, 2, 3])
                with row_cols[0]:
                    prefix_icon = "★ " if is_mythic else "◆ "
                    gen_str = f" (Gen {HERO_GENERATION[h]})" if h in HERO_GENERATION else ""
                    is_owned = st.checkbox(
                        f"{prefix_icon}{h}{gen_str}",
                        value=owned_default,
                        key=f"settings_roster_owned_{h}",
                    )
                with row_cols[1]:
                    lvl_chosen = st.selectbox(
                        f"Level {h}",
                        _LEVEL_KEYS,
                        index=lvl_idx,
                        key=f"settings_roster_lvl_{h}",
                        label_visibility="collapsed",
                    )
                with row_cols[2]:
                    if is_mythic:
                        wdg_chosen = st.slider(
                            f"Widget {h}",
                            0,
                            10,
                            value=wdg_default,
                            key=f"settings_roster_wdg_{h}",
                            label_visibility="collapsed",
                        )
                    else:
                        st.caption("— (Epic)")
                        wdg_chosen = 0
                with row_cols[3]:
                    sl_chosen = _skill_levels_subform(
                        lvl_chosen,
                        sl_default,
                        key_prefix=f"settings_roster_sk_{h}",
                    )

                if is_owned:
                    collected_owned[klass].append(h)
                collected_builds[h] = HeroBuild(
                    level=lvl_chosen,
                    widget_level=wdg_chosen,
                    skill_levels=sl_chosen,
                )

    # Class Gear Editor
    st.markdown("---")
    components.render_subheading("Class Gear")
    st.caption("Shared gear configuration per class. Applies to all leaders of each class.")
    class_gear_val = class_gear_editor(
        default=roster_obj.class_gear,
        key_prefix="settings_roster_gear",
    )

    # Account Stat Bonuses
    st.markdown("---")
    components.render_subheading("Account Stat Bonuses")
    bonuses_val = bonuses_form(
        default=roster_obj.bonuses,
        key_prefix="settings_roster_bonuses",
    )

    # Account Buffs
    st.markdown("---")
    components.render_subheading("Account Buffs")
    buffs_val = buffs_form(
        default=roster_obj.buffs,
        key_prefix="settings_roster_buffs",
    )

    current_roster = AccountRoster(
        name=profile_name.strip() or "Unnamed Profile",
        generation=gen_val,
        owned_heroes=collected_owned,
        builds=collected_builds,
        class_gear=class_gear_val,
        bonuses=bonuses_val,
        buffs=buffs_val,
    )
    st.session_state["_settings_roster_obj"] = current_roster

    st.markdown("---")
    bottom_save_clicked = st.button(
        "Save Profile",
        type="primary",
        key="settings_roster_bottom_save_btn",
    )

    if save_clicked or bottom_save_clicked:
        save_name = current_roster.name
        persistence.save_roster(current_roster, save_name)
        st.session_state["_ks_active_roster"] = save_name
        st.session_state["_settings_active_roster_loaded"] = save_name
        st.session_state["_settings_roster_obj"] = current_roster
        st.session_state["settings_roster_select"] = save_name
        st.success(f"Profile '{save_name}' saved successfully!")
        st.rerun()

    if save_as_clicked:
        new_name = save_as_name.strip()
        if new_name:
            current_roster.name = new_name
            persistence.save_roster(current_roster, new_name)
            st.session_state["_ks_active_roster"] = new_name
            st.session_state["_settings_active_roster_loaded"] = new_name
            st.session_state["_settings_roster_obj"] = current_roster
            st.session_state["settings_roster_select"] = new_name
            st.success(f"Profile saved as '{new_name}'!")
            st.rerun()

    if del_clicked and not is_new:
        persistence.delete_roster(selected_profile)
        st.session_state.pop("_settings_roster_obj", None)
        st.session_state.pop("_settings_active_roster_loaded", None)
        if st.session_state.get("_ks_active_roster") == selected_profile:
            st.session_state.pop("_ks_active_roster", None)
        st.session_state.pop("settings_roster_select", None)
        st.success(f"Profile '{selected_profile}' deleted.")
        st.rerun()

    with st.expander(f"All saved roster profiles ({len(saved_rosters)})", expanded=False):
        if not saved_rosters:
            st.info("No saved roster profiles yet.")
        else:
            for r_name in saved_rosters:
                r_cols = st.columns([3, 1, 1])
                r_cols[0].markdown(f"**{r_name}**")
                if r_cols[1].button("Load", key=f"settings_load_roster_list_{r_name}"):
                    st.session_state["_ks_active_roster"] = r_name
                    st.session_state["settings_roster_select"] = r_name
                    st.session_state["_settings_active_roster_loaded"] = r_name
                    st.session_state["_settings_roster_obj"] = persistence.load_roster(r_name)
                    for k in list(st.session_state.keys()):
                        if (k.startswith("settings_roster_") or k.startswith("settings_roster_gear_") or
                            k.startswith("settings_roster_bonuses_") or k.startswith("settings_roster_buffs_")):
                            if k != "settings_roster_select":
                                st.session_state.pop(k, None)
                    st.rerun()
                if r_cols[2].button("Delete", key=f"settings_del_roster_list_{r_name}"):
                    persistence.delete_roster(r_name)
                    if st.session_state.get("_ks_active_roster") == r_name:
                        st.session_state.pop("_ks_active_roster", None)
                        st.session_state.pop("_settings_active_roster_loaded", None)
                        st.session_state.pop("_settings_roster_obj", None)
                    st.rerun()



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
        components.render_subheading(f"Inspecting: {html.escape(name)}")
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
                f'text-align:right;">{html.escape(str(v))}</span></div>'
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
