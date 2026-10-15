"""Single-city district placement optimizer.

The objective is non-separable: a district gains +0.5 for every adjacent district,
so placements interact. We therefore:

1. build a strong solution with **greedy + local search + random restarts**
   (always available, fast, near-optimal), and
2. when the instance is small, certify the optimum with an **exact full
   enumeration** of injective district->tile assignments (no pruning, so it is
   correct by construction; runs only within a leaf budget).

No third-party solver is required. OR-Tools could replace step (2) for very large
instances later, but for a single city the search space is tiny.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from ..domain.hexgrid import Hex, within_radius
from ..domain.models import City, DistrictType, GameMap, Yields, add_yields
from ..rules.adjacency import (
    adjacency_yield,
    can_place,
    displayed_adjacency,
    weighted_score,
)
from ..rules.districts import DISTRICTS, resolve_def
from ..rules.modifiers import Loadout
from ..rules.tile_yields import opportunity_cost

# Run the exact enumeration only when the (over-)estimated number of leaves
# (= product of per-district candidate counts) is at most this.
EXACT_LEAF_BUDGET = 1_500_000
RESTARTS = 24


@dataclass
class Placement:
    district: DistrictType
    coord: Hex
    yields: Yields = field(default_factory=dict)
    displayed: int = 0          # in-game shown adjacency (floor of primary yield)
    score: float = 0.0          # weighted adjacency value (gross)
    opportunity: float = 0.0    # weighted base yield given up by covering the tile


@dataclass
class CityResult:
    city: str
    placements: list[Placement]
    total_score: float
    total_yields: Yields
    optimal: bool
    method: str
    unplaceable: list[DistrictType] = field(default_factory=list)
    total_opportunity: float = 0.0


def _clone_map(map: GameMap) -> GameMap:
    return GameMap(tiles={h: copy.copy(t) for h, t in map.tiles.items()}, ruleset=map.ruleset)


def _candidate_hexes(map: GameMap, city: City) -> list[Hex]:
    out: list[Hex] = []
    for h in within_radius(city.center, city.work_radius):
        if h == city.center:
            continue
        t = map.get(h)
        if t is None:
            continue
        if t.owner_city not in (None, city.name):
            continue  # owned by a different city
        out.append(h)
    return out


def _legal_tiles(map: GameMap, city: City, hexes: list[Hex], dtype: DistrictType,
                 loadout: Loadout | None = None) -> list[Hex]:
    return [h for h in hexes
            if map.get(h).district is None and can_place(map, h, dtype, city, loadout)]


def _layout_score(map: GameMap, placed: dict[Hex, DistrictType], loadout: Loadout) -> float:
    """Net objective: weighted adjacency MINUS the opportunity cost of each tile."""
    total = 0.0
    for h, d in placed.items():
        total += weighted_score(adjacency_yield(map, h, d, loadout), loadout)
        total -= opportunity_cost(map.get(h), loadout)
    return total


def _apply(map: GameMap, our_districts: set[DistrictType], assignment: dict[DistrictType, Hex]) -> None:
    """Make the map reflect exactly ``assignment`` for our districts."""
    for t in map.tiles.values():
        if t.district in our_districts:
            t.district = None
    for d, h in assignment.items():
        map.get(h).district = d


# --- construction heuristics ----------------------------------------------------

def _greedy(
    map: GameMap,
    loadout: Loadout,
    districts: list[DistrictType],
    legal: dict[DistrictType, list[Hex]],
    rng: random.Random | None = None,
) -> dict[DistrictType, Hex]:
    order = sorted(districts, key=lambda d: len(legal[d]))
    if rng is not None:
        rng.shuffle(order)
    assignment: dict[DistrictType, Hex] = {}
    used: set[Hex] = set()
    for d in order:
        best_h, best_gain = None, float("-inf")
        choices = legal[d][:]
        if rng is not None:
            rng.shuffle(choices)
        for h in choices:
            if h in used:
                continue
            map.get(h).district = d
            placed = {assignment[dd]: dd for dd in assignment}
            placed[h] = d
            gain = _layout_score(map, placed, loadout)
            map.get(h).district = None
            if gain > best_gain:
                best_gain, best_h = gain, h
        if best_h is not None:
            assignment[d] = best_h
            used.add(best_h)
            map.get(best_h).district = d
    return assignment


def _local_search(
    map: GameMap,
    loadout: Loadout,
    assignment: dict[DistrictType, Hex],
    legal: dict[DistrictType, list[Hex]],
) -> dict[DistrictType, Hex]:
    districts = list(assignment.keys())
    improved = True
    while improved:
        improved = False
        used = set(assignment.values())
        base = _layout_score(map, {assignment[d]: d for d in districts}, loadout)

        # (a) move one district to a free legal tile
        for d in districts:
            cur = assignment[d]
            for h in legal[d]:
                if h == cur or (h in used):
                    continue
                map.get(cur).district = None
                map.get(h).district = d
                trial = dict(assignment); trial[d] = h
                if _layout_score(map, {trial[x]: x for x in districts}, loadout) > base + 1e-9:
                    assignment[d] = h
                    improved = True
                    break
                map.get(h).district = None
                map.get(cur).district = d
            if improved:
                break
        if improved:
            continue

        # (b) swap the tiles of two districts
        for i in range(len(districts)):
            for j in range(i + 1, len(districts)):
                d1, d2 = districts[i], districts[j]
                h1, h2 = assignment[d1], assignment[d2]
                if h2 not in legal[d1] or h1 not in legal[d2]:
                    continue
                map.get(h1).district = d2
                map.get(h2).district = d1
                trial = dict(assignment); trial[d1], trial[d2] = h2, h1
                if _layout_score(map, {trial[x]: x for x in districts}, loadout) > base + 1e-9:
                    assignment[d1], assignment[d2] = h2, h1
                    improved = True
                    break
                map.get(h1).district = d1
                map.get(h2).district = d2
            if improved:
                break
    return assignment


def _random_assignment(
    rng: random.Random,
    districts: list[DistrictType],
    legal: dict[DistrictType, list[Hex]],
) -> dict[DistrictType, Hex]:
    order = districts[:]
    rng.shuffle(order)
    assignment: dict[DistrictType, Hex] = {}
    used: set[Hex] = set()
    for d in order:
        free = [h for h in legal[d] if h not in used]
        if free:
            h = rng.choice(free)
            assignment[d] = h
            used.add(h)
    return assignment


# --- exact enumeration (correct by construction) --------------------------------

def _exhaustive(
    map: GameMap,
    loadout: Loadout,
    districts: list[DistrictType],
    legal: dict[DistrictType, list[Hex]],
    incumbent: dict[DistrictType, Hex],
    incumbent_score: float,
) -> tuple[dict[DistrictType, Hex], float, bool]:
    order = sorted(districts, key=lambda d: len(legal[d]))
    our = set(districts)
    _apply(map, our, {})  # clear our districts
    best = dict(incumbent)
    best_score = incumbent_score
    used: set[Hex] = set()
    current: dict[Hex, DistrictType] = {}
    state = {"leaves": 0, "ok": True}

    def recurse(k: int) -> None:
        nonlocal best, best_score
        if not state["ok"]:
            return
        if k == len(order):
            state["leaves"] += 1
            score = _layout_score(map, dict(current), loadout)
            if score > best_score + 1e-9:
                best_score = score
                best = {d: h for h, d in current.items()}
            if state["leaves"] > EXACT_LEAF_BUDGET:
                state["ok"] = False
            return
        d = order[k]
        for h in legal[d]:
            if h in used:
                continue
            used.add(h); map.get(h).district = d; current[h] = d
            recurse(k + 1)
            del current[h]; map.get(h).district = None; used.discard(h)
            if not state["ok"]:
                return

    recurse(0)
    _apply(map, our, best)
    return best, best_score, state["ok"]


# --- public entry point ---------------------------------------------------------

def optimize_city(map: GameMap, city: City, loadout: Loadout | None = None) -> CityResult:
    loadout = loadout or Loadout()
    work = _clone_map(map)
    hexes = _candidate_hexes(work, city)

    districts: list[DistrictType] = []
    unplaceable: list[DistrictType] = []
    legal: dict[DistrictType, list[Hex]] = {}
    for d in city.requested:
        tiles = _legal_tiles(work, city, hexes, d, loadout)
        if tiles:
            districts.append(d)
            legal[d] = tiles
        else:
            unplaceable.append(d)

    if not districts:
        return CityResult(city.name, [], 0.0, {}, True, "none", unplaceable)

    our = set(districts)
    rng = random.Random(20250603)

    # deterministic greedy + local search
    best_assign = _local_search(work, loadout, _greedy(work, loadout, districts, legal), legal)
    best_score = _layout_score(work, {best_assign[d]: d for d in districts}, loadout)

    # random restarts
    for _ in range(RESTARTS):
        cand = _random_assignment(rng, districts, legal)
        if len(cand) < len(districts):
            continue
        _apply(work, our, cand)
        cand = _local_search(work, loadout, cand, legal)
        sc = _layout_score(work, {cand[d]: d for d in districts}, loadout)
        if sc > best_score + 1e-9:
            best_assign, best_score = cand, sc
    _apply(work, our, best_assign)

    method, optimal = "greedy+local+restarts", False
    est_leaves = 1
    for d in districts:
        est_leaves *= max(1, len(legal[d]))
    if est_leaves <= EXACT_LEAF_BUDGET:
        best_assign, best_score, completed = _exhaustive(
            work, loadout, districts, legal, best_assign, best_score
        )
        if completed:
            method, optimal = "exact_enumeration", True

    _apply(work, our, best_assign)

    placements: list[Placement] = []
    total_yields: Yields = {}
    total_score = 0.0
    total_opp = 0.0
    for d in districts:
        h = best_assign[d]
        y = adjacency_yield(work, h, d, loadout)
        sc = weighted_score(y, loadout)
        oc = opportunity_cost(work.get(h), loadout)
        ddef = resolve_def(d, loadout.civ) or DISTRICTS[d]
        disp = displayed_adjacency(y.get(ddef.primary_yield, 0.0)) if ddef.primary_yield else 0
        placements.append(Placement(d, h, y, disp, sc, oc))
        total_yields = add_yields(total_yields, y)
        total_score += sc
        total_opp += oc

    placements.sort(key=lambda p: p.score, reverse=True)
    return CityResult(
        city.name, placements, total_score, total_yields, optimal, method,
        unplaceable, round(total_opp, 3)
    )
