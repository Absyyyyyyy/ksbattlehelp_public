from __future__ import annotations
import json
import pytest
from pathlib import Path

from kingshot_sim.data import user_data as ud
from kingshot_sim.data import reference as ref
from kingshot_sim.data.user_data import (
    set_data_override, clear_data_override, clear_all_data_overrides,
    list_data_overrides, get_data_override, has_data_override,
    keys_with_prefix, KNOWN_PREFIXES, BLOCKED_KEYS,
)


@pytest.fixture(autouse=True)
def _isolate_data_overrides():
    snapshot = list_data_overrides()
    clear_all_data_overrides()
    yield
    clear_all_data_overrides()
    for k, v in snapshot.items():
        try:
            set_data_override(k, v)
        except ValueError:
            pass


def test_set_and_get_round_trip():
    set_data_override("hero_max.Yang", 600.0)
    assert get_data_override("hero_max.Yang", -1.0) == 600.0
    assert has_data_override("hero_max.Yang")
    assert list_data_overrides() == {"hero_max.Yang": 600.0}


def test_clear_single_key():
    set_data_override("hero_max.Yang", 600.0)
    set_data_override("hero_max.Sophia", 555.0)
    clear_data_override("hero_max.Yang")
    assert not has_data_override("hero_max.Yang")
    assert has_data_override("hero_max.Sophia")


def test_clear_all_wipes_registry():
    set_data_override("hero_max.Yang", 600.0)
    set_data_override("engine.cavalry_bypass_rate", 0.25)
    clear_all_data_overrides()
    assert list_data_overrides() == {}


def test_get_returns_default_when_absent():
    assert get_data_override("hero_max.Yang", 540.43) == 540.43


def test_clear_absent_key_is_noop():
    clear_data_override("hero_max.NotAHero")


def test_unknown_namespace_rejected():
    with pytest.raises(ValueError, match="does not match any known namespace"):
        set_data_override("weather.sunny", 1.0)


def test_blocked_keys_rejected():
    for blocked in BLOCKED_KEYS:
        with pytest.raises(ValueError, match="not adjustable"):
            set_data_override(blocked, 999.0)


def test_empty_key_rejected():
    with pytest.raises(ValueError, match="non-empty string"):
        set_data_override("", 1.0)


def test_known_prefixes_all_accepted():
    samples = {
        "tier_stat.": "tier_stat.T11.inf_atk",
        "hero_max.": "hero_max.Yang",
        "widget_max.": "widget_max.Frostkin",
        "helga_passive.": "helga_passive.5",
        "amadeus_passive.": "amadeus_passive.5",
        "engine.": "engine.type_bonus_pct",
    }
    for prefix, sample in samples.items():
        assert prefix in KNOWN_PREFIXES
        set_data_override(sample, 1.0)
        clear_data_override(sample)


def test_tier_stat_override_propagates():
    raw = ref.tier_stat("T10.5", "inf_atk")
    set_data_override("tier_stat.T10.5.inf_atk", raw + 100)
    assert ref.tier_stat("T10.5", "inf_atk") == raw + 100


def test_hero_max_override_propagates_through_leader_pct():
    raw_max = ref.HERO_LEADER_MAX["Yang"]
    raw_pct_at_max = ref.hero_leader_pct("Yang", "MAX")
    assert raw_pct_at_max == pytest.approx(raw_max * ref.LEVEL_FRACTION["MAX"])

    set_data_override("hero_max.Yang", raw_max + 100.0)
    new_pct_at_max = ref.hero_leader_pct("Yang", "MAX")
    assert new_pct_at_max == pytest.approx((raw_max + 100.0) * ref.LEVEL_FRACTION["MAX"])
    new_pct_at_3_5 = ref.hero_leader_pct("Yang", "3_5")
    assert new_pct_at_3_5 == pytest.approx((raw_max + 100.0) * ref.LEVEL_FRACTION["3_5"])


def test_widget_max_override_propagates():
    raw = ref.WIDGET_MAX["Frostkin"]
    set_data_override("widget_max.Frostkin", raw + 50.0)
    let, hp = ref.widget_stat_bonus("Frostkin", 10)
    assert let == pytest.approx(raw + 50.0)
    assert hp == pytest.approx(raw + 50.0)


