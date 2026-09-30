from __future__ import annotations

from functools import lru_cache
from itertools import product

import streamlit as st

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.data.reference import (
    MYTHIC_HEROES, EPIC_HEROES, NON_COMBAT_FIRST_SKILL_HEROES,
    HERO_GENERATION, hero_class,
)
from kingshot_sim.domain.enums import RNGMode, SquadType, TriggerKind
from kingshot_sim.domain.heroes import Hero
from kingshot_sim.engine.compile import compile_fighter
from kingshot_sim.engine.resolver import (
    collect_active_effects, compute_skill_mod, _expected_value_effect,
)
from kingshot_sim.webui import components, runtime_stats


_INF_LEADERS = tuple(sorted(h for h in MYTHIC_HEROES if hero_class(h) == "Inf"))
_CAV_LEADERS = tuple(sorted(h for h in MYTHIC_HEROES if hero_class(h) == "Cav"))
_ARC_LEADERS = tuple(sorted(h for h in MYTHIC_HEROES if hero_class(h) == "Arc"))
_JOINERS = tuple(sorted((MYTHIC_HEROES | EPIC_HEROES) - NON_COMBAT_FIRST_SKILL_HEROES))

_MAX_GEN = max(HERO_GENERATION.values())
_CLS_BY_KEY = {"inf": "Inf", "cav": "Cav", "arc": "Arc"}

_OFF_VAR = "var(--ks-success)"
_DEF_VAR = "var(--ks-cav)"

_OP_ORDER = (101, 102, 103, 211, 212, 111, 112, 113, 201, 202, 203)
_OP_GROUP = {
    101: "Lethality up", 102: "Attack up", 103: "Skill damage up",
    211: "Enemy damage taken up", 212: "Enemy defense down",
    111: "Damage taken down", 112: "Defense up", 113: "Health up",
    201: "Enemy damage down", 202: "Enemy attack down", 203: "Enemy lethality down",
}
_OP_PHRASE = {
    101: "+{v}% Lethality", 102: "+{v}% Attack", 103: "+{v}% Skill damage",
    211: "+{v}% enemy damage taken", 212: "-{v}% enemy defense",
    111: "-{v}% damage taken", 112: "+{v}% Defense", 113: "+{v}% Health",
    201: "-{v}% enemy damage", 202: "-{v}% enemy attack", 203: "-{v}% enemy Lethality",
}


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _fmt_pct(v: float) -> str:
    v = abs(v)
    return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def _effects_phrase(effects) -> str:
    parts = [_OP_PHRASE.get(e.op, f"{e.value:+.0f}%").format(v=_fmt_pct(e.value))
             for e in effects if e.op]
    return ", ".join(parts)


@lru_cache(maxsize=None)
def _joiner_primary_op(hero: str) -> int:
    try:
        sk = Hero(name=hero, level="MAX", widget_level=0).first_skill()
    except Exception:
        return 0
    return sk.effects[0].op if (sk and sk.effects) else 0


@lru_cache(maxsize=None)
def _joiner_effect_text(hero: str) -> str:
    try:
        sk = Hero(name=hero, level="MAX", widget_level=0).first_skill()
    except Exception:
        return ""
    if not sk or not sk.effects:
        return ""
    raw = _effects_phrase(sk.effects)
    if sk.trigger.kind == TriggerKind.PASSIVE:
        return raw
    exp = _expected_value_effect(sk)
    avg = _effects_phrase(exp) if exp else raw
    chance = sk.trigger.chance
    if chance:
        return f"{int(round(chance * 100))}% chance of {raw} (about {avg} on average)"
    return f"{raw} when active (about {avg} on average)"


_NUM_OPS = frozenset({101, 102, 103, 211, 212})
_DEN_OPS = frozenset({111, 112, 113, 201, 202, 203})


@lru_cache(maxsize=None)
def _joiner_ops(hero: str) -> frozenset[int]:
    try:
        sk = Hero(name=hero, level="MAX", widget_level=0).first_skill()
    except Exception:
        return frozenset()
    return frozenset(e.op for e in sk.effects if e.op) if (sk and sk.effects) else frozenset()


