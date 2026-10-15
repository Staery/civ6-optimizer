"""Approximate full building yields per district (the part that ISN'T adjacency).

Adjacency is only a fraction of a district's value — most of it comes from its
buildings (Library+University+Research Lab, Market+Bank+Stock Exchange, …). These
are flat (they don't depend on the tile), so they do NOT change *where* a district
goes; we add them only to report a more honest "full" value and to help rank which
district to build first.

Numbers are a representative late-game base set (no policies/wonders/great people),
so treat them as planning estimates, not exact values.
"""

from __future__ import annotations

from ..domain.models import DistrictType, YieldType, Yields

F, P, G = YieldType.FOOD, YieldType.PRODUCTION, YieldType.GOLD
S, C, FA = YieldType.SCIENCE, YieldType.CULTURE, YieldType.FAITH
H, A = YieldType.HOUSING, YieldType.AMENITIES

BUILDING_YIELDS: dict[DistrictType, Yields] = {
    DistrictType.CAMPUS: {S: 6.0},                     # Library + University + Research Lab
    DistrictType.HOLY_SITE: {FA: 5.0},                 # Shrine + Temple + Worship building
    DistrictType.THEATER: {C: 6.0},                    # Amphitheater + Museum + Broadcast Center
    DistrictType.COMMERCIAL_HUB: {G: 8.0},             # Market + Bank + Stock Exchange
    DistrictType.HARBOR: {G: 5.0, F: 1.0, H: 1.0},     # Lighthouse + Shipyard + Seaport
    DistrictType.INDUSTRIAL_ZONE: {P: 6.0},            # Workshop + Factory + Power Plant
    DistrictType.ENCAMPMENT: {P: 2.0, H: 1.0},
    DistrictType.AQUEDUCT: {H: 6.0},                   # up to +6 housing
    DistrictType.ENTERTAINMENT: {A: 2.0},              # Arena + Zoo + Stadium (amenities)
    DistrictType.WATER_PARK: {A: 2.0},
    DistrictType.NEIGHBORHOOD: {H: 4.0},               # appeal-based housing (approx)
}


def building_yields(dtype: DistrictType) -> Yields:
    return dict(BUILDING_YIELDS.get(dtype, {}))