def test_helga_passive_override_propagates():
    raw = ref.HELGA_PASSIVE[5]
    set_data_override("helga_passive.5", raw + 0.05)
    assert ref.helga_passive_value("MAX") == pytest.approx(raw + 0.05)
    assert ref.helga_passive_value("3_5") == pytest.approx(ref.HELGA_PASSIVE[3])


def test_amadeus_passive_override_propagates():
    raw = ref.AMADEUS_PASSIVE[5]
    set_data_override("amadeus_passive.5", raw + 0.05)
    assert ref.amadeus_passive_value("MAX") == pytest.approx(raw + 0.05)


def test_engine_constants_overrides_propagate():
    assert ref.cavalry_bypass_rate() == ref.CAVALRY_BYPASS_RATE
    set_data_override("engine.cavalry_bypass_rate", 0.30)
    assert ref.cavalry_bypass_rate() == pytest.approx(0.30)

    set_data_override("engine.archer_volley_rate", 0.15)
    assert ref.archer_volley_rate() == pytest.approx(0.15)

    set_data_override("engine.type_bonus_pct", 12.5)
    assert ref.type_bonus_pct() == pytest.approx(12.5)

    set_data_override("engine.fatigue_per_round", 0.0002)
    assert ref.fatigue_per_round() == pytest.approx(0.0002)


def test_valid_tiers_unchanged_by_existing_tier_override():
    set_data_override("tier_stat.T10.5.inf_atk", 999)
    assert ref.valid_tiers() == ref.VALID_TIERS


def test_valid_tiers_ignores_partial_new_tier():
    for stat in ("inf_atk", "inf_hp", "cav_atk", "cav_hp", "arc_atk"):
        set_data_override(f"tier_stat.T12.{stat}", 800)
    assert "T12" not in ref.valid_tiers()


def test_valid_tiers_recognizes_complete_new_tier():
    stats = {"inf_atk": 800, "inf_hp": 2400, "cav_atk": 2400,
             "cav_hp": 800, "arc_atk": 3200, "arc_hp": 552}
    for stat, val in stats.items():
        set_data_override(f"tier_stat.T12.{stat}", val)
    assert "T12" in ref.valid_tiers()
    assert ref.tier_stat("T12", "inf_atk") == 800.0
    assert ref.tier_stat("T12", "arc_hp") == 552.0


def test_tier_stat_raises_for_unknown_tier_without_full_override():
    with pytest.raises(KeyError, match="Unknown tier"):
        ref.tier_stat("T99", "inf_atk")


def test_tier_stat_raises_for_unknown_stat_name():
    with pytest.raises(KeyError, match="Unknown tier stat"):
        ref.tier_stat("T10.5", "made_up_stat")


def test_persistence_roundtrip(monkeypatch, tmp_path):
    persist = tmp_path / "data_overrides.json"
    monkeypatch.setattr(ud, "_PERSIST_PATH", persist)
    clear_all_data_overrides()

    set_data_override("hero_max.Yang", 600.0)
    set_data_override("engine.cavalry_bypass_rate", 0.25)
    set_data_override("tier_stat.T11.inf_atk", 700)

    ud._DATA_OVERRIDES.clear()
    ud._load()

    assert ud._DATA_OVERRIDES["hero_max.Yang"] == 600.0
    assert ud._DATA_OVERRIDES["engine.cavalry_bypass_rate"] == 0.25
    assert ud._DATA_OVERRIDES["tier_stat.T11.inf_atk"] == 700


def test_persistence_file_format_is_human_readable(monkeypatch, tmp_path):
    persist = tmp_path / "data_overrides.json"
    monkeypatch.setattr(ud, "_PERSIST_PATH", persist)
    clear_all_data_overrides()
    set_data_override("hero_max.Yang", 600.0)

    raw = persist.read_text()
    parsed = json.loads(raw)
    assert parsed["version"] == ud.PERSIST_VERSION
    assert parsed["overrides"] == {"hero_max.Yang": 600.0}
    assert "\n" in raw


