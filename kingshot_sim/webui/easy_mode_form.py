from __future__ import annotations
import io
from pathlib import Path
from dataclasses import replace
from typing import Any

import streamlit as st
from PIL import Image

from ..config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero,
)
from ..config.buffs import (
    Buffs,
    MOOSE_LEVEL_PCT, GRIZZLY_LEVEL_PCT, RHINO_LEVEL_PCT,
    PANTHER_LEVEL_PCT, ELEPHANT_LEVEL_PCT, LION_LEVEL_PCT,
)
from ..easy_mode.peeling import (
    VisibleAggregate, PeelingContext, EnemyScreenshotDebuffs,
    peel_visible_to_bonus_vector, widget_expedition_pct_by_stat,
)
from ..config.buffs import (
    GRIZZLY_LEVEL_PCT, GRIZZLY_MAX_LEVEL,
    MOOSE_LEVEL_PCT, MOOSE_MAX_LEVEL,
    TURRET_LEVEL_PCT, TURRET_MAX_LEVEL,
)
from ..easy_mode.ocr import ocr_battle_report, OCRResult
from ..easy_mode.ocr_troops import ocr_troops, TroopOCRResult
from ..easy_mode.ocr_buffs import (
    ocr_buffs, merge_buff_results, BuffOCRResult, BuffAggregate,
)
from ..data.reference import (
    valid_tiers, valid_tier_tg_pairs, make_tier_label, parse_tier_label,
)
from .forms import (
    leader_form, joiners_form, troops_form, empty_fighter,
    _troop_inputs_to_group, _troop_max_tier, _troop_tg_options,
)


_ASSETS = Path(__file__).parent / "assets"
_EXAMPLE_SCREENSHOT = _ASSETS / "easy_mode_example.png"


def easy_mode_fighter_form(
    default: Fighter,
    key_prefix: str,
    side: str = "attacker",
) -> Fighter:
    state = _quiz_state(key_prefix)

    hdr_cols = st.columns([5, 1])
    with hdr_cols[0]:
        label = st.text_input(
            "Fighter label",
            value=default.label,
            key=f"{key_prefix}_em_label",
            label_visibility="collapsed",
        )
    with hdr_cols[1]:
        if st.button("↻ Reset quiz", key=f"{key_prefix}_em_reset",
                       width="stretch",
                       help="Clear all answers and start the quiz over."):
            _reset_quiz(key_prefix)
            st.rerun()

    st.caption(
        "**Easy mode**. Upload a battle-report screenshot OR type your "
        "values in by hand (same result). Answer a few questions and we'll "
        "peel your account-wide bonuses and pre-fill them below."
    )

    _render_stepper(state)


    _render_p1(key_prefix, state)
    _render_p2(key_prefix, state)
    _render_p3(key_prefix, state)
    _render_q1(key_prefix, state)
    _render_q2(key_prefix, state)
    _render_q3(key_prefix, state)
    _render_q4(key_prefix, state, default)
    _render_q5(key_prefix, state, default)
    _render_q6_summary(key_prefix, state, label, default)

    _autoscroll_on_step_change(key_prefix, state)

    is_complete = state.get("q6_done", False)
    st.session_state[f"{key_prefix}_easy_complete"] = is_complete
    return replace(default, label=label)


def _quiz_state(key_prefix: str) -> dict:
    skey = f"{key_prefix}_easy_quiz"
    if skey not in st.session_state:
        st.session_state[skey] = {}
    return st.session_state[skey]


def _reset_quiz(key_prefix: str) -> None:
    skey = f"{key_prefix}_easy_quiz"
    st.session_state[skey] = {}
    st.session_state.pop(f"{key_prefix}_easy_complete", None)


def _step_header(label: str, done: bool, key: str, locked: bool = False,
                 anchor_id: str | None = None) -> bool:
    if locked:
        return False
    if done:
        cols = st.columns([5, 1])
        with cols[0]:
            st.markdown(f"**{label}**")
        with cols[1]:
            if st.button("Edit", key=f"{key}_edit",
                           width="stretch"):
                st.session_state[f"{key}_editing"] = True
                st.rerun()
        if st.session_state.get(f"{key}_editing", False):
            return True
        return False
    if anchor_id is not None:
        st.markdown(f'<a id="{anchor_id}"></a>', unsafe_allow_html=True)
    st.markdown(f"**{label}**")
    return True


def _scroll_anchor(anchor_id: str) -> None:
    st.markdown(f'<a id="{anchor_id}"></a>', unsafe_allow_html=True)


def _scroll_to(anchor_id: str) -> None:
    import streamlit.components.v1 as components
    components.html(
        f"""
        <script>
        setTimeout(function() {{
            const targetId = "{anchor_id}";
            try {{
                const el = window.parent.document.getElementById(targetId);
                if (el) {{
                    // block:'center' lands the next step mid-viewport so the
                    // eye doesn't lose it at the very top of the page (the
                    // old block:'start' jumped it flush to the top).
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    return;
                }}
            }} catch (e) {{ /* same-origin issues */ }}
            try {{
                window.parent.location.hash = '#' + targetId;
            }} catch (e) {{ /* sandboxed */ }}
        }}, 120);
        </script>
        """,
        height=0,
    )


def _buffs_captured_from_ocr(state: dict) -> bool:
    agg = state.get("buffs_ocr_agg")
    return bool(agg is not None and getattr(agg, "lines", None))


def _active_step(state: dict) -> str:
    if not state.get("p1_done"):  return "p1"
    if not state.get("p2_done"):  return "p2"
    if state.get("p2_role") == "attacking" and not state.get("p3_done"):
        return "p3"
    if not state.get("q1_done"):  return "q1"
    ocr_buffs = _buffs_captured_from_ocr(state)
    if (state.get("p2_role") == "defending" and not state.get("q2_done")
            and not ocr_buffs):
        return "q2"
    if not state.get("q3_done") and not ocr_buffs:
        return "q3"
    if not state.get("q4_done"):  return "q4"
    if not state.get("q5_done"):  return "q5"
    if not state.get("q6_done"):  return "q6"
    return "done"


_STEP_LABELS = {
    "p1": "Which side", "p2": "Attack or defend", "p3": "Rally or solo",
    "q1": "Screenshots / values", "q2": "Territory", "q3": "Active buffs",
    "q4": "Your trio", "q5": "Joiners", "q6": "Review & finish",
}


def _applicable_steps(state: dict) -> list[str]:
    steps = ["p1", "p2"]
    if state.get("p2_role") == "attacking":
        steps.append("p3")
    steps.append("q1")
    ocr_buffs = _buffs_captured_from_ocr(state)
    if state.get("p2_role") == "defending" and not ocr_buffs:
        steps.append("q2")
    if not ocr_buffs:
        steps.append("q3")
    steps += ["q4", "q5", "q6"]
    return steps


def _render_stepper(state: dict) -> None:
    steps = _applicable_steps(state)
    current = _active_step(state)
    total = len(steps)
    if current == "done":
        idx = total
        label = "Done"
    else:
        idx = (steps.index(current) + 1) if current in steps else 1
        label = _STEP_LABELS.get(current, current)
    pct = max(6, min(100, round(idx / total * 100)))
    st.markdown(
        f'<div style="margin:4px 0 12px;">'
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:baseline;font-size:12px;color:var(--ks-text-muted);'
        f'margin-bottom:4px;">'
        f'<span style="font-weight:600;color:var(--ks-text);">'
        f'Step {idx} / {total}</span>'
        f'<span>{label}</span></div>'
        f'<div style="height:5px;border-radius:999px;'
        f'background:var(--ks-surface-muted);overflow:hidden;">'
        f'<div style="height:5px;width:{pct}%;background:var(--ks-accent);'
        f'border-radius:999px;transition:width .2s ease;"></div></div></div>',
        unsafe_allow_html=True,
    )


def _autoscroll_on_step_change(key_prefix: str, state: dict) -> None:
    current = _active_step(state)
    last = state.get("_last_active_step")
    state["_last_active_step"] = current
    if last is not None and current != last and current != "done":
        _scroll_to(f"{key_prefix}_anchor_{current}")


def _commit_step(state: dict, step_key: str, edit_key: str | None = None) -> None:
    state[step_key] = True
    if edit_key is not None:
        st.session_state.pop(f"{edit_key}_editing", None)


