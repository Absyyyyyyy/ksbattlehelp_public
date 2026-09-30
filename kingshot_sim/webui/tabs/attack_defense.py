from __future__ import annotations
import html

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool
from kingshot_sim.optimizer.best_counter import find_best_counter, find_best_defender
from kingshot_sim.optimizer.enumerate import count_candidates
from kingshot_sim.data.reference import (
    MYTHIC_HEROES, EPIC_HEROES, HERO_CLASS,
    NON_COMBAT_FIRST_SKILL_HEROES, HERO_GENERATION, MAX_GENERATION,
    parse_tier_label, hero_class,
)
from kingshot_sim.config.fighter import Fighter
from kingshot_sim.io_pkg.roster_bridge import (
    roster_to_search_space,
    update_roster_from_search_space,
    roster_to_fighter,
)
from kingshot_sim.io_pkg.rosters import AccountRoster
from kingshot_sim.webui.forms import (
    empty_fighter, bonuses_form, buffs_form,
    pool_tier_from_inputs, _troop_max_tier, _troop_tg_options,
)
from kingshot_sim.webui.easy_mode_form import (
    fighter_form_with_mode, is_easy_mode, easy_mode_rally_flag,
    render_roster_import, render_gear_roster_import,
)
from kingshot_sim.webui import persistence, components
from kingshot_sim.webui.search_runner import (
    SearchJob, start_search, render_running_panel, MAX_SEARCH_SIZE,
)


_INF_MYTHICS = sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Inf")
_CAV_MYTHICS = sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Cav")
_ARC_MYTHICS = sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Arc")
_JOINER_HEROES = sorted(
    (MYTHIC_HEROES | EPIC_HEROES) - NON_COMBAT_FIRST_SKILL_HEROES
)


@dataclass(frozen=True)
class _ModeCfg:
    is_defense: bool
    prefix: str
    opp_tag: str
    opp_word: str
    title: str
    sub: str
    opp_section: str
    opp_lock_msg: str
    opp_heading: str
    opp_caption: str
    opp_setup_expander: str
    opp_empty_label: str
    roster_section: str
    roster_setup_expander: str
    save_sp_default: str
    topk_help: str
    work_fn: Callable
    results_noun: str
    tested_noun: str
    score_col_label: str
    win_col_label: str
    drill_save_prefix: str

    @property
    def sp_prefix(self) -> str:
        return f"{self.prefix}_sp"

    @property
    def opp_prefix(self) -> str:
        return f"{self.prefix}_{self.opp_tag}"

    @property
    def opp_session_key(self) -> str:
        return f"{self.prefix}_{self.opp_word}"

    @property
    def opp_form_side(self) -> str:
        return self.opp_word

    @property
    def roster_form_side(self) -> str:
        return "defender" if self.is_defense else "attacker"

    @property
    def opp_kwarg(self) -> str:
        return self.opp_word

    @property
    def last_label_key(self) -> str:
        return f"{self.prefix}_last_{self.opp_word}_label"

    @property
    def opp_label_attr(self) -> str:
        return f"{self.opp_word}_label"

    @property
    def entry_attr(self) -> str:
        return "candidate" if self.is_defense else "attacker"

    @property
    def results_anchor(self) -> str:
        return f"ks-{self.prefix}-results-anchor"


_ATTACK = _ModeCfg(
    is_defense=False,
    prefix="bc", opp_tag="def", opp_word="defender",
    title="Best Counter",
    sub="What's the best composition to break this garrison? "
        "Set the target and your roster, and we test every combination "
        "and rank the top 10.",
    opp_section="Garrison to break",
    opp_lock_msg="Target garrison locked while the search runs.",
    opp_heading="##### Target garrison",
    opp_caption="Describe the defense you're going to attack (heroes, troops, bonuses).",
    opp_setup_expander="Set up the enemy garrison",
    opp_empty_label="Target garrison",
    roster_section="Your roster",
    roster_setup_expander="Set up your roster",
    save_sp_default="my_roster",
    topk_help="How many top compositions to rank.",
    work_fn=find_best_counter,
    results_noun="counters",
    tested_noun="compositions",
    score_col_label="Score",
    win_col_label="Win rate",
    drill_save_prefix="top_",
)

_DEFENSE = _ModeCfg(
    is_defense=True,
    prefix="bd", opp_tag="att", opp_word="attacker",
    title="Best Defense",
    sub="What's the best defense to hold against this rally? "
        "Set the threat and your roster, and we test every garrison "
        "composition and rank the 10 strongest.",
    opp_section="Rally to stop",
    opp_lock_msg="Attacker rally locked while the search runs.",
    opp_heading="##### Incoming rally",
    opp_caption="Describe the attacker targeting your city (heroes, troops, bonuses).",
    opp_setup_expander="Set up the enemy rally",
    opp_empty_label="Incoming rally",
    roster_section="Your defending roster",
    roster_setup_expander="Set up your defending roster",
    save_sp_default="my_defense",
    topk_help="How many top defenses to rank.",
    work_fn=find_best_defender,
    results_noun="defenses",
    tested_noun="defenses",
    score_col_label="Defense score",
    win_col_label="Defender win",
    drill_save_prefix="def_top_",
)

_MODE_KEY = "ad_mode"
_ATTACK_LABEL = "Best counter (I'm attacking)"
_DEFENSE_LABEL = "Best defense (I'm defending)"

_DEFAULT_INF = ("Helga", "Eric", "Triton")
_DEFAULT_CAV = ("Petra", "Margot", "Sophia")
_DEFAULT_ARC = ("Jaeger", "Yang", "Vivian")
_DEFAULT_JOINERS = ("Chenko", "Howard", "Quinn", "Yeonwoo", "Amane")


def _default_space() -> SearchSpace:
    return SearchSpace(
        available_mythic_inf=list(_DEFAULT_INF),
        available_mythic_cav=list(_DEFAULT_CAV),
        available_mythic_arc=list(_DEFAULT_ARC),
        available_joiners=list(_DEFAULT_JOINERS),
        troop_pool=TroopPool(march_cap=300_000),
        n_joiners=4,
    )


def _roster_is_untouched_default(space: SearchSpace) -> bool:
    return (
        sorted(space.available_mythic_inf) == sorted(_DEFAULT_INF)
        and sorted(space.available_mythic_cav) == sorted(_DEFAULT_CAV)
        and sorted(space.available_mythic_arc) == sorted(_DEFAULT_ARC)
        and sorted(space.available_joiners) == sorted(_DEFAULT_JOINERS)
    )


def _cfg_for(mode_label: str) -> _ModeCfg:
    return _DEFENSE if mode_label == _DEFENSE_LABEL else _ATTACK


