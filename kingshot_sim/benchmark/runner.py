from __future__ import annotations
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Optional

from ..config.fighter import (
    Fighter, BonusVector, TroopRoster, TroopGroup, LeaderHero, HeroGearPiece,
)
from ..engine.battle import BattleConfig, run_battle
from ..domain.enums import RNGMode
from ..data.reference import (
    hero_class, heroes_up_to_generation, LEVEL_FRACTION,
    helga_passive_value, amadeus_passive_value,
)
from .reference import (
    SCENARIOS, SCENARIO_ROLE, scenario_formations,
    GEN_TROOP_TIER, GEN_BONUS_PCT, GEN_TROOP_COUNT, GEN_LEADER_MAX,
)

_Ratio = tuple[float, float, float]

_DUMMY_LEADERS = ("_BM_Inf", "_BM_Cav", "_BM_Arc")


@dataclass(frozen=True)
class BenchSettings:
    inflation_pct: float = 0.0
    dummy_troop_mult: float = 1.0
    n_rounds: int = 20
    target_troop_mult: float = 3.0
    gen_scale: float = 0.4
    defense_threat_pct: float = 0.0
    defense_attacker_mult: float = 0.5
    defense_survival_weight: float = 0.6


@dataclass(frozen=True)
class HeroBuild:
    level: str = "MAX"
    widget_level: int = 10
    skill_levels: Optional[tuple[int, int, int]] = None


@dataclass(frozen=True)
class Formations:
    per_scenario: dict[str, tuple[_Ratio, _Ratio]]

    @classmethod
    def for_gen(cls, gen: int) -> "Formations":
        return cls(per_scenario=scenario_formations(gen))


def _bonus(pct: float) -> BonusVector:
    return BonusVector(
        squad_atk_pct=pct, squad_def_pct=pct, squad_let_pct=pct, squad_hp_pct=pct,
    )


def _unique_passive_pool(
    names: tuple[str, ...], builds: Optional[dict[str, "HeroBuild"]]
) -> tuple[float, float, float, float]:
    d_atk = d_def = d_let = d_hp = 0.0
    builds = builds or {}
    for name in names:
        lvl = builds.get(name, HeroBuild()).level
        if name == "Helga":
            v = helga_passive_value(lvl) * 100.0
            d_atk += v
            d_def += v
        elif name == "Amadeus":
            v = amadeus_passive_value(lvl) * 100.0
            d_let += v
            d_hp += v
    return d_atk, d_def, d_let, d_hp


def _roster(tier: str, count: int, ratio: _Ratio) -> TroopRoster:
    ri, rc, ra = ratio
    ni = int(count * ri)
    nc = int(count * rc)
    na = count - ni - nc
    return TroopRoster(
        infantry=(TroopGroup(tier=tier, count=ni),) if ni > 0 else (),
        cavalry=(TroopGroup(tier=tier, count=nc),) if nc > 0 else (),
        archer=(TroopGroup(tier=tier, count=na),) if na > 0 else (),
    )


def _closest_level(frac: float) -> str:
    return min(LEVEL_FRACTION, key=lambda lv: abs(LEVEL_FRACTION[lv] - frac))


def user_strength_factor(builds: Optional[dict[str, HeroBuild]]) -> float:
    if not builds:
        return 1.0
    fr = [LEVEL_FRACTION[b.level] for b in builds.values()]
    return sum(fr) / len(fr) if fr else 1.0


def build_dummy(gen: int, settings: BenchSettings, ratio: _Ratio,
                user_factor: float = 1.0, troop_mult: Optional[float] = None) -> Fighter:
    pct = (GEN_BONUS_PCT[gen]
           + settings.gen_scale * GEN_LEADER_MAX[gen] * user_factor
           + settings.inflation_pct)
    mult = settings.dummy_troop_mult if troop_mult is None else troop_mult
    count = int(GEN_TROOP_COUNT[gen] * mult)
    dlevel = _closest_level(user_factor)
    li, lc, la = (LeaderHero(hero_name=n, level=dlevel, widget_level=0)
                  for n in _DUMMY_LEADERS)
    return Fighter(
        label="DUMMY", leader_inf=li, leader_cav=lc, leader_arc=la,
        joiners=(), bonuses=_bonus(pct),
        troops=_roster(GEN_TROOP_TIER[gen], count, ratio),
    )


