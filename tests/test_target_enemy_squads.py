from __future__ import annotations

from kingshot_sim.domain.enums import (
    SquadType, Family, OP_TO_FAMILY, family_for_op,
)
from kingshot_sim.domain.skills import Effect
from kingshot_sim.engine.resolver import aggregate_family


INF = frozenset({SquadType.INFANTRY})
CAV = frozenset({SquadType.CAVALRY})
ARC = frozenset({SquadType.ARCHER})
ALL = frozenset({SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER})


class TestOp212InFamily:
    def test_op_212_is_opp_defense_down(self):
        assert OP_TO_FAMILY[212] == Family.OPP_DEFENSE_DOWN
        assert family_for_op(212) == Family.OPP_DEFENSE_DOWN

    def test_op_212_stacks_multiplicatively_with_op_211(self):
        effects = [
            Effect(op=211, value=25.0, target_squads=ALL),
            Effect(op=212, value=25.0, target_squads=ALL),
        ]
        factor = aggregate_family(
            effects, Family.OPP_DEFENSE_DOWN, SquadType.ARCHER,
            enemy_squad=SquadType.ARCHER,
        )
        assert factor == 1.25 * 1.25


class TestTargetEnemySquadsFilter:
    def test_empty_filter_back_compat(self):
        e = Effect(op=102, value=30.0, target_squads=ALL)
        assert e.target_enemy_squads == frozenset()
        for own in (SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER):
            for enemy in (SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER):
                f = aggregate_family([e], Family.DAMAGE_UP, own, enemy_squad=enemy)
                assert f == 1.30, f"own={own}, enemy={enemy}: expected 1.30, got {f}"

    def test_filter_blocks_non_matching_defender(self):
        e = Effect(op=102, value=30.0, target_squads=ALL, target_enemy_squads=ARC)
        f_match = aggregate_family([e], Family.DAMAGE_UP, SquadType.INFANTRY,
                                    enemy_squad=SquadType.ARCHER)
        assert f_match == 1.30
        f_miss = aggregate_family([e], Family.DAMAGE_UP, SquadType.INFANTRY,
                                   enemy_squad=SquadType.CAVALRY)
        assert f_miss == 1.0
        f_miss2 = aggregate_family([e], Family.DAMAGE_UP, SquadType.INFANTRY,
                                    enemy_squad=SquadType.INFANTRY)
        assert f_miss2 == 1.0

    def test_two_filtered_effects_additive_when_matching(self):
        e_inf = Effect(op=102, value=25.0, target_squads=ALL, target_enemy_squads=INF)
        e_arc = Effect(op=102, value=30.0, target_squads=ALL, target_enemy_squads=ARC)
        f_inf = aggregate_family([e_inf, e_arc], Family.DAMAGE_UP,
                                  SquadType.INFANTRY, enemy_squad=SquadType.INFANTRY)
        assert f_inf == 1.25
        f_arc = aggregate_family([e_inf, e_arc], Family.DAMAGE_UP,
                                  SquadType.INFANTRY, enemy_squad=SquadType.ARCHER)
        assert f_arc == 1.30
        f_cav = aggregate_family([e_inf, e_arc], Family.DAMAGE_UP,
                                  SquadType.INFANTRY, enemy_squad=SquadType.CAVALRY)
        assert f_cav == 1.0

    def test_filter_additive_with_unfiltered_effect_when_matching(self):
        e_always = Effect(op=102, value=50.0, target_squads=ALL)
        e_vs_arc = Effect(op=102, value=30.0, target_squads=ALL, target_enemy_squads=ARC)
        f = aggregate_family([e_always, e_vs_arc], Family.DAMAGE_UP,
                              SquadType.INFANTRY, enemy_squad=SquadType.ARCHER)
        assert f == 1.80
        f_inf = aggregate_family([e_always, e_vs_arc], Family.DAMAGE_UP,
                                  SquadType.INFANTRY, enemy_squad=SquadType.INFANTRY)
        assert f_inf == 1.50

    def test_filter_redundant_when_target_squads_already_constrains(self):
        e_existing = Effect(op=211, value=25.0, target_squads=ARC)
        f = aggregate_family([e_existing], Family.OPP_DEFENSE_DOWN,
                              SquadType.ARCHER, enemy_squad=SquadType.ARCHER)
        assert f == 1.25
        f_miss = aggregate_family([e_existing], Family.OPP_DEFENSE_DOWN,
                                   SquadType.CAVALRY, enemy_squad=SquadType.CAVALRY)
        assert f_miss == 1.0


class TestBatchedParity:
    def test_batched_honors_target_enemy_squads(self):
        from kingshot_sim.engine.batched import _SideArrays
        e = Effect(op=102, value=30.0, target_squads=ALL, target_enemy_squads=ARC)
        import numpy as np
        expected = np.array([
            [1.0, 1.0, 1.3],
            [1.0, 1.0, 1.3],
            [1.0, 1.0, 1.3],
        ])
        squads = (SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER)
        out = np.empty((3, 3))
        for ai, asq in enumerate(squads):
            for di, dsq in enumerate(squads):
                f = aggregate_family([e], Family.DAMAGE_UP, asq, enemy_squad=dsq)
                out[ai, di] = f
        assert np.allclose(out, expected)
