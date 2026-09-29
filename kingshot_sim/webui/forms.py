from __future__ import annotations
import math
from typing import Optional

import streamlit as st

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.data.reference import (
    MYTHIC_HEROES, EPIC_HEROES, HERO_CLASS,
    NON_COMBAT_FIRST_SKILL_HEROES, VALID_TIERS, LEVEL_FRACTION,
    valid_tiers, valid_tier_tg_pairs, make_tier_label, parse_tier_label,
    HERO_GENERATION, MAX_GENERATION, TIER_RANGE,
    max_skill_level, default_skill_levels,
)


def _skill_levels_subform(
    level: str,
    default_levels: tuple[int, int, int],
    key_prefix: str,
) -> tuple[int, int, int]:
    out: list[int] = []
    cols = st.columns(3)
    for i, slot in enumerate(("sk1", "sk2", "sk3")):
        cap = max_skill_level(level, slot)
        with cols[i]:
            if cap == 0:
                st.caption(f"{slot.upper()} —")
                out.append(0)
                continue
            saved = default_levels[i] if i < len(default_levels) else cap
            init = max(1, min(int(saved), cap))
            options = list(range(1, cap + 1))
            skey = f"{key_prefix}_{slot}_lvl"
            if skey in st.session_state:
                curr_val = st.session_state[skey]
                if isinstance(curr_val, int):
                    if curr_val > cap:
                        st.session_state[skey] = cap
                    elif curr_val < 1:
                        st.session_state[skey] = 1
            cur_in_state = st.session_state.get(skey)
            idx = options.index(cur_in_state) if cur_in_state in options else options.index(init)
            chosen = st.selectbox(
                f"{slot.upper()}",
                options,
                index=idx,
                key=skey,
            )
            out.append(int(chosen))
    return (out[0], out[1], out[2])