def _render_p1(key_prefix: str, state: dict) -> None:
    step_key = "p1_done"
    edit_key = f"{key_prefix}_em_p1"
    show = _step_header("P1. Which side of the screenshot are you importing?",
                          state.get(step_key, False), edit_key,
                          anchor_id=f"{key_prefix}_anchor_p1")
    if not show:
        if state.get(step_key):
            chosen = "Left (me)" if state.get("p1_side") == "left" else "Right (opponent)"
            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {chosen}", unsafe_allow_html=True)
        return
    side_choice = st.radio(
        "Side",
        ["Left (me)", "Right (opponent)"],
        index=0 if state.get("p1_side", "left") == "left" else 1,
        horizontal=True,
        key=f"{edit_key}_radio",
        label_visibility="collapsed",
    )
    if st.button("Continue →", key=f"{edit_key}_btn", type="primary"):
        state["p1_side"] = "left" if side_choice.startswith("Left") else "right"
        _commit_step(state, step_key, edit_key)
        st.rerun()


def _render_p2(key_prefix: str, state: dict) -> None:
    step_key = "p2_done"
    edit_key = f"{key_prefix}_em_p2"
    locked = not state.get("p1_done", False)
    show = _step_header(
        "P2. Was this fighter attacking or defending in the screenshot?",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_p2",
    )
    if not show:
        if state.get(step_key):
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {state.get('p2_role', '').capitalize()}",
                unsafe_allow_html=True,
            )
        return
    role = st.radio(
        "Role",
        ["Attacking", "Defending"],
        index=0 if state.get("p2_role", "attacking") == "attacking" else 1,
        horizontal=True,
        key=f"{edit_key}_radio",
        label_visibility="collapsed",
    )
    if st.button("Continue →", key=f"{edit_key}_btn", type="primary"):
        new_role = role.lower()
        old_role = state.get("p2_role")
        state["p2_role"] = new_role
        if old_role != new_role:
            if state.get("p3_auto"):
                state["p3_done"] = False
                state.pop("was_rally", None)
                state.pop("p3_auto", None)
            if state.get("q2_auto"):
                state["q2_done"] = False
                state.pop("in_territory", None)
                state.pop("q2_auto", None)
        _commit_step(state, step_key, edit_key)
        st.rerun()


def _render_p3(key_prefix: str, state: dict) -> None:
    if state.get("p2_role") == "defending":
        if not state.get("p3_done"):
            state["was_rally"] = False
            state["p3_done"] = True
            state["p3_auto"] = True
        return

    step_key = "p3_done"
    edit_key = f"{key_prefix}_em_p3"
    locked = not state.get("p2_done", False)
    show = _step_header(
        "P3. Was this attack a rally or a solo march?",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_p3",
    )
    if not show:
        if state.get(step_key):
            label = "Rally" if state.get("was_rally") else "Solo march"
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {label}",
                unsafe_allow_html=True,
            )
        return
    choice = st.radio(
        "Mode",
        ["Rally (alliance group attack)", "Solo march (lone)"],
        index=0 if state.get("was_rally", True) else 1,
        horizontal=True,
        key=f"{edit_key}_radio",
        label_visibility="collapsed",
    )
    if st.button("Continue →", key=f"{edit_key}_btn", type="primary"):
        state["was_rally"] = choice.startswith("Rally")
        _commit_step(state, step_key, edit_key)
        st.rerun()


_EXAMPLE_ROSTER_SCREENSHOT = _ASSETS / "easy_mode_roster_example.png"
_EXAMPLE_BUFFS_SCREENSHOT  = _ASSETS / "easy_mode_buffs_example.png"
_EXAMPLE_OWNED_ROSTER_SCREENSHOT = _ASSETS / "easy_mode_roster_owned_example.png"


def _render_q1(key_prefix: str, state: dict, *, include_troops: bool = True) -> None:
    step_key = "q1_done"
    edit_key = f"{key_prefix}_em_q1"
    if state.get("p2_role") == "defending":
        locked = not state.get("p2_done", False)
    else:
        locked = not state.get("p3_done", False)
    show = _step_header(
        "Q1. Upload your battle-report screenshots",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_q1",
    )
    if not show:
        if state.get(step_key):
            v = state.get("visible_dict", {})
            sample = list(v.items())[:3]
            sample_str = ", ".join(f"{k}={float(val):.1f}%" for k, val in sample)
            n_stats = len(v)
            has_troops = "troops" in state
            badges = []
            if n_stats:
                badges.append(f"{n_stats}/12 stat cells")
            if has_troops:
                badges.append("troops ✓")
            badge_str = " · ".join(badges) or "no data captured"
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {badge_str}",
                unsafe_allow_html=True,
            )
        return

    ocr_side = state.get("p1_side", "left")
    n_steps = 3 if include_troops else 2

    _render_q1a_stats(key_prefix, state, edit_key, ocr_side,
                      step_label=f"Step 1 / {n_steps}")

    if include_troops:
        if state.get("q1a_done"):
            st.markdown("---")
            _render_q1b_roster(key_prefix, state, edit_key, ocr_side,
                               step_label="Step 2 / 3")
        troops_done = bool(state.get("q1b_done"))
    else:
        troops_done = True

    if state.get("q1a_done") and troops_done:
        st.markdown("---")
        _render_q1c_buffs(key_prefix, state, edit_key, ocr_side,
                          step_label="Step 3 / 3" if include_troops else "Step 2 / 2")

    if state.get("q1a_done") and troops_done and state.get("q1c_done"):
        if not state.get(step_key):
            _commit_step(state, step_key, edit_key)
            st.rerun()


def _render_q1a_stats(key_prefix: str, state: dict, edit_key: str, ocr_side: str,
                      *, step_label: str = "Step 1 / 3") -> None:
    sub_key = "q1a_done"
    sub_edit_key = f"{edit_key}_a"
    show = _step_header(
        f"{step_label}. Stats screenshot",
        state.get(sub_key, False), sub_edit_key, locked=False,
    )
    if not show:
        if state.get(sub_key):
            v = state.get("visible_dict", {})
            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {len(v)}/12 stat cells captured",
                       unsafe_allow_html=True)
        return

    st.caption(
        "The in-game page showing the 12 percentage bonuses (Infantry / "
        "Cavalry / Archer × Attack / Defense / Lethality / Health). The "
        "'Stat Bonuses' header at the top and 'Archer Health' as the last "
        "row must both be visible."
    )

    left, right = st.columns([3, 2])
    with left:
        upload = st.file_uploader(
            "Upload stats screenshot (PNG/JPG)",
            type=["png", "jpg", "jpeg"],
            key=f"{sub_edit_key}_upload",
        )
        st.caption("No screenshot? **Type it in. Same result.** "
                   "Use the button below to skip straight to manual entry.")
    with right:
        _render_upload_preview(
            upload, _EXAMPLE_SCREENSHOT,
            example_caption="Stat Bonuses panel with all 12 rows visible.",
        )

    with left:
        stats_res = None
        img_for_debug = None
        if upload is not None:
            try:
                img_for_debug = Image.open(upload)
                with st.spinner("Reading stats screenshot…"):
                    stats_res = ocr_battle_report(img_for_debug, side=ocr_side)
            except Exception as e:
                st.error(f"Failed to read stats screenshot: {e}")

        if stats_res is not None:
            st.markdown("---")
            confirmed = _render_q1_stats_confirm(
                state, stats_res, sub_edit_key, debug_img=img_for_debug,
            )
            if confirmed:
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()
        else:
            if st.button("Enter values manually. Same result",
                           key=f"{sub_edit_key}_skip", type="primary",
                           width="stretch"):
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()