def _fighter_from_roster(
    roster: AccountRoster,
    current_opp: Fighter | None = None,
    default_label: str = "Opponent",
) -> Fighter:
    def _pick_leader(cls: str, current_hero: str | None, fallback: str) -> str:
        cls_owned = [h for h in roster.owned_heroes.get(cls, []) if hero_class(h) == cls]
        if not cls_owned:
            cls_owned = [h for h in roster.builds if hero_class(h) == cls]
        if current_hero and current_hero in cls_owned:
            return current_hero
        if cls_owned:
            return cls_owned[0]
        if current_hero and hero_class(current_hero) == cls:
            return current_hero
        return fallback

    curr_inf = current_opp.leader_inf.hero_name if current_opp and current_opp.leader_inf else None
    curr_cav = current_opp.leader_cav.hero_name if current_opp and current_opp.leader_cav else None
    curr_arc = current_opp.leader_arc.hero_name if current_opp and current_opp.leader_arc else None

    inf_hero = _pick_leader("Inf", curr_inf, "Eric")
    cav_hero = _pick_leader("Cav", curr_cav, "Petra")
    arc_hero = _pick_leader("Arc", curr_arc, "Jaeger")

    joiners: list[str] = []
    if current_opp and current_opp.joiners:
        joiners = [j.hero_name for j in current_opp.joiners if j.hero_name not in (inf_hero, cav_hero, arc_hero)]
    if not joiners and roster.owned_heroes:
        for c in ("Inf", "Cav", "Arc"):
            for h in roster.owned_heroes.get(c, []):
                if (h in MYTHIC_HEROES or h in EPIC_HEROES) and (h not in NON_COMBAT_FIRST_SKILL_HEROES):
                    if h not in (inf_hero, cav_hero, arc_hero) and h not in joiners:
                        joiners.append(h)
    joiners = joiners[:4]

    troops = current_opp.troops if current_opp else None

    return roster_to_fighter(
        roster,
        inf_hero=inf_hero,
        cav_hero=cav_hero,
        arc_hero=arc_hero,
        joiners=tuple(joiners),
        troops=troops,
        label=roster.name or default_label,
    )


def _clear_and_rehydrate_space_widgets(sp: str, space: SearchSpace) -> None:
    prefixes = (
        f"{sp}_inf",
        f"{sp}_cav",
        f"{sp}_arc",
        f"{sp}_joiners",
        f"{sp}_lspec",
        f"{sp}_classgear",
        f"{sp}_bonus",
        f"{sp}_buffs",
        f"{sp}_march",
        f"{sp}_level",
        f"{sp}_tg",
        f"{sp}_step",
        f"{sp}_njoiners",
        f"{sp}_mininf",
        f"{sp}_easy",
        f"{sp}_pending",
        f"{sp}_post_import",
    )
    keys_to_pop = [k for k in list(st.session_state.keys()) if any(k.startswith(p) for p in prefixes)]
    for k in keys_to_pop:
        st.session_state.pop(k, None)

    st.session_state[f"{sp}_input_mode"] = "Advanced"
    st.session_state[f"{sp}_input_mode_radio"] = "Manual entry (Advanced)"


def _render_candidate_profile_toolbar(cfg: _ModeCfg) -> tuple[bool, bool, str | None]:
    prefix = cfg.prefix
    sp = cfg.sp_prefix
    saved_rosters = persistence.list_rosters()
    active_pref = st.session_state.get("_ks_active_roster")

    if not saved_rosters:
        col_msg, col_reload, col_save = st.columns([3, 1.5, 2])
        with col_msg:
            st.caption("No account profiles saved yet. Create one in Settings.")
        with col_reload:
            st.button(
                "🔄 Reload from Profile",
                disabled=True,
                key=f"{prefix}_reload_roster_btn",
            )
        with col_save:
            st.button(
                "💾 Save Changes Back to Profile",
                disabled=True,
                key=f"{prefix}_save_roster_btn",
            )
        return False, False, None

    default_idx = 0
    if active_pref and active_pref in saved_rosters:
        default_idx = saved_rosters.index(active_pref)
        if st.session_state.get(f"{prefix}_synced_active") != active_pref:
            st.session_state.pop(f"{prefix}_roster_select", None)
            st.session_state[f"{prefix}_synced_active"] = active_pref

    if st.session_state.get(f"{prefix}_roster_select") not in saved_rosters:
        st.session_state.pop(f"{prefix}_roster_select", None)

    col_sel, col_reload, col_save = st.columns([3, 1.5, 2])
    with col_sel:
        sb_idx = None if f"{prefix}_roster_select" in st.session_state else default_idx
        selected_profile = st.selectbox(
            "Account Profile",
            saved_rosters,
            index=sb_idx,
            key=f"{prefix}_roster_select",
            label_visibility="collapsed",
        )
    with col_reload:
        reload_clicked = st.button(
            "🔄 Reload from Profile",
            key=f"{prefix}_reload_roster_btn",
        )
    with col_save:
        save_clicked = st.button(
            "💾 Save Changes Back to Profile",
            key=f"{prefix}_save_roster_btn",
        )

    last_loaded = st.session_state.get(f"{prefix}_active_profile_loaded")
    should_load = False

    if selected_profile != last_loaded:
        should_load = True
    elif reload_clicked:
        should_load = True

    if should_load and selected_profile:
        try:
            roster = persistence.load_roster(selected_profile)
            base_space = st.session_state.get(f"{prefix}_space", _default_space())
            new_space = roster_to_search_space(roster, base=base_space)
            st.session_state[f"{prefix}_space"] = new_space
            st.session_state["_ks_active_roster"] = selected_profile
            st.session_state[f"{prefix}_active_profile_loaded"] = selected_profile
            st.session_state[f"{prefix}_synced_active"] = selected_profile
            st.session_state[f"{prefix}_example_banner_dismissed"] = True
            _clear_and_rehydrate_space_widgets(sp, new_space)
            if reload_clicked:
                st.success(f"Profile '{selected_profile}' reloaded successfully.")
        except Exception as e:
            st.error(f"Failed to load profile '{selected_profile}': {e}")

    return reload_clicked, save_clicked, selected_profile


def render_session_loss_note(key: str) -> None:
    if not persistence.is_session_backend():
        return
    st.caption("Session-only. It's gone on refresh. Back it up →")
    try:
        import json as _json
        from datetime import datetime as _dt
        from kingshot_sim.io_pkg import backup as _backup_mod
        payload = _backup_mod.build_backup_payload()
    except Exception:
        return
    n = (len(payload.get("profiles", {})) + len(payload.get("search_spaces", {}))
         + len(payload.get("op_overrides", [])) + len(payload.get("data_overrides", {})))
    if n == 0:
        return
    st.download_button(
        "Back up my data (.json)",
        data=_json.dumps(payload, indent=2),
        file_name=f"ksbattlehelper_backup_{_dt.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        key=f"{key}_backup_dl",
        width="stretch",
    )


def _handoff_to(target_tab: str, att_key: str, def_key: str,
                cand, opponent, *, is_def: bool, is_solo: bool) -> None:
    if is_def:
        st.session_state[att_key] = opponent
        st.session_state[def_key] = cand
    else:
        st.session_state[att_key] = cand
        st.session_state[def_key] = opponent
    if att_key == "qf_attacker":
        st.session_state["qf_is_solo_attack"] = is_solo
    st.session_state["_ks_active_tab"] = target_tab


