from __future__ import annotations

import json
import pytest

from kingshot_sim.config.fighter import (
    BonusVector, Fighter, JoinerHero, LeaderHero, TroopGroup, TroopRoster,
)
from kingshot_sim.data.catalog import get_hero_skills
from kingshot_sim.data.reference import (
    default_skill_levels, max_skill_level, STAR_TO_MAX_SKILL_LVL,
)
from kingshot_sim.domain.heroes import Hero
from kingshot_sim.io_pkg.profiles import (
    FighterSchema, LeaderHeroSchema, fighter_from_json, fighter_to_json,
)


@pytest.mark.parametrize("level,expected", [
    ("0_0", (1, 0, 0)),
    ("0_5", (1, 0, 0)),
    ("1_0", (2, 2, 0)),
    ("1_5", (2, 2, 0)),
    ("2_0", (3, 3, 3)),
    ("2_5", (3, 3, 3)),
    ("3_0", (4, 4, 4)),
    ("3_5", (4, 4, 4)),
    ("4_0", (5, 5, 5)),
    ("4_5", (5, 5, 5)),
    ("MAX", (5, 5, 5)),
])
def test_default_skill_levels_per_star(level, expected):
    assert default_skill_levels(level) == expected


def test_max_skill_level_per_slot():
    assert max_skill_level("0_0", "sk1") == 1
    assert max_skill_level("0_0", "sk2") == 0
    assert max_skill_level("0_0", "sk3") == 0
    assert max_skill_level("1_0", "sk2") == 2
    assert max_skill_level("2_5", "sk1") == 3
    assert max_skill_level("MAX", "sk3") == 5


def test_star_to_max_skill_lvl_table_is_monotone():
    for slot_idx in range(3):
        caps = [STAR_TO_MAX_SKILL_LVL[s][slot_idx] for s in range(6)]
        assert caps == sorted(caps)


def test_hero_defaults_skill_levels_to_cap():
    h = Hero("Amadeus", "3_0", widget_level=0)
    assert h.skill_levels == (4, 4, 4)


def test_hero_max_keeps_5_5_5_defaults():
    h = Hero("Eric", "MAX", widget_level=10)
    assert h.skill_levels == (5, 5, 5)


def test_hero_rejects_skill_levels_above_cap():
    with pytest.raises(ValueError, match="exceeds cap"):
        Hero("Eric", "2_0", widget_level=0, skill_levels=(5, 5, 5))


def test_hero_accepts_skill_levels_at_or_below_cap():
    h = Hero("Eric", "2_0", widget_level=0, skill_levels=(1, 2, 3))
    assert h.skill_levels == (1, 2, 3)


def test_hero_rejects_sk3_at_locked_star():
    with pytest.raises(ValueError, match="exceeds cap"):
        Hero("Eric", "1_0", widget_level=0, skill_levels=(2, 2, 1))


def test_hero_skill_level_accessor():
    h = Hero("Petra", "3_5", widget_level=5, skill_levels=(2, 4, 3))
    assert h.skill_level("sk1") == 2
    assert h.skill_level("sk2") == 4
    assert h.skill_level("sk3") == 3


def test_catalog_max_hero_identical_to_pre_change_math():
    h = Hero("Amadeus", "MAX", widget_level=0)
    sks = {s.slot: s for s in get_hero_skills(h)}
    assert sks["sk1"].effects[0].value == pytest.approx(25.0)
    assert sks["sk2"].effects[0].value == pytest.approx(25.0)
    assert sks["sk3"].trigger.chance == pytest.approx(0.40)
    assert sks["sk3"].effects[0].value == pytest.approx(50.0)