def _render_q1b_roster(key_prefix: str, state: dict, edit_key: str, ocr_side: str,
                       *, step_label: str = "Step 2 / 3") -> None:
    sub_key = "q1b_done"
    sub_edit_key = f"{edit_key}_b"
    show = _step_header(
        f"{step_label}. Troops screenshot",
        state.get(sub_key, False), sub_edit_key, locked=False,
    )
    if not show:
        if state.get(sub_key):
            badge = "troops ✓" if "troops" in state else "skipped"
            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {badge}",
                       unsafe_allow_html=True)
        return

    st.caption(
        "The **Troop Power Comparison** page. We read your troop tiers, levels "
        "and counts from it. Your **leaders and their gear are set by hand in "
        "Q4** (we don't auto-read those: the battle report isn't reliable enough "
        "and a wrong guess is worse than a quick manual pick). If the Master "
        "Comparison panel is shown above it, it's ignored automatically."
    )

    left, right = st.columns([3, 2])
    with left:
        upload = st.file_uploader(
            "Upload the Troop Power Comparison screenshot (PNG/JPG)",
            type=["png", "jpg", "jpeg"],
            key=f"{sub_edit_key}_upload",
        )
    with right:
        _render_upload_preview(
            upload, _EXAMPLE_ROSTER_SCREENSHOT,
            example_caption="The Troop Power Comparison rows (Infantry / "
                            "Cavalry / Archer) with the counts beneath.",
        )

    with left:
        troops_res = None
        img_for_debug = None
        if upload is not None:
            try:
                img_for_debug = Image.open(upload)
                with st.spinner("Reading troops…"):
                    try:
                        troops_res = ocr_troops(img_for_debug, side=ocr_side)
                    except Exception as troops_err:
                        troops_res = TroopOCRResult(
                            error=f"Troop OCR failed: {troops_err}"
                        )
            except Exception as e:
                st.error(f"Failed to read troops screenshot: {e}")

        if troops_res is not None:
            st.markdown("---")
            confirmed = _render_q1_troops_confirm(
                state, troops_res, sub_edit_key, debug_img=img_for_debug,
            )
            if confirmed:
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()
        else:
            if st.button("Skip. I'll enter troops by hand later",
                           key=f"{sub_edit_key}_skip"):
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()


_STAT_LABELS = {"atk": "Attack", "def": "Defense", "let": "Lethality", "hp": "Health"}


def _render_q1c_buffs(key_prefix: str, state: dict, edit_key: str, ocr_side: str,
                      *, step_label: str = "Step 3 / 3") -> None:
    sub_key = "q1c_done"
    sub_edit_key = f"{edit_key}_c"
    show = _step_header(
        f"{step_label}. Buffs screenshot(s)",
        state.get(sub_key, False), sub_edit_key, locked=False,
    )
    if not show:
        if state.get(sub_key):
            agg: BuffAggregate | None = state.get("buffs_ocr_agg")
            if agg is not None and agg.lines:
                st.caption(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;→ {len(agg.lines)} buff line(s) captured",
                    unsafe_allow_html=True)
            else:
                st.caption("&nbsp;&nbsp;&nbsp;&nbsp;→ skipped (buffs entered manually in Q3)",
                           unsafe_allow_html=True)
        return

    st.caption(
        "Open the battle report, tap the **(i)** next to **'Stat Bonuses'** to "
        "show the **'Notes on Special Bonuses'** popup, and screenshot it. The "
        "popup is long. If it doesn't fit on one screen, scroll and take "
        "**several** screenshots; upload them all and we'll combine + "
        "de-duplicate the overlapping lines."
    )

    left, right = st.columns([3, 2])
    with right:
        if _EXAMPLE_BUFFS_SCREENSHOT.exists():
            st.markdown("**Example of what we expect**")
            st.image(str(_EXAMPLE_BUFFS_SCREENSHOT),
                       caption="'Notes on Special Bonuses' popup. Your value "
                               "is the LEFT column; the opponent's is the right.",
                       width="stretch")
        else:
            st.markdown("**What we expect**")
            st.caption(
                "The 'Notes on Special Bonuses' popup: one line per bonus, "
                "your value on the left, the opponent's on the right."
            )

    with left:
        uploads = st.file_uploader(
            "Upload buff popup screenshot(s) (PNG/JPG). Multiple allowed",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"{sub_edit_key}_upload",
        )

        agg: BuffAggregate | None = None
        if uploads:
            results: list[BuffOCRResult] = []
            errored: list[str] = []
            with st.spinner(f"Reading {len(uploads)} buff screenshot(s)…"):
                for up in uploads:
                    try:
                        img = Image.open(up)
                        res = ocr_buffs(img, side=ocr_side)
                    except Exception as e:
                        res = BuffOCRResult(error=f"{up.name}: {e}")
                    if res.error:
                        errored.append(f"**{up.name}**: {res.error}")
                    results.append(res)
            for e in errored:
                st.warning(e)
            agg = merge_buff_results(results)

        if agg is not None and agg.lines:
            st.markdown("---")
            _render_buff_aggregate_preview(agg)
            st.warning(
                "These buffs are an **aggregate**. We can't tell which "
                "source (city / pet / turret / appointment) each came from. "
                "If you later edit buffs one-by-one in **Q3**, that will "
                "**overwrite** everything captured here."
            )
            if st.button("✓ Use these buffs", key=f"{sub_edit_key}_confirm",
                           type="primary"):
                state["buffs_ocr_agg"] = agg
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()
        else:
            if agg is not None and not agg.lines:
                st.info(
                    "No buff lines were parsed. Check the screenshot shows the "
                    "'Notes on Special Bonuses' popup, or skip and fill Q3 "
                    "manually."
                )
            if st.button("Skip. I'll set buffs manually in Q3",
                           key=f"{sub_edit_key}_skip"):
                state.pop("buffs_ocr_agg", None)
                _commit_step(state, sub_key, sub_edit_key)
                st.rerun()


def _render_buff_aggregate_preview(agg: "BuffAggregate") -> None:
    st.success(f"Captured {len(agg.lines)} buff line(s) (overlaps de-duplicated).")
    for w in agg.warnings:
        st.caption(f"{w}")

    rows = []
    for l in agg.lines:
        rows.append({
            "Buff": l.raw_label.strip(),
            "Applies to": "Enemy" if l.polarity == "enemy" else "My squads",
            "Stat": _STAT_LABELS.get(l.stat, l.stat),
            "Value": f"{l.value_pct:+.1f}%",
            "Review": "" if l.needs_review else "",
        })
    st.dataframe(rows, hide_index=True, width="stretch")

    net = []
    for stat in ("atk", "def", "let", "hp"):
        own = agg.own_get("inf", stat)
        enemy = agg.enemy_get("inf", stat)
        if own == 0.0 and enemy == 0.0:
            continue
        net.append({
            "Stat": _STAT_LABELS[stat],
            "My net buff": f"{own:+.1f}%",
            "Enemy net debuff": f"{enemy:+.1f}%",
        })
    if net:
        st.caption("Net totals (summed across all sources, applied to all squads):")
        st.dataframe(net, hide_index=True, width="stretch")


def _render_ocr_debug_expander(
    img,
    *,
    relevant_keywords: tuple[str, ...],
    errors: dict[str, str],
) -> None:
    with st.expander("Show OCR diagnostic details"):
        for label, err in errors.items():
            st.markdown(f"**{label}**: `{err}`")
        if img is None:
            st.caption(
                "No image available for diagnostic. Re-upload to inspect "
                "what Tesseract read."
            )
            return
        try:
            from ..easy_mode.ocr import debug_ocr_tokens
            tokens = debug_ocr_tokens(img)
        except Exception as e:
            st.warning(f"Could not run Tesseract on the upload: {e}")
            return
        st.markdown(
            f"**Tesseract returned {len(tokens)} tokens.** "
            f"Tokens containing any of {list(relevant_keywords)!s}:"
        )
        hits = [
            t for t in tokens
            if any(kw in t["text"].lower() for kw in relevant_keywords)
        ]
        if hits:
            import pandas as pd
            df = pd.DataFrame(
                [
                    {
                        "text": t["text"],
                        "conf": round(t["conf"], 1),
                        "x": t["x"],
                        "y": t["y"],
                    }
                    for t in sorted(hits, key=lambda t: t["y"])
                ]
            )
            st.dataframe(df, hide_index=True, width="stretch")
            st.caption(
                "**Reading tip**: tokens on roughly the same `y` line "
                "form a header phrase. If you see `Troop` and `Power` "
                "with very different `y` values (>80 px apart), the "
                "in-game UI may have rendered the phrase across "
                "two lines and Tesseract picked them up separately."
            )
        else:
            st.warning(
                "Tesseract couldn't find any tokens matching the expected "
                "keywords. This usually means the header text is too small, "
                "blurry, or partially covered (e.g. by a notification "
                "overlay). Try re-taking the screenshot without overlays."
            )
        with st.expander("Show all tokens (raw)"):
            import pandas as pd
            df_all = pd.DataFrame(
                [
                    {"text": t["text"], "conf": round(t["conf"], 1),
                     "x": t["x"], "y": t["y"]}
                    for t in tokens
                ]
            )
            st.dataframe(df_all, hide_index=True, width="stretch")


