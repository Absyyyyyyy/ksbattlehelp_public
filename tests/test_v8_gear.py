from __future__ import annotations
import pytest

from kingshot_sim.data.gear import (
    base_bonus_pct, imbuement_bonus, piece_contribution,
    gearset_contribution, validate_piece, PieceBonus,
    MYTHIC_MAX_LEVEL, RED_MIN_LEVEL, RED_MAX_LEVEL,
    MASTERY_REQ_RED_ASCENSION, MASTERY_REQ_RED_LVL_200,
    VALID_SLOTS, VALID_QUALITIES,
)
from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, HeroGearPiece,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.compile import _compute_squad_factors
from kingshot_sim.domain.enums import SquadType, RNGMode


@pytest.mark.parametrize("level,expected_pct", [
    (0,    15.0),
    (5,    16.75),
    (10,   18.5),
    (25,   23.75),
    (50,   32.5),
    (75,   41.25),
    (95,   48.25),
    (100,  50.0),
])
def test_mythic_base_bonus_matches_source_table(level, expected_pct):
    assert base_bonus_pct("mythic", level) == pytest.approx(expected_pct, abs=0.01)


@pytest.mark.parametrize("level,expected_pct", [
    (100, 50.0),
    (110, 55.0),
    (120, 60.0),
    (150, 75.0),
    (180, 90.0),
    (200, 100.0),
])
def test_red_base_bonus_matches_source_table(level, expected_pct):
    assert base_bonus_pct("red", level) == pytest.approx(expected_pct, abs=0.01)


def test_mythic_and_red_agree_at_ascension_boundary():
    assert base_bonus_pct("mythic", 100) == base_bonus_pct("red", 100)


@pytest.mark.parametrize("slot,level,expected_atk,expected_def", [
    ("head",   100, 0.0,   0.0),
    ("head",   119, 0.0,   0.0),
    ("head",   120, 20.0,  0.0),
    ("head",   159, 20.0,  0.0),
    ("head",   160, 20.0,  30.0),
    ("head",   199, 20.0,  30.0),
    ("head",   200, 70.0,  30.0),
    ("chest",  200, 70.0,  30.0),
    ("gloves", 120, 0.0,   20.0),
    ("gloves", 160, 30.0,  20.0),
    ("gloves", 200, 30.0,  70.0),
    ("boots",  200, 30.0,  70.0),
])
def test_imbuement_milestones_red(slot, level, expected_atk, expected_def):
    atk, def_ = imbuement_bonus(slot, "red", level)
    assert atk == pytest.approx(expected_atk)
    assert def_ == pytest.approx(expected_def)


def test_imbuement_zero_for_mythic_quality():
    for slot in VALID_SLOTS:
        atk, def_ = imbuement_bonus(slot, "mythic", 100)
        assert (atk, def_) == (0.0, 0.0)


@pytest.mark.parametrize("quality,level", [
    ("mythic", -1),
    ("mythic", 101),
    ("red",    99),
    ("red",    201),
])
def test_invalid_level_for_quality_rejected(quality, level):
    with pytest.raises(ValueError):
        base_bonus_pct(quality, level)


def test_unknown_quality_rejected():
    with pytest.raises(ValueError, match="Unknown gear quality"):
        base_bonus_pct("legendary", 50)


def test_unknown_slot_rejected():
    with pytest.raises(ValueError, match="Unknown slot"):
        piece_contribution("helmet", "mythic", 50)


def test_strict_mastery_gates_red_ascension():
    with pytest.raises(ValueError, match="forge_mastery"):
        validate_piece("head", "red", 120,
                       forge_mastery=MASTERY_REQ_RED_ASCENSION - 1,
                       strict_mastery=True)
    validate_piece("head", "red", 120,
                   forge_mastery=MASTERY_REQ_RED_ASCENSION,
                   strict_mastery=True)


def test_strict_mastery_gates_red_level_200():
    with pytest.raises(ValueError, match="forge_mastery"):
        validate_piece("head", "red", 200,
                       forge_mastery=MASTERY_REQ_RED_LVL_200 - 1,
                       strict_mastery=True)
    validate_piece("head", "red", 200,
                   forge_mastery=MASTERY_REQ_RED_LVL_200,
                   strict_mastery=True)


def test_non_strict_mastery_does_not_gate():
    validate_piece("head", "red", 200, forge_mastery=0, strict_mastery=False)


def test_helm_base_bonus_routes_to_lethality():
    p = piece_contribution("head", "mythic", 100)
    assert p.let_pct == 50.0
    assert p.hp_pct == 0.0
    assert p.atk_pct == 0.0
    assert p.def_pct == 0.0


def test_chest_base_bonus_routes_to_health():
    p = piece_contribution("chest", "mythic", 100)
    assert p.hp_pct == 50.0
    assert p.let_pct == 0.0
    assert p.atk_pct == 0.0
    assert p.def_pct == 0.0


