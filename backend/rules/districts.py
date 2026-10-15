"""District definitions: primary yield, adjacency rules, and placement constraints.

Ruleset: **Gathering Storm + New Frontier Pass**.

Adjacency tiers in Civ 6:
  * **Major**    = +2 per source
  * **Standard** = +1 per source
  * **Minor**    = +0.5 per source (two minor sources make +1)

We keep adjacency as a raw float (so the optimizer can prefer extra +0.5 sources);
the in-game *displayed* value is ``floor`` of the sum (see ``adjacency.py``).

``VALIDATE:`` marks numbers worth double-checking against the Adjacency Planner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..domain.hexgrid import Hex
from ..domain.models import (
    City,
    DistrictType,
    Feature,
    GameMap,
    Improvement,
    Terrain,
    Tile,
    YieldType,
)

# In Civ 6 EVERY district — including the City Center and engineering districts
# (Aqueduct/Dam/Canal/Neighborhood) — confers the generic minor adjacency bonus
# (+0.5) to nearby specialty districts. (Verified against the Adjacency Bonus wiki.)
# So the generic "+0.5 per adjacent district" counts any district tile.
# (Kept as a named set for reference / other call-sites.)
STANDARD_ADJ_DISTRICTS: frozenset[DistrictType] = frozenset(set(DistrictType))


# --- predicates over a neighbouring (or own) tile -------------------------------

def _is_mountain(t: Tile) -> bool:
    return t.terrain is Terrain.MOUNTAIN


def _is_standard_district(t: Tile) -> bool:
    return t.district in STANDARD_ADJ_DISTRICTS


def _feature(*features: Feature) -> Callable[[Tile], bool]:
    fs = set(features)
    return lambda t: t.feature in fs


def _district(*types: DistrictType) -> Callable[[Tile], bool]:
    ds = set(types)
    return lambda t: t.district in ds


def _sea_resource(t: Tile) -> bool:
    return t.terrain.is_water and t.resource is not None


def _improvement(*imps: Improvement) -> Callable[[Tile], bool]:
    s = set(imps)
    return lambda t: t.improvement in s


def _no_district(pred: Callable[[Tile], bool]) -> Callable[[Tile], bool]:
    """Wrap a predicate so it only matches tiles WITHOUT a district.

    Features (Woods/Rainforest), improvements (Mine/Quarry/Lumber Mill) and the
    resource on a tile are REMOVED when a district is built there, so they stop
    conferring adjacency once the tile is occupied. Pure terrain (Mountain/Coast)
    and other districts are unaffected and don't need this guard.
    """
    return lambda t: t.district is None and pred(t)


# --- adjacency rule model -------------------------------------------------------

@dataclass(frozen=True)
class AdjRule:
    """One adjacency contribution toward a district's *primary* yield.

    kind:
      * ``per_neighbor`` -> amount * (# neighbour tiles matching ``predicate``)
      * ``presence``     -> amount once if ANY neighbour matches ``predicate``
      * ``self``         -> amount once if the district's OWN tile matches
    """

    kind: str
    predicate: Callable[[Tile], bool]
    amount: float
    note: str = ""


# --- placement constraints ------------------------------------------------------

def _land(map: GameMap, coord: Hex, city: City) -> bool:
    t = map.get(coord)
    return t is not None and t.is_buildable_land


def _water(map: GameMap, coord: Hex, city: City) -> bool:
    # Harbor / Water Park: a Coast or Lake tile (NOT deep Ocean / Ice) that is adjacent
    # to land. Deep-ocean and land-locked water tiles are not valid in-game.
    t = map.get(coord)
    if t is None or t.district is not None or t.wonder is not None:
        return False
    if t.terrain not in (Terrain.COAST, Terrain.LAKE) or t.feature is Feature.ICE:
        return False
    return any(n.terrain.is_land for n in map.neighbors(coord))


def _aqueduct(map: GameMap, coord: Hex, city: City) -> bool:
    # Civ 6 rule: adjacent to the City Center AND itself touching fresh water — i.e. ON a
    # river, OR adjacent to a Mountain / Lake / Oasis. (Geothermal Fissure is NOT a fresh-
    # water source. A neighbour merely near a river that doesn't touch THIS tile doesn't count.)
    t = map.get(coord)
    if t is None or not t.is_buildable_land:
        return False
    nbrs = map.neighbors(coord)
    if not any(n.coord == city.center for n in nbrs):
        return False
    if t.on_river:
        return True
    return any(
        n.terrain in (Terrain.MOUNTAIN, Terrain.LAKE) or n.feature is Feature.OASIS
        for n in nbrs
    )


def _dam(map: GameMap, coord: Hex, city: City) -> bool:
    # Civ 6 rule: a Floodplains tile where a River crosses at least TWO of its edges.
    # When the game export gives the real edge count (`river_edges`), use it exactly.
    # For manual maps / old logs (river_edges unknown) fall back to a conservative
    # approximation: the tile is on a river AND ≥2 neighbours also sit on the river.
    t = map.get(coord)
    if t is None or t.district is not None or t.feature is not Feature.FLOODPLAINS:
        return False
    if t.river_edges is not None:
        return t.river_edges >= 2
    return t.on_river and sum(1 for n in map.neighbors(coord) if n.on_river) >= 2


def _adjacent_to_center(map: GameMap, coord: Hex, city: City) -> bool:
    return any(n.coord == city.center for n in map.neighbors(coord))


def _encampment(map: GameMap, coord: Hex, city: City) -> bool:
    # Standard land, but the Encampment may NOT be placed adjacent to the City Center.
    t = map.get(coord)
    return t is not None and t.is_buildable_land and not _adjacent_to_center(map, coord, city)


def _preserve(map: GameMap, coord: Hex, city: City) -> bool:
    # Standard land, but the Preserve may NOT be placed adjacent to the City Center.
    t = map.get(coord)
    return t is not None and t.is_buildable_land and not _adjacent_to_center(map, coord, city)


def _flat_land(map: GameMap, coord: Hex, city: City) -> bool:
    # Aerodrome / Spaceport need flat (non-Hills) buildable land.
    t = map.get(coord)
    return t is not None and t.is_buildable_land and not t.hills


def _canal(map: GameMap, coord: Hex, city: City) -> bool:
    # Flat land linking water: adjacent to a water tile/river AND to the City Center
    # or another water tile. (Simplified from the exact two-endpoints rule.)
    t = map.get(coord)
    if t is None or not t.is_buildable_land or t.hills:
        return False
    nbrs = map.neighbors(coord)
    water = sum(1 for n in nbrs if n.terrain.is_water or n.on_river)
    return water >= 1 and (water >= 2 or _adjacent_to_center(map, coord, city))


# --- district definitions -------------------------------------------------------

@dataclass(frozen=True)
class DistrictDef:
    type: DistrictType
    primary_yield: YieldType | None
    rules: tuple[AdjRule, ...] = ()
    placement: Callable[[GameMap, Hex, City], bool] = _land


def _std_district_rule(amount: float = 0.5) -> AdjRule:
    return AdjRule("per_neighbor", _is_standard_district, amount, "adjacent district")


DISTRICTS: dict[DistrictType, DistrictDef] = {
    DistrictType.CAMPUS: DistrictDef(
        DistrictType.CAMPUS,
        YieldType.SCIENCE,
        (
            AdjRule("per_neighbor", _is_mountain, 1.0, "mountain"),
            AdjRule("per_neighbor", _feature(Feature.GEOTHERMAL_FISSURE), 2.0, "geothermal"),
            AdjRule("per_neighbor", _feature(Feature.REEF), 2.0, "reef"),
            AdjRule("per_neighbor", _no_district(_feature(Feature.RAINFOREST)), 0.5, "rainforest"),
            _std_district_rule(),
        ),
    ),
    DistrictType.HOLY_SITE: DistrictDef(
        DistrictType.HOLY_SITE,
        YieldType.FAITH,
        (
            AdjRule("per_neighbor", lambda t: t.is_natural_wonder, 2.0, "natural wonder"),
            AdjRule("per_neighbor", _is_mountain, 1.0, "mountain"),
            AdjRule("per_neighbor", _no_district(_feature(Feature.WOODS)), 0.5, "woods"),
            _std_district_rule(),
        ),
    ),
    DistrictType.THEATER: DistrictDef(
        DistrictType.THEATER,
        YieldType.CULTURE,
        (
            AdjRule("per_neighbor", lambda t: t.is_world_wonder, 2.0, "world wonder"),
            # August 2020 Update: Entertainment Complex / Water Park give the Theater
            # Square a MAJOR (+2) Culture adjacency — same as a Wonder. The generic
            # per-district rule already adds +0.5 for each, so +1.5 more makes the full +2.
            AdjRule("per_neighbor",
                    _district(DistrictType.ENTERTAINMENT, DistrictType.WATER_PARK),
                    1.5, "entertainment/water park (major, Aug-2020 patch)"),
            _std_district_rule(),
        ),
    ),
    DistrictType.COMMERCIAL_HUB: DistrictDef(
        DistrictType.COMMERCIAL_HUB,
        YieldType.GOLD,
        (
            AdjRule("self", lambda t: t.on_river, 2.0, "river"),
            AdjRule("per_neighbor", _district(DistrictType.HARBOR), 2.0, "harbor"),
            _std_district_rule(),
        ),
    ),
    DistrictType.HARBOR: DistrictDef(
        DistrictType.HARBOR,
        YieldType.GOLD,
        (
            AdjRule("per_neighbor", _district(DistrictType.CITY_CENTER), 2.0, "city center"),
            AdjRule("per_neighbor", _no_district(_sea_resource), 1.0, "sea resource"),
            _std_district_rule(),
        ),
        placement=_water,
    ),
    DistrictType.INDUSTRIAL_ZONE: DistrictDef(
        DistrictType.INDUSTRIAL_ZONE,
        YieldType.PRODUCTION,
        (
            AdjRule(
                "per_neighbor",
                _district(DistrictType.AQUEDUCT, DistrictType.DAM, DistrictType.CANAL),
                2.0,
                "aqueduct/dam/canal",
            ),
            # Gathering Storm re-tiered improvements: Quarry and Strategic Resource are
            # STANDARD (+1); Mine and Lumber Mill are MINOR (+0.5). A strategic resource
            # counts once at +1 even when worked by a Mine (excluded from the mine rule
            # below to avoid double-counting).
            AdjRule("per_neighbor", _no_district(lambda t: t.resource_class == "strategic"),
                    1.0, "strategic resource"),
            AdjRule("per_neighbor", _no_district(_improvement(Improvement.QUARRY)), 1.0, "quarry"),
            AdjRule("per_neighbor",
                    _no_district(lambda t: t.improvement is Improvement.MINE
                                 and t.resource_class != "strategic"),
                    0.5, "mine"),
            AdjRule("per_neighbor", _no_district(_improvement(Improvement.LUMBER_MILL)), 0.5, "lumber mill"),
            _std_district_rule(),
        ),
    ),
    DistrictType.PRESERVE: DistrictDef(
        DistrictType.PRESERVE,
        YieldType.FAITH,
        # The Grove (first Preserve building) grants Faith from the appeal of adjacent
        # tiles; Sanctuary later adds Culture. Modelled as appeal-driven faith here; the
        # appeal module refines housing/National-Park interactions.
        (
            AdjRule("per_neighbor", lambda t: t.appeal >= 4, 2.0, "breathtaking tile"),
            AdjRule("per_neighbor", lambda t: 2 <= t.appeal < 4, 1.0, "charming tile"),
            _std_district_rule(),
        ),
        placement=_preserve,
    ),
    # Source-only / utility districts (placeable, but no primary yield-adjacency).
    DistrictType.AQUEDUCT: DistrictDef(DistrictType.AQUEDUCT, None, (), placement=_aqueduct),
    DistrictType.DAM: DistrictDef(DistrictType.DAM, None, (), placement=_dam),
    DistrictType.CANAL: DistrictDef(DistrictType.CANAL, None, (), placement=_canal),
    DistrictType.ENTERTAINMENT: DistrictDef(DistrictType.ENTERTAINMENT, None, (_std_district_rule(),)),
    DistrictType.WATER_PARK: DistrictDef(DistrictType.WATER_PARK, None, (_std_district_rule(),),
                                         placement=_water),
    DistrictType.ENCAMPMENT: DistrictDef(DistrictType.ENCAMPMENT, None, (_std_district_rule(),),
                                         placement=_encampment),
    DistrictType.NEIGHBORHOOD: DistrictDef(DistrictType.NEIGHBORHOOD, None, (_std_district_rule(),)),
    DistrictType.AERODROME: DistrictDef(DistrictType.AERODROME, None, (), placement=_flat_land),
    DistrictType.SPACEPORT: DistrictDef(DistrictType.SPACEPORT, None, (), placement=_flat_land),
    DistrictType.DIPLOMATIC_QUARTER: DistrictDef(DistrictType.DIPLOMATIC_QUARTER, None,
                                                 (_std_district_rule(),)),
    DistrictType.GOVERNMENT_PLAZA: DistrictDef(
        DistrictType.GOVERNMENT_PLAZA,
        None,
        # Government Plaza grants +1 (standard) to every adjacent district. That extra
        # +0.5 over the generic +0.5 source bonus is applied in adjacency.raw_adjacency
        # (GOVERNMENT_PLAZA_BONUS) so it benefits unique districts too.
        (_std_district_rule(),),
    ),
}


# The Government Plaza is a *standard* (+1) adjacency source, i.e. +0.5 MORE than the
# generic per-district minor bonus already counted for every district tile.
GOVERNMENT_PLAZA_EXTRA = 0.5


# --- unique districts (replace a standard district for one civ) ------------------
# Only civs whose unique district changes ADJACENCY/placement are modelled here; the
# rest keep the base district's adjacency (their bonus is flat yield / cheaper cost,
# captured as notes in CIVS). Numbers verified against the Civ 6 wiki.

def _always(_t: Tile) -> bool:
    return True


def _any_resource(t: Tile) -> bool:
    return t.resource is not None


def _hills_land(map: GameMap, coord: Hex, city: City) -> bool:
    # Seowon / Acropolis may only be built on Hills.
    t = map.get(coord)
    return t is not None and t.is_buildable_land and t.hills


# Seowon (Korea): inherent +4 Science, −1 per adjacent district (incl. City Center),
# ignores terrain. Hills only. Place AWAY from other districts, near farms/mines.
_SEOWON = DistrictDef(
    DistrictType.CAMPUS, YieldType.SCIENCE,
    (
        AdjRule("self", _always, 4.0, "inherent +4"),
        AdjRule("per_neighbor", _is_standard_district, -1.0, "−1 per adjacent district"),
    ),
    placement=_hills_land,
)

# Observatory (Maya): +2 per adjacent Plantation, +0.5 per adjacent Farm, +0.5 per
# district. NO mountain bonus — settle in farmland/plantations, not by mountains.
_OBSERVATORY = DistrictDef(
    DistrictType.CAMPUS, YieldType.SCIENCE,
    (
        AdjRule("per_neighbor", _improvement(Improvement.PLANTATION), 2.0, "plantation"),
        AdjRule("per_neighbor", _improvement(Improvement.FARM), 0.5, "farm"),
        _std_district_rule(),
    ),
)

# Acropolis (Greece): +1 Culture per adjacent district (full standard, not +0.5),
# +1 extra next to the City Center, +2 per adjacent World Wonder. Hills only.
_ACROPOLIS = DistrictDef(
    DistrictType.THEATER, YieldType.CULTURE,
    (
        AdjRule("per_neighbor", _is_standard_district, 1.0, "district (+1 each)"),
        AdjRule("per_neighbor", _district(DistrictType.CITY_CENTER), 1.0, "city center extra"),
        AdjRule("per_neighbor", lambda t: t.is_world_wonder, 2.0, "world wonder"),
    ),
    placement=_hills_land,
)

# Hansa (Germany): +2 per adjacent Commercial Hub, +1 per adjacent resource, +2 per
# Aqueduct/Dam/Canal, +0.5 per district. Pack next to Commercial Hub + Aqueduct.
_HANSA = DistrictDef(
    DistrictType.INDUSTRIAL_ZONE, YieldType.PRODUCTION,
    (
        AdjRule("per_neighbor",
                _district(DistrictType.AQUEDUCT, DistrictType.DAM, DistrictType.CANAL),
                2.0, "aqueduct/dam/canal"),
        AdjRule("per_neighbor", _district(DistrictType.COMMERCIAL_HUB), 2.0, "commercial hub"),
        AdjRule("per_neighbor", _any_resource, 1.0, "resource"),
        _std_district_rule(),
    ),
)

# Suguba (Mali): a Commercial Hub that also gains +2 Gold per adjacent Holy Site
# (in addition to river/harbor). Cluster Holy Sites + Suguba on a river.
_SUGUBA = DistrictDef(
    DistrictType.COMMERCIAL_HUB, YieldType.GOLD,
    (
        AdjRule("self", lambda t: t.on_river, 2.0, "river"),
        AdjRule("per_neighbor", _district(DistrictType.HARBOR), 2.0, "harbor"),
        AdjRule("per_neighbor", _district(DistrictType.HOLY_SITE), 2.0, "holy site"),
        _std_district_rule(),
    ),
)

UNIQUE_DISTRICTS: dict[str, dict[DistrictType, DistrictDef]] = {
    "korea":   {DistrictType.CAMPUS: _SEOWON},
    "maya":    {DistrictType.CAMPUS: _OBSERVATORY},
    "greece":  {DistrictType.THEATER: _ACROPOLIS},
    "germany": {DistrictType.INDUSTRIAL_ZONE: _HANSA},
    "mali":    {DistrictType.COMMERCIAL_HUB: _SUGUBA},
}


def resolve_def(dtype: DistrictType, civ: str | None = None) -> DistrictDef | None:
    """The DistrictDef in effect for ``dtype`` given the player's civ (unique override)."""
    if civ:
        unique = UNIQUE_DISTRICTS.get(civ)
        if unique and dtype in unique:
            return unique[dtype]
    return DISTRICTS.get(dtype)


# Districts the MVP optimizer can be asked to place (have a primary yield).
OPTIMIZABLE: tuple[DistrictType, ...] = (
    DistrictType.CAMPUS,
    DistrictType.HOLY_SITE,
    DistrictType.THEATER,
    DistrictType.COMMERCIAL_HUB,
    DistrictType.HARBOR,
    DistrictType.INDUSTRIAL_ZONE,
)
