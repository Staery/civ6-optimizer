"""Empire optimizer: cross-city adjacency and territory partition."""

from backend.domain.hexgrid import Hex, distance, within_radius
from backend.domain.models import City, DistrictType, GameMap, Terrain, Tile
from backend.optimizer import assign_territory, optimize_empire, suggest_settles


def _two_city_map() -> tuple[GameMap, list[City]]:
    gm = GameMap()
    for c in (Hex(0, 0), Hex(3, 0)):
        for h in within_radius(c, 3):
            if gm.get(h) is None:
                gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = DistrictType.CITY_CENTER
    gm.get(Hex(3, 0)).district = DistrictType.CITY_CENTER
    # one mountain per city, each adjacent to only that city's border tile, so the
    # extra value can only come from cross-city packing on the shared border.
    gm.get(Hex(1, -1)).terrain = Terrain.MOUNTAIN   # touches (1,0) only -> city A
    gm.get(Hex(2, 1)).terrain = Terrain.MOUNTAIN    # touches (2,0) only -> city B
    cities = [
        City("A", Hex(0, 0), work_radius=3, requested=[DistrictType.CAMPUS]),
        City("B", Hex(3, 0), work_radius=3, requested=[DistrictType.CAMPUS]),
    ]
    return gm, cities


def test_territory_partition_by_nearest_center():
    gm, cities = _two_city_map()
    owner = assign_territory(gm, cities)
    assert owner[Hex(1, 0)] == 0  # closer to A
    assert owner[Hex(2, 0)] == 1  # closer to B


def test_cross_city_adjacency_is_exploited():
    gm, cities = _two_city_map()
    res = optimize_empire(gm, cities)
    # each city places its single campus
    assert len(res.placements_by_city["A"]) == 1
    assert len(res.placements_by_city["B"]) == 1
    pa = res.placements_by_city["A"][0]
    pb = res.placements_by_city["B"][0]
    # campuses pack onto the border: +1 mountain + 0.5 own city center + 0.5 each
    # other (cross-city). Each = 2.0.
    assert distance(pa.coord, pb.coord) == 1
    assert pa.displayed == 2 and pb.displayed == 2  # floor(2.0)
    assert res.total_score == 4.0  # 2.0 + 2.0, vs 3.0 if cross-city ignored


def test_regional_overlap_rewards_shared_industrial_zone():
    # Two cities 6 apart on flat land; each builds an Industrial Zone. A higher
    # region_weight must report a positive regional-overlap bonus (Factory shared).
    from backend.rules.modifiers import Loadout

    gm = GameMap()
    for q in range(-3, 10):
        for r in range(-3, 4):
            gm.set(Tile(coord=Hex(q, r), terrain=Terrain.GRASSLAND))
    a, b = Hex(0, 0), Hex(6, 0)
    gm.get(a).district = DistrictType.CITY_CENTER
    gm.get(b).district = DistrictType.CITY_CENTER
    cities = [
        City("A", a, work_radius=3, requested=[DistrictType.INDUSTRIAL_ZONE]),
        City("B", b, work_radius=3, requested=[DistrictType.INDUSTRIAL_ZONE]),
    ]
    off = optimize_empire(gm, cities, Loadout(region_weight=0.0, oc_weight=0.0))
    on = optimize_empire(gm, cities, Loadout(region_weight=1.0, oc_weight=0.0))
    assert off.total_regional == 0.0
    assert on.total_regional > 0.0  # both IZ cover the other city center within 6


def test_suggest_settles_respects_spacing():
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 6):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = DistrictType.CITY_CENTER
    cities = [City("Capital", Hex(0, 0), work_radius=3, requested=[])]
    sugg = suggest_settles(gm, cities, count=3)
    assert sugg, "should suggest at least one site"
    for s in sugg:
        assert distance(s.coord, Hex(0, 0)) >= 4  # not too close to existing city


def test_inca_prefers_mountain_sites():
    from backend.optimizer.settle import _score_center

    gm = GameMap()
    for h in within_radius(Hex(0, 0), 8):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = DistrictType.CITY_CENTER
    for m in (Hex(6, 1), Hex(7, -1), Hex(5, 1)):  # mountains around (6,0)
        gm.get(m).terrain = Terrain.MOUNTAIN
    base = _score_center(gm, Hex(6, 0), [Hex(0, 0)], None)
    inca = _score_center(gm, Hex(6, 0), [Hex(0, 0)], "inca")
    assert inca.score > base.score            # mountains boost an Inca site
    assert inca.breakdown["civ"] == 3.0       # +1.0 per adjacent mountain (3 of them)
