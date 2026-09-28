from __future__ import annotations
import pytest

from kingshot_sim.config.buffs import (
    Buffs, MOOSE_LEVEL_PCT, GRIZZLY_LEVEL_PCT, RHINO_LEVEL_PCT,
    PANTHER_LEVEL_PCT, ELEPHANT_LEVEL_PCT, LION_LEVEL_PCT,
)
from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.engine.compile import compile_fighter
from kingshot_sim.engine.montecarlo import run_monte_carlo
from kingshot_sim.domain.enums import RNGMode, SquadType


def test_default_buffs_is_empty():
    b = Buffs()
    assert b.is_empty()
    assert b.own_atk_multiplier() == 1.0
    assert b.own_def_multiplier() == 1.0
    assert b.own_let_multiplier() == 1.0
    assert b.own_hp_multiplier() == 1.0
    assert b.enemy_atk_down_multiplier() == 1.0
    assert b.enemy_def_down_multiplier() == 1.0
    assert b.enemy_let_down_multiplier() == 1.0


def test_city_buff_invalid_level_raises():
    with pytest.raises(ValueError, match="not allowed"):
        Buffs(city_atk=15)
    with pytest.raises(ValueError, match="not allowed"):
        Buffs(city_let=5)
    with pytest.raises(ValueError, match="not allowed"):
        Buffs(city_enemy_atk_down=30)


def test_pet_level_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        Buffs(moose_level=8)
    with pytest.raises(ValueError, match="out of range"):
        Buffs(grizzly_level=9)
    with pytest.raises(ValueError, match="out of range"):
        Buffs(rhino_level=11)


def test_moose_table_max():
    assert MOOSE_LEVEL_PCT[7] == 5.0
    assert MOOSE_LEVEL_PCT[1] == 1.5
    assert MOOSE_LEVEL_PCT[0] == 0.0


def test_grizzly_table_max():
    assert GRIZZLY_LEVEL_PCT[8] == 5.0
    assert GRIZZLY_LEVEL_PCT[1] == 1.5


def test_tier1_pets_share_same_scale():
    for lvl in range(11):
        assert RHINO_LEVEL_PCT[lvl] == PANTHER_LEVEL_PCT[lvl]
        assert RHINO_LEVEL_PCT[lvl] == ELEPHANT_LEVEL_PCT[lvl]
        assert RHINO_LEVEL_PCT[lvl] == LION_LEVEL_PCT[lvl]
    assert RHINO_LEVEL_PCT[5] == 5.0
    assert RHINO_LEVEL_PCT[10] == 10.0


def test_city_atk_alone():
    b = Buffs(city_atk=20)
    assert b.own_atk_multiplier() == pytest.approx(1.20)


def test_rhino_alone_max():
    b = Buffs(rhino_level=10)
    assert b.own_atk_multiplier() == pytest.approx(1.10)


def test_city_atk_and_rhino_stack_multiplicatively():
    b = Buffs(city_atk=20, rhino_level=10)
    assert b.own_atk_multiplier() == pytest.approx(1.32)


def test_hp_buffs_stack_three_way():
    b = Buffs(city_hp=20, moose_level=7, elephant_level=10)
    assert b.own_hp_multiplier() == pytest.approx(1.32)
    assert b.enemy_hp_down_multiplier() == pytest.approx(0.95)


def test_moose_is_enemy_hp_debuff():
    b = Buffs(moose_level=7)
    assert b.own_hp_multiplier() == pytest.approx(1.00)
    assert b.enemy_hp_down_multiplier() == pytest.approx(0.95)


def test_turrets_buff_own_let():
    from kingshot_sim.config.buffs import TURRET_LEVEL_PCT
    assert TURRET_LEVEL_PCT == {0: 0.0, 1: 8.0, 2: 12.0, 3: 15.0, 4: 20.0}
    assert Buffs(turrets=4).own_let_multiplier() == pytest.approx(1.20)
    assert Buffs(turrets=1).own_let_multiplier() == pytest.approx(1.08)
    assert Buffs(city_let=20, turrets=4).own_let_multiplier() == pytest.approx(1.44)
    with pytest.raises(ValueError):
        Buffs(turrets=5)


