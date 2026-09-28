from __future__ import annotations

import pytest

from kingshot_sim.config.fighter import (
    Fighter, LeaderHero, BonusVector, TroopRoster, TroopGroup,
)
from kingshot_sim.data.reference import EPIC_HEROES
from kingshot_sim.benchmark.runner import trios_for_gen
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.domain.enums import RNGMode


def _mk(inf, cav, arc):
    bv = BonusVector(squad_atk_pct=100, squad_def_pct=100,
                     squad_let_pct=100, squad_hp_pct=100)
    tr = TroopRoster(
        infantry=(TroopGroup(tier="T10", count=33000),),
        cavalry=(TroopGroup(tier="T10", count=33000),),
        archer=(TroopGroup(tier="T10", count=34000),))
    return Fighter(
        label="x",
        leader_inf=LeaderHero(hero_name=inf, level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name=cav, level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name=arc, level="MAX", widget_level=10),
        joiners=(), bonuses=bv, troops=tr)


def test_epic_can_lead():
    h = LeaderHero(hero_name="Howard", level="MAX", widget_level=10).to_hero()
    assert h.is_epic
    assert h.widget_level == 0
    assert h.leader_atk_def_pct() == pytest.approx(140.11)
    assert all(s.slot == "sk1" for s in h.skills("rally"))


def test_epic_trio_builds_and_loses_to_mythic():
    epic = _mk("Howard", "Jabel", "Saul")
    myth = _mk("Amadeus", "Jabel", "Saul")
    r = run_battle(BattleConfig(attacker=epic, defender=myth,
                                rng_mode=RNGMode.EXPECTED, max_rounds=20))
    assert r.score < 0


def test_oracle_pool_is_mythic_only():
    flat = {h for t in trios_for_gen(7) for h in t}
    assert not (flat & EPIC_HEROES)


def test_benchmark_includes_owned_epics():
    roster = {"Amadeus", "Jabel", "Saul", "Howard"}
    flat = {h for t in trios_for_gen(1, roster=roster) for h in t}
    assert "Howard" in flat
