from __future__ import annotations
import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero,
)
from kingshot_sim.config.buffs import Buffs
from kingshot_sim.easy_mode.peeling import (
    PeelingContext,
    peel_visible_to_bonus_vector,
    build_visible_from_bonus_vector,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.domain.enums import RNGMode


def _make_advanced_fighter() -> Fighter:
    return Fighter(
        label="advanced",
        leader_inf=LeaderHero(
            hero_name="Eric", level="MAX", widget_level=8,
        ),
        leader_cav=LeaderHero(
            hero_name="Sophia", level="MAX", widget_level=8,
        ),
        leader_arc=LeaderHero(
            hero_name="Yang", level="MAX", widget_level=8,
        ),
        joiners=(
            JoinerHero(hero_name="Chenko", level="MAX"),
            JoinerHero(hero_name="Gordon", level="MAX"),
            JoinerHero(hero_name="Howard", level="MAX"),
            JoinerHero(hero_name="Amane",  level="MAX"),
        ),
        bonuses=BonusVector(
            inf_atk_pct=350.0, inf_def_pct=400.0, inf_let_pct=180.0, inf_hp_pct=210.0,
            cav_atk_pct=340.0, cav_def_pct=390.0, cav_let_pct=170.0, cav_hp_pct=200.0,
            arc_atk_pct=360.0, arc_def_pct=380.0, arc_let_pct=190.0, arc_hp_pct=220.0,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=150_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=200_000),),
        ),
        buffs=Buffs(
            city_atk=20, city_def=10, city_let=20, city_hp=10,
            rhino_level=10, lion_level=8, panther_level=5,
            moose_level=7, elephant_level=10,
            appoint_field_commander=True,
            appoint_marshal=True,
            appoint_king=True,
        ),
    )


def _defender_for_engine() -> Fighter:
    return Fighter(
        label="defender",
        leader_inf=LeaderHero(hero_name="Alcar",  level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Margot", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Rosa",   level="MAX", widget_level=10),
        joiners=(JoinerHero(hero_name="Quinn", level="MAX"),),
        bonuses=BonusVector(
            inf_atk_pct=300.0, inf_def_pct=350.0, inf_let_pct=150.0, inf_hp_pct=180.0,
            cav_atk_pct=310.0, cav_def_pct=360.0, cav_let_pct=160.0, cav_hp_pct=190.0,
            arc_atk_pct=320.0, arc_def_pct=370.0, arc_let_pct=170.0, arc_hp_pct=200.0,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=200_000),),
            cavalry=(TroopGroup(tier="T10.5", count=150_000),),
            archer=(TroopGroup(tier="T10.5", count=250_000),),
        ),
        buffs=Buffs(city_def=10, lion_level=5),
    )


def _to_easy_mode(advanced: Fighter, role: str, was_rally: bool,
                  in_territory: bool) -> Fighter:
    ctx = PeelingContext(
        importee_role=role,
        was_rally=was_rally,
        is_garrisoning_territory=in_territory,
        leader_inf=advanced.leader_inf,
        leader_cav=advanced.leader_cav,
        leader_arc=advanced.leader_arc,
        buffs=advanced.buffs,
    )
    visible = build_visible_from_bonus_vector(advanced.bonuses, ctx)
    peeled_bv = peel_visible_to_bonus_vector(visible, ctx)
    return Fighter(
        label=advanced.label + "_easy",
        leader_inf=advanced.leader_inf,
        leader_cav=advanced.leader_cav,
        leader_arc=advanced.leader_arc,
        joiners=advanced.joiners,
        bonuses=peeled_bv,
        troops=advanced.troops,
        buffs=advanced.buffs,
    )


def _assert_bv_equal(a: BonusVector, b: BonusVector, tol: float = 1e-6) -> None:
    for c in ("inf", "cav", "arc"):
        for stat in ("atk", "def", "let", "hp"):
            f = f"{c}_{stat}_pct"
            assert getattr(a, f) == pytest.approx(getattr(b, f), abs=tol), (
                f"{f}: a={getattr(a, f)}, b={getattr(b, f)}"
            )