def test_enemy_debuff_stored_positive_returns_le_1():
    b = Buffs(city_enemy_atk_down=20)
    assert b.enemy_atk_down_multiplier() == pytest.approx(0.80)
    assert b.enemy_atk_down_multiplier() < 1.0

    b2 = Buffs(grizzly_level=8)
    assert b2.enemy_let_down_multiplier() == pytest.approx(0.95)
    assert b2.enemy_let_down_multiplier() < 1.0


def _build_fighter(label: str, buffs: Buffs = None) -> Fighter:
    kwargs = {} if buffs is None else {"buffs": buffs}
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name="Eric",  level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Yang",  level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
        **kwargs,
    )


def test_own_atk_buff_multiplies_atk_factor():
    base = _build_fighter("base")
    buffed = _build_fighter("buffed", buffs=Buffs(city_atk=20))

    base_state = compile_fighter(base, side="rally")
    buffed_state = compile_fighter(buffed, side="rally")

    for sq in SquadType.all():
        bf = base_state.squad(sq).atk_factor
        bb = buffed_state.squad(sq).atk_factor
        assert bb == pytest.approx(bf), (
            f"{sq}: atk_factor is no longer affected by Section D at compile. "
            f"base={bf:.4f}, buffed={bb:.4f}"
        )

    from kingshot_sim.engine.section_d import section_d_factor
    assert section_d_factor(buffed_state.buffs, base_state.buffs, "atk") == pytest.approx(1.20)
    assert section_d_factor(base_state.buffs,   buffed_state.buffs, "atk") == pytest.approx(1.0)


def test_own_hp_buff_multiplies_hp_factor_only():
    base = _build_fighter("base")
    buffed = _build_fighter("buffed", buffs=Buffs(city_hp=20))

    base_state = compile_fighter(base, side="rally")
    buffed_state = compile_fighter(buffed, side="rally")

    for sq in SquadType.all():
        sq_b = base_state.squad(sq)
        sq_p = buffed_state.squad(sq)
        assert sq_p.atk_factor == pytest.approx(sq_b.atk_factor)
        assert sq_p.def_factor == pytest.approx(sq_b.def_factor)
        assert sq_p.let_factor == pytest.approx(sq_b.let_factor)
        assert sq_p.hp_factor  == pytest.approx(sq_b.hp_factor)

    from kingshot_sim.engine.section_d import section_d_factor
    assert section_d_factor(buffed_state.buffs, base_state.buffs, "hp") == pytest.approx(1.20)
    assert section_d_factor(buffed_state.buffs, base_state.buffs, "atk") == pytest.approx(1.0)
    assert section_d_factor(buffed_state.buffs, base_state.buffs, "def") == pytest.approx(1.0)
    assert section_d_factor(buffed_state.buffs, base_state.buffs, "let") == pytest.approx(1.0)


def test_pet_buff_increases_battle_score():
    defender = _build_fighter("def")
    att_base = _build_fighter("att_base")
    att_buff = _build_fighter("att_rhino", buffs=Buffs(rhino_level=10))

    s_base = run_battle(BattleConfig(attacker=att_base, defender=defender,
                                       rng_mode=RNGMode.EXPECTED)).score
    s_buff = run_battle(BattleConfig(attacker=att_buff, defender=defender,
                                       rng_mode=RNGMode.EXPECTED)).score
    assert s_buff > s_base, (
        f"Rhino lvl 10 should increase attacker score. "
        f"base={s_base:.4f}, buffed={s_buff:.4f}"
    )


def test_enemy_atk_down_hurts_opponent_only():
    attacker = _build_fighter("att")
    def_base = _build_fighter("def_base")
    def_debuff = _build_fighter("def_debuff", buffs=Buffs(city_enemy_atk_down=20))

    s_base = run_battle(BattleConfig(attacker=attacker, defender=def_base,
                                       rng_mode=RNGMode.EXPECTED)).score
    s_debuff = run_battle(BattleConfig(attacker=attacker, defender=def_debuff,
                                         rng_mode=RNGMode.EXPECTED)).score
    assert s_debuff < s_base, (
        f"Defender's enemy_atk_down should reduce attacker's score. "
        f"base={s_base:.4f}, debuff={s_debuff:.4f}"
    )


