from __future__ import annotations
from typing import TYPE_CHECKING

from ..domain.enums import SquadType, SkillSpecial, TriggerKind
from ..domain.skills import Skill, SkillTrigger, Effect
from .reference import (
    HERO_WIDGET, WIDGET_SKILL_MULTIPLIER, WIDGET_SKILL_MAX_PCT,
)

if TYPE_CHECKING:
    from ..domain.heroes import Hero


ALL_SQ = frozenset(SquadType.all())
INF_ARC = frozenset({SquadType.INFANTRY, SquadType.ARCHER})
INF_ONLY = frozenset({SquadType.INFANTRY})
CAV_ONLY = frozenset({SquadType.CAVALRY})
ARC_ONLY = frozenset({SquadType.ARCHER})


def _scale(value: float, skill_lvl: int) -> float:
    if skill_lvl >= 5:
        return value
    return value * (skill_lvl / 5.0)


def _scale_chance(p_max: float, skill_lvl: int) -> float:
    if skill_lvl >= 5:
        return p_max
    return p_max * (skill_lvl / 5.0)


WIDGET_SKILL_SPEC: dict[str, tuple[str, int, str]] = {
    "Aegis of Fate":     ("rally",    102, "Atk"),
    "Bands of Tyre":     ("rally",    101, "Let"),
    "Greaves of Faith":  ("defender", 101, "Let"),
    "Rabbitgear Cannon": ("defender", 102, "Atk"),
    "The Unrighteous":   ("defender", 102, "Atk"),
    "Revelation":        ("defender", 113, "HP"),
    "Mistweaver":        ("rally",    101, "Let"),
    "Anvil of Truth":    ("defender", 112, "Def"),
    "Fate's Writ":       ("rally",    102, "Atk"),
    "Wanderwail":        ("defender", 113, "HP"),
    "Praetorian Guard":  ("defender", 113, "HP"),
    "Revel Fang":        ("defender", 101, "Let"),
    "Aeolian":           ("rally",    101, "Let"),
    "Immortal's Flask":  ("defender", 102, "Atk"),
    "Bloodfang":         ("rally",    101, "Let"),
    "Lucky Spinner":     ("defender", 112, "Def"),
    "Tidal Scepter":     ("defender", 112, "Def"),
    "Scarlet Rose":      ("defender", 101, "Let"),
    "Frostkin":          ("rally",    101, "Let"),
    "Mortar":            ("defender", 102, "Atk"),
    "Chameleos":         ("rally",    101, "Let"),
    "Justice Fist":      ("defender", 113, "HP"),
}


def _widget_skill(hero: "Hero") -> Skill | None:
    if not hero.is_mythic or hero.widget_level == 0:
        return None
    wname = HERO_WIDGET[hero.name]
    side, op, label = WIDGET_SKILL_SPEC[wname]
    pct = WIDGET_SKILL_MAX_PCT * WIDGET_SKILL_MULTIPLIER[hero.widget_level]
    if pct == 0:
        return None
    return Skill(
        name=f"{wname} (widget)",
        trigger=SkillTrigger.passive(),
        effects=(Effect(op=op, value=pct),),
        side_scope=side,
        hero=hero.name,
        slot="widget",
        description=f"+{pct:.1f}% {label} on {side} side",
    )


