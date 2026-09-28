from __future__ import annotations
import pytest

from kingshot_sim.config.fighter import BonusVector, LeaderHero
from kingshot_sim.config.buffs import Buffs, MOOSE_LEVEL_PCT
from kingshot_sim.easy_mode.peeling import (
    VisibleAggregate,
    PeelingContext,
    EnemyScreenshotDebuffs,
    peel_visible_to_bonus_vector,
    build_visible_from_bonus_vector,
    TERRITORY_BONUS_PCT,
    APPOINTMENT_FIELD_COMMANDER_LET_PCT,
    APPOINTMENT_MARSHAL_ATK_PCT,
    APPOINTMENT_KING_PCT,
)
from kingshot_sim.data.reference import (
    hero_leader_pct, widget_stat_bonus, HERO_WIDGET,
    WIDGET_SKILL_MAX_PCT, WIDGET_SKILL_MULTIPLIER,
)
from kingshot_sim.data.catalog import WIDGET_SKILL_SPEC


def _zero_visible() -> VisibleAggregate:
    return VisibleAggregate(**{
        f"{c}_{s}_pct": 0.0
        for c in ("inf", "cav", "arc")
        for s in ("atk", "def", "let", "hp")
    })


def _bare_leader(hero: str, level: str = "MAX", widget: int = 0) -> LeaderHero:
    return LeaderHero(hero_name=hero, level=level, widget_level=widget)


def _bare_ctx(
    role: str = "attacking",
    was_rally: bool = True,
    in_territory: bool = False,
    inf_hero: str = "Eric",
    cav_hero: str = "Petra",
    arc_hero: str = "Jaeger",
    inf_widget: int = 0,
    cav_widget: int = 0,
    arc_widget: int = 0,
    buffs: Buffs | None = None,
    field_commander: bool = False,
    marshal: bool = False,
    king: bool = False,
    enemy_debuffs: EnemyScreenshotDebuffs | None = None,
) -> PeelingContext:
    if buffs is None:
        buffs = Buffs(
            appoint_field_commander=field_commander,
            appoint_marshal=marshal,
            appoint_king=king,
        )
    elif field_commander or marshal or king:
        from dataclasses import replace
        buffs = replace(
            buffs,
            appoint_field_commander=field_commander or buffs.appoint_field_commander,
            appoint_marshal=marshal or buffs.appoint_marshal,
            appoint_king=king or buffs.appoint_king,
        )
    return PeelingContext(
        importee_role=role,
        was_rally=was_rally,
        is_garrisoning_territory=in_territory,
        leader_inf=_bare_leader(inf_hero, widget=inf_widget),
        leader_cav=_bare_leader(cav_hero, widget=cav_widget),
        leader_arc=_bare_leader(arc_hero, widget=arc_widget),
        buffs=buffs,
        enemy_debuffs=enemy_debuffs or EnemyScreenshotDebuffs(),
    )


def test_visible_aggregate_get_reads_correct_cell():
    v = VisibleAggregate(
        inf_atk_pct=100.0, inf_def_pct=200.0, inf_let_pct=50.0, inf_hp_pct=75.0,
        cav_atk_pct=110.0, cav_def_pct=210.0, cav_let_pct=55.0, cav_hp_pct=80.0,
        arc_atk_pct=120.0, arc_def_pct=220.0, arc_let_pct=60.0, arc_hp_pct=85.0,
    )
    assert v.get("inf", "atk") == 100.0
    assert v.get("cav", "let") == 55.0
    assert v.get("arc", "hp") == 85.0


def test_visible_aggregate_get_rejects_bad_keys():
    v = _zero_visible()
    with pytest.raises(ValueError, match="Unknown class"):
        v.get("xyz", "atk")
    with pytest.raises(ValueError, match="Unknown stat"):
        v.get("inf", "xyz")


def test_widget_sides_defending():
    ctx = _bare_ctx(role="defending", was_rally=False)
    assert ctx.active_widget_sides() == frozenset({"defender"})


def test_widget_sides_attacking_rally():
    ctx = _bare_ctx(role="attacking", was_rally=True)
    assert ctx.active_widget_sides() == frozenset({"rally"})


def test_widget_sides_attacking_solo_is_empty():
    ctx = _bare_ctx(role="attacking", was_rally=False)
    assert ctx.active_widget_sides() == frozenset()


