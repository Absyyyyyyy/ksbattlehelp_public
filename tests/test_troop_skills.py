from __future__ import annotations

import pytest

from kingshot_sim.data.troop_skills import (
    tg8_always_on,
    troop_skill_outgoing_mult, troop_skill_incoming_mult,
    roll_tg_outgoing, roll_tg_incoming,
    dominant_tg,
    TG8_INF_DEF_PCT_BONUS, TG8_ARC_ATK_PCT_BONUS,
)
from kingshot_sim.data.user_data import set_data_override, clear_data_override
from kingshot_sim.domain.enums import SquadType

INF, CAV, ARC = SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER


@pytest.fixture(autouse=True)
def _clear_tg8_toggle():
    clear_data_override("engine.tg8_always_on")
    yield
    clear_data_override("engine.tg8_always_on")


class TestExpectedMultipliers:
    def test_tg0_to_tg2_have_no_skill(self):
        for tg in (0, 1, 2):
            for sq in (INF, CAV, ARC):
                assert troop_skill_outgoing_mult(sq, tg) == 1.0
                assert troop_skill_incoming_mult(sq, tg) == 1.0

    def test_tg3_inf_incoming(self):
        assert troop_skill_incoming_mult(INF, 3) == pytest.approx(0.910)
        assert troop_skill_incoming_mult(INF, 4) == pytest.approx(0.910)

    def test_tg3_cav_outgoing(self):
        assert troop_skill_outgoing_mult(CAV, 3) == pytest.approx(1.10)
        assert troop_skill_outgoing_mult(CAV, 4) == pytest.approx(1.10)

    def test_tg3_arc_outgoing(self):
        assert troop_skill_outgoing_mult(ARC, 3) == pytest.approx(1.10)
        assert troop_skill_outgoing_mult(ARC, 4) == pytest.approx(1.10)

    def test_tg5plus_inf_incoming(self):
        for tg in (5, 6, 7):
            assert troop_skill_incoming_mult(INF, tg) == pytest.approx(0.865)

    def test_tg5plus_cav_outgoing(self):
        for tg in (5, 6, 7, 8):
            assert troop_skill_outgoing_mult(CAV, tg) == pytest.approx(1.150)

    def test_tg5plus_arc_outgoing_no_tg8_addon(self):
        for tg in (5, 6, 7):
            assert troop_skill_outgoing_mult(ARC, tg) == pytest.approx(1.150)


    def test_tg8_inf_conditional_default(self):
        assert tg8_always_on() is False
        assert troop_skill_incoming_mult(INF, 8) == pytest.approx(0.8275)

    def test_tg8_arc_conditional_default(self):
        assert troop_skill_outgoing_mult(ARC, 8) == pytest.approx(1.225)

    def test_tg8_cav_independent_defensive_proc(self):
        assert troop_skill_incoming_mult(CAV, 8) == pytest.approx(0.95)
        assert troop_skill_outgoing_mult(CAV, 8) == pytest.approx(1.150)


    def test_tg8_inf_always_on_toggle(self):
        set_data_override("engine.tg8_always_on", 1)
        assert troop_skill_incoming_mult(INF, 8) == pytest.approx(0.7785)

    def test_tg8_arc_always_on_toggle(self):
        set_data_override("engine.tg8_always_on", 1)
        assert troop_skill_outgoing_mult(ARC, 8) == pytest.approx(1.4375)

    def test_tg8_cav_unaffected_by_toggle(self):
        for toggle in (0, 1):
            set_data_override("engine.tg8_always_on", toggle)
            assert troop_skill_incoming_mult(CAV, 8) == pytest.approx(0.95)
            assert troop_skill_outgoing_mult(CAV, 8) == pytest.approx(1.150)


