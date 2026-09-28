from __future__ import annotations
import streamlit as st

from kingshot_sim.webui import components, runtime_stats, search_runner, persistence
from kingshot_sim.io_pkg.roster_bridge import (
    apply_roster_to_benchmark,
    extract_roster_from_benchmark,
)
from kingshot_sim.benchmark.runner import (
    BenchSettings, HeroBuild, rank_generation,
)
from kingshot_sim.benchmark.reference import CASH_ONLY_HEROES
from kingshot_sim.benchmark.advisor import simulate, advise_from_passes, best_per_class_trio
from kingshot_sim.benchmark.economy import F2P_SHARDS_PER_GEN
from kingshot_sim.data.reference import (
    hero_class, heroes_up_to_generation, MAX_GENERATION, EPIC_HEROES, VALID_LEVELS,
)
from kingshot_sim.io_pkg.rosters import (
    BenchmarkRoster,
    roster_to_json,
    roster_from_json,
    _safe_star_subtier_from_level,
)

def _code(star: int, tier: int) -> str:
    return "MAX" if int(star) >= 5 else f"{int(star)}_{int(tier)}"


def _extract_roster_from_session(
    name: str,
    gen: int,
    builds: dict[str, HeroBuild],
    owned: dict[str, list[str]],
) -> BenchmarkRoster:
    from kingshot_sim.data.reference import HERO_GENERATION

    master_owned = st.session_state.get("_bm_master_owned", {})
    clean_owned: dict[str, list[str]] = {}
    if master_owned and any(master_owned.values()):
        for c in ("Inf", "Cav", "Arc"):
            combined = list(master_owned.get(c, []))
            if owned and c in owned:
                for h in owned[c]:
                    if h not in combined:
                        combined.append(h)
            clean_owned[c] = combined
    else:
        clean_owned = {c: list(h_list) for c, h_list in owned.items()} if owned else {}
        if not any(clean_owned.values()):
            clean_owned = {
                c: list(st.session_state.get(f"_bm_own_{c}", []))
                for c in ("Inf", "Cav", "Arc")
                if st.session_state.get(f"_bm_own_{c}")
            }

    master_builds = st.session_state.setdefault("_bm_master_builds", {})
    b_copy = dict(master_builds)
    if builds:
        b_copy.update(builds)

    for cls, h_list in clean_owned.items():
        for h in h_list:
            if f"_bm_star_{h}" in st.session_state and (not builds or h not in builds):
                star = st.session_state[f"_bm_star_{h}"]
                tier = st.session_state.get(f"_bm_tier_{h}", 0)
                wl = 0 if h in EPIC_HEROES else st.session_state.get(f"_bm_wl_{h}", _WIDGET_DEFAULT)
                h_build = HeroBuild(level=_code(star, tier), widget_level=int(wl))
                b_copy[h] = h_build
                master_builds[h] = h_build
            elif h not in b_copy:
                star = st.session_state.get(f"_bm_star_{h}", _STAR_DEFAULT)
                tier = st.session_state.get(f"_bm_tier_{h}", 0)
                wl = 0 if h in EPIC_HEROES else st.session_state.get(f"_bm_wl_{h}", _WIDGET_DEFAULT)
                h_build = HeroBuild(level=_code(star, tier), widget_level=int(wl))
                b_copy[h] = h_build
                master_builds[h] = h_build

    master_gen = st.session_state.get("_bm_master_gen")
    roster_gen = max(master_gen, gen) if master_gen is not None else gen
    highest_hero_gen = max(
        (HERO_GENERATION.get(h, 1) for h_list in clean_owned.values() for h in h_list),
        default=1,
    )
    final_gen = max(roster_gen, highest_hero_gen)

    return BenchmarkRoster(
        name=name,
        generation=final_gen,
        owned_heroes=clean_owned,
        builds=b_copy,
    )


def _load_roster_into_session(roster: BenchmarkRoster) -> None:
    st.session_state["_bm_active_roster"] = persistence._safe_name(roster.name)
    st.session_state["_bm_master_gen"] = roster.generation
    st.session_state["_bm_pending_gen"] = roster.generation
    try:
        st.session_state["_bm_gen"] = roster.generation
    except Exception:
        pass
    st.session_state["_bm_last_gen"] = roster.generation

    master_owned = {c: list(roster.owned_heroes.get(c, [])) for c in ("Inf", "Cav", "Arc")}
    st.session_state["_bm_master_owned"] = master_owned
    for cls in ("Inf", "Cav", "Arc"):
        st.session_state[f"_bm_own_{cls}"] = list(master_owned[cls])

    master_builds: dict[str, HeroBuild] = dict(roster.builds)
    st.session_state["_bm_master_builds"] = master_builds
    for h, b in roster.builds.items():
        star, tier = _safe_star_subtier_from_level(b.level)
        st.session_state[f"_bm_star_{h}"] = int(star)
        st.session_state[f"_bm_tier_{h}"] = int(tier)
        st.session_state[f"_bm_wl_{h}"] = int(b.widget_level)

    st.session_state.pop("_bm_result", None)
    st.session_state.pop("_bm_passes_cache", None)


_STAR_DEFAULT = 5
_WIDGET_DEFAULT = 4

_SCENARIOS: list[tuple[str, str]] = [
    ("defense", "Solo defense"),
    ("solo_atk", "Solo attack"),
    ("garrison", "Garrison"),
    ("rally_atk", "Rally lead"),
    ("all_around", "All-around"),
]
_SCEN_LABEL = dict(_SCENARIOS)

_ADVICE: dict[str, str] = {
    "defense": (
        "Your march gets caught defending (no optimised wall). <b>Defensive "
        "widgets are on in solo defense</b>. All-Out, Swordland, Eternity's "
        "Reach, <b>KvK</b>, <b>Vikings</b>. Usually the best F2P focus."
    ),
    "garrison": (
        "You hold an alliance <b>garrison / rally defense</b> behind a real wall. "
        "Rewards mitigation + kill-speed. Matters most if you're the one anchoring "
        "the garrison (a whale or alliance lead). Otherwise defense is closer to "
        "your day-to-day."
    ),
    "solo_atk": (
        "Your own solo march. All-Out, Swordland, Eternity, Alliance "
        "Championship, Trialliance, <b>KvK</b>. <b>Offensive widgets are off in solo</b>, so "
        "an \"offensive\" hero isn't automatically better than a defensive one."
    ),
    "rally_atk": (
        "Leading a rally. Often whale-led. <b>but if you're the whale or the "
        "de-facto rally lead of your alliance, this is your scenario</b>. Also "
        "matters in Bear, which this sim doesn't model well "
        "(<a href='https://frakinator.streamlit.app/' target='_blank' "
        "style='color:var(--ks-accent);'>use Frak's sim</a> for Bear)."
    ),
    "all_around": (
        "The flat mean of all four scenarios. Use it only if you truly split your "
        "time; otherwise read the scenario you actually play."
    ),
}


def _callout(html: str, tone: str = "accent") -> None:
    bg = {"accent": "rgba(99,91,255,0.06)", "warn": "rgba(187,85,4,0.06)",
          "ok": "rgba(22,163,74,0.07)"}[tone]
    bd = {"accent": "rgba(99,91,255,0.25)", "warn": "rgba(187,85,4,0.28)",
          "ok": "rgba(22,163,74,0.30)"}[tone]
    st.markdown(
        f'<div style="background:{bg};border:1px solid {bd};border-radius:8px;'
        f'padding:12px 16px;font-size:13px;line-height:1.6;color:var(--ks-text);'
        f'margin:6px 0 14px;">{html}</div>',
        unsafe_allow_html=True,
    )


def _guarded_run(fn, *, count: bool = True):
    lock = search_runner._global_search_lock()
    runtime_stats.queue_enter()
    acquired = False
    try:
        acquired = lock.acquire()
        runtime_stats.queue_to_running()
        result = fn()
        if count:
            try:
                runtime_stats.increment_total_sims()
                runtime_stats.add_total_battles(int(getattr(result, "n_battles", 0)))
            except Exception:
                pass
        return result
    finally:
        if acquired:
            runtime_stats.queue_exit_running()
            try:
                lock.release()
            except RuntimeError:
                pass
        else:
            runtime_stats.queue_exit_unstarted()


