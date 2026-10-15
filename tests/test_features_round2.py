"""Loyalty, strategic resources, pantheons, and building yields."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import (
    City,
    DistrictType,
    Feature,
    GameMap,
    Terrain,
    Tile,
    YieldType,
)
from backend.optimizer.settle import _loyalty_balance, _score_center
from backend.rules.adjacency import adjacency_yield, raw_adjacency
from backend.rules.buildings import building_yields
from backend.rules.modifiers import Loadout


def _grass(center: Hex, radius: int = 3) -> GameMap:
    gm = GameMap()
    for h in within_radius(center, radius):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    return gm


# --- pantheons --------------------------------------------------------------
def test_pantheon_dance_of_aurora_rewards_tundra_for_holy_site():
    c = Hex(0, 0)
    gm = GameMap()
    gm.set(Tile(coord=c, terrain=Terrain.GRASSLAND))
    for n in c.neighbors():
        gm.set(Tile(coord=n, terrain=Terrain.TUNDRA))
    base = raw_adjacency(gm, c, DistrictType.HOLY_SITE)        # tundra gives nothing by default
    y = adjacency_yield(gm, c, DistrictType.HOLY_SITE, Loadout(pantheon="dance_of_the_aurora"))
    assert y[YieldType.FAITH] == base + 6.0                    # +1 per adjacent tundra (6)


def test_pantheon_does_not_affect_other_districts():
    c = Hex(0, 0)
    gm = GameMap()
    gm.set(Tile(coord=c, terrain=Terrain.GRASSLAND))
    for n in c.neighbors():
        gm.set(Tile(coord=n, terrain=Terrain.TUNDRA))
    y = adjacency_yield(gm, c, DistrictType.CAMPUS, Loadout(pantheon="dance_of_the_aurora"))
    assert y.get(YieldType.SCIENCE, 0.0) == 0.0                # campus unaffected by Holy Site pantheon


# --- building yields --------------------------------------------------------
def test_building_yields_present_for_specialty_districts():
    assert building_yields(DistrictType.CAMPUS)[YieldType.SCIENCE] == 6.0
    assert building_yields(DistrictType.COMMERCIAL_HUB)[YieldType.GOLD] == 8.0
    assert building_yields(DistrictType.AQUEDUCT)[YieldType.HOUSING] == 6.0


# --- loyalty ----------------------------------------------------------------
def test_loyalty_balance_negative_near_strong_rival():
    h = Hex(0, 0)
    own = [(Hex(5, 0), 3)]      # your city, far + small
    rivals = [(Hex(1, 0), 10)]  # rival, close + large
    assert _loyalty_balance(h, own, rivals) < 0


def test_loyalty_penalty_lowers_score_and_warns():
    c = Hex(0, 0)
    gm = _grass(c)
    rivals = [(Hex(2, 0), 12)]
    safe = _score_center(gm, c, [], None, [(Hex(5, 0), 4)], [])
    risky = _score_center(gm, c, [], None, [(Hex(5, 0), 4)], rivals)
    assert risky.score < safe.score
    assert risky.breakdown["loyalty"] < 0
    assert "лояльност" in risky.note


# --- strategic resources ----------------------------------------------------
def test_strategic_resource_adds_score_and_note():
    c = Hex(0, 0)
    gm = _grass(c)
    gm.get(Hex(1, 0)).resource = "iron"
    s = _score_center(gm, c, [], None, [], [])
    assert s.breakdown["strategic"] > 0
    assert "iron" in s.note