def test_malformed_persistence_does_not_crash(monkeypatch, tmp_path):
    persist = tmp_path / "data_overrides.json"
    persist.write_text("{not valid json")
    monkeypatch.setattr(ud, "_PERSIST_PATH", persist)
    ud._DATA_OVERRIDES.clear()
    ud._load()
    assert ud._DATA_OVERRIDES == {}


def _make_pair():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    attacker = Fighter(
        label="att",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_atk_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=60_000),),
            cavalry=(TroopGroup(tier="T10.5", count=60_000),),
            archer=(TroopGroup(tier="T10.5", count=60_000),),
        ),
    )
    defender = Fighter(
        label="def",
        leader_inf=LeaderHero(hero_name="Helga",  level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Rosa",   level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=60_000),),
            cavalry=(TroopGroup(tier="T10.5", count=60_000),),
            archer=(TroopGroup(tier="T10.5", count=60_000),),
        ),
    )
    return attacker, defender


def test_type_bonus_override_changes_battle_score():
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    attacker, defender = _make_pair()
    cfg = BattleConfig(attacker=attacker, defender=defender, rng_mode=RNGMode.EXPECTED)
    score_default = run_battle(cfg).score

    set_data_override("engine.type_bonus_pct", 50.0)
    score_overridden = run_battle(cfg).score

    assert score_default != score_overridden, (
        f"Override should change battle outcome; both scored {score_default:.6f}"
    )


def test_cavalry_bypass_override_changes_battle_score():
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    attacker, defender = _make_pair()
    cfg = BattleConfig(attacker=attacker, defender=defender, rng_mode=RNGMode.EXPECTED)
    score_default = run_battle(cfg).score

    set_data_override("engine.cavalry_bypass_rate", 0.0)
    score_overridden = run_battle(cfg).score

    assert score_default != score_overridden, (
        f"Override should change battle outcome; both scored {score_default:.6f}"
    )


def test_batched_and_sequential_agree_under_override():
    import numpy as np
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.engine.batched import run_batch_expected
    from kingshot_sim.domain.enums import RNGMode

    attacker, defender = _make_pair()
    cfg = BattleConfig(attacker=attacker, defender=defender, rng_mode=RNGMode.EXPECTED)

    set_data_override("engine.type_bonus_pct", 25.0)
    set_data_override("engine.cavalry_bypass_rate", 0.10)

    seq_score = run_battle(cfg).score
    batch_scores = run_batch_expected([attacker], defender).score
    assert np.isclose(batch_scores[0], seq_score, atol=1e-9), (
        f"Batched and sequential disagreed under override: "
        f"seq={seq_score:.10f}, batched={batch_scores[0]:.10f}"
    )


def test_new_tier_full_override_works_in_compile():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    stats = {"inf_atk": 746, "inf_hp": 2238, "cav_atk": 2238,
             "cav_hp": 746, "arc_atk": 2984, "arc_hp": 560}
    for stat, val in stats.items():
        set_data_override(f"tier_stat.T11.{stat}", val)

    attacker, defender = _make_pair()
    attacker_t11 = Fighter(
        label="att-t11",
        leader_inf=attacker.leader_inf,
        leader_cav=attacker.leader_cav,
        leader_arc=attacker.leader_arc,
        joiners=attacker.joiners,
        bonuses=attacker.bonuses,
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T11", count=60_000),),
            cavalry=(TroopGroup(tier="T11", count=60_000),),
            archer=(TroopGroup(tier="T11", count=60_000),),
        ),
    )
    cfg_t10 = BattleConfig(attacker=attacker,     defender=defender, rng_mode=RNGMode.EXPECTED)
    cfg_t11 = BattleConfig(attacker=attacker_t11, defender=defender, rng_mode=RNGMode.EXPECTED)
    score_t10 = run_battle(cfg_t10).score
    score_t11 = run_battle(cfg_t11).score
    assert score_t11 > score_t10, (
        f"T11 (override-defined, 25% stronger) should score higher than "
        f"T10.5 against the same T10.5 defender. Got T10={score_t10}, T11={score_t11}."
    )


def test_sos_r0_anchor_still_passes_after_d34_wiring():
    from tests.test_damage_formula import test_sos_round_zero_example
    test_sos_round_zero_example()
