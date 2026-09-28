from __future__ import annotations

from kingshot_sim.data.catalog import get_hero_skills
from kingshot_sim.data.reference import (
    HERO_CLASS, HERO_GENERATION, HERO_LEADER_MAX, HERO_WIDGET,
    MAX_GENERATION, MYTHIC_HEROES, WIDGET_MAX,
)
from kingshot_sim.domain.enums import (
    SquadType, TriggerKind, SkillSpecial, OP_TO_FAMILY, Family,
)
from kingshot_sim.domain.heroes import Hero


INF = SquadType.INFANTRY
CAV = SquadType.CAVALRY
ARC = SquadType.ARCHER

GEN7_HEROES = ("Charles", "Ava", "Wee & Woo")


class TestGen7Registration:
    def test_max_generation_is_7(self):
        assert MAX_GENERATION == 7

    def test_all_three_are_mythic(self):
        for name in GEN7_HEROES:
            assert name in MYTHIC_HEROES, f"{name!r} not in MYTHIC_HEROES"

    def test_classes(self):
        assert HERO_CLASS["Charles"]   == "Inf"
        assert HERO_CLASS["Ava"]       == "Cav"
        assert HERO_CLASS["Wee & Woo"] == "Arc"

    def test_generation_is_7(self):
        for name in GEN7_HEROES:
            assert HERO_GENERATION[name] == 7

    def test_leader_max(self):
        for name in GEN7_HEROES:
            assert HERO_LEADER_MAX[name] == 650.52

    def test_widgets_and_max(self):
        assert HERO_WIDGET["Charles"]   == "Justice Fist"
        assert HERO_WIDGET["Ava"]       == "Chameleos"
        assert HERO_WIDGET["Wee & Woo"] == "Mortar"
        for w in ("Justice Fist", "Chameleos", "Mortar"):
            assert WIDGET_MAX[w] == 160.50


class TestWeeAndWoo:
    @staticmethod
    def _skills(star: int = 5, widget: int = 10):
        h = Hero(name="Wee & Woo", level="MAX" if star == 5 else f"{star}_5",
                 widget_level=widget)
        return get_hero_skills(h)

    def test_sk1_is_passive_two_effects_atk15_let10(self):
        ss = self._skills()
        sk1 = next(s for s in ss if s.slot == "sk1")
        assert sk1.name == "Artillerymen"
        assert sk1.trigger.kind == TriggerKind.PASSIVE
        ops = sorted((e.op, e.value) for e in sk1.effects)
        assert ops == [(101, 10.0), (102, 15.0)]

    def test_sk2_target_enemy_squads_filter(self):
        ss = self._skills()
        sk2 = next(s for s in ss if s.slot == "sk2")
        assert sk2.name == "Chain Shelling"
        assert sk2.trigger.kind == TriggerKind.PASSIVE
        effs = list(sk2.effects)
        assert len(effs) == 2
        assert all(e.op == 102 for e in effs)
        by_target = {tuple(sorted(e.target_enemy_squads, key=str)): e.value
                     for e in effs}
        assert by_target == {
            (INF,): 25.0,
            (ARC,): 30.0,
        }

    def test_sk3_is_pity_with_scaling_chance(self):
        ss = self._skills()
        sk3 = next(s for s in ss if s.slot == "sk3")
        assert sk3.name == "Boom Boom"
        assert sk3.trigger.kind == TriggerKind.PITY
        assert sk3.special == SkillSpecial.PITY_PROC
        assert sk3.trigger.chance == 0.50
        assert sk3.effects[0].op == 102
        assert sk3.effects[0].value == 50.0

    def test_sk3_chance_scales_with_skill_level(self):
        for star_level, expected_chance in [
            ("2_5", 0.30),
            ("3_5", 0.40),
            ("4_5", 0.50),
            ("MAX", 0.50),
        ]:
            h = Hero(name="Wee & Woo", level=star_level, widget_level=10)
            ss = get_hero_skills(h)
            sk3 = next((s for s in ss if s.slot == "sk3"), None)
            assert sk3 is not None, f"sk3 missing at {star_level}"
            assert abs(sk3.trigger.chance - expected_chance) < 1e-6, (
                f"{star_level}: chance={sk3.trigger.chance}, expected {expected_chance}"
            )

    def test_widget_is_defender_scoped(self):
        ss = self._skills(widget=10)
        w = next((s for s in ss if s.slot == "widget"), None)
        assert w is not None, "Wee & Woo Mortar widget skill missing at widget_level=10"
        assert w.side_scope == "defender"
        assert w.effects[0].op == 102
        assert w.effects[0].value == 15.0