def test_gloves_base_bonus_routes_to_health():
    p = piece_contribution("gloves", "mythic", 100)
    assert p.hp_pct == 50.0
    assert p.let_pct == 0.0
    assert p.atk_pct == 0.0
    assert p.def_pct == 0.0


def test_boots_base_bonus_routes_to_lethality():
    p = piece_contribution("boots", "mythic", 100)
    assert p.let_pct == 50.0
    assert p.hp_pct == 0.0
    assert p.atk_pct == 0.0
    assert p.def_pct == 0.0


def test_full_red_l200_set_aggregates_correctly():
    pieces = {
        "head":   HeroGearPiece(slot="head",   quality="red", level=200),
        "chest":  HeroGearPiece(slot="chest",  quality="red", level=200),
        "gloves": HeroGearPiece(slot="gloves", quality="red", level=200),
        "boots":  HeroGearPiece(slot="boots",  quality="red", level=200),
    }
    total = gearset_contribution(pieces)
    assert total.atk_pct == pytest.approx(200.0)
    assert total.def_pct == pytest.approx(200.0)
    assert total.let_pct == pytest.approx(200.0)
    assert total.hp_pct  == pytest.approx(200.0)


def test_red_l200_helm_routes_correctly():
    p = piece_contribution("head", "red", 200)
    assert p.atk_pct == pytest.approx(70.0)
    assert p.def_pct == pytest.approx(30.0)
    assert p.let_pct == pytest.approx(100.0)
    assert p.hp_pct == pytest.approx(0.0)


def test_red_l200_gloves_routes_correctly():
    p = piece_contribution("gloves", "red", 200)
    assert p.atk_pct == pytest.approx(30.0)
    assert p.def_pct == pytest.approx(70.0)
    assert p.let_pct == pytest.approx(0.0)
    assert p.hp_pct == pytest.approx(100.0)


def test_per_piece_forge_mastery_is_independent():
    pieces = {
        "head":   HeroGearPiece(slot="head",   quality="red", level=200, forge_mastery=15),
        "chest":  HeroGearPiece(slot="chest",  quality="red", level=180, forge_mastery=12),
        "gloves": HeroGearPiece(slot="gloves", quality="mythic", level=100, forge_mastery=10),
        "boots":  HeroGearPiece(slot="boots",  quality="mythic", level=80,  forge_mastery=0),
    }
    assert pieces["head"].forge_mastery == 15
    assert pieces["chest"].forge_mastery == 12
    assert pieces["gloves"].forge_mastery == 10
    assert pieces["boots"].forge_mastery == 0
    total = gearset_contribution(pieces)
    assert total.atk_pct == pytest.approx(90.0)
    assert total.def_pct == pytest.approx(60.0)
    assert total.let_pct == pytest.approx(293.0)
    assert total.hp_pct == pytest.approx(298.0)


def test_mastery_is_multiplicative_on_base_d102():
    base = piece_contribution("head", "mythic", 50, forge_mastery=0).let_pct
    assert base == pytest.approx(32.5)
    m1 = piece_contribution("head", "mythic", 50, forge_mastery=1).let_pct
    assert m1 == pytest.approx(35.75)
    assert m1 == pytest.approx(base * 1.10)
    assert m1 != pytest.approx(42.5)
    assert piece_contribution("head", "mythic", 50, forge_mastery=2).let_pct == pytest.approx(39.0)
    assert piece_contribution("head", "mythic", 50, forge_mastery=20).let_pct == pytest.approx(97.5)

    p0 = piece_contribution("boots", "red", 200, forge_mastery=0)
    p10 = piece_contribution("boots", "red", 200, forge_mastery=10)
    assert p10.let_pct == pytest.approx(p0.let_pct * 2.0)
    assert p10.atk_pct == pytest.approx(p0.atk_pct)
    assert p10.def_pct == pytest.approx(p0.def_pct)


