"""Verified Civ 6 (Gathering Storm) base tile yields + opportunity cost."""

from backend.domain.hexgrid import Hex
from backend.domain.models import Feature, Terrain, Tile, YieldType
from backend.rules.modifiers import Loadout
from backend.rules.tile_yields import base_yields, opportunity_cost

F, P, G = YieldType.FOOD, YieldType.PRODUCTION, YieldType.GOLD


def y(**kw):
    return base_yields(Tile(coord=Hex(0, 0), **kw))


def test_base_terrain_yields_verified():
    assert y(terrain=Terrain.GRASSLAND) == {F: 2, P: 0, G: 0}
    assert y(terrain=Terrain.PLAINS) == {F: 1, P: 1, G: 0}
    assert y(terrain=Terrain.TUNDRA) == {F: 1, P: 0, G: 0}
    assert y(terrain=Terrain.DESERT) == {F: 0, P: 0, G: 0}
    assert y(terrain=Terrain.SNOW) == {F: 0, P: 0, G: 0}
    assert y(terrain=Terrain.COAST) == {F: 1, P: 0, G: 1}
    assert y(terrain=Terrain.OCEAN) == {F: 1, P: 0, G: 0}
    assert y(terrain=Terrain.LAKE) == {F: 1, P: 0, G: 1}


def test_hills_add_one_production():
    assert y(terrain=Terrain.GRASSLAND, hills=True) == {F: 2, P: 1, G: 0}
    assert y(terrain=Terrain.PLAINS, hills=True) == {F: 1, P: 2, G: 0}


def test_feature_yields_verified():
    assert y(terrain=Terrain.GRASSLAND, feature=Feature.WOODS) == {F: 2, P: 1, G: 0}
    assert y(terrain=Terrain.PLAINS, feature=Feature.RAINFOREST) == {F: 2, P: 1, G: 0}
    assert y(terrain=Terrain.GRASSLAND, feature=Feature.MARSH) == {F: 3, P: 0, G: 0}
    assert y(terrain=Terrain.DESERT, feature=Feature.OASIS) == {F: 3, P: 0, G: 1}
    assert y(terrain=Terrain.COAST, feature=Feature.REEF) == {F: 2, P: 1, G: 1}
    # desert floodplains: +2 food (officially verified)
    assert y(terrain=Terrain.DESERT, feature=Feature.FLOODPLAINS) == {F: 2, P: 0, G: 0}


def test_opportunity_cost_off_by_default():
    assert opportunity_cost(Tile(coord=Hex(0, 0), terrain=Terrain.GRASSLAND), Loadout()) == 0.0


def test_opportunity_cost_scales_with_yields_weights_and_resource():
    woods = Tile(coord=Hex(0, 0), terrain=Terrain.GRASSLAND, feature=Feature.WOODS)  # 2F,1P
    assert opportunity_cost(woods, Loadout(oc_weight=1.0)) == 3.0   # 2 + 1
    res = Tile(coord=Hex(0, 0), terrain=Terrain.GRASSLAND, resource="wheat")  # 2F + keep 2
    assert opportunity_cost(res, Loadout(oc_weight=1.0)) == 4.0