def test_widget_sides_defending_ignores_rally_flag():
    ctx = _bare_ctx(role="defending", was_rally=True)
    assert ctx.active_widget_sides() == frozenset({"defender"})


def test_bare_ctx_no_layers_peel_to_visible_minus_leader_only():
    ctx = _bare_ctx()
    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead, inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=cav_lead, cav_def_pct=cav_lead, cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=arc_lead, arc_def_pct=arc_lead, arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    for cls in ("inf", "cav", "arc"):
        for stat in ("atk", "def", "let", "hp"):
            assert getattr(bv, f"{cls}_{stat}_pct") == pytest.approx(0.0, abs=1e-6)


def test_section_d_city_atk_only_divides_out():
    buffs = Buffs(city_atk=20)
    ctx = _bare_ctx(buffs=buffs)
    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")

    base_inf_atk = 100.0 + inf_lead
    base_cav_atk = 100.0 + cav_lead
    base_arc_atk = 100.0 + arc_lead
    visible = VisibleAggregate(
        inf_atk_pct=base_inf_atk * 1.20,
        inf_def_pct=hero_leader_pct("Eric", "MAX"),
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=base_cav_atk * 1.20,
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=base_arc_atk * 1.20,
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_def_pct == pytest.approx(0.0, abs=1e-6)


def test_section_d_lion_pet_def_only():
    buffs = Buffs(lion_level=5)
    ctx = _bare_ctx(buffs=buffs)
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible_inf_def = (100.0 + inf_lead) * 1.05
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=visible_inf_def, inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"), cav_def_pct=hero_leader_pct("Petra", "MAX") * 1.05,
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"), arc_def_pct=hero_leader_pct("Jaeger", "MAX") * 1.05,
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_def_pct == pytest.approx(100.0, abs=1e-6)


def test_section_d_multiplicative_composition():
    buffs = Buffs(city_atk=20, rhino_level=10)
    ctx = _bare_ctx(buffs=buffs)
    inf_lead = hero_leader_pct("Eric", "MAX")
    base = 50.0 + inf_lead
    visible_inf_atk = base * 1.20 * 1.10
    v = _zero_visible()
    v = VisibleAggregate(
        **{**v.__dict__, "inf_atk_pct": visible_inf_atk, "inf_def_pct": inf_lead,
            "cav_atk_pct": hero_leader_pct("Petra", "MAX") * 1.20 * 1.10,
            "cav_def_pct": hero_leader_pct("Petra", "MAX"),
            "arc_atk_pct": hero_leader_pct("Jaeger", "MAX") * 1.20 * 1.10,
            "arc_def_pct": hero_leader_pct("Jaeger", "MAX")}
    )
    bv = peel_visible_to_bonus_vector(v, ctx)
    assert bv.inf_atk_pct == pytest.approx(50.0, abs=1e-6)


def test_section_c_territory_applies_to_atk_def_only():
    ctx = _bare_ctx(role="defending", was_rally=False, in_territory=True)
    inf_lead = hero_leader_pct("Eric", "MAX")
    a_inf_atk = 100.0 + inf_lead
    b_inf_atk = a_inf_atk * (1 + TERRITORY_BONUS_PCT / 100) + TERRITORY_BONUS_PCT
    visible = VisibleAggregate(
        inf_atk_pct=b_inf_atk,
        inf_def_pct=inf_lead * (1 + TERRITORY_BONUS_PCT/100) + TERRITORY_BONUS_PCT,
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX") * 1.10 + 10,
        cav_def_pct=hero_leader_pct("Petra", "MAX") * 1.10 + 10,
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX") * 1.10 + 10,
        arc_def_pct=hero_leader_pct("Jaeger", "MAX") * 1.10 + 10,
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_let_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.inf_hp_pct == pytest.approx(0.0, abs=1e-6)


def test_section_c_no_territory_no_change():
    ctx = _bare_ctx(role="defending", was_rally=False, in_territory=False)
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=100.0 + inf_lead, inf_def_pct=inf_lead, inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"), cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"), arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)


