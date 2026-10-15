"""Core domain models: terrain/feature/resource enums and map/city/district types.

Ruleset target: **Gathering Storm + New Frontier Pass**. Values that need to be
double-checked against the community Adjacency Planner are flagged ``VALIDATE:``
in :mod:`backend.rules.districts`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .hexgrid import Hex


class Terrain(str, Enum):
    GRASSLAND = "grassland"
    PLAINS = "plains"
    DESERT = "desert"
    TUNDRA = "tundra"
    SNOW = "snow"
    MOUNTAIN = "mountain"
    COAST = "coast"      # shallow water
    OCEAN = "ocean"      # deep water
    LAKE = "lake"

    @property
    def is_water(self) -> bool:
        return self in (Terrain.COAST, Terrain.OCEAN, Terrain.LAKE)

    @property
    def is_land(self) -> bool:
        return not self.is_water and self is not Terrain.MOUNTAIN


class Feature(str, Enum):
    NONE = "none"
    WOODS = "woods"
    RAINFOREST = "rainforest"
    MARSH = "marsh"
    FLOODPLAINS = "floodplains"
    OASIS = "oasis"
    REEF = "reef"
    ICE = "ice"
    GEOTHERMAL_FISSURE = "geothermal_fissure"
    VOLCANIC_SOIL = "volcanic_soil"
    NATURAL_WONDER = "natural_wonder"


class Improvement(str, Enum):
    NONE = "none"
    MINE = "mine"
    QUARRY = "quarry"
    FARM = "farm"
    PASTURE = "pasture"
    PLANTATION = "plantation"
    LUMBER_MILL = "lumber_mill"
    FISHING_BOATS = "fishing_boats"


class DistrictType(str, Enum):
    CITY_CENTER = "city_center"
    CAMPUS = "campus"
    HOLY_SITE = "holy_site"
    THEATER = "theater_square"
    COMMERCIAL_HUB = "commercial_hub"
    HARBOR = "harbor"
    INDUSTRIAL_ZONE = "industrial_zone"
    AQUEDUCT = "aqueduct"
    DAM = "dam"
    CANAL = "canal"
    ENTERTAINMENT = "entertainment_complex"
    WATER_PARK = "water_park"
    ENCAMPMENT = "encampment"
    GOVERNMENT_PLAZA = "government_plaza"
    NEIGHBORHOOD = "neighborhood"
    AERODROME = "aerodrome"
    SPACEPORT = "spaceport"
    PRESERVE = "preserve"
    DIPLOMATIC_QUARTER = "diplomatic_quarter"


class YieldType(str, Enum):
    FOOD = "food"
    PRODUCTION = "production"
    GOLD = "gold"
    SCIENCE = "science"
    CULTURE = "culture"
    FAITH = "faith"
    HOUSING = "housing"
    AMENITIES = "amenities"


# Yields combine as a simple mapping. Adjacency for a district contributes to its
# *primary* yield, but modifiers (beliefs/civs) may add others, hence a dict.
Yields = dict[YieldType, float]


def add_yields(a: Yields, b: Yields) -> Yields:
    out: Yields = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0.0) + v
    return out


@dataclass
class Tile:
    coord: Hex
    terrain: Terrain = Terrain.GRASSLAND
    feature: Feature = Feature.NONE
    hills: bool = False
    on_river: bool = False          # tile touches a river (simplified river model)
    river_edges: int | None = None  # how many of the 6 tile edges a river crosses (Dam rule);
    #                                 None = unknown (manual map / old export) -> approximated
    resource: str | None = None
    resource_class: str | None = None  # "bonus" | "luxury" | "strategic" | None
    resource_revealed: bool | None = None  # strategic: revealed by tech? None = unknown
    improvement: Improvement = Improvement.NONE
    appeal: int = 0
    wonder: str | None = None        # a built World Wonder occupies this tile
    natural_wonder: str | None = None  # specific Natural Wonder key (multi-tile -> same key)
    district: DistrictType | None = None
    owner_city: str | None = None    # name of the city that owns this tile
    volcano: bool = False            # an (impassable) volcano mountain — eruptions enrich/damage neighbours

    @property
    def is_natural_wonder(self) -> bool:
        return (
            self.feature is Feature.NATURAL_WONDER
            or self.natural_wonder is not None
            or (self.wonder is not None and self.wonder.startswith("nw:"))
        )

    @property
    def is_world_wonder(self) -> bool:
        return self.wonder is not None and not self.wonder.startswith("nw:")

    @property
    def has_district(self) -> bool:
        return self.district is not None

    @property
    def is_fresh_water(self) -> bool:
        """Fresh-water source for Aqueduct/housing purposes (the tile itself)."""
        return (
            self.on_river
            or self.terrain is Terrain.LAKE
            or self.feature is Feature.OASIS
        )

    @property
    def _resource_blocks_district(self) -> bool:
        """Luxury resources block districts (can't be removed). A Strategic resource blocks
        only once its reveal tech is researched — before that you may build over it and keep
        access (so unknown/unrevealed strategics do NOT block, enabling plan-ahead). Bonus
        resources never block (the district just removes them)."""
        if self.resource_class == "luxury":
            return True
        if self.resource_class == "strategic":
            return self.resource_revealed is True
        return False

    @property
    def is_buildable_land(self) -> bool:
        """Can a standard land district physically go here?"""
        return (
            self.terrain.is_land
            and self.feature is not Feature.NATURAL_WONDER
            and self.wonder is None
            and self.district is None
            and not self._resource_blocks_district
        )


@dataclass
class GameMap:
    tiles: dict[Hex, Tile] = field(default_factory=dict)
    ruleset: str = "gathering_storm_nfp"

    def get(self, coord: Hex) -> Tile | None:
        return self.tiles.get(coord)

    def set(self, tile: Tile) -> None:
        self.tiles[tile.coord] = tile

    def neighbors(self, coord: Hex) -> list[Tile]:
        return [self.tiles[n] for n in coord.neighbors() if n in self.tiles]


@dataclass
class City:
    name: str
    center: Hex
    work_radius: int = 3
    # Districts to be placed by the optimizer (excludes already-built ones).
    requested: list[DistrictType] = field(default_factory=list)
    population: int = 0          # 0 = unknown (manual map); used to estimate Amenities