def _build_fighter_with_gear(gear: dict[str, HeroGearPiece]) -> Fighter:
    return Fighter(
        label="att",
        leader_inf=LeaderHero(
            hero_name="Eric", level="MAX", widget_level=0, gear=gear,
        ),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def test_inf_leader_gear_only_buffs_inf_squad():
    pieces = {
        "head":   HeroGearPiece(slot="head",   quality="red", level=200),
        "chest":  HeroGearPiece(slot="chest",  quality="red", level=200),
        "gloves": HeroGearPiece(slot="gloves", quality="red", level=200),
        "boots":  HeroGearPiece(slot="boots",  quality="red", level=200),
    }
    f_no_gear = _build_fighter_with_gear({})
    f_gear    = _build_fighter_with_gear(pieces)

    a_no, d_no, _, _ = _compute_squad_factors(f_no_gear, SquadType.INFANTRY)
    a_g,  d_g,  _, _ = _compute_squad_factors(f_gear,   SquadType.INFANTRY)
    assert a_g > a_no, f"Inf atk_factor should rise with full red gear: {a_no} → {a_g}"
    assert d_g > d_no, f"Inf def_factor should rise with full red gear: {d_no} → {d_g}"

    for sq in (SquadType.CAVALRY, SquadType.ARCHER):
        a_ng, d_ng, _, _ = _compute_squad_factors(f_no_gear, sq)
        a_g2, d_g2, _, _ = _compute_squad_factors(f_gear,   sq)
        assert a_ng == pytest.approx(a_g2, abs=1e-9), (
            f"Inf leader's gear leaked to {sq.name} atk_factor: "
            f"no_gear={a_ng}, with_gear={a_g2}"
        )
        assert d_ng == pytest.approx(d_g2, abs=1e-9), (
            f"Inf leader's gear leaked to {sq.name} def_factor: "
            f"no_gear={d_ng}, with_gear={d_g2}"
        )


def test_manual_mode_when_gear_dict_empty():
    h = LeaderHero(
        hero_name="Eric", level="MAX", widget_level=0,
        gear_atk_pct=100.0, gear_def_pct=80.0, gear_let_pct=10.0, gear_hp_pct=20.0,
    )
    atk, def_, let, hp = h.resolve_gear_contribution()
    assert (atk, def_, let, hp) == (100.0, 80.0, 10.0, 20.0)


def test_per_piece_mode_overrides_manual_fields_when_present():
    h = LeaderHero(
        hero_name="Eric", level="MAX", widget_level=0,
        gear_atk_pct=999.0, gear_def_pct=999.0, gear_let_pct=999.0, gear_hp_pct=999.0,
        gear={
            "head": HeroGearPiece(slot="head", quality="mythic", level=100),
        },
    )
    atk, def_, let, hp = h.resolve_gear_contribution()
    assert atk == pytest.approx(0.0)
    assert def_ == pytest.approx(0.0)
    assert let == pytest.approx(50.0)
    assert hp == pytest.approx(0.0)


def _identical_defender() -> Fighter:
    return Fighter(
        label="def",
        leader_inf=LeaderHero(hero_name="Helga",  level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Rosa",   level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(squad_def_pct=100),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


def test_full_red_l200_gear_increases_attacker_score():
    pieces = {
        "head":   HeroGearPiece(slot="head",   quality="red", level=200),
        "chest":  HeroGearPiece(slot="chest",  quality="red", level=200),
        "gloves": HeroGearPiece(slot="gloves", quality="red", level=200),
        "boots":  HeroGearPiece(slot="boots",  quality="red", level=200),
    }
    bare = Fighter(
        label="bare",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=(), bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    geared = Fighter(
        label="geared",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=0, gear=pieces),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0, gear=pieces),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0, gear=pieces),
        joiners=(), bonuses=BonusVector(),
        troops=bare.troops,
    )
    defender = _identical_defender()
    cfg_b = BattleConfig(attacker=bare,   defender=defender, rng_mode=RNGMode.EXPECTED)
    cfg_g = BattleConfig(attacker=geared, defender=defender, rng_mode=RNGMode.EXPECTED)
    s_b = run_battle(cfg_b).score
    s_g = run_battle(cfg_g).score
    assert s_g > s_b, (
        f"Full red lvl-200 gear should outscore bare attackers. "
        f"bare={s_b:.4f}, geared={s_g:.4f}"
    )


def test_per_piece_and_equivalent_manual_yield_same_score():
    manual = LeaderHero(
        hero_name="Eric", level="MAX", widget_level=0,
        gear_let_pct=50.0,
    )
    per_piece = LeaderHero(
        hero_name="Eric", level="MAX", widget_level=0,
        gear={"head": HeroGearPiece(slot="head", quality="mythic", level=100)},
    )

    cav = LeaderHero(hero_name="Petra",  level="MAX", widget_level=0)
    arc = LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0)
    troops = TroopRoster(
        infantry=(TroopGroup(tier="T10.5", count=100_000),),
        cavalry=(TroopGroup(tier="T10.5", count=100_000),),
        archer=(TroopGroup(tier="T10.5", count=100_000),),
    )
    f_manual = Fighter(label="m", leader_inf=manual, leader_cav=cav, leader_arc=arc,
                         joiners=(), bonuses=BonusVector(), troops=troops)
    f_piece  = Fighter(label="p", leader_inf=per_piece, leader_cav=cav, leader_arc=arc,
                         joiners=(), bonuses=BonusVector(), troops=troops)
    defender = _identical_defender()
    cfg_m = BattleConfig(attacker=f_manual, defender=defender, rng_mode=RNGMode.EXPECTED)
    cfg_p = BattleConfig(attacker=f_piece,  defender=defender, rng_mode=RNGMode.EXPECTED)
    s_m = run_battle(cfg_m).score
    s_p = run_battle(cfg_p).score
    assert s_m == pytest.approx(s_p, abs=1e-9), (
        f"Manual and per-piece modes should agree when configured "
        f"equivalently. manual={s_m:.6f}, per_piece={s_p:.6f}"
    )