def render() -> None:
    if st.session_state.get(_MODE_KEY) not in (_ATTACK_LABEL, _DEFENSE_LABEL):
        st.session_state[_MODE_KEY] = _ATTACK_LABEL

    pending_cfg = _cfg_for(st.session_state[_MODE_KEY])
    pj = st.session_state.get(f"{pending_cfg.prefix}_search_job")
    in_flight = pj is not None and pj.phase in ("queued", "running")

    mode_label = st.radio(
        "What are you planning?",
        [_ATTACK_LABEL, _DEFENSE_LABEL],
        horizontal=True,
        key=_MODE_KEY,
        disabled=in_flight,
        help="Best counter optimises YOUR attacking comp against a target "
             "garrison. Best defense optimises YOUR defending comp against an "
             "incoming rally. Your roster setup is kept separately for each.",
    )
    cfg = _cfg_for(mode_label)

    components.render_page_header(title=cfg.title, sub=cfg.sub)

    body = st.empty()
    with body.container():
        _render_body(cfg)


def _render_body(cfg: _ModeCfg) -> None:
    prefix = cfg.prefix
    job_key = f"{prefix}_search_job"
    cancel_key = f"{prefix}_cancel"

    job_in_flight = st.session_state.get(job_key)
    if job_in_flight is not None and job_in_flight.phase in ("queued", "running"):
        components.render_section_label(cfg.opp_section, num=1)
        st.markdown(
            '<div style="opacity:.55;padding:.6rem 1rem;border:1px solid '
            '#e5e7eb;border-radius:.5rem;background:#fafafa;">'
            f'<i>{cfg.opp_lock_msg}</i>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        components.render_section_label(cfg.roster_section, num=2)
        st.markdown(
            '<div style="opacity:.55;padding:.6rem 1rem;border:1px solid '
            '#e5e7eb;border-radius:.5rem;background:#fafafa;">'
            '<i>Roster & search-space locked while the search runs.</i>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")

        components.render_section_label("Run the search", num=3)
        render_running_panel(job_in_flight, cancel_key=cancel_key)
        return

    with st.expander("Speed tip", expanded=False):
        st.markdown(
            "**Small roster (2-4 mythics per class)** → a few seconds \n\n"
            "**Full roster (5+ mythics × 3 classes, many joiners)** → "
            "can take 1 to 5 minutes. To speed things up, tick "
            "**Quick search** in the options below: no confidence "
            "interval but reliable ranking, **5-10× faster** (still "
            "takes some time on very large rosters)."
        )

    components.render_section_label(cfg.opp_section, num=1)
    st.markdown(cfg.opp_heading)
    st.caption(cfg.opp_caption)

    is_solo_attack = st.session_state.get(f"{prefix}_is_solo_attack", False)
    if cfg.is_defense:
        if is_easy_mode(cfg.opp_prefix):
            is_solo_attack = not easy_mode_rally_flag(cfg.opp_prefix, default=True)
            st.caption(
                f"Incoming attack mode: "
                f"**{'Solo march' if is_solo_attack else 'Rally'}** (from Easy-mode P3)"
            )
        else:
            attack_mode = st.radio(
                "Incoming attack mode",
                ["Rally (with joiners)", "Solo march (no joiners)"],
                index=0 if not is_solo_attack else 1,
                horizontal=True,
                key=f"{prefix}_attack_mode",
                help=(
                    "How the attacker is hitting you. Rally evaluates each "
                    "defender candidate against a full rally (joiners + rally-side "
                    "widget skills active). Solo evaluates against a lone attacker."
                ),
            )
            is_solo_attack = attack_mode.startswith("Solo")
        st.session_state[f"{prefix}_is_solo_attack"] = is_solo_attack

    if cfg.opp_session_key not in st.session_state:
        st.session_state[cfg.opp_session_key] = empty_fighter(cfg.opp_empty_label)

    rosters = persistence.list_rosters()
    if rosters:
        rc1, rc2 = st.columns([3, 1])
        with rc1:
            sel_r = st.selectbox(
                "Load opponent from Account Profile",
                ["—"] + rosters,
                key=f"{prefix}_load_roster_{cfg.opp_tag}",
            )
        with rc2:
            if st.button(
                "Load",
                key=f"{prefix}_btn_load_roster_{cfg.opp_tag}",
                width="stretch",
            ):
                if sel_r != "—":
                    loaded_r = persistence.load_roster(sel_r)
                    curr_opp = st.session_state.get(cfg.opp_session_key)
                    st.session_state[cfg.opp_session_key] = _fighter_from_roster(
                        loaded_r, curr_opp, default_label=cfg.opp_empty_label,
                    )
                    gen_key = f"{cfg.opp_prefix}_form_gen"
                    st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[f"{cfg.opp_prefix}_input_mode"] = "Advanced"
                    st.session_state[f"{cfg.opp_prefix}_input_mode_radio"] = "Advanced (manual entry)"
                    st.rerun()

    profiles = persistence.list_profiles()
    if profiles:
        c1, c2 = st.columns([3, 1])
        with c1:
            sel = st.selectbox("Load a saved profile",
                                ["—"] + profiles, key=f"{prefix}_load_{cfg.opp_tag}")
        with c2:
            if st.button("Load", key=f"{prefix}_btn_load_{cfg.opp_tag}",
                          width="stretch"):
                if sel != "—":
                    st.session_state[cfg.opp_session_key] = persistence.load_profile(sel)
                    st.rerun()

    with st.expander(cfg.opp_setup_expander, expanded=False):
        try:
            opponent = fighter_form_with_mode(
                st.session_state[cfg.opp_session_key],
                key_prefix=cfg.opp_prefix, side=cfg.opp_form_side,
            )
            st.session_state[cfg.opp_session_key] = opponent
        except Exception as e:
            st.error(f"Invalid configuration: {e}")
            return

    components.render_section_label(cfg.roster_section, num=2)

    with st.expander(cfg.roster_setup_expander, expanded=True):
        reload_clicked, save_clicked, selected_profile = _render_candidate_profile_toolbar(cfg)

        if not cfg.is_defense:
            attack_mode = st.radio(
                "How will candidates attack?",
                ["Rally (with joiners)", "Solo march (no joiners)"],
                index=0 if not is_solo_attack else 1,
                horizontal=True,
                key=f"{prefix}_attack_mode",
                help=(
                    "Determines how every candidate attacker is evaluated. "
                    "Rally allows joiners and rally-side widgets; Solo march "
                    "disables both."
                ),
            )
            is_solo_attack = attack_mode.startswith("Solo")
            st.session_state[f"{prefix}_is_solo_attack"] = is_solo_attack

        st.markdown("##### Available heroes & joiners")
        st.caption("Check the mythic heroes you own (per class) and your available joiners.")

        if f"{prefix}_space" not in st.session_state:
            st.session_state[f"{prefix}_space"] = _default_space()

        _dismiss_key = f"{prefix}_example_banner_dismissed"
        if (_roster_is_untouched_default(st.session_state[f"{prefix}_space"])
                and not st.session_state.get(_dismiss_key, False)):
            bc1, bc2 = st.columns([6, 1])
            with bc1:
                st.warning(
                    "**These are example heroes.** Replace them with the ones "
                    "**you** own before trusting the result.",
                )
            with bc2:
                if st.button("Got it", key=f"{prefix}_dismiss_example",
                             width="stretch"):
                    st.session_state[_dismiss_key] = True
                    st.rerun()

        spaces = persistence.list_search_spaces()
        if spaces:
            c1, c2 = st.columns([3, 1])
            with c1:
                sel_s = st.selectbox("Load search space from saved",
                                      ["—"] + spaces, key=f"{prefix}_load_space")
            with c2:
                if st.button("Load", key=f"{prefix}_btn_load_space",
                              width="stretch"):
                    if sel_s != "—":
                        st.session_state[f"{prefix}_space"] = persistence.load_search(sel_s)
                        st.rerun()

        space_default = st.session_state[f"{prefix}_space"]
        try:
            space = _search_space_form(space_default, cfg, is_solo=is_solo_attack)
            st.session_state[f"{prefix}_space"] = space
        except Exception as e:
            st.error(f"Search space invalid: {e}")
            return

        if save_clicked and selected_profile:
            try:
                roster = persistence.load_roster(selected_profile)
                updated_roster = update_roster_from_search_space(roster, space)
                persistence.save_roster(updated_roster, selected_profile)
                st.success(f"Saved your candidate roster to '{selected_profile}'.")
            except Exception as e:
                st.error(f"Failed to save profile '{selected_profile}': {e}")

    with st.expander("Save current setup"):
        c1, c2 = st.columns(2)
        with c1:
            opp_name = st.text_input(f"Save {cfg.opp_word} as", value=opponent.label,
                                      key=f"{prefix}_save_{cfg.opp_tag}_name")
            if st.button(f"Save {cfg.opp_word}", key=f"{prefix}_save_{cfg.opp_tag}"):
                persistence.save_profile(opponent, opp_name)
                st.success(f"Saved profile {opp_name!r}")
        with c2:
            sp_name = st.text_input("Save search space as", value=cfg.save_sp_default,
                                     key=f"{prefix}_save_sp_name")
            if st.button("Save search space", key=f"{prefix}_save_sp"):
                persistence.save_search(space, sp_name)
                st.success(f"Saved search space {sp_name!r}")
        render_session_loss_note(f"{prefix}_savesetup")

    n_total = count_candidates(space)
    st.markdown(f"**Search space size:** {n_total:,} candidates")
    if n_total == 0:
        st.warning("Search space is empty. Pick at least one mythic per class.")
        return

    if n_total > MAX_SEARCH_SIZE:
        st.error(
            f"**Too many candidates** ({n_total:,}). The public server is "
            f"capped at **{MAX_SEARCH_SIZE:,}** to keep RAM under 1 GB. "
            f"Try one of: ↑ raise the ratio step (0.20 or 0.25), "
            f"↓ trim your mythic leader list, or ↓ reduce the joiner pool."
        )
        return

    components.render_section_label("Run the search", num=3)

    top_k = st.number_input("Top to show", 1, 50, 10, key=f"{prefix}_topk",
                            help=cfg.topk_help)

    adv_open = st.session_state.get(f"{prefix}_adv_opts_open", False)
    with st.expander("Advanced search options", expanded=adv_open):
        cols = st.columns(2)
        with cols[0]:
            quick_mode = st.checkbox("Quick search", value=True,
                                     key=f"{prefix}_quick",
                                     help="Skip Monte Carlo refinement: "
                                          "5-10× faster, but no confidence interval.")
        with cols[1]:
            screen_top_n = st.number_input("Refine top N", top_k, 200, 50,
                                           key=f"{prefix}_screen",
                                           help="How many candidates to refine. "
                                                "More = more accurate.")
        cols2 = st.columns(2)
        with cols2[0]:
            if quick_mode:
                st.caption("Quick mode on. No Monte Carlo trials.")
                mc_trials = 0
            else:
                mc_trials = st.number_input("Accuracy (trials)", 50, 5000, 100,
                                            step=50, key=f"{prefix}_trials",
                                            help="Number of stochastic simulations. "
                                                 "100 is a good speed/accuracy balance.")
        with cols2[1]:
            seed = st.number_input("Seed", 0, 2**31 - 1, 0, key=f"{prefix}_seed",
                                   help="For reproducible randomness.")
    st.session_state[f"{prefix}_adv_opts_open"] = not quick_mode
    use_batch = True

    job: SearchJob = st.session_state.setdefault(job_key, SearchJob())

    if job.phase in ("queued", "running"):
        render_running_panel(job, cancel_key=cancel_key)
        return

    if job.phase == "done":
        status = job.result_status
        payload = job.result_payload
        if status == "ok":
            st.session_state[f"{prefix}_last_report"] = payload
            st.session_state[cfg.last_label_key] = opponent.label
            st.session_state[f"{prefix}_scroll_to_results"] = True
        elif status == "cancelled":
            if payload is not None and getattr(payload, "top_k", None):
                st.session_state[f"{prefix}_last_report"] = payload
                st.session_state[cfg.last_label_key] = opponent.label
                st.session_state[f"{prefix}_scroll_to_results"] = True
                st.warning(
                    "Search cancelled before completion. Showing the "
                    "best results found so far."
                )
            else:
                st.info("Search cancelled. No results to show yet.")
        elif status == "error":
            st.error(f"Search failed: {payload}")
        st.session_state[job_key] = SearchJob()

    run_clicked = st.button("Run search", type="primary", key=f"{prefix}_run",
                              width="stretch")
    if run_clicked:
        start_search(
            job=st.session_state[job_key],
            work_fn=cfg.work_fn,
            work_kwargs={
                cfg.opp_kwarg: opponent,
                "space": space,
                "top_k": int(top_k),
                "screen_top_n": int(screen_top_n),
                "mc_trials": int(mc_trials),
                "mc_seed": int(seed),
                "use_batched_screen": use_batch,
                "is_solo_attack": is_solo_attack,
            },
            n_total=n_total,
        )
        st.rerun()

    report = st.session_state.get(f"{prefix}_last_report")
    if report is None:
        return
    mode_lbl = "quick" if (report.top_k and report.top_k[0].mc is None) else "full"
    st.success(
        f"Done in {report.elapsed_s:.1f}s · "
        f"{report.n_screened:,} {cfg.tested_noun} tested · {mode_lbl} mode "
        f"(vs {st.session_state.get(cfg.last_label_key, opponent.label)})"
    )
    _render_top_k(cfg, report)

    if st.session_state.pop(f"{prefix}_scroll_to_results", False):
        components.scroll_to_anchor(cfg.results_anchor)


def _search_space_form(default: SearchSpace, cfg: _ModeCfg,
                        is_solo: bool = False) -> SearchSpace:
    from kingshot_sim.webui.easy_mode_form import (
        searchspace_easy_import_render,
        searchspace_easy_import_complete,
        searchspace_easy_import_rally_flag,
        searchspace_easy_import_reset,
        _scroll_to,
    )

    sp = cfg.sp_prefix

    toggle_key = f"{sp}_input_mode"
    current = st.session_state.get(toggle_key, "Easy")
    mode = st.radio(
        "Setup helper for account bonuses + buffs",
        ["From screenshot (Easy)", "Manual entry (Advanced)"],
        index=0 if current.startswith("From") or current == "Easy" else 1,
        horizontal=True,
        key=f"{toggle_key}_radio",
        help=(
            "Easy: upload a battle-report screenshot, walk a short quiz, "
            "and we peel your account-wide bonuses + buffs into the panels "
            "below. Advanced: enter everything by hand."
        ),
    )
    st.session_state[toggle_key] = "Easy" if mode.startswith("From") else "Advanced"
    is_easy = mode.startswith("From")
    quiz_done = searchspace_easy_import_complete(sp)

    if is_easy and not quiz_done:
        searchspace_easy_import_render(
            default_bv=default.bonuses,
            default_buffs=default.buffs,
            key_prefix=sp,
            side=cfg.roster_form_side,
            bonuses_widget_prefix=f"{sp}_bonus",
            buffs_widget_prefix=f"{sp}_buffs",
        )
        return default

    if is_easy and quiz_done:
        banner_anchor = f"{sp}_post_import_banner"
        st.markdown(f'<a id="{banner_anchor}"></a>', unsafe_allow_html=True)
        c1, c2 = st.columns([5, 1])
        with c1:
            st.success(
                "Imported from screenshot. Your bonuses & buffs are filled "
                "in under **Advanced setup** below (opened automatically after "
                "an import). Review or tweak them there."
            )
        with c2:
            if st.button("Re-import", key=f"{sp}_reimport",
                           width="stretch",
                           help="Discard the imported values and run the quiz again."):
                searchspace_easy_import_reset(sp)
                st.rerun()
        if not cfg.is_defense:
            was_rally = searchspace_easy_import_rally_flag(sp)
            if was_rally is not None:
                new_is_solo = not was_rally
                if st.session_state.get(f"{cfg.prefix}_is_solo_attack") != new_is_solo:
                    st.session_state[f"{cfg.prefix}_is_solo_attack"] = new_is_solo
                is_solo = new_is_solo
        if st.session_state.pop(f"{sp}_ss_scroll_to_banner", False):
            _scroll_to(banner_anchor)


    max_gen = st.slider(
        "Max generation",
        min_value=1, max_value=MAX_GENERATION, value=MAX_GENERATION,
        key=f"{sp}_maxgen",
        help="Choosing Gen 3 keeps Gen 1, 2, 3. Filters the mythic leader and "
             "joiner pickers. Epic joiners are always available.",
    )
    inf_options = tuple(h for h in _INF_MYTHICS if HERO_GENERATION.get(h, 99) <= max_gen)
    cav_options = tuple(h for h in _CAV_MYTHICS if HERO_GENERATION.get(h, 99) <= max_gen)
    arc_options = tuple(h for h in _ARC_MYTHICS if HERO_GENERATION.get(h, 99) <= max_gen)
    joiner_options = tuple(
        h for h in _JOINER_HEROES
        if (h not in HERO_GENERATION) or (HERO_GENERATION[h] <= max_gen)
    )

    render_roster_import(sp, inf_options, cav_options, arc_options, joiner_options)

    st.caption("Pick the mythic leaders you own, per class.")
    c1, c2, c3 = st.columns(3)
    with c1:
        inf = st.multiselect("Inf mythics", inf_options,
                              default=[h for h in default.available_mythic_inf if h in inf_options],
                              key=f"{sp}_inf")
    with c2:
        cav = st.multiselect("Cav mythics", cav_options,
                              default=[h for h in default.available_mythic_cav if h in cav_options],
                              key=f"{sp}_cav")
    with c3:
        arc = st.multiselect("Arc mythics", arc_options,
                              default=[h for h in default.available_mythic_arc if h in arc_options],
                              key=f"{sp}_arc")
    selected_mythics = tuple(inf) + tuple(cav) + tuple(arc)

    from kingshot_sim.webui.forms import leader_specs_editor, class_gear_editor

    solo_attack = (not cfg.is_defense) and is_solo
    show_adv = st.toggle(
        "Advanced setup. Widget & gear levels, joiners, troops, buffs",
        value=st.session_state.get(f"{sp}_show_adv", is_easy and quiz_done),
        key=f"{sp}_show_adv",
        help="Off: we use your saved gear / troops / buffs. Good defaults for a "
             "quick answer. On: fine-tune every input.",
    )

    if show_adv:
        with st.expander("Per-mythic widget level & gear contribution", expanded=False):
            leader_specs = leader_specs_editor(
                selected_heroes=selected_mythics,
                current_specs=default.leader_specs,
                key_prefix=f"{sp}_lspec",
                default_widget=default.leader_widget_level,
                default_level=default.leader_level,
            )

        render_gear_roster_import(f"{sp}_classgear")
        with st.expander("Per-class gear", expanded=False):
            st.caption(
                "Set the 4 gear pieces (head/chest/gloves/boots) once per class. "
                "Every mythic leader of that class will be equipped with this set."
            )
            class_gear = class_gear_editor(
                default=default.class_gear,
                key_prefix=f"{sp}_classgear",
            )

        if solo_attack:
            joiners: list[str] = []
            st.info(
                "Solo march mode is on. The joiner pool is hidden because "
                "solo attackers can't bring joiners. Switch back to Rally in §2 "
                "to bring them back."
            )
        else:
            with st.expander("Joiner pool", expanded=False):
                joiners = st.multiselect("Available joiners (mythic + epic)",
                                          joiner_options,
                                          default=[h for h in default.available_joiners if h in joiner_options],
                                          key=f"{sp}_joiners",
                                          help="Identical-skill heroes are auto-deduplicated (Chenko = Yeonwoo).")

        with st.expander("Troop pool & ratio grid", expanded=False):
            _cur_t, _cur_tg = parse_tier_label(default.troop_pool.infantry_tier)
            _cur_lvl = (default.troop_pool.infantry_level
                        if default.troop_pool.infantry_level is not None else float(_cur_t))
            _tg_opts = _troop_tg_options()
            cols = st.columns(4)
            with cols[0]:
                march_cap = st.number_input("March cap", 10_000, 5_000_000,
                                              default.troop_pool.march_cap, step=10_000,
                                              key=f"{sp}_march")
            with cols[1]:
                level = st.number_input("Troop level", min_value=1.0,
                                          max_value=float(_troop_max_tier()),
                                          value=float(_cur_lvl), step=0.1, format="%.1f",
                                          key=f"{sp}_level",
                                          help="Your troops' level, e.g. 9.9. Decimals "
                                                 "interpolate between tiers (D-61).")
            with cols[2]:
                tg = st.selectbox("TrueGold", _tg_opts,
                                    index=_tg_opts.index(_cur_tg) if _cur_tg in _tg_opts else 0,
                                    format_func=lambda g: "—" if g == 0 else f"TG{g}",
                                    key=f"{sp}_tg")
            with cols[3]:
                _step_default = max(0.10, default.troop_ratio_step)
                step = st.select_slider("Ratio step", [0.10, 0.20, 0.25],
                                          value=_step_default, key=f"{sp}_step",
                                          help="Granularity of the troop ratio grid. "
                                                 "Smaller = more compositions tested but more memory & time.")
            tier, pool_level = pool_tier_from_inputs(float(level), int(tg))

            cols2 = st.columns(2)
            with cols2[0]:
                if solo_attack:
                    n_joiners = 0
                    st.caption("Joiner slots: **0** (solo)")
                else:
                    n_joiners = st.slider("Joiner slots", 0, 4, default.n_joiners,
                                           key=f"{sp}_njoiners")
            with cols2[1]:
                min_inf = st.slider("Min Infantry %", 0.0, 1.0, default.min_inf_pct,
                                      step=0.05, key=f"{sp}_mininf")

        with st.expander("Account stat bonuses (constant across candidates)",
                           expanded=False):
            bonuses = bonuses_form(default.bonuses, key_prefix=f"{sp}_bonus")

        with st.expander("Your buffs (city + pets + appointments)",
                           expanded=False):
            buffs = buffs_form(default.buffs, key_prefix=f"{sp}_buffs")
    else:
        leader_specs = default.leader_specs
        class_gear = default.class_gear
        _cur_t, _cur_tg = parse_tier_label(default.troop_pool.infantry_tier)
        _cur_lvl = (default.troop_pool.infantry_level
                    if default.troop_pool.infantry_level is not None else float(_cur_t))
        tier, pool_level = pool_tier_from_inputs(float(_cur_lvl), int(_cur_tg))
        march_cap = default.troop_pool.march_cap
        step = float(max(0.10, default.troop_ratio_step))
        min_inf = default.min_inf_pct
        if solo_attack:
            joiners = []
            n_joiners = 0
        else:
            joiners = [h for h in default.available_joiners if h in joiner_options]
            n_joiners = default.n_joiners
        bonuses = default.bonuses
        buffs = default.buffs
        st.caption(
            "Using your saved gear, troops, joiners, bonuses & buffs. "
            "Tick **Advanced setup** above to fine-tune them."
        )

    return SearchSpace(
        available_mythic_inf=inf,
        available_mythic_cav=cav,
        available_mythic_arc=arc,
        available_joiners=joiners,
        troop_pool=TroopPool(infantry_tier=tier, cavalry_tier=tier,
                              archer_tier=tier, march_cap=int(march_cap),
                              infantry_level=pool_level, cavalry_level=pool_level,
                              archer_level=pool_level),
        troop_ratio_step=float(step),
        min_inf_pct=float(min_inf),
        n_joiners=int(n_joiners),
        bonuses=bonuses,
        leader_level=default.leader_level,
        leader_widget_level=default.leader_widget_level,
        joiner_level=default.joiner_level,
        label_prefix=default.label_prefix,
        leader_specs=leader_specs,
        class_gear=class_gear,
        buffs=buffs,
    )


def _banner_trio_html(cand) -> str:
    parts = []
    for hero, cls in (
        (cand.leader_inf.hero_name, "Inf"),
        (cand.leader_cav.hero_name, "Cav"),
        (cand.leader_arc.hero_name, "Arc"),
    ):
        if not hero:
            continue
        parts.append(
            '<div style="display:flex;flex-direction:column;align-items:center;'
            'gap:4px;">'
            + components.hero_portrait_html(hero, size=50, cls=cls)
            + f'<span style="font-size:11px;color:var(--ks-text-muted);">{hero}</span>'
            '</div>'
        )
    return f'<div style="display:flex;gap:10px;">{"".join(parts)}</div>'


def _recommendation_html(cfg: _ModeCfg, score_val: float,
                         win_pct: float | None,
                         margin_to_next: float | None) -> str:
    is_def = cfg.is_defense
    verb = "holds" if is_def else "wins"
    rel = (f"{verb} <b>{win_pct:.0%}</b> of simulations" if win_pct is not None
           else f"{verb} on expected value")
    if score_val >= 0.15:
        if is_def:
            lead = "Rock-solid hold" if score_val >= 0.50 else "Solid hold"
        else:
            lead = "Decisive break" if score_val >= 0.50 else "Clear win"
        gap = (f", clear of the runner-up by {margin_to_next:.2f}"
               if margin_to_next is not None and margin_to_next >= 0.01 else "")
        return f"{lead}. {rel}{gap}."
    if score_val >= -0.15:
        return (f"Within coin-flip noise. {rel}, and nothing in your roster "
                f"pulls clear; it comes down to execution and RNG.")
    threat = "This rally gets through" if is_def else "Nothing here breaks it"
    best = (f"best {'hold' if is_def else 'result'} is <b>{win_pct:.0%}</b>"
            if win_pct is not None else "even the top option falls short")
    return f"{threat}. {best}. You need more development or troops."


def _render_answer_banner(cfg: _ModeCfg, report) -> None:
    if not report.top_k:
        return
    best = report.top_k[0]
    cand = getattr(best, cfg.entry_attr)
    has_mc = best.mc is not None

    def _disp(entry) -> float:
        s = entry.mc.score_median if has_mc else entry.expected_score
        return -s if cfg.is_defense else s

    score_val = _disp(best)

    if cfg.is_defense:
        win_pct = (1.0 - best.mc.win_rate_attacker) if has_mc else None
        score_label, win_label = "Defense score", "Hold rate"
    else:
        win_pct = best.mc.win_rate_attacker if has_mc else None
        score_label, win_label = "Battle score", "Win rate"

    _, _, color = components.score_verdict(score_val)
    stats = [{"label": score_label, "value": f"{score_val:+.2f}", "color": color}]
    if win_pct is not None:
        n = len(best.mc.scores) if getattr(best.mc, "scores", None) else 0
        sub = f"across {n:,} sims" if n else "Monte-Carlo refine"
        stats.append({"label": win_label, "value": f"{win_pct:.0%}", "sub": sub})
    else:
        stats[0]["sub"] = "expected value (no RNG)"

    components.render_result_summary(
        eyebrow=("Your best defense" if cfg.is_defense else "Your best counter"),
        score=score_val,
        stats=stats,
        trio_html=_banner_trio_html(cand),
    )


def _render_assumptions_expander(cfg: _ModeCfg, report, has_mc: bool) -> None:
    space = st.session_state.get(f"{cfg.prefix}_space")
    march = getattr(getattr(space, "troop_pool", None), "march_cap", None)
    march_txt = (f"<code>{march:,}</code> troops" if isinstance(march, int)
                 else "the march cap you set")
    best = report.top_k[0] if report.top_k else None
    n_iter = len(best.mc.scores) if (best and getattr(best.mc, "scores", None)) else 0
    if has_mc:
        mc_line = (
            f"Each ranked comp is refined with a Monte-Carlo run"
            + (f" of <code>{n_iter:,}</code> iterations" if n_iter else "")
            + "; the win rate is the fraction of fights it won."
        )
    else:
        mc_line = ("This is a fast expected-value screen. No Monte-Carlo, so "
                   "no win rate or interval. Run a full search for those.")
    side = "defending roster" if cfg.is_defense else "marching trio"
    with st.expander("Assumptions behind these numbers", expanded=False):
        st.markdown(
            f"- March cap {march_txt}, split across classes by the troop ratio "
            f"under test.\n"
            f"- Bonuses are read from the setups you entered. No hidden buffs "
            f"are assumed on either side.\n"
            f"- {mc_line}\n"
            f"- Hero passives count only when the hero is in the {side} "
            f"(joiners contribute their first skill + troops only).",
            unsafe_allow_html=True,
        )


def _render_top_k(cfg: _ModeCfg, report) -> None:
    prefix = cfg.prefix
    is_def = cfg.is_defense

    st.markdown(
        f'<div id="{cfg.results_anchor}" style="position:relative;top:-20px;"></div>',
        unsafe_allow_html=True,
    )
    components.render_section_label("Results", num=4)

    _render_answer_banner(cfg, report)

    opp_label = getattr(report, cfg.opp_label_attr)
    st.markdown(
        f"##### Ranked {cfg.results_noun} · "
        f"<span style='color:var(--ks-text-muted);font-weight:400;'>top "
        f"{len(report.top_k)} vs "
        f"<strong style='color:var(--ks-text);'>{html.escape(str(opp_label))}</strong></span>",
        unsafe_allow_html=True,
    )
    st.caption("Every comp we tested, best to worst. Expand a candidate below "
               "for the full breakdown.")

    has_mc = report.top_k and report.top_k[0].mc is not None

    entries = list(report.top_k)
    if has_mc:
        c_radio, c_note = st.columns([2, 3])
        with c_radio:
            ranking_mode = st.radio(
                "Rank by",
                ["Battle score", "Win rate"],
                index=0,
                horizontal=True,
                key=f"{prefix}_ranking_mode",
                help="Switches the sort key of the table below.",
            )
        with c_note:
            with st.expander("Which one should I use?", expanded=False):
                st.markdown(
                    "- **Battle score (margin)**. More RNG-driven; favours "
                    "double / triple rally setups, or when you're the underdog "
                    "and chasing a high-variance blowout.\n"
                    "- **Win rate**. Smaller wins but far more consistent. "
                    "Best when you already have an edge and want to keep it."
                )
        if is_def:
            if ranking_mode == "Win rate":
                entries.sort(key=lambda e: (e.mc.win_rate_attacker, e.mc.score_median))
            else:
                entries.sort(key=lambda e: (e.mc.score_median, e.mc.win_rate_attacker))
        else:
            if ranking_mode == "Win rate":
                entries.sort(key=lambda e: (-e.mc.win_rate_attacker, -e.mc.score_median))
            else:
                entries.sort(key=lambda e: (-e.mc.score_median, -e.mc.win_rate_attacker))
        for i, e in enumerate(entries, start=1):
            e.rank = i

    rows_html: list[str] = []
    cards_html: list[str] = []
    for e in entries:
        cand = getattr(e, cfg.entry_attr)
        inf_n = sum(g.count for g in cand.troops.infantry)
        cav_n = sum(g.count for g in cand.troops.cavalry)
        arc_n = sum(g.count for g in cand.troops.archer)
        total = max(inf_n + cav_n + arc_n, 1)
        split = (inf_n / total, cav_n / total, arc_n / total)

        if is_def:
            if has_mc:
                score_val = -e.mc.score_median
                ci_lo, ci_hi = -e.mc.score_ic95_high, -e.mc.score_ic95_low
                defender_win = 1.0 - e.mc.win_rate_attacker
                score_bar = components.score_bar_html(score_val, ci_lo, ci_hi, width=140)
                score_bar_fluid = components.score_bar_html(score_val, ci_lo, ci_hi, width="100%")
                win_html = (
                    f'<div style="font-size:13px;color:var(--ks-text);'
                    f'font-family:\'JetBrains Mono\',monospace;font-weight:500;">'
                    f'{defender_win:.0%}</div>'
                    f'<div style="font-size:11px;color:var(--ks-text-faint);margin-top:2px;">'
                    f'defender win</div>'
                )
            else:
                score_val = -e.expected_score
                score_bar = components.score_bar_html(score_val, width=140)
                score_bar_fluid = components.score_bar_html(score_val, width="100%")
                win_html = '<div style="font-size:12px;color:var(--ks-text-faint);">Quick mode</div>'
        else:
            if has_mc:
                score_val = e.mc.score_median
                score_bar = components.score_bar_html(
                    score_val, e.mc.score_ic95_low, e.mc.score_ic95_high, width=140)
                score_bar_fluid = components.score_bar_html(
                    score_val, e.mc.score_ic95_low, e.mc.score_ic95_high, width="100%")
                win_html = (
                    f'<div style="font-size:13px;color:var(--ks-text);'
                    f'font-family:\'JetBrains Mono\',monospace;font-weight:500;">'
                    f'{e.mc.win_rate_attacker:.0%}</div>'
                    f'<div style="font-size:11px;color:var(--ks-text-faint);margin-top:2px;">win rate</div>'
                )
            else:
                score_val = e.expected_score
                score_bar = components.score_bar_html(score_val, width=140)
                score_bar_fluid = components.score_bar_html(score_val, width="100%")
                win_html = '<div style="font-size:12px;color:var(--ks-text-faint);">Quick mode</div>'

        score_str = f"{score_val:+.4f}"
        verdict_pill = components.score_verdict_html(score_val)

        trio_html = "".join(
            f'<div style="margin-bottom:4px;">'
            f'{components.portrait_name_html(h, c, size=26)}</div>'
            for h, c in (
                (cand.leader_inf.hero_name, "Inf"),
                (cand.leader_cav.hero_name, "Cav"),
                (cand.leader_arc.hero_name, "Arc"),
            )
        )
        split_html = components.split_bar_html(split, height=8, show_labels=True)
        joiners_html = "".join(components.multi_pill_html(j.hero_name) for j in cand.joiners)
        joiners_card = "".join(
            f'<span style="margin:0 8px 4px 0;">'
            f'{components.portrait_name_html(j.hero_name, None, size=20, font_size=12)}</span>'
            for j in cand.joiners
        ) or '<span style="color:var(--ks-text-faint);font-size:12px;">no joiners</span>'

        rank_color = "var(--ks-accent)" if e.rank <= 3 else "var(--ks-text-muted)"
        rows_html.append(
            f'<tr style="border-top:1px solid var(--ks-border);">'
            f'<td style="padding:14px 12px;font-size:18px;font-weight:700;'
            f'color:{rank_color};font-family:\'JetBrains Mono\',monospace;'
            f'vertical-align:top;width:48px;">#{e.rank}</td>'
            f'<td style="padding:14px 12px;vertical-align:top;min-width:180px;">'
            f'<div style="margin-bottom:6px;">{verdict_pill}</div>'
            f'<div style="font-size:15px;font-weight:600;color:var(--ks-text);'
            f'font-family:\'JetBrains Mono\',monospace;margin-bottom:5px;">{score_str}</div>'
            f'{score_bar}</td>'
            f'<td style="padding:14px 12px;vertical-align:top;min-width:90px;">{win_html}</td>'
            f'<td style="padding:14px 12px;vertical-align:top;">{trio_html}</td>'
            f'<td style="padding:14px 12px;vertical-align:top;min-width:160px;">{split_html}</td>'
            f'<td style="padding:14px 12px;vertical-align:top;">'
            f'<div style="display:flex;flex-wrap:wrap;">{joiners_html}</div></td>'
            f'</tr>'
        )

        cards_html.append(
            f'<div style="border:1px solid var(--ks-border);border-radius:10px;'
            f'background:var(--ks-surface);box-shadow:var(--ks-shadow);'
            f'padding:14px 16px;margin-bottom:12px;">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'margin-bottom:8px;">'
            f'<span style="font-size:17px;font-weight:700;color:{rank_color};'
            f'font-family:\'JetBrains Mono\',monospace;">#{e.rank}</span>'
            f'{verdict_pill}</div>'
            f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px;">'
            f'<span style="font-size:15px;font-weight:600;color:var(--ks-text);'
            f'font-family:\'JetBrains Mono\',monospace;">{score_str}</span>'
            f'<span style="font-size:12px;color:var(--ks-text-muted);">{win_html}</span></div>'
            f'<div style="margin:6px 0 10px;">{score_bar_fluid}</div>'
            f'<div style="margin-bottom:8px;">{trio_html}</div>'
            f'<div style="margin-bottom:8px;">{split_html}</div>'
            f'<div style="display:flex;flex-wrap:wrap;align-items:center;">{joiners_card}</div>'
            f'</div>'
        )

    win_header = cfg.win_col_label if has_mc else "Mode"
    table_html = (
        '<div class="ks-topk-table" style="background:var(--ks-surface);'
        'border:1px solid var(--ks-border);'
        'border-radius:8px;box-shadow:0 0 0 1px rgba(10,37,64,0.06),0 1px 3px rgba(10,37,64,0.04);'
        'overflow-x:auto;-webkit-overflow-scrolling:touch;margin-top:14px;">'
        '<table style="width:100%;border-collapse:collapse;min-width:760px;">'
        '<thead><tr style="background:var(--ks-surface-alt);">'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">#</th>'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        f'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">{cfg.score_col_label}</th>'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        f'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">{win_header}</th>'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">Trio</th>'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">Troop split</th>'
        '<th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:600;'
        'letter-spacing:0.06em;text-transform:uppercase;color:var(--ks-text-muted);">Joiners</th>'
        '</tr></thead><tbody>' + "".join(rows_html) + '</tbody></table></div>'
    )
    cards_block = (
        '<div class="ks-topk-cards" style="margin-top:14px;">'
        + "".join(cards_html) + '</div>'
    )
    st.markdown(table_html + cards_block, unsafe_allow_html=True)

    _render_assumptions_expander(cfg, report, has_mc)
    components.render_score_formula_expander()

    st.markdown("")
    st.markdown("##### Drill into a candidate")
    rank_idx = st.selectbox("Pick rank", [e.rank for e in entries], key=f"{prefix}_drill")
    chosen = next(e for e in entries if e.rank == rank_idx)
    cand = getattr(chosen, cfg.entry_attr)
    opponent = st.session_state.get(cfg.opp_session_key)
    is_solo = bool(st.session_state.get(f"{prefix}_is_solo_attack", False))
    with st.expander(f"Details for #{chosen.rank}", expanded=True):
        c1, c2, c3 = st.columns(3)
        if is_def:
            if chosen.mc is not None:
                c1.metric("Defense score", f"{-chosen.mc.score_median:+.4f}")
                c2.metric("Mean (flipped)", f"{-chosen.mc.score_mean:+.4f}")
                c3.metric("Std dev", f"{chosen.mc.score_std:.4f}")
            else:
                c1.metric("Defense score (Quick)", f"{-chosen.expected_score:+.4f}")
                c2.metric("Mode", "Quick search")
                c3.metric("Trials", "—")
        else:
            if chosen.mc is not None:
                c1.metric("Median score", f"{chosen.mc.score_median:+.4f}")
                c2.metric("Mean score",   f"{chosen.mc.score_mean:+.4f}")
                c3.metric("Std dev",      f"{chosen.mc.score_std:.4f}")
            else:
                c1.metric("Score (Quick)", f"{chosen.expected_score:+.4f}")
                c2.metric("Mode", "Quick search")
                c3.metric("Trials", "—")

        leader_lines = "".join(
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0;">'
            f'{components.portrait_name_html(h.hero_name, c, size=30, font_size=14)}'
            f'<span style="color:var(--ks-text-muted);font-size:12.5px;">'
            f'★{h.level} · W{h.widget_level}</span></div>'
            for h, c in ((cand.leader_inf, "Inf"), (cand.leader_cav, "Cav"),
                         (cand.leader_arc, "Arc"))
        )
        st.markdown(
            '<div style="font-size:11px;font-weight:600;letter-spacing:0.06em;'
            'text-transform:uppercase;color:var(--ks-text-muted);margin:8px 0 4px;">'
            'Leaders</div>' + leader_lines,
            unsafe_allow_html=True,
        )
        if cand.joiners:
            joiner_strip = "".join(
                f'<span style="margin:0 10px 4px 0;">'
                f'{components.portrait_name_html(j.hero_name, None, size=24, font_size=13)}'
                f'</span>' for j in cand.joiners
            )
            st.markdown(
                '<div style="font-size:11px;font-weight:600;letter-spacing:0.06em;'
                'text-transform:uppercase;color:var(--ks-text-muted);margin:10px 0 4px;">'
                'Joiners</div>'
                f'<div style="display:flex;flex-wrap:wrap;align-items:center;">'
                f'{joiner_strip}</div>',
                unsafe_allow_html=True,
            )

        h1, h2, h3 = st.columns(3)
        with h1:
            st.button("Open in Quick Fight", key=f"{prefix}_to_qf",
                      width="stretch", disabled=opponent is None,
                      help="Send this matchup to Quick Fight, both sides pre-filled.",
                      on_click=_handoff_to,
                      args=("quick_fight", "qf_attacker", "qf_defender",
                            cand, opponent),
                      kwargs={"is_def": is_def, "is_solo": is_solo})
        with h2:
            st.button("Test in Sensitivity", key=f"{prefix}_to_sn",
                      width="stretch", disabled=opponent is None,
                      help="Send this matchup to Sensitivity to sweep one lever.",
                      on_click=_handoff_to,
                      args=("sensitivity", "sn_attacker", "sn_defender",
                            cand, opponent),
                      kwargs={"is_def": is_def, "is_solo": is_solo})
        with h3:
            if st.button("Save as profile", key=f"{prefix}_drill_save",
                         width="stretch"):
                persistence.save_profile(
                    cand, f"{cfg.drill_save_prefix}{chosen.rank}_{cand.label}"[:50])
                st.success("Saved to profiles.")
        render_session_loss_note(f"{prefix}_drill")