def build_trio(
    inf: str, cav: str, arc: str, gen: int, ratio: _Ratio,
    *,
    builds: Optional[dict[str, HeroBuild]] = None,
    class_gear: Optional[dict[str, dict[str, HeroGearPiece]]] = None,
) -> Fighter:
    builds = builds or {}
    cg = class_gear or {}

    def lh(name: str) -> LeaderHero:
        b = builds.get(name, HeroBuild())
        return LeaderHero(
            hero_name=name, level=b.level, widget_level=b.widget_level,
            skill_levels=b.skill_levels, gear=cg.get(hero_class(name), {}),
        )

    base = GEN_BONUS_PCT[gen]
    pa, pd, pl, ph = _unique_passive_pool((inf, cav, arc), builds)
    bonuses = BonusVector(
        squad_atk_pct=base + pa, squad_def_pct=base + pd,
        squad_let_pct=base + pl, squad_hp_pct=base + ph,
    )
    return Fighter(
        label=f"{inf}|{cav}|{arc}", leader_inf=lh(inf), leader_cav=lh(cav),
        leader_arc=lh(arc), joiners=(), bonuses=bonuses,
        troops=_roster(GEN_TROOP_TIER[gen], GEN_TROOP_COUNT[gen], ratio),
    )


def build_scenario_dummies(
    gen: int, settings: BenchSettings, formations: Formations, user_factor: float,
) -> dict[str, Fighter]:
    atk_settings = replace(
        settings, inflation_pct=settings.inflation_pct + settings.defense_threat_pct)
    dummies: dict[str, Fighter] = {}
    for scen, (_user_ratio, enemy_ratio) in formations.per_scenario.items():
        user_is_attacker, _ = SCENARIO_ROLE[scen]
        if user_is_attacker:
            dummies[scen] = build_dummy(
                gen, settings, enemy_ratio, user_factor=user_factor,
                troop_mult=settings.target_troop_mult)
        else:
            dummies[scen] = build_dummy(
                gen, atk_settings, enemy_ratio, user_factor=user_factor,
                troop_mult=settings.defense_attacker_mult)
    return dummies


def score_trio(
    names: tuple[str, str, str], gen: int, settings: BenchSettings,
    dummies: dict[str, Fighter], formations: Formations,
    builds: Optional[dict[str, HeroBuild]] = None,
    class_gear: Optional[dict[str, dict[str, HeroGearPiece]]] = None,
    all_around_weights: Optional[dict[str, float]] = None,
) -> dict[str, float]:
    out: dict[str, float] = {}
    user_total = GEN_TROOP_COUNT[gen]
    sw = settings.defense_survival_weight
    for scen, (user_ratio, _enemy_ratio) in formations.per_scenario.items():
        user_is_attacker, is_solo = SCENARIO_ROLE[scen]
        fighter = build_trio(*names, gen, user_ratio,
                             builds=builds, class_gear=class_gear)
        dummy = dummies[scen]
        if user_is_attacker:
            r = run_battle(BattleConfig(
                attacker=fighter, defender=dummy, rng_mode=RNGMode.EXPECTED,
                max_rounds=settings.n_rounds, is_solo_attack=is_solo,
            ))
            out[scen] = r.defender_lost() / user_total
        else:
            r = run_battle(BattleConfig(
                attacker=dummy, defender=fighter, rng_mode=RNGMode.EXPECTED,
                max_rounds=settings.n_rounds, is_solo_attack=is_solo,
            ))
            own0 = sum(r.defender_initial.values())
            own1 = sum(r.defender_final.values())
            survival = (own1 / own0) if own0 else 0.0
            en0 = sum(r.attacker_initial.values())
            kill_frac = (r.attacker_lost() / en0) if en0 else 0.0
            out[scen] = sw * survival + (1.0 - sw) * kill_frac
    if all_around_weights is None:
        out["all_around"] = sum(out[s] for s in SCENARIOS) / len(SCENARIOS)
    else:
        w = all_around_weights
        tot = sum(w.get(s, 0.0) for s in SCENARIOS) or 1.0
        out["all_around"] = sum(out[s] * w.get(s, 0.0) for s in SCENARIOS) / tot
    return out