def _ocr_import(gen: int, options_by_cls: dict[str, list[str]]) -> None:
    with st.expander("Import from a screenshot (your Heroes page, sorted by Quality)"):
        st.caption(
            "Open the in-game **Heroes** screen, sort by **Quality**, screenshot "
            "it, and drop it here. We pre-fill the heroes you own + their stars. "
            "Then check/adjust below. Widgets/sub-tiers aren't read; set those "
            "yourself."
        )
        _ex = components._ASSETS_DIR / "easy_mode_roster_owned_example.png"
        if _ex.exists():
            st.image(str(_ex), width=260,
                     caption="Example. The in-game 'Heroes' grid, sorted by Quality")
        up = st.file_uploader("Heroes screenshot", type=["png", "jpg", "jpeg"],
                              key="_bm_ocr_up", label_visibility="collapsed")
        if up is not None and st.button("Read screenshot", type="primary",
                                        key="_bm_ocr_go"):
            from PIL import Image
            from kingshot_sim.easy_mode.ocr_hero_roster import ocr_hero_roster
            try:
                res = ocr_hero_roster(Image.open(up))
            except Exception as e:
                st.error(f"Couldn't read that screenshot: {e}")
                return
            if res.error:
                st.warning(res.error)
                return
            valid = {h for opts in options_by_cls.values() for h in opts}
            picked: dict[str, list[str]] = {c: [] for c in ("Inf", "Cav", "Arc")}
            master_builds = st.session_state.setdefault("_bm_master_builds", {})
            for c in res.cells:
                if c.hero_name in valid and c.klass in picked \
                        and c.hero_name not in picked[c.klass]:
                    picked[c.klass].append(c.hero_name)
                    star = max(0, min(5, int(c.star)))
                    sub = max(0, min(5, int(getattr(c, "sub_tier", 0))))
                    st.session_state[f"_bm_star_{c.hero_name}"] = star
                    st.session_state[f"_bm_tier_{c.hero_name}"] = sub
                    wl = master_builds.get(c.hero_name).widget_level if c.hero_name in master_builds else (0 if c.hero_name in EPIC_HEROES else _WIDGET_DEFAULT)
                    master_builds[c.hero_name] = HeroBuild(level=_code(star, sub), widget_level=int(wl))
            n = sum(len(v) for v in picked.values())
            master_owned = st.session_state.setdefault("_bm_master_owned", {})
            for c in ("Inf", "Cav", "Arc"):
                if picked[c]:
                    st.session_state[f"_bm_own_{c}"] = picked[c]
                    visible_set = set(options_by_cls[c])
                    hidden = [h for h in master_owned.get(c, []) if h not in visible_set]
                    master_owned[c] = list(picked[c]) + hidden
            st.session_state["_bm_ocr_msg"] = (
                f"Pre-filled {n} hero(es) from the screenshot. Confirm below."
                if n else "No known heroes matched. Pick them manually below.")
            st.rerun()
    msg = st.session_state.get("_bm_ocr_msg")
    if msg:
        _callout(f"{msg}", tone="ok")


def _render_roster_manager(
    gen: int,
    builds: dict[str, HeroBuild] | None = None,
    owned: dict[str, list[str]] | None = None,
) -> None:
    roster_msg = st.session_state.pop("_bm_roster_msg", None)
    if roster_msg:
        try:
            st.toast(roster_msg)
        except Exception:
            _callout(roster_msg, tone="ok")

    master_owned = st.session_state.get("_bm_master_owned", {})
    master_builds = st.session_state.get("_bm_master_builds", {})

    if owned is None:
        if master_owned and any(master_owned.values()):
            owned = {c: list(master_owned.get(c, [])) for c in ("Inf", "Cav", "Arc")}
        else:
            owned = {
                c: [h for h in st.session_state.get(f"_bm_own_{c}", []) if hero_class(h) == c]
                for c in ("Inf", "Cav", "Arc")
            }
    if builds is None:
        builds = dict(master_builds)
        for cls, h_list in owned.items():
            for h in h_list:
                if h not in builds:
                    star = st.session_state.get(f"_bm_star_{h}", _STAR_DEFAULT)
                    tier = st.session_state.get(f"_bm_tier_{h}", 0)
                    wl = 0 if h in EPIC_HEROES else st.session_state.get(f"_bm_wl_{h}", _WIDGET_DEFAULT)
                    builds[h] = HeroBuild(level=_code(star, tier), widget_level=int(wl))

    saved_rosters = persistence.list_rosters()
    options = ["[Custom / Unsaved]"] + saved_rosters
    active_roster = st.session_state.get("_bm_active_roster", "[Custom / Unsaved]")
    if active_roster not in options:
        active_roster = "[Custom / Unsaved]"
        st.session_state["_bm_active_roster"] = active_roster

    c_sel, c_save, c_del, c_exp = st.columns([3, 1, 1, 1.2])
    with c_sel:
        idx = options.index(active_roster)
        selected = st.selectbox(
            "Roster",
            options=options,
            index=idx,
            label_visibility="collapsed",
            help="Select a saved roster or customize.",
        )
        if selected != active_roster:
            if selected != "[Custom / Unsaved]":
                safe_name = persistence._safe_name(selected)
                loaded = persistence.load_roster(safe_name)
                _load_roster_into_session(loaded)
                st.session_state["_bm_active_roster"] = safe_name
            else:
                st.session_state["_bm_active_roster"] = "[Custom / Unsaved]"
            st.rerun()

    with c_save:
        if st.button("Save", key="_bm_save_btn", use_container_width=True):
            if active_roster != "[Custom / Unsaved]":
                safe_name = persistence._safe_name(active_roster)
                r = _extract_roster_from_session(safe_name, gen, builds, owned)
                persistence.save_roster(r, safe_name)
                st.session_state["_bm_active_roster"] = safe_name
                st.session_state["_bm_roster_msg"] = f"Saved roster '{safe_name}'."
                st.rerun()
            else:
                st.session_state["_bm_prompt_save_name"] = True
                st.rerun()

    with c_del:
        if st.button("Delete", key="_bm_delete_btn", use_container_width=True,
                     disabled=(active_roster == "[Custom / Unsaved]")):
            if active_roster != "[Custom / Unsaved]":
                persistence.delete_roster(active_roster)
                st.session_state["_bm_active_roster"] = "[Custom / Unsaved]"
                st.session_state["_bm_roster_msg"] = f"Deleted roster '{active_roster}'."
                st.rerun()

    with c_exp:
        current_name = active_roster if active_roster != "[Custom / Unsaved]" else "benchmark_roster"
        export_roster = _extract_roster_from_session(current_name, gen, builds, owned)
        export_json = roster_to_json(export_roster)
        st.download_button(
            "Export JSON",
            data=export_json,
            file_name=f"{current_name}.json",
            mime="application/json",
            key="_bm_export_btn",
            use_container_width=True,
        )

    if st.session_state.get("_bm_prompt_save_name"):
        c_prompt_in, c_prompt_btn, c_prompt_cancel = st.columns([3, 1, 1])
        with c_prompt_in:
            prompt_name = st.text_input("Name for this roster", key="_bm_prompt_name",
                                        label_visibility="collapsed", placeholder="Enter roster name...")
        with c_prompt_btn:
            if st.button("Confirm", key="_bm_prompt_confirm", type="primary", use_container_width=True):
                p_name = prompt_name.strip()
                if not p_name:
                    st.error("Please enter a valid roster name.")
                elif p_name == "[Custom / Unsaved]":
                    st.error("Cannot use reserved name '[Custom / Unsaved]'. Please enter a different name.")
                else:
                    safe_name = persistence._safe_name(p_name)
                    r = _extract_roster_from_session(safe_name, gen, builds, owned)
                    persistence.save_roster(r, safe_name)
                    st.session_state["_bm_active_roster"] = safe_name
                    st.session_state.pop("_bm_prompt_save_name", None)
                    st.session_state["_bm_roster_msg"] = f"Saved roster '{safe_name}'."
                    st.rerun()
        with c_prompt_cancel:
            if st.button("Cancel", key="_bm_prompt_cancel_btn", use_container_width=True):
                st.session_state.pop("_bm_prompt_save_name", None)
                st.rerun()

    c_sub1, c_sub2 = st.columns(2)
    with c_sub1:
        with st.expander("Save As..."):
            save_as_col_in, save_as_col_btn = st.columns([2.5, 1])
            with save_as_col_in:
                new_roster_name = st.text_input("New roster name", key="_bm_save_as_name",
                                                label_visibility="collapsed", placeholder="New roster name...")
            with save_as_col_btn:
                if st.button("Save As", key="_bm_save_as_btn", use_container_width=True):
                    name_clean = new_roster_name.strip()
                    if not name_clean:
                        st.error("Please enter a roster name.")
                    elif name_clean == "[Custom / Unsaved]":
                        st.error("Cannot use reserved name '[Custom / Unsaved]'. Please enter a different name.")
                    else:
                        safe_name = persistence._safe_name(name_clean)
                        r = _extract_roster_from_session(safe_name, gen, builds, owned)
                        persistence.save_roster(r, safe_name)
                        st.session_state["_bm_active_roster"] = safe_name
                        st.session_state["_bm_roster_msg"] = f"Saved roster '{safe_name}'."
                        st.rerun()
    with c_sub2:
        with st.expander("Import JSON"):
            up = st.file_uploader("Roster JSON file", type=["json"], key="_bm_import_upload",
                                  label_visibility="collapsed")
            if up is not None:
                if st.button("Apply imported roster", type="primary", key="_bm_apply_import_btn",
                             use_container_width=True):
                    try:
                        raw = up.getvalue().decode("utf-8")
                        imported = roster_from_json(raw)
                        raw_imported_name = imported.name.strip() if imported.name else ""
                        safe_imported_name = persistence._safe_name(raw_imported_name)
                        if not safe_imported_name or safe_imported_name in ("[Custom / Unsaved]", "unnamed"):
                            safe_imported_name = "imported_roster"
                        imported.name = safe_imported_name
                        persistence.save_roster(imported, safe_imported_name)
                        _load_roster_into_session(imported)
                        st.session_state["_bm_active_roster"] = safe_imported_name
                        st.session_state["_bm_roster_msg"] = f"Loaded roster '{safe_imported_name}'."
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load roster: {e}")