def _render_upload_preview(uploaded_file, example_path, example_caption: str) -> None:
    if uploaded_file is not None:
        st.markdown("**What you uploaded**")
        st.image(uploaded_file, width="stretch",
                 caption="Tap to inspect. Re-upload if it looks wrong.")
        return
    st.markdown("**Example of what we expect**")
    if example_path is not None and example_path.exists():
        st.image(str(example_path), caption=example_caption,
                 width="stretch")
    else:
        st.caption(example_caption)


def _render_q1_stats_confirm(
    state: dict,
    res: "OCRResult",
    edit_key: str,
    *,
    debug_img=None,
) -> bool:
    if not res.is_ok():
        st.error(f"Stats OCR couldn't parse the screenshot: {res.error}")
        _render_ocr_debug_expander(
            debug_img,
            relevant_keywords=("stat", "bonuses", "mail"),
            errors={"stats": res.error},
        )
        return st.button(
            "Continue without stats (I'll fill them manually)",
            key=f"{edit_key}_continue_fail",
        )

    for w in res.warnings:
        st.warning(w)
    if res.n_low_confidence > 0:
        st.warning(
            f"{res.n_low_confidence} cell(s) below confidence threshold. "
            "Confirm them in the table below."
        )
    st.success(f"Extracted {len(res.cells)} stat cells.")

    overridden: dict[str, float] = {}
    by_class: dict[str, list] = {"inf": [], "cav": [], "arc": []}
    for c in res.cells:
        by_class[c.klass].append(c)

    cols = st.columns(3)
    class_labels = {"inf": "Infantry", "cav": "Cavalry", "arc": "Archer"}
    stat_labels = {"atk": "Atk", "def": "Def", "let": "Let", "hp": "HP"}
    for col_idx, klass in enumerate(("inf", "cav", "arc")):
        with cols[col_idx]:
            st.markdown(f"**{class_labels[klass]}**")
            for c in by_class[klass]:
                flag = " " if c.needs_review else ""
                val = st.number_input(
                    f"{stat_labels[c.stat]}{flag} ({c.confidence:.0f}% conf)",
                    value=float(c.value_pct),
                    min_value=0.0,
                    max_value=10000.0,
                    step=0.1,
                    format="%.1f",
                    key=f"{edit_key}_cell_{klass}_{c.stat}",
                )
                overridden[f"{klass}_{c.stat}_pct"] = float(val)

    if st.button("✓ Confirm stats & continue", key=f"{edit_key}_confirm",
                   type="primary"):
        state["visible_dict"] = overridden
        return True
    return False


def _render_q1_troops_confirm(
    state: dict,
    troops_res: "TroopOCRResult | None",
    edit_key: str,
    *,
    debug_img=None,
) -> bool:
    if troops_res is not None and troops_res.is_ok():
        st.success(f"Found {len(troops_res.cells)} troop slot(s).")
    else:
        err = troops_res.error if troops_res else "no troops result"
        st.warning(f"Troops not detected: {err}")
        _render_ocr_debug_expander(
            debug_img,
            relevant_keywords=("troop", "power", "comparison", "lv"),
            errors={"Troops": err},
        )

    troops_override = _render_q1_troops_section(troops_res, edit_key)

    if st.button("✓ Confirm troops & continue", key=f"{edit_key}_confirm",
                   type="primary"):
        if troops_override is not None:
            state["troops"] = troops_override
        return True
    return False


def _parse_level_label(level_label: str, max_tier: int) -> float:
    import re
    m = re.search(r"(\d{1,2}(?:\.\d)?)", str(level_label or ""))
    if not m:
        return float(max_tier)
    try:
        v = float(m.group(1))
    except ValueError:
        return float(max_tier)
    return max(1.0, min(float(max_tier), v))


def _render_q1_troops_section(
    troops_res: TroopOCRResult | None,
    edit_key: str,
) -> "TroopRoster | None":
    st.markdown("---")
    st.markdown("### Troops (from same screenshot)")

    if troops_res is None or not troops_res.is_ok():
        err = troops_res.error if troops_res else "no result"
        st.info(
            f"Troops couldn't be read automatically ({err}). You can edit "
            "them later in the Advanced Troops panel."
        )
        return None

    for w in troops_res.warnings:
        st.warning(w)
    if troops_res.n_low_confidence > 0:
        st.warning(
            f"{troops_res.n_low_confidence} troop slot(s) below confidence "
            "threshold. Please confirm tier and count below."
        )

    max_tier = _troop_max_tier()
    tg_options = _troop_tg_options()
    class_labels = {"inf": "Infantry", "cav": "Cavalry", "arc": "Archer"}

    cols = st.columns(3)
    by_class: dict[str, list] = {"inf": [], "cav": [], "arc": []}
    for c in troops_res.cells:
        by_class[c.klass].append(c)

    edited: dict[str, tuple[float, int, int]] = {}
    for col_idx, klass in enumerate(("inf", "cav", "arc")):
        with cols[col_idx]:
            st.markdown(f"**{class_labels[klass]}**")
            for c in by_class[klass]:
                flag = " " if c.needs_review else ""
                default_level = _parse_level_label(c.level_label, max_tier)
                level = st.number_input(
                    f"Level{flag}",
                    value=default_level, min_value=1.0, max_value=float(max_tier),
                    step=0.1, format="%.1f",
                    key=f"{edit_key}_troop_{klass}_lvl",
                    help=f"Detected Lv {c.level_label}, TG {c.star} "
                         f"(conf {c.confidence:.0f}%). Decimals interpolate "
                         "between tiers.",
                )
                tg_default = c.star if c.star in tg_options else 0
                tg = st.selectbox(
                    "TrueGold", tg_options,
                    index=tg_options.index(tg_default),
                    format_func=lambda x: "—" if x == 0 else f"TG{x}",
                    key=f"{edit_key}_troop_{klass}_tg",
                    help="TrueGold grade. The troop OCR can't always read the "
                         "badge, so please confirm.",
                )
                count = st.number_input(
                    "Count",
                    value=int(c.count), min_value=0, step=1000, format="%d",
                    key=f"{edit_key}_troop_{klass}_count",
                )
                edited[klass] = (float(level), int(tg), int(count))

    def _grp(k: str) -> tuple:
        if k not in edited:
            return ()
        lvl, tg, cnt = edited[k]
        g = _troop_inputs_to_group(lvl, tg, cnt)
        return (g,) if g is not None else ()

    try:
        roster = TroopRoster(
            infantry=_grp("inf"), cavalry=_grp("cav"), archer=_grp("arc"),
        )
    except ValueError as e:
        st.error(f"Invalid troop entry: {e}")
        return None
    return roster


def _render_q2(key_prefix: str, state: dict) -> None:
    if state.get("p2_role") == "attacking":
        if not state.get("q2_done"):
            state["in_territory"] = False
            state["q2_done"] = True
            state["q2_auto"] = True
        return

    if _buffs_captured_from_ocr(state):
        state["in_territory"] = False
        st.caption("Territory skipped. Captured from your buff screenshot.")
        return

    step_key = "q2_done"
    edit_key = f"{key_prefix}_em_q2"
    locked = not state.get("q1_done", False)
    show = _step_header(
        "Q2. Were you garrisoning in allied territory?",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_q2",
    )
    if not show:
        if state.get(step_key):
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {'Yes' if state.get('in_territory') else 'No'}",
                unsafe_allow_html=True,
            )
        return
    choice = st.radio(
        "In allied territory?",
        ["Yes (territory bonus +10% Atk/Def active)", "No"],
        index=0 if state.get("in_territory", False) else 1,
        horizontal=True,
        key=f"{edit_key}_radio",
        label_visibility="collapsed",
    )
    if st.button("Continue →", key=f"{edit_key}_btn", type="primary"):
        state["in_territory"] = choice.startswith("Yes")
        _commit_step(state, step_key, edit_key)
        st.rerun()


