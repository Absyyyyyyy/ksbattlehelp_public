import math
import pytest

from kingshot_sim.engine.state import SquadState, FighterState
from kingshot_sim.engine.round import compute_damage
from kingshot_sim.engine.resolver import (
    aggregate_family, _pity_effective_rate, compute_skill_mod,
)
from kingshot_sim.domain.enums import SquadType, Family, RNGMode
from kingshot_sim.domain.skills import Effect


def _make_squad(
    sq_type: SquadType, count: int,
    base_atk: float, base_hp: float,
    atk_pct: float, def_pct: float, let_pct: float, hp_pct: float,
) -> SquadState:
    return SquadState(
        squad_type=sq_type,
        base_atk=base_atk,
        base_let=10.0,
        base_def=10.0,
        base_hp=base_hp,
        atk_factor=1.0 + atk_pct / 100.0,
        let_factor=1.0 + let_pct / 100.0,
        def_factor=1.0 + def_pct / 100.0,
        hp_factor=1.0 + hp_pct / 100.0,
        count=count,
        initial_count=count,
    )


def _make_fighter(label: str, side: str, squads: dict[SquadType, SquadState]) -> FighterState:
    return FighterState(
        label=label,
        side=side,
        squads=squads,
        skills=[],
    )


def test_sos_round_zero_example():
    att_inf = _make_squad(
        SquadType.INFANTRY, count=40_233,
        base_atk=491.0, base_hp=1473.0,
        atk_pct=293.66, def_pct=0.0, let_pct=251.82, hp_pct=0.0,
    )
    att_cav = _make_squad(
        SquadType.CAVALRY, count=40_323,
        base_atk=1473.0, base_hp=491.0,
        atk_pct=0.0, def_pct=0.0, let_pct=0.0, hp_pct=0.0,
    )
    att_arc = _make_squad(
        SquadType.ARCHER, count=40_233,
        base_atk=1964.0, base_hp=368.0,
        atk_pct=0.0, def_pct=0.0, let_pct=0.0, hp_pct=0.0,
    )
    attacker = _make_fighter("att", "rally", {
        SquadType.INFANTRY: att_inf,
        SquadType.CAVALRY: att_cav,
        SquadType.ARCHER: att_arc,
    })

    def_inf = _make_squad(
        SquadType.INFANTRY, count=23_644,
        base_atk=400.0, base_hp=1200.0,
        atk_pct=0.0, def_pct=200.0, let_pct=0.0, hp_pct=610.53,
    )
    def_cav = _make_squad(
        SquadType.CAVALRY, count=27_644,
        base_atk=1200.0, base_hp=400.0,
        atk_pct=0.0, def_pct=0.0, let_pct=0.0, hp_pct=0.0,
    )
    def_arc = _make_squad(
        SquadType.ARCHER, count=27_584,
        base_atk=1600.0, base_hp=300.0,
        atk_pct=0.0, def_pct=0.0, let_pct=0.0, hp_pct=0.0,
    )
    defender = _make_fighter("def", "defender", {
        SquadType.INFANTRY: def_inf,
        SquadType.CAVALRY: def_cav,
        SquadType.ARCHER: def_arc,
    })

    army_min = min(
        sum(s.count for s in attacker.squads.values()),
        sum(s.count for s in defender.squads.values()),
    )
    assert army_min == 78_872, f"armyMin should be 78872, got {army_min}"

    army_factor = math.sqrt(40_233 * army_min)
    assert abs(army_factor - 56_335) < 5, f"army_factor should be ~56335, got {army_factor:.0f}"

    att_per_troop = 491 * (1 + 293.66/100) * 10 * (1 + 251.82/100) / 100
    assert abs(att_per_troop - 680) < 1.5, f"att_per_troop should be ~680, got {att_per_troop:.2f}"

    def_per_troop = def_inf.base_def * def_inf.def_factor * def_inf.base_hp * def_inf.hp_factor / 100
    assert abs(def_per_troop - 2557.9) < 1.0, f"def_per_troop should be ~2557.9, got {def_per_troop:.2f}"

    att_effects = [Effect(op=102, value=26.0)]
    def_effects: list[Effect] = []

    damage = compute_damage(
        attacker_state=attacker,
        attacker_squad=SquadType.INFANTRY,
        defender_state=defender,
        defender_squad=SquadType.INFANTRY,
        army_min=army_min,
        round_idx=0,
        attacker_effects=att_effects,
        defender_effects=def_effects,
        fatigue_enabled=True,
    )

    assert damage == pytest.approx(188.7, abs=0.6), (
        f"Expected damage ≈ 188.7, got {damage:.4f}"
    )
    assert math.ceil(damage) == 189, (
        f"Expected ceil(damage) = 189, got {math.ceil(damage)}"
    )


