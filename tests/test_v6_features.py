import pytest
import numpy as np

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool
from kingshot_sim.optimizer.best_counter import find_best_counter, find_best_defender
from kingshot_sim.optimizer.enumerate import enumerate_candidates
from kingshot_sim.engine.batched import (
    run_batch_expected, run_batch_expected_defense,
)
from kingshot_sim.data.op_overrides import (
    set_op_override, clear_op_override, clear_all_overrides, list_op_overrides,
)


@pytest.fixture(autouse=True)
def _isolate_op_overrides():
    snapshot = list_op_overrides()
    clear_all_overrides()
    yield
    clear_all_overrides()
    for (hero, slot), rules in snapshot.items():
        for orig, new in rules:
            set_op_override(hero, slot, orig, new)


def _make_attacker_for_defense_tests() -> Fighter:
    return Fighter(
        label="threat",
        leader_inf=LeaderHero(hero_name="Triton", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Sophia", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Howard", level="MAX"),),
        bonuses=BonusVector(squad_atk_pct=200, squad_def_pct=180),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=120_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _basic_defender_space() -> SearchSpace:
    return SearchSpace(
        available_mythic_inf=["Helga", "Eric"],
        available_mythic_cav=["Petra", "Margot"],
        available_mythic_arc=["Jaeger", "Yang"],
        available_joiners=["Chenko", "Howard", "Quinn"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.25, n_joiners=2,
    )


def test_run_batch_expected_defense_matches_sequential():
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    attacker = _make_attacker_for_defense_tests()
    space = _basic_defender_space()
    candidates = list(enumerate_candidates(space))[:30]

    seq = []
    for cand in candidates:
        cfg = BattleConfig(attacker=attacker, defender=cand, rng_mode=RNGMode.EXPECTED)
        seq.append(run_battle(cfg).score)

    batch = run_batch_expected_defense(candidates, attacker)

    assert len(batch.score) == len(seq)
    np.testing.assert_allclose(batch.score, seq, atol=1e-9, rtol=1e-9)


def test_find_best_defender_batched_matches_sequential_ordering():
    attacker = _make_attacker_for_defense_tests()
    space = _basic_defender_space()

    r_batch = find_best_defender(attacker, space, top_k=5, screen_top_n=15,
                                    mc_trials=20, mc_seed=42, use_batched_screen=True)
    r_seq = find_best_defender(attacker, space, top_k=5, screen_top_n=15,
                                  mc_trials=20, mc_seed=42, use_batched_screen=False)

    bs = [e.mc.score_median for e in r_batch.top_k]
    ss = [e.mc.score_median for e in r_seq.top_k]
    assert bs == ss


def test_find_best_defender_batched_is_faster():
    import time
    attacker = _make_attacker_for_defense_tests()
    space = SearchSpace(
        available_mythic_inf=["Helga", "Eric", "Triton"],
        available_mythic_cav=["Petra", "Margot", "Sophia"],
        available_mythic_arc=["Jaeger", "Yang", "Vivian"],
        available_joiners=["Chenko", "Howard"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.20, n_joiners=2,
    )

    t0 = time.time()
    find_best_defender(attacker, space, top_k=3, screen_top_n=10,
                          mc_trials=10, mc_seed=0, use_batched_screen=False)
    seq_time = time.time() - t0

    t0 = time.time()
    find_best_defender(attacker, space, top_k=3, screen_top_n=10,
                          mc_trials=10, mc_seed=0, use_batched_screen=True)
    batch_time = time.time() - t0

    assert batch_time < seq_time / 1.5, (
        f"Batched should be at least 1.5× faster; "
        f"sequential={seq_time:.2f}s, batched={batch_time:.2f}s"
    )


def test_set_op_override_round_trip():
    set_op_override("Amadeus", "sk3", original_op=103, new_op=102)
    overrides = list_op_overrides()
    assert ("Amadeus", "sk3") in overrides
    assert (103, 102) in overrides[("Amadeus", "sk3")]


def test_set_op_override_replaces_prior_for_same_orig():
    set_op_override("Amadeus", "sk3", 103, 102)
    set_op_override("Amadeus", "sk3", 103, 101)
    overrides = list_op_overrides()
    rules = overrides[("Amadeus", "sk3")]
    assert (103, 101) in rules
    assert (103, 102) not in rules


def test_set_op_override_same_op_clears_it():
    set_op_override("Amadeus", "sk3", 103, 102)
    set_op_override("Amadeus", "sk3", 103, 103)
    assert ("Amadeus", "sk3") not in list_op_overrides()


def test_clear_op_override():
    set_op_override("Amadeus", "sk3", 103, 102)
    set_op_override("Amadeus", "sk3", 101, 103)
    clear_op_override("Amadeus", "sk3", 103)
    rules = list_op_overrides()[("Amadeus", "sk3")]
    assert (103, 102) not in rules
    assert (101, 103) in rules


def test_invalid_op_rejected():
    with pytest.raises(ValueError, match="not in any known family"):
        set_op_override("Amadeus", "sk3", 103, 999)


def test_op_override_actually_rewrites_skill():
    from kingshot_sim.config.fighter import LeaderHero
    from kingshot_sim.data.catalog import get_hero_skills

    amadeus = LeaderHero(hero_name="Amadeus", level="MAX", widget_level=10).to_hero()
    skills_before = get_hero_skills(amadeus)
    sk3_before = next(s for s in skills_before if s.slot == "sk3")
    op_before = sk3_before.effects[0].op
    assert op_before == 102, f"Sanity: Amadeus sk3 should default to op 102, got {op_before}"

    set_op_override("Amadeus", "sk3", 102, 103)
    skills_after = get_hero_skills(amadeus)
    sk3_after = next(s for s in skills_after if s.slot == "sk3")
    assert sk3_after.effects[0].op == 103


def test_op_override_changes_battle_outcome():
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    attacker = Fighter(
        label="amadeus-att",
        leader_inf=LeaderHero(hero_name="Amadeus", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",   level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger",  level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=150),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )
    defender = Fighter(
        label="def",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=150),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )
    cfg = BattleConfig(attacker=attacker, defender=defender, rng_mode=RNGMode.EXPECTED)

    score_default = run_battle(cfg).score
    set_op_override("Amadeus", "sk3", 102, 103)
    score_overridden = run_battle(cfg).score

    assert score_default != score_overridden, (
        f"Override should change battle outcome; both scored {score_default:.6f}"
    )


def test_optimizer_emits_quad_saul_when_pool_has_only_saul():
    space = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Jaeger"],
        available_joiners=["Saul"],
        troop_pool=TroopPool(march_cap=100_000),
        troop_ratio_step=0.5, n_joiners=4,
    )
    candidates = list(enumerate_candidates(space))
    assert len(candidates) > 0
    for cand in candidates:
        names = [j.hero_name for j in cand.joiners]
        assert names == ["Saul"] * 4, f"Expected 4 Sauls, got {names}"