@lru_cache(maxsize=None)
def _joiner_type(hero: str) -> str:
    ops = _joiner_ops(hero)
    num, den = bool(ops & _NUM_OPS), bool(ops & _DEN_OPS)
    if num and den:
        return "Mixed"
    return "Defensive" if den else "Offensive"


@lru_cache(maxsize=None)
def _joiner_is_rng(hero: str) -> bool:
    try:
        sk = Hero(name=hero, level="MAX", widget_level=0).first_skill()
    except Exception:
        return False
    return bool(sk and sk.trigger.kind != TriggerKind.PASSIVE)


@lru_cache(maxsize=None)
def _acquire_rank(hero: str) -> tuple[int, int, str]:
    from kingshot_sim.data.reference import EPIC_HEROES
    return (0 if hero in EPIC_HEROES else 1, HERO_GENERATION.get(hero) or 0, hero)


def _gen_leaders(pool: tuple[str, ...], gen: int) -> tuple[str, ...]:
    return tuple(h for h in pool if HERO_GENERATION.get(h, 99) <= gen)


def _gen_joiners(gen: int) -> tuple[str, ...]:
    return tuple(h for h in _JOINERS if HERO_GENERATION.get(h) is None
                 or HERO_GENERATION[h] <= gen)


def _build_fighter(
    label: str, inf: str, cav: str, arc: str,
    joiners: tuple[str, ...], widget_on: bool,
) -> Fighter:
    wl = 10 if widget_on else 0
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name=inf, level="MAX", widget_level=wl),
        leader_cav=LeaderHero(hero_name=cav, level="MAX", widget_level=wl),
        leader_arc=LeaderHero(hero_name=arc, level="MAX", widget_level=wl),
        joiners=tuple(JoinerHero(hero_name=h, level="MAX") for h in joiners),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _states_and_effects(fighter: Fighter, side: str):
    state = compile_fighter(fighter, side=side)
    eff = collect_active_effects(state, 0, RNGMode.EXPECTED)
    return state, eff


def _directional(att_state, att_eff, def_state, def_eff) -> tuple[dict, float]:
    squads = SquadType.all()
    per_class = {
        asq: _mean(compute_skill_mod(att_eff, def_eff, asq, def_state.squad(dsq))
                   for dsq in squads)
        for asq in squads
    }
    return per_class, _mean(per_class.values())


def matchup_skillmods(your: Fighter, enemy: Fighter) -> dict:
    a_state, a_eff = _states_and_effects(your, "rally")
    d_state, d_eff = _states_and_effects(enemy, "defender")
    you, you_mean = _directional(a_state, a_eff, d_state, d_eff)
    enemy, enemy_mean = _directional(d_state, d_eff, a_state, a_eff)
    return {"you": you, "enemy": enemy,
            "you_mean": you_mean, "enemy_mean": enemy_mean}


def _fighter_from_dict(label: str, sd: dict) -> Fighter:
    return _build_fighter(label, sd["inf"], sd["cav"], sd["arc"],
                          tuple(sd["joiners"]), sd["widget"])


