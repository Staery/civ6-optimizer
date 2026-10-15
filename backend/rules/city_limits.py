"""Population-based district limit (Civ 6) — used to plan a build ORDER, not to drop
districts. We still lay out every planned district ("на вырост" — reserve the best
tiles); this just says how many a city may build at its current population and when
the rest unlock.

Rule: a city may build its 1st capped specialty district at population 1, then one
more for every +3 population (pop 4, 7, 10, …). So the cap = (pop + 2) // 3.

Some districts do NOT count toward this cap (infrastructure you can always build):
City Center, Aqueduct, Neighborhood, Canal, Dam, Spaceport.
"""

from __future__ import annotations

from ..domain.models import DistrictType

UNCAPPED_DISTRICTS: frozenset[DistrictType] = frozenset({
    DistrictType.CITY_CENTER,
    DistrictType.AQUEDUCT,
    DistrictType.NEIGHBORHOOD,
    DistrictType.CANAL,
    DistrictType.DAM,
    DistrictType.SPACEPORT,
    DistrictType.GOVERNMENT_PLAZA,    # special districts that don't count toward the
    DistrictType.DIPLOMATIC_QUARTER,  # population-based district limit in Civ 6
})


def counts_toward_cap(dtype: DistrictType) -> bool:
    return dtype not in UNCAPPED_DISTRICTS


def district_cap(population: int) -> int:
    """How many *capped* specialty districts a city of this population may build.

    Returns 0 when population is unknown (<=0) so callers can treat it as 'no limit
    info' rather than a real limit of zero.
    """
    if population <= 0:
        return 0
    return (population + 2) // 3


def pop_to_unlock(n: int) -> int:
    """Population needed to build the n-th capped district (n is 1-based): 1, 4, 7, 10…"""
    return 3 * n - 2