def test_leader_atk_def_class_restricted():
    ctx = _bare_ctx()
    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead, inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=cav_lead, cav_def_pct=cav_lead, cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=arc_lead, arc_def_pct=arc_lead, arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.cav_atk_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.arc_atk_pct == pytest.approx(0.0, abs=1e-6)


def test_widget_stat_bonus_class_restricted():
    inf_widget_level = 10
    ctx = _bare_ctx(inf_widget=inf_widget_level)
    inf_lead = hero_leader_pct("Eric", "MAX")
    widget_let, widget_hp = widget_stat_bonus(HERO_WIDGET["Eric"], inf_widget_level)
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=widget_let, inf_hp_pct=widget_hp,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"), cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"), arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_let_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.inf_hp_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.cav_let_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.cav_hp_pct == pytest.approx(0.0, abs=1e-6)


def test_widget_expedition_skill_defender_side_subtracted_when_defending():
    eric_widget_level = 10
    ctx_def = _bare_ctx(role="defending", was_rally=False,
                          inf_hero="Eric", inf_widget=eric_widget_level)
    inf_lead = hero_leader_pct("Eric", "MAX")
    _, _, op_label = WIDGET_SKILL_SPEC["Anvil of Truth"]
    assert WIDGET_SKILL_SPEC["Anvil of Truth"][0] == "defender"
    assert WIDGET_SKILL_SPEC["Anvil of Truth"][1] == 112
    widget_let, widget_hp = widget_stat_bonus("Anvil of Truth", eric_widget_level)
    widget_def_skill_pct = WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[eric_widget_level]
    visible_inf_def = inf_lead * (1.0 + widget_def_skill_pct / 100.0)
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=visible_inf_def,
        inf_let_pct=widget_let, inf_hp_pct=widget_hp,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"),
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx_def)
    assert bv.inf_def_pct == pytest.approx(0.0, abs=1e-6)


def test_widget_expedition_skill_rally_side_not_subtracted_when_defending():
    am_widget = 10
    ctx = _bare_ctx(role="defending", was_rally=False,
                     inf_hero="Amadeus", inf_widget=am_widget)
    inf_lead = hero_leader_pct("Amadeus", "MAX")
    widget_let, widget_hp = widget_stat_bonus("Aegis of Fate", am_widget)
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=widget_let, inf_hp_pct=widget_hp,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"), cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"), arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(0.0, abs=1e-6)


def test_solo_attacker_no_widgets_subtracted():
    ctx = _bare_ctx(role="attacking", was_rally=False,
                     inf_hero="Amadeus", inf_widget=10,
                     cav_hero="Petra", cav_widget=10,
                     arc_hero="Jaeger", arc_widget=10)
    assert ctx.active_widget_sides() == frozenset()


def test_appointment_field_commander_lethality_only():
    ctx = _bare_ctx(field_commander=True)
    fc = APPOINTMENT_FIELD_COMMANDER_LET_PCT
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=100.0 + fc, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"), cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=50.0 + fc, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"), arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=200.0 + fc, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_let_pct == pytest.approx(50.0, abs=1e-6)
    assert bv.arc_let_pct == pytest.approx(200.0, abs=1e-6)
    assert bv.inf_atk_pct == pytest.approx(0.0, abs=1e-6)


def test_appointment_king_all_four_stats():
    ctx = _bare_ctx(king=True)
    kp = APPOINTMENT_KING_PCT
    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=100.0 + inf_lead + kp, inf_def_pct=inf_lead + kp,
        inf_let_pct=50.0 + kp, inf_hp_pct=75.0 + kp,
        cav_atk_pct=cav_lead + kp, cav_def_pct=cav_lead + kp,
        cav_let_pct=kp, cav_hp_pct=kp,
        arc_atk_pct=arc_lead + kp, arc_def_pct=arc_lead + kp,
        arc_let_pct=kp, arc_hp_pct=kp,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_let_pct == pytest.approx(50.0, abs=1e-6)
    assert bv.inf_hp_pct == pytest.approx(75.0, abs=1e-6)
    assert bv.cav_let_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.arc_hp_pct == pytest.approx(0.0, abs=1e-6)


def test_peeled_squad_fields_are_zero():
    ctx = _bare_ctx()
    bv = peel_visible_to_bonus_vector(_zero_visible(), ctx)
    assert bv.squad_atk_pct == 0.0
    assert bv.squad_def_pct == 0.0
    assert bv.squad_let_pct == 0.0
    assert bv.squad_hp_pct == 0.0


