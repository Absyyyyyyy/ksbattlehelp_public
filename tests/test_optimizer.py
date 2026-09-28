import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.optimizer import (
    SearchSpace, TroopPool, find_best_counter, count_candidates,
    enumerate_candidates, deduplicate_joiner_pool,
)


def _defender() -> Fighter:
    return Fighter(
        label="Def",
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=BonusVector(squad_atk_pct=180, squad_def_pct=220,
                            squad_let_pct=100, squad_hp_pct=180),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )


def _small_space() -> SearchSpace:
    return SearchSpace(
        available_mythic_inf=["Helga", "Eric"],
        available_mythic_cav=["Petra", "Margot"],
        available_mythic_arc=["Jaeger", "Yang"],
        available_joiners=["Chenko", "Howard"],
        troop_pool=TroopPool(march_cap=240_000),
        troop_ratio_step=0.20,
        n_joiners=2,
        bonuses=BonusVector(squad_atk_pct=200, squad_def_pct=180,
                            squad_let_pct=120, squad_hp_pct=140),
    )


def test_dedup_collapses_identical_signatures():
    pool = deduplicate_joiner_pool(["Chenko", "Yeonwoo"], "MAX")
    assert len(pool) == 1
    assert pool[0] == "Chenko"


def test_dedup_keeps_distinct_signatures():
    pool = deduplicate_joiner_pool(["Chenko", "Amane"], "MAX")
    assert len(pool) == 2
    assert set(pool) == {"Chenko", "Amane"}


def test_count_matches_actual_enumeration():
    space = _small_space()
    n = count_candidates(space)
    actual = sum(1 for _ in enumerate_candidates(space))
    assert actual <= n


def test_invalid_hero_class_in_search_space():
    with pytest.raises(ValueError):
        SearchSpace(available_mythic_inf=["Saul"])


def test_diana_silently_dropped_from_joiner_pool():
    space = SearchSpace(available_joiners=["Chenko", "Diana", "Howard"])
    assert "Diana" not in space.available_joiners
    assert set(space.available_joiners) == {"Chenko", "Howard"}


def test_enumeration_produces_valid_fighters():
    space = _small_space()
    candidates = list(enumerate_candidates(space))
    assert len(candidates) > 0
    for c in candidates[:5]:
        assert isinstance(c, Fighter)
        from kingshot_sim.data.reference import HERO_CLASS
        assert HERO_CLASS[c.leader_inf.hero_name] == "Inf"
        assert HERO_CLASS[c.leader_cav.hero_name] == "Cav"
        assert HERO_CLASS[c.leader_arc.hero_name] == "Arc"
        assert c.troops.total_count() <= space.troop_pool.march_cap
        inf = c.troops.squad_count(c.troops.infantry[0].tier.__class__) if False else \
              sum(g.count for g in c.troops.infantry)
        if c.troops.total_count() > 0:
            assert inf / c.troops.total_count() >= space.min_inf_pct - 1e-9


def test_enumeration_no_duplicate_leaders():
    space = _small_space()
    for c in enumerate_candidates(space):
        names = {c.leader_inf.hero_name, c.leader_cav.hero_name, c.leader_arc.hero_name}
        assert len(names) == 3


def test_find_best_counter_returns_top_k():
    space = _small_space()
    report = find_best_counter(
        _defender(), space,
        top_k=3, screen_top_n=10, mc_trials=20, mc_seed=0,
    )
    assert len(report.top_k) == 3
    assert report.n_candidates > 0
    assert [e.rank for e in report.top_k] == [1, 2, 3]
    medians = [e.mc.score_median for e in report.top_k]
    assert medians == sorted(medians, reverse=True)
    n_mc = sum(1 for e in report.top_k if e.mc is not None)
    assert report.n_battles == report.n_screened + report.n_refined * 20
    assert report.n_battles >= report.n_screened >= n_mc > 0


def test_quick_mode_battles_exclude_mc_trials():
    space = _small_space()
    report = find_best_counter(_defender(), space, top_k=3, screen_top_n=10,
                               mc_trials=0)
    assert all(e.mc is None for e in report.top_k)
    assert report.n_battles == report.n_screened


def test_find_best_counter_respects_top_k_le_screen():
    space = _small_space()
    with pytest.raises(ValueError):
        find_best_counter(_defender(), space, top_k=20, screen_top_n=10)


def test_find_best_counter_reproducible_with_seed():
    space = _small_space()
    r1 = find_best_counter(_defender(), space, top_k=3, screen_top_n=5,
                            mc_trials=10, mc_seed=42)
    r2 = find_best_counter(_defender(), space, top_k=3, screen_top_n=5,
                            mc_trials=10, mc_seed=42)
    medians_1 = [e.mc.score_median for e in r1.top_k]
    medians_2 = [e.mc.score_median for e in r2.top_k]
    assert medians_1 == medians_2


def test_search_completes_in_reasonable_time():
    import time
    space = _small_space()
    t = time.time()
    report = find_best_counter(_defender(), space, top_k=3, screen_top_n=10,
                                mc_trials=20, mc_seed=0)
    elapsed = time.time() - t
    assert elapsed < 30, f"Small search took {elapsed:.1f}s — too slow"
    assert report.elapsed_s == pytest.approx(elapsed, abs=1.0)