def _render_q3(key_prefix: str, state: dict) -> None:
    if _buffs_captured_from_ocr(state):
        st.caption("Buffs skipped. Captured from your buff screenshot "
                   "(edit the screenshot step to change them).")
        return

    step_key = "q3_done"
    edit_key = f"{key_prefix}_em_q3"
    if state.get("p2_role") == "defending":
        locked = not state.get("q2_done", False)
    else:
        locked = not state.get("q1_done", False)
    show = _step_header(
        "Q3. Active buffs at the time of the screenshot",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_q3",
    )
    if not show:
        if state.get(step_key):
            buffs = state.get("buffs", Buffs())
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {'no buffs' if buffs.is_empty() else 'buffs configured'}",
                unsafe_allow_html=True,
            )
        return

    st.caption(
        "Pick the buffs that were active **at the moment the screenshot was "
        "taken**. These will be peeled out of the visible aggregate so the "
        "simulator can re-apply them when running battles."
    )

    current = state.get("buffs", Buffs())
    _city_stat_labels = (
        "Attack", "Defense", "Lethality", "Health",
        "Enemy Attack Down", "Enemy Defense Down",
    )

    with st.expander("City buffs", expanded=False):
        qf = st.columns(2)
        with qf[0]:
            if st.button("Select all at +10%", key=f"{edit_key}_qf10"):
                for stat_label in _city_stat_labels:
                    st.session_state[f"{edit_key}_{stat_label}"] = 10
                st.rerun()
        with qf[1]:
            if st.button("Select all at +20%", key=f"{edit_key}_qf20"):
                for stat_label in _city_stat_labels:
                    st.session_state[f"{edit_key}_{stat_label}"] = 20
                st.rerun()

        c1, c2 = st.columns(2)
        def _city_pick(label: str, default_val: int) -> int:
            wkey = f"{edit_key}_{label}"
            current_val = st.session_state.get(wkey, default_val)
            try:
                idx = {0: 0, 10: 1, 20: 2}[int(current_val)]
            except KeyError:
                idx = 0
            sel = st.selectbox(
                label, [0, 10, 20], index=idx,
                key=wkey,
                format_func=lambda x: f"+{x}%" if x else "off",
            )
            return int(sel)

        with c1:
            city_atk = _city_pick("Attack",     current.city_atk)
            city_def = _city_pick("Defense",    current.city_def)
        with c2:
            city_let = _city_pick("Lethality",  current.city_let)
            city_hp  = _city_pick("Health",     current.city_hp)

    with st.expander("Pet active buffs", expanded=False):
        st.caption("Set a level (0 = pet inactive) for each pet that was active.")

        def _pet_row(label: str, table: dict, default_level: int, key: str) -> int:
            mx = max(table)
            wkey = f"{edit_key}_{key}"
            lvl = st.slider(label, 0, mx, default_level, key=wkey)
            if lvl > 0:
                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;Level {lvl} → +{table[lvl]}%",
                             unsafe_allow_html=True)
            return int(lvl)

        p1, p2 = st.columns(2)
        with p1:
            rhino    = _pet_row("Rhino (+Atk)",    RHINO_LEVEL_PCT,    current.rhino_level,   "rhino")
            lion     = _pet_row("Lion (+Def)",     LION_LEVEL_PCT,     current.lion_level,    "lion")
        with p2:
            panther  = _pet_row("Panther (+Let)",  PANTHER_LEVEL_PCT,  current.panther_level, "panther")
            elephant = _pet_row("Elephant (+HP)",  ELEPHANT_LEVEL_PCT, current.elephant_level,"elephant")

    with st.expander("Minister appointments", expanded=False):
        a1, a2, a3 = st.columns(3)
        with a1:
            fc = st.checkbox("Field Commander (+15% Let)",
                              value=current.appoint_field_commander,
                              key=f"{edit_key}_fc")
        with a2:
            mr = st.checkbox("Marshal (+5% Atk)",
                              value=current.appoint_marshal,
                              key=f"{edit_key}_mr")
        with a3:
            kg = st.checkbox("King (+5% to all 4)",
                              value=current.appoint_king,
                              key=f"{edit_key}_kg")

    with st.expander("Turrets", expanded=False):
        st.caption(
            "Turrets buff your Lethality. Non-linear: "
            "1=+8%, 2=+12%, 3=+15%, 4=+20%."
        )
        turret_key = f"{edit_key}_turrets"
        turret_default = int(st.session_state.get(turret_key, current.turrets))
        turrets = st.slider(
            "Turret count", 0, TURRET_MAX_LEVEL, turret_default, key=turret_key,
        )
        if turrets > 0:
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;{turrets} turret(s) → +"
                f"{TURRET_LEVEL_PCT[turrets]}% Lethality",
                unsafe_allow_html=True,
            )

    current_ed: EnemyScreenshotDebuffs = state.get(
        "enemy_debuffs", EnemyScreenshotDebuffs()
    )
    with st.expander("Enemy debuffs at screenshot time", expanded=False):
        st.caption(
            "If the opposing side was applying these debuffs to this fighter "
            "when the screenshot was taken, the visible stats are lower than "
            "the true bonuses. We'll divide them out alongside the active buffs "
            "when peeling. These values are used **once** for this import. "
            "They're not saved with the fighter."
        )
        ed_c1, ed_c2 = st.columns(2)
        def _ed_pick(label: str, default_val: int, key: str) -> int:
            wkey = f"{edit_key}_ed_{key}"
            current_val = st.session_state.get(wkey, default_val)
            try:
                idx = {0: 0, 10: 1, 20: 2}[int(current_val)]
            except KeyError:
                idx = 0
            sel = st.selectbox(
                label, [0, 10, 20], index=idx, key=wkey,
                format_func=lambda x: f"−{x}%" if x else "off",
            )
            return int(sel)

        with ed_c1:
            ed_atk = _ed_pick("Enemy City Attack Debuff",
                                current_ed.city_atk_down, "atk")
        with ed_c2:
            ed_def = _ed_pick("Enemy City Defense Debuff",
                                current_ed.city_def_down, "def")

        st.caption("Enemy pets affecting this fighter:")
        ep1, ep2 = st.columns(2)
        with ep1:
            ed_grizzly_key = f"{edit_key}_ed_grizzly"
            ed_grizzly_default = int(
                st.session_state.get(ed_grizzly_key, current_ed.grizzly_level)
            )
            ed_grizzly = st.slider(
                "Enemy Grizzly (−Let)", 0, GRIZZLY_MAX_LEVEL,
                ed_grizzly_default, key=ed_grizzly_key,
            )
            if ed_grizzly > 0:
                st.caption(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;Lvl {ed_grizzly} → "
                    f"−{GRIZZLY_LEVEL_PCT[ed_grizzly]}% Let",
                    unsafe_allow_html=True,
                )
        with ep2:
            ed_moose_key = f"{edit_key}_ed_moose"
            ed_moose_default = int(
                st.session_state.get(ed_moose_key, current_ed.moose_level)
            )
            ed_moose = st.slider(
                "Enemy Moose (−HP)", 0, MOOSE_MAX_LEVEL,
                ed_moose_default, key=ed_moose_key,
            )
            if ed_moose > 0:
                st.caption(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;Lvl {ed_moose} → "
                    f"−{MOOSE_LEVEL_PCT[ed_moose]}% HP",
                    unsafe_allow_html=True,
                )

    if st.button("✓ Confirm buffs", key=f"{edit_key}_confirm",
                   type="primary"):
        state["buffs"] = Buffs(
            city_let=city_let, city_atk=city_atk, city_def=city_def, city_hp=city_hp,
            city_enemy_atk_down=current.city_enemy_atk_down,
            city_enemy_def_down=current.city_enemy_def_down,
            moose_level=current.moose_level,
            grizzly_level=current.grizzly_level,
            rhino_level=rhino, panther_level=panther,
            elephant_level=elephant, lion_level=lion,
            appoint_field_commander=fc,
            appoint_marshal=mr,
            appoint_king=kg,
            turrets=int(turrets),
        )
        state["enemy_debuffs"] = EnemyScreenshotDebuffs(
            city_atk_down=ed_atk,
            city_def_down=ed_def,
            grizzly_level=int(ed_grizzly),
            moose_level=int(ed_moose),
        )
        _commit_step(state, step_key, edit_key)
        st.rerun()