def _roster_input(gen: int) -> dict[str, HeroBuild]:
    myth = sorted(heroes_up_to_generation(gen))
    by_myth = {c: [h for h in myth if hero_class(h) == c] for c in ("Inf", "Cav", "Arc")}
    by_epic = {c: sorted(h for h in EPIC_HEROES if hero_class(h) == c)
               for c in ("Inf", "Cav", "Arc")}
    options_by_cls = {c: by_myth[c] + by_epic[c] for c in ("Inf", "Cav", "Arc")}

    # Detect generation slider change
    last_gen = st.session_state.get("_bm_last_gen")
    gen_changed = (last_gen is not None and last_gen != gen)
    st.session_state["_bm_last_gen"] = gen

    # Initialize master backing stores
    if "_bm_master_owned" not in st.session_state:
        existing_owned = {
            c: [h for h in st.session_state.get(f"_bm_own_{c}", []) if hero_class(h) == c]
            for c in ("Inf", "Cav", "Arc")
        }
        if any(existing_owned.values()):
            st.session_state["_bm_master_owned"] = existing_owned
        else:
            st.session_state["_bm_master_owned"] = {c: list(by_myth[c]) for c in ("Inf", "Cav", "Arc")}
    master_owned: dict[str, list[str]] = st.session_state["_bm_master_owned"]

    if "_bm_master_builds" not in st.session_state:
        st.session_state["_bm_master_builds"] = {}
    master_builds: dict[str, HeroBuild] = st.session_state["_bm_master_builds"]

    # Pre-collect owned and builds for toolbar
    owned_preview: dict[str, list[str]] = {}
    for cls in ("Inf", "Cav", "Arc"):
        owned_preview[cls] = [h for h in master_owned.get(cls, []) if h in options_by_cls[cls]]

    builds_preview: dict[str, HeroBuild] = {}
    for cls in ("Inf", "Cav", "Arc"):
        for h in owned_preview[cls]:
            if f"_bm_star_{h}" in st.session_state:
                star = st.session_state[f"_bm_star_{h}"]
                tier = st.session_state.get(f"_bm_tier_{h}", 0)
                wl = 0 if h in EPIC_HEROES else st.session_state.get(f"_bm_wl_{h}", _WIDGET_DEFAULT)
                h_build = HeroBuild(level=_code(star, tier), widget_level=int(wl))
                builds_preview[h] = h_build
                master_builds[h] = h_build
            elif h in master_builds:
                builds_preview[h] = master_builds[h]
            else:
                star = st.session_state.get(f"_bm_star_{h}", _STAR_DEFAULT)
                tier = st.session_state.get(f"_bm_tier_{h}", 0)
                wl = 0 if h in EPIC_HEROES else st.session_state.get(f"_bm_wl_{h}", _WIDGET_DEFAULT)
                h_build = HeroBuild(level=_code(star, tier), widget_level=int(wl))
                builds_preview[h] = h_build
                master_builds[h] = h_build

    _render_roster_manager(gen, builds_preview, owned_preview)

    components.render_section_label("Your roster", num=2)
    st.caption(
        "Pick the heroes you own. Or import them from a screenshot. Levels "
        "default to MAX; open the expander to set your real sub-stars/widgets."
    )
    _ocr_import(gen, options_by_cls)

    _CLS_NAME = {"Inf": "Infantry", "Cav": "Cavalry", "Arc": "Archer"}
    owned: dict[str, list[str]] = {}
    cols = st.columns(3)
    for col, cls in zip(cols, ("Inf", "Cav", "Arc")):
        with col:
            st.markdown(components.class_chip_html(cls), unsafe_allow_html=True)
            key = f"_bm_own_{cls}"
            visible_set = set(options_by_cls[cls])

            if gen_changed or key not in st.session_state:
                st.session_state[key] = [h for h in master_owned.get(cls, []) if h in visible_set]

            selected = st.multiselect(
                _CLS_NAME[cls],
                options=options_by_cls[cls],
                key=key,
                format_func=lambda h: f"{h} (epic)" if h in EPIC_HEROES else h,
                label_visibility="collapsed",
            )
            owned[cls] = [h for h in selected if h in visible_set]
            hidden = [h for h in master_owned.get(cls, []) if h not in visible_set]
            master_owned[cls] = owned[cls] + hidden

    builds: dict[str, HeroBuild] = {}
    all_owned = [h for cls in ("Inf", "Cav", "Arc") for h in owned[cls]]
    with st.expander("Set your real stars / widgets. Type the numbers (default 5★, widget 4)"):
        hh = st.columns([3, 2, 2, 3])
        hh[0].caption("Hero")
        hh[1].caption("★ 0–5")
        hh[2].caption("Sub-tier 0–5")
        hh[3].caption("Widget 0–10")
        for cls in ("Inf", "Cav", "Arc"):
            if not owned[cls]:
                continue
            st.markdown(f"**{cls}**")
            for h in owned[cls]:
                is_epic = h in EPIC_HEROES
                s_key = f"_bm_star_{h}"
                t_key = f"_bm_tier_{h}"
                w_key = f"_bm_wl_{h}"

                b_saved = master_builds.get(h)
                if b_saved is not None:
                    init_star, init_tier = _safe_star_subtier_from_level(b_saved.level)
                    init_wl = b_saved.widget_level
                else:
                    init_star, init_tier = _STAR_DEFAULT, 0
                    init_wl = 0 if is_epic else _WIDGET_DEFAULT

                if s_key not in st.session_state:
                    st.session_state[s_key] = init_star
                if t_key not in st.session_state:
                    st.session_state[t_key] = init_tier
                if w_key not in st.session_state and not is_epic:
                    st.session_state[w_key] = init_wl

                c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
                with c1:
                    st.markdown(f"<div style='padding-top:6px'>{h}"
                                + (" <span style='color:var(--ks-text-muted);"
                                   "font-size:10px;'>epic</span>" if is_epic else "")
                                + "</div>", unsafe_allow_html=True)
                with c2:
                    star = st.number_input("star", min_value=0, max_value=5, step=1,
                                           key=s_key, label_visibility="collapsed")
                with c3:
                    tier = st.number_input("sub-tier", min_value=0, max_value=5, step=1,
                                           key=t_key, label_visibility="collapsed",
                                           disabled=int(star) >= 5,
                                           help="Sub-tier (ascension) within a star "
                                                "level. 0 for none, up to 5. Ignored "
                                                "at 5★ (MAX).")
                with c4:
                    if is_epic:
                        wl = 0
                        st.markdown("<div style='padding-top:6px;color:var(--ks-text-muted);"
                                    "font-size:11px;'>no widget</div>",
                                    unsafe_allow_html=True)
                    else:
                        wl = st.slider("widget", min_value=0, max_value=10, step=1,
                                       key=w_key, label_visibility="collapsed")
                h_build = HeroBuild(level=_code(star, tier), widget_level=int(wl))
                builds[h] = h_build
                master_builds[h] = h_build

    for h in all_owned:
        if h not in builds:
            b_default = HeroBuild(widget_level=0 if h in EPIC_HEROES else _WIDGET_DEFAULT)
            builds[h] = b_default
            master_builds[h] = b_default

    return builds


def _scenario_explainer() -> None:
    components.render_section_label("The scenarios it tests", num=3)
    st.caption(
        "You don't pick one. The benchmark scores all four. This is just so you "
        "know what each means and which one matters for how you play."
    )
    _tone = {"defense": "accent", "solo_atk": "accent",
             "garrison": "warn", "rally_atk": "warn"}
    for key, _ in _SCENARIOS[:4]:
        st.markdown(f"**{_SCEN_LABEL[key]}**")
        _callout(_ADVICE[key], tone=_tone[key])


def _lineup_card(names, title: str, sub: str = "") -> None:
    cells = ""
    has_cash = False
    for h in names:
        c = hero_class(h)
        cash = h in CASH_ONLY_HEROES
        has_cash = has_cash or cash
        nm = h + (" <span style='color:var(--ks-warn);font-size:11px;'></span>" if cash else "")
        cells += (
            f"<div style='display:flex;flex-direction:column;align-items:center;gap:6px;"
            f"flex:1 1 0;min-width:0;'>"
            f"{components.hero_portrait_html(h, size=60, cls=c)}"
            f"<div style='font-weight:600;font-size:13px;text-align:center;max-width:100%;"
            f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{nm}</div>"
            f"{components.class_badge_html(c, size='sm')}</div>")
    notes = [t for t in [sub, ("= a cash hero you <b>own</b>. Field it. We never "
             "recommend <i>buying</i> cash heroes; build a non-cash one for the long run."
             if has_cash else "")] if t]
    sub_html = ("<div style='color:var(--ks-text-muted);font-size:12px;margin-top:10px;'>"
                + "<br>".join(notes) + "</div>") if notes else ""
    st.markdown(
        f"<div style='border:1px solid var(--ks-border);border-radius:12px;"
        f"background:var(--ks-surface);box-shadow:var(--ks-shadow-card);"
        f"padding:14px 16px;margin:6px 0 14px;'>"
        f"<div style='font-size:11px;font-weight:700;letter-spacing:.04em;"
        f"text-transform:uppercase;color:var(--ks-text-muted);margin-bottom:12px;'>{title}</div>"
        f"<div style='display:flex;gap:12px;align-items:flex-start;'>{cells}</div>"
        f"{sub_html}</div>",
        unsafe_allow_html=True)


