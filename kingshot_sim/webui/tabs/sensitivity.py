from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from kingshot_sim.config.fighter import Fighter
from kingshot_sim.sensitivity import (
    build_param_catalog, run_sweep, linspace,
    SensitivityParam, SweepResult,
)
from kingshot_sim.webui.forms import fighter_form, empty_fighter
from kingshot_sim.webui import persistence, components
from kingshot_sim.io_pkg.roster_bridge import account_roster_to_fighter


def render() -> None:
    components.render_page_header(
        title="Sensitivity",
        sub="Plot how one parameter (hero star, widget level, a bonus) changes "
            "the battle result, so you can see which upgrade is worth it.",
    )

    components.render_subheading(
        "Expert tool",
        "Build both fighters below, or send a matchup straight from "
        "Attack &amp; Defense / Quick Fight and just pick the lever to sweep.",
    )

    if "sn_attacker" not in st.session_state:
        st.session_state.sn_attacker = empty_fighter("Attacker")
    if "sn_defender" not in st.session_state:
        st.session_state.sn_defender = empty_fighter("Defender")

    rosters = persistence.list_rosters()
    if rosters:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sel_a = st.selectbox("Load attacker", ["—"] + rosters, key="sn_load_att_roster")
        with c2:
            if st.button("→ Attacker", key="sn_btn_att", width="stretch"):
                if sel_a != "—":
                    loaded_r = persistence.load_roster(sel_a)
                    curr = st.session_state.sn_attacker
                    st.session_state.sn_attacker = account_roster_to_fighter(
                        loaded_r, curr, default_label="Attacker",
                    )
                    gen_key = "sn_att_gen"
                    st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
                    st.rerun()
        with c3:
            sel_d = st.selectbox("Load defender", ["—"] + rosters, key="sn_load_def_roster")
        with c4:
            if st.button("→ Defender", key="sn_btn_def", width="stretch"):
                if sel_d != "—":
                    loaded_r = persistence.load_roster(sel_d)
                    curr = st.session_state.sn_defender
                    st.session_state.sn_defender = account_roster_to_fighter(
                        loaded_r, curr, default_label="Defender",
                    )
                    gen_key = "sn_def_gen"
                    st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
                    st.rerun()
        st.markdown("---")

    att_gen = st.session_state.get("sn_att_gen", 0)
    def_gen = st.session_state.get("sn_def_gen", 0)

    left, right = st.columns(2)
    with left:
        with st.expander("Attacker", expanded=False):
            try:
                attacker = fighter_form(
                    st.session_state.sn_attacker,
                    key_prefix=f"sn_att_g{att_gen}",
                    side="attacker",
                )
                st.session_state.sn_attacker = attacker
            except Exception as e:
                st.error(f"Attacker invalid: {e}")
                return
    with right:
        with st.expander("Defender", expanded=False):
            try:
                defender = fighter_form(
                    st.session_state.sn_defender,
                    key_prefix=f"sn_def_g{def_gen}",
                    side="defender",
                )
                st.session_state.sn_defender = defender
            except Exception as e:
                st.error(f"Defender invalid: {e}")
                return

    st.markdown("---")

    components.render_subheading("Parameter to sweep")
    catalog = build_param_catalog()

    cols = st.columns([1, 2, 2])
    with cols[0]:
        side = st.radio("Side", ["attacker", "defender"], horizontal=True, key="sn_side")
    side_filtered = [p for p in catalog if p.side == side]
    groups = sorted({p.group for p in side_filtered})
    with cols[1]:
        group = st.selectbox("Category", groups, key="sn_group")
    group_filtered = [p for p in side_filtered if p.group == group]
    with cols[2]:
        labels = [p.label for p in group_filtered]
        idx = st.selectbox(
            "Parameter",
            list(range(len(group_filtered))),
            format_func=lambda i: labels[i],
            key="sn_param",
        )
    param: SensitivityParam = group_filtered[idx]

    st.markdown("##### Sweep range")
    rcols = st.columns(4)
    with rcols[0]:
        vmin = st.number_input("Min", value=float(param.default_min),
                                  step=float(param.default_step),
                                  key=f"sn_min_{param.key}")
    with rcols[1]:
        vmax = st.number_input("Max", value=float(param.default_max),
                                  step=float(param.default_step),
                                  key=f"sn_max_{param.key}")
    with rcols[2]:
        vstep = st.number_input("Step", value=float(param.default_step),
                                   min_value=0.001, step=float(param.default_step / 4 + 0.001),
                                   format="%.3f", key=f"sn_step_{param.key}")
    with rcols[3]:
        vals_preview = linspace(vmin, vmax, vstep)
        st.metric("Points", f"{len(vals_preview)}")

    mcols = st.columns([2, 2, 2, 3])
    with mcols[0]:
        mode_label = st.radio("Mode", ["Expected", "Monte Carlo"],
                                horizontal=True, key="sn_mode")
    with mcols[1]:
        mc_trials = st.number_input("MC trials per point", 10, 1000, 50, step=10,
                                       disabled=(mode_label != "Monte Carlo"),
                                       key="sn_mc_trials")
    with mcols[2]:
        seed = st.number_input("Seed", 0, 2**31 - 1, 42, key="sn_seed")
    with mcols[3]:
        run_btn = st.button("▶ Run sweep", width="stretch",
                              type="primary", key="sn_run")

    if not run_btn:
        return
    if len(vals_preview) < 2:
        st.warning("Need at least 2 points. Adjust min/max/step.")
        return

    progress = st.progress(0.0, text="Sweeping...")

    def _on_progress(done: int, total: int) -> None:
        if total > 0:
            progress.progress(min(1.0, done / total),
                                text=f"Sweep: {done}/{total}")

    mode = "mc" if mode_label == "Monte Carlo" else "expected"
    with st.spinner("Running sensitivity sweep..."):
        result = run_sweep(
            attacker, defender, param, vals_preview,
            mode=mode, mc_trials=int(mc_trials), mc_seed=int(seed),
            progress=_on_progress,
        )
    progress.empty()

    st.success(f"Done in {result.elapsed_s:.1f}s · {len(result.points)} points")

    _render_curve(result)


