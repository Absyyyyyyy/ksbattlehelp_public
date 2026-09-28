from __future__ import annotations
import pytest

from kingshot_sim.domain.heroes import Hero
from kingshot_sim.domain.enums import OP_TO_FAMILY, Family
from kingshot_sim.data.catalog import get_hero_skills


MIGRATED_SKILLS = [
    ("Amadeus", "sk3", +50.0, 0),
    ("Jabel",   "sk2", +50.0, 0),
    ("Marlin",  "sk1", +50.0, 0),
    ("Vivian",  "sk2", +100.0, 0),
    ("Vivian",  "sk3", +60.0, 0),
    ("Sophia",  "sk2", +200.0, 0),
    ("Yang",    "sk2", +100.0, 0),
]


def _find_slot(skills, slot):
    for s in skills:
        if s.slot == slot:
            return s
    raise LookupError(f"No skill at slot {slot}")


@pytest.mark.parametrize("hero_name,slot,expected_value,effect_idx", MIGRATED_SKILLS)
def test_migrated_skill_has_op_102_at_max(hero_name, slot, expected_value, effect_idx):
    hero = Hero(name=hero_name, level="MAX", widget_level=0)
    skill = _find_slot(get_hero_skills(hero), slot)
    eff = skill.effects[effect_idx]
    assert eff.op == 102, (
        f"{hero_name} {slot} effect[{effect_idx}]: expected op 102 after V8 D-33 "
        f"migration, got op {eff.op}. If this is intentional, update "
        f"MIGRATED_SKILLS (D-33)."
    )
    assert eff.value == pytest.approx(expected_value), (
        f"{hero_name} {slot} effect[{effect_idx}]: value drifted during migration "
        f"(expected {expected_value}, got {eff.value}). D-33 was an op-code-only "
        f"change; the numeric value should not have moved."
    )


_ALL_HEROES = [
    "Amadeus", "Helga", "Jabel", "Saul",
    "Zoe", "Hilde", "Marlin",
    "Eric", "Petra", "Jaeger",
    "Alcar", "Margot", "Rosa",
    "Long Fei", "Thrud", "Vivian",
    "Triton", "Sophia", "Yang",
    "Howard", "Chenko", "Gordon", "Fahd",
    "Quinn", "Yeonwoo", "Amane",
]


def _scan_op(target_op: int) -> list[str]:
    hits = []
    for hero_name in _ALL_HEROES:
        hero = Hero(name=hero_name, level="MAX", widget_level=10)
        for skill in get_hero_skills(hero):
            for i, eff in enumerate(skill.effects):
                if eff.op == target_op:
                    hits.append(f"{hero_name} {skill.slot} effect[{i}]")
    return hits


def test_no_default_skill_emits_retired_op_104():
    offenders = _scan_op(104)
    assert not offenders, (
        f"Found {len(offenders)} default-catalog effect(s) still emitting the "
        f"retired op 104 after D-103: {offenders}. Renumber them to op 103 in "
        f"catalog.py, or document the exception under D-103."
    )


def test_op_103_is_skill_damage_and_only_triton_sk2():
    users = _scan_op(103)
    assert users == ["Triton sk2 effect[0]"], (
        f"Expected op 103 to be used only by Triton sk2 after D-103, got {users}. "
        f"Either a migrated skill leaked onto 103, or Triton sk2's renumber "
        f"regressed."
    )


def test_op_103_registered_and_op_104_retired():
    assert 103 in OP_TO_FAMILY, (
        "op 103 was dropped from OP_TO_FAMILY. D-33/D-103 keep it alive: users "
        "must be able to override migrated skills to op 103. "
        "Restore 103: Family.DAMAGE_UP in domain/enums.py."
    )
    assert OP_TO_FAMILY[103] == Family.DAMAGE_UP, (
        f"op 103 must remain in DamageUp family, got {OP_TO_FAMILY[103]}."
    )
    assert 104 not in OP_TO_FAMILY, (
        "op 104 was retired in D-103 (renumbered to 103) and must be removed "
        "from OP_TO_FAMILY so set_op_override rejects it as unknown."
    )


def test_migration_collapses_amadeus_sk2_and_sk3_into_single_op_102_bucket():
    from kingshot_sim.engine.resolver import aggregate_family

    amadeus = Hero(name="Amadeus", level="MAX", widget_level=0)
    skills = get_hero_skills(amadeus)
    sk2 = _find_slot(skills, "sk2")
    sk3 = _find_slot(skills, "sk3")

    assert sk2.effects[0].op == 102, "Amadeus sk2 must be op 102 (Way of the Blade, unchanged)"
    assert sk3.effects[0].op == 102, "Amadeus sk3 must be op 102 (post-migration)"

    sk3_chance = sk3.trigger.chance
    sk3_expected_value = sk3_chance * sk3.effects[0].value

    from kingshot_sim.domain.skills import Effect
    from kingshot_sim.domain.enums import SquadType

    sk2_eff = Effect(op=102, value=sk2.effects[0].value)
    sk3_post = Effect(op=102, value=sk3_expected_value)
    sk3_pre = Effect(op=103, value=sk3_expected_value)

    post = aggregate_family(
        [sk2_eff, sk3_post], Family.DAMAGE_UP, target_squad=SquadType.INFANTRY,
    )
    pre = aggregate_family(
        [sk2_eff, sk3_pre], Family.DAMAGE_UP, target_squad=SquadType.INFANTRY,
    )

    assert post < pre, (
        f"V8 D-33 expected post-migration DamageUp < pre-migration. "
        f"Got post={post:.4f}, pre={pre:.4f}. Either the migration was "
        f"reverted in catalog.py, or aggregate_family changed semantics."
    )
    assert post == pytest.approx(1.45, abs=1e-9)
    assert pre == pytest.approx(1.25 * 1.20, abs=1e-9)