_MODE_LABEL = {"defense": "Solo defense", "solo_atk": "Solo attack",
               "garrison": "Garrison", "rally_atk": "Rally"}


def _render_comp_per_mode(rep) -> None:
    comp = getattr(rep, "comp_by_mode", {}) or {}
    if not any(comp.values()):
        return
    st.markdown("**Your best team for each mode**", unsafe_allow_html=True)
    st.caption("You field different heroes per mode. That's normal, not a contradiction. "
               "Here's your strongest non-cash trio for each.")
    cols = st.columns(2)
    for i, m in enumerate(("defense", "solo_atk", "garrison", "rally_atk")):
        trio = comp.get(m)
        if not trio:
            continue
        chips = "".join(
            f"<span style='display:inline-flex;align-items:center;gap:5px;margin:0 10px 6px 0;'>"
            f"{components.hero_portrait_html(h, size=30, cls=hero_class(h))}"
            f"<span style='font-size:12.5px;'>{h}{' ' if h in CASH_ONLY_HEROES else ''}</span></span>" for h in trio)
        with cols[i % 2]:
            st.markdown(
                f"<div style='margin:2px 0 8px;'><div style='font-size:12px;font-weight:700;"
                f"color:var(--ks-text-muted);margin-bottom:4px;'>{_MODE_LABEL[m]}</div>"
                f"<div style='display:flex;flex-wrap:wrap;align-items:center;'>{chips}</div>"
                f"</div>", unsafe_allow_html=True)


def _hero_rows(per_hero: dict[str, float], cls: str) -> None:
    ranked = sorted(((v, h) for h, v in per_hero.items() if hero_class(h) == cls),
                    reverse=True)
    if not ranked:
        st.caption("None owned")
        return
    top = ranked[0][0] or 1.0
    for i, (v, h) in enumerate(ranked, start=1):
        cash = h in CASH_ONLY_HEROES
        w = max(0, min(100, v * 100))
        name = (f"{h} <span style='color:var(--ks-warn);font-size:10px;'>ref</span>"
                if cash else h)
        muted = "opacity:0.55;" if cash else ""
        delta = "" if i == 1 else (
            f"<span style='color:var(--ks-text-muted);font-size:11px;'> "
            f"{v - top:+.2f}</span>")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;margin:3px 0;{muted}'>"
            f"<span style='width:16px;color:var(--ks-text-muted);font-size:11px;'>{i}</span>"
            f"{components.hero_portrait_html(h, size=22, cls=cls)}"
            f"<span style='flex:1;font-size:13px;'>{name}{delta}</span>"
            f"<span style='width:42px;text-align:right;font-size:12px;font-variant-numeric:tabular-nums;'>{v:.2f}</span>"
            f"<span style='width:60px;height:6px;background:var(--ks-border);border-radius:3px;overflow:hidden;'>"
            f"<span style='display:block;height:6px;width:{w:.0f}%;background:var(--ks-accent);'></span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def _render_results(gen: int, gr) -> None:
    scen = st.radio(
        "scenario", [s[0] for s in _SCENARIOS],
        format_func=lambda k: _SCEN_LABEL[k], horizontal=True,
        key="_bm_scen", label_visibility="collapsed",
    )
    _callout(_ADVICE[scen])

    best = best_per_class_trio(gr.per_hero.get(scen, {}))
    if best:
        _lineup_card(best, "Best trio to field",
                     "Your strongest owned trio for this scenario.")

    cols = st.columns(3)
    for col, cls in zip(cols, ("Inf", "Cav", "Arc")):
        with col:
            st.markdown(components.class_chip_html(cls), unsafe_allow_html=True)
            _hero_rows(gr.per_hero[scen], cls)
    st.caption(
        "Score = how the hero does averaged over every trio it leads in this "
        "scenario (higher = better; attack = enemy destroyed, defense = troops "
        "you keep). A **ref** tag marks a cash-only hero (a ceiling, not recommended)."
    )
    st.markdown("**Visualise**", unsafe_allow_html=True)
    tab_h, tab_r = st.tabs(["Strength grid", "Role shape"])
    with tab_h:
        _render_heatmap(gr)
    with tab_r:
        _render_radar(gr)


_HEAT_COLS = [("defense", "Defense"), ("solo_atk", "Solo"),
              ("garrison", "Garrison"), ("rally_atk", "Rally"),
              ("all_around", "All-round")]
_RADAR_AXES = [("defense", "Defense"), ("solo_atk", "Solo atk"),
               ("garrison", "Garrison"), ("rally_atk", "Rally")]
_CLS_ORDER = {"Inf": 0, "Cav": 1, "Arc": 2}
_CLS_COLOR = {"Inf": "#7c3aed", "Cav": "#0ea5e9", "Arc": "#22c55e"}
_PALETTE = ["#7c3aed", "#0ea5e9", "#22c55e", "#f59e0b", "#ef4444", "#ec4899",
            "#14b8a6", "#a855f7", "#84cc16", "#f97316", "#06b6d4", "#e11d48"]


def _render_heatmap(gr) -> None:
    import plotly.graph_objects as go
    by_cls = {c: sorted((h for h in gr.per_hero["all_around"] if hero_class(h) == c),
                        key=lambda h: -gr.per_hero["all_around"][h])
              for c in ("Inf", "Cav", "Arc")}
    heroes: list[str] = []
    labels: list[str] = []
    for c in ("Inf", "Cav", "Arc"):
        for h in by_cls[c]:
            heroes.append(h)
            labels.append(f"{c[0]} · {h}")
    if not heroes:
        st.caption("Nothing to plot.")
        return
    raw = [[gr.per_hero[s].get(h, 0.0) for s, _ in _HEAT_COLS] for h in heroes]
    cols = list(zip(*raw))
    norm_cols = []
    for col in cols:
        lo, hi = min(col), max(col)
        rng = (hi - lo) or 1.0
        norm_cols.append([(v - lo) / rng for v in col])
    z = list(map(list, zip(*norm_cols)))
    text = [[f"{v:.2f}" for v in row] for row in raw]
    fig = go.Figure(go.Heatmap(
        z=z, x=[c for _, c in _HEAT_COLS], y=labels,
        text=text, texttemplate="%{text}", textfont=dict(size=10),
        colorscale="Viridis", zmin=0.0, zmax=1.0, showscale=False,
        hovertemplate="%{y} · %{x}: %{text}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10),
                      height=max(280, 26 * len(heroes) + 60))
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Brightest cell in a column = the best hero for that scenario "
               "(colour is normalised per column; the number is the raw score). "
               "Rows are grouped Inf / Cav / Arc.")


def _render_radar(gr) -> None:
    import plotly.graph_objects as go
    cls = st.selectbox("Class", ["Inf", "Cav", "Arc"], key="_bm_radar_cls")
    pool = sorted((h for h in gr.per_hero["all_around"] if hero_class(h) == cls),
                  key=lambda h: -gr.per_hero["all_around"][h])
    if not pool:
        st.caption("None owned in this class.")
        return
    sel = st.multiselect("Compare", pool, default=pool[:3], key=f"_bm_radar_sel_{cls}")
    if not sel:
        st.caption("Pick at least one hero to compare.")
        return
    amax = {s: (max((gr.per_hero[s][h] for h in pool), default=1.0) or 1.0)
            for s, _ in _RADAR_AXES}
    fig = go.Figure()
    theta = [t for _, t in _RADAR_AXES]
    for i, h in enumerate(sel):
        color = _PALETTE[i % len(_PALETTE)]
        r = [gr.per_hero[s][h] / amax[s] for s, _ in _RADAR_AXES]
        fig.add_trace(go.Scatterpolar(
            r=r + [r[0]], theta=theta + [theta[0]], name=h,
            line=dict(color=color, width=2),
            fill="toself", fillcolor=_rgba(color, 0.12)))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1], showticklabels=False)),
        margin=dict(l=40, r=40, t=24, b=24), height=420, showlegend=True,
    )
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Each axis is normalised to the best in class. The *shape* shows "
               "specialisation (a defender peaks on Defense/Garrison, an attacker "
               "on Solo/Rally).")


def _rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{a})"


_VERDICT = {
    "develop": ("Build", "accent"),
    "save":    ("Bank", "warn"),
    "hold":    ("Hold", "warn"),
    "set":     ("Set", "ok"),
}
_PROFILE_LABEL = {"f2p": "F2P", "spender": "Spender", "whale": "Whale"}
_SCEN_SHORT = {"solo_atk": "solo attack", "rally_atk": "rally",
               "defense": "defense", "garrison": "garrison"}


def _builds_sig(builds) -> tuple:
    return tuple(sorted((h, b.level, b.widget_level) for h, b in builds.items()))


