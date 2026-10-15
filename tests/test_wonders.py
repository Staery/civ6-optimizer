"""World Wonder recommender: valid placement, ranking, taken-detection."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import City, DistrictType, Feature, GameMap, Terrain, Tile
from backend.optimizer import detect_taken, recommend_wonders


def _map() -> tuple[GameMap, list[City]]:
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 3):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND, owner_city="Capital"))
    gm.get(Hex(0, 0)).district = DistrictType.CITY_CENTER
    gm.get(Hex(1, 0)).terrain = Terrain.DESERT     # Pyramids / Petra
    gm.get(Hex(0, 1)).terrain = Terrain.MOUNTAIN   # Machu Picchu
    cities = [City("Capital", Hex(0, 0), work_radius=3, requested=[])]
    return gm, cities


def test_recommends_desert_and_mountain_wonders():
    gm, cities = _map()
    recs, _taken = recommend_wonders(gm, cities)
    keys = {r.key for r in recs}
    assert "pyramids" in keys
    assert "machu_picchu" in keys
    pyr = next(r for r in recs if r.key == "pyramids")
    assert (pyr.q, pyr.r) == (1, 0)
    assert pyr.risk == "высокий"  # ancient wonders are AI-contested


def test_ranked_by_value():
    gm, cities = _map()
    recs, _ = recommend_wonders(gm, cities)
    values = [r.value for r in recs]
    assert values == sorted(values, reverse=True)


def test_no_wonder_on_city_center_including_planned_new_city():
    """A wonder must never be recommended on a city centre — even a PLANNED new city
    whose centre tile is still empty on the map."""
    gm, cities = _map()
    planned = Hex(2, 0)
    for h in within_radius(planned, 3):
        if gm.get(h) is None:
            gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND, owner_city="New"))
    gm.get(planned).terrain = Terrain.DESERT          # otherwise a prime Pyramids tile
    cities = cities + [City("New", planned, work_radius=3, requested=[])]
    recs, _ = recommend_wonders(gm, cities)
    centers = {(c.center.q, c.center.r) for c in cities}
    assert all((r.q, r.r) not in centers for r in recs)


def test_detect_taken_excludes_built_wonder():
    gm, cities = _map()
    gm.get(Hex(2, 0)).wonder = "Pyramids"  # already built somewhere on the map
    assert "pyramids" in detect_taken(gm)
    recs, taken = recommend_wonders(gm, cities)
    assert "pyramids" not in {r.key for r in recs}
    assert "pyramids" in taken