def _full_bv(**kwargs) -> BonusVector:
    defaults = {f"{c}_{s}_pct": 0.0 for c in ("inf", "cav", "arc")
                  for s in ("atk", "def", "let", "hp")}
    defaults.update({f"squad_{s}_pct": 0.0 for s in ("atk", "def", "let", "hp")})
    defaults.update(kwargs)
    return BonusVector(**defaults)


def _assert_bv_equal(actual: BonusVector, expected: BonusVector, abs_tol: float = 1e-6):
    for c in ("inf", "cav", "arc"):
        for s in ("atk", "def", "let", "hp"):
            field = f"{c}_{s}_pct"
            assert getattr(actual, field) == pytest.approx(
                getattr(expected, field), abs=abs_tol
            ), f"{field} differs: actual={getattr(actual, field)}, expected={getattr(expected, field)}"


def test_roundtrip_empty_context():
    ctx = _bare_ctx()
    bv = _full_bv(inf_atk_pct=100.0, inf_def_pct=200.0,
                    cav_atk_pct=110.0, cav_def_pct=210.0,
                    arc_atk_pct=120.0, arc_def_pct=220.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_with_city_buffs():
    buffs = Buffs(city_atk=20, city_def=10, city_let=20, city_hp=10)
    ctx = _bare_ctx(buffs=buffs)
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_with_pets():
    buffs = Buffs(rhino_level=10, lion_level=8, panther_level=5,
                    moose_level=7, elephant_level=10)
    ctx = _bare_ctx(buffs=buffs)
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_with_appointments():
    ctx = _bare_ctx(field_commander=True, marshal=True, king=True)
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_defender_with_territory():
    ctx = _bare_ctx(role="defending", was_rally=False, in_territory=True)
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_defender_widgets_at_max():
    ctx = _bare_ctx(
        role="defending", was_rally=False,
        inf_hero="Eric", inf_widget=10,
        cav_hero="Sophia", cav_widget=10,
        arc_hero="Jaeger", arc_widget=10,
    )
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_rally_attacker_with_rally_widgets():
    ctx = _bare_ctx(
        role="attacking", was_rally=True,
        inf_hero="Amadeus", inf_widget=10,
        cav_hero="Petra", cav_widget=10,
        arc_hero="Yang", arc_widget=10,
    )
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_solo_attacker_no_widget_contribution():
    ctx = _bare_ctx(
        role="attacking", was_rally=False,
        inf_hero="Amadeus", inf_widget=10,
        cav_hero="Petra", cav_widget=10,
        arc_hero="Yang", arc_widget=10,
    )
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0, inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0, cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0, arc_let_pct=160.0, arc_hp_pct=210.0)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_roundtrip_full_stack():
    buffs = Buffs(city_atk=20, city_def=10, city_let=20, city_hp=10,
                    rhino_level=10, lion_level=8, panther_level=5,
                    moose_level=7, elephant_level=10)
    ctx = _bare_ctx(
        role="defending", was_rally=False, in_territory=True,
        inf_hero="Eric", inf_widget=10,
        cav_hero="Sophia", cav_widget=10,
        arc_hero="Jaeger", arc_widget=10,
        buffs=buffs,
        field_commander=True, marshal=True, king=True,
    )
    bv = _full_bv(inf_atk_pct=523.1, inf_def_pct=601.0, inf_let_pct=348.1, inf_hp_pct=356.3,
                    cav_atk_pct=597.6, cav_def_pct=601.0, cav_let_pct=291.9, cav_hp_pct=263.5,
                    arc_atk_pct=528.0, arc_def_pct=529.0, arc_let_pct=316.1, arc_hp_pct=280.3)
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv, abs_tol=1e-6)


