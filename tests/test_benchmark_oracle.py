from __future__ import annotations

import pytest

from kingshot_sim.benchmark.runner import (
    BenchSettings, HeroBuild, rank_generation, build_dummy, trios_for_gen,
    GenRanking, user_strength_factor,
)
from kingshot_sim.benchmark.reference import GEN_LINEUPS
from kingshot_sim.data.reference import (
    hero_class, MYTHIC_HEROES, EPIC_HEROES, BENCHMARK_DUMMIES,
    heroes_up_to_generation,
)

_SETTINGS = BenchSettings()
_CACHE: dict[int, GenRanking] = {}


def _ranking(gen: int) -> GenRanking:
    if gen not in _CACHE:
        _CACHE[gen] = rank_generation(gen, _SETTINGS)
    return _CACHE[gen]


def _class_rank(per_hero: dict[str, float], hero: str) -> int:
    kls = hero_class(hero)
    ordered = sorted(
        ((v, h) for h, v in per_hero.items() if hero_class(h) == kls),
        reverse=True,
    )
    return [h for _, h in ordered].index(hero) + 1


@pytest.mark.parametrize("gen", list(range(1, 8)))
def test_oracle_heroes_top_their_class(gen: int):
    gr = _ranking(gen)
    for scen in GEN_LINEUPS[gen]:
        for hero in GEN_LINEUPS[gen][scen]:
            rk = _class_rank(gr.per_hero[scen], hero)
            assert rk <= 4, (
                f"gen{gen} {scen}: oracle hero {hero!r} ranked #{rk} in "
                f"{hero_class(hero)} (expected top-4)"
            )


def test_oracle_top3_aggregate():
    top3 = total = 0
    for gen in range(1, 8):
        gr = _ranking(gen)
        for scen in GEN_LINEUPS[gen]:
            for hero in GEN_LINEUPS[gen][scen]:
                total += 1
                if _class_rank(gr.per_hero[scen], hero) <= 3:
                    top3 += 1
    assert total == 63
    assert top3 >= 60, f"only {top3}/63 oracle placements were top-3"


@pytest.mark.parametrize("gen", [1, 2])
def test_amadeus_tops_inf_at_low_gens(gen: int):
    gr = _ranking(gen)
    assert _class_rank(gr.per_hero["solo_atk"], "Amadeus") == 1


def test_amadeus_stays_top2_inf_gen3_d117():
    gr = _ranking(3)
    assert _class_rank(gr.per_hero["solo_atk"], "Amadeus") <= 2


@pytest.mark.parametrize("gen", [3, 7])
def test_scores_spread(gen: int):
    gr = _ranking(gen)
    scores = [s for s, _ in gr.ranked["all_around"]]
    spread = max(scores) - min(scores)
    assert spread > 0.15, f"gen{gen} scores compressed (spread={spread:.3f})"
    assert -0.95 < (sum(scores) / len(scores)) < 0.95


def test_garrison_newer_cav_supersede_by_gen():
    def cav_order(gen):
        gr = _ranking(gen)
        ranked = sorted(((v, h) for h, v in gr.per_hero["garrison"].items()
                         if hero_class(h) == "Cav"), reverse=True)
        return [h for _, h in ranked]

    g5 = cav_order(5)
    g7 = cav_order(7)
    assert g7.index("Sophia") < g7.index("Hilde")
    assert g7.index("Ava") < g7.index("Petra")
    assert g5.index("Margot") < g5.index("Hilde")
    assert g7.index("Margot") < g7.index("Hilde")


def test_user_strength_factor():
    assert user_strength_factor(None) == 1.0
    assert user_strength_factor({}) == 1.0
    f = user_strength_factor({"Eric": HeroBuild(level="2_0")})
    assert 0.0 < f < 1.0


@pytest.mark.parametrize("level,skills", [("4_0", (5, 5, 5)), ("3_5", (2, 2, 2)),
                                          ("2_5", (3, 3, 3)), ("2_0", (2, 2, 2))])
def test_benchmark_fair_at_low_levels(level, skills):
    gen = 5
    builds = {h: HeroBuild(level=level, widget_level=4, skill_levels=skills)
              for h in heroes_up_to_generation(gen)}
    gr = rank_generation(gen, BenchSettings(), builds=builds)
    scores = [s for s, _ in gr.ranked["all_around"]]
    spread = max(scores) - min(scores)
    assert spread > 0.10, (
        f"level {level}: ranking compressed (spread={spread:.3f}) — mirror dummy "
        "is not tracking the user's tier"
    )


def test_dummies_segregated_from_real_roster():
    for name in BENCHMARK_DUMMIES:
        assert name not in MYTHIC_HEROES
        assert name not in EPIC_HEROES
    assert len(MYTHIC_HEROES) == 22


def test_dummy_fighter_builds_and_is_class_correct():
    dummy = build_dummy(7, _SETTINGS, (0.5, 0.2, 0.3))
    assert hero_class(dummy.leader_inf.hero_name) == "Inf"
    assert hero_class(dummy.leader_cav.hero_name) == "Cav"
    assert hero_class(dummy.leader_arc.hero_name) == "Arc"


def test_every_gen_enumerates_legal_trios():
    assert len(trios_for_gen(7)) == 8 * 7 * 7
    assert len(trios_for_gen(1)) >= 1
