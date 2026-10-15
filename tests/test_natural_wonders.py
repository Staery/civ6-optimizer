"""Natural wonders: multi-tile Holy Site stacking, settle value, placement."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import DistrictType, Feature, GameMap, Terrain, Tile
from backend.optimizer.settle import _score_center, _valid_center
from backend.rules.adjacency import raw_adjacency

CENTER = Hex(0, 0)


def _hs_map(nw_keys: list[str]) -> GameMap:
    gm = GameMap()
    gm.set(Tile(coord=CENTER))
    for i, key in enumerate(nw_keys):
        n = CENTER.neighbor(i)
        gm.set(Tile(coord=n, feature=Feature.NATURAL_WONDER, natural_wonder=key))
    return gm


def test_single_natural_wonder_gives_holy_site_plus_two():
    gm = _hs_map(["pamukkale"])
    assert raw_adjacency(gm, CENTER, DistrictType.HOLY_SITE) == 2.0


def test_multitile_natural_wonder_stacks_holy_site():
    # adjacent to TWO tiles of the same 2-tile wonder -> +2 each = +4 (the 'area' effect)
    gm = _hs_map(["great_barrier_reef", "great_barrier_reef"])
    assert raw_adjacency(gm, CENTER, DistrictType.HOLY_SITE) == 4.0


def test_natural_wonder_boosts_settle_value():
    gm = GameMap()
    for h in within_radius(CENTER, 3):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    base = _score_center(gm, CENTER, [])
    t = gm.get(Hex(1, 0))
    t.feature = Feature.NATURAL_WONDER
    t.natural_wonder = "pamukkale"
    with_nw = _score_center(gm, CENTER, [])
    assert with_nw.score > base.score


def test_cannot_settle_on_a_natural_wonder():
    gm = GameMap()
    gm.set(Tile(coord=CENTER, feature=Feature.NATURAL_WONDER, natural_wonder="uluru"))
    assert _valid_center(gm, CENTER) is False