def test_helga_in_trio_does_not_change_peeled_bv():
    bv = _full_bv(inf_atk_pct=300.0, inf_def_pct=400.0,
                    cav_atk_pct=310.0, cav_def_pct=410.0,
                    arc_atk_pct=320.0, arc_def_pct=420.0)
    ctx_with_helga = _bare_ctx(inf_hero="Helga")
    ctx_with_eric  = _bare_ctx(inf_hero="Eric")
    visible_helga = build_visible_from_bonus_vector(bv, ctx_with_helga)
    visible_eric  = build_visible_from_bonus_vector(bv, ctx_with_eric)
    peeled_helga = peel_visible_to_bonus_vector(visible_helga, ctx_with_helga)
    peeled_eric  = peel_visible_to_bonus_vector(visible_eric, ctx_with_eric)
    _assert_bv_equal(peeled_helga, bv)
    _assert_bv_equal(peeled_eric, bv)
    _assert_bv_equal(peeled_helga, peeled_eric)


def test_amadeus_in_trio_does_not_change_peeled_bv():
    bv = _full_bv(inf_let_pct=150.0, inf_hp_pct=200.0,
                    cav_let_pct=155.0, cav_hp_pct=205.0,
                    arc_let_pct=160.0, arc_hp_pct=210.0)
    ctx_with_amadeus = _bare_ctx(inf_hero="Amadeus")
    ctx_with_eric    = _bare_ctx(inf_hero="Eric")
    visible_amadeus = build_visible_from_bonus_vector(bv, ctx_with_amadeus)
    visible_eric    = build_visible_from_bonus_vector(bv, ctx_with_eric)
    peeled_amadeus = peel_visible_to_bonus_vector(visible_amadeus, ctx_with_amadeus)
    peeled_eric    = peel_visible_to_bonus_vector(visible_eric, ctx_with_eric)
    _assert_bv_equal(peeled_amadeus, bv)
    _assert_bv_equal(peeled_eric, bv)


def test_enemy_screenshot_debuffs_validation():
    EnemyScreenshotDebuffs(city_atk_down=20, city_def_down=10, grizzly_level=5)
    EnemyScreenshotDebuffs()
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(city_atk_down=15)
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(city_def_down=5)
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(grizzly_level=99)
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(grizzly_level=-1)


def test_enemy_screenshot_debuffs_is_empty():
    assert EnemyScreenshotDebuffs().is_empty()
    assert not EnemyScreenshotDebuffs(city_atk_down=10).is_empty()
    assert not EnemyScreenshotDebuffs(grizzly_level=1).is_empty()


def test_default_peeling_context_has_empty_enemy_debuffs():
    ctx = _bare_ctx()
    assert ctx.enemy_debuffs.is_empty()