def _gear_sig(class_gear) -> tuple:
    if not class_gear or not isinstance(class_gear, dict):
        return ()
    res = []
    for cls in sorted(class_gear.keys()):
        slots = class_gear[cls]
        if isinstance(slots, dict):
            for s in sorted(slots.keys()):
                p = slots[s]
                res.append((cls, s, getattr(p, "quality", ""), getattr(p, "level", 0), getattr(p, "forge_mastery", 0)))
    return tuple(res)


def _cached_passes(gen, builds, widget_target, income, profile_override=None):
    cg = st.session_state.get("_bm_class_gear", None)
    sig = (gen, widget_target, income, profile_override, _builds_sig(builds), _gear_sig(cg))
    cache = st.session_state.setdefault("_bm_passes_cache", {})
    if sig not in cache:
        with st.spinner("Building your roadmap… (queues behind any running search)"):
            cache[sig] = _guarded_run(lambda: simulate(
                gen, builds, widget_target=widget_target, shard_income=income,
                profile_override=profile_override,
                class_gear=cg))
    return cache[sig]


_WEIGHT_SLIDERS = [("defense", "Defense"), ("solo_atk", "Attack"),
                   ("garrison", "Garrison"), ("rally_atk", "Rally")]


def _render_weight_controls(profile: str) -> dict:
    from kingshot_sim.benchmark.economy import PLAY_WEIGHTS, PROFILE_WEIGHTS
    st.markdown("**How you split your time** <span style='color:var(--ks-text-muted);"
                "font-size:12px;'>(your develop priorities follow this mix)</span>",
                unsafe_allow_html=True)
    for m, _ in _WEIGHT_SLIDERS:
        st.session_state.setdefault(f"_bm_w_{m}",
                                    int(round(PROFILE_WEIGHTS[profile][m] * 100)))
    presets = [("Balanced", PROFILE_WEIGHTS[profile]),
               ("Defense", PLAY_WEIGHTS["defense"]), ("Attack", PLAY_WEIGHTS["attack"]),
               ("Garrison", PLAY_WEIGHTS["garrison"]), ("Rally", PLAY_WEIGHTS["rally"])]
    for col, (lbl, w) in zip(st.columns(len(presets)), presets):
        if col.button(lbl, key=f"_bm_preset_{lbl}", use_container_width=True):
            for m, v in w.items():
                st.session_state[f"_bm_w_{m}"] = int(round(v * 100))
            st.rerun()
    raw = {}
    for col, (m, lbl) in zip(st.columns(4), _WEIGHT_SLIDERS):
        with col:
            raw[m] = st.slider(lbl, 0, 100, key=f"_bm_w_{m}")
    tot = sum(raw.values())
    if tot <= 0:
        st.caption("All sliders at 0. Falling back to **Balanced**. "
                   "Drag a slider (or hit a preset) to set your own mix.")
        return dict(PROFILE_WEIGHTS[profile])
    norm = {m: v / tot for m, v in raw.items()}
    st.caption("These are relative. Auto-balanced to 100% → " + "  ·  ".join(
        f"{lbl} {round(norm[m] * 100)}%" for m, lbl in _WEIGHT_SLIDERS))
    return norm


def _render_advice(gen, builds) -> None:
    from kingshot_sim.benchmark.economy import PROFILE_INCOME, PROFILE_WIDGET, PROFILE_WEIGHTS
    prof = st.radio("Your profile", [p[0] for p in _PROFILE_PICK],
                    format_func=dict(_PROFILE_PICK).get, key="_bm_adv_profile",
                    horizontal=True)
    if st.session_state.get("_bm_adv_prof_prev") != prof:
        st.session_state["_bm_income"] = PROFILE_INCOME[prof]
        st.session_state["_bm_widget_target"] = PROFILE_WIDGET[prof]
        for _m, _ in _WEIGHT_SLIDERS:
            st.session_state[f"_bm_w_{_m}"] = int(round(PROFILE_WEIGHTS[prof][_m] * 100))
        st.session_state["_bm_adv_prof_prev"] = prof
    c1, c2, c3 = st.columns(3)
    with c1:
        _budget_in = st.number_input(
            "Spare generic shards", min_value=0, max_value=20000, step=50,
            value=0, key="_bm_budget",
            help="Generic hero shards you have spare right now. We spend them where "
                 "each one buys the most power and bank the rest for what's next. "
                 "0 = just show me the priority order.")
        budget = int(_budget_in) if int(_budget_in) > 0 else None
    with c2:
        income = st.number_input(
            "Mythic shards / gen (approx)", min_value=0, max_value=5000, step=50,
            key="_bm_income",
            help="Roughly how many generic mythic shards you earn per generation "
                 "(~2 months). Drives the 'bank N now, afford X in Y gens' math. "
                 "A F2P should aim for ~400; whales are usually over 1500.")
        st.caption("F2P aim for ~400  ·  whales are usually 1500+")
    with c3:
        widget_target = st.slider(
            "Widget level you build to", min_value=0, max_value=10, step=1,
            key="_bm_widget_target",
            help="No fixed per-gen widget baseline exists, so tell us the widget "
                 "level you typically reach on a hero. We fold it into a hero's "
                 "potential. 0 = ignore widgets (rank on stars/skills only).")

    passes = _cached_passes(gen, builds, int(widget_target), int(income), profile_override=prof)
    weights = _render_weight_controls(prof)
    rep = advise_from_passes(passes, builds, weights, shard_budget=budget)

    _profile_tail = {
        "f2p": ". Stop at 4★ (the 4★→5★ step is pure stat tax).",
        "spender": ". 4★ everything, then bank spare shards toward 5★ on a keeper.",
        "whale": ". Push your kept heroes to 5★.",
    }[rep.profile]
    _profile_target = "max (5★)" if rep.target_star >= 5 else "skill-complete (4★)"
    _callout(
        f"You look like a <b>{_PROFILE_LABEL[rep.profile]}</b> "
        f"(widget {rep.widget_target}, ~{rep.shard_income} shards/gen) → "
        f"develop to <b>{_profile_target}</b>{_profile_tail}",
        tone=("ok" if rep.profile == "whale" else "accent"))

    if rep.best_trio:
        _lineup_card(rep.best_trio, "Field this trio",
                     "Your best trio for your current mix.")
    else:
        _callout("No fully-buildable trio. A class only has cash heroes "
                 "(e.g. Amadeus/Helga). Grab or develop a non-cash hero there.",
                 tone="warn")
    _render_comp_per_mode(rep)
    if rep.roulette_hero and rep.roulette_hero not in CASH_ONLY_HEROES:
        _callout(
            f"<b>Grab this gen's roulette hero: {rep.roulette_hero}.</b> It's "
            "gem-funded (separate from your shard bank), so it's the cheapest hero "
            "to max. Never skip it.", tone="ok")

    _render_spend_plan(rep)

    _render_timeline(rep)

    _render_shard_ledger(rep)

    with st.expander("Per-slot detail: develop / hold / set, with the why"):
        for p in rep.roadmap:
            _render_plan_row(p)

    with st.expander("Worth waiting for? Your hero vs the upcoming ones"):
        _render_crossover(rep)
    with st.expander("Where your shards buy the most"):
        _render_quadrant(rep)

    keeps: dict[str, list[str]] = {}
    for k, sk in rep.keep_over:
        keeps.setdefault(k, []).append(sk)
    if keeps:
        scen_lbl = _MODE_LABEL.get(max(weights, key=weights.get), "mix")
        st.markdown(f"**Newer isn't always better. For {scen_lbl}**",
                    unsafe_allow_html=True)
        for k, skips in list(keeps.items())[:3]:
            st.markdown(
                f"<div style='font-size:12.5px;color:var(--ks-text-muted);margin:2px 0;'>"
                f"• Your <b style='color:var(--ks-text);'>{k}</b> is already as good as "
                f"the newer {', '.join(skips)} for {scen_lbl.lower()}. "
                f"No need to develop {'them' if len(skips) > 1 else 'it'}.</div>",
                unsafe_allow_html=True)
    st.caption(
        "Advice is for your owned roster at the levels you set. 4★ = skills maxed "
        "(the F2P target); the 4★→5★ step is +600 stat-only shards. "
        "Amadeus/Helga are cash-only.")