def _mythic_skills(hero: "Hero") -> list[Skill]:
    s1, s2, s3 = hero.skill_levels
    name = hero.name
    out: list[Skill] = []

    if name == "Amadeus":
        out += [
            Skill("Battle Ready",
                  SkillTrigger.passive(),
                  (Effect(101, _scale(25.0, s1)),),
                  hero=name, slot="sk1",
                  description="+25% Lethality, all squads"),
            Skill("Way of the Blade",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s2)),),
                  hero=name, slot="sk2",
                  description="+25% Attack, all squads"),
            Skill("Unrighteous Strike",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s3)),
                  (Effect(102, 50.0),),
                  hero=name, slot="sk3",
                  description="8/16/24/32/40% × +50% Damage Dealt all squads (chance scales)"),
        ]

    elif name == "Helga":
        out += [
            Skill("Oath of Guardian",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s1)),
                  (Effect(111, 50.0),),
                  hero=name, slot="sk1",
                  description="8/16/24/32/40% × -50% damage taken all squads (chance scales)"),
            Skill("Echoes of Valhalla",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s2)),),
                  hero=name, slot="sk2",
                  description="+25% Attack all squads"),
            Skill("Nature's Balance",
                  SkillTrigger.passive(),
                  (Effect(101, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Lethality all squads"),
        ]

    elif name == "Jabel":
        out += [
            Skill("Rally Flag",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s1)),
                  (Effect(111, 50.0),),
                  hero=name, slot="sk1",
                  description="8/16/24/32/40% × -50% damage taken all squads (chance scales)"),
            Skill("Hero's Domain",
                  SkillTrigger.rng_round(p=0.50),
                  (Effect(102, _scale(50.0, s2)),),
                  hero=name, slot="sk2",
                  description="50% × +50% damage dealt"),
            Skill("Youthful Rage",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Damage all squads"),
        ]

    elif name == "Saul":
        out += [
            Skill("Taskforce Training",
                  SkillTrigger.passive(),
                  (Effect(112, _scale(10.0, s1)), Effect(113, _scale(15.0, s1))),
                  hero=name, slot="sk1",
                  description="+10% Defense AND +15% Health"),
            Skill("Resourceful",
                  SkillTrigger.passive(),
                  (),
                  hero=name, slot="sk2",
                  description="Construction speed (non-combat)"),
            Skill("Positional Batter",
                  SkillTrigger.passive(),
                  (Effect(101, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Lethality all squads"),
        ]

    elif name == "Zoe":
        out += [
            Skill("Sundering Wound",
                  SkillTrigger.rng_attack(p=0.20, duration=3),
                  (Effect(102, _scale(40.0, s1)),),
                  hero=name, slot="sk1",
                  description="20% per attack × +40% damage for 3 turns"),
            Skill("Stoic",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s2)),),
                  hero=name, slot="sk2",
                  description="+25% Attack all squads"),
            Skill("Infinite Arsenal",
                  SkillTrigger.rng_round(p=0.50),
                  (Effect(211, _scale(50.0, s3)),),
                  hero=name, slot="sk3",
                  description="50% × +50% enemy damage taken"),
        ]

    elif name == "Hilde":
        out += [
            Skill("Noble Path",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(15.0, s1)), Effect(112, _scale(10.0, s1))),
                  hero=name, slot="sk1",
                  description="+15% Atk AND +10% Def all squads"),
            Skill("Elixir of Strength",
                  SkillTrigger.rng_round(p=0.25),
                  (Effect(102, _scale(200.0, s2)),),
                  hero=name, slot="sk2",
                  description="25% × +200% damage"),
            Skill("Trial by Fire",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s3)),
                  (Effect(111, 50.0),),
                  hero=name, slot="sk3",
                  description="8/16/24/32/40% × -50% damage taken (chance scales)"),
        ]

    elif name == "Marlin":
        out += [
            Skill("Wild Card",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s1)),
                  (Effect(102, 50.0),),
                  hero=name, slot="sk1",
                  description="8/16/24/32/40% × +50% damage dealt (chance scales)"),
            Skill("Rumhead",
                  SkillTrigger.rng_round(p=0.20, duration=2),
                  (Effect(203, _scale(50.0, s2)),),
                  hero=name, slot="sk2",
                  description="20% × -50% enemy damage for 2 turns"),
            Skill("Dynamo",
                  SkillTrigger.rng_round(p=0.50),
                  (Effect(102, _scale(50.0, s3)),),
                  hero=name, slot="sk3",
                  description="50% × +50% damage all squads"),
        ]

    elif name == "Eric":
        out += [
            Skill("Holy Warrior",
                  SkillTrigger.passive(),
                  (Effect(202, _scale(20.0, s1)),),
                  hero=name, slot="sk1",
                  description="-20% enemy Attack"),
            Skill("Conviction",
                  SkillTrigger.passive(),
                  (Effect(111, _scale(20.0, s2)),),
                  hero=name, slot="sk2",
                  description="-20% damage taken"),
            Skill("Exhortation",
                  SkillTrigger.passive(),
                  (Effect(113, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Health"),
        ]

    elif name == "Petra":
        out += [
            Skill("Evil Eye",
                  SkillTrigger.rng_attack(p=0.50),
                  (Effect(211, _scale(50.0, s1)),),
                  special=SkillSpecial.TARGET_DEBUFF_ON_HIT,
                  hero=name, slot="sk1",
                  description="50%/attack × +50% target damage taken (1 round)"),
            Skill("The Favor",
                  SkillTrigger.rng_round(p=0.50),
                  (Effect(102, _scale(50.0, s2)),),
                  hero=name, slot="sk2",
                  description="50% × +50% Attack"),
            Skill("The Shield",
                  SkillTrigger.rng_round(p=0.40),
                  (Effect(111, _scale(50.0, s3)),),
                  hero=name, slot="sk3",
                  description="40% chance x -10/20/30/40/50% damage taken (value scales)"),
        ]

    elif name == "Jaeger":
        out += [
            Skill("The Tempest",
                  SkillTrigger.rng_round(p=0.20, duration=3),
                  (Effect(102, _scale(40.0, s1)),),
                  hero=name, slot="sk1",
                  description="20% × +40% damage for 3 turns"),
            Skill("The Resistance",
                  SkillTrigger.rng_attack(p=0.20, duration=2),
                  (Effect(203, _scale(50.0, s2)),),
                  hero=name, slot="sk2",
                  description="20%/attack × -50% enemy damage for 2 turns"),
            Skill("The Celebration",
                  SkillTrigger.passive(),
                  (Effect(113, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Health"),
        ]

    elif name == "Alcar":
        out += [
            Skill("Rescuing Hands",
                  SkillTrigger.periodic(period=5, duration=2, offset=4),
                  (Effect(111, _scale(70.0, s1), target_squads=INF_ARC),),
                  hero=name, slot="sk1",
                  description="Every 5 turns: -70% damage taken Inf+Arc 2 turns"),
            Skill("Praetorian Will",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(100.0, s2), target_squads=INF_ONLY),
                   Effect(102, _scale(10.0, s2), target_squads=frozenset({SquadType.CAVALRY, SquadType.ARCHER}))),
                  hero=name, slot="sk2",
                  description="Inf +100% / Cav&Arc +10% damage"),
            Skill("Carpe Diem",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(60.0, s3), target_squads=INF_ONLY),
                   Effect(211, _scale(25.0, s3))),
                  hero=name, slot="sk3",
                  description="+60% Inf damage AND +25% target damage taken"),
        ]

    elif name == "Margot":
        out += [
            Skill("Warbringer",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s1)),),
                  hero=name, slot="sk1",
                  description="+25% Attack all squads"),
            Skill("Subterfuge",
                  SkillTrigger.passive(),
                  (Effect(0, _scale(20.0, s2)),),
                  special=SkillSpecial.DODGE,
                  hero=name, slot="sk2",
                  description="20% dodge chance per incoming attack"),
            Skill("Sleight of Hand",
                  SkillTrigger.rng_attack(p=0.25),
                  (Effect(102, _scale(200.0, s3), target_squads=CAV_ONLY),),
                  hero=name, slot="sk3",
                  description="Cav 25%/atk × +200% damage"),
        ]

    elif name == "Rosa":
        out += [
            Skill("Chaos Gambit",
                  SkillTrigger.rng_round(p=0.40),
                  (Effect(102, _scale(50.0, s1)),),
                  hero=name, slot="sk1",
                  description="40% × +50% damage all squads"),
            Skill("Rose of War",
                  SkillTrigger.passive(),
                  (Effect(201, _scale(20.0, s2)),),
                  hero=name, slot="sk2",
                  description="-20% enemy damage"),
            Skill("Golden Rhythm",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(30.0, s3), target_squads=ARC_ONLY),),
                  hero=name, slot="sk3",
                  description="+30% Arc Attack"),
        ]

    elif name == "Long Fei":
        out += [
            Skill("Mighty Paragon",
                  SkillTrigger.rng_round(p=0.40),
                  (Effect(111, _scale(50.0, s1)),),
                  hero=name, slot="sk1",
                  description="40% chance x -10/20/30/40/50% damage taken (value scales)"),
            Skill("Celestial Sustenance",
                  SkillTrigger.passive(),
                  (Effect(112, _scale(25.0, s2)),),
                  hero=name, slot="sk2",
                  description="+25% Defense"),
            Skill("Art of War",
                  SkillTrigger.rng_attack(p=0.25),
                  (Effect(102, _scale(200.0, s3)),),
                  hero=name, slot="sk3",
                  description="25%/atk × +200% damage"),
        ]

    elif name == "Thrud":
        out += [
            Skill("Battle Hunger",
                  SkillTrigger.passive(),
                  (Effect(111, _scale(15.0, s1), target_squads=INF_ARC),
                   Effect(102, _scale(15.0, s1), target_squads=INF_ARC)),
                  hero=name, slot="sk1",
                  description="-15% damage taken AND +15% damage on Inf+Arc"),
            Skill("Reckless Charge",
                  SkillTrigger.rng_attack(p=0.20),
                  (Effect(102, _scale(100.0, s2), target_squads=CAV_ONLY),),
                  hero=name, slot="sk2",
                  description="Cav 20%/atk × +100% damage"),
            Skill("Ancestral Guidance",
                  SkillTrigger.periodic(period=4, duration=2, offset=3),
                  (Effect(102, _scale(25.0, s3)), Effect(111, _scale(25.0, s3))),
                  hero=name, slot="sk3",
                  description="Every 4 cav atks: +25% dmg AND -25% dmg taken 2t"),
        ]

    elif name == "Vivian":
        out += [
            Skill("Crouching Tiger",
                  SkillTrigger.passive(),
                  (Effect(211, _scale(25.0, s1)),),
                  hero=name, slot="sk1",
                  description="+25% enemy damage taken (passive)"),
            Skill("Focus Fire",
                  SkillTrigger.periodic(period=4, duration=1, offset=3),
                  (Effect(102, _scale(100.0, s2)), Effect(211, _scale(15.0, s2))),
                  hero=name, slot="sk2",
                  description="Every 4: +100% extra damage AND +15% target dmg taken"),
            Skill("Trap of Greed",
                  SkillTrigger.periodic(period=4, duration=1, offset=3),
                  (Effect(102, _scale(60.0, s3)),),
                  hero=name, slot="sk3",
                  description="Every 4 attacks: next attack +60% damage"),
        ]

    elif name == "Triton":
        out += [
            Skill("Command of Power",
                  SkillTrigger.passive(),
                  (Effect(112, _scale(25.0, s1)),),
                  hero=name, slot="sk1",
                  description="+25% Defense"),
            Skill("Warfare of Power",
                  SkillTrigger.passive(),
                  (Effect(103, _scale(30.0, s2)),),
                  hero=name, slot="sk2",
                  description="+30% Skill Damage (op 103, multiplicative on DamageUp)"),
            Skill("Oath of Power",
                  SkillTrigger.passive(),
                  (Effect(113, _scale(20.0, s3), target_squads=INF_ONLY),
                   Effect(113, _scale(30.0, s3),
                          target_squads=frozenset({SquadType.CAVALRY, SquadType.ARCHER}))),
                  hero=name, slot="sk3",
                  description="Inf HP +20% / Cav&Arc HP +30%"),
        ]

    elif name == "Sophia":
        out += [
            Skill("Arcane Pact",
                  SkillTrigger.rng_round(p=_scale_chance(0.40, s1)),
                  (Effect(111, 50.0),),
                  hero=name, slot="sk1",
                  description="8/16/24/32/40% × -50% damage taken (chance scales)"),
            Skill("Terror - Deathblow",
                  SkillTrigger.rng_attack(p=0.50),
                  (Effect(102, _scale(200.0, s2), target_squads=CAV_ONLY),),
                  special=SkillSpecial.APPLY_TERROR_ON_HIT,
                  hero=name, slot="sk2",
                  description="Per Cav-attack 50%: apply Terror on target + Cav deals +200% damage"),
            Skill("Terror - Annihilation",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(75.0, s3)),),
                  special=SkillSpecial.CONDITIONAL_TERROR,
                  hero=name, slot="sk3",
                  description="+75% damage on Terror'd target (all squads)"),
        ]

    elif name == "Yang":
        out += [
            Skill("Avalanche",
                  SkillTrigger.periodic(period=4, duration=1, offset=3),
                  (Effect(102, _scale(100.0, s1)),),
                  hero=name, slot="sk1",
                  description="Every 4 turns: +100% damage all squads (1t)"),
            Skill("Ice Zone",
                  SkillTrigger.rng_attack(p=0.40),
                  (Effect(102, _scale(100.0, s2), target_squads=ARC_ONLY),),
                  hero=name, slot="sk2",
                  description="Arc 40%/atk × +100% damage"),
            Skill("Ambush",
                  SkillTrigger.pity(base_chance=0.40),
                  (Effect(102, _scale(40.0, s3)),),
                  special=SkillSpecial.PITY_PROC,
                  hero=name, slot="sk3",
                  description="Pity proc base 40% × +40% damage"),
        ]

    elif name == "Wee & Woo":
        out += [
            Skill("Artillerymen",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(15.0, s1)),
                   Effect(101, _scale(10.0, s1))),
                  hero=name, slot="sk1",
                  description="+15% Attack and +10% Lethality, all squads"),
            Skill("Chain Shelling",
                  SkillTrigger.passive(),
                  (Effect(102, _scale(25.0, s2), target_enemy_squads=INF_ONLY),
                   Effect(102, _scale(30.0, s2), target_enemy_squads=ARC_ONLY)),
                  hero=name, slot="sk2",
                  description="+25% damage vs Inf targets, +30% damage vs Arc targets"),
            Skill("Boom Boom",
                  SkillTrigger.pity(base_chance=_scale_chance(0.50, s3)),
                  (Effect(102, 50.0),),
                  special=SkillSpecial.PITY_PROC,
                  hero=name, slot="sk3",
                  description="Pity proc base 10/20/30/40/50% × +50% damage (chance scales)"),
        ]

    elif name == "Ava":
        out += [
            Skill("Dissolution",
                  SkillTrigger.passive(),
                  (Effect(212, _scale(25.0, s1)),),
                  hero=name, slot="sk1",
                  description="-25% enemy Defense, all squads"),
            Skill("Chiaroscuro",
                  SkillTrigger.periodic(period=4, duration=2, offset=3),
                  (Effect(211, _scale(50.0, s2)),),
                  hero=name, slot="sk2",
                  description="Every 4 turns: +50% damage taken on all enemy squads for 2 turns"),
            Skill("Light and Cold",
                  SkillTrigger.passive(),
                  (Effect(101, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Lethality, all squads"),
        ]

    elif name == "Charles":
        out += [
            Skill("Intimidation",
                  SkillTrigger.passive(),
                  (Effect(203, _scale(20.0, s1)),),
                  hero=name, slot="sk1",
                  description="-20% enemy total Lethality (generic damage down), all squads"),
            Skill("Iron Bodies",
                  SkillTrigger.passive(),
                  (Effect(111, _scale(20.0, s2)),),
                  hero=name, slot="sk2",
                  description="-20% damage taken, all squads"),
            Skill("Great Justice",
                  SkillTrigger.passive(),
                  (Effect(113, _scale(25.0, s3)),),
                  hero=name, slot="sk3",
                  description="+25% Health, all squads"),
        ]

    return out


def _epic_skills(hero: "Hero") -> list[Skill]:
    s1 = hero.skill_level("sk1")
    name = hero.name
    out: list[Skill] = []

    if name == "Howard":
        out.append(Skill("Defenders' Edge",
                         SkillTrigger.passive(),
                         (Effect(111, _scale(20.0, s1)),),
                         hero=name, slot="sk1",
                         description="-20% damage taken"))
    elif name == "Chenko":
        out.append(Skill("Stand of Arms",
                         SkillTrigger.passive(),
                         (Effect(101, _scale(25.0, s1)),),
                         hero=name, slot="sk1",
                         description="+25% Lethality"))
    elif name == "Gordon":
        out.append(Skill("Super Nutrients",
                         SkillTrigger.passive(),
                         (Effect(113, _scale(25.0, s1)),),
                         hero=name, slot="sk1",
                         description="+25% Health"))
    elif name == "Fahd":
        out.append(Skill("Desert Eclipse",
                         SkillTrigger.passive(),
                         (Effect(201, _scale(20.0, s1)),),
                         hero=name, slot="sk1",
                         description="-20% enemy damage"))
    elif name == "Quinn":
        out.append(Skill("Sixth Sense",
                         SkillTrigger.passive(),
                         (Effect(111, _scale(20.0, s1)),),
                         hero=name, slot="sk1",
                         description="-20% damage taken"))
    elif name == "Diana":
        pass
    elif name == "Yeonwoo":
        out.append(Skill("On Guard",
                         SkillTrigger.passive(),
                         (Effect(101, _scale(25.0, s1)),),
                         hero=name, slot="sk1",
                         description="+25% Lethality"))
    elif name == "Amane":
        out.append(Skill("Tri-Phalanx",
                         SkillTrigger.passive(),
                         (Effect(102, _scale(25.0, s1)),),
                         hero=name, slot="sk1",
                         description="+25% Attack"))

    return out


def get_hero_skills(hero: "Hero") -> list[Skill]:
    from .op_overrides import apply_overrides_to_skill
    from . import reference as _ref

    if hero.name in _ref.BENCHMARK_DUMMIES:
        eff = tuple(Effect(op=op, value=val) for op, val in _ref.BENCHMARK_DUMMY_SKILL)
        if not eff:
            return []
        return [Skill(
            name="Benchmark Threat",
            trigger=SkillTrigger.passive(),
            effects=eff,
            side_scope="both",
            hero=hero.name,
            slot="sk1",
            description="Synthetic benchmark dummy offensive profile",
        )]

    raw_skills: list[Skill] = []
    if hero.is_mythic:
        raw_skills.extend(_mythic_skills(hero))
        widget = _widget_skill(hero)
        if widget is not None:
            raw_skills.append(widget)
    elif hero.is_epic:
        raw_skills.extend(_epic_skills(hero))

    return [apply_overrides_to_skill(hero.name, sk.slot, sk) for sk in raw_skills]


__all__ = ["get_hero_skills", "WIDGET_SKILL_SPEC"]