def test_chenko_vs_amane_stacking():
    effs_4_chenko = [Effect(op=101, value=25.0) for _ in range(4)]
    factor_4_chenko = aggregate_family(effs_4_chenko, Family.DAMAGE_UP, SquadType.INFANTRY)
    assert factor_4_chenko == pytest.approx(2.00, abs=1e-9), \
        f"4 Chenko stack should be 2.00, got {factor_4_chenko}"

    effs_mixed = (
        [Effect(op=101, value=25.0) for _ in range(2)] +
        [Effect(op=102, value=25.0) for _ in range(2)]
    )
    factor_mixed = aggregate_family(effs_mixed, Family.DAMAGE_UP, SquadType.INFANTRY)
    assert factor_mixed == pytest.approx(2.25, abs=1e-9), \
        f"Mixed stack should be 2.25, got {factor_mixed}"

    assert factor_mixed > factor_4_chenko


def test_helga_amadeus_passive_additive_account_wide_d108():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, LeaderHero,
    )
    from kingshot_sim.engine.compile import _compute_squad_factors

    bv = BonusVector(squad_atk_pct=290.0)

    def _fighter(inf_name: str) -> Fighter:
        return Fighter(
            label="t",
            leader_inf=LeaderHero(inf_name, "MAX"),
            leader_cav=LeaderHero("Jabel", "MAX"),
            leader_arc=LeaderHero("Saul", "MAX"),
            joiners=(),
            bonuses=bv,
            troops=TroopRoster(),
        )

    atk_helga, *_ = _compute_squad_factors(_fighter("Helga"), SquadType.INFANTRY)
    atk_zoe,   *_ = _compute_squad_factors(_fighter("Zoe"),   SquadType.INFANTRY)

    helga_lead = LeaderHero("Helga", "MAX").to_hero().leader_atk_def_pct()
    zoe_lead   = LeaderHero("Zoe",   "MAX").to_hero().leader_atk_def_pct()
    base_helga = atk_helga - helga_lead / 100.0
    base_zoe   = atk_zoe   - zoe_lead   / 100.0
    assert base_helga == pytest.approx(base_zoe, abs=1e-9), (
        "Helga passive must no longer change the engine factor (D-108): "
        f"{base_helga} vs {base_zoe}"
    )
    assert base_helga == pytest.approx(1.0 + 290.0 / 100.0, abs=1e-9)


def test_skill_mod_formula():
    att_effects = [
        Effect(op=102, value=50.0),
        Effect(op=211, value=20.0),
    ]
    def_effects = [
        Effect(op=112, value=30.0),
        Effect(op=202, value=-20.0),
    ]
    def_sq = SquadState(
        squad_type=SquadType.INFANTRY,
        base_atk=400, base_let=10, base_def=10, base_hp=1200,
        atk_factor=1.0, let_factor=1.0, def_factor=1.0, hp_factor=1.0,
        count=1000, initial_count=1000,
    )
    sm = compute_skill_mod(att_effects, def_effects, SquadType.INFANTRY, def_sq)
    expected = (1.50 * 1.20) / (0.80 * 1.30)
    assert sm == pytest.approx(expected, abs=1e-9)


def test_yang_pity_effective_rate():
    rate = _pity_effective_rate(0.40)
    assert rate == pytest.approx(0.581, abs=0.005), f"Pity rate should be ~0.581, got {rate}"


def test_pity_edge_cases():
    assert _pity_effective_rate(0.0) == 0.0
    assert _pity_effective_rate(1.0) == 1.0
    assert _pity_effective_rate(0.50) == pytest.approx(2/3, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
