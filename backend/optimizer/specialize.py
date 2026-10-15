"""Assign each city a ROLE and a focused district set — "city specialization".

In Civ 6 building every district in every city is harmful: the district limit scales
with population ((pop+2)//3) and production is scarce, so cities should be narrowly
specialised toward the chosen victory. Pros build by a "pyramid":

* base districts in EVERY city — economy (Commercial Hub / Harbor) + the victory's
  primary district (Campus for science, Theater for culture, …);
* secondary districts in 30–50% of cities — Holy Site, Theater, Encampment, Preserve;
* unique districts ONCE per empire — Government Plaza and Diplomatic Quarter;
* yet the EMPIRE should still have ≥1 of each key district (faith, gold, amenities,
  strategic resources, Spaceport) for the mechanics they unlock.

`assign_specialization` turns the player's cities + map + victory into per-city district
sets, choosing the best-suited city for each role. The result feeds the normal optimizer
(which already accepts a per-city `requested`); infrastructure (Aqueduct/Dam/Canal) is
still added by ``app._augment_districts`` and the build ORDER is phased by population in
``app._annotate_build_order``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.hexgrid import within_radius
from ..domain.models import City, DistrictType as D, GameMap, Terrain, YieldType
from ..rules.adjacency import can_place, raw_adjacency
from ..rules.city_limits import counts_toward_cap
from ..rules.modifiers import FOCUS_DISTRICTS, Loadout
from .empire import assign_territory

# Specialty districts the planner reasons about (capped, victory-relevant).
ECONOMY = (D.HARBOR, D.COMMERCIAL_HUB)
SECONDARY = (D.HOLY_SITE, D.THEATER, D.ENCAMPMENT, D.PRESERVE)
# Key types the empire wants at least one of (coverage). Economy is satisfied by EITHER
# Commercial Hub or Harbor, handled specially.
KEY_COVERAGE = (D.CAMPUS, D.HOLY_SITE, D.THEATER, D.INDUSTRIAL_ZONE,
                D.ENCAMPMENT, D.ENTERTAINMENT, D.PRESERVE)

ROLE_LABEL = {
    "capital": "Столица", "production": "Производство", "science": "Наука",
    "culture": "Культура", "faith": "Религия", "gold": "Золото",
    "military": "Военный", "coastal": "Морской", "general": "Универсальный",
}
ROLE_REASON = {
    "capital": "главный город — наука/чудеса и уникальные районы",
    "production": "промышленность — здесь Чудеса света и юниты",
    "science": "наука — Кампус как ядро",
    "culture": "культура — Театральная площадь",
    "faith": "вера — Святое место",
    "gold": "экономика — Центр коммерции",
    "military": "стратег. ресурсы и полководцы — Военный лагерь",
    "coastal": "морской — Гавань и торговые пути",
    "general": "база: экономика + опорный район",
}

_VICTORY_BY_YIELD = {
    YieldType.SCIENCE: "science", YieldType.CULTURE: "culture",
    YieldType.FAITH: "religious", YieldType.GOLD: "gold",
    YieldType.PRODUCTION: "domination",
}


@dataclass
class CityRole:
    name: str
    role: str
    role_label: str
    reason: str
    districts: list[D] = field(default_factory=list)


@dataclass
class Specialization:
    cities: dict[str, CityRole]
    uniques: dict[str, str]            # government_plaza / diplomatic_quarter -> city name
    coverage: dict[str, int]          # district value -> how many cities hold it


# Districts surfaced in the empire-coverage summary.
COVERAGE_REPORT = (D.CAMPUS, D.HOLY_SITE, D.THEATER, D.COMMERCIAL_HUB, D.HARBOR,
                   D.INDUSTRIAL_ZONE, D.ENCAMPMENT, D.ENTERTAINMENT, D.PRESERVE,
                   D.GOVERNMENT_PLAZA, D.DIPLOMATIC_QUARTER)


def _victory(loadout: Loadout) -> str:
    if loadout.victory:
        return loadout.victory
    w = loadout.weights or {}
    if w:
        best_y = max(w, key=lambda y: w.get(y, 1.0))
        return _VICTORY_BY_YIELD.get(best_y, "science")
    return "science"


def _victory_primary(victory: str, allowed: set[D]) -> D | None:
    for name in FOCUS_DISTRICTS.get(victory, ()):
        d = D(name)
        if d in allowed:
            return d
    return None


def _production_potential(map: GameMap, city: City) -> float:
    """Heuristic Industrial-Zone value beyond raw adjacency: hills/mines/quarries plus a
    bonus when an Aqueduct/Dam is possible (those give the IZ +2 once built)."""
    score = 0.0
    aqueduct_possible = False
    for hx in within_radius(city.center, city.work_radius):
        t = map.get(hx)
        if t is None:
            continue
        if t.hills or t.improvement.value in ("mine", "quarry"):
            score += 0.5
        if t.terrain is Terrain.MOUNTAIN or t.is_fresh_water:
            aqueduct_possible = True
    if aqueduct_possible:
        score += 1.0
    return score


def _suitability(map: GameMap, city: City, dtype: D, loadout: Loadout) -> float | None:
    """Best achievable value of ``dtype`` in the city's territory, or None if it can't be
    placed anywhere. Yield districts use best raw adjacency; the Industrial Zone adds its
    production potential; yield-less districts (Encampment/Entertainment/…) score 0 but a
    non-None means 'placeable here'."""
    best: float | None = None
    placeable = False
    for hx in within_radius(city.center, city.work_radius):
        if hx == city.center:
            continue
        t = map.get(hx)
        if t is None or t.district is not None:
            continue
        if not can_place(map, hx, dtype, city, loadout):
            continue
        placeable = True
        v = raw_adjacency(map, hx, dtype, loadout.civ if loadout else None)
        if best is None or v > best:
            best = v
    if not placeable:
        return None
    val = best or 0.0
    if dtype is D.INDUSTRIAL_ZONE:
        val += _production_potential(map, city)
    return val


def _role_of(idx: int, ds: set[D]) -> tuple[str, str, str]:
    if idx == 0:
        role = "capital"
    elif D.GOVERNMENT_PLAZA in ds or D.INDUSTRIAL_ZONE in ds:
        role = "production"
    elif D.CAMPUS in ds:
        role = "science"
    elif D.THEATER in ds:
        role = "culture"
    elif D.HOLY_SITE in ds:
        role = "faith"
    elif D.ENCAMPMENT in ds:
        role = "military"
    elif D.HARBOR in ds:
        role = "coastal"
    elif D.COMMERCIAL_HUB in ds:
        role = "gold"
    else:
        role = "general"
    return role, ROLE_LABEL[role], ROLE_REASON[role]


def assign_specialization(map: GameMap, cities: list[City], loadout: Loadout,
                          pool) -> Specialization:
    """Per-city role + focused district list. ``pool`` is the allowed district types
    (the UI checkboxes); only these are ever assigned, and coverage is guaranteed only
    among them."""
    n = len(cities)
    if n == 0:
        return {}
    allowed = {d if isinstance(d, D) else D(d) for d in pool}
    if not allowed:
        allowed = {D.CAMPUS, D.HOLY_SITE, D.THEATER, D.COMMERCIAL_HUB,
                   D.HARBOR, D.INDUSTRIAL_ZONE}
    # the tool always wants ONE Government Plaza per empire (it's not a pool checkbox).
    allowed = allowed | {D.GOVERNMENT_PLAZA}
    victory = _victory(loadout)

    # already-built specialty districts: respect them (keep in the plan as anchors) and
    # count toward coverage / one-per-empire uniques.
    owner_of = assign_territory(map, cities)
    built_global: set[D] = set()
    built_city: dict[int, set[D]] = {i: set() for i in range(n)}
    for h, ci in owner_of.items():
        t = map.get(h)
        if t is not None and t.district not in (None, D.CITY_CENTER):
            built_global.add(t.district)
            built_city[ci].add(t.district)

    suit_types = set(ECONOMY) | set(SECONDARY) | {
        D.CAMPUS, D.INDUSTRIAL_ZONE, D.ENTERTAINMENT, D.WATER_PARK,
        D.GOVERNMENT_PLAZA, D.DIPLOMATIC_QUARTER, D.SPACEPORT,
    }
    suit = [{d: _suitability(map, cities[i], d, loadout) for d in suit_types}
            for i in range(n)]

    def can(i: int, d: D) -> bool:
        return suit[i].get(d) is not None

    def _load(i: int) -> int:                # how many specialty districts already assigned
        return sum(1 for d in sets[i] if counts_toward_cap(d))

    def assign_top(d: D, frac: float) -> None:
        """Give district ``d`` to ~round(frac*n) cities — best-suited, but load-aware so
        roles spread across the empire instead of piling onto one or two cities."""
        if d not in allowed:
            return
        k = max(1, round(frac * n))
        ranked = sorted((i for i in range(n) if can(i, d) and d not in sets[i]),
                        key=lambda i: suit[i][d] - 0.4 * _load(i), reverse=True)
        for i in ranked[:k]:
            sets[i].add(d)

    sets: list[set[D]] = [set(built_city[i]) for i in range(n)]   # respect built

    # --- production cities: top ~40% by Industrial-Zone potential ----------------
    primary = _victory_primary(victory, allowed) or D.CAMPUS
    iz_ok = [i for i in range(n) if D.INDUSTRIAL_ZONE in allowed and can(i, D.INDUSTRIAL_ZONE)]
    iz_rank = sorted(iz_ok, key=lambda i: suit[i][D.INDUSTRIAL_ZONE], reverse=True)
    prod = set(iz_rank[:max(1, round(0.4 * n))]) if iz_rank else set()
    # Leaders whose kit rewards an Industrial Zone in EVERY city (not just top producers):
    #   Abraham Lincoln (America)   — empire-wide Loyalty + a free unit per Industrial Zone.
    #   Victoria "Age of Steam" (England) — +10% Production per Industrial Zone building.
    if getattr(loadout, "leader", "") in ("abraham_lincoln", "victoria_steam"):
        prod = set(iz_ok)

    # --- base in every city: ONE economy district + ONE engine -------------------
    for i in range(n):
        if D.HARBOR in allowed and can(i, D.HARBOR):
            sets[i].add(D.HARBOR)                     # coastal -> Harbor (trade + cheap)
        elif D.COMMERCIAL_HUB in allowed and can(i, D.COMMERCIAL_HUB):
            sets[i].add(D.COMMERCIAL_HUB)             # inland -> Commercial Hub
        if i in prod:
            sets[i].add(D.INDUSTRIAL_ZONE)            # production city -> Industrial Zone
        # the capital is a dual hub (also gets the primary); other cities get IZ OR primary
        if (i == 0 or i not in prod) and primary in allowed and can(i, primary):
            sets[i].add(primary)                      # the victory's primary district

    # --- secondary specialists: each type to its best ~30% of cities -------------
    for d in SECONDARY:
        if d == primary:                              # already an engine in most cities
            continue
        assign_top(d, 0.3)
    # --- amenities: Entertainment (or Water Park) in ~1 of every 3 cities ---------
    amen = D.ENTERTAINMENT if D.ENTERTAINMENT in allowed else (
        D.WATER_PARK if D.WATER_PARK in allowed else None)
    if amen is not None:
        by_pop = sorted(range(n), key=lambda i: cities[i].population, reverse=True)
        picked = 0
        for i in by_pop:
            use = amen
            if amen is D.ENTERTAINMENT and not can(i, D.ENTERTAINMENT) and D.WATER_PARK in allowed and can(i, D.WATER_PARK):
                use = D.WATER_PARK
            if can(i, use):
                sets[i].add(use)
                picked += 1
            if picked >= max(1, round(n / 3.5)):
                break

    # --- unique districts: one per empire, best city -----------------------------
    uniques: dict[str, str] = {}
    if D.GOVERNMENT_PLAZA in allowed and D.GOVERNMENT_PLAZA not in built_global:
        order = sorted(range(n), key=lambda i: suit[i].get(D.INDUSTRIAL_ZONE) or -1, reverse=True)
        for i in order:
            if can(i, D.GOVERNMENT_PLAZA):
                sets[i].add(D.GOVERNMENT_PLAZA); uniques["government_plaza"] = cities[i].name
                break
    elif D.GOVERNMENT_PLAZA in built_global:
        uniques["government_plaza"] = "построено"
    if D.DIPLOMATIC_QUARTER in allowed and D.DIPLOMATIC_QUARTER not in built_global:
        for i in [0, *range(1, n)]:                  # prefer the capital
            if can(i, D.DIPLOMATIC_QUARTER):
                sets[i].add(D.DIPLOMATIC_QUARTER); uniques["diplomatic_quarter"] = cities[i].name
                break
    elif D.DIPLOMATIC_QUARTER in built_global:
        uniques["diplomatic_quarter"] = "построено"

    # Spaceport for a Science victory: one in the strongest production city.
    if victory == "science" and D.SPACEPORT in allowed and D.SPACEPORT not in built_global:
        order = sorted(range(n), key=lambda i: suit[i].get(D.INDUSTRIAL_ZONE) or -1, reverse=True)
        for i in order:
            if _sp_tile(map, cities[i], loadout) is not None:
                sets[i].add(D.SPACEPORT); break

    # --- coverage: ensure ≥1 of each key type somewhere in the empire ------------
    economy_present = any((D.COMMERCIAL_HUB in s or D.HARBOR in s) for s in sets) \
        or D.COMMERCIAL_HUB in built_global or D.HARBOR in built_global
    if not economy_present:
        for d in (D.COMMERCIAL_HUB, D.HARBOR):
            cand = [i for i in range(n) if d in allowed and can(i, d)]
            if cand:
                sets[max(cand, key=lambda i: suit[i][d])].add(d); break
    for d in KEY_COVERAGE:
        if d not in allowed:
            continue
        if d in built_global or any(d in s for s in sets):
            continue
        cand = [i for i in range(n) if can(i, d)]
        if cand:
            sets[max(cand, key=lambda i: (suit[i].get(d) or 0.0))].add(d)

    # --- assemble result ---------------------------------------------------------
    enum_order = list(D)
    out: dict[str, CityRole] = {}
    for i, c in enumerate(cities):
        role, label, reason = _role_of(i, sets[i])
        ds = sorted(sets[i] & (allowed | built_city[i]), key=enum_order.index)
        out[c.name] = CityRole(c.name, role, label, reason, ds)
    coverage = {d.value: sum(1 for r in out.values() if d in r.districts)
                for d in COVERAGE_REPORT}
    return Specialization(out, uniques, coverage)


def _sp_tile(map: GameMap, city: City, loadout: Loadout):
    for hx in within_radius(city.center, city.work_radius):
        if hx == city.center:
            continue
        if can_place(map, hx, D.SPACEPORT, city, loadout):
            return hx
    return None
