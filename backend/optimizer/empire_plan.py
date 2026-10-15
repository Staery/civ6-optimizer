"""Joint empire planner: choose WHERE to found new cities so the resulting DISTRICT
layout is as strong as possible (best combinations), not just where the land looks nice.

Quality-first design (the user explicitly prioritises pick quality over speed):

* Generate a generous pool of valid, well-spaced candidate city sites near the borders,
  pre-ranked by the settle scorer (fresh water, yields, district potential, anti-sprawl).
* Greedily add the site with the best **marginal value** = the increase in optimized
  district adjacency it produces (we actually re-run the district optimizer on the local
  cluster WITH vs WITHOUT the city, so cross-city packing and combos are measured), plus
  a fraction of the raw site quality. Stop at ``max_new`` or when no site adds value.
* The final district layout is produced by the normal optimize pipeline on all cities.

The marginal evaluation only re-optimizes the *local cluster* (the candidate plus existing
cities whose territories could touch it), so it stays accurate AND tractable.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..i18n import tr
from ..domain.hexgrid import Hex, distance
from ..domain.models import City, DistrictType, GameMap
from ..rules.modifiers import Loadout
from .empire import assign_territory, optimize_empire
from .settle import (
    MAX_SETTLE_DIST, MIN_CITY_DIST, SettleSuggestion, _score_center, _valid_center,
)
from .single_city import _clone_map

# How much raw site quality (growth/yields) counts next to district-adjacency gain.
SITE_QUALITY_WEIGHT = 0.4
DEFAULT_POOL = 14          # candidate sites to seriously consider


@dataclass
class PlannedSite:
    coord: Hex
    site_score: float        # raw settle quality
    district_gain: float     # extra optimized adjacency this city brings (incl. packing)
    total_gain: float        # district_gain + weighted site quality (ranking value)
    note: str


def _link_dist(cities: list[City]) -> int:
    return 2 * max((c.work_radius for c in cities), default=3) + 1


def _strip_built(map: GameMap, cities: list[City]) -> list[City]:
    """Copies of existing cities with already-built specialty districts removed from
    their requested list. Specialty districts are one-per-city in Civ 6, so when we plan
    the NEXT wave of cities the marginal value must measure only NEW districts — the built
    ones already sit on the map and act as fixed adjacency anchors for the newcomers
    (cross-city packing). This mirrors what the final optimize pass locks, so the site
    ranking optimizes the same problem the player will actually build."""
    owner_of = assign_territory(map, cities)
    built: dict[int, set[DistrictType]] = {i: set() for i in range(len(cities))}
    for h, ci in owner_of.items():
        t = map.get(h)
        if t is not None and t.district not in (None, DistrictType.CITY_CENTER):
            built[ci].add(t.district)
    return [
        City(name=c.name, center=c.center, work_radius=c.work_radius,
             population=c.population,
             requested=[d for d in c.requested if d not in built[i]])
        for i, c in enumerate(cities)
    ]


def _candidate_sites(map: GameMap, cities: list[City], loadout: Loadout,
                     settlers: list[Hex], rivals: list[tuple[Hex, int]],
                     max_dist: int, pool: int,
                     blocked_centers: list[Hex] | None = None) -> list[SettleSuggestion]:
    existing = [c.center for c in cities]
    own = [(c.center, max(1, c.population)) for c in cities]
    anchors = existing or list(settlers or [])
    # forbid founding within MIN_CITY_DIST of any city center — yours OR foreign (incl.
    # city-states / free cities, carried in blocked_centers).
    spacing = existing + list(blocked_centers or [])
    cand: list[SettleSuggestion] = []
    for h in list(map.tiles):
        if not _valid_center(map, h):
            continue
        if any(distance(h, c) < MIN_CITY_DIST for c in spacing):
            continue
        if anchors and not any(distance(h, c) <= max_dist for c in anchors):
            continue
        cand.append(_score_center(map, h, existing, loadout.civ, own, rivals, home=anchors))
    cand.sort(key=lambda s: s.score, reverse=True)
    spaced: list[SettleSuggestion] = []
    for s in cand:
        if all(distance(s.coord, p.coord) >= MIN_CITY_DIST for p in spaced):
            spaced.append(s)
        if len(spaced) >= pool:
            break
    return spaced


def plan_empire(map: GameMap, cities: list[City], loadout: Loadout,
                settlers: list[Hex] | None = None,
                rival_cities: list[tuple[Hex, int]] | None = None,
                max_new: int = 5, max_dist: int = MAX_SETTLE_DIST,
                requested: list[DistrictType] | None = None,
                blocked_centers: list[Hex] | None = None,
                ) -> tuple[list[PlannedSite], list[City]]:
    """Return (chosen new sites, full city list = existing + new).

    ``blocked_centers`` are foreign city centers (rivals, city-states, free cities) that
    new sites must stay MIN_CITY_DIST away from — Civ 6 forbids founding too close to ANY
    city, not just your own.
    """
    requested = list(requested or [])
    rivals = rival_cities or []
    blocked = list(blocked_centers or [])
    work = _clone_map(map)                      # existing centers already carry city_center
    link = _link_dist(cities) if cities else 7
    # need at least as many spaced candidates as cities we want to plant, plus headroom
    # so the greedy picker has real choice at every step (each pick consumes one site).
    pool = max(DEFAULT_POOL, max_new + 8)
    candidates = _candidate_sites(work, cities, loadout, settlers or [], rivals, max_dist,
                                  pool, blocked_centers=blocked)

    chosen: list[PlannedSite] = []
    # plan around what's already built: existing cities keep only their UN-built requests,
    # while their built districts remain on `work` as fixed adjacency anchors.
    current = _strip_built(work, cities)
    next_idx = len(cities) + 1

    def district_total(city_list: list[City]) -> float:
        if not city_list:
            return 0.0
        # fast ranking pass — the final layout is recomputed at full quality downstream
        return optimize_empire(work, city_list, loadout, fast=True).total_score

    for _ in range(max_new):
        before_cache: dict[frozenset, float] = {}
        best = None  # (total_gain, district_gain, suggestion)
        for s in candidates:
            if any(distance(s.coord, c.center) < MIN_CITY_DIST for c in current):
                continue
            local = [c for c in current if distance(c.center, s.coord) <= link]
            key = frozenset(c.center for c in local)
            before = before_cache.get(key)
            if before is None:
                before = district_total(local)
                before_cache[key] = before
            trial = City(name=tr("План {n}", n=next_idx), center=s.coord,
                         population=6, requested=list(requested))
            saved = work.get(s.coord).district
            work.get(s.coord).district = DistrictType.CITY_CENTER   # so neighbours see a center
            after = district_total(local + [trial])
            work.get(s.coord).district = saved
            dgain = after - before
            total = dgain + SITE_QUALITY_WEIGHT * s.score
            if best is None or total > best[0]:
                best = (total, dgain, s)
        if best is None:
            break
        total, dgain, s = best
        # always take the first city; afterwards stop if a site adds no real value
        if chosen and total <= 0:
            break
        chosen.append(PlannedSite(s.coord, s.score, round(dgain, 2), round(total, 2), s.note))
        work.get(s.coord).district = DistrictType.CITY_CENTER       # commit the center
        current.append(City(name=tr("План {n}", n=next_idx), center=s.coord,
                            population=6, requested=list(requested)))
        next_idx += 1
        candidates = [c for c in candidates if distance(c.coord, s.coord) >= MIN_CITY_DIST]

    return chosen, current