def trios_for_gen(gen: int,
                  roster: Optional[set[str]] = None) -> list[tuple[str, str, str]]:
    if roster is not None:
        pool = set(roster)
    else:
        pool = set(heroes_up_to_generation(gen))
    inf = sorted(h for h in pool if hero_class(h) == "Inf")
    cav = sorted(h for h in pool if hero_class(h) == "Cav")
    arc = sorted(h for h in pool if hero_class(h) == "Arc")
    return [(i, c, a) for i in inf for c in cav for a in arc]


@dataclass
class GenRanking:
    gen: int
    settings: BenchSettings
    ranked: dict[str, list[tuple[float, tuple[str, str, str]]]] = field(default_factory=dict)
    per_hero: dict[str, dict[str, float]] = field(default_factory=dict)
    n_battles: int = 0


def rank_generation(
    gen: int, settings: BenchSettings,
    formations: Optional[Formations] = None,
    builds: Optional[dict[str, HeroBuild]] = None,
    class_gear: Optional[dict[str, dict[str, HeroGearPiece]]] = None,
    roster: Optional[set[str]] = None,
    dummy_factor: Optional[float] = None,
    all_around_weights: Optional[dict[str, float]] = None,
) -> GenRanking:
    formations = formations or Formations.for_gen(gen)
    uf = user_strength_factor(builds) if dummy_factor is None else dummy_factor
    dummies = build_scenario_dummies(gen, settings, formations, uf)
    scen_keys = list(SCENARIOS) + ["all_around"]
    scores: dict[tuple[str, str, str], dict[str, float]] = {}
    for names in trios_for_gen(gen, roster=roster):
        scores[names] = score_trio(
            names, gen, settings, dummies, formations,
            builds=builds, class_gear=class_gear,
            all_around_weights=all_around_weights,
        )

    ranked: dict[str, list[tuple[float, tuple[str, str, str]]]] = {}
    per_hero: dict[str, dict[str, float]] = {}
    for scen in scen_keys:
        ranked[scen] = sorted(
            ((sc[scen], names) for names, sc in scores.items()),
            key=lambda t: -t[0],
        )
        acc: dict[str, list[float]] = {}
        for names, sc in scores.items():
            for h in names:
                acc.setdefault(h, []).append(sc[scen])
        per_hero[scen] = {h: sum(v) / len(v) for h, v in acc.items()}

    n_battles = len(scores) * len(SCENARIOS)
    return GenRanking(gen=gen, settings=settings, ranked=ranked, per_hero=per_hero,
                      n_battles=n_battles)


@lru_cache(maxsize=32)
def maxed_ranking(gen: int, settings: BenchSettings = BenchSettings()) -> GenRanking:
    return rank_generation(gen, settings)


def oracle_rank(ranked: list[tuple[float, tuple[str, str, str]]],
                target: tuple[str, str, str]) -> int:
    for i, (_, names) in enumerate(ranked, start=1):
        if names == target:
            return i
    return 0


__all__ = [
    "BenchSettings", "HeroBuild", "Formations", "build_dummy", "build_trio",
    "build_scenario_dummies", "score_trio", "trios_for_gen", "rank_generation",
    "maxed_ranking", "oracle_rank", "GenRanking", "user_strength_factor",
]