def _render_spend_plan(rep) -> None:
    order = [p for p in rep.spend_order if p.verdict in ("develop", "save")]
    if not order:
        return
    if rep.shard_budget is not None:
        head = (f"<b>With {rep.shard_budget} shards</b> (+{rep.shard_income}/gen): "
                f"spend <b>{rep.spend_now}</b> now")
        if rep.bank_amount > 0 and rep.bank_target:
            label, cost, gens, arrival = rep.bank_target
            if arrival is not None:
                when = f", arrives gen {arrival}"
            elif gens:
                when = f", ~{gens} more gen{'s' if gens != 1 else ''} of income"
            else:
                when = ""
            head += (f", then <b>bank {rep.bank_amount}</b> toward <b>{label}</b> "
                     f"({cost} sh{when}).")
        elif rep.bank_amount > 0:
            head += f", and keep the spare <b>{rep.bank_amount}</b> for next gen."
        else:
            head += ":"
    else:
        head = "<b>Spend order</b>: fund the top of this list first:"
    tgt = "5★" if rep.target_star >= 5 else "4★"
    rows = []
    for p in order:
        mark = "fund now" if (rep.shard_budget is None or p.funded) else "bank for it"
        eff = rep.efficiency.get(p.best_hero)
        metric = f"{p.shards_to_4star} sh"
        if eff:
            sg, _ssh, wg, wl = eff
            metric += f" · +{sg:.2f}"
            if wl > 0:
                metric += f" +{wg:.2f}"
        rows.append(
            f"<div style='display:flex;gap:8px;align-items:center;margin:3px 0;'>"
            f"<span style='width:14px;color:var(--ks-text-muted);'>{p.priority}</span>"
            f"{components.class_chip_html(p.cls)} "
            f"<b style='flex:1;'>{'' if p.acquire else ''}{p.best_hero}</b> "
            f"<span style='color:var(--ks-text-muted);font-size:12px;'>{metric}</span> "
            f"<span style='font-size:12px;'>{mark}</span></div>")
    _callout(head + "".join(rows))
    st.caption(f"Ordered by power-per-shard, best value first. \"fund now\" = your budget "
               "covers it; \"bank for it\" = save up (a pricey top pick can wait while a "
               f"cheaper slot is funded first). In the metric, the first +N is the power "
               f"gained leveling stars to {tgt}, the second +N is from raising the widget.")


def _render_shard_ledger(rep) -> None:
    if not rep.shard_ledger:
        return
    rows = []
    for s in rep.shard_ledger:
        if s.spends:
            spent = ", ".join(
                f"<b>{lbl}</b> <span style='color:var(--ks-text-muted);'>({c} sh)</span>"
                for lbl, c in s.spends)
        else:
            spent = "<span style='color:var(--ks-text-muted);'>banking, no buy</span>"
        save = ""
        if s.saving_for:
            lbl, need = s.saving_for
            save = (f" <span style='color:#f59e0b;'>· saving for {lbl} "
                    f"({need} more)</span>")
        rows.append(
            f"<div style='display:flex;gap:8px;align-items:baseline;margin:3px 0;"
            f"flex-wrap:wrap;'>"
            f"<b style='width:48px;'>Gen {s.gen}</b>"
            f"<span style='color:var(--ks-text-muted);font-size:12px;width:74px;'>"
            f"{s.start} +{s.income}</span>"
            f"<span style='flex:1;min-width:140px;'>{spent}</span>"
            f"<span style='font-size:12px;'>left <b>{s.end}</b> sh</span>{save}</div>")
    _callout("<b>Shard plan: projected bank</b>" + "".join(rows))
    st.caption(
        "Start = your shard bank that gen; +income is credited each gen; spends fund your "
        "priority order (roulette heroes are gem-funded, not shown here). “Saving for” = "
        "banking toward the next pick you can't afford yet. It's funded once income covers "
        "it. Enter your bank in the **Spare generic shards** field above to drive this.")


def _versatility_note(p) -> str:
    if p.versatility:
        return (f" <span style='color:var(--ks-text-muted);'>(also your top "
                f"{_SCEN_SHORT.get(p.versatility, p.versatility)} {p.cls})</span>")
    return ""


def _upcoming_note(p) -> str:
    if p.upcoming_hero:
        return (f" A stronger <b>{p.upcoming_hero}</b> lands gen {p.upcoming_gen} "
                "(costs shards too. Develop now and upgrade later, or bank for it).")
    return ""


def _gap_str(gap: float) -> str:
    if gap <= 0:
        return "stronger"
    return "much stronger" if gap >= 1.0 else f"+{gap * 100:.0f}% stronger"


def _free_soon_note(p) -> str:
    if p.free_soon_hero:
        return (f" <span style='color:var(--ks-text-muted);'>(a free <b>{p.free_soon_hero}</b> "
                f"lands gen {p.free_soon_gen}. Only a smaller step up, so develop now for "
                f"the gens of use and swap to it later.)</span>")
    return ""


def _render_timeline(rep) -> None:
    from kingshot_sim.benchmark.advisor import (
        _future_class_hero, future_generic_picks, LOOKAHEAD,
    )
    from kingshot_sim.benchmark.economy import ROULETTE_HERO_BY_GEN
    from kingshot_sim.data.reference import MAX_GENERATION
    target = "5★" if rep.target_star >= 5 else "4★"
    picks_by_gen = {g: hero for g, _c, hero, _e
                    in future_generic_picks(rep.gen, rep.curve_target)}

    nodes: list[tuple[str, str, list[str]]] = []
    now_parts: list[str] = []
    if rep.roulette_hero and rep.roulette_hero not in CASH_ONLY_HEROES:
        now_parts.append(f"grab <b>{rep.roulette_hero}</b> free")
    for p in rep.roadmap:
        chip = components.class_chip_html(p.cls)
        if p.verdict == "develop":
            swap = (f" <span style='color:var(--ks-text-muted);'>(better {p.free_soon_hero}"
                    f" free gen {p.free_soon_gen}, swap later)</span>"
                    if p.free_soon_hero else "")
            verb = "get &amp; build" if p.acquire else "develop"
            now_parts.append(f"{chip} {verb} <b>{p.best_hero}</b> → {target}{swap}")
        elif p.verdict == "save":
            now_parts.append(f"{chip} bank for <b>{p.best_hero}</b> → {target}")
        elif p.verdict == "hold":
            now_parts.append(f"{chip} skip: <b>{p.future_hero}</b> free gen {p.future_gen}")
        else:
            now_parts.append(f"{chip} <b>{p.best_hero}</b> set")
    nodes.append((f"Gen {rep.gen}", "now", now_parts))

    from kingshot_sim.data.reference import HERO_GENERATION
    for g in range(rep.gen + 1, min(rep.gen + LOOKAHEAD, MAX_GENERATION) + 1):
        parts: list[str] = []
        r = ROULETTE_HERO_BY_GEN.get(g)
        if r and r not in CASH_ONLY_HEROES:
            parts.append(f"grab <b>{r}</b> free")
        pick = picks_by_gen.get(g)
        for c in ("Inf", "Cav", "Arc"):
            h = _future_class_hero(g, c)
            if not h or h == r:
                continue
            cv = rep.curve_target.get(c, {})
            owned_vals = [v for hh, v in cv.items()
                          if HERO_GENERATION.get(hh, 0) <= rep.gen]
            base = max(owned_vals) if owned_vals else None
            edge = (cv.get(h, 0.0) - base) if base is not None else None
            chip = components.class_chip_html(c)
            if pick is not None and h == pick:
                tag = " <b style='color:var(--ks-accent);'>★ best pick to develop</b>"
            elif edge is not None and edge > 0:
                tag = (" <span style='color:var(--ks-text-muted);'>(also strong, but "
                       f"income funds ~1/gen. Do {pick} first)</span>")
            else:
                tag = " <span style='color:var(--ks-text-muted);'>(costs shards)</span>"
            parts.append(f"{chip} <b>{h}</b> arrives{tag}")
        if parts:
            nodes.append((f"Gen {g}", "future", parts))

    rail = ""
    for i, (label, kind, parts) in enumerate(nodes):
        dot = "var(--ks-accent)" if kind == "now" else "var(--ks-text-faint)"
        line = ("" if i == len(nodes) - 1 else
                "<div style='position:absolute;left:5px;top:16px;bottom:-8px;width:2px;"
                "background:var(--ks-border);'></div>")
        body = "".join(f"<div style='margin:2px 0;font-size:12.5px;'>{p}</div>" for p in parts)
        tag = ("<span style='color:var(--ks-accent);font-weight:600;'> · now</span>"
               if kind == "now" else "")
        rail += (
            f"<div style='position:relative;padding:0 0 14px 22px;'>"
            f"<div style='position:absolute;left:0;top:3px;width:12px;height:12px;"
            f"border-radius:50%;background:{dot};box-shadow:0 0 0 2px var(--ks-surface),"
            f"0 0 0 3px var(--ks-border);'></div>{line}"
            f"<div style='font-weight:700;font-size:12px;margin-bottom:3px;'>{label}{tag}</div>"
            f"{body}</div>")

    foot = (f"<div style='margin-top:2px;padding-top:8px;border-top:1px solid var(--ks-border);"
            f"color:var(--ks-text-muted);font-size:12px;line-height:1.55;'>"
            f"At ~<b>{rep.shard_income}</b> shards/gen you fund about <b>one</b> hero "
            f"0→{target} per gen. So follow the priority order, don't try to take two "
            f"classes to {target} at once. Roulette grabs are free &amp; parallel; generic "
            f"newcomers cost shards, so only chase them after your priorities.</div>")

    st.markdown("**Your roadmap: next generations**", unsafe_allow_html=True)
    st.markdown(
        f"<div style='border:1px solid var(--ks-border);border-radius:12px;"
        f"background:var(--ks-surface);box-shadow:var(--ks-shadow-card);"
        f"padding:14px 16px;margin:6px 0 14px;'>{rail}{foot}</div>",
        unsafe_allow_html=True)


