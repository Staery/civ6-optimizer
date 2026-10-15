"""Amenities estimator: deficit detection, luxury supply, the 4-city rule."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import City, DistrictType, GameMap, Terrain, Tile
from backend.optimizer.amenities import estimate_amenities


def _city_map(center: Hex, radius: int = 3) -> GameMap:
    gm = GameMap()
    for h in within_radius(center, radius):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(center).district = DistrictType.CITY_CENTER
    return gm


def test_amenity_deficit_is_flagged():
    c = Hex(0, 0)
    cities = [City("A", c, work_radius=3, requested=[], population=8)]  # needs 3
    r = estimate_amenities(_city_map(c), cities)[0]
    assert r.required == 3
    assert r.supply == 0
    assert r.surplus == -3
    assert r.state in ("unhappy", "unrest")
    assert any("дефицит" in a for a in r.advice)


def test_distinct_luxuries_supply_amenities():
    c = Hex(0, 0)
    gm = _city_map(c)
    gm.get(Hex(1, 0)).resource = "wine"
    gm.get(Hex(-1, 0)).resource = "silk"
    cities = [City("A", c, work_radius=3, requested=[], population=4)]  # needs 1
    r = estimate_amenities(gm, cities)[0]
    assert r.supply == 2          # two distinct luxuries
    assert r.surplus == 1
    assert r.state == "happy"


def test_entertainment_district_adds_an_amenity():
    c = Hex(0, 0)
    gm = _city_map(c)
    gm.get(Hex(1, 0)).district = DistrictType.ENTERTAINMENT
    cities = [City("A", c, work_radius=3, requested=[], population=4)]
    r = estimate_amenities(gm, cities)[0]
    assert r.supply == 1


def test_fifth_city_gets_no_luxury_amenities():
    centers = [Hex(0, 0), Hex(8, 0), Hex(0, 8), Hex(8, 8), Hex(16, 0)]
    gm = GameMap()
    for ctr in centers:
        for h in within_radius(ctr, 2):
            if gm.get(h) is None:
                gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
        gm.get(ctr).district = DistrictType.CITY_CENTER
        gm.get(Hex(ctr.q + 1, ctr.r)).resource = "wine"   # one distinct luxury empire-wide
    cities = [City(f"C{i}", ctr, work_radius=2, requested=[], population=10 - i)
              for i, ctr in enumerate(centers)]
    reps = {r.city: r for r in estimate_amenities(gm, cities)}
    assert reps["C0"].supply >= 1     # highest population -> in top 4 -> gets the luxury
    assert reps["C4"].supply == 0     # 5th by population -> luxuries don't reach it
    assert any("роскош" in a or "4 самых" in a for a in reps["C4"].advice)
