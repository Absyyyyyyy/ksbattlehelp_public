import pytest

from kingshot_sim.domain.heroes import Hero
from kingshot_sim.data.catalog import get_hero_skills
from kingshot_sim.data.reference import star_from_level, max_skill_level


def _hero(name, level, widget_level=0):
    star = star_from_level(level)
    skill_levels = tuple(
        min(star, max_skill_level(level, slot))
        for slot in ("sk1", "sk2", "sk3")
    )
    return Hero(
        name=name,
        level=level,
        widget_level=widget_level,
        skill_levels=skill_levels,
    )


def _find(skills, slot):
    for s in skills:
        if s.slot == slot:
            return s
    raise LookupError(f"No skill at slot {slot}")


@pytest.mark.parametrize("hero_name,slot,p_max,fixed_value", [
    ("Helga",     "sk1", 0.40, +50.0),
    ("Jabel",     "sk1", 0.40, +50.0),
    ("Marlin",    "sk1", 0.40, +50.0),
    ("Hilde",     "sk3", 0.40, +50.0),
    ("Sophia",    "sk1", 0.40, +50.0),
    ("Amadeus",   "sk3", 0.40, +50.0),
])
def test_chance_scaling_skill_value_fixed(hero_name, slot, p_max, fixed_value):
    s_low = _find(get_hero_skills(_hero(hero_name, "1_5")), slot)
    s_max = _find(get_hero_skills(_hero(hero_name, "MAX")), slot)
    assert s_low.effects[0].value == pytest.approx(fixed_value), \
        f"{hero_name} {slot}: value at ⭐1 = {s_low.effects[0].value}, expected fixed {fixed_value}"
    assert s_max.effects[0].value == pytest.approx(fixed_value), \
        f"{hero_name} {slot}: value at ⭐5 = {s_max.effects[0].value}, expected fixed {fixed_value}"


@pytest.mark.parametrize("hero_name,slot,p_max", [
    ("Helga",     "sk1", 0.40),
    ("Jabel",     "sk1", 0.40),
    ("Marlin",    "sk1", 0.40),
    ("Hilde",     "sk3", 0.40),
    ("Sophia",    "sk1", 0.40),
    ("Amadeus",   "sk3", 0.40),
])
def test_chance_scaling_skill_chance_progresses(hero_name, slot, p_max):
    s_3 = _find(get_hero_skills(_hero(hero_name, "3_5")), slot)
    s_5 = _find(get_hero_skills(_hero(hero_name, "MAX")), slot)
    assert s_5.trigger.chance == pytest.approx(p_max), \
        f"{hero_name} {slot}: ⭐5 chance = {s_5.trigger.chance}, expected {p_max}"
    assert s_3.trigger.chance == pytest.approx(0.6 * p_max), \
        f"{hero_name} {slot}: ⭐3 chance = {s_3.trigger.chance}, expected {0.6 * p_max}"


@pytest.mark.parametrize("hero_name,slot,fixed_chance,v_max", [
    ("Jabel",     "sk2", 0.50, +50.0),
    ("Marlin",    "sk2", 0.20, +50.0),
    ("Marlin",    "sk3", 0.50, +50.0),
    ("Petra",     "sk1", 0.50, +50.0),
    ("Petra",     "sk2", 0.50, +50.0),
    ("Petra",     "sk3", 0.40, +50.0),
    ("Hilde",     "sk2", 0.25, +200.0),
    ("Zoe",       "sk1", 0.20, +40.0),
    ("Zoe",       "sk3", 0.50, +50.0),
    ("Jaeger",    "sk1", 0.20, +40.0),
    ("Jaeger",    "sk2", 0.20, +50.0),
    ("Margot",    "sk3", 0.25, +200.0),
    ("Rosa",      "sk1", 0.40, +50.0),
    ("Long Fei",  "sk1", 0.40, +50.0),
    ("Long Fei",  "sk3", 0.25, +200.0),
    ("Thrud",     "sk2", 0.20, +100.0),
    ("Yang",      "sk2", 0.40, +100.0),
])
def test_value_scaling_skill_chance_fixed(hero_name, slot, fixed_chance, v_max):
    s_low = _find(get_hero_skills(_hero(hero_name, "1_5")), slot)
    s_max = _find(get_hero_skills(_hero(hero_name, "MAX")), slot)
    assert s_low.trigger.chance == pytest.approx(fixed_chance), \
        f"{hero_name} {slot}: ⭐1 chance = {s_low.trigger.chance}, expected fixed {fixed_chance}"
    assert s_max.trigger.chance == pytest.approx(fixed_chance), \
        f"{hero_name} {slot}: ⭐5 chance = {s_max.trigger.chance}, expected fixed {fixed_chance}"


@pytest.mark.parametrize("hero_name,slot,v_max", [
    ("Jabel",     "sk2", +50.0),
    ("Marlin",    "sk2", +50.0),
    ("Marlin",    "sk3", +50.0),
    ("Petra",     "sk1", +50.0),
    ("Petra",     "sk2", +50.0),
    ("Petra",     "sk3", +50.0),
    ("Hilde",     "sk2", +200.0),
    ("Zoe",       "sk1", +40.0),
    ("Zoe",       "sk3", +50.0),
    ("Jaeger",    "sk1", +40.0),
    ("Jaeger",    "sk2", +50.0),
    ("Rosa",      "sk1", +50.0),
    ("Long Fei",  "sk1", +50.0),
    ("Yang",      "sk2", +100.0),
])
def test_value_scaling_skill_value_progresses(hero_name, slot, v_max):
    s_3 = _find(get_hero_skills(_hero(hero_name, "3_5")), slot)
    s_5 = _find(get_hero_skills(_hero(hero_name, "MAX")), slot)
    assert s_5.effects[0].value == pytest.approx(v_max), \
        f"{hero_name} {slot}: ⭐5 value = {s_5.effects[0].value}, expected {v_max}"
    assert s_3.effects[0].value == pytest.approx(0.6 * v_max), \
        f"{hero_name} {slot}: ⭐3 value = {s_3.effects[0].value}, expected {0.6 * v_max}"


def test_helga_sk1_expected_contribution_at_different_stars():
    helga_max = _hero("Helga", "MAX")
    helga_3 = _hero("Helga", "3_5")

    s_max = _find(get_hero_skills(helga_max), "sk1")
    s_3 = _find(get_hero_skills(helga_3), "sk1")

    contrib_max = s_max.trigger.chance * s_max.effects[0].value
    contrib_3 = s_3.trigger.chance * s_3.effects[0].value

    assert contrib_max == pytest.approx(0.40 * 50.0)
    assert contrib_3 == pytest.approx(0.24 * 50.0)
    assert s_max.effects[0].value == s_3.effects[0].value == 50.0


def test_petra_sk1_evil_eye_union_expected_contribution_d118():
    from kingshot_sim.engine.resolver import _expected_value_effect
    sk1 = _find(get_hero_skills(_hero("Petra", "MAX")), "sk1")
    assert sk1.trigger.chance == pytest.approx(0.50)
    assert sk1.effects[0].op == 211
    assert sk1.effects[0].value == pytest.approx(50.0)
    exp = _expected_value_effect(sk1)
    assert exp[0].value == pytest.approx(0.875 * 50.0)


def test_own_buff_per_attack_keeps_single_roll_d118():
    from kingshot_sim.engine.resolver import _expected_value_effect
    sk3 = _find(get_hero_skills(_hero("Long Fei", "MAX")), "sk3")
    exp = _expected_value_effect(sk3)
    assert exp[0].value == pytest.approx(0.25 * 200.0)