def _render_plan_row(p) -> None:
    icon, tone = _VERDICT[p.verdict]
    chip = components.class_chip_html(p.cls)
    target = "5★" if p.target_star >= 5 else "4★"
    if p.verdict == "develop":
        action = ("don't own it yet. Get &amp; build now" if p.acquire
                  else "develop now")
        start = "—" if p.acquire else f"{p.best_star}★ → {target}"
        body = (f"{chip} <b>{p.best_hero}</b> "
                f"<span style='color:var(--ks-text-muted);'>{start}</span> · "
                f"{action}. {p.shards_to_4star} sh.{_versatility_note(p)}"
                f"{_free_soon_note(p)}{_upcoming_note(p)}")
    elif p.verdict == "save":
        body = (f"{chip} <b>{p.best_hero}</b>. Worth it, but the budget goes to "
                f"higher-value slots first. Bank the next {p.shards_to_4star} sh for "
                f"it (→ {target}).{_versatility_note(p)}{_free_soon_note(p)}")
    elif p.verdict == "hold":
        gap = f" <b>{_gap_str(p.future_gap)}</b>" if p.future_gap > 0 else " stronger"
        body = (f"{chip} <b>Skip {p.cls} shards</b>. <b>{p.future_hero}</b> lands "
                f"gen {p.future_gen} <b>free (roulette)</b>,{gap} than your "
                f"{p.best_hero}. That's a big jump worth waiting for. Don't sink "
                f"shards here, grab it when it drops.")
    else:
        body = (f"{chip} <b>{p.best_hero}</b> is set ({target}+, skills maxed). "
                f"Nothing more to spend here.{_versatility_note(p)}{_upcoming_note(p)}")
    _callout(f"{icon} {body}", tone=tone)


def _render_crossover(rep) -> None:
    import plotly.graph_objects as go
    from kingshot_sim.data.reference import HERO_GENERATION
    cls = st.selectbox("Class", ["Inf", "Cav", "Arc"], key="_bm_xover_cls")
    cv = rep.curve_target.get(cls, {})
    cvc = rep.curve_current.get(cls, {})
    plan = next((p for p in rep.roadmap if p.cls == cls), None)
    if not cv or plan is None:
        st.caption("Own at least one hero in every class to chart this.")
        return
    owned = {h: v for h, v in cv.items() if HERO_GENERATION.get(h, 0) <= rep.gen}
    future = {h: v for h, v in cv.items() if HERO_GENERATION.get(h, 0) > rep.gen}
    if not owned:
        st.caption("None owned in this class.")
        return
    if not future:
        st.caption("You're at the latest generation. No newer hero to wait for "
                   "in this class. Develop what you own.")
        return
    tgt = "5★" if rep.target_star >= 5 else "4★"
    best_h = max(owned, key=owned.get)
    best_v = owned[best_h]
    cur_v = cvc.get(best_h)
    cur_star = next((a.current_star for a in rep.heroes if a.hero == best_h), None)
    gens = [rep.gen] + sorted({HERO_GENERATION[h] for h in future})
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[gens[0], gens[-1]], y=[best_v, best_v], mode="lines",
        name=f"{best_h} at your {tgt} target", line=dict(color=_CLS_COLOR[cls], width=3)))
    if cur_v is not None:
        now_lbl = f"{best_h} now" + (f" ({cur_star}★)" if cur_star is not None else "")
        fig.add_trace(go.Scatter(
            x=[rep.gen], y=[cur_v], mode="markers+text", text=[now_lbl],
            textposition="bottom center", textfont=dict(size=10), name=now_lbl,
            marker=dict(size=13, color=_CLS_COLOR[cls], symbol="circle-open",
                        line=dict(width=2.5, color=_CLS_COLOR[cls]))))
    fx = [HERO_GENERATION[h] for h in future]
    fy = [future[h] for h in future]
    fig.add_trace(go.Scatter(
        x=fx, y=fy, mode="markers+text", text=list(future),
        textposition="top center", textfont=dict(size=10), name=f"upcoming at {tgt}",
        marker=dict(size=12, color="#f59e0b", symbol="diamond")))
    fig.update_layout(
        xaxis=dict(title="Generation", dtick=1),
        yaxis=dict(title="leader strength (same scale)"),
        margin=dict(l=10, r=10, t=10, b=10), height=340,
        legend=dict(orientation="h", yanchor="bottom", y=-0.35))
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Green line = your **{best_h}** at your {tgt} target (you keep it). Hollow dot "
        "= where it is now. The gap to the line is what you gain by developing what you "
        f"own. Diamonds = upcoming heroes at the same {tgt} target: above the line = worth "
        "banking for, on/below = your own hero is the better spend.")


_VERDICT_COLOR = {"develop": "#22c55e", "save": "#f59e0b", "hold": "#ef4444",
                  "set": "#64748b"}


def _render_quadrant(rep) -> None:
    import plotly.graph_objects as go
    owned = [a for a in rep.heroes
             if a.acquisition != "cash" and a.headroom > 0.005]
    if not owned:
        st.caption("Everything you own is already at its target. Nothing left to "
                   "develop for this playstyle.")
        return
    verdict_of = {p.best_hero: p.verdict for p in rep.roadmap}
    _glyph = {k: v[0] for k, v in _VERDICT.items()}
    owned.sort(key=lambda a: a.headroom)
    ys = [f"{_glyph.get(verdict_of.get(a.hero, 'set'), '')} {a.cls[0]} · {a.hero}"
          for a in owned]
    xs = [a.headroom for a in owned]
    colors = [_VERDICT_COLOR.get(verdict_of.get(a.hero, "set"), "#64748b")
              for a in owned]
    fig = go.Figure(go.Bar(
        x=xs, y=ys, orientation="h", marker_color=colors,
        text=[f"+{v:.2f}" for v in xs], textposition="outside",
        hovertemplate="%{y}: +%{x:.2f} power if you develop it<extra></extra>"))
    fig.update_layout(
        xaxis=dict(title="benchmark power unlocked (develop → your potential)"),
        margin=dict(l=10, r=10, t=24, b=10),
        height=max(220, 30 * len(owned) + 50))
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Each bar = the power you'd UNLOCK by taking that hero to its "
               "potential (your target★ + widget). Longest bars = where your shards/"
               "widget buy the most. Colour = the advisor's call (green = develop, "
               "amber = bank, red = skip, grey = already set).")


_PROFILE_PICK = [("f2p", "F2P"), ("spender", "Spender"), ("whale", "Whale")]
_PLAY_PICK = [("balanced", "A bit of everything"), ("defense", "Mostly defend"),
              ("attack", "Mostly attack"), ("garrison", "Hold garrison"),
              ("rally", "Lead rallies")]


def _render_simple_pickers() -> tuple[str, dict]:
    from kingshot_sim.benchmark.economy import PLAY_WEIGHTS, PROFILE_WEIGHTS
    c1, c2 = st.columns([1, 1.5])
    with c1:
        prof = st.radio("How much do you spend?", [p[0] for p in _PROFILE_PICK],
                        format_func=dict(_PROFILE_PICK).get, key="_bm_simple_profile",
                        horizontal=True)
    with c2:
        play = st.radio("What do you play most?", [p[0] for p in _PLAY_PICK],
                        format_func=dict(_PLAY_PICK).get, key="_bm_simple_play",
                        horizontal=True)
    weights = (dict(PROFILE_WEIGHTS[prof]) if play == "balanced"
               else dict(PLAY_WEIGHTS[play]))
    return prof, weights


def _render_noob_digest(rep) -> None:
    target = "5★" if rep.target_star >= 5 else "4★"
    _callout(f"As a <b>{_PROFILE_LABEL[rep.profile]}</b> we aim for <b>{target}</b> "
             f"heroes (assuming widget ~{rep.widget_target}, ~{rep.shard_income} sh/gen).",
             tone=("ok" if rep.profile == "whale" else "accent"))
    if rep.best_trio:
        _lineup_card(rep.best_trio, "Field this trio", "Your best 3 heroes right now.")
    else:
        _callout("No fully-buildable trio here. A class only has cash heroes "
                 "(e.g. Amadeus/Helga). Grab or develop a non-cash hero there.", tone="warn")

    do = [p for p in rep.spend_order
          if p.verdict in ("develop", "save") and not p.is_roulette][:2]
    if do:
        rows = "".join(
            f"<div style='margin:5px 0;font-size:13px;'>"
            f"{components.class_chip_html(p.cls)} Develop <b>{p.best_hero}</b> to "
            f"{target} <span style='color:var(--ks-text-muted);'>"
            f"(~{p.shards_to_4star} shards)</span></div>"
            for p in do)
        _callout("<b>Do this next</b>" + rows, tone="ok")
    elif not any(p.verdict in ("develop", "save") for p in rep.roadmap):
        _callout(f"<b>You're set</b>. Your best per class is already at {target}. "
                 "Just grab the free roulette heroes as they come.", tone="ok")

    if rep.roulette_hero and rep.roulette_hero not in CASH_ONLY_HEROES:
        _callout(f"<b>Grab {rep.roulette_hero} free</b>. This gen's roulette hero "
                 "is gem-funded, the cheapest hero to max. Never skip it.", tone="ok")

    donts = [f"Don't spend shards on {components.class_chip_html(p.cls)} <b>{p.cls}</b>"
             f". <b>{p.future_hero}</b> arrives free (roulette) gen {p.future_gen}."
             for p in rep.roadmap if p.verdict == "hold"]
    if donts:
        _callout("<b>Don't bother</b>"
                 + "".join(f"<div style='margin:5px 0;font-size:13px;'>{d}</div>"
                           for d in donts), tone="warn")

    _render_timeline(rep)
    st.caption("Simple mode shows just the essentials. Pick **Explore rankings** "
               "or **Advisor** (top of the page) for the full rankings, charts "
               "and shard economics.")