def test_optimizer_with_mixed_pool_includes_quad_stacks():
    space = SearchSpace(
        available_mythic_inf=["Eric"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Jaeger"],
        available_joiners=["Chenko", "Saul"],
        troop_pool=TroopPool(march_cap=100_000),
        troop_ratio_step=0.5, n_joiners=4,
    )
    seen_combos = set()
    for cand in enumerate_candidates(space):
        seen_combos.add(tuple(j.hero_name for j in cand.joiners))
    assert ("Chenko",) * 4 in seen_combos
    assert ("Saul",) * 4 in seen_combos


def test_amadeus_widget_active_on_rally_only():
    from kingshot_sim.config.fighter import LeaderHero
    amadeus = LeaderHero(hero_name="Amadeus", level="MAX", widget_level=10).to_hero()
    rally_widgets   = [s for s in amadeus.skills("rally")    if s.slot == "widget"]
    defender_widgets = [s for s in amadeus.skills("defender") if s.slot == "widget"]
    assert len(rally_widgets) == 1
    assert len(defender_widgets) == 0


def test_eric_widget_active_on_defender_only():
    from kingshot_sim.config.fighter import LeaderHero
    eric = LeaderHero(hero_name="Eric", level="MAX", widget_level=10).to_hero()
    rally_widgets   = [s for s in eric.skills("rally")    if s.slot == "widget"]
    defender_widgets = [s for s in eric.skills("defender") if s.slot == "widget"]
    assert len(rally_widgets) == 0
    assert len(defender_widgets) == 1


def test_archers_appear_in_top_counter_vs_inf_only_defender():
    defender = Fighter(
        label="all-inf-def",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=150, squad_def_pct=150),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=300_000),),
            cavalry=(),
            archer=(),
        ),
    )
    space = SearchSpace(
        available_mythic_inf=["Helga", "Triton"],
        available_mythic_cav=["Petra", "Sophia"],
        available_mythic_arc=["Jaeger", "Yang"],
        available_joiners=["Chenko"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.10, n_joiners=1,
    )
    report = find_best_counter(defender, space, top_k=5, screen_top_n=15,
                                  mc_trials=20, mc_seed=0)
    top1 = report.top_k[0]
    arc_n = sum(g.count for g in top1.attacker.troops.archer)
    total = top1.attacker.troops.total_count()
    arc_pct = arc_n / max(total, 1)
    assert arc_pct >= 0.40, (
        f"Vs all-Inf defender, top-1 attacker should be archer-heavy; "
        f"got arc%={arc_pct:.0%}"
    )