def _render_q4(key_prefix: str, state: dict, default: Fighter) -> None:
    step_key = "q4_done"
    edit_key = f"{key_prefix}_em_q4"
    locked = not state.get("q3_done", False) and not _buffs_captured_from_ocr(state)
    show = _step_header(
        "Q4. Leader trio + per-hero gear",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_q4",
    )
    if not show:
        if state.get(step_key):
            trio = state.get("trio", (default.leader_inf, default.leader_cav, default.leader_arc))
            names = ", ".join(t.hero_name for t in trio)
            st.caption(
                f"&nbsp;&nbsp;&nbsp;&nbsp;→ {names}",
                unsafe_allow_html=True,
            )
        return

    st.caption(
        "Pick the 3 mythic leaders that fought, with their star level, "
        "T sub-tier, widget level, and gear pieces. This is a quick manual "
        "step. We don't auto-read leaders or gear from the battle report "
        "(it isn't reliable enough to trust)."
    )

    saved_trio: tuple[LeaderHero, LeaderHero, LeaderHero] | None = state.get("trio")
    if saved_trio:
        cur_inf, cur_cav, cur_arc = saved_trio
    else:
        cur_inf, cur_cav, cur_arc = (
            default.leader_inf, default.leader_cav, default.leader_arc,
        )

    inf = leader_form(label="Infantry leader", klass="Inf",
                          default=cur_inf, key_prefix=f"{edit_key}_inf")
    st.markdown("---")
    cav = leader_form(label="Cavalry leader", klass="Cav",
                          default=cur_cav, key_prefix=f"{edit_key}_cav")
    st.markdown("---")
    arc = leader_form(label="Archer leader", klass="Arc",
                          default=cur_arc, key_prefix=f"{edit_key}_arc")

    if st.button("✓ Confirm trio", key=f"{edit_key}_confirm", type="primary"):
        state["trio"] = (inf, cav, arc)
        _commit_step(state, step_key, edit_key)
        st.rerun()


def _render_q5(key_prefix: str, state: dict, default: Fighter) -> None:
    step_key = "q5_done"
    edit_key = f"{key_prefix}_em_q5"
    locked = not state.get("q4_done", False)
    show = _step_header(
        "Q5. Joiners (up to 4)",
        state.get(step_key, False), edit_key, locked=locked,
        anchor_id=f"{key_prefix}_anchor_q5",
    )
    if not show:
        if state.get(step_key):
            joiners = state.get("joiners", ())
            if joiners:
                names = ", ".join(j.hero_name for j in joiners)
                st.caption(
                    f"&nbsp;&nbsp;&nbsp;&nbsp;→ {len(joiners)} joiner(s): {names}",
                    unsafe_allow_html=True,
                )
            else:
                st.caption(
                    "&nbsp;&nbsp;&nbsp;&nbsp;→ no joiners",
                    unsafe_allow_html=True,
                )
        return

    st.caption(
        "Pick the up-to-4 joiners that contributed their first skill. "
        "Chance-based joiner skills don't stack. Duplicates of the same "
        "RNG joiner are wasted. Joiners with non-MAX first skill are skipped."
    )
    saved = state.get("joiners", default.joiners)
    joiners = joiners_form(saved, f"{edit_key}_joiners")

    c1, c2 = st.columns([3, 2])
    with c1:
        if st.button("✓ Confirm joiners", key=f"{edit_key}_confirm",
                       type="primary"):
            state["joiners"] = tuple(joiners)
            _commit_step(state, step_key, edit_key)
            st.rerun()
    with c2:
        skip_state_key = f"{edit_key}_skip_confirming"
        if st.button("Skip joiners…", key=f"{edit_key}_skip_btn",
                       width="stretch"):
            st.session_state[skip_state_key] = True
        if st.session_state.get(skip_state_key, False):
            st.warning(
                "Skipping joiners assumes **zero joiner contribution**. "
                "In practice, players rarely fight without meta joiners. "
                "You'll get more accurate results by entering at least "
                "Gordon, Chenko, Saul, Howard, or whichever typical "
                "joiners would have been in this fight."
            )
            sc1, sc2 = st.columns(2)
            with sc1:
                if st.button("Cancel", key=f"{edit_key}_skip_cancel",
                               width="stretch"):
                    st.session_state.pop(skip_state_key, None)
                    st.rerun()
            with sc2:
                if st.button("Skip anyway", key=f"{edit_key}_skip_ok",
                               type="primary",
                               width="stretch"):
                    state["joiners"] = ()
                    st.session_state.pop(skip_state_key, None)
                    _commit_step(state, step_key, edit_key)
                    st.rerun()


def _render_q6_summary(key_prefix: str, state: dict, label: str, default: Fighter) -> None:
    step_key = "q6_done"
    edit_key = f"{key_prefix}_em_q6"
    locked = not state.get("q5_done", False)
    if locked:
        return

    st.markdown("**Q6. Summary**")
    visible = _visible_from_state(state)
    ctx = _peeling_context_from_state(state)
    try:
        bv = peel_visible_to_bonus_vector(visible, ctx)
    except Exception as e:
        st.error(f"Peeling failed: {e}")
        return

    st.caption(
        "Peeled BonusVector. These are the account-wide stat bonuses "
        "the simulator will use for this Fighter (after subtracting your "
        "Section D buffs, territory, leader stats, widget stats and gear)."
    )
    cells = []
    for klass in ("inf", "cav", "arc"):
        row = {"Class": klass.upper()}
        for stat in ("atk", "def", "let", "hp"):
            row[stat.upper()] = f"{getattr(bv, f'{klass}_{stat}_pct'):.1f}%"
        cells.append(row)
    st.dataframe(cells, hide_index=True, width="stretch")

    if not state.get(step_key, False):
        if st.button("✓ Use these values & open the editor", key=f"{edit_key}_confirm",
                       type="primary"):
            peeled = _assemble_fighter(label, state, default)
            st.session_state[f"{key_prefix}_pending_import"] = peeled
            gen_key = f"{key_prefix}_form_gen"
            st.session_state[gen_key] = int(st.session_state.get(gen_key, 0)) + 1
            state[step_key] = True
            st.session_state[f"{key_prefix}_easy_complete"] = True
            st.session_state[f"{key_prefix}_scroll_to_banner"] = True
            st.rerun()
    else:
        st.success("Imported. Review or tweak the panels below.")


def _visible_from_state(state: dict) -> VisibleAggregate:
    return VisibleAggregate(**state["visible_dict"])


def _effective_buffs(state: dict) -> Buffs:
    buffs = state.get("buffs", Buffs())
    agg = state.get("buffs_ocr_agg")
    if agg is None or not getattr(agg, "lines", None):
        return buffs
    from dataclasses import replace
    trio = state.get("trio")
    net = (
        widget_expedition_pct_by_stat(
            trio, state.get("p2_role"), bool(state.get("was_rally", True))
        )
        if trio else {"atk": 0.0, "def": 0.0, "let": 0.0, "hp": 0.0}
    )
    return replace(
        buffs,
        ocr_own_atk_pct=max(0.0, agg.own_get("inf", "atk") - net["atk"]),
        ocr_own_def_pct=max(0.0, agg.own_get("inf", "def") - net["def"]),
        ocr_own_let_pct=max(0.0, agg.own_get("inf", "let") - net["let"]),
        ocr_own_hp_pct=max(0.0, agg.own_get("inf", "hp") - net["hp"]),
        ocr_enemy_atk_down_pct=-agg.enemy_get("inf", "atk"),
        ocr_enemy_def_down_pct=-agg.enemy_get("inf", "def"),
        ocr_enemy_let_down_pct=-agg.enemy_get("inf", "let"),
        ocr_enemy_hp_down_pct=-agg.enemy_get("inf", "hp"),
    )


