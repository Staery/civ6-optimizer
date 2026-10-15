"""Empire-scale (multi-city) joint district optimizer.

Civ 6 adjacency does not care which city owns a neighbouring district, so districts
on the *border* between two cities can boost each other. This optimizer therefore
places the requested districts of **all** cities at once on a shared board, so
cross-city packing is exploited.

Territory model: each non-foreign tile is assigned to the nearest of the player's
city centers (within that city's work radius). Tiles marked foreign/occupied
(``owner_city`` starting with ``rival``) are excluded. This mirrors Civ 6 borders
closely enough for planning without forcing the user to paint every tile's owner.

Search reuses the same engine idea as the single-city optimizer (greedy + local
search + random restarts), but keyed by *slot* (city, district) so the same
district type can appear in several cities.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..domain.hexgrid import Hex, distance, within_radius
from ..domain.models import City, DistrictType, GameMap, Yields, add_yields
from ..rules.adjacency import (
    adjacency_yield,
    can_place,
    displayed_adjacency,
    raw_adjacency,
    weighted_score,
)
from ..rules.districts import DISTRICTS
from ..rules.modifiers import Loadout
from ..rules.tile_yields import opportunity_cost
from .single_city import EXACT_LEAF_BUDGET, Placement, _clone_map, _layout_score

# Empire instances are larger than single cities. We prune each slot's candidate
# tiles to the most promising ones (keeps speed and quality), then run restarts.
RESTARTS = 14
CANDIDATE_CAP = 14

# Regional-building overlap (community scheme): a Factory/Power Plant (Industrial
# Zone) or Zoo/Stadium/Aquarium (Entertainment Complex / Water Park) reaches every
# City Center within 6 tiles and is *shared* by those cities. Pure per-tile adjacency
# can't see this, so we add a small empire-scale bonus for such districts placed
# where they also cover OTHER cities. (Same-type buildings don't stack, so we only
# reward distinct extra cities covered.)
REGIONAL_RANGE = 6
REGIONAL_DISTRICTS = frozenset(
    {DistrictType.INDUSTRIAL_ZONE, DistrictType.ENTERTAINMENT, DistrictType.WATER_PARK}
)
REGIONAL_CAP = 4  # diminishing returns past a handful of covered cities


def _regional_overlap(placed: dict[Hex, DistrictType], centers: list[Hex], loadout: Loadout) -> float:
    """Empire-scale bonus for shared regional buildings (Factory/Zoo within 6 tiles)."""
    if loadout.region_weight <= 0 or len(centers) < 2:
        return 0.0
    total = 0.0
    for h, d in placed.items():
        if d not in REGIONAL_DISTRICTS:
            continue
        covered = sum(1 for c in centers if distance(h, c) <= REGIONAL_RANGE)
        total += min(max(covered - 1, 0), REGIONAL_CAP)  # value only the *extra* cities
    return loadout.region_weight * total


def _rank_cap(map: GameMap, tiles: list[Hex], dtype: DistrictType, cap: int = CANDIDATE_CAP) -> list[Hex]:
    """Keep only the most promising candidate tiles for a district slot."""
    if len(tiles) <= cap:
        return tiles

    def score(h: Hex) -> float:
        base = raw_adjacency(map, h, dtype)  # terrain/existing-district sources
        occ = sum(1 for n in map.neighbors(h)
                  if n.terrain.is_land and n.terrain.value != "mountain")
        return base + 0.5 * occ  # reward packing potential (occupiable neighbours)

    return sorted(tiles, key=score, reverse=True)[:cap]


def is_foreign(owner: str | None) -> bool:
    return owner is not None and str(owner).startswith("rival")


@dataclass
class EmpireResult:
    placements_by_city: dict[str, list[Placement]]
    total_score: float
    total_yields: Yields
    method: str
    optimal: bool
    unplaceable: dict[str, list[DistrictType]] = field(default_factory=dict)
    territory: dict[str, int] = field(default_factory=dict)
    total_opportunity: float = 0.0
    total_regional: float = 0.0


def assign_territory(map: GameMap, cities: list[City]) -> dict[Hex, int]:
    """Map each ownable tile to the index of its nearest city (within work radius)."""
    owner_of: dict[Hex, int] = {}
    for ci, c in enumerate(cities):
        for h in within_radius(c.center, c.work_radius):
            t = map.get(h)
            if t is None or is_foreign(t.owner_city):
                continue
            d = distance(h, c.center)
            prev = owner_of.get(h)
            if prev is None or d < distance(h, cities[prev].center):
                owner_of[h] = ci
    return owner_of


# --- indexed search (slots = (city_index, district)) ----------------------------

def _placed_dict(assignment: dict[int, Hex], dtypes: list[DistrictType]) -> dict[Hex, DistrictType]:
    return {h: dtypes[i] for i, h in assignment.items()}


def _greedy(map, loadout, dtypes, legal, rng=None, score=_layout_score):
    n = len(dtypes)
    order = sorted(range(n), key=lambda i: len(legal[i]))
    if rng is not None:
        rng.shuffle(order)
    assignment: dict[int, Hex] = {}
    used: set[Hex] = set()
    for i in order:
        best_h, best_gain = None, float("-inf")
        choices = legal[i][:]
        if rng is not None:
            rng.shuffle(choices)
        for h in choices:
            if h in used:
                continue
            map.get(h).district = dtypes[i]
            gain = score(map, _placed_dict({**assignment, i: h}, dtypes), loadout)
            map.get(h).district = None
            if gain > best_gain:
                best_gain, best_h = gain, h
        if best_h is not None:
            assignment[i] = best_h
            used.add(best_h)
            map.get(best_h).district = dtypes[i]
    return assignment


def _local_search(map, loadout, dtypes, legal, assignment, score=_layout_score,
                  max_passes: int = 10_000, do_swaps: bool = True):
    n = len(dtypes)
    improved = True
    passes = 0
    while improved and passes < max_passes:
        passes += 1
        improved = False
        used = set(assignment.values())
        base = score(map, _placed_dict(assignment, dtypes), loadout)

        for i in range(n):
            cur = assignment.get(i)        # may be None: slot couldn't get a tile yet (high
            #                                contention) — then this is a "fill" move attempt.
            for h in legal[i]:
                if h == cur or h in used:
                    continue
                if cur is not None:
                    map.get(cur).district = None
                map.get(h).district = dtypes[i]
                trial = dict(assignment); trial[i] = h
                if score(map, _placed_dict(trial, dtypes), loadout) > base + 1e-9:
                    assignment[i] = h
                    improved = True
                    break
                map.get(h).district = None
                if cur is not None:
                    map.get(cur).district = dtypes[i]
            if improved:
                break
        if improved or not do_swaps:
            continue

        for i in range(n):
            for j in range(i + 1, n):
                h1, h2 = assignment.get(i), assignment.get(j)
                if h1 is None or h2 is None:           # skip unassigned slots
                    continue
                if h2 not in legal[i] or h1 not in legal[j]:
                    continue
                map.get(h1).district = dtypes[j]
                map.get(h2).district = dtypes[i]
                trial = dict(assignment); trial[i], trial[j] = h2, h1
                if score(map, _placed_dict(trial, dtypes), loadout) > base + 1e-9:
                    assignment[i], assignment[j] = h2, h1
                    improved = True
                    break
                map.get(h1).district = dtypes[i]
                map.get(h2).district = dtypes[j]
            if improved:
                break
    return assignment


def _random_assignment(rng, dtypes, legal):
    order = list(range(len(dtypes)))
    rng.shuffle(order)
    assignment: dict[int, Hex] = {}
    used: set[Hex] = set()
    for i in order:
        free = [h for h in legal[i] if h not in used]
        if free:
            h = rng.choice(free)
            assignment[i] = h
            used.add(h)
    return assignment


def _set_map(map, dtypes, assignment):
    for i, h in assignment.items():
        map.get(h).district = dtypes[i]


def _search_budget(slots: int) -> tuple[int, int, bool, int]:
    """(restarts, max_local_passes, do_swaps, candidate_cap) scaled to problem size.

    The local search is ~O(passes·slots²·score) and swaps add another slots² factor, so
    for big clusters we trim restarts/passes/swaps to keep planning bounded (seconds, not
    hours) while greedy + a few local passes still gives a strong layout.
    """
    if slots <= 14:
        return RESTARTS, 10_000, True, CANDIDATE_CAP
    if slots <= 30:
        return 6, 8, True, 12
    if slots <= 60:
        return 3, 5, True, 10
    return 2, 4, False, 9


def _optimize_cluster(map: GameMap, cities: list[City], loadout: Loadout,
                      fast: bool = False) -> EmpireResult:
    work = _clone_map(map)
    owner_of = assign_territory(work, cities)

    territory = {c.name: 0 for c in cities}
    for ci in owner_of.values():
        territory[cities[ci].name] += 1

    # build slots
    slot_city: list[int] = []
    dtypes: list[DistrictType] = []
    legal: list[list[Hex]] = []
    unplaceable: dict[str, list[DistrictType]] = {c.name: [] for c in cities}
    # provisional slot count to size the search budget (candidate cap included)
    n_slots = sum(len(c.requested) for c in cities)
    restarts, max_passes, do_swaps, cand_cap = _search_budget(n_slots)
    if fast:                       # planning-phase ranking: cheap, relative quality is enough
        restarts, max_passes, do_swaps, cand_cap = 0, 2, False, min(cand_cap, 8)

    for ci, c in enumerate(cities):
        terr = [h for h, o in owner_of.items() if o == ci and h != c.center]
        for d in c.requested:
            tiles = [h for h in terr
                     if work.get(h).district is None and can_place(work, h, d, c, loadout)]
            if tiles:
                slot_city.append(ci)
                dtypes.append(d)
                legal.append(_rank_cap(work, tiles, d, cap=cand_cap))
            else:
                unplaceable[c.name].append(d)

    if not dtypes:
        return EmpireResult({c.name: [] for c in cities}, 0.0, {}, "none", True,
                            unplaceable, territory)

    # Objective = per-tile adjacency (incl. cross-city packing & opportunity cost)
    # PLUS the empire-scale regional-overlap synergy.
    centers = [c.center for c in cities]

    def score(m, placed, lo):
        return _layout_score(m, placed, lo) + _regional_overlap(placed, centers, lo)

    rng = random.Random(20250603)

    best = _greedy(work, loadout, dtypes, legal, score=score)
    best = _local_search(work, loadout, dtypes, legal, best, score=score,
                         max_passes=max_passes, do_swaps=do_swaps)
    best_score = score(work, _placed_dict(best, dtypes), loadout)

    for _ in range(restarts):
        cand = _random_assignment(rng, dtypes, legal)
        if len(cand) < len(dtypes):
            continue
        # reset our placements then apply candidate
        for t in work.tiles.values():
            if t.district in dtypes and t.coord not in cand.values():
                t.district = None
        _set_map(work, dtypes, cand)
        cand = _local_search(work, loadout, dtypes, legal, cand, score=score,
                             max_passes=max_passes, do_swaps=do_swaps)
        sc = score(work, _placed_dict(cand, dtypes), loadout)
        if sc > best_score + 1e-9:
            best, best_score = cand, sc

    # finalize map state
    for t in work.tiles.values():
        if t.district in dtypes and t.coord not in best.values():
            t.district = None
    _set_map(work, dtypes, best)

    # slots that never got a tile (too much contention for the territory) -> report them
    # as unplaceable rather than silently dropping them.
    for i in range(len(dtypes)):
        if i not in best:
            unplaceable[cities[slot_city[i]].name].append(dtypes[i])

    # build per-city placements
    by_city: dict[str, list[Placement]] = {c.name: [] for c in cities}
    total_yields: Yields = {}
    total_score = 0.0
    total_opp = 0.0
    for i, h in best.items():
        d = dtypes[i]
        y = adjacency_yield(work, h, d, loadout)
        sc = weighted_score(y, loadout)
        oc = opportunity_cost(work.get(h), loadout)
        ddef = DISTRICTS[d]
        disp = displayed_adjacency(y.get(ddef.primary_yield, 0.0)) if ddef.primary_yield else 0
        by_city[cities[slot_city[i]].name].append(Placement(d, h, y, disp, sc, oc))
        total_yields = add_yields(total_yields, y)
        total_score += sc
        total_opp += oc

    for name in by_city:
        by_city[name].sort(key=lambda p: p.score, reverse=True)

    regional = _regional_overlap(_placed_dict(best, dtypes), centers, loadout)

    return EmpireResult(by_city, total_score, total_yields,
                        "greedy+local+restarts", False, unplaceable, territory,
                        round(total_opp, 3), round(regional, 3))


def _cluster_cities(cities: list[City], link_dist: int) -> list[list[int]]:
    """Group city indices into connected components linked when centers are within
    ``link_dist`` (i.e. their districts could possibly be adjacent). Union-find."""
    n = len(cities)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if distance(cities[i].center, cities[j].center) <= link_dist:
                parent[find(j)] = find(i)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def optimize_empire(map: GameMap, cities: list[City], loadout: Loadout | None = None,
                    fast: bool = False) -> EmpireResult:
    """Joint multi-city optimizer. Cross-city adjacency only matters between cities whose
    territories touch, so we split far-apart cities into independent clusters and solve
    each separately — this keeps planning tractable up to 20+ cities.

    ``fast`` trims the search (used by the empire planner to rank candidate sites quickly;
    the final layout is computed at full quality)."""
    loadout = loadout or Loadout()
    if len(cities) <= 1:
        return _optimize_cluster(map, cities, loadout, fast=fast)

    # districts of two cities can be adjacent only if centers are within 2*work_radius+1
    link = 2 * max((c.work_radius for c in cities), default=3) + 1
    clusters = _cluster_cities(cities, link)
    if len(clusters) == 1:
        return _optimize_cluster(map, cities, loadout, fast=fast)

    by_city: dict[str, list[Placement]] = {}
    total_yields: Yields = {}
    total_score = total_opp = total_regional = 0.0
    unplaceable: dict[str, list[DistrictType]] = {}
    territory: dict[str, int] = {}
    for idxs in clusters:
        sub = [cities[i] for i in idxs]
        r = _optimize_cluster(map, sub, loadout, fast=fast)
        by_city.update(r.placements_by_city)
        total_yields = add_yields(total_yields, r.total_yields)
        total_score += r.total_score
        total_opp += r.total_opportunity
        total_regional += r.total_regional
        unplaceable.update(r.unplaceable)
        territory.update(r.territory)
    return EmpireResult(by_city, round(total_score, 3), total_yields,
                        f"clustered({len(clusters)})+greedy+local", False,
                        unplaceable, territory, round(total_opp, 3), round(total_regional, 3))
