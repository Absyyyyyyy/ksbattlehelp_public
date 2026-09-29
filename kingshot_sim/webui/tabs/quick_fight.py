from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from kingshot_sim.config.fighter import Fighter
from kingshot_sim.domain.enums import RNGMode, BattleType, SquadType
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.montecarlo import run_monte_carlo
from kingshot_sim.webui.forms import fighter_form, empty_fighter
from kingshot_sim.webui.easy_mode_form import (
    fighter_form_with_mode, is_easy_mode, easy_mode_rally_flag,
)
from kingshot_sim.webui import persistence, components, runtime_stats
from kingshot_sim.io_pkg.roster_bridge import account_roster_to_fighter


def render() -> None:
    components.render_page_header(
        title="Quick Fight",
        sub="Set up an attacker and a defender, then simulate the battle "
            "for a full round-by-round breakdown.",
    )

    if "qf_attacker" not in st.session_state:
        st.session_state.qf_attacker = empty_fighter("Attacker")
    if "qf_defender" not in st.session_state:
        st.session_state.qf_defender = empty_fighter("Defender")

    rosters = persistence.list_rosters()
    if rosters:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            sel_a = st.selectbox("Load attacker", ["—"] + rosters, key="qf_load_att_roster")
        with c2:
            if st.button("→ Attacker", key="qf_btn_load_att", width="stretch"):
                if sel_a != "—":
                    loaded_r = persistence.load_roster(sel_a)
                    curr = st.session_state.qf_attacker
                    st.session_state.qf_attacker = account_roster_to_fighter(
                        loaded_r, curr, default_label="Attacker",
                    )
                    st.session_state["qf_att_roster"] = loaded_r
                    gen_key = "qf_att_form_gen"
                    st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state["qf_att_input_mode"] = "Advanced"
                    st.session_state["qf_att_input_mode_radio"] = "Advanced (manual entry)"
                    st.rerun()
        with c3:
            sel_d = st.selectbox("Load defender", ["—"] + rosters, key="qf_load_def_roster")
        with c4:
            if st.button("→ Defender", key="qf_btn_load_def", width="stretch"):
                if sel_d != "—":
                    loaded_r = persistence.load_roster(sel_d)
                    curr = st.session_state.qf_defender
                    st.session_state.qf_defender = account_roster_to_fighter(
                        loaded_r, curr, default_label="Defender",
                    )
                    st.session_state["qf_def_roster"] = loaded_r
                    gen_key = "qf_def_form_gen"
                    st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state["qf_def_input_mode"] = "Advanced"
                    st.session_state["qf_def_input_mode_radio"] = "Advanced (manual entry)"
                    st.rerun()
        st.markdown("---")

    left, right = st.columns(2)
    with left:
        components.render_subheading("Attacker")
        _render_trio_strip(st.session_state.qf_attacker)
        try:
            attacker = fighter_form_with_mode(
                st.session_state.qf_attacker,
                key_prefix="qf_att",
                side="attacker",
                roster=st.session_state.get("qf_att_roster"),
            )
            st.session_state.qf_attacker = attacker
        except Exception as e:
            st.error(f"Invalid attacker: {e}")
            attacker = None

        if is_easy_mode("qf_att"):
            is_solo_attack = not easy_mode_rally_flag("qf_att", default=True)
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;Attack mode: "
                f"**{'Solo march' if is_solo_attack else 'Rally'}** "
                f"(from Easy-mode P3)",
                unsafe_allow_html=True,
            )
        else:
            attack_mode = st.radio(
                "Attack mode",
                ["Rally (with joiners)", "Solo march (no joiners)"],
                index=0 if not st.session_state.get("qf_is_solo_attack", False) else 1,
                horizontal=True,
                key="qf_attack_mode",
                help=(
                    "Rally: joiners and rally-side widget skills are active.\n\n"
                    "Solo march: a lone attacker. No joiners contribute, and "
                    "the attacker's own widget expedition skills with rally side "
                    "(e.g. Aegis of Fate, Cosmic Eye) do not fire."
                ),
            )
            is_solo_attack = attack_mode.startswith("Solo")
        st.session_state.qf_is_solo_attack = is_solo_attack

    with right:
        components.render_subheading("Defender")
        _render_trio_strip(st.session_state.qf_defender)
        try:
            defender = fighter_form_with_mode(
                st.session_state.qf_defender,
                key_prefix="qf_def",
                side="defender",
                roster=st.session_state.get("qf_def_roster"),
            )
            st.session_state.qf_defender = defender
        except Exception as e:
            st.error(f"Invalid defender: {e}")
            defender = None

    if attacker is None or defender is None:
        return

    st.markdown("---")
    rcols = st.columns([2, 2, 2, 3])
    with rcols[0]:
        rng_mode_label = st.radio("Simulation mode",
                                    ["Deterministic", "With randomness (Monte Carlo)"],
                                    horizontal=True, key="qf_rng_mode",
                                    help="Deterministic = average expected outcome, instant. "
                                         "Monte Carlo = N simulations with dice rolls, gives "
                                         "a confidence interval.")
    with rcols[1]:
        trials = st.number_input("Number of simulations", 10, 5000, 100, step=50,
                                  disabled=(rng_mode_label == "Deterministic"),
                                  key="qf_trials")
    with rcols[2]:
        seed = st.number_input("Random seed", 0, 2**31 - 1, 42, key="qf_seed",
                                 help="For reproducible randomness.")
    with rcols[3]:
        run_btn = st.button("▶ Run battle", width="stretch",
                             type="primary", key="qf_run")

    if not run_btn:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;'
            'padding:14px 16px;border:1px dashed var(--ks-border);'
            'border-radius:8px;color:var(--ks-text-muted);font-size:13px;'
            'margin-top:6px;">'
            '<span>↓ Your battle breakdown appears here after you Run. '
            'a plain-language verdict like</span>'
            + components.score_verdict_html(0.3)
            + '<span>plus casualties and a round-by-round chart.</span></div>',
            unsafe_allow_html=True,
        )
        return

    rng_mode = RNGMode.STOCHASTIC if rng_mode_label.startswith("With") else RNGMode.EXPECTED
    n_battles = int(trials) + 1 if (rng_mode == RNGMode.STOCHASTIC and trials > 1) else 1
    try:
        runtime_stats.increment_total_sims()
        runtime_stats.add_total_battles(n_battles)
    except Exception:
        pass
    base_cfg = BattleConfig(
        attacker=attacker, defender=defender,
        rng_mode=rng_mode, seed=int(seed),
        is_solo_attack=is_solo_attack,
    )

    if rng_mode == RNGMode.STOCHASTIC and trials > 1:
        with st.spinner(f"Simulating {trials} battles..."):
            mc = run_monte_carlo(base_cfg, n_trials=int(trials), seed=int(seed),
                                  keep_scores=True)
        _render_mc_result(mc)
        single_cfg = BattleConfig(
            attacker=attacker, defender=defender,
            rng_mode=RNGMode.STOCHASTIC, seed=int(seed),
            is_solo_attack=is_solo_attack,
        )
        result = run_battle(single_cfg)
        st.markdown("---")
        st.markdown(f"#### Battle replay (seed = {seed})")
        _render_single_result(result, attacker, defender, show_verdict=False)
    else:
        with st.spinner("Simulating..."):
            result = run_battle(base_cfg)
        _render_single_result(result, attacker, defender)


