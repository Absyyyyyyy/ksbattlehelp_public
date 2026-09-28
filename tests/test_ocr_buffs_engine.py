from __future__ import annotations

import numpy as np
import pytest

from kingshot_sim.config.buffs import Buffs
from kingshot_sim.engine.section_d import (
    section_d_factor, own_pct, enemy_down_pct, LAYERS,
)


class TestOcrLayerInLAYERS:
    def test_ocr_layer_registered(self):
        assert "ocr" in LAYERS
        assert LAYERS[-1] == "ocr"


class TestOcrOwnBuffs:
    @pytest.mark.parametrize("stat,field", [
        ("atk", "ocr_own_atk_pct"), ("def", "ocr_own_def_pct"),
        ("let", "ocr_own_let_pct"), ("hp", "ocr_own_hp_pct"),
    ])
    def test_own_buff_raises_factor(self, stat, field):
        b = Buffs(**{field: 30.0})
        assert own_pct(b, stat, "ocr") == pytest.approx(30.0)
        assert section_d_factor(b, Buffs(), stat) == pytest.approx(1.30)

    def test_own_buff_only_affects_its_stat(self):
        b = Buffs(ocr_own_atk_pct=30.0)
        assert section_d_factor(b, Buffs(), "atk") == pytest.approx(1.30)
        for other in ("def", "let", "hp"):
            assert section_d_factor(b, Buffs(), other) == pytest.approx(1.0)


class TestOcrEnemyDebuffs:
    @pytest.mark.parametrize("stat,field", [
        ("atk", "ocr_enemy_atk_down_pct"), ("def", "ocr_enemy_def_down_pct"),
        ("let", "ocr_enemy_let_down_pct"), ("hp", "ocr_enemy_hp_down_pct"),
    ])
    def test_enemy_debuff_cuts_opponent_factor(self, stat, field):
        my = Buffs(**{field: 20.0})
        assert enemy_down_pct(my, stat, "ocr") == pytest.approx(20.0)
        assert section_d_factor(Buffs(), my, stat) == pytest.approx(0.80)


class TestOcrLayerComposition:
    def test_within_layer_additive_cancellation(self):
        own = Buffs(ocr_own_atk_pct=20.0)
        opp = Buffs(ocr_enemy_atk_down_pct=20.0)
        assert section_d_factor(own, opp, "atk") == pytest.approx(1.00)

    def test_partial_within_layer(self):
        own = Buffs(ocr_own_atk_pct=20.0)
        opp = Buffs(ocr_enemy_atk_down_pct=5.0)
        assert section_d_factor(own, opp, "atk") == pytest.approx(1.15)

    def test_ocr_multiplies_across_city_layer(self):
        b = Buffs(city_atk=20, ocr_own_atk_pct=10.0)
        assert section_d_factor(b, Buffs(), "atk") == pytest.approx(1.20 * 1.10)

    def test_negative_own_buff_lowers_factor(self):
        b = Buffs(ocr_own_def_pct=-15.0)
        assert section_d_factor(b, Buffs(), "def") == pytest.approx(0.85)


class TestOcrLayerNoOpWhenEmpty:
    def test_empty_buffs_unchanged(self):
        assert Buffs().is_empty() is True
        for stat in ("atk", "def", "let", "hp"):
            assert section_d_factor(Buffs(), Buffs(), stat) == pytest.approx(1.0)

    def test_ocr_field_breaks_is_empty(self):
        assert Buffs(ocr_own_let_pct=5.0).is_empty() is False
        assert Buffs(ocr_enemy_hp_down_pct=5.0).is_empty() is False


class TestSequentialBatchedParityWithOcrBuffs:
    def _fighter(self, buffs, ip=0.5, cp=0.3):
        from kingshot_sim.config.fighter import (
            Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
        )
        total = 300_000
        return Fighter(
            label="t",
            leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=0),
            leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
            leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
            joiners=(JoinerHero(hero_name="Chenko", level="MAX"),),
            bonuses=BonusVector(inf_atk_pct=100.0, cav_atk_pct=80.0, arc_atk_pct=60.0),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10.5", count=int(total * ip)),),
                cavalry=(TroopGroup(tier="T10.5", count=int(total * cp)),),
                archer=(TroopGroup(tier="T10.5", count=int(total * (1 - ip - cp))),),
            ),
            buffs=buffs,
        )

    def test_parity_with_ocr_own_and_enemy(self):
        from kingshot_sim.engine.battle import run_battle, BattleConfig
        from kingshot_sim.domain.enums import RNGMode
        from kingshot_sim.engine.batched import run_batch_expected

        att = self._fighter(Buffs(ocr_own_atk_pct=25.0, ocr_own_let_pct=12.0,
                                  ocr_enemy_def_down_pct=15.0))
        dfn = self._fighter(Buffs(ocr_own_def_pct=18.0, ocr_own_hp_pct=8.0,
                                  ocr_enemy_atk_down_pct=10.0), ip=0.4, cp=0.3)

        seq = run_battle(BattleConfig(
            attacker=att, defender=dfn,
            rng_mode=RNGMode.EXPECTED, max_rounds=200)).score
        batch = run_batch_expected([att], dfn, max_rounds=200)
        assert batch.score[0] == pytest.approx(seq, abs=1e-9)

    def test_ocr_buffs_change_the_outcome(self):
        from kingshot_sim.engine.battle import run_battle, BattleConfig
        from kingshot_sim.domain.enums import RNGMode

        dfn = self._fighter(Buffs(), ip=0.4, cp=0.3)
        base = run_battle(BattleConfig(
            attacker=self._fighter(Buffs()), defender=dfn,
            rng_mode=RNGMode.EXPECTED, max_rounds=200)).score
        buffed = run_battle(BattleConfig(
            attacker=self._fighter(Buffs(ocr_own_atk_pct=50.0, ocr_own_let_pct=50.0)),
            defender=dfn, rng_mode=RNGMode.EXPECTED, max_rounds=200)).score
        assert buffed > base


class TestBuffsProfileRoundTrip:
    def test_ocr_fields_round_trip(self):
        from kingshot_sim.io_pkg.profiles import BuffsSchema
        b = Buffs(
            ocr_own_atk_pct=25.0, ocr_own_def_pct=10.0, ocr_own_let_pct=15.0,
            ocr_own_hp_pct=5.0, ocr_enemy_atk_down_pct=20.0,
            ocr_enemy_def_down_pct=20.0, ocr_enemy_let_down_pct=5.0,
            ocr_enemy_hp_down_pct=5.0,
        )
        round_tripped = BuffsSchema.from_domain(b).to_domain()
        for f in (
            "ocr_own_atk_pct", "ocr_own_def_pct", "ocr_own_let_pct",
            "ocr_own_hp_pct", "ocr_enemy_atk_down_pct", "ocr_enemy_def_down_pct",
            "ocr_enemy_let_down_pct", "ocr_enemy_hp_down_pct",
        ):
            assert getattr(round_tripped, f) == pytest.approx(getattr(b, f))

    def test_pre_d59_profile_loads_with_zero_ocr(self):
        from kingshot_sim.io_pkg.profiles import BuffsSchema
        b = BuffsSchema(city_atk=20).to_domain()
        assert b.city_atk == 20
        assert b.ocr_own_atk_pct == 0.0
        assert b.is_empty() is False
        assert Buffs(city_atk=20).ocr_own_let_pct == 0.0
