import pytest

from kingshot_sim.config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup,
    LeaderHero, JoinerHero,
)
from kingshot_sim.engine.battle import BattleConfig, run_battle
from kingshot_sim.domain.enums import SquadType, BattleType, RNGMode


def _make_fighter(label: str, troop_count: int = 100_000) -> Fighter:
    return Fighter(
        label=label,
        leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
        joiners=(
            JoinerHero(hero_name="Chenko", level="MAX"),
            JoinerHero(hero_name="Howard", level="MAX"),
            JoinerHero(hero_name="Quinn", level="MAX"),
            JoinerHero(hero_name="Yeonwoo", level="MAX"),
        ),
        bonuses=BonusVector(
            squad_atk_pct=80.0, squad_def_pct=70.0,
            squad_let_pct=40.0, squad_hp_pct=50.0,
            inf_atk_pct=20.0, inf_def_pct=15.0, inf_let_pct=10.0, inf_hp_pct=12.0,
            cav_atk_pct=20.0, cav_def_pct=15.0, cav_let_pct=10.0, cav_hp_pct=12.0,
            arc_atk_pct=20.0, arc_def_pct=15.0, arc_let_pct=10.0, arc_hp_pct=12.0,
        ),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=troop_count),),
            cavalry=(TroopGroup(tier="T10.5", count=troop_count),),
            archer=(TroopGroup(tier="T10.5", count=troop_count),),
        ),
    )


def test_full_battle_runs_to_completion():
    attacker = _make_fighter("attacker")
    defender = _make_fighter("defender")
    config = BattleConfig(
        attacker=attacker, defender=defender,
        battle_type=BattleType.RALLY_VS_GARRISON,
        rng_mode=RNGMode.EXPECTED,
    )

    result = run_battle(config)

    assert len(result.rounds) > 0, "Battle should have at least 1 round"
    assert len(result.rounds) < 1000, "Symmetric battle shouldn't take 1000+ rounds"

    assert result.attacker_lost() > 0
    assert result.defender_lost() > 0

    assert -1.0 <= result.score <= 1.0


def test_attacker_with_bonuses_wins_against_weaker_defender():
    strong_att = _make_fighter("strong_att")
    weak_def = Fighter(
        label="weak_def",
        leader_inf=LeaderHero(hero_name="Eric", level="0_0", widget_level=0),
        leader_cav=LeaderHero(hero_name="Petra", level="0_0", widget_level=0),
        leader_arc=LeaderHero(hero_name="Jaeger", level="0_0", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    config = BattleConfig(attacker=strong_att, defender=weak_def, rng_mode=RNGMode.EXPECTED)
    result = run_battle(config)

    assert result.winner == "attacker", f"Strong attacker should win, got {result.winner}"
    assert result.score > 0, f"Score should be positive, got {result.score}"


def test_invalid_leader_class_raises():
    with pytest.raises(ValueError, match="leader_inf must be an Inf-class hero"):
        Fighter(
            label="bad",
            leader_inf=LeaderHero(hero_name="Petra", level="MAX"),
            leader_cav=LeaderHero(hero_name="Jabel", level="MAX"),
            leader_arc=LeaderHero(hero_name="Saul", level="MAX"),
            joiners=(),
            bonuses=BonusVector(),
            troops=TroopRoster(),
        )


def test_epic_can_be_leader():
    lh = LeaderHero(hero_name="Howard", level="MAX")
    assert lh.to_hero().is_epic
    with pytest.raises(ValueError, match="Unknown leader hero"):
        LeaderHero(hero_name="NotAHero", level="MAX")


def test_helga_passive_is_account_wide_additive_d108():
    def _make(label: str, owns_helga: bool) -> Fighter:
        atk = 110 if owns_helga else 100
        dff = 110 if owns_helga else 100
        return Fighter(
            label=label,
            leader_inf=LeaderHero(hero_name="Eric", level="MAX", widget_level=10),
            leader_cav=LeaderHero(hero_name="Petra", level="MAX", widget_level=10),
            leader_arc=LeaderHero(hero_name="Jaeger", level="MAX", widget_level=10),
            joiners=(),
            bonuses=BonusVector(squad_atk_pct=atk, squad_def_pct=dff,
                                squad_let_pct=100, squad_hp_pct=100),
            troops=TroopRoster(
                infantry=(TroopGroup(tier="T10.5", count=100_000),),
                cavalry=(TroopGroup(tier="T10.5", count=100_000),),
                archer=(TroopGroup(tier="T10.5", count=100_000),),
            ),
        )

    enemy = _make("enemy", owns_helga=False)
    no_passive = run_battle(BattleConfig(attacker=_make("base", False), defender=enemy))
    with_passive = run_battle(BattleConfig(attacker=_make("helga", True), defender=enemy))

    assert with_passive.score > no_passive.score, (
        "Account-wide additive passive (no Helga in trio) must still improve the "
        f"outcome: base={no_passive.score:.4f}, with_passive={with_passive.score:.4f}"
    )


def test_decisiveness_score_rewards_lopsided_annihilation():
    big = _make_fighter("big", troop_count=100_000)
    small = _make_fighter("small", troop_count=10_000)
    r = run_battle(BattleConfig(attacker=big, defender=small, rng_mode=RNGMode.EXPECTED))
    assert r.winner == "attacker"
    assert -1.0 <= r.score <= 1.0
    assert r.score > 0.5, f"lopsided annihilation should be decisive, got {r.score:+.4f}"


def test_decisiveness_score_symmetric_when_outnumbered():
    small = _make_fighter("small", troop_count=10_000)
    big = _make_fighter("big", troop_count=100_000)
    r = run_battle(BattleConfig(attacker=small, defender=big, rng_mode=RNGMode.EXPECTED))
    assert r.winner == "defender"
    assert r.score < -0.5, f"being annihilated should be a decisive loss, got {r.score:+.4f}"


def test_decisiveness_score_matches_legacy_for_equal_armies():
    att = _make_fighter("att", troop_count=100_000)
    dfn = _make_fighter("dfn", troop_count=100_000)
    r = run_battle(BattleConfig(attacker=att, defender=dfn, rng_mode=RNGMode.EXPECTED))
    att_total = sum(r.attacker_initial.values())
    dfn_total = sum(r.defender_initial.values())
    assert att_total == dfn_total
    legacy = (r.defender_lost() - r.attacker_lost()) / max(att_total, dfn_total, 1)
    assert r.score == pytest.approx(legacy, abs=1e-9)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