class TestStochasticRolls:
    def _rng(self, seed=42):
        import random
        class _R:
            def __init__(self, seed): self._r = random.Random(seed)
            def random(self): return self._r.random()
        return _R(seed)

    def test_tg0_rolls_always_one(self):
        rng = self._rng()
        for _ in range(100):
            for sq in (INF, CAV, ARC):
                assert roll_tg_outgoing(rng, sq, 0) == 1.0
                assert roll_tg_incoming(rng, sq, 0) == 1.0

    def test_tg5_inf_roll_is_one_or_0_64(self):
        rng = self._rng()
        seen = set()
        for _ in range(500):
            v = roll_tg_incoming(rng, INF, 5)
            seen.add(round(v, 6))
        assert seen == {1.0, round(1.0 - 0.36, 6)}

    def test_tg5_cav_roll_is_one_or_two(self):
        rng = self._rng()
        seen = set()
        for _ in range(500):
            v = roll_tg_outgoing(rng, CAV, 5)
            seen.add(round(v, 6))
        assert seen == {1.0, 2.0}

    def test_tg8_arc_conditional_outputs_one_or_1_75(self):
        rng = self._rng()
        seen = set()
        for _ in range(500):
            v = roll_tg_outgoing(rng, ARC, 8)
            seen.add(round(v, 6))
        assert seen == {1.0, 1.75}

    def test_tg8_arc_always_on_outputs_1_25_or_1_875(self):
        set_data_override("engine.tg8_always_on", 1)
        rng = self._rng()
        seen = set()
        for _ in range(500):
            v = roll_tg_outgoing(rng, ARC, 8)
            seen.add(round(v, 6))
        assert seen == {1.25, 1.875}

    def test_stochastic_mean_matches_expected(self):
        rng = self._rng(seed=12345)
        n = 50_000
        total = sum(roll_tg_incoming(rng, INF, 5) for _ in range(n))
        observed = total / n
        ev = troop_skill_incoming_mult(INF, 5)
        assert abs(observed - ev) < 0.005, f"observed={observed}, ev={ev}"


class TestTg8PassiveStatBonuses:
    def _build_fighter(self, inf_tg: int, arc_tg: int):
        from kingshot_sim.config.fighter import (
            Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
        )
        return Fighter(
            label="probe",
            leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=0),
            leader_cav=LeaderHero(hero_name="Hilde",   level="MAX", widget_level=0),
            leader_arc=LeaderHero(hero_name="Marlin",  level="MAX", widget_level=0),
            joiners=(),
            bonuses=BonusVector(),
            troops=TroopRoster(
                infantry=(TroopGroup(tier=f"T10.TG{inf_tg}" if inf_tg > 0 else "T10",
                                      count=10_000),),
                cavalry=(TroopGroup(tier="T10", count=10_000),),
                archer=(TroopGroup(tier=f"T10.TG{arc_tg}" if arc_tg > 0 else "T10",
                                    count=10_000),),
            ),
        )

    def test_tg5_no_passive_bonus(self):
        from kingshot_sim.engine.compile import compile_fighter
        fs = compile_fighter(self._build_fighter(inf_tg=5, arc_tg=5), side="rally")
        inf_def_baseline = fs.squad(INF).def_factor
        arc_atk_baseline = fs.squad(ARC).atk_factor
        assert fs.squad(INF).dominant_tg == 5
        assert fs.squad(ARC).dominant_tg == 5

    def test_tg8_inf_gains_4pct_def(self):
        from kingshot_sim.engine.compile import compile_fighter
        fs_tg5 = compile_fighter(self._build_fighter(inf_tg=5, arc_tg=5), side="rally")
        fs_tg8 = compile_fighter(self._build_fighter(inf_tg=8, arc_tg=5), side="rally")
        assert fs_tg8.squad(INF).dominant_tg == 8
        diff = fs_tg8.squad(INF).def_factor - fs_tg5.squad(INF).def_factor
        assert diff == pytest.approx(TG8_INF_DEF_PCT_BONUS / 100.0)

    def test_tg8_arc_gains_4pct_atk(self):
        from kingshot_sim.engine.compile import compile_fighter
        fs_tg5 = compile_fighter(self._build_fighter(inf_tg=5, arc_tg=5), side="rally")
        fs_tg8 = compile_fighter(self._build_fighter(inf_tg=5, arc_tg=8), side="rally")
        assert fs_tg8.squad(ARC).dominant_tg == 8
        diff = fs_tg8.squad(ARC).atk_factor - fs_tg5.squad(ARC).atk_factor
        assert diff == pytest.approx(TG8_ARC_ATK_PCT_BONUS / 100.0)


