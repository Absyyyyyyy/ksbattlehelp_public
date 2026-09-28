from __future__ import annotations
import pytest

from kingshot_sim.data.catalog import get_hero_skills
from kingshot_sim.data.reference import HERO_CLASS, HERO_LEADER_MAX
from kingshot_sim.domain.heroes import Hero
from kingshot_sim.domain.enums import (
    Family, SkillSpecial, TriggerKind, family_for_op,
)


MYTHICS: list[str] = [h for h, m in HERO_LEADER_MAX.items() if m >= 200]

EPICS: list[str] = [h for h, m in HERO_LEADER_MAX.items() if m < 200]

NON_COMBAT_SK1: frozenset[str] = frozenset({"Diana"})

NON_COMBAT_SK2: frozenset[str] = frozenset({"Saul", "Fahd", "Diana", "Yeonwoo", "Amane"})


@pytest.mark.parametrize("hero", MYTHICS)
def test_mythic_has_4_slots(hero):
    skills = get_hero_skills(Hero(name=hero, level="MAX", widget_level=10))
    slots = {sk.slot for sk in skills}
    assert "sk1" in slots, f"{hero} missing sk1"
    assert "sk2" in slots, f"{hero} missing sk2"
    assert "sk3" in slots, f"{hero} missing sk3"
    assert "widget" in slots, f"{hero} missing widget"


@pytest.mark.parametrize("hero", EPICS)
def test_epic_has_sk1_only(hero):
    if hero == "Diana":
        return
    skills = get_hero_skills(Hero(name=hero, level="MAX", widget_level=0))
    slots = {sk.slot for sk in skills}
    assert "sk1" in slots, f"{hero} missing sk1 in combat catalog"
    assert "sk3" not in slots, f"{hero} unexpectedly has sk3 (epics have no sk3)"
    assert "widget" not in slots, f"{hero} unexpectedly has widget (epics have no widget)"


def _get_skill(hero: str, slot: str, widget_level: int = 10):
    skills = get_hero_skills(Hero(name=hero, level="MAX", widget_level=widget_level))
    matches = [sk for sk in skills if sk.slot == slot]
    return matches[0] if matches else None


@pytest.mark.parametrize("hero,slot", [(h, s) for h in MYTHICS
                                          for s in ("sk1", "sk2", "sk3", "widget")])
def test_mythic_skill_has_valid_op_codes(hero, slot):
    if hero == "Saul" and slot == "sk2":
        return
    sk = _get_skill(hero, slot)
    assert sk is not None, f"{hero} {slot} not found"
    for e in sk.effects:
        if e.op == 0:
            assert sk.special == SkillSpecial.DODGE, (
                f"{hero} {slot} has op=0 effect but special={sk.special.name}; "
                f"op=0 is reserved for DODGE"
            )
            continue
        fam = family_for_op(e.op)
        assert isinstance(fam, Family), (
            f"{hero} {slot} op {e.op} doesn't map to a known Family"
        )


@pytest.mark.parametrize("hero", [h for h in EPICS if h != "Diana"])
def test_epic_sk1_has_effect_or_is_noncombat(hero):
    sk = _get_skill(hero, "sk1", widget_level=0)
    assert sk is not None, f"{hero} sk1 not found"
    assert len(sk.effects) > 0, f"{hero} sk1 has no effects"


@pytest.mark.parametrize("hero,slot", [(h, s) for h in MYTHICS
                                          for s in ("sk1", "sk2", "sk3", "widget")])
def test_mythic_trigger_kind_is_valid(hero, slot):
    if hero == "Saul" and slot == "sk2":
        return
    sk = _get_skill(hero, slot)
    assert sk is not None
    assert sk.trigger.kind in {
        TriggerKind.PASSIVE, TriggerKind.RNG_PER_ROUND,
        TriggerKind.RNG_PER_ATTACK, TriggerKind.PERIODIC,
        TriggerKind.TIMED, TriggerKind.PITY,
    }, f"{hero} {slot} has unknown trigger.kind = {sk.trigger.kind!r}"


@pytest.mark.parametrize("hero", MYTHICS)
def test_widget_side_scope_is_one_sided(hero):
    w = _get_skill(hero, "widget")
    assert w is not None, f"{hero} widget not found"
    assert w.side_scope in ("rally", "defender"), (
        f"{hero} widget side_scope must be 'rally' or 'defender', "
        f"got {w.side_scope!r}"
    )