def render_profile_toolbar() -> None:
    saved_rosters = persistence.list_rosters()
    active_pref = st.session_state.get("_ks_active_roster")

    if not saved_rosters:
        col_sel, col_reload, col_save = st.columns([3, 1.5, 2])
        with col_sel:
            st.selectbox(
                "Account Profile",
                ["(No saved profiles)"],
                disabled=True,
                key="benchmark_roster_select",
                label_visibility="collapsed",
            )
        with col_reload:
            st.button(
                "🔄 Reload from Profile",
                disabled=True,
                key="benchmark_reload_roster_btn",
            )
        with col_save:
            st.button(
                "💾 Save Changes Back to Profile",
                disabled=True,
                key="benchmark_save_roster_btn",
            )
        return

    # Determine default index
    default_idx = 0
    if active_pref and active_pref in saved_rosters:
        default_idx = saved_rosters.index(active_pref)
        if st.session_state.get("_bm_synced_active") != active_pref:
            st.session_state["benchmark_roster_select"] = active_pref
            st.session_state["_bm_synced_active"] = active_pref

    # Clean up stale widget key in session_state if it's no longer valid
    if st.session_state.get("benchmark_roster_select") not in saved_rosters:
        st.session_state.pop("benchmark_roster_select", None)

    col_sel, col_reload, col_save = st.columns([3, 1.5, 2])
    with col_sel:
        selected_profile = st.selectbox(
            "Account Profile",
            saved_rosters,
            index=default_idx,
            key="benchmark_roster_select",
            label_visibility="collapsed",
        )
    with col_reload:
        reload_clicked = st.button(
            "🔄 Reload from Profile",
            key="benchmark_reload_roster_btn",
        )
    with col_save:
        save_clicked = st.button(
            "💾 Save Changes Back to Profile",
            key="benchmark_save_roster_btn",
        )

    last_loaded = st.session_state.get("_bm_active_profile_loaded")
    should_load = False

    if selected_profile != last_loaded:
        should_load = True
    elif reload_clicked:
        should_load = True

    if should_load and selected_profile:
        try:
            roster = persistence.load_roster(selected_profile)
            apply_roster_to_benchmark(roster)
            if st.session_state.get("_bm_gen", 1) > MAX_GENERATION:
                st.session_state["_bm_gen"] = MAX_GENERATION
            st.session_state["_bm_class_gear"] = roster.class_gear
            st.session_state["_ks_active_roster"] = roster.name
            st.session_state["_bm_active_profile_loaded"] = roster.name
            st.session_state["_bm_synced_active"] = roster.name
            st.session_state.pop("_bm_result", None)
            st.session_state.pop("_bm_passes_cache", None)
            if reload_clicked:
                st.success(f"Profile '{roster.name}' reloaded successfully.")
        except Exception as e:
            st.error(f"Failed to load profile '{selected_profile}': {e}")

    if save_clicked and selected_profile:
        try:
            roster = persistence.load_roster(selected_profile)
            updated_roster = extract_roster_from_benchmark(roster)
            persistence.save_roster(updated_roster, updated_roster.name)
            st.session_state["_bm_class_gear"] = updated_roster.class_gear
            st.session_state["_ks_active_roster"] = updated_roster.name
            st.session_state["_bm_active_profile_loaded"] = updated_roster.name
            st.session_state["_bm_synced_active"] = updated_roster.name
            st.success(f"Profile '{updated_roster.name}' saved back to profile!")
        except Exception as e:
            st.error(f"Failed to save profile '{selected_profile}': {e}")


def render() -> None:
    components.render_page_header(
        "Hero Benchmark",
        "Which heroes should you develop? Pick your generation and roster, "
        "and the tool ranks what to build next.",
    )
    render_profile_toolbar()
    _bm_view_options = ["Simple", "Explore rankings", "Advisor"]
    _persisted_view = st.session_state.get("_bm_view_mode")
    if _persisted_view is not None and _persisted_view not in _bm_view_options:
        _pv = str(_persisted_view)
        st.session_state["_bm_view_mode"] = (
            "Simple" if "Simple" in _pv
            else "Advisor" if "Advisor" in _pv
            else "Explore rankings")
    advanced = st.session_state.get(
        "_bm_view_mode", _bm_view_options[0]) != "Simple"
    _callout(
        "<b>A rule of thumb, not a truth-teller.</b> This ignores the live "
        "opponent, your joiners, gear, buffs, pets and turrets. It answers "
        "\"which heroes to prioritise / is my Jabel better than my Hilde\", not "
        "\"what wins your next specific fight\".", tone="warn",
    )

    components.render_section_label("Generation", num=1)
    gc1, gc2 = st.columns([4, 1])
    with gc1:
        pending_gen = st.session_state.pop("_bm_pending_gen", None)
        if pending_gen is not None:
            st.session_state["_bm_gen"] = pending_gen
        cur_gen = st.session_state.get("_bm_gen")
        if cur_gen not in range(1, MAX_GENERATION + 1):
            st.session_state["_bm_gen"] = MAX_GENERATION
        gen = st.select_slider(
            "Your generation",
            options=list(range(1, MAX_GENERATION + 1)),
            key="_bm_gen",
            label_visibility="collapsed",
        )
        st.session_state["_bm_master_gen"] = max(st.session_state.get("_bm_master_gen", gen), gen)
    with gc2:
        st.markdown(
            f"<div style='text-align:center;font-weight:800;font-size:18px;"
            f"color:var(--ks-accent);padding-top:2px;'>Gen {gen}</div>",
            unsafe_allow_html=True)
    st.caption(
        "The benchmark fights your roster against a tier-matched dummy across "
        "four scenarios, each on its own meta troop split."
    )

    builds = _roster_input(gen)
    if advanced:
        _scenario_explainer()

    if st.button("Analyse my roster", type="primary", key="_bm_run"):
        have = {c: sum(1 for h in builds if hero_class(h) == c)
                for c in ("Inf", "Cav", "Arc")}
        if min(have.values()) < 1:
            st.warning("Pick at least one hero in each class (Inf, Cav, Arc).")
        else:
            with st.spinner("Simulating your roster… (queues behind any running "
                            "search to keep the server responsive)"):
                cg = st.session_state.get("_bm_class_gear", None)
                cur = _guarded_run(lambda: rank_generation(
                    gen, BenchSettings(), builds=builds, roster=set(builds),
                    class_gear=cg))
            st.session_state["_bm_result"] = (gen, dict(builds), cur)
            st.session_state.pop("_bm_passes_cache", None)

    with st.container(border=True):
        st.markdown("<div style='font-weight:700;font-size:14px;margin-bottom:2px;'>"
                    "What do you want to see?</div>", unsafe_allow_html=True)
        view = st.radio(
            "View mode", _bm_view_options, horizontal=True,
            key="_bm_view_mode", label_visibility="collapsed",
            help="Simple = a quick 'do this / not that' plan. "
                 "Explore rankings = the full per-scenario rankings, charts and "
                 "shard economics. Advisor = a personalised develop / hold / skip "
                 "roadmap for your profile.",
        )
    advanced = view != "Simple"

    res = st.session_state.get("_bm_result")
    if not (res and len(res) == 3):
        _callout(
            "↓ <b>Your build plan appears here after you Analyse.</b> "
            "You'll get a recommended trio, a develop / hold / skip priority "
            "list, and a generation roadmap. Tuned to your profile and "
            "playstyle.", tone="accent")
        return
    rgen, rbuilds, cur = res
    if rgen != gen:
        _callout(f"↻ <b>You changed generation to gen {gen}.</b> Click "
                 "<b>Analyse my roster</b> to analyse it.", tone="warn")
        return
    if _builds_sig(rbuilds) != _builds_sig(builds):
        _callout("↻ <b>Your roster changed.</b> Click <b>Analyse my roster</b> to "
                 "refresh the plan below.", tone="warn")

    if not advanced:
        from kingshot_sim.benchmark.economy import PROFILE_INCOME, PROFILE_WIDGET
        prof, weights = _render_simple_pickers()
        passes = _cached_passes(rgen, rbuilds, PROFILE_WIDGET[prof], PROFILE_INCOME[prof],
                                profile_override=prof)
        rep = advise_from_passes(passes, rbuilds, weights, shard_budget=None)
        _render_noob_digest(rep)
        return

    components.render_section_label(
        "Advisor" if view == "Advisor" else "Rankings", num=4)
    if view == "Advisor":
        _render_advice(rgen, rbuilds)
    else:
        _render_results(rgen, cur)


__all__ = [
    "render",
    "render_profile_toolbar",
    "_extract_roster_from_session",
    "_load_roster_into_session",
    "_render_roster_manager",
]
