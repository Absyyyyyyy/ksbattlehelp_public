from __future__ import annotations

from kingshot_sim.benchmark.economy import (
    acquisition_tier, shards_to_star, shards_to_skill_complete,
    STAR_SHARD_CUMULATIVE, SKILL_COMPLETE_STAR, gens_to_afford,
)
from kingshot_sim.benchmark.advisor import advise, advise_from_rankings
from kingshot_sim.benchmark.runner import HeroBuild, rank_generation, BenchSettings
from kingshot_sim.data.reference import heroes_up_to_generation, hero_class


def test_acquisition_tiers():
    assert acquisition_tier("Amadeus") == "cash"
    assert acquisition_tier("Helga") == "cash"
    assert acquisition_tier("Petra") == "roulette"
    assert acquisition_tier("Rosa") == "roulette"
    assert acquisition_tier("Wee & Woo") == "roulette"
    assert acquisition_tier("Eric") == "generic"
    assert acquisition_tier("Jaeger") == "generic"


def test_shard_cumulative_matches_absy_table():
    assert STAR_SHARD_CUMULATIVE[4] == 465
    assert STAR_SHARD_CUMULATIVE[5] == 1065


def test_shards_to_skill_complete():
    assert shards_to_skill_complete("MAX") == 0
    assert shards_to_skill_complete("4_0") == 0
    assert shards_to_skill_complete("0_0") == 465
    assert shards_to_star("2_0", SKILL_COMPLETE_STAR) == 465 - 50
    assert 0.9 < gens_to_afford(415) < 1.0


def test_gens_to_save():
    from kingshot_sim.benchmark.economy import gens_to_save
    assert gens_to_save(465, 450, have=0) == 2
    assert gens_to_save(465, 450, have=400) == 1
    assert gens_to_save(465, 450, have=465) == 0
    assert gens_to_save(465, 0) is None