class TestDominantTg:
    def test_single_group(self):
        from kingshot_sim.config.fighter import TroopGroup
        assert dominant_tg([TroopGroup(tier="T10.TG5", count=100_000)]) == 5
        assert dominant_tg([TroopGroup(tier="T10", count=100_000)]) == 0

    def test_count_weighted_pick(self):
        from kingshot_sim.config.fighter import TroopGroup
        groups = [
            TroopGroup(tier="T10.TG8", count=60_000),
            TroopGroup(tier="T10.TG5", count=40_000),
        ]
        assert dominant_tg(groups) == 8
        groups2 = [
            TroopGroup(tier="T10.TG8", count=40_000),
            TroopGroup(tier="T10.TG5", count=60_000),
        ]
        assert dominant_tg(groups2) == 5

    def test_tie_breaks_to_higher_tg(self):
        from kingshot_sim.config.fighter import TroopGroup
        groups = [
            TroopGroup(tier="T10.TG5", count=50_000),
            TroopGroup(tier="T10.TG8", count=50_000),
        ]
        assert dominant_tg(groups) == 8

    def test_empty(self):
        assert dominant_tg([]) == 0


class TestEndToEndToggleDivergence:
    def test_arc_tg8_attacker_deals_more_damage_when_always_on(self):
        from kingshot_sim.config.fighter import (
            Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
        )
        from kingshot_sim.engine.battle import BattleConfig, run_battle
        from kingshot_sim.domain.enums import RNGMode

        def _build(arc_tg: int, arc_count: int) -> Fighter:
            return Fighter(
                label=f"arc_tg{arc_tg}",
                leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=0),
                leader_cav=LeaderHero(hero_name="Hilde",   level="MAX", widget_level=0),
                leader_arc=LeaderHero(hero_name="Marlin",  level="MAX", widget_level=0),
                joiners=(),
                bonuses=BonusVector(),
                troops=TroopRoster(
                    infantry=(TroopGroup(tier="T10", count=10_000),),
                    cavalry=(TroopGroup(tier="T10", count=10_000),),
                    archer=(TroopGroup(tier=f"T10.TG{arc_tg}", count=arc_count),),
                ),
            )

        att_tg8 = _build(8, arc_count=100_000)
        defender_tg5 = _build(5, arc_count=2_000_000)

        cfg = BattleConfig(
            attacker=att_tg8, defender=defender_tg5,
            rng_mode=RNGMode.EXPECTED, fatigue_enabled=False,
        )
        res_cond = run_battle(cfg)
        cond_survivors_def_arc = res_cond.defender_final[ARC]

        set_data_override("engine.tg8_always_on", 1)
        res_aon = run_battle(cfg)
        aon_survivors_def_arc = res_aon.defender_final[ARC]

        assert aon_survivors_def_arc < cond_survivors_def_arc, (
            f"Always-on should kill more: cond={cond_survivors_def_arc}, "
            f"aon={aon_survivors_def_arc}"
        )


def test_sequential_batched_parity_with_tg8():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.engine.batched import run_batch_expected
    from kingshot_sim.domain.enums import RNGMode

    att = Fighter(
        label="att", joiners=(), bonuses=BonusVector(),
        leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Hilde",   level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Marlin",  level="MAX", widget_level=0),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.TG8", count=50_000),),
            cavalry=(TroopGroup(tier="T10.TG8", count=50_000),),
            archer=(TroopGroup(tier="T10.TG8", count=50_000),),
        ),
    )
    dfn = Fighter(
        label="dfn", joiners=(), bonuses=BonusVector(),
        leader_inf=LeaderHero(hero_name="Helga",   level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Jabel",   level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Saul",    level="MAX", widget_level=0),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.TG5", count=50_000),),
            cavalry=(TroopGroup(tier="T10.TG5", count=50_000),),
            archer=(TroopGroup(tier="T10.TG5", count=50_000),),
        ),
    )
    cfg = BattleConfig(
        attacker=att, defender=dfn,
        rng_mode=RNGMode.EXPECTED, fatigue_enabled=True,
    )
    seq = run_battle(cfg)
    bat = run_batch_expected([att], dfn, fatigue_enabled=True)
    seq_score = seq.score
    bat_score = float(bat.score[0])
    assert abs(seq_score - bat_score) < 1e-3, (
        f"Sequential vs batched score diverged on TG8 fighter: "
        f"seq={seq_score}, batched={bat_score}"
    )
