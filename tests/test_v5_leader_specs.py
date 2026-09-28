import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, JoinerHero,
)
from kingshot_sim.optimizer.search_space import SearchSpace, TroopPool, LeaderSpec
from kingshot_sim.optimizer.enumerate import enumerate_candidates
from kingshot_sim.io_pkg.search_space_io import (
    SearchSpaceSchema, search_space_to_json, search_space_from_json,
)


def _basic_space(**overrides) -> SearchSpace:
    base = dict(
        available_mythic_inf=["Helga"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Jaeger"],
        available_joiners=[],
        troop_pool=TroopPool(march_cap=100_000),
        troop_ratio_step=0.50,
        n_joiners=0,
    )
    base.update(overrides)
    return SearchSpace(**base)


def test_get_leader_spec_falls_back_to_global_defaults():
    sp = _basic_space(leader_level="MAX", leader_widget_level=7)
    spec = sp.get_leader_spec("Helga")
    assert spec.level == "MAX"
    assert spec.widget_level == 7
    assert spec.gear_atk_pct == 0.0
    assert spec.gear_def_pct == 0.0


def test_get_leader_spec_uses_per_hero_override():
    sp = _basic_space(
        leader_widget_level=10,
        leader_specs={"Helga": LeaderSpec(level="MAX", widget_level=3,
                                            gear_atk_pct=42.0, gear_let_pct=15.0)},
    )
    spec = sp.get_leader_spec("Helga")
    assert spec.widget_level == 3
    assert spec.gear_atk_pct == 42.0
    assert spec.gear_let_pct == 15.0
    petra = sp.get_leader_spec("Petra")
    assert petra.widget_level == 10
    assert petra.gear_atk_pct == 0.0


def test_build_leader_hero_uses_spec():
    sp = _basic_space(
        leader_specs={"Helga": LeaderSpec(level="MAX", widget_level=8,
                                            gear_atk_pct=30.0, gear_def_pct=40.0,
                                            gear_let_pct=10.0, gear_hp_pct=20.0)},
    )
    h = sp.build_leader_hero("Helga")
    assert isinstance(h, LeaderHero)
    assert h.hero_name == "Helga"
    assert h.widget_level == 8
    assert h.gear_atk_pct == 30.0
    assert h.gear_def_pct == 40.0
    assert h.gear_let_pct == 10.0
    assert h.gear_hp_pct == 20.0


def test_enumerated_candidates_inherit_per_hero_widget_and_gear():
    sp = _basic_space(
        leader_widget_level=10,
        leader_specs={
            "Helga":  LeaderSpec(level="MAX", widget_level=3, gear_atk_pct=50.0),
            "Petra":  LeaderSpec(level="MAX", widget_level=5, gear_def_pct=25.0),
        },
    )
    candidates = list(enumerate_candidates(sp))
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.leader_inf.hero_name == "Helga"
        assert cand.leader_inf.widget_level == 3
        assert cand.leader_inf.gear_atk_pct == 50.0
        assert cand.leader_cav.hero_name == "Petra"
        assert cand.leader_cav.widget_level == 5
        assert cand.leader_cav.gear_def_pct == 25.0
        assert cand.leader_arc.hero_name == "Jaeger"
        assert cand.leader_arc.widget_level == 10
        assert cand.leader_arc.gear_atk_pct == 0.0


def test_search_space_json_roundtrip_with_leader_specs():
    sp = _basic_space(
        leader_specs={
            "Helga": LeaderSpec(level="MAX", widget_level=4,
                                  gear_atk_pct=12.5, gear_def_pct=22.0,
                                  gear_let_pct=8.0, gear_hp_pct=16.0),
        },
    )
    js = search_space_to_json(sp)
    sp2 = search_space_from_json(js)
    assert "Helga" in sp2.leader_specs
    h2 = sp2.leader_specs["Helga"]
    assert h2.widget_level == 4
    assert h2.gear_atk_pct == 12.5
    assert h2.gear_def_pct == 22.0
    assert h2.gear_let_pct == 8.0
    assert h2.gear_hp_pct == 16.0


def test_search_space_json_roundtrip_without_leader_specs_backward_compat():
    payload = """
    {
      "available_mythic_inf": ["Helga"],
      "available_mythic_cav": ["Petra"],
      "available_mythic_arc": ["Jaeger"],
      "available_joiners": [],
      "troop_pool": {
        "infantry_tier": "T10.5", "cavalry_tier": "T10.5",
        "archer_tier": "T10.5", "march_cap": 100000
      },
      "troop_ratio_step": 0.5, "min_inf_pct": 0.3,
      "n_joiners": 0, "bonuses": {},
      "leader_level": "MAX", "leader_widget_level": 7,
      "joiner_level": "MAX", "label_prefix": "Cand"
    }
    """
    sp = search_space_from_json(payload)
    assert sp.leader_specs == {}
    h = sp.build_leader_hero("Helga")
    assert h.widget_level == 7
    assert h.gear_atk_pct == 0.0


def test_per_hero_gear_affects_optimizer_score():
    from kingshot_sim.optimizer.best_counter import find_best_counter
    from kingshot_sim.config.fighter import Fighter

    defender = Fighter(
        label="def",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=5),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=5),
        leader_arc=LeaderHero(hero_name="Yang",   level="MAX", widget_level=5),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=200, squad_def_pct=180),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=80_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),),
            archer=(TroopGroup(tier="T10.5", count=80_000),),
        ),
    )
    common = dict(
        available_mythic_inf=["Helga"],
        available_mythic_cav=["Petra"],
        available_mythic_arc=["Jaeger"],
        available_joiners=["Howard"],
        troop_pool=TroopPool(march_cap=200_000),
        troop_ratio_step=0.5, n_joiners=1,
        bonuses=BonusVector(squad_atk_pct=180, squad_def_pct=160),
    )
    space_no_gear  = SearchSpace(**common)
    space_big_gear = SearchSpace(
        **common,
        leader_specs={"Helga": LeaderSpec(widget_level=10, gear_atk_pct=200.0)},
    )

    r_no  = find_best_counter(defender, space_no_gear,  top_k=1, screen_top_n=3,
                                 mc_trials=20, mc_seed=42, use_batched_screen=False)
    r_big = find_best_counter(defender, space_big_gear, top_k=1, screen_top_n=3,
                                 mc_trials=20, mc_seed=42, use_batched_screen=False)

    assert r_big.top_k[0].mc.score_median > r_no.top_k[0].mc.score_median, (
        f"Big gear should win: no-gear={r_no.top_k[0].mc.score_median}, "
        f"big-gear={r_big.top_k[0].mc.score_median}"
    )