def test_grizzly_reduces_opponent_score():
    attacker = _build_fighter("att")
    def_base = _build_fighter("def_base")
    def_grizzly = _build_fighter("def_grizzly", buffs=Buffs(grizzly_level=8))

    s_base = run_battle(BattleConfig(attacker=attacker, defender=def_base,
                                       rng_mode=RNGMode.EXPECTED)).score
    s_griz = run_battle(BattleConfig(attacker=attacker, defender=def_grizzly,
                                       rng_mode=RNGMode.EXPECTED)).score
    assert s_griz < s_base, (
        f"Defender's Grizzly (enemy Let down) should reduce attacker score. "
        f"base={s_base:.4f}, grizzly={s_griz:.4f}"
    )


def test_enemy_def_down_helps_attacker_not_defender():
    base_a = _build_fighter("base_a")
    base_d = _build_fighter("base_d")

    att_with_debuff = _build_fighter("att_dbf", buffs=Buffs(city_enemy_def_down=20))
    s_baseline = run_battle(BattleConfig(attacker=base_a, defender=base_d,
                                           rng_mode=RNGMode.EXPECTED)).score
    s_att_dbf = run_battle(BattleConfig(attacker=att_with_debuff, defender=base_d,
                                          rng_mode=RNGMode.EXPECTED)).score
    assert s_att_dbf > s_baseline, (
        f"Attacker's enemy_def_down should help attacker. "
        f"baseline={s_baseline:.4f}, with_debuff={s_att_dbf:.4f}"
    )

    def_with_debuff = _build_fighter("def_dbf", buffs=Buffs(city_enemy_def_down=20))
    s_def_dbf = run_battle(BattleConfig(attacker=base_a, defender=def_with_debuff,
                                          rng_mode=RNGMode.EXPECTED)).score
    assert s_def_dbf < s_baseline, (
        f"Defender's enemy_def_down should hurt attacker (their Def "
        f"reduced when defender attacks them). "
        f"baseline={s_baseline:.4f}, def_with_debuff={s_def_dbf:.4f}"
    )


def test_buffs_have_same_effect_in_both_rng_modes():
    attacker = _build_fighter(
        "buff_pile",
        buffs=Buffs(city_atk=20, city_def=10, city_hp=20,
                     rhino_level=10, lion_level=10, elephant_level=10),
    )
    defender = _build_fighter("def")
    cfg_e = BattleConfig(attacker=attacker, defender=defender,
                          rng_mode=RNGMode.EXPECTED)
    cfg_s = BattleConfig(attacker=attacker, defender=defender,
                          rng_mode=RNGMode.STOCHASTIC)
    s_e = run_battle(cfg_e).score
    mc = run_monte_carlo(cfg_s, n_trials=200, seed=0, keep_scores=False)
    assert mc.score_ic95_low <= s_e <= mc.score_ic95_high, (
        f"EXPECTED={s_e:.4f} outside STOCHASTIC IC95 "
        f"[{mc.score_ic95_low:.4f}, {mc.score_ic95_high:.4f}]. "
        f"Buffs should be RNG-mode-invariant — drift here means a buff "
        f"is leaking into the RNG path."
    )


def test_enemy_debuff_actually_reduces_not_increases():
    b = Buffs(city_enemy_atk_down=20)
    m = b.enemy_atk_down_multiplier()
    assert m == pytest.approx(0.80)
    assert m != pytest.approx(1.20), (
        "Sign-flip regression! enemy_atk_down=20 should give 0.80 "
        "multiplier (reduces opponent), not 1.20 (would BUFF them)."
    )