def find_best_counter(
    optimize: str, off: dict, deff: dict, gen: int,
    top_trios: int = 6, fixed_leaders: tuple[str, str, str] | None = None,
) -> dict:
    inf_pool = _gen_leaders(_INF_LEADERS, gen)
    cav_pool = _gen_leaders(_CAV_LEADERS, gen)
    arc_pool = _gen_leaders(_ARC_LEADERS, gen)
    join_pool = _gen_joiners(gen)

    if optimize == "off":
        fixed_state, fixed_eff = _states_and_effects(
            _fighter_from_dict("fixed-def", deff), "defender")
        opt_side = "rally"
    else:
        fixed_state, fixed_eff = _states_and_effects(
            _fighter_from_dict("fixed-off", off), "rally")
        opt_side = "defender"

    n_evals = 0

    def evaluate(inf: str, cav: str, arc: str, joiners: tuple[str, ...]):
        nonlocal n_evals
        n_evals += 1
        cand = _build_fighter("cand", inf, cav, arc, joiners, True)
        c_state, c_eff = _states_and_effects(cand, opt_side)
        _, off_sm = _directional(c_state, c_eff, fixed_state, fixed_eff)
        _, ctr_sm = _directional(fixed_state, fixed_eff, c_state, c_eff)
        score = off_sm - ctr_sm
        return score, off_sm, ctr_sm

    if fixed_leaders is not None:
        trios = [(0.0, *fixed_leaders)]
    else:
        trios = []
        for inf, cav, arc in product(inf_pool, cav_pool, arc_pool):
            score, _, _ = evaluate(inf, cav, arc, ())
            trios.append((score, inf, cav, arc))
        trios.sort(key=lambda t: t[0], reverse=True)
        trios = trios[:top_trios]

    best = None
    for _s0, inf, cav, arc in trios:
        chosen: list[str] = []
        score, off_sm, ctr_sm = evaluate(inf, cav, arc, ())
        while len(chosen) < 4:
            step_best = None
            for h in join_pool:
                s, o, c = evaluate(inf, cav, arc, tuple(chosen + [h]))
                rank = _acquire_rank(h)
                better = step_best is None or s > step_best[0] + 1e-9 or (
                    abs(s - step_best[0]) <= 1e-9 and rank < step_best[4])
                if better:
                    step_best = (s, o, c, h, rank)
            if step_best is None or step_best[0] <= score + 1e-12:
                break
            score, off_sm, ctr_sm, h, _rank = step_best
            chosen.append(h)
        cand = {"inf": inf, "cav": cav, "arc": arc, "widget": True,
                "joiners": chosen, "score": score, "net": off_sm - ctr_sm,
                "off_sm": off_sm, "ctr_sm": ctr_sm}
        if best is None or cand["score"] > best["score"]:
            best = cand

    if best is not None:
        best["n_evals"] = n_evals
    return best


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("sm_gen", _MAX_GEN)
    ss.setdefault("sm_active", "off")
    ss.setdefault("sm_off", {"inf": "Amadeus", "cav": "Petra", "arc": "Marlin",
                             "widget": True, "joiners": ["Chenko", "Amane"]})
    ss.setdefault("sm_def", {"inf": "Eric", "cav": "Hilde", "arc": "Jaeger",
                             "widget": True, "joiners": []})


def _portrait_block(hero: str, cls: str, size: int, count: int = 0) -> str:
    ring = "var(--ks-success)" if count > 0 else "transparent"
    badge = (f'<span style="position:absolute;top:-5px;right:-5px;'
             f'background:var(--ks-success);color:#06240f;border-radius:9px;'
             f'min-width:18px;height:18px;padding:0 3px;font-size:11px;'
             f'line-height:18px;text-align:center;font-weight:800;">x{count}</span>'
             ) if count > 0 else ""
    return (
        '<div style="text-align:center;">'
        f'<div style="position:relative;display:inline-block;padding:2px;'
        f'border-radius:10px;border:2px solid {ring};">'
        f'{components.hero_portrait_html(hero, size=size, cls=cls)}{badge}</div>'
        f'<div style="font-size:11px;font-weight:600;color:var(--ks-text);'
        f'margin-top:3px;line-height:1.1;">{hero}</div></div>'
    )


def _side_banner(active: str) -> None:
    is_off = active == "off"
    accent = _OFF_VAR if is_off else _DEF_VAR
    label = "OFFENSIVE RALLY" if is_off else "DEFENSIVE GARRISON"
    note = ("The side that attacks." if is_off
            else "The side that holds and counterattacks.")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:16px;padding:20px 24px;'
        f'border-radius:14px;border:2px solid {accent};border-left:10px solid {accent};'
        f'background:color-mix(in srgb, {accent} 18%, var(--ks-surface-alt));'
        f'margin:6px 0 18px;box-shadow:var(--ks-shadow-card);">'
        f'<span style="font-weight:900;color:{accent};font-size:1.9rem;'
        f'letter-spacing:.03em;line-height:1.05;">{label}</span>'
        f'<span style="color:var(--ks-text-muted);font-size:13.5px;'
        f'margin-left:auto;max-width:230px;text-align:right;">{note}</span></div>',
        unsafe_allow_html=True,
    )


