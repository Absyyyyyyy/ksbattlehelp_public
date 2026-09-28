import json
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero,
)
from kingshot_sim.io_pkg.profiles import (
    FighterSchema, fighter_to_json, fighter_from_json,
    save_fighter, load_fighter,
)


def _sample_fighter() -> Fighter:
    return Fighter(
        label="MyAccount",
        leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=8),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=6),
        joiners=(
            JoinerHero(hero_name="Chenko", level="MAX"),
            JoinerHero(hero_name="Howard", level="MAX"),
        ),
        bonuses=BonusVector(
            squad_atk_pct=80, squad_def_pct=70, squad_let_pct=40, squad_hp_pct=50,
            inf_atk_pct=20, inf_def_pct=15, inf_let_pct=10, inf_hp_pct=12,
            cav_atk_pct=20, cav_def_pct=15, cav_let_pct=10, cav_hp_pct=12,
            arc_atk_pct=20, arc_def_pct=15, arc_let_pct=10, arc_hp_pct=12,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=80_000),
                     TroopGroup(tier="T10",   count=20_000)),
            archer=(TroopGroup(tier="T10.5", count=60_000),),
        ),
    )


def test_round_trip_preserves_all_fields():
    f = _sample_fighter()
    json_str = fighter_to_json(f)
    f2 = fighter_from_json(json_str)
    assert f2.label == f.label
    assert f2.leader_inf.hero_name == "Eric"
    assert f2.leader_cav.widget_level == 8
    assert len(f2.joiners) == 2
    assert f2.bonuses.squad_atk_pct == 80
    assert f2.troops.cavalry == (
        TroopGroup(tier="T10.5", count=80_000),
        TroopGroup(tier="T10", count=20_000),
    )


def test_save_and_load(tmp_path):
    f = _sample_fighter()
    p = tmp_path / "fighter.json"
    save_fighter(f, p)
    f2 = load_fighter(p)
    assert f2.label == f.label
    assert f2.troops.total_count() == f.troops.total_count()


def test_invalid_tier_rejected_at_load():
    payload = json.dumps({
        "label": "Bad",
        "leader_inf": {"hero_name": "Eric", "level": "MAX"},
        "leader_cav": {"hero_name": "Petra", "level": "MAX"},
        "leader_arc": {"hero_name": "Jaeger", "level": "MAX"},
        "troops": {"infantry": [{"tier": "T99", "count": 1000}]},
    })
    with pytest.raises(Exception):
        fighter_from_json(payload)


def test_epic_as_leader_rejected_at_schema_layer():
    payload = json.dumps({
        "label": "Bad",
        "leader_inf": {"hero_name": "Chenko", "level": "MAX"},
        "leader_cav": {"hero_name": "Petra", "level": "MAX"},
        "leader_arc": {"hero_name": "Jaeger", "level": "MAX"},
    })
    with pytest.raises(Exception):
        fighter_from_json(payload)


def test_unknown_field_rejected():
    payload = json.dumps({
        "label": "Bad",
        "leader_inf": {"hero_name": "Eric", "level": "MAX"},
        "leader_cav": {"hero_name": "Petra", "level": "MAX"},
        "leader_arc": {"hero_name": "Jaeger", "level": "MAX"},
        "bogus_field": 123,
    })
    with pytest.raises(Exception):
        fighter_from_json(payload)


def test_minimum_valid_payload():
    payload = json.dumps({
        "label": "Min",
        "leader_inf": {"hero_name": "Eric", "level": "MAX"},
        "leader_cav": {"hero_name": "Petra", "level": "MAX"},
        "leader_arc": {"hero_name": "Jaeger", "level": "MAX"},
    })
    f = fighter_from_json(payload)
    assert f.label == "Min"
    assert f.bonuses.squad_atk_pct == 0
    assert f.troops.total_count() == 0