def test_each_debuff_fires_on_either_side_no_side_scoping():
    base_a = _build_fighter("base_a")
    base_d = _build_fighter("base_d")
    baseline = run_battle(
        BattleConfig(attacker=base_a, defender=base_d, rng_mode=RNGMode.EXPECTED)
    ).score

    debuffs = [
        ("city_enemy_atk_down", 20),
        ("city_enemy_def_down", 20),
        ("grizzly_level",        8),
    ]

    for field, value in debuffs:
        kwargs = {field: value}
        att_with = _build_fighter(f"att_{field}", buffs=Buffs(**kwargs))
        s_att = run_battle(BattleConfig(attacker=att_with, defender=base_d,
                                           rng_mode=RNGMode.EXPECTED)).score
        def_with = _build_fighter(f"def_{field}", buffs=Buffs(**kwargs))
        s_def = run_battle(BattleConfig(attacker=base_a, defender=def_with,
                                           rng_mode=RNGMode.EXPECTED)).score

        assert s_att != pytest.approx(baseline), (
            f"{field} on attacker did NOT change the score — wiring missing "
            f"for the rally-side direction."
        )
        assert s_def != pytest.approx(baseline), (
            f"{field} on defender did NOT change the score — wiring missing "
            f"for the defender-side direction."
        )
        assert s_att > baseline, (
            f"{field}={value} on attacker should INCREASE attacker score, "
            f"got {s_att:.4f} vs baseline {baseline:.4f}"
        )
        assert s_def < baseline, (
            f"{field}={value} on defender should DECREASE attacker score, "
            f"got {s_def:.4f} vs baseline {baseline:.4f}"
        )


from kingshot_sim.config.buffs import (
    APPOINT_FIELD_COMMANDER_LET_PCT,
    APPOINT_MARSHAL_ATK_PCT,
    APPOINT_KING_PCT,
)


def test_default_appointments_inactive():
    b = Buffs()
    assert b.appoint_field_commander is False
    assert b.appoint_marshal is False
    assert b.appoint_king is False
    assert b.is_empty()


def test_field_commander_lethality_only():
    b = Buffs(appoint_field_commander=True)
    assert APPOINT_FIELD_COMMANDER_LET_PCT == 15.0
    assert b.appoint_additive_pct("let") == pytest.approx(15.0)
    assert b.appoint_additive_pct("atk") == 0.0
    assert b.appoint_additive_pct("def") == 0.0
    assert b.appoint_additive_pct("hp") == 0.0
    assert b.own_let_multiplier() == 1.0
    assert not b.is_empty()


def test_marshal_attack_only():
    b = Buffs(appoint_marshal=True)
    assert b.appoint_additive_pct("atk") == pytest.approx(APPOINT_MARSHAL_ATK_PCT)
    assert b.appoint_additive_pct("def") == 0.0
    assert b.appoint_additive_pct("let") == 0.0
    assert b.appoint_additive_pct("hp") == 0.0
    assert b.own_atk_multiplier() == 1.0
    assert not b.is_empty()


def test_king_all_four_stats():
    b = Buffs(appoint_king=True)
    for stat in ("atk", "def", "let", "hp"):
        assert b.appoint_additive_pct(stat) == pytest.approx(APPOINT_KING_PCT)
    assert not b.is_empty()


def test_king_stacks_additively_with_field_commander():
    b = Buffs(appoint_king=True, appoint_field_commander=True)
    assert b.appoint_additive_pct("let") == pytest.approx(
        APPOINT_KING_PCT + APPOINT_FIELD_COMMANDER_LET_PCT
    )
    assert b.appoint_additive_pct("atk") == pytest.approx(APPOINT_KING_PCT)


def test_appointments_are_additive_not_multiplicative_d107():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.engine.compile import compile_fighter
    from kingshot_sim.domain.enums import SquadType

    def make(buffs: Buffs) -> Fighter:
        return Fighter(
            label="x",
            leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=0),
            leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
            leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
            joiners=(),
            bonuses=BonusVector(
                inf_let_pct=300.0, cav_let_pct=150.0, arc_let_pct=450.0,
            ),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10.5", count=10_000),),
                cavalry=(TroopGroup(tier="T10.5", count=10_000),),
                archer=(TroopGroup(tier="T10.5", count=10_000),),
            ),
            buffs=buffs,
        )

    off = compile_fighter(make(Buffs()), side="rally")
    on = compile_fighter(make(Buffs(appoint_field_commander=True)), side="rally")
    for sq in (SquadType.INFANTRY, SquadType.CAVALRY, SquadType.ARCHER):
        delta = on.squad(sq).let_factor - off.squad(sq).let_factor
        assert delta == pytest.approx(0.15, abs=1e-9), f"{sq}: {delta}"
    assert on.squad(SquadType.INFANTRY).atk_factor == pytest.approx(
        off.squad(SquadType.INFANTRY).atk_factor
    )