@pytest.mark.parametrize(
    "role,was_rally,in_territory",
    [
        ("attacking", True,  False),
        ("attacking", False, False),
        ("defending", False, True),
        ("defending", False, False),
    ],
)
def test_roundtrip_bv_matches_within_1pp(role, was_rally, in_territory):
    adv = _make_advanced_fighter()
    easy = _to_easy_mode(adv, role=role, was_rally=was_rally,
                            in_territory=in_territory)
    _assert_bv_equal(adv.bonuses, easy.bonuses, tol=1.0)
    _assert_bv_equal(adv.bonuses, easy.bonuses, tol=1e-6)


@pytest.mark.parametrize(
    "role,was_rally,in_territory",
    [
        ("attacking", True,  False),
        ("defending", False, True),
    ],
)
def test_roundtrip_engine_produces_identical_battle_result(
    role, was_rally, in_territory
):
    adv = _make_advanced_fighter()
    easy = _to_easy_mode(adv, role=role, was_rally=was_rally,
                            in_territory=in_territory)
    defender = _defender_for_engine()

    is_solo = (role == "attacking" and not was_rally)

    if role == "attacking":
        cfg_adv  = BattleConfig(attacker=adv,  defender=defender,
                                  rng_mode=RNGMode.EXPECTED,
                                  is_solo_attack=is_solo)
        cfg_easy = BattleConfig(attacker=easy, defender=defender,
                                  rng_mode=RNGMode.EXPECTED,
                                  is_solo_attack=is_solo)
    else:
        cfg_adv  = BattleConfig(attacker=defender, defender=adv,
                                  rng_mode=RNGMode.EXPECTED)
        cfg_easy = BattleConfig(attacker=defender, defender=easy,
                                  rng_mode=RNGMode.EXPECTED)

    r_adv  = run_battle(cfg_adv)
    r_easy = run_battle(cfg_easy)

    assert r_easy.score == pytest.approx(r_adv.score, abs=1e-9), (
        f"Score drift: adv={r_adv.score}, easy={r_easy.score}"
    )
    for st in r_adv.attacker_final:
        assert r_easy.attacker_final[st] == r_adv.attacker_final[st], (
            f"Attacker {st} drift: adv={r_adv.attacker_final[st]}, "
            f"easy={r_easy.attacker_final[st]}"
        )
    for st in r_adv.defender_final:
        assert r_easy.defender_final[st] == r_adv.defender_final[st], (
            f"Defender {st} drift: adv={r_adv.defender_final[st]}, "
            f"easy={r_easy.defender_final[st]}"
        )
    assert r_easy.winner == r_adv.winner


def test_roundtrip_preserves_joiners_and_troops():
    adv = _make_advanced_fighter()
    easy = _to_easy_mode(adv, role="attacking", was_rally=True,
                            in_territory=False)
    assert easy.joiners == adv.joiners
    assert easy.troops == adv.troops


def test_roundtrip_preserves_buffs_including_appointments():
    adv = _make_advanced_fighter()
    easy = _to_easy_mode(adv, role="attacking", was_rally=True,
                            in_territory=False)
    assert easy.buffs == adv.buffs


def test_roundtrip_with_no_buffs_and_no_widgets():
    minimal = Fighter(
        label="minimal",
        leader_inf=LeaderHero(hero_name="Eric",   level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra",  level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(
            inf_atk_pct=100.0, inf_def_pct=100.0,
            cav_atk_pct=100.0, cav_def_pct=100.0,
            arc_atk_pct=100.0, arc_def_pct=100.0,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=50_000),),
            cavalry=(TroopGroup(tier="T10.5", count=50_000),),
            archer=(TroopGroup(tier="T10.5", count=50_000),),
        ),
        buffs=Buffs(),
    )
    easy = _to_easy_mode(minimal, role="attacking", was_rally=True,
                            in_territory=False)
    _assert_bv_equal(minimal.bonuses, easy.bonuses, tol=1e-6)