class TestAva:
    @staticmethod
    def _skills(star: int = 5, widget: int = 10):
        h = Hero(name="Ava", level="MAX" if star == 5 else f"{star}_5",
                 widget_level=widget)
        return get_hero_skills(h)

    def test_sk1_uses_op_212_new(self):
        ss = self._skills()
        sk1 = next(s for s in ss if s.slot == "sk1")
        assert sk1.name == "Dissolution"
        assert sk1.trigger.kind == TriggerKind.PASSIVE
        assert sk1.effects[0].op == 212
        assert sk1.effects[0].value == 25.0
        assert OP_TO_FAMILY[212] == Family.OPP_DEFENSE_DOWN

    def test_sk2_is_periodic_4_2(self):
        ss = self._skills()
        sk2 = next(s for s in ss if s.slot == "sk2")
        assert sk2.name == "Chiaroscuro"
        assert sk2.trigger.kind == TriggerKind.PERIODIC
        assert sk2.trigger.period == 4
        assert sk2.trigger.duration == 2
        assert sk2.effects[0].op == 211
        assert sk2.effects[0].value == 50.0

    def test_sk3_passive_op_101(self):
        ss = self._skills()
        sk3 = next(s for s in ss if s.slot == "sk3")
        assert sk3.name == "Light and Cold"
        assert sk3.trigger.kind == TriggerKind.PASSIVE
        assert sk3.effects[0].op == 101
        assert sk3.effects[0].value == 25.0

    def test_widget_is_rally_scoped(self):
        ss = self._skills(widget=10)
        w = next((s for s in ss if s.slot == "widget"), None)
        assert w is not None
        assert w.side_scope == "rally"
        assert w.effects[0].op == 101
        assert w.effects[0].value == 15.0


class TestCharles:
    @staticmethod
    def _skills(star: int = 5, widget: int = 10):
        h = Hero(name="Charles", level="MAX" if star == 5 else f"{star}_5",
                 widget_level=widget)
        return get_hero_skills(h)

    def test_sk1_uses_op_203_like_marlin_jaeger(self):
        ss = self._skills()
        sk1 = next(s for s in ss if s.slot == "sk1")
        assert sk1.name == "Intimidation"
        assert sk1.trigger.kind == TriggerKind.PASSIVE
        assert sk1.effects[0].op == 203
        assert sk1.effects[0].value == 20.0
        assert OP_TO_FAMILY[203] == Family.OPP_DAMAGE_DOWN

    def test_sk2_op_111_damage_taken_down(self):
        ss = self._skills()
        sk2 = next(s for s in ss if s.slot == "sk2")
        assert sk2.name == "Iron Bodies"
        assert sk2.effects[0].op == 111
        assert sk2.effects[0].value == 20.0

    def test_sk3_op_113_hp_up(self):
        ss = self._skills()
        sk3 = next(s for s in ss if s.slot == "sk3")
        assert sk3.name == "Great Justice"
        assert sk3.effects[0].op == 113
        assert sk3.effects[0].value == 25.0

    def test_widget_is_defender_scoped_op_113_hp(self):
        ss = self._skills(widget=10)
        w = next((s for s in ss if s.slot == "widget"), None)
        assert w is not None
        assert w.side_scope == "defender"
        assert w.effects[0].op == 113
        assert w.effects[0].value == 15.0


def test_wee_and_woo_sk2_changes_skill_mod_per_target_class():
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    from kingshot_sim.engine.compile import compile_fighter
    from kingshot_sim.engine.resolver import collect_active_effects, aggregate_family
    from kingshot_sim.domain.enums import Family, RNGMode

    attacker = Fighter(
        label="Wee&Woo test",
        leader_inf=LeaderHero(hero_name="Amadeus",   level="MAX", widget_level=0),
        leader_cav=LeaderHero(hero_name="Hilde",     level="MAX", widget_level=0),
        leader_arc=LeaderHero(hero_name="Wee & Woo", level="MAX", widget_level=0),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )
    fs = compile_fighter(attacker, side="rally")
    effects = collect_active_effects(fs, round_idx=0, rng_mode=RNGMode.EXPECTED)

    f_vs_inf = aggregate_family(effects, Family.DAMAGE_UP, ARC, enemy_squad=INF)
    f_vs_cav = aggregate_family(effects, Family.DAMAGE_UP, ARC, enemy_squad=CAV)
    f_vs_arc = aggregate_family(effects, Family.DAMAGE_UP, ARC, enemy_squad=ARC)

    assert f_vs_arc > f_vs_inf > f_vs_cav, (
        f"Expected ARC > INF > CAV target ordering, got "
        f"arc={f_vs_arc:.4f}, inf={f_vs_inf:.4f}, cav={f_vs_cav:.4f}"
    )
