import math
import pytest

from kingshot_sim.config.fighter import TroopGroup, TroopRoster
from kingshot_sim.data.reference import (
    TIER_BASE_STATS, interpolated_tier_stat, tier_stat, make_tier_label,
)
from kingshot_sim.domain.enums import SquadType
from kingshot_sim.engine.compile import _aggregate_troops


def test_integer_level_is_exact_tier_stat():
    for lvl in (6, 9, 10, 11):
        assert interpolated_tier_stat(float(lvl), 0, "inf_atk") == pytest.approx(
            tier_stat(make_tier_label(lvl, 0), "inf_atk")
        )


def test_half_level_is_linear_midpoint_tg0():
    lo = TIER_BASE_STATS["T10"]["inf_atk"]
    hi = TIER_BASE_STATS["T11"]["inf_atk"]
    assert interpolated_tier_stat(10.5, 0, "inf_atk") == pytest.approx((lo + hi) / 2)
    assert interpolated_tier_stat(10.5, 0, "inf_atk") == pytest.approx(519.0)


def test_half_level_holds_truegold_fixed():
    lo = tier_stat("T10.TG3", "inf_atk")
    hi = tier_stat("T11.TG3", "inf_atk")
    assert interpolated_tier_stat(10.5, 3, "inf_atk") == pytest.approx((lo + hi) / 2)


def test_fraction_weighting_is_linear():
    lo = TIER_BASE_STATS["T9"]["inf_hp"]
    hi = TIER_BASE_STATS["T10"]["inf_hp"]
    assert interpolated_tier_stat(9.25, 0, "inf_hp") == pytest.approx(0.75 * lo + 0.25 * hi)


def test_level_clamped_to_tier_range():
    assert interpolated_tier_stat(0.5, 0, "inf_atk") == pytest.approx(
        tier_stat("T1", "inf_atk")
    )
    assert interpolated_tier_stat(12.0, 0, "inf_atk") == pytest.approx(
        tier_stat("T11", "inf_atk")
    )


def test_base_stat_none_level_matches_integer_lookup():
    g = TroopGroup(tier="T10.TG5", count=100)
    assert g.level is None
    assert g.base_stat("inf_atk") == pytest.approx(tier_stat("T10.TG5", "inf_atk"))


def test_base_stat_fractional_level_interpolates_at_its_tg():
    g = TroopGroup(tier="T10.TG3", count=100, level=10.5)
    expected = interpolated_tier_stat(10.5, 3, "inf_atk")
    assert g.base_stat("inf_atk") == pytest.approx(expected)


def test_invalid_level_rejected():
    with pytest.raises(ValueError):
        TroopGroup(tier="T10", count=100, level=12.5)
    with pytest.raises(ValueError):
        TroopGroup(tier="T10", count=100, level=0.0)


def test_aggregate_single_fractional_group():
    roster = TroopRoster(
        infantry=(TroopGroup(tier="T10", count=50_000, level=10.5),),
    )
    atk, hp, n = _aggregate_troops(roster, SquadType.INFANTRY)
    assert atk == pytest.approx(interpolated_tier_stat(10.5, 0, "inf_atk"))
    assert hp == pytest.approx(interpolated_tier_stat(10.5, 0, "inf_hp"))
    assert n == 50_000


def test_aggregate_integer_group_unchanged():
    roster = TroopRoster(infantry=(TroopGroup(tier="T10", count=50_000),))
    atk, hp, n = _aggregate_troops(roster, SquadType.INFANTRY)
    assert atk == pytest.approx(tier_stat("T10", "inf_atk"))
    assert hp == pytest.approx(tier_stat("T10", "inf_hp"))


def test_aggregate_mixed_fractional_and_integer():
    g_frac = TroopGroup(tier="T10", count=50_000, level=10.5)
    g_int = TroopGroup(tier="T9", count=50_000)
    roster = TroopRoster(infantry=(g_frac, g_int))
    atk, _, n = _aggregate_troops(roster, SquadType.INFANTRY)
    s_frac = interpolated_tier_stat(10.5, 0, "inf_atk")
    s_int = tier_stat("T9", "inf_atk")
    assert atk == pytest.approx(math.sqrt(s_frac * s_int))
    assert n == 100_000


def test_profile_roundtrip_preserves_level():
    from kingshot_sim.io_pkg.profiles import TroopGroupSchema
    g = TroopGroup(tier="T10.TG3", count=12_345, level=10.4)
    js = TroopGroupSchema.from_domain(g).model_dump_json()
    back = TroopGroupSchema.model_validate_json(js).to_domain()
    assert back.tier == "T10.TG3"
    assert back.count == 12_345
    assert back.level == pytest.approx(10.4)


def test_profile_pre_d60_save_without_level_loads():
    from kingshot_sim.io_pkg.profiles import TroopGroupSchema
    back = TroopGroupSchema.model_validate_json(
        '{"tier":"T10","count":100}'
    ).to_domain()
    assert back.level is None


def test_inputs_to_group_whole_number_is_clean_integer_tier():
    from kingshot_sim.webui.forms import _troop_inputs_to_group
    g = _troop_inputs_to_group(10.0, 3, 100)
    assert g.tier == "T10.TG3"
    assert g.level is None
    assert g.count == 100


def test_inputs_to_group_fractional_keeps_level_and_interpolates():
    from kingshot_sim.webui.forms import _troop_inputs_to_group
    g = _troop_inputs_to_group(10.5, 3, 100)
    assert g.level == pytest.approx(10.5)
    assert g.count == 100
    assert g.base_stat("inf_atk") == pytest.approx(
        interpolated_tier_stat(10.5, 3, "inf_atk")
    )


def test_inputs_to_group_empty_count_is_none():
    from kingshot_sim.webui.forms import _troop_inputs_to_group
    assert _troop_inputs_to_group(10.0, 0, 0) is None


def test_group_to_inputs_roundtrip():
    from kingshot_sim.webui.forms import (
        _troop_inputs_to_group, _troop_group_to_inputs,
    )
    g = _troop_inputs_to_group(9.7, 0, 5_000)
    lvl, tg, cnt = _troop_group_to_inputs(g)
    assert lvl == pytest.approx(9.7)
    assert tg == 0
    assert cnt == 5_000


def test_parse_level_label():
    from kingshot_sim.webui.easy_mode_form import _parse_level_label
    assert _parse_level_label("9.7", 11) == pytest.approx(9.7)
    assert _parse_level_label("Lv. 10.0", 11) == pytest.approx(10.0)
    assert _parse_level_label("", 11) == pytest.approx(11.0)
    assert _parse_level_label("99.9", 11) == pytest.approx(11.0)