def _render_trio_strip(fighter: Fighter) -> None:
    try:
        leaders = [
            (fighter.leader_inf.hero_name, "Inf"),
            (fighter.leader_cav.hero_name, "Cav"),
            (fighter.leader_arc.hero_name, "Arc"),
        ]
    except Exception:
        return
    chips = "".join(
        f'<span style="margin-right:10px;">'
        f'{components.portrait_name_html(h, c, size=24, font_size=12.5)}</span>'
        for h, c in leaders if h
    )
    if not chips:
        return
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;align-items:center;'
        f'margin:0 0 8px;">{chips}</div>',
        unsafe_allow_html=True,
    )


def _render_single_result(result, attacker: Fighter, defender: Fighter,
                          *, show_verdict: bool = True) -> None:
    if show_verdict:
        _, _, color = components.score_verdict(result.score)
        components.render_result_summary(
            eyebrow="Result · deterministic",
            score=result.score,
            stats=[
                {"label": "Battle score", "value": f"{result.score:+.2f}",
                 "color": color, "sub": "−1 … +1 margin"},
                {"label": "Rounds", "value": f"{len(result.rounds)}"},
            ],
        )
        components.render_score_formula_expander()

    components.render_subheading("Casualties")
    initial_att = {st: sum(g.count for g in getattr(attacker.troops, st_name))
                    for st, st_name in [(SquadType.INFANTRY, "infantry"),
                                          (SquadType.CAVALRY, "cavalry"),
                                          (SquadType.ARCHER, "archer")]}
    initial_def = {st: sum(g.count for g in getattr(defender.troops, st_name))
                    for st, st_name in [(SquadType.INFANTRY, "infantry"),
                                          (SquadType.CAVALRY, "cavalry"),
                                          (SquadType.ARCHER, "archer")]}
    att_lost = {st: initial_att[st] - result.attacker_final[st] for st in SquadType.all()}
    def_lost = {st: initial_def[st] - result.defender_final[st] for st in SquadType.all()}

    _render_casualty_table(initial_att, att_lost, initial_def, def_lost)

    components.render_subheading("Round-by-round troop counts")
    fig = _round_chart(result, initial_att, initial_def)
    components.apply_plotly_theme(fig, dark=components.is_dark_mode())
    st.plotly_chart(fig, width="stretch")


