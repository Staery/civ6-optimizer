"""Optimizer correctness: known optima on small maps + exact-vs-bruteforce check."""

from itertools import permutations

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import City, DistrictType, Feature, GameMap, Terrain, Tile
from backend.optimizer import optimize_city
from backend.rules.adjacency import adjacency_yield, can_place, weighted_score
from backend.rules.modifiers import Loadout

CENTER = Hex(0, 0)


def _tiny_map() -> GameMap:
    gm = GameMap()
    coords = {
        (0, 0): {"district": DistrictType.CITY_CENTER},
        (1, 0): {},                    # campus tile (touches both mountains)
        (0, 1): {"on_river": True},    # commercial hub tile (river)
        (2, 0): {"terrain": Terrain.MOUNTAIN},
        (2, -1): {"terrain": Terrain.MOUNTAIN},
        (1, 1): {},
        (-1, 0): {},
        (0, -1): {},
    }
    for (q, r), attrs in coords.items():
        t = Tile(coord=Hex(q, r), terrain=Terrain.GRASSLAND, owner_city="Capital")
        for k, v in attrs.items():
            setattr(t, k, v)
        gm.set(t)
    return gm


def _brute_force(gm: GameMap, city: City, loadout: Loadout) -> float:
    hexes = [h for h in within_radius(city.center, city.work_radius)
             if h != city.center and gm.get(h) is not None]
    legal = {
        d: [h for h in hexes if gm.get(h).district is None and can_place(gm, h, d, city)]
        for d in city.requested
    }
    best = float("-inf")
    ds = list(city.requested)
    # iterate all injective tile choices
    pools = [legal[d] for d in ds]
    for combo in _injective(pools):
        for d, h in zip(ds, combo):
            gm.get(h).district = d
        score = sum(weighted_score(adjacency_yield(gm, h, d, loadout), loadout)
                    for d, h in zip(ds, combo))
        best = max(best, score)
        for h in combo:
            gm.get(h).district = None
    return best


def _injective(pools):
    if not pools:
        yield ()
        return
    head, *rest = pools
    for h in head:
        for tail in _injective(rest):
            if h not in tail:
                yield (h, *tail)


def test_single_campus_known_optimum():
    gm = _tiny_map()
    city = City("Capital", CENTER, work_radius=2, requested=[DistrictType.CAMPUS])
    res = optimize_city(gm, city)
    assert res.optimal is True
    assert res.method == "exact_enumeration"
    assert len(res.placements) == 1
    p = res.placements[0]
    assert p.coord == Hex(1, 0)
    assert p.score == 2.5  # two adjacent mountains (+2) + adjacent city center (+0.5)


def test_two_districts_pack_for_mutual_bonus():
    gm = _tiny_map()
    city = City("Capital", CENTER, work_radius=2,
                requested=[DistrictType.CAMPUS, DistrictType.COMMERCIAL_HUB])
    res = optimize_city(gm, city)
    assert res.optimal is True
    coords = {p.district: p.coord for p in res.placements}
    assert coords[DistrictType.CAMPUS] == Hex(1, 0)
    assert coords[DistrictType.COMMERCIAL_HUB] == Hex(0, 1)
    # campus 2 (mtns) + 0.5 (hub) + 0.5 (city center); hub 2 (river) + 0.5 (campus)
    # + 0.5 (city center) = 6.0
    assert res.total_score == 6.0


def test_opportunity_cost_shifts_district_off_valuable_tile():
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 2):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND, owner_city="Cap"))
    gm.get(Hex(0, 0)).district = DistrictType.CITY_CENTER
    gm.get(Hex(2, 0)).terrain = Terrain.MOUNTAIN
    # (2,-1) is a rich Oasis tile that is ALSO adjacent to the mountain
    gm.get(Hex(2, -1)).terrain = Terrain.DESERT
    gm.get(Hex(2, -1)).feature = Feature.OASIS
    city = City("Cap", Hex(0, 0), work_radius=2, requested=[DistrictType.CAMPUS])
    # with opportunity cost ON, the campus must avoid wasting the oasis tile
    res = optimize_city(gm, city, Loadout(oc_weight=1.0))
    assert res.placements[0].coord != Hex(2, -1)
    # grassland filler costs 2.0; the oasis would have cost 4.0
    assert res.total_opportunity < 3.0


def test_optimizer_matches_bruteforce():
    gm = _tiny_map()
    loadout = Loadout()
    city = City("Capital", CENTER, work_radius=2,
                requested=[DistrictType.CAMPUS, DistrictType.COMMERCIAL_HUB,
                           DistrictType.HOLY_SITE])
    res = optimize_city(gm, city)
    brute = _brute_force(_tiny_map(), city, loadout)
    assert res.optimal is True
    assert abs(res.total_score - brute) < 1e-9
