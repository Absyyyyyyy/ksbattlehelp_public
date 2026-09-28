from __future__ import annotations

import pytest

from kingshot_sim.config.buffs import Buffs
from kingshot_sim.easy_mode.ocr_buffs import BuffAggregate, BuffLineCell
from kingshot_sim.webui.easy_mode_form import _effective_buffs


def _agg(own=None, enemy=None, with_line=True):
    a = BuffAggregate(
        own={f"{k}_{s}": 0.0 for k in ("inf", "cav", "arc") for s in ("atk", "def", "let", "hp")},
        enemy={f"{k}_{s}": 0.0 for k in ("inf", "cav", "arc") for s in ("atk", "def", "let", "hp")},
    )
    for key, val in (own or {}).items():
        for k in ("inf", "cav", "arc"):
            a.own[f"{k}_{key}"] = val
    for key, val in (enemy or {}).items():
        for k in ("inf", "cav", "arc"):
            a.enemy[f"{k}_{key}"] = val
    if with_line:
        a.lines = [BuffLineCell("x", "X", "atk", "own", 0.0, 1.0)]
    return a


def test_no_aggregate_is_passthrough():
    b = Buffs(city_atk=20)
    assert _effective_buffs({"buffs": b}) is b


def test_empty_aggregate_is_passthrough():
    b = Buffs(city_atk=20)
    assert _effective_buffs({"buffs": b, "buffs_ocr_agg": _agg(with_line=False)}) is b


def test_own_buffs_folded_into_ocr_fields():
    eff = _effective_buffs({
        "buffs": Buffs(),
        "buffs_ocr_agg": _agg(own={"atk": 20.0, "let": 15.0, "hp": 5.0}),
    })
    assert eff.ocr_own_atk_pct == pytest.approx(20.0)
    assert eff.ocr_own_let_pct == pytest.approx(15.0)
    assert eff.ocr_own_hp_pct == pytest.approx(5.0)
    assert eff.ocr_own_def_pct == pytest.approx(0.0)


def test_enemy_lines_negated_to_positive_magnitude():
    eff = _effective_buffs({
        "buffs": Buffs(),
        "buffs_ocr_agg": _agg(enemy={"def": -20.0, "atk": -10.0}),
    })
    assert eff.ocr_enemy_def_down_pct == pytest.approx(20.0)
    assert eff.ocr_enemy_atk_down_pct == pytest.approx(10.0)


def test_manual_buffs_preserved_alongside_ocr():
    eff = _effective_buffs({
        "buffs": Buffs(city_atk=10, rhino_level=5, turrets=2),
        "buffs_ocr_agg": _agg(own={"atk": 20.0}),
    })
    assert eff.city_atk == 10
    assert eff.rhino_level == 5
    assert eff.turrets == 2
    assert eff.ocr_own_atk_pct == pytest.approx(20.0)


def test_effective_buffs_drive_section_d():
    from kingshot_sim.engine.section_d import section_d_factor
    eff = _effective_buffs({
        "buffs": Buffs(),
        "buffs_ocr_agg": _agg(own={"atk": 30.0}),
    })
    assert section_d_factor(eff, Buffs(), "atk") == pytest.approx(1.30)
