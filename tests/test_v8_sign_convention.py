from __future__ import annotations
import pytest

from kingshot_sim.data.catalog import get_hero_skills
from kingshot_sim.domain.heroes import Hero
from kingshot_sim.domain.skills import Effect
from kingshot_sim.domain.enums import Family, SquadType
from kingshot_sim.engine.resolver import aggregate_family


def test_spec_example_three_gordons_plus_one_howard_defense_up():
    effects = [
        Effect(113, 25.0), Effect(113, 25.0), Effect(113, 25.0),
        Effect(111, 20.0),
    ]
    factor = aggregate_family(effects, Family.DEFENSE_UP, SquadType.INFANTRY)
    assert factor == pytest.approx(2.10), (
        f"V8 D-36 anchor: 3 Gordons + 1 Howard DefenseUp must equal 2.10 "
        f"(spec §5.3). Got {factor:.4f}. If this is < 2.10, op 111 may be "
        f"stored as negative again — check catalog.py."
    )


def test_four_sauls_defense_up_equals_two_point_two_four():
    effects = [Effect(112, 10.0), Effect(113, 15.0)] * 4
    factor = aggregate_family(effects, Family.DEFENSE_UP, SquadType.INFANTRY)
    assert factor == pytest.approx(2.24)


_DOWN_OPS = (111, 201, 202, 203)

_ALL_HEROES = [
    "Amadeus", "Helga", "Jabel", "Saul",
    "Zoe", "Hilde", "Marlin",
    "Eric", "Petra", "Jaeger",
    "Alcar", "Margot", "Rosa",
    "Long Fei", "Thrud", "Vivian",
    "Triton", "Sophia", "Yang",
    "Howard", "Chenko", "Gordon", "Fahd",
    "Quinn", "Yeonwoo", "Amane",
]


def test_no_catalog_effect_stores_negative_down_op_value():
    offenders: list[str] = []
    for hero_name in _ALL_HEROES:
        hero = Hero(name=hero_name, level="MAX", widget_level=10)
        for sk in get_hero_skills(hero):
            for i, eff in enumerate(sk.effects):
                if eff.op in _DOWN_OPS and eff.value < 0:
                    offenders.append(
                        f"{hero_name} {sk.slot} effect[{i}] "
                        f"op={eff.op} value={eff.value}"
                    )
    assert not offenders, (
        f"V8 D-36 regression: {len(offenders)} catalog effect(s) on 'down' "
        f"ops have NEGATIVE values, which inverts their meaning:\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\n\nFlip them to POSITIVE in catalog.py. The user-facing "
        "description strings can stay '-X%' (in-game label); the stored "
        "value is the formula's additive contribution magnitude."
    )


@pytest.mark.parametrize("hero_name,slot,expected_op,expected_value", [
    ("Helga",     "sk1", 111, +50.0),
    ("Howard",    "sk1", 111, +20.0),
    ("Quinn",     "sk1", 111, +20.0),
    ("Eric",      "sk1", 202, +20.0),
    ("Fahd",      "sk1", 201, +20.0),
    ("Rosa",      "sk2", 201, +20.0),
])
def test_defensive_skill_value_positive(hero_name, slot, expected_op, expected_value):
    hero = Hero(name=hero_name, level="MAX", widget_level=0)
    target = next(s for s in get_hero_skills(hero) if s.slot == slot)
    assert target.effects[0].op == expected_op
    assert target.effects[0].value == pytest.approx(expected_value), (
        f"{hero_name} {slot}: expected stored value {expected_value} "
        f"(positive, post-D-36), got {target.effects[0].value}. The user-"
        f"facing description may still say '−X%' — that's the in-game "
        f"label; the stored magnitude must be positive."
    )


def test_defensive_skill_actually_reduces_attacker_damage():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
    )
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    attacker = Fighter(
        label="Att",
        leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",   level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",    level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=200),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    def_no_howard = Fighter(
        label="Def-no-Howard",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Saul",   level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    def_with_howard = Fighter(
        label="Def-with-Howard",
        leader_inf=def_no_howard.leader_inf,
        leader_cav=def_no_howard.leader_cav,
        leader_arc=def_no_howard.leader_arc,
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=def_no_howard.bonuses,
        troops=def_no_howard.troops,
    )

    cfg_no = BattleConfig(attacker=attacker, defender=def_no_howard,
                          rng_mode=RNGMode.EXPECTED)
    cfg_with = BattleConfig(attacker=attacker, defender=def_with_howard,
                            rng_mode=RNGMode.EXPECTED)

    score_no = run_battle(cfg_no).score
    score_with = run_battle(cfg_with).score

    assert score_with < score_no, (
        f"Howard's defensive joiner skill (op 111 +20%) should REDUCE the "
        f"attacker's score (the defender is tougher). Got "
        f"with_howard={score_with:.4f}, no_howard={score_no:.4f}. "
        f"If with_howard > no_howard, op 111 may be stored negative again "
        f"(V8 D-36 bug)."
    )
