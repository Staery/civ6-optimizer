"""Settle scorer: housing/amenities + volcano & floodplain risk (and Dam mitigation)."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import Feature, GameMap, Terrain, Tile
from backend.optimizer.settle import _score_center


def _grass_map(radius: int = 3) -> GameMap:
    gm = GameMap()
    for h in within_radius(Hex(0, 0), radius):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    return gm


def test_volcano_adjacent_is_riskier_than_plain_mountain():
    mtn = _grass_map()
    mtn.get(Hex(1, 0)).terrain = Terrain.MOUNTAIN
    s_mtn = _score_center(mtn, Hex(0, 0), [])

    volc = _grass_map()
    volc.get(Hex(1, 0)).terrain = Terrain.MOUNTAIN
    volc.get(Hex(1, 0)).volcano = True
    s_volc = _score_center(volc, Hex(0, 0), [])

    # same mountain adjacency bonus, but the volcano adds eruption risk -> lower score
    assert s_volc.score < s_mtn.score
    assert s_volc.breakdown["volcano"] < 0
    assert "вулкан" in s_volc.note.lower()


def test_floodplains_on_river_recommends_a_dam():
    gm = _grass_map()
    fp = gm.get(Hex(1, 0))
    fp.feature = Feature.FLOODPLAINS
    fp.on_river = True
    s = _score_center(gm, Hex(0, 0), [])
    assert "дамб" in s.note.lower()


def test_floodplains_without_river_flagged_as_risky():
    gm = _grass_map()
    gm.get(Hex(1, 0)).feature = Feature.FLOODPLAINS  # no river -> no Dam possible
    s = _score_center(gm, Hex(0, 0), [])
    assert s.breakdown["flood"] < 0
    assert "затопл" in s.note.lower()


def test_dam_mitigates_flood_penalty():
    dry = _grass_map()
    dry.get(Hex(1, 0)).feature = Feature.FLOODPLAINS          # risky, no dam
    risky = _score_center(dry, Hex(0, 0), []).breakdown["flood"]

    wet = _grass_map()
    fp = wet.get(Hex(1, 0))
    fp.feature = Feature.FLOODPLAINS
    fp.on_river = True                                       # dam buildable -> mitigated
    mitigated = _score_center(wet, Hex(0, 0), []).breakdown["flood"]
    assert mitigated > risky


def test_distinct_luxuries_add_amenities():
    base = _score_center(_grass_map(), Hex(0, 0), [])
    lux = _grass_map()
    lux.get(Hex(1, 0)).resource = "wine"
    lux.get(Hex(-1, 0)).resource = "silk"
    s = _score_center(lux, Hex(0, 0), [])
    assert s.breakdown["amenities"] > 0
    assert s.score > base.score


def test_plains_hills_center_beats_flat_grassland():
    flat = _score_center(_grass_map(), Hex(0, 0), [])
    ph_map = _grass_map()
    ph_map.get(Hex(0, 0)).terrain = Terrain.PLAINS
    ph_map.get(Hex(0, 0)).hills = True
    ph = _score_center(ph_map, Hex(0, 0), [])
    assert ph.breakdown["center"] > 0
    assert ph.score > flat.score