def test_budget_spends_now_and_banks_the_rest():
    gen = 4
    builds = {h: HeroBuild(level="2_0", widget_level=2)
              for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense", shard_budget=1200, shard_income=450)
    funded_paid = sum(p.shards_to_4star for p in rep.spend_order
                      if p.verdict == "develop" and not p.is_roulette and p.funded)
    assert rep.spend_now == funded_paid
    assert 0 < rep.spend_now <= 1200
    assert rep.bank_amount == 1200 - rep.spend_now
    if rep.bank_amount > 0:
        assert rep.bank_target is not None
        _label, cost, gens, _arrival = rep.bank_target
        assert cost > 0 and (gens is None or gens >= 0)


def test_shard_ledger_conserves_and_carries_balance():
    gen = 4
    builds = {h: HeroBuild(level="2_0", widget_level=2)
              for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense", shard_budget=1000, shard_income=450)
    led = rep.shard_ledger
    assert led, "a budget+income should produce a forward ledger"
    assert led[0].gen == gen and led[0].start == 1000
    for i, s in enumerate(led):
        assert s.start + s.income - sum(c for _l, c in s.spends) == s.end
        assert s.end >= 0
        if i + 1 < len(led):
            assert led[i + 1].start == s.end
        for label, _c in s.spends:
            if "new gen" in label:
                arrival = int(label.split("new gen")[1].split(")")[0])
                assert arrival <= s.gen, f"funded {label} at gen {s.gen} before it exists"


def test_shard_ledger_empty_without_budget():
    gen = 4
    builds = {h: HeroBuild(level="2_0") for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense", shard_budget=None, shard_income=450)
    assert rep.shard_ledger == []


def test_upgrade_efficiency_reports_shard_and_widget():
    gen = 4
    builds = {h: HeroBuild(level="2_0", widget_level=2)
              for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense", widget_target=8)
    assert rep.develop_next
    for a in rep.develop_next:
        assert a.hero in rep.efficiency
        star_gain, star_sh, widget_gain, widget_lv = rep.efficiency[a.hero]
        assert star_gain >= 0.0 and widget_gain >= 0.0
        assert star_sh >= 0 and widget_lv >= 0
    assert any(rep.efficiency[a.hero][3] > 0 for a in rep.develop_next)


def test_player_profile_thresholds():
    from kingshot_sim.benchmark.economy import player_profile
    assert player_profile(0, 400) == "f2p"
    assert player_profile(2, 400) == "f2p"
    assert player_profile(3, 400) == "spender"
    assert player_profile(0, 450) == "f2p"
    assert player_profile(0, 451) == "spender"
    assert player_profile(8, 2000) == "whale"
    assert player_profile(10, 5000) == "whale"
    assert player_profile(7, 2000) == "spender"
    assert player_profile(8, 1999) == "spender"
    assert player_profile(4, 1000) == "spender"


def test_profile_weights_blend_is_wellformed():
    from kingshot_sim.benchmark.economy import PROFILE_WEIGHTS
    from kingshot_sim.benchmark.reference import SCENARIOS
    for prof, w in PROFILE_WEIGHTS.items():
        assert set(w) == set(SCENARIOS), prof
        assert abs(sum(w.values()) - 1.0) < 1e-9, prof
    f2p, whale = PROFILE_WEIGHTS["f2p"], PROFILE_WEIGHTS["whale"]
    assert whale["rally_atk"] > f2p["rally_atk"]
    assert whale["garrison"] > f2p["garrison"]
    assert f2p["defense"] > whale["defense"]


def test_all_around_weights_reweight_only_all_around():
    from kingshot_sim.benchmark.runner import rank_generation, BenchSettings
    from kingshot_sim.benchmark.economy import PROFILE_WEIGHTS
    from kingshot_sim.benchmark.reference import SCENARIOS
    gen = 2
    flat = rank_generation(gen, BenchSettings())
    weighted = rank_generation(gen, BenchSettings(),
                               all_around_weights=PROFILE_WEIGHTS["whale"])
    for s in SCENARIOS:
        assert flat.per_hero[s] == weighted.per_hero[s]
    assert flat.per_hero["all_around"] != weighted.per_hero["all_around"]


def test_whale_develops_4star_heroes_to_5star():
    gen = 5
    builds = {h: HeroBuild(level="4_0", widget_level=8)
              for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense", widget_target=8, shard_income=2000)
    assert rep.profile == "whale" and rep.target_star == 5
    assert all(p.target_star == 5 for p in rep.roadmap)
    assert any(p.verdict == "develop" for p in rep.roadmap)


def test_genranking_counts_battles():
    gen = 2
    gr = rank_generation(gen, BenchSettings())
    assert gr.n_battles == len(gr.ranked["solo_atk"]) * 4


def test_keep_skip_is_playstyle_dependent():
    gen = 5
    builds = {h: HeroBuild() for h in heroes_up_to_generation(gen)}
    builds["Thrud"] = HeroBuild(level="2_0")
    def_rep = advise(gen, builds, "defense")
    rally_rep = advise(gen, builds, "rally")
    assert ("Margot", "Thrud") in def_rep.keep_over
    assert ("Margot", "Thrud") not in rally_rep.keep_over


def test_smart_hold_develops_for_distant_small_upgrade():
    gen = 5
    builds = {h: HeroBuild(level="2_0", widget_level=2)
              for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "balanced", shard_income=450)
    cav = next(p for p in rep.roadmap if p.cls == "Cav")
    assert cav.verdict == "develop"
    assert cav.free_soon_hero == "Sophia" and cav.free_soon_gen == 6
    arc = next(p for p in rep.roadmap if p.cls == "Arc")
    assert arc.verdict == "develop"
    assert arc.free_soon_hero == "Wee & Woo" and arc.free_soon_gen == 7


def test_advises_acquiring_current_gen_hero():
    gen = 5
    builds = {h: HeroBuild(level="2_0") for h in heroes_up_to_generation(gen)
              if h not in ("Vivian", "Thrud")}
    rep = advise(gen, builds, "balanced")
    acq = {p.best_hero for p in rep.roadmap if p.acquire}
    assert acq & {"Vivian", "Thrud"}, \
        f"current-gen acquire not surfaced: {[(p.cls, p.best_hero, p.acquire) for p in rep.roadmap]}"
    assert any((not a.owned) for a in rep.develop_next if a.hero in acq)
    assert rep.best_trio is not None
    assert "Vivian" not in rep.best_trio and "Thrud" not in rep.best_trio
    assert all(a.acquisition != "cash" for a in rep.develop_next)
    acq_plans = [p for p in rep.roadmap if p.acquire and p.verdict in ("develop", "save")]
    if acq_plans:
        assert acq_plans[0].shards_to_4star == 465


def test_full_gen_roster_has_no_acquire_targets():
    gen = 5
    builds = {h: HeroBuild(level="2_0") for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "balanced")
    assert not any(p.acquire for p in rep.roadmap)
    assert all(a.owned for a in rep.develop_next)


def test_use_recommends_owned_cash_hero():
    gen = 1
    builds = {h: HeroBuild() for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "balanced")
    assert rep.best_trio is not None and "Amadeus" in rep.best_trio
    assert all(a.acquisition != "cash" for a in rep.develop_next)


def test_field_non_cash_when_it_outperforms_cash():
    gen = 2
    builds = {h: HeroBuild() for h in heroes_up_to_generation(gen)}
    builds["Amadeus"] = HeroBuild(level="1_0")
    rep = advise(gen, builds, "balanced")
    inf = next(h for h in rep.best_trio if hero_class(h) == "Inf")
    assert inf != "Amadeus", f"weak cash Amadeus fielded over a stronger non-cash Inf ({inf})"


def test_keeper_bank_target_excludes_held_hero():
    gen = 4
    roster = {"Alcar": ("4_3", 2), "Amadeus": ("3_5", 1), "Eric": ("3_0", 7),
              "Zoe": ("2_4", 2), "Hilde": ("2_3", 6), "Jabel": ("4_0", 4),
              "Margot": ("2_4", 2), "Petra": ("4_4", 7), "Jaeger": ("3_1", 6),
              "Marlin": ("2_2", 7), "Rosa": ("4_4", 2), "Saul": ("1_1", 6)}
    builds = {h: HeroBuild(level=lv, widget_level=w) for h, (lv, w) in roster.items()}
    rep = advise(gen, builds, "defense", shard_budget=1200, shard_income=500)
    held = {p.best_hero for p in rep.roadmap if p.verdict == "hold"}
    assert held, "precondition: at least one class is held"
    assert rep.bank_target is not None
    label = rep.bank_target[0].split(" ")[0]
    assert label not in held, f"bank target {label!r} is a held hero {held}"


def test_develop_next_targets_underleveled_non_cash():
    gen = 5
    builds = {h: HeroBuild(level="2_0") for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "balanced")
    assert rep.develop_next
    assert all(not a.skill_complete for a in rep.develop_next)
    assert all(a.acquisition != "cash" for a in rep.develop_next)
    assert rep.develop_next[0].shards_to_4star == 415
    assert [a.headroom for a in rep.develop_next] == \
        sorted((a.headroom for a in rep.develop_next), reverse=True)


def test_develop_is_one_per_class():
    gen = 5
    builds = {h: HeroBuild(level="2_0") for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense")
    classes = [hero_class(a.hero) for a in rep.develop_next]
    assert len(classes) == len(set(classes)), f"duplicate class in {classes}"
    assert {p.cls for p in rep.roadmap} <= {"Inf", "Cav", "Arc"}
    assert len(rep.roadmap) == len({p.cls for p in rep.roadmap})


def test_roadmap_holds_weak_class_for_strong_newcomer():
    gen = 5
    builds = {h: HeroBuild(level="3_0")
              for h in heroes_up_to_generation(gen) if hero_class(h) != "Cav"}
    builds["Jabel"] = HeroBuild(level="3_0")
    rep = advise(gen, builds, "garrison")
    cav = next(p for p in rep.roadmap if p.cls == "Cav")
    assert cav.verdict == "hold"
    assert cav.future_hero == "Sophia"
    assert "Jabel" not in [a.hero for a in rep.develop_next]


def test_maxed_roster_has_nothing_to_develop():
    gen = 3
    builds = {h: HeroBuild() for h in heroes_up_to_generation(gen)}
    rep = advise(gen, builds, "defense")
    assert rep.develop_next == []
    assert rep.roulette_hero == "Petra"


def test_advise_is_deterministic_and_pure_layer_callable():
    from kingshot_sim.benchmark.runner import user_strength_factor
    gen = 3
    builds = {h: HeroBuild(level="3_0") for h in heroes_up_to_generation(gen)}
    a = advise(gen, builds, "defense")
    b = advise(gen, builds, "defense")
    assert [h.hero for h in a.heroes] == [h.hero for h in b.heroes]
    assert a.keep_over == b.keep_over
    assert [p.verdict for p in a.roadmap] == [p.verdict for p in b.roadmap]
    s = BenchSettings()
    uf = user_strength_factor(builds)
    cur = rank_generation(gen, s, builds=builds, roster=set(builds), dummy_factor=uf)
    rep = advise_from_rankings(gen, builds, cur, cur, {}, "defense")
    assert len(rep.roadmap) == len({p.cls for p in rep.roadmap})