def test_appointments_affect_battle_outcome():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.engine.battle import BattleConfig, run_battle
    from kingshot_sim.domain.enums import RNGMode

    def make_fighter(label: str, buffs: Buffs, per_squad: int = 50_000) -> Fighter:
        return Fighter(
            label=label,
            leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=0),
            leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=0),
            leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
            joiners=(),
            bonuses=BonusVector(),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10.5", count=per_squad),),
                cavalry=(TroopGroup(tier="T10.5", count=per_squad),),
                archer=(TroopGroup(tier="T10.5", count=per_squad),),
            ),
            buffs=buffs,
        )

    att_baseline = make_fighter("attacker", Buffs(), per_squad=30_000)
    att_with_king = make_fighter("attacker", Buffs(appoint_king=True), per_squad=30_000)
    defender = make_fighter("defender", Buffs(), per_squad=300_000)

    cfg_baseline = BattleConfig(
        attacker=att_baseline, defender=defender, rng_mode=RNGMode.EXPECTED
    )
    cfg_king = BattleConfig(
        attacker=att_with_king, defender=defender, rng_mode=RNGMode.EXPECTED
    )
    r_base = run_battle(cfg_baseline)
    r_king = run_battle(cfg_king)
    assert r_king.defender_lost() > r_base.defender_lost(), (
        f"King appointment should increase defender losses; "
        f"baseline={r_base.defender_lost()}, king={r_king.defender_lost()}"
    )


def test_section_d_factor_pure_own_buff():
    from kingshot_sim.engine.section_d import section_d_factor
    no_buffs = Buffs()
    assert section_d_factor(Buffs(city_atk=20), no_buffs, "atk") == pytest.approx(1.20)


def test_section_d_factor_user_cancellation_example():
    from kingshot_sim.engine.section_d import section_d_factor
    own = Buffs(city_atk=20)
    enemy = Buffs(city_enemy_atk_down=20)
    f = section_d_factor(own, enemy, "atk")
    assert f == pytest.approx(1.00), (
        f"Model B cancellation: own +20 vs enemy -20 must net to 1.00 in "
        f"the CITY layer (got {f})"
    )


def test_section_d_factor_partial_cancellation():
    from kingshot_sim.engine.section_d import section_d_factor
    own = Buffs(city_atk=20, rhino_level=5)
    enemy = Buffs(city_enemy_atk_down=10)
    f = section_d_factor(own, enemy, "atk")
    assert f == pytest.approx(1.10 * 1.05, abs=1e-9)


def test_section_d_factor_cross_layer_multiplicative():
    from kingshot_sim.engine.section_d import section_d_factor
    base = Buffs(city_atk=20, rhino_level=5)
    f_base = section_d_factor(base, Buffs(), "atk")
    assert f_base == pytest.approx(1.20 * 1.05, abs=1e-9)
    with_appoint = Buffs(city_atk=20, rhino_level=5,
                         appoint_marshal=True, appoint_king=True)
    assert section_d_factor(with_appoint, Buffs(), "atk") == pytest.approx(
        f_base, abs=1e-9
    )


def test_section_d_factor_grizzly_panther_cancel_in_pet_layer():
    from kingshot_sim.engine.section_d import section_d_factor
    own = Buffs(panther_level=10)
    enemy = Buffs(grizzly_level=8)
    f = section_d_factor(own, enemy, "let")
    assert f == pytest.approx(1.05, abs=1e-6)


def test_section_d_factor_moose_elephant_cancel_in_pet_layer():
    from kingshot_sim.engine.section_d import section_d_factor
    own = Buffs(elephant_level=10)
    enemy = Buffs(moose_level=7)
    f = section_d_factor(own, enemy, "hp")
    assert f == pytest.approx(1.05, abs=1e-6)


def test_section_d_factor_turrets_let():
    from kingshot_sim.engine.section_d import section_d_factor
    f = section_d_factor(Buffs(turrets=4), Buffs(), "let")
    assert f == pytest.approx(1.20, abs=1e-9)


def test_section_d_factor_no_enemy_hp_at_city_layer():
    from kingshot_sim.engine.section_d import section_d_factor
    own = Buffs(city_hp=20)
    enemy = Buffs(city_enemy_atk_down=20)
    f = section_d_factor(own, enemy, "hp")
    assert f == pytest.approx(1.20, abs=1e-9)
