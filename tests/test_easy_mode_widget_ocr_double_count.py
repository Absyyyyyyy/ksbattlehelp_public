from __future__ import annotations

import pytest

from kingshot_sim.config.buffs import Buffs
from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
)
from kingshot_sim.domain.enums import RNGMode
from kingshot_sim.engine.battle import run_battle, BattleConfig
from kingshot_sim.easy_mode.ocr_buffs import BuffAggregate, BuffLineCell
from kingshot_sim.easy_mode.peeling import (
    PeelingContext, build_visible_from_bonus_vector,
    peel_visible_to_bonus_vector, widget_expedition_pct_by_stat,
)
from kingshot_sim.webui.easy_mode_form import _effective_buffs
from kingshot_sim.data.reference import (
    WIDGET_SKILL_MAX_PCT, WIDGET_SKILL_MULTIPLIER,
)

WLVL = 10
WIDGET_PCT = WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[WLVL]


def _agg(own=None, enemy=None):
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
    a.lines = [BuffLineCell("x", "X", "def", "own", 0.0, 1.0)]
    return a


def _defender_trio(inf_wlvl=WLVL):
    return (
        LeaderHero(hero_name="Eric",   level="MAX", widget_level=inf_wlvl),
        LeaderHero(hero_name="Hilde",  level="MAX", widget_level=0),
        LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
    )


_TROOPS = TroopRoster(
    infantry=(TroopGroup(tier="T10.5", count=120_000),),
    cavalry=(TroopGroup(tier="T10.5", count=90_000),),
    archer=(TroopGroup(tier="T10.5", count=90_000),),
)

_BV_TRUE = BonusVector(
    inf_atk_pct=120, cav_atk_pct=120, arc_atk_pct=120,
    inf_def_pct=120, cav_def_pct=120, arc_def_pct=120,
    inf_let_pct=80, cav_let_pct=80, arc_let_pct=80,
    inf_hp_pct=80, cav_hp_pct=80, arc_hp_pct=80,
)


def _attacker():
    return Fighter(
        label="atk", joiners=(),
        leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra",   level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger",  level="MAX", widget_level=0),
        bonuses=BonusVector(
            inf_atk_pct=130, cav_atk_pct=130, arc_atk_pct=130,
            inf_let_pct=90, cav_let_pct=90, arc_let_pct=90,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=110_000),),
            cavalry=(TroopGroup(tier="T10.5", count=95_000),),
            archer=(TroopGroup(tier="T10.5", count=95_000),),
        ),
        buffs=Buffs(),
    )


def _import_defender(visible, trio, ocr_agg):
    state = {
        "buffs": Buffs(), "buffs_ocr_agg": ocr_agg,
        "trio": trio, "p2_role": "defending", "was_rally": False,
    }
    eff = _effective_buffs(state)
    ctx = PeelingContext(
        importee_role="defending", was_rally=False, is_garrisoning_territory=False,
        leader_inf=trio[0], leader_cav=trio[1], leader_arc=trio[2], buffs=eff,
    )
    bv = peel_visible_to_bonus_vector(visible, ctx)
    return Fighter(
        label="def", joiners=(), leader_inf=trio[0], leader_cav=trio[1],
        leader_arc=trio[2], bonuses=bv, troops=_TROOPS, buffs=eff,
    )


def _score(defender):
    return run_battle(BattleConfig(
        attacker=_attacker(), defender=defender,
        rng_mode=RNGMode.EXPECTED, max_rounds=200)).score


class TestWidgetExpeditionPctByStat:
    def test_defender_widget_counts_on_its_stat(self):
        trio = _defender_trio()
        net = widget_expedition_pct_by_stat(trio, "defending", False)
        assert net["def"] == pytest.approx(WIDGET_PCT)
        assert net["atk"] == 0.0 and net["let"] == 0.0 and net["hp"] == 0.0

    def test_solo_attacker_has_no_active_widgets(self):
        trio = _defender_trio()
        net = widget_expedition_pct_by_stat(trio, "attacking", False)
        assert all(v == 0.0 for v in net.values())

    def test_role_gates_the_side(self):
        trio = _defender_trio()
        net = widget_expedition_pct_by_stat(trio, "attacking", True)
        assert net["def"] == 0.0

    def test_multiple_leaders_sum_per_stat(self):
        trio = (
            LeaderHero(hero_name="Eric",   level="MAX", widget_level=WLVL),
            LeaderHero(hero_name="Hilde",  level="MAX", widget_level=0),
            LeaderHero(hero_name="Jaeger", level="MAX", widget_level=WLVL),
        )
        net = widget_expedition_pct_by_stat(trio, "defending", False)
        assert net["def"] == pytest.approx(WIDGET_PCT)
        assert net["hp"] == pytest.approx(WIDGET_PCT)


class TestNoDoubleCount:
    def _visible(self, trio):
        ctx = PeelingContext(
            importee_role="defending", was_rally=False,
            is_garrisoning_territory=False,
            leader_inf=trio[0], leader_cav=trio[1], leader_arc=trio[2],
            buffs=Buffs(),
        )
        return build_visible_from_bonus_vector(_BV_TRUE, ctx)

    def test_panel_only_equals_panel_plus_popup(self):
        trio = _defender_trio()
        V = self._visible(trio)

        score_a = _score(_import_defender(V, trio, ocr_agg=None))
        agg = _agg(own={"def": WIDGET_PCT})
        score_b = _score(_import_defender(V, trio, ocr_agg=agg))

        assert score_b == pytest.approx(score_a, abs=1e-9)

    def test_fix_is_load_bearing(self):
        trio = _defender_trio()
        V = self._visible(trio)
        score_a = _score(_import_defender(V, trio, ocr_agg=None))

        eff_raw = Buffs(ocr_own_def_pct=WIDGET_PCT)
        ctx = PeelingContext(
            importee_role="defending", was_rally=False,
            is_garrisoning_territory=False,
            leader_inf=trio[0], leader_cav=trio[1], leader_arc=trio[2],
            buffs=eff_raw,
        )
        bv = peel_visible_to_bonus_vector(V, ctx)
        unfixed = Fighter(
            label="def", joiners=(), leader_inf=trio[0], leader_cav=trio[1],
            leader_arc=trio[2], bonuses=bv, troops=_TROOPS, buffs=eff_raw,
        )
        assert _score(unfixed) != pytest.approx(score_a, abs=1e-6)


class TestRealBuffsSurvive:
    def test_extra_defender_buff_is_kept(self):
        trio = _defender_trio()
        eff = _effective_buffs({
            "buffs": Buffs(), "buffs_ocr_agg": _agg(own={"def": WIDGET_PCT + 30.0}),
            "trio": trio, "p2_role": "defending", "was_rally": False,
        })
        assert eff.ocr_own_def_pct == pytest.approx(30.0)

    def test_clamp_never_goes_negative(self):
        trio = _defender_trio()
        eff = _effective_buffs({
            "buffs": Buffs(), "buffs_ocr_agg": _agg(own={"def": WIDGET_PCT - 5.0}),
            "trio": trio, "p2_role": "defending", "was_rally": False,
        })
        assert eff.ocr_own_def_pct == pytest.approx(0.0)

    def test_no_trio_is_passthrough(self):
        eff = _effective_buffs({
            "buffs": Buffs(), "buffs_ocr_agg": _agg(own={"def": 25.0}),
        })
        assert eff.ocr_own_def_pct == pytest.approx(25.0)