def _section_label(text: str, accent: str, margin: str = "2px 0 6px") -> None:
    st.markdown(
        f'<div style="font-size:11px;font-weight:700;letter-spacing:.06em;'
        f'text-transform:uppercase;color:{accent};margin:{margin};">{text}</div>',
        unsafe_allow_html=True)


def _leader_grid(side: str, sd: dict, gen: int, accent: str) -> None:
    _section_label("Leader trio", accent)
    cols = st.columns(3)
    for col, key in zip(cols, ("inf", "cav", "arc")):
        klass = _CLS_BY_KEY[key]
        pool = _gen_leaders({"inf": _INF_LEADERS, "cav": _CAV_LEADERS,
                             "arc": _ARC_LEADERS}[key], gen)
        wkey = f"sm_{side}_{key}"
        chosen = st.session_state.get(wkey)
        if chosen not in pool:
            chosen = sd[key] if sd[key] in pool else pool[0]
            st.session_state.pop(wkey, None)
        with col:
            st.markdown(_portrait_block(chosen, klass, 56), unsafe_allow_html=True)
            sd[key] = st.selectbox(klass, pool, index=pool.index(chosen), key=wkey)


def _joiner_grid(side: str, sd: dict, gen: int, accent: str) -> None:
    from collections import Counter
    pool = set(_gen_joiners(gen))
    sd["joiners"] = [h for h in sd["joiners"] if h in pool]
    sel = sd["joiners"]
    counts = Counter(sel)
    full = len(sel) >= 4
    _section_label(f"Joiners ({len(sel)}/4)", accent, margin="14px 0 2px")

    st.markdown(
        f'<div style="font-size:11px;font-weight:700;letter-spacing:.06em;'
        f'text-transform:uppercase;color:{accent};margin:6px 0 4px;">'
        f'&#10003; Your joiners ({len(sel)}/4)</div>', unsafe_allow_html=True)
    box = st.container(border=True)
    with box:
        if sel:
            cols = st.columns(4)
            for i, (col, hero) in enumerate(zip(cols, sel)):
                with col:
                    st.markdown(_portrait_block(hero, hero_class(hero), 44),
                                unsafe_allow_html=True)
                    if st.button("Remove", key=f"sm_{side}_rm_{i}",
                                 type="primary", width="stretch"):
                        sd["joiners"].pop(i)
                        st.rerun()
        else:
            st.caption("No joiners picked yet. Add up to four from the roster below.")

    _section_label("Add from the roster", "var(--ks-text-muted)",
                   margin="16px 0 4px")
    st.caption("Click Add to include a hero. The same hero can be added more "
               "than once (Chenko x4); chance-based skills do not stack across "
               "copies.")
    fc1, fc2 = st.columns(2)
    with fc1:
        ftype = st.radio(
            "Effect", ["All", "Offensive", "Defensive", "Mixed"],
            horizontal=True, key="sm_jf_type")
    with fc2:
        fproc = st.radio(
            "Trigger", ["All", "Fixed", "RNG"],
            horizontal=True, key="sm_jf_proc")

    visible = [h for h in sorted(pool)
               if (ftype == "All" or _joiner_type(h) == ftype)
               and (fproc == "All" or _joiner_is_rng(h) == (fproc == "RNG"))]
    if not visible:
        st.caption("No joiners match the filter.")
        return
    by_op: dict[int, list[str]] = {}
    for h in visible:
        by_op.setdefault(_joiner_primary_op(h), []).append(h)

    def _tiles(heroes: list[str]) -> None:
        ncols = 4
        for i in range(0, len(heroes), ncols):
            cols = st.columns(ncols)
            for col, hero in zip(cols, heroes[i:i + ncols]):
                cnt = counts.get(hero, 0)
                with col:
                    st.markdown(_portrait_block(hero, hero_class(hero), 44,
                                                count=cnt),
                                unsafe_allow_html=True)
                    if st.button("Add", key=f"sm_{side}_jb_{hero}",
                                 type="primary" if cnt else "secondary",
                                 width="stretch", disabled=full,
                                 help=_joiner_effect_text(hero)):
                        if len(sd["joiners"]) < 4:
                            sd["joiners"].append(hero)
                        st.rerun()

    ordered_ops = list(_OP_ORDER) + [op for op in by_op if op not in _OP_ORDER]
    for op in ordered_ops:
        heroes = by_op.get(op)
        if heroes:
            _section_label(_OP_GROUP.get(op, "Other"), "var(--ks-text-muted)",
                           margin="12px 0 4px")
            _tiles(heroes)


