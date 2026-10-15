"""Base tile yields and the *opportunity cost* of building a district on a tile.

In Civ 6 a tile worked by a citizen produces base Food/Production/Gold. Placing a
district there forfeits that yield, so good players put districts on low-value
filler tiles and keep rich tiles (resources, floodplains, hills) workable. The
optimizer subtracts this opportunity cost from a placement's adjacency score.

Numbers below are the **verified** Gathering Storm base yields (sources checked):
  Grassland 2F · Plains 1F/1P · Tundra 1F · Desert/Snow 0 · Coast 1F/1G ·
  Ocean 1F · Lake 1F/1G · Hills +1P · Woods +1P · Rainforest +1F · Marsh +1F ·
  Reef +1F/1P · Oasis +3F/1G · Desert Floodplains +2F.
Approximated (GS flood mechanic is inconsistent across sources / rare): generic
Floodplains +1F, Volcanic Soil 0, and resources as a flat "keep" value.
"""

from __future__ import annotations

from ..domain.models import Feature, Terrain, Tile, YieldType

F, P, G = YieldType.FOOD, YieldType.PRODUCTION, YieldType.GOLD

# Base terrain yields (flat, before Hills). (food, production, gold)
_TERRAIN: dict[Terrain, tuple[int, int, int]] = {
    Terrain.GRASSLAND: (2, 0, 0),
    Terrain.PLAINS: (1, 1, 0),
    Terrain.DESERT: (0, 0, 0),
    Terrain.TUNDRA: (1, 0, 0),
    Terrain.SNOW: (0, 0, 0),
    Terrain.COAST: (1, 0, 1),
    Terrain.OCEAN: (1, 0, 0),
    Terrain.LAKE: (1, 0, 1),
    Terrain.MOUNTAIN: (0, 0, 0),
}

# Feature additions (food, production, gold). Floodplains handled specially.
_FEATURE: dict[Feature, tuple[int, int, int]] = {
    Feature.WOODS: (0, 1, 0),
    Feature.RAINFOREST: (1, 0, 0),
    Feature.MARSH: (1, 0, 0),
    Feature.OASIS: (3, 0, 1),
    Feature.REEF: (1, 1, 0),
    Feature.GEOTHERMAL_FISSURE: (0, 0, 0),
    Feature.VOLCANIC_SOIL: (1, 1, 0),  # fertile post-eruption soil (GS): +1F/+1P
}

# Flat "this tile is worth keeping" value for any resource (approx; exact per-resource
# yields vary widely and aren't enumerated here).
RESOURCE_KEEP_VALUE = 2.0


def base_yields(tile: Tile) -> dict[YieldType, float]:
    f, p, g = _TERRAIN.get(tile.terrain, (0, 0, 0))
    if tile.hills and tile.terrain.is_land:
        p += 1
    if tile.feature is Feature.FLOODPLAINS:
        f += 2 if tile.terrain is Terrain.DESERT else 1  # desert floodplains +2 (verified)
    else:
        ff, pp, gg = _FEATURE.get(tile.feature, (0, 0, 0))
        f += ff; p += pp; g += gg
    return {F: float(f), P: float(p), G: float(g)}


def opportunity_cost(tile: Tile, loadout) -> float:
    """Weighted value of the yields lost by covering this tile with a district.

    Returns 0 when ``loadout.oc_weight`` is 0 (feature off). Scales by the player's
    yield weights so e.g. valuing Food highly makes the model protect food tiles.
    """
    oc = getattr(loadout, "oc_weight", 0.0) if loadout is not None else 0.0
    if not oc or tile is None:
        return 0.0
    yields = base_yields(tile)
    val = sum(loadout.weight(y) * amt for y, amt in yields.items())
    if tile.resource:
        val += RESOURCE_KEEP_VALUE
    return oc * val