def _render_curve(result: SweepResult) -> None:
    pts = result.points
    xs = [p.value for p in pts]
    ys = [p.score for p in pts]

    valid_ys = [y for y in ys if y == y]
    if valid_ys:
        cols = st.columns(4)
        cols[0].metric("Min score", f"{min(valid_ys):+.4f}")
        cols[1].metric("Max score", f"{max(valid_ys):+.4f}")
        cols[2].metric("Δ (max − min)", f"{max(valid_ys) - min(valid_ys):.4f}")
        mid_i = len(valid_ys) // 2
        if 0 < mid_i < len(valid_ys) - 1:
            dy = ys[mid_i + 1] - ys[mid_i - 1]
            dx = xs[mid_i + 1] - xs[mid_i - 1]
            slope = dy / dx if dx != 0 else float("nan")
            cols[3].metric("Mid-range slope", f"{slope:+.5f}")

    fig = go.Figure()
    if result.mode == "mc":
        ci_low = [p.score_ci_low for p in pts]
        ci_high = [p.score_ci_high for p in pts]
        fig.add_trace(go.Scatter(
            x=xs + xs[::-1],
            y=ci_high + ci_low[::-1],
            fill="toself", fillcolor="rgba(124,58,237,0.18)",
            line=dict(color="rgba(255,255,255,0)"),
            showlegend=False, hoverinfo="skip", name="95% CI",
        ))
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines+markers",
        line=dict(color="#7c3aed", width=2),
        marker=dict(size=6),
        name="Score (median)" if result.mode == "mc" else "Score",
    ))
    components.add_score_verdict_bands(fig, axis="y")
    fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
    fig.update_layout(
        xaxis_title=result.param.label,
        yaxis_title="Battle score (att perspective)",
        margin=dict(l=10, r=10, t=10, b=10), height=400,
    )
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, width="stretch")

    with st.expander("Sweep data", expanded=False):
        import pandas as pd
        rows = []
        for p in pts:
            row = {
                "value": result.param.value_format(p.value),
                "score": f"{p.score:+.4f}" if p.score == p.score else "NaN",
            }
            if result.mode == "mc":
                row["CI low"]  = f"{p.score_ci_low:+.4f}"  if p.score_ci_low  is not None else "—"
                row["CI high"] = f"{p.score_ci_high:+.4f}" if p.score_ci_high is not None else "—"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
