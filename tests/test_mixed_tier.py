import math
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.domain.enums import SquadType
from kingshot_sim.engine.compile import _aggregate_troops, compile_fighter
from kingshot_sim.data.reference import TIER_BASE_STATS


def test_aggregate_single_tier_returns_tier_stats():
    troops = TroopRoster(
        infantry=(TroopGroup(tier="T10.5", count=100_000),),
        cavalry=(),
        archer=(),
    )
    atk, hp, n = _aggregate_troops(troops, SquadType.INFANTRY)
    assert atk == pytest.approx(TIER_BASE_STATS["T10.5"]["inf_atk"])
    assert hp == pytest.approx(TIER_BASE_STATS["T10.5"]["inf_hp"])
    assert n == 100_000


def test_aggregate_empty_squad():
    troops = TroopRoster(infantry=(), cavalry=(), archer=())
    atk, hp, n = _aggregate_troops(troops, SquadType.INFANTRY)
    assert (atk, hp, n) == (0.0, 0.0, 0)


def test_aggregate_two_tiers_uses_geometric_mean():
    t1 = TIER_BASE_STATS["T10.1"]["inf_atk"]
    t2 = TIER_BASE_STATS["T10.5"]["inf_atk"]
    troops = TroopRoster(
        infantry=(
            TroopGroup(tier="T10.1", count=50_000),
            TroopGroup(tier="T10.5", count=50_000),
        ),
        cavalry=(), archer=(),
    )
    atk, _, n = _aggregate_troops(troops, SquadType.INFANTRY)
    expected = math.sqrt(t1 * t2)
    assert atk == pytest.approx(expected, abs=0.01)
    assert n == 100_000


def test_aggregate_geometric_below_arithmetic():
    t1 = TIER_BASE_STATS["T6"]["inf_atk"]
    t2 = TIER_BASE_STATS["T10.5"]["inf_atk"]
    troops = TroopRoster(
        infantry=(
            TroopGroup(tier="T6", count=50_000),
            TroopGroup(tier="T10.5", count=50_000),
        ),
        cavalry=(), archer=(),
    )
    atk_geom, _, _ = _aggregate_troops(troops, SquadType.INFANTRY)
    atk_arith = (t1 + t2) / 2
    assert atk_geom < atk_arith
    assert atk_geom == pytest.approx(math.sqrt(t1 * t2), abs=0.1)


def test_aggregate_weighted_geometric_with_unequal_counts():
    t1 = TIER_BASE_STATS["T6"]["inf_atk"]
    t2 = TIER_BASE_STATS["T10.5"]["inf_atk"]
    troops = TroopRoster(
        infantry=(
            TroopGroup(tier="T6",     count=80_000),
            TroopGroup(tier="T10.5",  count=20_000),
        ),
        cavalry=(), archer=(),
    )
    atk, _, n = _aggregate_troops(troops, SquadType.INFANTRY)
    expected = math.exp(0.8 * math.log(t1) + 0.2 * math.log(t2))
    assert atk == pytest.approx(expected, abs=0.01)
    assert n == 100_000


def test_full_compile_mixed_tier_battle_runnable():
    fighter = Fighter(
        label="Mixed",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX"),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX"),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX"),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(
                TroopGroup(tier="T10.1", count=50_000),
                TroopGroup(tier="T10.5", count=50_000),
            ),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )
    state = compile_fighter(fighter, side="rally")
    inf = state.squad(SquadType.INFANTRY)
    assert 535 < inf.base_atk < 545
    assert inf.count == 100_000
