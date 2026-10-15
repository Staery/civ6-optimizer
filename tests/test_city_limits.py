"""Population-based district cap (used for build-order planning, not dropping districts)."""

from backend.domain.models import DistrictType
from backend.rules.city_limits import (
    counts_toward_cap,
    district_cap,
    pop_to_unlock,
)


def test_cap_grows_every_three_population():
    assert district_cap(1) == 1
    assert district_cap(3) == 1
    assert district_cap(4) == 2
    assert district_cap(6) == 2
    assert district_cap(7) == 3
    assert district_cap(10) == 4


def test_unknown_population_is_zero():
    assert district_cap(0) == 0      # caller treats 0 as 'no limit info'


def test_pop_to_unlock_thresholds():
    assert pop_to_unlock(1) == 1
    assert pop_to_unlock(2) == 4
    assert pop_to_unlock(3) == 7
    assert pop_to_unlock(4) == 10


def test_infrastructure_districts_are_uncapped():
    for d in (DistrictType.AQUEDUCT, DistrictType.DAM, DistrictType.CANAL,
              DistrictType.NEIGHBORHOOD, DistrictType.SPACEPORT, DistrictType.CITY_CENTER):
        assert not counts_toward_cap(d)
    for d in (DistrictType.CAMPUS, DistrictType.HOLY_SITE, DistrictType.COMMERCIAL_HUB,
              DistrictType.INDUSTRIAL_ZONE, DistrictType.HARBOR, DistrictType.THEATER):
        assert counts_toward_cap(d)