def test_enemy_city_atk_down_peeled_into_underlying_atk():
    enemy = EnemyScreenshotDebuffs(city_atk_down=20)
    ctx = _bare_ctx(enemy_debuffs=enemy)

    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")

    visible = VisibleAggregate(
        inf_atk_pct=(100.0 + inf_lead) * 0.80,
        inf_def_pct=inf_lead,
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=(100.0 + cav_lead) * 0.80,
        cav_def_pct=cav_lead,
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=(100.0 + arc_lead) * 0.80,
        arc_def_pct=arc_lead,
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_def_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.cav_def_pct == pytest.approx(0.0, abs=1e-6)
    assert bv.arc_def_pct == pytest.approx(0.0, abs=1e-6)


def test_enemy_city_def_down_peeled_into_underlying_def():
    enemy = EnemyScreenshotDebuffs(city_def_down=20)
    ctx = _bare_ctx(enemy_debuffs=enemy)
    inf_lead = hero_leader_pct("Eric", "MAX")
    cav_lead = hero_leader_pct("Petra", "MAX")
    arc_lead = hero_leader_pct("Jaeger", "MAX")
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=(100.0 + inf_lead) * 0.80,
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=cav_lead, cav_def_pct=(100.0 + cav_lead) * 0.80,
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=arc_lead, arc_def_pct=(100.0 + arc_lead) * 0.80,
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_def_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_def_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_def_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_atk_pct == pytest.approx(0.0, abs=1e-6)


def test_enemy_grizzly_peeled_into_underlying_let():
    from kingshot_sim.config.buffs import GRIZZLY_LEVEL_PCT
    enemy = EnemyScreenshotDebuffs(grizzly_level=5)
    ctx = _bare_ctx(enemy_debuffs=enemy)
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible_let_factor = 1.0 - GRIZZLY_LEVEL_PCT[5] / 100.0
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=100.0 * visible_let_factor, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"),
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=100.0 * visible_let_factor, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=100.0 * visible_let_factor, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_let_pct == pytest.approx(100.0, abs=1e-6)


def test_own_buff_plus_enemy_debuff_compose_multiplicatively():
    buffs = Buffs(city_atk=20)
    enemy = EnemyScreenshotDebuffs(city_atk_down=20)
    ctx = _bare_ctx(buffs=buffs, enemy_debuffs=enemy)

    inf_lead = hero_leader_pct("Eric", "MAX")
    composed = 1.00
    visible_inf_atk = (100.0 + inf_lead) * composed
    visible = VisibleAggregate(
        inf_atk_pct=visible_inf_atk, inf_def_pct=inf_lead,
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=(100.0 + hero_leader_pct("Petra", "MAX")) * composed,
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=(100.0 + hero_leader_pct("Jaeger", "MAX")) * composed,
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_atk_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_atk_pct == pytest.approx(100.0, abs=1e-6)


def test_no_buff_with_enemy_debuff_adds_back():
    enemy = EnemyScreenshotDebuffs(city_atk_down=20)
    ctx_fixed = _bare_ctx(enemy_debuffs=enemy)

    inf_lead = hero_leader_pct("Eric", "MAX")
    underlying = 100.0
    visible_inf_atk = (underlying + inf_lead) * 0.80
    visible = VisibleAggregate(
        inf_atk_pct=visible_inf_atk, inf_def_pct=inf_lead,
        inf_let_pct=0.0, inf_hp_pct=0.0,
        cav_atk_pct=(underlying + hero_leader_pct("Petra", "MAX")) * 0.80,
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0, cav_hp_pct=0.0,
        arc_atk_pct=(underlying + hero_leader_pct("Jaeger", "MAX")) * 0.80,
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0, arc_hp_pct=0.0,
    )

    bv_fixed = peel_visible_to_bonus_vector(visible, ctx_fixed)
    assert bv_fixed.inf_atk_pct == pytest.approx(underlying, abs=1e-6)
    assert bv_fixed.cav_atk_pct == pytest.approx(underlying, abs=1e-6)
    assert bv_fixed.arc_atk_pct == pytest.approx(underlying, abs=1e-6)


def test_enemy_debuff_roundtrip():
    enemy = EnemyScreenshotDebuffs(city_atk_down=20, city_def_down=10, grizzly_level=3)
    buffs = Buffs(city_atk=10, city_let=20)
    ctx = _bare_ctx(buffs=buffs, enemy_debuffs=enemy)
    bv = _full_bv(
        inf_atk_pct=215.0, inf_def_pct=140.0, inf_let_pct=80.0, inf_hp_pct=120.0,
        cav_atk_pct=230.0, cav_def_pct=150.0, cav_let_pct=85.0, cav_hp_pct=125.0,
        arc_atk_pct=245.0, arc_def_pct=160.0, arc_let_pct=90.0, arc_hp_pct=130.0,
    )
    visible = build_visible_from_bonus_vector(bv, ctx)
    peeled = peel_visible_to_bonus_vector(visible, ctx)
    _assert_bv_equal(peeled, bv)


def test_section_d_turrets_let_only():
    buffs = Buffs(turrets=4)
    ctx = _bare_ctx(buffs=buffs)
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible_inf_let = 100.0 * 1.20
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=visible_inf_let, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"),
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=100.0 * 1.20, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=100.0 * 1.20, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_let_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.inf_atk_pct == pytest.approx(0.0, abs=1e-6)


def test_section_d_turrets_with_panther_stack():
    buffs = Buffs(turrets=4, panther_level=10, city_let=20)
    ctx = _bare_ctx(buffs=buffs)
    inf_lead = hero_leader_pct("Eric", "MAX")
    factor = 1.20 * 1.10 * 1.20
    visible_inf_let = 100.0 * factor
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=visible_inf_let, inf_hp_pct=0.0,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"),
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=100.0 * factor, cav_hp_pct=0.0,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=100.0 * factor, arc_hp_pct=0.0,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_let_pct == pytest.approx(100.0, abs=1e-6)


def test_moose_no_longer_peeled_from_own_hp():
    bv = _full_bv(inf_hp_pct=200.0, cav_hp_pct=210.0, arc_hp_pct=220.0)
    ctx_no_moose = _bare_ctx(buffs=Buffs(moose_level=0))
    ctx_with_moose = _bare_ctx(buffs=Buffs(moose_level=7))
    v_no_moose = build_visible_from_bonus_vector(bv, ctx_no_moose)
    v_with_moose = build_visible_from_bonus_vector(bv, ctx_with_moose)
    assert v_no_moose.inf_hp_pct == pytest.approx(v_with_moose.inf_hp_pct)
    assert v_no_moose.cav_hp_pct == pytest.approx(v_with_moose.cav_hp_pct)
    assert v_no_moose.arc_hp_pct == pytest.approx(v_with_moose.arc_hp_pct)


def test_enemy_moose_peeled_into_underlying_hp():
    enemy = EnemyScreenshotDebuffs(moose_level=7)
    ctx = _bare_ctx(enemy_debuffs=enemy)
    inf_lead = hero_leader_pct("Eric", "MAX")
    visible_hp_factor = 1.0 - MOOSE_LEVEL_PCT[7] / 100.0
    visible = VisibleAggregate(
        inf_atk_pct=inf_lead, inf_def_pct=inf_lead,
        inf_let_pct=0.0,
        inf_hp_pct=100.0 * visible_hp_factor,
        cav_atk_pct=hero_leader_pct("Petra", "MAX"),
        cav_def_pct=hero_leader_pct("Petra", "MAX"),
        cav_let_pct=0.0,
        cav_hp_pct=100.0 * visible_hp_factor,
        arc_atk_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_def_pct=hero_leader_pct("Jaeger", "MAX"),
        arc_let_pct=0.0,
        arc_hp_pct=100.0 * visible_hp_factor,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    assert bv.inf_hp_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.cav_hp_pct == pytest.approx(100.0, abs=1e-6)
    assert bv.arc_hp_pct == pytest.approx(100.0, abs=1e-6)


def test_enemy_moose_validation():
    EnemyScreenshotDebuffs(moose_level=0)
    EnemyScreenshotDebuffs(moose_level=7)
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(moose_level=99)
    with pytest.raises(ValueError):
        EnemyScreenshotDebuffs(moose_level=-1)
    assert EnemyScreenshotDebuffs().is_empty()
    assert not EnemyScreenshotDebuffs(moose_level=3).is_empty()


def test_engine_moose_reduces_defender_hp_factor():
    from dataclasses import replace
    from kingshot_sim.engine.compile import compile_fighter
    from kingshot_sim.engine.section_d import section_d_factor
    from kingshot_sim.webui.forms import empty_fighter

    f = empty_fighter()
    f = replace(f, buffs=Buffs(moose_level=7))
    fs = compile_fighter(f, side="attacker")
    no_buffs = empty_fighter()
    no_buffs_fs = compile_fighter(no_buffs, side="defender")
    factor_hp = section_d_factor(no_buffs_fs.buffs, fs.buffs, "hp")
    assert factor_hp == pytest.approx(0.95, abs=1e-6)

    f2 = replace(f, buffs=Buffs())
    fs2 = compile_fighter(f2, side="attacker")
    assert section_d_factor(no_buffs_fs.buffs, fs2.buffs, "hp") == pytest.approx(1.0, abs=1e-9)


def test_engine_moose_and_grizzly_independent():
    from dataclasses import replace
    from kingshot_sim.engine.compile import compile_fighter
    from kingshot_sim.engine.section_d import section_d_factor
    from kingshot_sim.webui.forms import empty_fighter

    f = empty_fighter()
    f = replace(f, buffs=Buffs(moose_level=7, grizzly_level=8))
    fs = compile_fighter(f, side="attacker")
    no_buffs_fs = compile_fighter(empty_fighter(), side="defender")
    assert section_d_factor(no_buffs_fs.buffs, fs.buffs, "hp")  == pytest.approx(0.95, abs=1e-6)
    assert section_d_factor(no_buffs_fs.buffs, fs.buffs, "let") == pytest.approx(0.95, abs=1e-6)
    assert section_d_factor(no_buffs_fs.buffs, fs.buffs, "atk") == pytest.approx(1.0, abs=1e-9)
    assert section_d_factor(no_buffs_fs.buffs, fs.buffs, "def") == pytest.approx(1.0, abs=1e-9)