def _render_casualty_table(initial_att: dict, att_lost: dict,
                           initial_def: dict, def_lost: dict) -> None:
    def _row(side: str, init: dict, lost: dict) -> str:
        cells = (
            f'<td style="padding:10px 12px;font-weight:600;color:var(--ks-text);">{side}</td>'
        )
        for stt in SquadType.all():
            cells += (
                f'<td style="padding:10px 12px;text-align:right;color:var(--ks-text-muted);'
                f'font-family:\'JetBrains Mono\',monospace;font-size:13px;">{init[stt]:,}</td>'
                f'<td style="padding:10px 12px;text-align:right;color:var(--ks-danger);'
                f'font-family:\'JetBrains Mono\',monospace;font-size:13px;">'
                f'-{lost[stt]:,}</td>'
            )
        cells += (
            f'<td style="padding:10px 12px;text-align:right;font-weight:700;'
            f'color:var(--ks-danger);font-family:\'JetBrains Mono\',monospace;'
            f'font-size:13px;">-{sum(lost.values()):,}</td>'
        )
        return f'<tr style="border-top:1px solid var(--ks-border);">{cells}</tr>'

    def _th(label: str, align: str = "right") -> str:
        return (
            f'<th style="padding:9px 12px;text-align:{align};font-size:11px;'
            f'font-weight:600;letter-spacing:0.06em;text-transform:uppercase;'
            f'color:var(--ks-text-muted);white-space:nowrap;">{label}</th>'
        )

    head = _th("Side", "left") + "".join(
        _th(f"{c} init") + _th(f"{c} lost") for c in ("Inf", "Cav", "Arc")
    ) + _th("Total lost")
    html = (
        '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;'
        'border:1px solid var(--ks-border);border-radius:8px;'
        'box-shadow:var(--ks-shadow);margin-top:4px;">'
        '<table style="width:100%;border-collapse:collapse;min-width:520px;">'
        f'<thead><tr style="background:var(--ks-surface-alt);">{head}</tr></thead>'
        '<tbody>'
        + _row("Attacker", initial_att, att_lost)
        + _row("Defender", initial_def, def_lost)
        + '</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_mc_result(mc) -> None:
    components.render_subheading("Monte Carlo summary")
    _, _, color = components.score_verdict(mc.score_median)
    components.render_result_summary(
        eyebrow="Result · Monte-Carlo",
        score=mc.score_median,
        stats=[
            {"label": "Median score", "value": f"{mc.score_median:+.2f}",
             "color": color},
            {"label": "Win rate", "value": f"{mc.win_rate_attacker:.0%}",
             "sub": "attacker"},
            {"label": "95% interval",
             "value": f"{mc.score_ic95_low:+.2f} → {mc.score_ic95_high:+.2f}"},
        ],
    )
    components.render_score_formula_expander()

    if mc.scores:
        fig = go.Figure()
        components.add_score_verdict_bands(fig, axis="x")
        fig.add_trace(go.Histogram(x=mc.scores, nbinsx=40, name="Score distribution"))
        fig.add_vline(x=mc.score_median, line_dash="dash",
                       annotation_text=f"Median {mc.score_median:+.3f}")
        fig.add_vline(x=mc.score_ic95_low, line_color="orange", opacity=0.5,
                       annotation_text="2.5%")
        fig.add_vline(x=mc.score_ic95_high, line_color="orange", opacity=0.5,
                       annotation_text="97.5%")
        fig.update_layout(
            xaxis_title="Battle score", yaxis_title="Trial count",
            margin=dict(l=10, r=10, t=10, b=10), height=300,
        )
        components.apply_plotly_theme(fig, dark=components.is_dark_mode())
        st.plotly_chart(fig, width="stretch")


def _round_chart(result, initial_att: dict, initial_def: dict) -> go.Figure:
    rounds_x = list(range(len(result.rounds) + 1))
    att_curves = {st: [initial_att[st]] for st in SquadType.all()}
    def_curves = {st: [initial_def[st]] for st in SquadType.all()}
    for r in result.rounds:
        for st in SquadType.all():
            att_curves[st].append(max(0, att_curves[st][-1] - r.kills_on_attacker.get(st, 0)))
            def_curves[st].append(max(0, def_curves[st][-1] - r.kills_on_defender.get(st, 0)))

    fig = go.Figure()
    palette = {SquadType.INFANTRY: "#7c3aed", SquadType.CAVALRY: "#0891b2", SquadType.ARCHER: "#16a34a"}
    for st in SquadType.all():
        fig.add_trace(go.Scatter(x=rounds_x, y=att_curves[st], name=f"Att {st.value}",
                                   line=dict(color=palette[st], width=2)))
        fig.add_trace(go.Scatter(x=rounds_x, y=def_curves[st], name=f"Def {st.value}",
                                   line=dict(color=palette[st], width=2, dash="dash")))
    fig.update_layout(
        xaxis_title="Round", yaxis_title="Troops alive",
        margin=dict(l=10, r=10, t=10, b=10), height=400,
        legend=dict(orientation="h", yanchor="top", y=-0.2),
    )
    return fig
