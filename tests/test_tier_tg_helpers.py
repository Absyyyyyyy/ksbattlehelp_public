from __future__ import annotations
import pytest

from kingshot_sim.data.reference import (
    TIER_BASE_STATS,
    TIER_RANGE, TG_RANGE,
    make_tier_label, parse_tier_label,
    tier_stat, valid_tier_tg_pairs, valid_tiers,
)


class TestMakeTierLabel:
    def test_bare_tier(self):
        assert make_tier_label(6, 0) == "T6"
        assert make_tier_label(10, 0) == "T10"
        assert make_tier_label(11, 0) == "T11"

    def test_with_tg(self):
        assert make_tier_label(10, 5) == "T10.TG5"
        assert make_tier_label(6, 3) == "T6.TG3"
        assert make_tier_label(11, 8) == "T11.TG8"

    def test_tier_range_guard(self):
        with pytest.raises(ValueError, match="tier="):
            make_tier_label(0, 0)
        with pytest.raises(ValueError, match="tier="):
            make_tier_label(12, 0)

    def test_tg_range_guard(self):
        with pytest.raises(ValueError, match="tg="):
            make_tier_label(10, -1)
        with pytest.raises(ValueError, match="tg="):
            make_tier_label(10, 9)


class TestParseTierLabel:
    def test_bare(self):
        assert parse_tier_label("T6") == (6, 0)
        assert parse_tier_label("T10") == (10, 0)
        assert parse_tier_label("T11") == (11, 0)

    def test_canonical_tg(self):
        assert parse_tier_label("T10.TG5") == (10, 5)
        assert parse_tier_label("T6.TG3") == (6, 3)
        assert parse_tier_label("T11.TG8") == (11, 8)

    def test_legacy_short(self):
        assert parse_tier_label("T10.5") == (10, 5)
        assert parse_tier_label("T10.1") == (10, 1)

    def test_round_trip_canonical(self):
        for tier in range(TIER_RANGE[0], TIER_RANGE[1] + 1):
            for tg in range(TG_RANGE[0], TG_RANGE[1] + 1):
                label = make_tier_label(tier, tg)
                assert parse_tier_label(label) == (tier, tg)

    def test_round_trip_legacy(self):
        for legacy, canonical in [
            ("T10.1", "T10.TG1"),
            ("T10.5", "T10.TG5"),
        ]:
            assert parse_tier_label(legacy) == parse_tier_label(canonical)

    def test_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_tier_label("Tier10")
        with pytest.raises(ValueError):
            parse_tier_label("10")
        with pytest.raises(ValueError):
            parse_tier_label("T10.TG")
        with pytest.raises(ValueError):
            parse_tier_label("")


class TestCanonicalAliases:
    def test_alias_points_to_same_object(self):
        assert TIER_BASE_STATS["T10.5"] is TIER_BASE_STATS["T10.TG5"]
        assert TIER_BASE_STATS["T10.1"] is TIER_BASE_STATS["T10.TG1"]

    def test_tier_stat_equivalent_for_aliases(self):
        for legacy, canonical in [
            ("T10.1", "T10.TG1"),
            ("T10.3", "T10.TG3"),
            ("T10.5", "T10.TG5"),
        ]:
            for stat in ("inf_atk", "inf_hp", "cav_atk", "cav_hp", "arc_atk", "arc_hp"):
                assert tier_stat(legacy, stat) == tier_stat(canonical, stat)


class TestValidTierTgPairs:
    def test_dedup_alias(self):
        pairs = valid_tier_tg_pairs()
        assert pairs.count((10, 5)) == 1

    def test_baseline_pairs_present(self):
        pairs = set(valid_tier_tg_pairs())
        assert (6, 0) in pairs
        assert (9, 0) in pairs
        assert (10, 0) in pairs
        for tg in range(1, 6):
            assert (10, tg) in pairs

    def test_sorted_output(self):
        pairs = valid_tier_tg_pairs()
        assert list(pairs) == sorted(pairs)

    def test_full_grid_present_after_seed(self):
        pairs = set(valid_tier_tg_pairs())
        for tier in range(1, 12):
            for tg in range(0, 9):
                assert (tier, tg) in pairs, (
                    f"T{tier}.TG{tg} missing from valid_tier_tg_pairs() — "
                    f"the cascade seed should have created it."
                )
        from kingshot_sim.data.reference import TIER_BASE_STATS
        assert TIER_BASE_STATS["T10.TG8"]["inf_atk"] == 691
        assert TIER_BASE_STATS["T10.TG6"]["inf_atk"] == 627
        assert TIER_BASE_STATS["T10.TG7"]["inf_atk"] == 658
        assert TIER_BASE_STATS["T11.TG8"]["arc_hp"] == 571

    def test_valid_tiers_string_form_still_works(self):
        labels = set(valid_tiers())
        assert "T10.5" in labels
        assert "T10.TG5" in labels