def _side_editor() -> None:
    ss = st.session_state
    gen = ss["sm_gen"]
    active = ss["sm_active"]
    sd = ss["sm_off"] if active == "off" else ss["sm_def"]
    accent = _OFF_VAR if active == "off" else _DEF_VAR

    _side_banner(active)
    sd["widget"] = st.checkbox(
        "Widgets active (max level)", value=sd["widget"],
        key=f"sm_{active}_widget",
        help="On = each leader's widget at level 10. Widget expedition skills "
             "are side-scoped, so offensive widgets only fire on the rally and "
             "defensive ones on the garrison.")
    _leader_grid(active, sd, gen, accent)
    _inline_find_best(active, sd, accent)
    _joiner_grid(active, sd, gen, accent)


def _inline_find_best(active: str, sd: dict, accent: str) -> None:
    ss = st.session_state
    opp = "defensive garrison" if active == "off" else "offensive rally"
    _section_label("Find the best counter", accent, margin="16px 0 2px")
    st.caption(f"Hold your leaders and search the joiners that give this side "
               f"the strongest net SkillMod trade (its hit minus the counter it "
               f"takes) against the current {opp}, within the generation filter. "
               f"This can bring defensive joiners into an attack to win the "
               f"overall exchange.")
    if st.button("Suggest best joiners", key=f"sm_{active}_find"):
        fixed = (sd["inf"], sd["cav"], sd["arc"])
        with st.spinner("Searching joiners..."):
            best = find_best_counter(active, ss["sm_off"], ss["sm_def"],
                                     ss["sm_gen"], fixed_leaders=fixed)
        try:
            runtime_stats.increment_total_sims()
            runtime_stats.add_total_battles(int(best.get("n_evals", 0)) if best else 0)
        except Exception:
            pass
        if best:
            sd["joiners"] = list(best["joiners"])
            ss[f"sm_{active}_findinfo"] = {"off": best["off_sm"], "net": best["net"]}
        st.rerun()
    info = ss.get(f"sm_{active}_findinfo")
    if info:
        st.caption(f"Applied below. This side's SkillMod x{info['off']:.2f} "
                   f"(net {info['net']:+.2f}).")


def _verdict_html(you: float, enemy: float) -> str:
    win = you > enemy * 1.02
    lose = you < enemy * 0.98
    if win:
        label, var = "Offense has the SkillMod advantage", _OFF_VAR
    elif lose:
        label, var = "Defense has the SkillMod advantage", _DEF_VAR
    else:
        label, var = "No clear SkillMod advantage", "var(--ks-text-muted)"
    return (
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'gap:10px;flex-wrap:wrap;padding:13px 18px;border-radius:11px;'
        f'border:1px solid {var};background:color-mix(in srgb, {var} 10%, '
        f'var(--ks-surface-alt));margin:6px 0 14px;">'
        f'<span style="font-weight:800;font-size:1.1rem;color:{var};">{label}</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:.85rem;'
        f'color:var(--ks-text-muted);">offense x{you:.2f} vs defense x{enemy:.2f}</span></div>'
    )


