"""Appeal mechanics (Gathering Storm): bands, Neighborhood housing, and the
eligibility of appeal-gated improvements (National Park / Seaside Resort).

Appeal of a tile is exported from the game (``plot:GetAppeal()``). It drives:
  * **Neighborhood** housing (the main late-game housing lever),
  * **Preserve** yields (modelled in rules.districts),
  * **National Park** (needs a vertical 1x3 of Charming+ natural tiles),
  * **Seaside Resort** (needs a Breathtaking coast tile),
  * tourism from Wonders/Seaside Resorts.

Numbers follow the community wiki; the exact band cut-offs vary slightly between
sources, so they are kept here in one place and flagged approximate.
"""

from __future__ import annotations

from ..domain.models import Tile

# Appeal bands (lower bound -> name). Standard Civ 6 cut-offs.
BREATHTAKING = 4
CHARMING = 2
AVERAGE = -1
UNINVITING = -4
# below UNINVITING -> Disgusting


def band(appeal: int) -> str:
    if appeal >= BREATHTAKING:
        return "breathtaking"
    if appeal >= CHARMING:
        return "charming"
    if appeal >= AVERAGE:
        return "average"
    if appeal >= UNINVITING:
        return "uninviting"
    return "disgusting"


BAND_LABEL_RU: dict[str, str] = {
    "breathtaking": "захватывающая",
    "charming": "очаровательная",
    "average": "средняя",
    "uninviting": "невзрачная",
    "disgusting": "отвратительная",
}

# Neighborhood housing by appeal band (Gathering Storm).
_NEIGHBORHOOD_HOUSING: dict[str, int] = {
    "breathtaking": 6,
    "charming": 5,
    "average": 4,
    "uninviting": 3,
    "disgusting": 2,
}


def neighborhood_housing(appeal: int) -> int:
    """Housing a Neighborhood built on a tile of this appeal would provide (GS)."""
    return _NEIGHBORHOOD_HOUSING[band(appeal)]


def best_neighborhood_tile(appeal_values: list[int]) -> int:
    """Best Neighborhood housing achievable given the appeals of candidate tiles."""
    return max((neighborhood_housing(a) for a in appeal_values), default=4)


def seaside_resort_ok(t: Tile) -> bool:
    """Seaside Resort needs a flat Breathtaking Coast tile (no district/feature)."""
    return (
        t.terrain.value == "coast"
        and t.appeal >= BREATHTAKING
        and t.district is None
        and t.feature.value in ("none", "reef")
    )


def national_park_candidate(t: Tile) -> bool:
    """A tile that could be part of a National Park: Charming+ natural land."""
    return (
        t.appeal >= CHARMING
        and t.district is None
        and t.wonder is None
        and t.terrain.value in ("grassland", "plains", "tundra", "desert", "snow", "mountain")
    )
