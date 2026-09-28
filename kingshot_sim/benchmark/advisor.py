from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Optional

from ..config.fighter import HeroGearPiece
from ..data.reference import (
    hero_class, hero_leader_max, star_from_level, HERO_GENERATION, MAX_GENERATION,
    EPIC_HEROES,
)
from .runner import (
    BenchSettings, HeroBuild, rank_generation, GenRanking, user_strength_factor,
)
from .reference import CASH_ONLY_HEROES
from .economy import (
    acquisition_tier, shards_to_skill_complete, shards_to_star, gens_to_afford,
    gens_to_save, player_profile, PROFILE_TARGET_STAR, PROFILE_WEIGHTS,
    SKILL_COMPLETE_STAR, MAX_STAR,
    ROULETTE_HERO_BY_GEN, STAR_SHARD_CUMULATIVE, F2P_SHARDS_PER_GEN,
)

PLAYSTYLE_SCENARIO: dict[str, str] = {
    "attack": "solo_atk", "rally": "rally_atk", "defense": "defense",
    "garrison": "garrison", "balanced": "all_around",
}

HOLD_MARGIN: float = 0.07

HOLD_MARGIN_PER_GEN: float = 0.13


def _hold_margin(gens_away: int) -> float:
    return HOLD_MARGIN + HOLD_MARGIN_PER_GEN * max(0, gens_away - 1)

_CURVE_DEF_ATK_MULT: float = 0.7

LOOKAHEAD: int = 2

_CORE_SCENARIOS: tuple[str, ...] = ("solo_atk", "rally_atk", "defense", "garrison")
_SCEN_SHORT = {"solo_atk": "solo attack", "rally_atk": "rally",
               "defense": "defense", "garrison": "garrison"}


def _star_level(star: int) -> str:
    return "MAX" if star >= MAX_STAR else f"{int(star)}_0"


@dataclass
class HeroAdvice:
    hero: str
    cls: str
    acquisition: str
    current_star: int
    current_value: float
    ceiling_value: float
    shards_to_4star: int
    target_star: int = SKILL_COMPLETE_STAR
    shards_to_target: int = 0
    owned: bool = True

    @property
    def headroom(self) -> float:
        return max(0.0, self.ceiling_value - self.current_value)

    @property
    def skill_complete(self) -> bool:
        return self.current_star >= self.target_star

    @property
    def gens_to_4star(self) -> float:
        return gens_to_afford(self.shards_to_target or self.shards_to_4star)

    @property
    def power_per_shard(self) -> float:
        cost = self.shards_to_target or self.shards_to_4star
        return self.headroom / cost * 1000.0 if cost > 0 else 0.0


@dataclass
class ClassPlan:
    cls: str
    best_hero: str
    best_star: int
    best_headroom: float
    shards_to_4star: int
    verdict: str
    target_star: int = SKILL_COMPLETE_STAR
    power_per_shard: float = 0.0
    priority: int = 0
    funded: bool = False
    is_roulette: bool = False
    acquire: bool = False
    future_hero: Optional[str] = None
    future_gen: Optional[int] = None
    future_acquisition: Optional[str] = None
    upcoming_hero: Optional[str] = None
    upcoming_gen: Optional[int] = None
    free_soon_hero: Optional[str] = None
    free_soon_gen: Optional[int] = None
    free_soon_gap: float = 0.0
    future_gap: float = 0.0
    versatility: Optional[str] = None

    @property
    def gens_to_4star(self) -> float:
        return gens_to_afford(self.shards_to_4star)


@dataclass
class ShardLedgerStep:
    gen: int
    start: int
    income: int
    spends: list[tuple[str, int]] = field(default_factory=list)
    end: int = 0
    saving_for: Optional[tuple[str, int]] = None