def _per_class_table(res: dict) -> str:
    def _cell(v: float) -> str:
        return (f'<td style="padding:7px 12px;text-align:right;'
                f'font-family:\'JetBrains Mono\',monospace;font-size:13px;'
                f'color:var(--ks-text);">x{v:.3f}</td>')

    def _th(label: str, align: str = "right") -> str:
        return (f'<th style="padding:8px 12px;text-align:{align};font-size:11px;'
                f'font-weight:600;letter-spacing:.06em;text-transform:uppercase;'
                f'color:var(--ks-text-muted);">{label}</th>')

    rows = ""
    for sq in SquadType.all():
        rows += (
            '<tr style="border-top:1px solid var(--ks-border);">'
            f'<td style="padding:7px 12px;font-weight:600;color:var(--ks-text);">{sq.value}</td>'
            + _cell(res["you"][sq]) + _cell(res["enemy"][sq]) + '</tr>'
        )
    head = _th("Class", "left") + _th("offense to defense") + _th("defense to offense")
    return (
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="background:var(--ks-surface-alt);">{head}</tr></thead>'
        f'<tbody>{rows}</tbody></table>'
    )


def _render_results() -> None:
    ss = st.session_state
    off = _fighter_from_dict("Offense", ss["sm_off"])
    deff = _fighter_from_dict("Defense", ss["sm_def"])
    try:
        res = matchup_skillmods(off, deff)
    except Exception as e:
        st.error(f"Could not resolve this matchup: {e}")
        return

    st.markdown(_verdict_html(res["you_mean"], res["enemy_mean"]),
                unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    dyou = (res["you_mean"] - 1) * 100
    denemy = (res["enemy_mean"] - 1) * 100
    with m1:
        _section_label("Offensive rally", _OFF_VAR, margin="0 0 2px")
        st.metric("hits the defense", f"x{res['you_mean']:.2f}", f"{dyou:+.0f}% dmg")
    with m2:
        _section_label("Defensive garrison", _DEF_VAR, margin="0 0 2px")
        st.metric("counterattacks", f"x{res['enemy_mean']:.2f}",
                  f"{denemy:+.0f}% dmg", delta_color="inverse")
    st.caption(
        "The defensive side's DefenseUp and enemy-attack-down shrink the "
        f"offense's x{res['you_mean']:.2f}; the offensive side's debuffs shrink "
        f"the defense's x{res['enemy_mean']:.2f} counterattack. Both sides need "
        "offense and defense.")

    with st.expander("Per-class detail"):
        st.markdown(
            "Each row is one attacking class (mean over the three enemy "
            "squads). Class-targeted skills make these diverge; the headline "
            "is the mean across all three.")
        st.markdown(_per_class_table(res), unsafe_allow_html=True)


def _side_switcher() -> None:
    ss = st.session_state
    c1, c2 = st.columns(2)
    for col, key, label in ((c1, "off", "OFFENSIVE RALLY"),
                            (c2, "def", "DEFENSIVE GARRISON")):
        with col:
            if st.button(label, key=f"sm_switch_{key}", width="stretch",
                         type="primary" if ss["sm_active"] == key else "secondary"):
                ss["sm_active"] = key
                st.rerun()


def render() -> None:
    _init_state()
    ss = st.session_state

    components.render_page_header(
        title="SkillMod calculator",
        sub="Build an offensive rally and a defensive garrison, then read the "
            "hidden SkillMod multiplier both ways: your hit on them, and their "
            "counterattack on you.")

    ss["sm_gen"] = st.slider("Generation filter", 1, _MAX_GEN,
                             value=ss["sm_gen"], key="sm_gen_slider",
                             help="Limits leaders and joiners to heroes up to "
                                  "this generation. Epics are always available.")
    _side_switcher()

    st.markdown("---")
    _side_editor()
    st.markdown("---")
    components.render_subheading("Result")
    _render_results()


__all__ = ["render", "matchup_skillmods", "find_best_counter"]