_INF_MYTHICS = tuple(sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Inf"))
_CAV_MYTHICS = tuple(sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Cav"))
_ARC_MYTHICS = tuple(sorted(h for h in MYTHIC_HEROES if HERO_CLASS[h] == "Arc"))
_JOINER_HEROES = tuple(sorted(
    (MYTHIC_HEROES | EPIC_HEROES) - NON_COMBAT_FIRST_SKILL_HEROES
))
_LEVEL_KEYS = list(LEVEL_FRACTION.keys())


def filter_heroes_by_max_gen(heroes: tuple[str, ...], max_gen: int) -> tuple[str, ...]:
    out: list[str] = []
    for h in heroes:
        gen = HERO_GENERATION.get(h)
        if gen is None or gen <= max_gen:
            out.append(h)
    return tuple(out)


def leader_form(
    label: str,
    klass: str,
    default: Optional[LeaderHero],
    key_prefix: str,
    mythics_filter: Optional[tuple[str, ...]] = None,
    roster: Optional[Any] = None,
    builds: Optional[dict[str, Any]] = None,
) -> LeaderHero:
    if klass == "Inf":
        choices = _INF_MYTHICS
    elif klass == "Cav":
        choices = _CAV_MYTHICS
    else:
        choices = _ARC_MYTHICS

    if mythics_filter is not None:
        filtered = tuple(h for h in choices if h in mythics_filter)
        choices = filtered if filtered else choices

    default_name = default.hero_name if default and default.hero_name in choices else choices[0]
    default_level = default.level if default else "MAX"
    default_widget = default.widget_level if default else 10
    default_skill = (
        default.skill_levels if (default and default.skill_levels is not None)
        else default_skill_levels(default_level)
    )

    st.markdown(f"**{label}**")
    cols = st.columns([2, 1, 1])
    with cols[0]:
        name = st.selectbox("Hero", choices,
                              index=choices.index(default_name),
                              key=f"{key_prefix}_name",
                              label_visibility="collapsed")

    # Detect hero switch and update level, widget, and skills
    hero_cache = st.session_state.setdefault(f"{key_prefix}_hero_cache", {})
    tracked_hero_key = f"{key_prefix}_tracked_hero"
    prev_hero = st.session_state.get(tracked_hero_key)

    effective_builds = builds
    if effective_builds is None and roster is not None and hasattr(roster, "builds"):
        effective_builds = roster.builds
    if effective_builds is None:
        act_name = st.session_state.get("_ks_active_roster")
        if act_name:
            try:
                from kingshot_sim.webui import persistence
                act_r = persistence.load_roster(act_name)
                effective_builds = act_r.builds
            except Exception:
                pass

    if prev_hero is None:
        st.session_state[tracked_hero_key] = name
        if name not in hero_cache:
            hero_cache[name] = {
                "level": default_level,
                "widget": default_widget,
                "skills": default_skill,
            }
    elif prev_hero != name:
        st.session_state[tracked_hero_key] = name
        if name in hero_cache:
            target = hero_cache[name]
        elif effective_builds and name in effective_builds:
            b = effective_builds[name]
            sl = b.skill_levels if b.skill_levels is not None else default_skill_levels(b.level)
            target = {"level": b.level, "widget": int(b.widget_level), "skills": sl}
            hero_cache[name] = target
        else:
            def_wl = 0 if name in EPIC_HEROES else 10
            target = {"level": "MAX", "widget": def_wl, "skills": default_skill_levels("MAX")}
            hero_cache[name] = target

        st.session_state[f"{key_prefix}_level"] = target["level"]
        st.session_state[f"{key_prefix}_widget"] = int(target["widget"])
        for s_idx, slot in enumerate(("sk1", "sk2", "sk3")):
            st.session_state[f"{key_prefix}_{slot}_lvl"] = target["skills"][s_idx]

    lvl_val = st.session_state.get(f"{key_prefix}_level", default_level)
    level_idx = _LEVEL_KEYS.index(lvl_val) if lvl_val in _LEVEL_KEYS else len(_LEVEL_KEYS) - 1
    with cols[1]:
        level = st.selectbox("Level", _LEVEL_KEYS, index=level_idx,
                              key=f"{key_prefix}_level")

    w_val = st.session_state.get(f"{key_prefix}_widget", default_widget)
    with cols[2]:
        widget = st.slider("Widget", 0, 10, int(w_val), key=f"{key_prefix}_widget")

    st.caption("Skill levels (capped by hero star)")
    cur_skills = (
        st.session_state.get(f"{key_prefix}_sk1_lvl", default_skill[0]),
        st.session_state.get(f"{key_prefix}_sk2_lvl", default_skill[1]),
        st.session_state.get(f"{key_prefix}_sk3_lvl", default_skill[2]),
    )
    skill_levels = _skill_levels_subform(level, cur_skills, key_prefix)

    hero_cache[name] = {
        "level": level,
        "widget": widget,
        "skills": skill_levels,
    }

    with st.expander(f"Gear contribution ({label})", expanded=False):
        gatk, gdef, glet, ghp, gear_dict = _gear_subform(
            default=default,
            key_prefix=key_prefix,
            klass=klass,
        )

    return LeaderHero(
        hero_name=name, level=level, widget_level=widget,
        skill_levels=skill_levels,
        gear_atk_pct=gatk, gear_def_pct=gdef, gear_let_pct=glet, gear_hp_pct=ghp,
        gear=gear_dict,
    )


_GEAR_SLOTS: tuple[str, ...] = ("head", "chest", "gloves", "boots")


def _gear_subform(
    default: Optional[LeaderHero],
    key_prefix: str,
    klass: str,
) -> tuple[float, float, float, float, dict[str, "HeroGearPiece"]]:
    from kingshot_sim.config.fighter import HeroGearPiece
    from kingshot_sim.data.gear import (
        piece_contribution, gearset_contribution,
        MYTHIC_MIN_LEVEL, MYTHIC_MAX_LEVEL,
        RED_MIN_LEVEL, RED_MAX_LEVEL,
    )

    st.caption(
        f"Configure each of the 4 pieces. Contributions apply to the "
        f"{klass} class only."
    )
    pieces: dict[str, HeroGearPiece] = {}
    hdr = st.columns([1, 1, 1, 1, 2])
    hdr[0].markdown("**Slot**")
    hdr[1].markdown("**Quality**")
    hdr[2].markdown("**Level**")
    hdr[3].markdown("**Mastery**")
    hdr[4].markdown("**Contribution**")

    for slot in _GEAR_SLOTS:
        existing = default.gear.get(slot) if (default and default.gear) else None
        cols = st.columns([1, 1, 1, 1, 2])
        cols[0].text(slot.capitalize())
        with cols[1]:
            default_quality = existing.quality if existing else "mythic"
            quality = st.selectbox(
                "Quality", ["mythic", "red"],
                index=0 if default_quality == "mythic" else 1,
                key=f"{key_prefix}_gear_{slot}_quality",
                label_visibility="collapsed",
            )
        with cols[2]:
            if quality == "mythic":
                lo, hi = MYTHIC_MIN_LEVEL, MYTHIC_MAX_LEVEL
                fallback = MYTHIC_MAX_LEVEL
            else:
                lo, hi = RED_MIN_LEVEL, RED_MAX_LEVEL
                fallback = RED_MIN_LEVEL
            if existing and lo <= existing.level <= hi:
                init_level = int(existing.level)
            else:
                init_level = fallback
            level = st.number_input(
                "Level", min_value=lo, max_value=hi, value=init_level,
                step=1, key=f"{key_prefix}_gear_{slot}_level",
                label_visibility="collapsed",
            )
        with cols[3]:
            mastery_init = int(existing.forge_mastery) if existing else 0
            mastery = st.number_input(
                "Mastery", min_value=0, max_value=30, value=mastery_init,
                step=1, key=f"{key_prefix}_gear_{slot}_mastery",
                label_visibility="collapsed",
                help="Forge mastery per piece. Each level adds +10% of the "
                       "base bonus (base × (1 + 0.1 × mastery)), routed to the "
                       "same stat as the base: Head/Boots → Lethality, "
                       "Chest/Gloves → Health. "
                       "Also gates ascension: ≥10 mythic→red, ≥15 for red L=200.",
            )
        try:
            pb = piece_contribution(slot, quality, int(level), int(mastery))
            preview_parts = []
            if pb.atk_pct: preview_parts.append(f"+{pb.atk_pct:.1f}% Atk")
            if pb.def_pct: preview_parts.append(f"+{pb.def_pct:.1f}% Def")
            if pb.let_pct: preview_parts.append(f"+{pb.let_pct:.1f}% Let")
            if pb.hp_pct:  preview_parts.append(f"+{pb.hp_pct:.1f}% HP")
            cols[4].caption(", ".join(preview_parts) if preview_parts else "—")
            pieces[slot] = HeroGearPiece(
                slot=slot, quality=quality, level=int(level),
                enhance=0, forge_mastery=int(mastery),
            )
        except ValueError as exc:
            cols[4].error(str(exc))

    if pieces:
        total = gearset_contribution(pieces)
        parts = []
        if total.atk_pct: parts.append(f"+{total.atk_pct:.1f}% Atk")
        if total.def_pct: parts.append(f"+{total.def_pct:.1f}% Def")
        if total.let_pct: parts.append(f"+{total.let_pct:.1f}% Let")
        if total.hp_pct:  parts.append(f"+{total.hp_pct:.1f}% HP")
        st.markdown(
            f"**Total: {', '.join(parts) if parts else '—'}** "
            f"(applied to {klass} class only)"
        )
    return 0.0, 0.0, 0.0, 0.0, pieces


def joiners_form(
    default: tuple[JoinerHero, ...],
    key_prefix: str,
    max_joiners: int = 4,
) -> tuple[JoinerHero, ...]:
    NONE_LABEL = "— None —"
    options = [NONE_LABEL] + list(_JOINER_HEROES)

    default_names = [j.hero_name for j in default[:max_joiners]]
    default_names += [NONE_LABEL] * (max_joiners - len(default_names))

    selected: list[str] = []
    cols = st.columns(min(max_joiners, 4))
    for i in range(max_joiners):
        col = cols[i % len(cols)]
        with col:
            d = default_names[i] if default_names[i] in options else NONE_LABEL
            choice = st.selectbox(
                f"Slot {i+1}",
                options,
                index=options.index(d),
                key=f"{key_prefix}_jslot_{i}",
            )
            selected.append(choice)

    return tuple(JoinerHero(hero_name=h, level="MAX")
                  for h in selected if h != NONE_LABEL)


def bonuses_form(default: BonusVector, key_prefix: str) -> BonusVector:
    st.caption(
        "Account-wide stat bonuses. Tech, charm, pet, masters, alliance tech, "
        "outposts, town skin, VIP, island, **governor gear**. "
        "**Do NOT include leader hero gear, widget, city buffs, or pet buffs "
        "here**. Those are added separately by the engine (gear and widget "
        "from the per-leader fields; city/pet buffs from the Buffs section)."
    )
    rows = ("squad", "inf", "cav", "arc")
    row_labels = {"squad": "All Squads", "inf": "Infantry", "cav": "Cavalry", "arc": "Archer"}
    stats = ("atk", "def", "let", "hp")
    stat_labels = {"atk": "Attack %", "def": "Defense %", "let": "Lethality %", "hp": "Health %"}

    out: dict[str, float] = {}
    cols = st.columns([1] + [1] * len(stats))
    cols[0].markdown("**Category**")
    for i, s in enumerate(stats, start=1):
        cols[i].markdown(f"**{stat_labels[s]}**")

    for r in rows:
        c = st.columns([1] + [1] * len(stats))
        c[0].markdown(f"**{row_labels[r]}**")
        for i, s in enumerate(stats, start=1):
            field = f"{r}_{s}_pct"
            default_val = float(getattr(default, field))
            out[field] = c[i].number_input(
                f"{r}_{s}",
                min_value=0.0, max_value=2000.0, value=default_val, step=5.0,
                key=f"{key_prefix}_{field}",
                label_visibility="collapsed",
            )

    return BonusVector(**out)


def _canonical_tier_options() -> list[str]:
    return [make_tier_label(t, g) for (t, g) in valid_tier_tg_pairs()]


def _normalize_tier_for_display(tier_label: str, options: list[str]) -> str:
    try:
        t, g = parse_tier_label(tier_label)
        canonical = make_tier_label(t, g)
        if canonical in options:
            return canonical
    except ValueError:
        pass
    return options[-1] if options else tier_label


def _troop_max_tier() -> int:
    pairs = valid_tier_tg_pairs()
    return max((t for t, _ in pairs), default=TIER_RANGE[1])


def _troop_tg_options() -> list[int]:
    pairs = valid_tier_tg_pairs()
    tgs = sorted({tg for _, tg in pairs} | {0})
    return tgs


def _troop_group_to_inputs(g: TroopGroup | None) -> tuple[float, int, int]:
    if g is None:
        return (float(_troop_max_tier()), 0, 0)
    tier_int, tg = parse_tier_label(g.tier)
    level = float(g.level) if g.level is not None else float(tier_int)
    return (level, int(tg), int(g.count))


def pool_tier_from_inputs(level: float, tg: int) -> tuple[str, float | None]:
    lo_t, hi_t = TIER_RANGE
    tier_int = max(lo_t, min(hi_t, int(math.floor(level + 0.5))))
    label = make_tier_label(tier_int, int(tg))
    is_whole = abs(level - round(level)) < 1e-9
    return label, (None if is_whole else float(level))


def _troop_inputs_to_group(level: float, tg: int, count: int) -> TroopGroup | None:
    if count <= 0:
        return None
    lo_t, hi_t = TIER_RANGE
    tier_int = max(lo_t, min(hi_t, int(math.floor(level + 0.5))))
    label = make_tier_label(tier_int, int(tg))
    is_whole = abs(level - round(level)) < 1e-9
    return TroopGroup(
        tier=label, count=int(count),
        level=None if is_whole else float(level),
    )


def _troop_class_editor(
    default_groups: tuple[TroopGroup, ...],
    key_prefix: str,
    squad_label: str,
) -> list[TroopGroup]:
    ids_key = f"{key_prefix}_rowids"
    next_key = f"{key_prefix}_nextid"
    max_tier = _troop_max_tier()
    tg_options = _troop_tg_options()

    if ids_key not in st.session_state:
        seed = list(default_groups) or [None]
        st.session_state[ids_key] = list(range(len(seed)))
        st.session_state[next_key] = len(seed)

    row_ids: list[int] = st.session_state[ids_key]

    seed_groups = list(default_groups)
    for i, rid in enumerate(row_ids):
        if f"{key_prefix}_{rid}_cnt" in st.session_state:
            continue
        g = seed_groups[i] if i < len(seed_groups) else None
        lvl, tg, cnt = _troop_group_to_inputs(g)
        st.session_state[f"{key_prefix}_{rid}_lvl"] = float(lvl)
        st.session_state[f"{key_prefix}_{rid}_tg"] = tg if tg in tg_options else 0
        st.session_state[f"{key_prefix}_{rid}_cnt"] = int(cnt)
    groups: list[TroopGroup] = []

    st.markdown(f"**{squad_label}**")
    hdr = st.columns([3, 2, 4, 1])
    hdr[0].caption("Level")
    hdr[1].caption("TrueGold")
    hdr[2].caption("Count")

    for rid in list(row_ids):
        c = st.columns([3, 2, 4, 1])
        level = c[0].number_input(
            "Level", min_value=1.0, max_value=float(max_tier), step=0.1,
            format="%.1f", key=f"{key_prefix}_{rid}_lvl",
            label_visibility="collapsed",
            help="In-game troop level, e.g. 10.5. Decimals interpolate between tiers.",
        )
        tg = c[1].selectbox(
            "TrueGold", tg_options,
            format_func=lambda x: "—" if x == 0 else f"TG{x}",
            key=f"{key_prefix}_{rid}_tg", label_visibility="collapsed",
        )
        count = c[2].number_input(
            "Count", min_value=0, max_value=10_000_000, step=10_000,
            format="%d", key=f"{key_prefix}_{rid}_cnt",
            label_visibility="collapsed",
        )
        if len(row_ids) > 1:
            if c[3].button("", key=f"{key_prefix}_{rid}_rm",
                           help="Remove this tier"):
                row_ids.remove(rid)
                for suf in ("_lvl", "_tg", "_cnt"):
                    st.session_state.pop(f"{key_prefix}_{rid}{suf}", None)
                st.rerun()
        try:
            g = _troop_inputs_to_group(float(level), int(tg), int(count))
        except ValueError as e:
            st.error(f"{squad_label}: {e}")
            g = None
        if g is not None:
            groups.append(g)

    if st.button(f"Add {squad_label.split(' ', 1)[-1].lower()} tier",
                 key=f"{key_prefix}_add"):
        new_id = st.session_state[next_key]
        st.session_state[next_key] += 1
        st.session_state[f"{key_prefix}_{new_id}_lvl"] = float(max_tier)
        st.session_state[f"{key_prefix}_{new_id}_tg"] = 0
        st.session_state[f"{key_prefix}_{new_id}_cnt"] = 0
        row_ids.append(new_id)
        st.rerun()

    return groups


def troops_form(
    default: TroopRoster,
    key_prefix: str,
    side: str = "own",
) -> TroopRoster:
    if side == "defender" or side == "enemy":
        st.caption("How many troops the **enemy** has per squad. Type the troop level (e.g. 10.5) and TrueGold; add rows for mixed tiers.")
    elif side == "attacker":
        st.caption("How many troops the **attacker** is sending per squad. Type the troop level (e.g. 10.5) and TrueGold; add rows for mixed tiers.")
    else:
        st.caption("How many troops per squad. Type the troop level (e.g. 10.5) and TrueGold; add rows for mixed tiers.")

    out_groups: dict[str, tuple[TroopGroup, ...]] = {}
    counts: dict[str, int] = {}

    for squad_label, attr in [
        ("Infantry", "infantry"),
        ("Cavalry", "cavalry"),
        ("Archers", "archer"),
    ]:
        groups = _troop_class_editor(
            getattr(default, attr), f"{key_prefix}_{attr}", squad_label,
        )
        out_groups[attr] = tuple(groups)
        counts[attr] = sum(g.count for g in groups)
        st.markdown("")

    total = sum(counts.values())
    if total > 0:
        st.caption(
            f"**Total: {total:,} troops**. "
            f"{counts['infantry']/total:.0%} Inf · "
            f"{counts['cavalry']/total:.0%} Cav · "
            f"{counts['archer']/total:.0%} Arc"
        )
    else:
        st.caption("No troops yet. Add at least 1 squad to simulate.")

    return TroopRoster(
        infantry=out_groups["infantry"],
        cavalry=out_groups["cavalry"],
        archer=out_groups["archer"],
    )


def buffs_form(default: "Buffs", key_prefix: str) -> "Buffs":
    from kingshot_sim.config.buffs import (
        Buffs, MOOSE_MAX_LEVEL, GRIZZLY_MAX_LEVEL, TIER1_PET_MAX_LEVEL,
        TURRET_MAX_LEVEL, TURRET_LEVEL_PCT,
    )
    st.caption(
        "**Multiplicative buffs**: applied directly to stat factors, "
        "OUTSIDE the SkillMod. City buffs are toggleable consumables "
        "(0/+10%/+20%). Pet buffs scale with pet skill level. "
        "Enemy debuffs reduce the OPPONENT's stat factors at damage-compute time."
    )

    st.markdown("**City buffs (own)**")
    cc = st.columns(4)
    options = [0, 10, 20]
    def _city_select(label: str, current: int, col, key_suffix: str) -> int:
        idx = options.index(current) if current in options else 0
        return col.selectbox(label, options, index=idx,
                              format_func=lambda v: f"+{v}%" if v else "off",
                              key=f"{key_prefix}_buffs_{key_suffix}")

    city_let = _city_select("Lethality",   int(default.city_let), cc[0], "city_let")
    city_atk = _city_select("Attack",      int(default.city_atk), cc[1], "city_atk")
    city_def = _city_select("Defense",     int(default.city_def), cc[2], "city_def")
    city_hp  = _city_select("Health",      int(default.city_hp),  cc[3], "city_hp")

    st.markdown("**City debuffs (on enemy)**")
    cd = st.columns(4)
    def _enemy_select(label: str, current: int, col, key_suffix: str) -> int:
        idx = options.index(current) if current in options else 0
        return col.selectbox(label, options, index=idx,
                              format_func=lambda v: f"-{v}%" if v else "off",
                              key=f"{key_prefix}_buffs_{key_suffix}")

    eatk = _enemy_select("Enemy Attack",  int(default.city_enemy_atk_down), cd[0], "city_enemy_atk_down")
    edef = _enemy_select("Enemy Defense", int(default.city_enemy_def_down), cd[1], "city_enemy_def_down")

    st.markdown("**Pet buff levels**")
    st.caption("Enter the level your pet has reached (each pet has its own max level).")
    pc = st.columns(3)
    moose    = pc[0].number_input("Moose level (−enemy HP · max 7)", 0, MOOSE_MAX_LEVEL,
                                    int(default.moose_level), step=1,
                                    key=f"{key_prefix}_buffs_moose")
    grizzly  = pc[1].number_input("Grizzly level (−enemy Let · max 8)", 0, GRIZZLY_MAX_LEVEL,
                                    int(default.grizzly_level), step=1,
                                    key=f"{key_prefix}_buffs_grizzly")
    rhino    = pc[2].number_input("Rhino level (+Atk · max 10)", 0, TIER1_PET_MAX_LEVEL,
                                    int(default.rhino_level), step=1,
                                    key=f"{key_prefix}_buffs_rhino")
    pc2 = st.columns(3)
    panther  = pc2[0].number_input("Black Panther level (+Let · max 10)", 0, TIER1_PET_MAX_LEVEL,
                                     int(default.panther_level), step=1,
                                     key=f"{key_prefix}_buffs_panther")
    elephant = pc2[1].number_input("Elephant level (+HP · max 10)", 0, TIER1_PET_MAX_LEVEL,
                                     int(default.elephant_level), step=1,
                                     key=f"{key_prefix}_buffs_elephant")
    lion     = pc2[2].number_input("Lion level (+Def · max 10)", 0, TIER1_PET_MAX_LEVEL,
                                     int(default.lion_level), step=1,
                                     key=f"{key_prefix}_buffs_lion")

    st.markdown("**Minister appointments**")
    st.caption(
        "Fixed-value boolean appointments. Each contributes a "
        "multiplicative buff alongside city/pet buffs."
    )
    ac = st.columns(3)
    field_commander = ac[0].checkbox(
        "Field Commander (+15% Let)",
        value=bool(default.appoint_field_commander),
        key=f"{key_prefix}_buffs_appoint_field_commander",
    )
    marshal = ac[1].checkbox(
        "Marshal (+5% Atk)",
        value=bool(default.appoint_marshal),
        key=f"{key_prefix}_buffs_appoint_marshal",
    )
    king = ac[2].checkbox(
        "King (+5% to all 4 stats)",
        value=bool(default.appoint_king),
        key=f"{key_prefix}_buffs_appoint_king",
    )

    st.markdown("**Turrets**")
    st.caption(
        "Turrets buff your Lethality. Non-linear: 1=+8%, 2=+12%, 3=+15%, 4=+20%."
    )
    turrets = st.slider(
        "Turret count", 0, TURRET_MAX_LEVEL, int(default.turrets),
        key=f"{key_prefix}_buffs_turrets",
    )
    if turrets > 0:
        st.caption(
            f"&nbsp;&nbsp;&nbsp;&nbsp;{turrets} turret(s) → +"
            f"{TURRET_LEVEL_PCT[int(turrets)]}% Lethality",
            unsafe_allow_html=True,
        )

    return Buffs(
        city_let=city_let, city_atk=city_atk, city_def=city_def, city_hp=city_hp,
        city_enemy_atk_down=eatk, city_enemy_def_down=edef,
        moose_level=int(moose), grizzly_level=int(grizzly),
        rhino_level=int(rhino), panther_level=int(panther),
        elephant_level=int(elephant), lion_level=int(lion),
        appoint_field_commander=bool(field_commander),
        appoint_marshal=bool(marshal),
        appoint_king=bool(king),
        turrets=int(turrets),
    )


def fighter_form(
    default: Fighter,
    key_prefix: str,
    side: str = "own",
    roster: Optional[Any] = None,
    builds: Optional[dict[str, Any]] = None,
) -> Fighter:
    label = st.text_input("Label", value=default.label, key=f"{key_prefix}_label")

    with st.expander(
        "Leaders: 3 mythics, one per class (no duplicates)",
        expanded=False,
    ):
        leader_inf = leader_form("Infantry leader", "Inf", default.leader_inf, f"{key_prefix}_li", roster=roster, builds=builds)
        leader_cav = leader_form("Cavalry leader",  "Cav", default.leader_cav, f"{key_prefix}_lc", roster=roster, builds=builds)
        leader_arc = leader_form("Archer leader",   "Arc", default.leader_arc, f"{key_prefix}_la", roster=roster, builds=builds)

    with st.expander(
        "Joiners: up to 4 (duplicates allowed for stacking)",
        expanded=False,
    ):
        joiners = joiners_form(default.joiners, key_prefix)

    with st.expander(
        "Account-wide stat bonuses",
        expanded=False,
    ):
        bonuses = bonuses_form(default.bonuses, key_prefix)

    with st.expander(
        "Buffs: city / pets / appointments (multiplicative)",
        expanded=False,
    ):
        buffs = buffs_form(default.buffs, key_prefix)

    with st.expander(
        "Troops",
        expanded=False,
    ):
        troops = troops_form(default.troops, key_prefix, side=side)

    return Fighter(
        label=label,
        leader_inf=leader_inf,
        leader_cav=leader_cav,
        leader_arc=leader_arc,
        joiners=joiners,
        bonuses=bonuses,
        troops=troops,
        buffs=buffs,
    )


def empty_fighter(label: str = "New") -> Fighter:
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Chenko", level="MAX"),),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


__all__ = [
    "leader_form", "joiners_form", "bonuses_form", "buffs_form", "troops_form",
    "fighter_form", "empty_fighter", "filter_heroes_by_max_gen",
    "leader_specs_editor", "class_gear_editor",
]


def leader_specs_editor(
    selected_heroes: tuple[str, ...],
    current_specs: dict,
    key_prefix: str,
    default_widget: int = 10,
    default_level: str = "MAX",
) -> dict:
    from kingshot_sim.optimizer.search_space import LeaderSpec

    if not selected_heroes:
        st.info("Pick at least one mythic above to configure its level and widget.")
        return {}

    st.caption(
        "Per-hero settings. Set the level and widget level for each "
        "selected mythic. Gear is configured separately below (per class)."
    )

    out: dict[str, LeaderSpec] = {}
    hdr = st.columns([2, 2, 2, 3])
    hdr[0].markdown("**Hero**")
    hdr[1].markdown("**Level**")
    hdr[2].markdown("**Widget**")
    hdr[3].markdown("**Skill levels (Sk1 / Sk2 / Sk3)**")

    for hero in selected_heroes:
        existing = current_specs.get(hero)
        cols = st.columns([2, 2, 2, 3])
        cols[0].markdown(f"★ **{hero}**")
        with cols[1]:
            lvl_init = existing.level if existing else default_level
            lvl_idx = _LEVEL_KEYS.index(lvl_init) if lvl_init in _LEVEL_KEYS else len(_LEVEL_KEYS) - 1
            level = st.selectbox(
                "Level", _LEVEL_KEYS, index=lvl_idx,
                key=f"{key_prefix}_{hero}_level",
                label_visibility="collapsed",
            )
        with cols[2]:
            widget = st.slider(
                "Widget", 0, 10,
                value=int(existing.widget_level) if existing else default_widget,
                key=f"{key_prefix}_{hero}_widget",
                label_visibility="collapsed",
            )
        with cols[3]:
            existing_sl = (
                existing.skill_levels if (existing and existing.skill_levels is not None)
                else default_skill_levels(level)
            )
            skill_levels = _skill_levels_subform(
                level, existing_sl, f"{key_prefix}_{hero}",
            )
        out[hero] = LeaderSpec(
            level=level,
            widget_level=widget,
            skill_levels=skill_levels,
            gear_atk_pct=0.0, gear_def_pct=0.0,
            gear_let_pct=0.0, gear_hp_pct=0.0,
        )
    return out


def class_gear_editor(
    default: dict[str, dict[str, "HeroGearPiece"]],
    key_prefix: str,
) -> dict[str, dict[str, "HeroGearPiece"]]:
    from kingshot_sim.data.gear import (
        piece_contribution, gearset_contribution,
        MYTHIC_MIN_LEVEL, MYTHIC_MAX_LEVEL, RED_MIN_LEVEL, RED_MAX_LEVEL,
    )
    from kingshot_sim.config.fighter import HeroGearPiece

    result: dict[str, dict[str, HeroGearPiece]] = {}
    for klass, label in [("Inf", "Infantry"),
                          ("Cav", "Cavalry"),
                          ("Arc", "Archer")]:
        existing_class = default.get(klass, {}) if default else {}
        with st.expander(f"{label} class gear",
                          expanded=bool(existing_class)):
            hdr = st.columns([1, 1, 1, 1, 2])
            hdr[0].markdown("**Slot**")
            hdr[1].markdown("**Quality**")
            hdr[2].markdown("**Level**")
            hdr[3].markdown("**Mastery**")
            hdr[4].markdown("**Contribution**")

            pieces: dict[str, HeroGearPiece] = {}
            any_active = False
            for slot in _GEAR_SLOTS:
                existing = existing_class.get(slot)
                cols = st.columns([1, 1, 1, 1, 2])
                cols[0].text(slot.capitalize())
                with cols[1]:
                    dq = existing.quality if existing else "mythic"
                    quality = st.selectbox(
                        "Quality", ["mythic", "red"],
                        index=0 if dq == "mythic" else 1,
                        key=f"{key_prefix}_{klass}_{slot}_q",
                        label_visibility="collapsed",
                    )
                with cols[2]:
                    if quality == "mythic":
                        lo, hi = MYTHIC_MIN_LEVEL, MYTHIC_MAX_LEVEL
                        fb = 0
                    else:
                        lo, hi = RED_MIN_LEVEL, RED_MAX_LEVEL
                        fb = RED_MIN_LEVEL
                    init = int(existing.level) if (existing and lo <= existing.level <= hi) else fb
                    level = st.number_input(
                        "Level", min_value=lo, max_value=hi, value=init,
                        step=1, key=f"{key_prefix}_{klass}_{slot}_lvl",
                        label_visibility="collapsed",
                    )
                with cols[3]:
                    minit = int(existing.forge_mastery) if existing else 0
                    mastery = st.number_input(
                        "Mastery", min_value=0, max_value=30, value=minit,
                        step=1, key=f"{key_prefix}_{klass}_{slot}_mast",
                        label_visibility="collapsed",
                    )
                if int(level) > 0:
                    try:
                        pb = piece_contribution(slot, quality, int(level), int(mastery))
                        bits = []
                        if pb.atk_pct: bits.append(f"+{pb.atk_pct:.1f}% Atk")
                        if pb.def_pct: bits.append(f"+{pb.def_pct:.1f}% Def")
                        if pb.let_pct: bits.append(f"+{pb.let_pct:.1f}% Let")
                        if pb.hp_pct:  bits.append(f"+{pb.hp_pct:.1f}% HP")
                        cols[4].caption(", ".join(bits) or "—")
                        pieces[slot] = HeroGearPiece(
                            slot=slot, quality=quality, level=int(level),
                            enhance=0, forge_mastery=int(mastery),
                        )
                        any_active = True
                    except ValueError as exc:
                        cols[4].error(str(exc))
                else:
                    cols[4].caption("(off)")

            if any_active:
                total = gearset_contribution(pieces)
                parts = []
                if total.atk_pct: parts.append(f"+{total.atk_pct:.1f}% Atk")
                if total.def_pct: parts.append(f"+{total.def_pct:.1f}% Def")
                if total.let_pct: parts.append(f"+{total.let_pct:.1f}% Let")
                if total.hp_pct:  parts.append(f"+{total.hp_pct:.1f}% HP")
                st.markdown(
                    f"**Total: {', '.join(parts) or '—'}** "
                    f"(applied to every {label} leader)"
                )
                result[klass] = pieces
    return result