@dataclass
class AdvisorReport:
    gen: int
    playstyle: str
    scenario: str
    heroes: list[HeroAdvice] = field(default_factory=list)
    roadmap: list[ClassPlan] = field(default_factory=list)
    develop_next: list[HeroAdvice] = field(default_factory=list)
    keep_over: list[tuple[str, str]] = field(default_factory=list)
    best_trio: Optional[tuple[str, str, str]] = None
    roulette_hero: Optional[str] = None
    shard_budget: Optional[int] = None
    shard_income: int = F2P_SHARDS_PER_GEN
    widget_target: int = 0
    profile: str = "spender"
    target_star: int = SKILL_COMPLETE_STAR
    spend_order: list[ClassPlan] = field(default_factory=list)
    total_shards_needed: int = 0
    spend_now: int = 0
    bank_amount: int = 0
    bank_target: Optional[tuple[str, int, Optional[int], Optional[int]]] = None
    n_battles: int = 0
    efficiency: dict[str, tuple[float, int, float, int]] = field(default_factory=dict)
    curve: dict[str, dict[str, float]] = field(default_factory=dict)
    curve_target: dict[str, dict[str, float]] = field(default_factory=dict)
    curve_current: dict[str, dict[str, float]] = field(default_factory=dict)
    comp_by_mode: dict[str, tuple] = field(default_factory=dict)
    shard_ledger: list[ShardLedgerStep] = field(default_factory=list)


def _future_class_hero(gen_f: int, cls: str) -> Optional[str]:
    for h, g in HERO_GENERATION.items():
        if g == gen_f and hero_class(h) == cls:
            return h
    return None


def _acquirable_now(gen: int, owned: set[str]) -> list[str]:
    return sorted(h for h, g in HERO_GENERATION.items()
                  if g == gen and h not in owned and acquisition_tier(h) != "cash")


def _ceiling_widget(hero: str, current_widget: int, widget_target: int) -> int:
    if hero in EPIC_HEROES:
        return 0
    return max(int(widget_target), int(current_widget))