def _peeling_context_from_state(
    state: dict, *, include_ocr_buffs: bool = True
) -> PeelingContext:
    trio = state["trio"]
    buffs = _effective_buffs(state) if include_ocr_buffs else state.get("buffs", Buffs())
    return PeelingContext(
        importee_role=state["p2_role"],
        was_rally=bool(state.get("was_rally", True)),
        is_garrisoning_territory=bool(state.get("in_territory", False)),
        leader_inf=trio[0],
        leader_cav=trio[1],
        leader_arc=trio[2],
        buffs=buffs,
        enemy_debuffs=state.get("enemy_debuffs", EnemyScreenshotDebuffs()),
    )


def _assemble_fighter(label: str, state: dict, default: Fighter) -> Fighter:
    visible = _visible_from_state(state)
    ctx = _peeling_context_from_state(state)
    bv = peel_visible_to_bonus_vector(visible, ctx)
    trio = state["trio"]
    return Fighter(
        label=label,
        leader_inf=trio[0],
        leader_cav=trio[1],
        leader_arc=trio[2],
        joiners=tuple(state.get("joiners", ())),
        bonuses=bv,
        troops=state.get("troops", default.troops),
        buffs=_effective_buffs(state),
    )


__all__ = [
    "easy_mode_fighter_form",
    "fighter_form_with_mode",
    "is_easy_mode",
    "easy_mode_rally_flag",
]


def is_easy_mode(key_prefix: str) -> bool:
    return st.session_state.get(f"{key_prefix}_input_mode", "Easy") == "Easy"


def easy_mode_rally_flag(key_prefix: str, default: bool = True) -> bool:
    quiz = st.session_state.get(f"{key_prefix}_easy_quiz", {})
    if not quiz.get("p3_done"):
        return default
    return bool(quiz.get("was_rally", default))


def fighter_form_with_mode(
    default: Fighter,
    key_prefix: str,
    side: str = "attacker",
    allow_easy_mode: bool = True,
) -> Fighter:
    if not allow_easy_mode:
        from .forms import fighter_form
        return fighter_form(default, key_prefix=key_prefix, side=side)

    toggle_key = f"{key_prefix}_input_mode"
    current = st.session_state.get(toggle_key, "Easy")
    mode = st.radio(
        "Input mode",
        ["Easy (upload screenshot)", "Advanced (manual entry)"],
        index=0 if current.startswith("Easy") else 1,
        horizontal=True,
        key=f"{toggle_key}_radio",
        label_visibility="collapsed",
    )
    st.session_state[toggle_key] = "Easy" if mode.startswith("Easy") else "Advanced"
    is_easy = mode.startswith("Easy")

    pending_key = f"{key_prefix}_pending_import"
    if pending_key in st.session_state:
        default = st.session_state.pop(pending_key)

    gen_key = f"{key_prefix}_form_gen"
    if gen_key not in st.session_state:
        st.session_state[gen_key] = 0
    gen = int(st.session_state[gen_key])
    effective_prefix = f"{key_prefix}_g{gen}"

    from .forms import fighter_form

    quiz_done = (
        st.session_state.get(f"{key_prefix}_easy_quiz", {}).get("q6_done", False)
        or bool(st.session_state.get(f"{key_prefix}_easy_complete", False))
    )

    if is_easy and not quiz_done:
        return easy_mode_fighter_form(default, key_prefix=key_prefix, side=side)

    if is_easy and quiz_done:
        banner_anchor = f"{key_prefix}_post_import_banner"
        st.markdown(f'<a id="{banner_anchor}"></a>', unsafe_allow_html=True)
        cols = st.columns([5, 1])
        with cols[0]:
            st.success("Imported from screenshot. Review or tweak the panels below.")
        with cols[1]:
            if st.button("Re-import", key=f"{key_prefix}_reimport",
                           width="stretch",
                           help="Discard the imported values and run the quiz again."):
                st.session_state[f"{key_prefix}_easy_quiz"] = {}
                st.session_state.pop(f"{key_prefix}_easy_complete", None)
                st.rerun()
        if st.session_state.pop(f"{key_prefix}_scroll_to_banner", False):
            _scroll_to(banner_anchor)

    return fighter_form(default, effective_prefix, side=side)


_BONUS_FIELDS: tuple[str, ...] = (
    "inf_atk_pct", "inf_def_pct", "inf_let_pct", "inf_hp_pct",
    "cav_atk_pct", "cav_def_pct", "cav_let_pct", "cav_hp_pct",
    "arc_atk_pct", "arc_def_pct", "arc_let_pct", "arc_hp_pct",
)

_BUFF_KEY_SUFFIXES: dict[str, str] = {
    "city_let":              "city_let",
    "city_atk":              "city_atk",
    "city_def":              "city_def",
    "city_hp":               "city_hp",
    "city_enemy_atk_down":   "city_enemy_atk_down",
    "city_enemy_def_down":   "city_enemy_def_down",
    "moose_level":           "moose",
    "grizzly_level":         "grizzly",
    "rhino_level":           "rhino",
    "panther_level":         "panther",
    "elephant_level":        "elephant",
    "lion_level":            "lion",
    "appoint_field_commander": "appoint_field_commander",
    "appoint_marshal":         "appoint_marshal",
    "appoint_king":            "appoint_king",
    "turrets":                 "turrets",
}


def _q4_default_fighter() -> Fighter:
    return Fighter(
        label="(peeling context)",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=0),),
            cavalry=(TroopGroup(tier="T10.5", count=0),),
            archer=(TroopGroup(tier="T10.5", count=0),),
        ),
    )


def searchspace_easy_import_complete(key_prefix: str) -> bool:
    return bool(
        st.session_state.get(f"{key_prefix}_ss_easy_quiz", {}).get("q6_done", False)
        or st.session_state.get(f"{key_prefix}_ss_easy_complete", False)
    )


def searchspace_easy_import_rally_flag(key_prefix: str, default: bool = True) -> bool | None:
    quiz = st.session_state.get(f"{key_prefix}_ss_easy_quiz", {})
    if not quiz.get("q6_done"):
        return None
    if quiz.get("p2_role") != "attacking":
        return None
    return bool(quiz.get("was_rally", default))


def searchspace_easy_import_reset(key_prefix: str) -> None:
    st.session_state[f"{key_prefix}_ss_easy_quiz"] = {}
    st.session_state.pop(f"{key_prefix}_ss_easy_complete", None)


def searchspace_easy_import_render(
    default_bv: BonusVector,
    default_buffs: Buffs,
    key_prefix: str,
    side: str,
    bonuses_widget_prefix: str,
    buffs_widget_prefix: str,
) -> None:
    state_key = f"{key_prefix}_ss_easy_quiz"
    if state_key not in st.session_state:
        st.session_state[state_key] = {}
    state = st.session_state[state_key]

    if "p2_role" not in state:
        state["p2_role"] = "attacking" if side == "attacker" else "defending"

    if not state.get("buffs"):
        state.setdefault("buffs_default", default_buffs)

    cols = st.columns([5, 1])
    with cols[0]:
        st.caption(
            "**Easy mode** for your roster. Upload a battle-report "
            "screenshot and we'll peel your account-wide bonuses + buffs "
            "into the panels below. Heroes you pick in Q4 are used "
            "**only** for the peeling math; the actual search pool is "
            "configured in the panels."
        )
    with cols[1]:
        if st.button("↻ Reset", key=f"{key_prefix}_ss_reset",
                       width="stretch"):
            searchspace_easy_import_reset(key_prefix)
            st.rerun()

    _render_p1(key_prefix, state)
    _render_p2(key_prefix, state)
    _render_p3(key_prefix, state)
    _render_q1(key_prefix, state, include_troops=False)
    _render_q2(key_prefix, state)
    _render_q3(key_prefix, state)

    _render_q4(key_prefix, state, _q4_default_fighter())

    if not state.get("q5_done"):
        state["joiners"] = ()
        state["q5_done"] = True

    _render_q6_searchspace(
        key_prefix=key_prefix,
        state=state,
        default_bv=default_bv,
        bonuses_widget_prefix=bonuses_widget_prefix,
        buffs_widget_prefix=buffs_widget_prefix,
    )

    _autoscroll_on_step_change(key_prefix, state)