def test_widget_side_distribution_matches_spec():
    rally = []
    defender = []
    for hero in MYTHICS:
        w = _get_skill(hero, "widget")
        if w.side_scope == "rally":
            rally.append(hero)
        else:
            defender.append(hero)
    expected_rally = {"Amadeus", "Petra", "Helga", "Marlin", "Rosa", "Thrud", "Yang", "Ava"}
    assert set(rally) == expected_rally, (
        f"Rally widgets diverged from spec. Got: {sorted(rally)}, "
        f"expected: {sorted(expected_rally)}"
    )
    assert len(defender) == 14, (
        f"Expected 14 DEFENDER widgets (22 mythics - 8 rally), got "
        f"{len(defender)}: {defender}"
    )


def _build_test_fighter(hero_inf="Eric", hero_cav="Petra", hero_arc="Yang"):
    from kingshot_sim.config.fighter import (
        Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero,
    )
    return Fighter(
        label="t",
        leader_inf=LeaderHero(hero_name=hero_inf, level="MAX", widget_level=10),
        leader_cav=LeaderHero(hero_name=hero_cav, level="MAX", widget_level=10),
        leader_arc=LeaderHero(hero_name=hero_arc, level="MAX", widget_level=10),
        joiners=(),
        bonuses=BonusVector(),
        troops=TroopRoster(
            infantry=(TroopGroup(tier="T10.5", count=100_000),),
            cavalry=(TroopGroup(tier="T10.5", count=100_000),),
            archer=(TroopGroup(tier="T10.5", count=100_000),),
        ),
    )


@pytest.mark.parametrize("hero,slot", [
    ("Eric",     "sk1"),
    ("Eric",     "sk2"),
    ("Triton",   "sk1"),
    ("Margot",   "sk1"),
    ("Yang",     "sk1"),
    ("Sophia",   "sk2"),
    ("Sophia",   "sk3"),
    ("Petra",    "sk1"),
    ("Margot",   "sk2"),
    ("Vivian",   "sk1"),
])
def test_skill_surfaces_in_resolver(hero, slot):
    from kingshot_sim.engine.compile import compile_fighter
    from kingshot_sim.engine.resolver import collect_active_effects
    from kingshot_sim.domain.enums import RNGMode

    klass = HERO_CLASS[hero]
    if klass == "Inf":
        fighter = _build_test_fighter(hero_inf=hero)
    elif klass == "Cav":
        fighter = _build_test_fighter(hero_cav=hero)
    else:
        fighter = _build_test_fighter(hero_arc=hero)

    fs = compile_fighter(fighter, side="rally")
    effects = collect_active_effects(fs, round_idx=0, rng_mode=RNGMode.EXPECTED)

    sk = _get_skill(hero, slot)
    if sk.special == SkillSpecial.DODGE:
        assert fs.dodge_chance > 0, (
            f"{hero} {slot} is DODGE but fighter.dodge_chance is 0"
        )
        return

    skill_ops = {e.op for e in sk.effects if e.op != 0}
    surfaced_ops = {e.op for e in effects}
    assert skill_ops & surfaced_ops, (
        f"{hero} {slot} produced no surfaced effects in resolver. "
        f"Skill ops: {skill_ops}. Surfaced ops: {surfaced_ops}."
    )


@pytest.mark.parametrize("hero,slot", [(h, s) for h in MYTHICS
                                          for s in ("sk1", "sk2", "sk3", "widget")])
def test_mythic_effect_values_stored_positive(hero, slot):
    if hero == "Saul" and slot == "sk2":
        return
    sk = _get_skill(hero, slot)
    if sk is None:
        return
    for e in sk.effects:
        if e.op in (111, 112, 113, 201, 202, 203, 211):
            assert e.value >= 0, (
                f"{hero} {slot} op {e.op} has NEGATIVE value {e.value}; "
                f"per V8 D-36 convention these must be stored as positive "
                f"magnitudes."
            )


@pytest.mark.parametrize("hero", MYTHICS + EPICS)
def test_hero_has_leader_max(hero):
    assert hero in HERO_LEADER_MAX, f"{hero} missing from HERO_LEADER_MAX"
    val = HERO_LEADER_MAX[hero]
    assert val > 0, f"{hero} has leader_max = 0"
