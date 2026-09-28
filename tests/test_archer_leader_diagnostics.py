from __future__ import annotations
import pytest
import numpy as np

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.compile import compile_fighter, _compute_squad_factors
from kingshot_sim.domain.enums import SquadType, RNGMode, Family
from kingshot_sim.engine.resolver import aggregate_family


INF_LEADER = "Eric"
CAV_LEADER = "Petra"

ARC_HEROES_BY_GEN = {
    1: "Saul",
    2: "Marlin",
    3: "Jaeger",
    4: "Rosa",
    5: "Vivian",
    6: "Yang",
}


def _build_attacker(arc_hero: str, widget_level: int = 0,
                     joiners: tuple = ()) -> Fighter:
    return Fighter(
        label=f"att-{arc_hero}",
        leader_inf=LeaderHero(hero_name=INF_LEADER, level="MAX", widget_level=widget_level),
        leader_cav=LeaderHero(hero_name=CAV_LEADER, level="MAX", widget_level=widget_level),
        leader_arc=LeaderHero(hero_name=arc_hero,    level="MAX", widget_level=widget_level),
        joiners=joiners,
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def _build_defender() -> Fighter:
    return Fighter(
        label="def-fixed",
        leader_inf=LeaderHero(hero_name="Helga",  level="MAX", widget_level=10),
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


@pytest.mark.parametrize("arc_hero", list(ARC_HEROES_BY_GEN.values()))
def test_leader_atk_pct_goes_only_to_leader_class(arc_hero):
    factors_inf = {}
    factors_cav = {}
    factors_arc = {}
    for h in ARC_HEROES_BY_GEN.values():
        f = _build_attacker(h, widget_level=0)
        atk_i, _, _, _ = _compute_squad_factors(f, SquadType.INFANTRY)
        atk_c, _, _, _ = _compute_squad_factors(f, SquadType.CAVALRY)
        atk_a, _, _, _ = _compute_squad_factors(f, SquadType.ARCHER)
        factors_inf[h] = atk_i
        factors_cav[h] = atk_c
        factors_arc[h] = atk_a

    inf_vals = set(round(v, 6) for v in factors_inf.values())
    cav_vals = set(round(v, 6) for v in factors_cav.values())
    assert len(inf_vals) == 1, (
        f"Inf atk_factor leaked across Arc-leader changes: {factors_inf}"
    )
    assert len(cav_vals) == 1, (
        f"Cav atk_factor leaked across Arc-leader changes: {factors_cav}"
    )

    gens_sorted = sorted(ARC_HEROES_BY_GEN.keys())
    expected_order = [ARC_HEROES_BY_GEN[g] for g in gens_sorted]
    actual_order = sorted(factors_arc.keys(), key=lambda h: factors_arc[h])
    assert actual_order == expected_order, (
        f"Arc atk_factor not monotonic in generation. "
        f"Got: {[(h, round(factors_arc[h], 4)) for h in actual_order]}; "
        f"expected order by Gen 1→6: {expected_order}."
    )


@pytest.mark.parametrize("arc_hero", list(ARC_HEROES_BY_GEN.values()))
def test_widget_let_hp_bonus_goes_only_to_leader_class(arc_hero):
    let_inf = {}
    let_cav = {}
    let_arc = {}
    for h in ARC_HEROES_BY_GEN.values():
        f = _build_attacker(h, widget_level=10)
        _, _, l_i, _ = _compute_squad_factors(f, SquadType.INFANTRY)
        _, _, l_c, _ = _compute_squad_factors(f, SquadType.CAVALRY)
        _, _, l_a, _ = _compute_squad_factors(f, SquadType.ARCHER)
        let_inf[h] = l_i
        let_cav[h] = l_c
        let_arc[h] = l_a

    assert len(set(round(v, 6) for v in let_inf.values())) == 1, (
        f"Inf let_factor leaked: {let_inf}"
    )
    assert len(set(round(v, 6) for v in let_cav.values())) == 1, (
        f"Cav let_factor leaked: {let_cav}"
    )
    assert let_arc["Yang"] > let_arc["Saul"] + 0.5, (
        f"Yang widget should give a much larger Arc let_factor than Saul's. "
        f"Yang={let_arc['Yang']}, Saul={let_arc['Saul']}"
    )


def test_arc_atk_pct_strictly_increases_with_arc_leader_strength():
    f_saul = _build_attacker("Saul")
    f_yang = _build_attacker("Yang")
    atk_saul, _, _, _ = _compute_squad_factors(f_saul, SquadType.ARCHER)
    atk_yang, _, _, _ = _compute_squad_factors(f_yang, SquadType.ARCHER)
    ratio = atk_yang / atk_saul
    assert ratio > 2.0, (
        f"Expected Arc atk_factor(Yang) / atk_factor(Saul) > 2.0; "
        f"got {ratio:.4f}. atk_factor(Saul)={atk_saul:.4f}, "
        f"atk_factor(Yang)={atk_yang:.4f}."
    )


def test_rosa_sk3_arc_only_bonus_does_not_leak_to_inf_or_cav():
    from kingshot_sim.engine.compile import _gather_skills
    from kingshot_sim.engine.resolver import _expected_value_effect

    f = _build_attacker("Rosa")
    skills = _gather_skills(f, "rally")
    rosa_sk3 = next((s for s in skills if s.name == "Golden Rhythm"), None)
    assert rosa_sk3 is not None, "Rosa sk3 not found in gathered skills"

    eff = rosa_sk3.effects[0]
    assert eff.op == 102, f"Expected op 102 (Atk%), got {eff.op}"
    assert eff.target_squads == frozenset({SquadType.ARCHER}), (
        f"Rosa sk3 should target ARC only; got {eff.target_squads}"
    )

    all_effects = []
    for sk in skills:
        all_effects.extend(_expected_value_effect(sk))

    arc_dmg_up = aggregate_family(all_effects, Family.DAMAGE_UP, SquadType.ARCHER)
    inf_dmg_up = aggregate_family(all_effects, Family.DAMAGE_UP, SquadType.INFANTRY)
    cav_dmg_up = aggregate_family(all_effects, Family.DAMAGE_UP, SquadType.CAVALRY)

    no_sk3 = [e for e in all_effects if e is not eff]
    arc_dmg_up_no = aggregate_family(no_sk3, Family.DAMAGE_UP, SquadType.ARCHER)
    inf_dmg_up_no = aggregate_family(no_sk3, Family.DAMAGE_UP, SquadType.INFANTRY)
    cav_dmg_up_no = aggregate_family(no_sk3, Family.DAMAGE_UP, SquadType.CAVALRY)

    assert arc_dmg_up > arc_dmg_up_no, (
        f"Rosa sk3 +30% must affect Arc DamageUp. With sk3={arc_dmg_up:.4f}, "
        f"without={arc_dmg_up_no:.4f}."
    )
    assert inf_dmg_up == pytest.approx(inf_dmg_up_no, abs=1e-9), (
        f"Rosa sk3 (Arc-only) leaked into Inf DamageUp. "
        f"With sk3={inf_dmg_up:.4f}, without={inf_dmg_up_no:.4f}."
    )
    assert cav_dmg_up == pytest.approx(cav_dmg_up_no, abs=1e-9), (
        f"Rosa sk3 (Arc-only) leaked into Cav DamageUp. "
        f"With sk3={cav_dmg_up:.4f}, without={cav_dmg_up_no:.4f}."
    )


def test_thrud_sk1_inf_arc_only_does_not_leak_to_cav():
    from kingshot_sim.engine.compile import _gather_skills
    from kingshot_sim.engine.resolver import _expected_value_effect

    f = Fighter(
        label="att-thrud",
        leader_inf=LeaderHero(hero_name="Eric",  level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Thrud", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Saul",  level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    skills = _gather_skills(f, "rally")
    thrud_sk1 = next((s for s in skills if s.name == "Battle Hunger"), None)
    assert thrud_sk1 is not None

    for eff in thrud_sk1.effects:
        assert eff.target_squads == frozenset({SquadType.INFANTRY, SquadType.ARCHER}), (
            f"Thrud sk1 effect op {eff.op} should target Inf+Arc only; "
            f"got {eff.target_squads}"
        )

    all_effects = []
    for sk in skills:
        all_effects.extend(_expected_value_effect(sk))
    thrud_effs = set(thrud_sk1.effects)
    other_effects = [e for e in all_effects if e not in thrud_effs]

    inf_with = aggregate_family(all_effects, Family.DAMAGE_UP, SquadType.INFANTRY)
    inf_without = aggregate_family(other_effects, Family.DAMAGE_UP, SquadType.INFANTRY)
    cav_with = aggregate_family(all_effects, Family.DAMAGE_UP, SquadType.CAVALRY)
    cav_without = aggregate_family(other_effects, Family.DAMAGE_UP, SquadType.CAVALRY)

    assert inf_with > inf_without, "Thrud sk1 must boost Inf DamageUp"
    assert cav_with == pytest.approx(cav_without, abs=1e-9), (
        f"Thrud sk1 (Inf+Arc only) leaked into Cav. "
        f"With Thrud={cav_with:.4f}, without={cav_without:.4f}."
    )


def _run_score(arc_hero: str, defender: Fighter, widget_level: int = 10) -> float:
    f = _build_attacker(arc_hero, widget_level=widget_level)
    cfg = BattleConfig(attacker=f, defender=defender, rng_mode=RNGMode.EXPECTED)
    return run_battle(cfg).score


@pytest.mark.parametrize("weaker,stronger", [
    ("Saul", "Marlin"),
    ("Marlin", "Jaeger"),
    ("Jaeger", "Rosa"),
    ("Rosa", "Vivian"),
    ("Vivian", "Yang"),
    ("Saul", "Yang"),
    ("Saul", "Rosa"),
])
def test_later_generation_arc_leader_scores_higher(weaker, stronger):
    defender = _build_defender()
    s_weaker = _run_score(weaker, defender, widget_level=10)
    s_stronger = _run_score(stronger, defender, widget_level=10)
    assert s_stronger > s_weaker, (
        f"Expected {stronger} (later gen) to outscore {weaker} (earlier gen). "
        f"{weaker}={s_weaker:.6f}, {stronger}={s_stronger:.6f}. "
        f"This is the bug — drill into the data pipeline for this pair."
    )


def test_rally_widget_skill_contributes_when_attacking():
    from kingshot_sim.engine.compile import _gather_skills
    from kingshot_sim.engine.resolver import _expected_value_effect

    f0 = _build_attacker("Rosa", widget_level=0)
    f10 = _build_attacker("Rosa", widget_level=10)

    eff0 = []
    for sk in _gather_skills(f0, "rally"):
        eff0.extend(_expected_value_effect(sk))
    eff10 = []
    for sk in _gather_skills(f10, "rally"):
        eff10.extend(_expected_value_effect(sk))

    arc_dmg_0 = aggregate_family(eff0, Family.DAMAGE_UP, SquadType.ARCHER)
    arc_dmg_10 = aggregate_family(eff10, Family.DAMAGE_UP, SquadType.ARCHER)
    assert arc_dmg_10 > arc_dmg_0, (
        f"Rosa widget at lvl 10 (rally-side, +15% Let) must boost Arc DamageUp. "
        f"lvl 0={arc_dmg_0:.4f}, lvl 10={arc_dmg_10:.4f}."
    )


def test_defender_widget_skill_does_not_contribute_when_attacking():
    from kingshot_sim.engine.compile import _gather_skills

    f10 = _build_attacker("Saul", widget_level=10)
    rally_skills = _gather_skills(f10, "rally")
    assert not any("Rabbitgear Cannon" in s.name for s in rally_skills), (
        "Saul's defender-only widget skill leaked into the rally-side skill list!"
    )


def test_defender_widget_skill_contributes_when_defending():
    from kingshot_sim.engine.compile import _gather_skills

    f10 = _build_attacker("Saul", widget_level=10)
    defender_skills = _gather_skills(f10, "defender")
    assert any("Rabbitgear Cannon" in s.name for s in defender_skills), (
        "Saul's defender-only widget skill should appear when this fighter "
        "is treated as the defender — but it's missing from the defender-side "
        "skill list."
    )


def test_best_counter_does_not_pick_saul_when_rosa_available():
    from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool
    from kingshot_sim.optimizer.best_counter import find_best_counter

    defender = _build_defender()
    space = SearchSpace(
        available_mythic_inf=[INF_LEADER],
        available_mythic_cav=[CAV_LEADER],
        available_mythic_arc=["Saul", "Rosa"],
        available_joiners=["Chenko"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.10,
        n_joiners=1,
    )
    rep = find_best_counter(defender, space, top_k=5, screen_top_n=20,
                              mc_trials=10, mc_seed=0)
    top = rep.top_k[0]
    arc_leader_name = top.attacker.leader_arc.hero_name
    assert arc_leader_name == "Rosa", (
        f"Best Counter picked {arc_leader_name} as Arc leader over Rosa! "
        f"Top-5 leaders: {[e.attacker.leader_arc.hero_name for e in rep.top_k]}. "
        f"This is the user-reported bug."
    )


def test_best_counter_full_gen_ladder():
    from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool
    from kingshot_sim.optimizer.best_counter import find_best_counter

    defender = _build_defender()
    space = SearchSpace(
        available_mythic_inf=[INF_LEADER],
        available_mythic_cav=[CAV_LEADER],
        available_mythic_arc=list(ARC_HEROES_BY_GEN.values()),
        available_joiners=["Chenko"],
        troop_pool=TroopPool(march_cap=300_000),
        troop_ratio_step=0.10,
        n_joiners=1,
    )
    rep = find_best_counter(defender, space, top_k=5, screen_top_n=30,
                              mc_trials=10, mc_seed=0)
    top1_arc = rep.top_k[0].attacker.leader_arc.hero_name
    assert top1_arc != "Saul", (
        f"Best Counter picked Saul as top-1 Arc leader with the full Gen 1-6 "
        f"ladder available. Top-5: "
        f"{[e.attacker.leader_arc.hero_name for e in rep.top_k]}. "
        f"This is the anomaly the user reported."
    )


def test_print_arc_leader_score_table(capsys):
    defender = _build_defender()

    print("\n=== Arc-leader score comparison (defender held constant) ===")
    print(f"{'Hero':<10} {'Gen':<4} {'LdrMax%':<10} {'WidMax':<8} "
          f"{'Score':<10}")
    print("-" * 50)
    from kingshot_sim.data.reference import HERO_LEADER_MAX, HERO_WIDGET, WIDGET_MAX
    for gen, hero in ARC_HEROES_BY_GEN.items():
        score = _run_score(hero, defender, widget_level=10)
        ldr = HERO_LEADER_MAX[hero]
        wid = WIDGET_MAX[HERO_WIDGET[hero]]
        print(f"{hero:<10} {gen:<4} {ldr:<10.2f} {wid:<8.2f} {score:<10.6f}")

    assert True