def _render_q6_searchspace(
    key_prefix: str,
    state: dict,
    default_bv: BonusVector,
    bonuses_widget_prefix: str,
    buffs_widget_prefix: str,
) -> None:
    step_key = "q6_done"
    edit_key = f"{key_prefix}_em_q6_ss"
    locked = not state.get("q4_done", False)
    if locked:
        return

    st.markdown("**Q6. Summary**")
    try:
        visible = _visible_from_state(state)
        ctx = _peeling_context_from_state(state, include_ocr_buffs=False)
        bv = peel_visible_to_bonus_vector(visible, ctx)
    except Exception as e:
        st.error(f"Peeling failed: {e}")
        return

    cells = []
    for klass in ("inf", "cav", "arc"):
        row = {"Class": klass.upper()}
        for stat in ("atk", "def", "let", "hp"):
            row[stat.upper()] = f"{getattr(bv, f'{klass}_{stat}_pct'):.1f}%"
        cells.append(row)
    st.caption(
        "Peeled account-wide bonuses. These will populate the "
        "**Account stat bonuses** panel below. Buffs from Q3 will "
        "populate the **Your buffs** panel."
    )
    st.dataframe(cells, hide_index=True, width="stretch")

    if not state.get(step_key, False):
        if st.button("✓ Use these values & open the editor",
                       key=f"{edit_key}_confirm", type="primary"):
            for field in _BONUS_FIELDS:
                st.session_state[f"{bonuses_widget_prefix}_{field}"] = float(
                    getattr(bv, field)
                )
            buffs: Buffs = state.get("buffs", Buffs())
            for buff_field, key_suffix in _BUFF_KEY_SUFFIXES.items():
                widget_key = f"{buffs_widget_prefix}_buffs_{key_suffix}"
                st.session_state[widget_key] = getattr(buffs, buff_field)
            state[step_key] = True
            st.session_state[f"{key_prefix}_ss_easy_complete"] = True
            st.session_state[f"{key_prefix}_ss_scroll_to_banner"] = True
            st.rerun()
    else:
        st.success("Imported. Review the panels below.")


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_hero_roster_ocr(file_bytes: bytes):
    from ..easy_mode.ocr_hero_roster import ocr_hero_roster
    return ocr_hero_roster(Image.open(io.BytesIO(file_bytes)))


@st.cache_data(show_spinner=False, max_entries=8)
def _cached_gear_roster_ocr(file_bytes: bytes):
    from ..easy_mode.ocr_gear_roster import ocr_gear_roster
    return ocr_gear_roster(Image.open(io.BytesIO(file_bytes)))


def render_roster_import(
    key_prefix: str,
    inf_options, cav_options, arc_options, joiner_options,
) -> None:
    with st.expander("Import owned heroes from your roster screenshot (optional)",
                       expanded=False):
        st.caption(
            "Upload your in-game **Heroes** screen, sorted by **Quality** so "
            "owned heroes sit at the top. We detect which heroes you OWN "
            "(unlocked) and their star level, and pre-fill the pools + per-mythic "
            "levels below. Best-effort colour match, so review after applying."
        )
        if _EXAMPLE_OWNED_ROSTER_SCREENSHOT.exists():
            st.image(
                str(_EXAMPLE_OWNED_ROSTER_SCREENSHOT),
                caption="Example. The in-game 'Heroes' grid, sorted by "
                        "Quality so owned mythics sit at the top.",
                width=260,
            )
        ups = st.file_uploader(
            "Heroes screenshot(s). Multiple allowed",
            type=["png", "jpg", "jpeg"], accept_multiple_files=True,
            key=f"{key_prefix}_roster_upload",
        )
        if not ups:
            return
        owned: dict[str, tuple[int, int]] = {}
        with st.spinner(f"Reading {len(ups)} roster screenshot(s)…"):
            for f in ups:
                try:
                    res = _cached_hero_roster_ocr(f.getvalue())
                except Exception as e:
                    st.warning(f"{f.name}: {e}")
                    continue
                for cell in res.cells:
                    if cell.hero_name and cell.hero_name not in owned:
                        star = max(0, min(5, int(cell.star)))
                        sub = max(0, min(5, int(cell.sub_tier)))
                        owned[cell.hero_name] = (star, sub)
        if not owned:
            st.info(
                "No owned heroes detected. Make sure it's the 'Heroes' grid "
                "sorted by Quality, at full resolution (not a chat-app copy)."
            )
            return
        inf = [h for h in owned if h in inf_options]
        cav = [h for h in owned if h in cav_options]
        arc = [h for h in owned if h in arc_options]
        joiners = [h for h in owned if h in joiner_options]
        st.success(f"Detected {len(owned)} owned hero(es): " + ", ".join(sorted(owned)))
        st.caption(
            "Best-effort colour match (4 mythics have no reference image yet, "
            "so they may be missed or mis-named). Confirm the pools + per-mythic "
            "levels below."
        )
        if st.button("✓ Use these as my available heroes",
                       key=f"{key_prefix}_roster_apply_btn", type="primary"):
            st.session_state[f"{key_prefix}_inf"] = inf
            st.session_state[f"{key_prefix}_cav"] = cav
            st.session_state[f"{key_prefix}_arc"] = arc
            st.session_state[f"{key_prefix}_joiners"] = joiners
            for hero in inf + cav + arc:
                star, sub = owned[hero]
                lvl = "MAX" if star >= 5 else f"{star}_{sub}"
                st.session_state[f"{key_prefix}_lspec_{hero}_level"] = lvl
            st.session_state[f"{key_prefix}_show_adv"] = True
            st.success("✓ Applied your heroes and their star levels below.")


def render_gear_roster_import(classgear_prefix: str) -> None:
    from ..easy_mode.ocr_gear_roster import GEAR_CLASSES, GEAR_SLOTS

    with st.expander("Import gear from your Backpack screenshot (optional)",
                       expanded=False):
        st.caption(
            "Upload your in-game **Backpack → Gear** tab (it's sorted "
            "strongest-first by default, so one screenshot carries every "
            "leader's best loadout). We detect each class's best 4 pieces and "
            "pre-fill the per-class gear below. Class, slot and quality are "
            "reliable; **review the levels and mastery** after applying (a "
            "level-up arrow can hide a digit)."
        )
        up = st.file_uploader(
            "Backpack Gear screenshot",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{classgear_prefix}_gearroster_upload",
        )
        if not up:
            return
        with st.spinner("Reading your gear…"):
            try:
                res = _cached_gear_roster_ocr(up.getvalue())
            except Exception as e:
                st.error(f"Could not read that screenshot: {e}")
                return
        if not res.is_ok():
            st.error(res.error or "No gear detected. Upload the Backpack "
                     "'Gear' tab at full resolution (not a chat-app copy).")
            return
        n = sum(len(slots) for slots in res.loadouts.values())
        st.success(f"Detected {n} gear piece(s) across {len(res.loadouts)} class(es).")
        for w in res.warnings:
            st.warning(w)
        for cls in GEAR_CLASSES:
            parts = []
            for slot in GEAR_SLOTS:
                p = res.loadouts.get(cls, {}).get(slot)
                if p is None:
                    continue
                lvl = p.engine_level if p.engine_level is not None else "?"
                parts.append(f"{slot} · {p.quality} · L{lvl}")
            if parts:
                st.markdown(f"**{cls}**. " + "   ".join(parts))
        st.caption(
            "Best-effort: levels/mastery are hints. Confirm them in the "
            "Per-class gear editor below after applying."
        )
        if st.button("✓ Use this gear", type="primary",
                       key=f"{classgear_prefix}_gearroster_apply_btn"):
            for cls in GEAR_CLASSES:
                for slot in GEAR_SLOTS:
                    p = res.loadouts.get(cls, {}).get(slot)
                    if p is None:
                        continue
                    st.session_state[f"{classgear_prefix}_{cls}_{slot}_q"] = p.quality
                    if p.engine_level is not None:
                        st.session_state[f"{classgear_prefix}_{cls}_{slot}_lvl"] = int(p.engine_level)
                    if p.mastery is not None:
                        st.session_state[f"{classgear_prefix}_{cls}_{slot}_mast"] = int(p.mastery)
            st.success("✓ Applied. Review levels/mastery in 'Per-class gear' below.")


__all__.extend([
    "searchspace_easy_import_render",
    "searchspace_easy_import_complete",
    "searchspace_easy_import_rally_flag",
    "searchspace_easy_import_reset",
    "render_roster_import",
    "render_gear_roster_import",
])