def class_value_curve(
    gen: int, builds: dict[str, HeroBuild], cls: str,
    future_heroes: list[str], settings: Optional[BenchSettings] = None,
    widget_target: int = 0, target_star: int = MAX_STAR,
    with_current: bool = False,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    cset = replace(settings or BenchSettings(),
                   defense_attacker_mult=_CURVE_DEF_ATK_MULT)
    owned = set(builds)
    partners: dict[str, str] = {}
    for c in ("Inf", "Cav", "Arc"):
        if c == cls:
            continue
        cand = [h for h in owned if hero_class(h) == c]
        if not cand:
            return {}, {}
        partners[c] = max(cand, key=hero_leader_max)
    cls_owned = [h for h in owned if hero_class(h) == cls]
    pool = set(cls_owned) | set(future_heroes) | set(partners.values())
    tgt_lvl = _star_level(target_star)
    tgt_builds = {h: HeroBuild(level=tgt_lvl,
                               widget_level=(0 if h in EPIC_HEROES else int(widget_target)))
                  for h in pool}
    gt = rank_generation(gen, cset, builds=tgt_builds, roster=pool, dummy_factor=1.0)
    any_mode = gt.per_hero.get(_CORE_SCENARIOS[0], {})
    level = {h: {m: gt.per_hero.get(m, {}).get(h, 0.0) for m in _CORE_SCENARIOS}
             for h in [*cls_owned, *future_heroes] if h in any_mode}
    if not with_current:
        return level, {}
    cur_pool = set(cls_owned) | set(partners.values())
    cur_builds = {**{p: tgt_builds[p] for p in partners.values()},
                  **{h: builds[h] for h in cls_owned}}
    gc = rank_generation(gen, cset, builds=cur_builds, roster=cur_pool, dummy_factor=1.0)
    cany = gc.per_hero.get(_CORE_SCENARIOS[0], {})
    current = {h: {m: gc.per_hero.get(m, {}).get(h, 0.0) for m in _CORE_SCENARIOS}
               for h in cls_owned if h in cany}
    return level, current


def upgrade_efficiency(
    gen: int, scen: str, builds: dict[str, HeroBuild], hero: str,
    target_star: int = SKILL_COMPLETE_STAR, widget_target: int = 0,
    settings: Optional[BenchSettings] = None,
    all_around_weights: Optional[dict[str, float]] = None,
) -> tuple[float, int, float, int]:
    settings = settings or BenchSettings()
    cls = hero_class(hero)
    partners: dict[str, str] = {}
    for c in ("Inf", "Cav", "Arc"):
        if c == cls:
            continue
        cand = [h for h in builds if hero_class(h) == c]
        if not cand:
            return 0.0, 0, 0.0, 0
        partners[c] = max(cand, key=hero_leader_max)
    uf = user_strength_factor(builds)
    base_build = builds.get(hero, HeroBuild())

    def _value(hb: HeroBuild) -> float:
        bd = {hero: hb, **{p: builds[p] for p in partners.values()}}
        gr = rank_generation(gen, settings, builds=bd, roster=set(bd), dummy_factor=uf,
                             all_around_weights=all_around_weights)
        return gr.per_hero.get(scen, {}).get(hero, 0.0)

    base = _value(base_build)
    star_shards = shards_to_star(base_build.level, target_star)
    star_gain = 0.0
    if star_shards > 0:
        star_val = _value(HeroBuild(level=_star_level(target_star),
                                    widget_level=base_build.widget_level,
                                    skill_levels=base_build.skill_levels))
        star_gain = max(0.0, star_val - base)
    widget_gain = 0.0
    widget_levels = 0
    tgt_w = 0 if hero in EPIC_HEROES else max(int(widget_target), base_build.widget_level)
    if tgt_w > base_build.widget_level:
        widget_levels = tgt_w - base_build.widget_level
        w_val = _value(HeroBuild(level=base_build.level, widget_level=tgt_w,
                                 skill_levels=base_build.skill_levels))
        widget_gain = max(0.0, w_val - base)
    return star_gain, star_shards, widget_gain, widget_levels


def _resolve_weights(playstyle: str, profile: str) -> dict[str, float]:
    if playstyle == "balanced":
        return dict(PROFILE_WEIGHTS[profile])
    scen = PLAYSTYLE_SCENARIO[playstyle]
    return {m: (1.0 if m == scen else 0.0) for m in _CORE_SCENARIOS}


def _blend(vals: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights.get(m, 0.0) * vals.get(m, 0.0) for m in _CORE_SCENARIOS)


def _blend_ranking(gr: GenRanking, weights: dict[str, float]) -> GenRanking:
    core = _CORE_SCENARIOS
    heroes: set[str] = set()
    for m in core:
        heroes |= set(gr.per_hero.get(m, {}).keys())
    ph = {h: _blend({m: gr.per_hero.get(m, {}).get(h, 0.0) for m in core}, weights)
          for h in heroes}
    trio: dict[tuple, dict[str, float]] = {}
    for m in core:
        for sc, names in gr.ranked.get(m, []):
            trio.setdefault(names, {})[m] = sc
    ranked = sorted(((_blend(ms, weights), names) for names, ms in trio.items()),
                    key=lambda t: -t[0])
    return replace(gr, per_hero={**gr.per_hero, "all_around": ph},
                   ranked={**gr.ranked, "all_around": ranked})


def _blend_curve(curve: dict[str, dict[str, dict[str, float]]],
                 weights: dict[str, float]) -> dict[str, dict[str, float]]:
    return {cls: {h: _blend(vals, weights) for h, vals in hv.items()}
            for cls, hv in curve.items()}


@dataclass
class AdvisorPasses:
    gen: int
    cur: GenRanking
    ceil: GenRanking
    curve: dict[str, dict[str, dict[str, float]]]
    curve_target: dict[str, dict[str, dict[str, float]]]
    curve_current: dict[str, dict[str, dict[str, float]]]
    profile: str
    target_star: int
    widget_target: int
    shard_income: int
    settings: BenchSettings
    acquire: dict[str, HeroBuild] = field(default_factory=dict)
    n_battles: int = 0
    class_gear: Optional[dict[str, dict[str, HeroGearPiece]]] = None


def simulate(gen: int, builds: dict[str, HeroBuild],
             settings: Optional[BenchSettings] = None, lookahead: int = LOOKAHEAD,
             widget_target: int = 0, shard_income: int = F2P_SHARDS_PER_GEN,
             profile_override: Optional[str] = None,
             class_gear: Optional[dict[str, dict[str, HeroGearPiece]]] = None) -> AdvisorPasses:
    settings = settings or BenchSettings()
    uf = user_strength_factor(builds)
    profile = profile_override or player_profile(widget_target, shard_income)
    target_star = PROFILE_TARGET_STAR[profile]
    acquire = {h: HeroBuild(level=_star_level(0), widget_level=0)
               for h in _acquirable_now(gen, set(builds))}
    sim_builds = {**acquire, **builds}
    roster = set(sim_builds)
    cur = rank_generation(gen, settings, builds=sim_builds, roster=roster, dummy_factor=uf,
                          class_gear=class_gear)
    ceil_builds = {
        h: HeroBuild(level=_star_level(max(target_star, star_from_level(b.level))),
                     widget_level=_ceiling_widget(h, b.widget_level, widget_target))
        for h, b in sim_builds.items()
    }
    ceil = rank_generation(gen, settings, builds=ceil_builds, roster=roster, dummy_factor=uf,
                           class_gear=class_gear)
    last = min(gen + lookahead, MAX_GENERATION)
    curve: dict[str, dict[str, dict[str, float]]] = {}
    curve_target: dict[str, dict[str, dict[str, float]]] = {}
    curve_current: dict[str, dict[str, dict[str, float]]] = {}
    for cls in ("Inf", "Cav", "Arc"):
        newcomers = [h for gf in range(gen + 1, last + 1)
                     if (h := _future_class_hero(gf, cls)) is not None]
        curve_target[cls], curve_current[cls] = class_value_curve(
            gen, sim_builds, cls, newcomers, settings,
            widget_target=widget_target, target_star=target_star, with_current=True)
        if target_star >= MAX_STAR:
            curve[cls] = curve_target[cls]
        else:
            curve[cls], _ = class_value_curve(gen, sim_builds, cls, newcomers, settings,
                                              widget_target=widget_target)
    return AdvisorPasses(
        gen=gen, cur=cur, ceil=ceil, curve=curve, curve_target=curve_target,
        curve_current=curve_current, profile=profile, target_star=target_star,
        widget_target=widget_target, shard_income=shard_income, settings=settings,
        acquire=acquire,
        n_battles=getattr(cur, "n_battles", 0) + getattr(ceil, "n_battles", 0),
        class_gear=class_gear)


def advise_from_passes(passes: AdvisorPasses, builds: dict[str, HeroBuild],
                       weights: Optional[dict[str, float]] = None,
                       shard_budget: Optional[int] = None) -> AdvisorReport:
    if weights is None:
        weights = PROFILE_WEIGHTS[passes.profile]
    cur_b = _blend_ranking(passes.cur, weights)
    ceil_b = _blend_ranking(passes.ceil, weights)
    curve_b = _blend_curve(passes.curve, weights)
    cand_builds = {**passes.acquire, **builds}
    rep = advise_from_rankings(
        passes.gen, cand_builds, cur_b, ceil_b, curve_b, "balanced",
        shard_budget=shard_budget, widget_target=passes.widget_target,
        shard_income=passes.shard_income, target_star=passes.target_star,
        profile=passes.profile, owned=set(builds))
    rep.curve_target = _blend_curve(passes.curve_target, weights)
    rep.curve_current = _blend_curve(passes.curve_current, weights)
    rep.shard_ledger = build_shard_ledger(rep)
    rep.efficiency = {}
    for a in rep.develop_next:
        eff_builds = builds if a.owned else {**builds, a.hero: passes.acquire[a.hero]}
        rep.efficiency[a.hero] = upgrade_efficiency(
            passes.gen, "all_around", eff_builds, a.hero, passes.target_star,
            passes.widget_target, passes.settings, all_around_weights=weights)
    return rep


def advise(gen: int, builds: dict[str, HeroBuild], playstyle: str = "balanced",
           settings: Optional[BenchSettings] = None,
           lookahead: int = LOOKAHEAD, shard_budget: Optional[int] = None,
           widget_target: int = 0, shard_income: int = F2P_SHARDS_PER_GEN,
           weights: Optional[dict[str, float]] = None,
           profile_override: Optional[str] = None) -> AdvisorReport:
    passes = simulate(gen, builds, settings, lookahead, widget_target, shard_income,
                      profile_override=profile_override)
    w = weights if weights is not None else _resolve_weights(playstyle, passes.profile)
    return advise_from_passes(passes, builds, w, shard_budget=shard_budget)


def _best_other_scenario(cur: GenRanking, hero: str, scen: str) -> Optional[str]:
    vals = {s: cur.per_hero.get(s, {}).get(hero) for s in _CORE_SCENARIOS}
    vals = {s: v for s, v in vals.items() if v is not None}
    if not vals:
        return None
    best = max(vals, key=vals.get)
    return best if best != scen and vals[best] > vals.get(scen, 0.0) + 0.02 else None


def best_per_class_trio(per_hero_scen: dict[str, float]) -> Optional[tuple[str, str, str]]:
    picks: dict[str, tuple[str, float]] = {}
    for h, v in per_hero_scen.items():
        c = hero_class(h)
        if c in ("Inf", "Cav", "Arc") and (c not in picks or v > picks[c][1]):
            picks[c] = (h, v)
    if len(picks) < 3:
        return None
    return (picks["Inf"][0], picks["Cav"][0], picks["Arc"][0])


def advise_from_rankings(gen: int, builds: dict[str, HeroBuild],
                         cur: GenRanking, ceil: GenRanking,
                         curve: dict[str, dict[str, float]],
                         playstyle: str = "balanced",
                         shard_budget: Optional[int] = None,
                         widget_target: int = 0,
                         shard_income: int = F2P_SHARDS_PER_GEN,
                         target_star: int = SKILL_COMPLETE_STAR,
                         profile: str = "spender",
                         owned: Optional[set[str]] = None) -> AdvisorReport:
    scen = PLAYSTYLE_SCENARIO[playstyle]
    owned = set(builds) if owned is None else owned

    heroes: list[HeroAdvice] = []
    for h in builds:
        if h not in cur.per_hero.get(scen, {}):
            continue
        lvl = builds[h].level
        heroes.append(HeroAdvice(
            hero=h, cls=hero_class(h), acquisition=acquisition_tier(h),
            current_star=star_from_level(lvl),
            current_value=cur.per_hero[scen][h],
            ceiling_value=ceil.per_hero[scen][h],
            shards_to_4star=shards_to_skill_complete(lvl),
            target_star=target_star,
            shards_to_target=shards_to_star(lvl, target_star),
            owned=h in owned,
        ))
    heroes.sort(key=lambda a: -a.ceiling_value)

    roulette = ROULETTE_HERO_BY_GEN.get(gen)
    by_cls: dict[str, list[HeroAdvice]] = {}
    for a in heroes:
        if a.acquisition != "cash":
            by_cls.setdefault(a.cls, []).append(a)

    roadmap: list[ClassPlan] = []
    develop_next: list[HeroAdvice] = []
    for cls in ("Inf", "Cav", "Arc"):
        cls_pool = by_cls.get(cls)
        if not cls_pool:
            continue
        best = max(cls_pool, key=lambda a: a.ceiling_value)
        cv = curve.get(cls, {})
        best_cv = cv.get(best.hero)
        hold_up: Optional[tuple[str, int, float, float]] = None
        free_soon: Optional[tuple[str, int, float, float]] = None
        generic_up: Optional[tuple[str, int, float]] = None
        if best_cv is not None:
            for h, v in sorted(cv.items(), key=lambda kv: HERO_GENERATION.get(kv[0], 0)):
                gf = HERO_GENERATION.get(h, 0)
                if gf <= gen:
                    continue
                gap_abs = v - best_cv
                gap_rel = gap_abs / best_cv if best_cv > 1e-6 else 99.0
                if acquisition_tier(h) == "roulette":
                    if gap_abs > _hold_margin(gf - gen):
                        if hold_up is None or gap_abs > hold_up[3]:
                            hold_up = (h, gf, gap_rel, gap_abs)
                    elif gap_abs > 0 and (free_soon is None or gf < free_soon[1]):
                        free_soon = (h, gf, gap_rel, gap_abs)
                elif gap_abs > HOLD_MARGIN and (generic_up is None or v > generic_up[2]):
                    generic_up = (h, gf, v)

        is_roulette = best.hero == roulette
        if best.skill_complete:
            verdict = "set"
        elif hold_up is not None:
            verdict = "hold"
        else:
            verdict = "develop"
            develop_next.append(best)

        roadmap.append(ClassPlan(
            cls=cls, best_hero=best.hero, best_star=best.current_star,
            best_headroom=best.headroom, shards_to_4star=best.shards_to_target,
            verdict=verdict, target_star=target_star,
            power_per_shard=best.power_per_shard, is_roulette=is_roulette,
            acquire=not best.owned,
            future_hero=hold_up[0] if hold_up else None,
            future_gen=hold_up[1] if hold_up else None,
            future_gap=hold_up[2] if hold_up else 0.0,
            future_acquisition="roulette" if hold_up else None,
            free_soon_hero=free_soon[0] if free_soon else None,
            free_soon_gen=free_soon[1] if free_soon else None,
            free_soon_gap=free_soon[2] if free_soon else 0.0,
            upcoming_hero=generic_up[0] if generic_up else None,
            upcoming_gen=generic_up[1] if generic_up else None,
            versatility=_best_other_scenario(cur, best.hero, scen),
        ))
    develop_next.sort(key=lambda a: -a.headroom)

    develop_plans = [p for p in roadmap if p.verdict == "develop"]
    free = [p for p in develop_plans if p.is_roulette]
    paid = [p for p in develop_plans if not p.is_roulette]
    paid.sort(key=lambda p: -p.power_per_shard)
    remaining = shard_budget
    for i, p in enumerate(paid, start=1):
        p.priority = i
        if remaining is None:
            p.funded = True
        elif remaining >= p.shards_to_4star:
            p.funded = True
            remaining -= p.shards_to_4star
        else:
            p.funded = False
            p.verdict = "save"
    for p in free:
        p.funded = True
    spend_order = free + paid
    total_shards_needed = sum(p.shards_to_4star for p in paid)

    spend_now = sum(p.shards_to_4star for p in paid if p.funded)
    bank_amount = (max(0, shard_budget - spend_now) if shard_budget is not None else 0)
    bank_target: Optional[tuple[str, int, Optional[int], Optional[int]]] = None
    saved = [p for p in paid if not p.funded]
    held_bests = {p.best_hero for p in roadmap if p.verdict == "hold"}
    keeper = next((a for a in heroes
                   if a.owned and a.acquisition != "cash" and a.current_star < MAX_STAR
                   and a.hero not in held_bests), None)
    if saved:
        t = saved[0]
        bank_target = (t.best_hero, t.shards_to_4star,
                       gens_to_save(t.shards_to_4star, shard_income, have=bank_amount),
                       None)
    elif profile in ("spender", "whale") and keeper is not None:
        cost = shards_to_star(builds[keeper.hero].level, MAX_STAR)
        if cost > 0:
            bank_target = ("%s → 5★" % keeper.hero, cost,
                           gens_to_save(cost, shard_income, have=bank_amount), None)
    if bank_target is None:
        upcoming = next((p for p in roadmap if p.upcoming_hero), None)
        if upcoming is not None:
            cost = STAR_SHARD_CUMULATIVE[target_star]
            afford = gens_to_save(cost, shard_income, have=bank_amount)
            arrive = max(0, (upcoming.upcoming_gen or gen) - gen)
            gens = (max(afford, arrive) if afford is not None else arrive)
            bank_target = (upcoming.upcoming_hero, cost, gens, upcoming.upcoming_gen)

    keep_over: list[tuple[str, str]] = []
    for cl in by_cls.values():
        cl = [a for a in cl if a.owned]
        if not cl:
            continue
        best = max(cl, key=lambda a: a.ceiling_value)
        newest = max(cl, key=lambda a: HERO_GENERATION.get(a.hero, 0))
        if (newest.hero != best.hero
                and HERO_GENERATION.get(newest.hero, 0) > HERO_GENERATION.get(best.hero, 0)
                and newest.current_star < target_star
                and best.ceiling_value >= newest.ceiling_value):
            keep_over.append((best.hero, newest.hero))

    def _owned_scen(m: str) -> dict[str, float]:
        return {h: v for h, v in cur.per_hero.get(m, {}).items() if h in owned}
    best_trio = best_per_class_trio(_owned_scen(scen))
    comp_by_mode = {m: best_per_class_trio(_owned_scen(m)) for m in _CORE_SCENARIOS}
    return AdvisorReport(
        gen=gen, playstyle=playstyle, scenario=scen, heroes=heroes,
        roadmap=roadmap, develop_next=develop_next, keep_over=keep_over,
        best_trio=best_trio, roulette_hero=ROULETTE_HERO_BY_GEN.get(gen),
        shard_budget=shard_budget, shard_income=int(shard_income),
        widget_target=int(widget_target), profile=profile, target_star=target_star,
        spend_order=spend_order, total_shards_needed=total_shards_needed,
        spend_now=spend_now, bank_amount=bank_amount, bank_target=bank_target,
        n_battles=getattr(cur, "n_battles", 0) + getattr(ceil, "n_battles", 0),
        curve=curve, comp_by_mode=comp_by_mode,
    )


def future_generic_picks(
    gen: int, curve_target: dict[str, dict[str, float]], lookahead: int = LOOKAHEAD,
) -> list[tuple[int, str, str, float]]:
    last = min(gen + lookahead, MAX_GENERATION)
    picks: list[tuple[int, str, str, float]] = []
    for g in range(gen + 1, last + 1):
        roul = ROULETTE_HERO_BY_GEN.get(g)
        best: Optional[tuple[str, str, float]] = None
        for cls in ("Inf", "Cav", "Arc"):
            h = _future_class_hero(g, cls)
            if not h or h == roul:
                continue
            cv = curve_target.get(cls, {})
            owned = [v for hh, v in cv.items() if HERO_GENERATION.get(hh, 0) <= gen]
            if not owned:
                continue
            edge = cv.get(h, 0.0) - max(owned)
            if edge > 0 and (best is None or edge > best[2]):
                best = (cls, h, edge)
        if best is not None:
            picks.append((g, best[0], best[1], best[2]))
    return picks


def build_shard_ledger(rep: AdvisorReport, lookahead: int = LOOKAHEAD) -> list[ShardLedgerStep]:
    if rep.shard_budget is None:
        return []
    income = int(rep.shard_income)
    cost_from_scratch = STAR_SHARD_CUMULATIVE[rep.target_star]
    queue: list[list] = []
    for p in rep.spend_order:
        if p.verdict in ("develop", "save") and not p.is_roulette:
            label = ("Get & build %s" % p.best_hero) if p.acquire else p.best_hero
            queue.append([rep.gen, label, int(p.shards_to_4star)])
    for g, _cls, hero, _edge in future_generic_picks(rep.gen, rep.curve_target, lookahead):
        queue.append([g, "%s (new gen %d)" % (hero, g), cost_from_scratch])
    queue.sort(key=lambda it: it[0])

    steps: list[ShardLedgerStep] = []
    bal = int(rep.shard_budget)
    last = min(rep.gen + lookahead, MAX_GENERATION)
    for g in range(rep.gen, last + 1):
        start = bal
        bal += income
        spends: list[tuple[str, int]] = []
        saving_for: Optional[tuple[str, int]] = None
        while queue:
            avail, label, cost = queue[0]
            if avail > g:
                break
            if cost <= bal:
                bal -= cost
                spends.append((label, cost))
                queue.pop(0)
            else:
                saving_for = (label, cost - bal)
                break
        steps.append(ShardLedgerStep(gen=g, start=start, income=income, spends=spends,
                                     end=bal, saving_for=saving_for))
    return steps


__all__ = [
    "HeroAdvice", "ClassPlan", "AdvisorReport", "AdvisorPasses", "ShardLedgerStep",
    "advise", "simulate", "advise_from_passes", "advise_from_rankings",
    "best_per_class_trio", "class_value_curve", "upgrade_efficiency",
    "future_generic_picks", "build_shard_ledger", "PLAYSTYLE_SCENARIO",
    "HOLD_MARGIN", "LOOKAHEAD",
]