def test_catalog_value_scales_with_per_skill_level():
    h_full = Hero("Eric", "MAX", widget_level=0)
    h_sk2_low = Hero("Eric", "MAX", widget_level=0, skill_levels=(5, 2, 5))

    full = {s.slot: s for s in get_hero_skills(h_full)}
    low  = {s.slot: s for s in get_hero_skills(h_sk2_low)}
    assert full["sk1"].effects[0].value == low["sk1"].effects[0].value
    assert full["sk3"].effects[0].value == low["sk3"].effects[0].value
    assert low["sk2"].effects[0].value == pytest.approx(0.4 * full["sk2"].effects[0].value)


def test_catalog_chance_scales_with_per_skill_level():
    h_lv5 = Hero("Helga", "MAX", widget_level=0)
    h_lv2 = Hero("Helga", "MAX", widget_level=0, skill_levels=(2, 5, 5))
    sk1_5 = next(s for s in get_hero_skills(h_lv5) if s.slot == "sk1")
    sk1_2 = next(s for s in get_hero_skills(h_lv2) if s.slot == "sk1")
    assert sk1_5.trigger.chance == pytest.approx(0.40)
    assert sk1_2.trigger.chance == pytest.approx(0.40 * 2 / 5)
    assert sk1_5.effects[0].value == sk1_2.effects[0].value == 50.0


def test_locked_sk3_at_star1_yields_zero():
    h = Hero("Eric", "1_5", widget_level=0)
    sks = {s.slot: s for s in get_hero_skills(h)}
    assert sks["sk3"].effects[0].value == 0.0


def test_leader_hero_default_skill_levels():
    lh = LeaderHero(hero_name="Eric", level="MAX", widget_level=10)
    assert lh.skill_levels == (5, 5, 5)
    assert lh.to_hero().skill_levels == (5, 5, 5)


def test_leader_hero_passes_explicit_skill_levels_through():
    lh = LeaderHero(hero_name="Eric", level="MAX", widget_level=10,
                    skill_levels=(3, 2, 1))
    assert lh.skill_levels == (3, 2, 1)
    assert lh.to_hero().skill_levels == (3, 2, 1)


def test_leader_hero_rejects_out_of_range():
    with pytest.raises(ValueError, match="exceeds cap"):
        LeaderHero(hero_name="Eric", level="2_0", widget_level=0,
                   skill_levels=(4, 4, 4))


def _fighter(skill_levels=None) -> Fighter:
    return Fighter(
        label="t",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10,
                              skill_levels=skill_levels),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Chenko", level="MAX"),),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def test_profile_roundtrip_with_explicit_skill_levels():
    f = _fighter(skill_levels=(3, 2, 1))
    blob = fighter_to_json(f)
    g = fighter_from_json(blob)
    assert g.leader_inf.skill_levels == (3, 2, 1)
    assert g.leader_cav.skill_levels == (5, 5, 5)


def test_profile_load_legacy_json_without_skill_levels():
    legacy = {
        "label": "old",
        "leader_inf": {"hero_name": "Eric",   "level": "3_0", "widget_level": 5},
        "leader_cav": {"hero_name": "Petra",  "level": "MAX", "widget_level": 10},
        "leader_arc": {"hero_name": "Jaeger", "level": "MAX", "widget_level": 10},
        "joiners":    [{"hero_name": "Chenko", "level": "MAX"}],
        "bonuses":    {},
        "troops":     {"infantry": [{"tier": "T10.5", "count": 100000}],
                       "cavalry":  [{"tier": "T10.5", "count": 100000}],
                       "archer":   [{"tier": "T10.5", "count": 100000}]},
    }
    f = fighter_from_json(json.dumps(legacy))
    assert f.leader_inf.skill_levels == (4, 4, 4)
    assert f.leader_cav.skill_levels == (5, 5, 5)


def test_profile_rejects_out_of_range_skill_levels():
    bad = LeaderHeroSchema(
        hero_name="Eric", level="2_0", widget_level=0,
        skill_levels=[5, 5, 5],
    )
    with pytest.raises(ValueError, match="exceeds cap"):
        bad.to_domain()
