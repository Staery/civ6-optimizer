"""Estimate each city's Housing budget vs population and advise how to keep growing.

Housing caps population growth in Civ 6 (Gathering Storm): growth slows as
population approaches Housing and stops when it reaches it. This module gives an
**approximate** supply estimate from data we can see in the export (city-center
water, tile improvements, Aqueduct/Dam/Neighborhood districts) and flags the
growth state, plus the Neighborhood housing available from the city's best-appeal
tile (the main late-game lever — see :mod:`backend.rules.appeal`).

Buildings we can't see (Granary/Sewer/etc.) are noted, not auto-counted, so the
estimate is a conservative floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import tr
from ..domain.models import City, DistrictType, Feature, GameMap, Improvement, Terrain
from ..rules.appeal import band, BAND_LABEL_RU, neighborhood_housing
from .empire import assign_territory

# Improvements that each add +0.5 Housing (GS, after the relevant techs).
_HOUSING_IMPROVEMENTS = frozenset({
    Improvement.FARM, Improvement.PASTURE, Improvement.PLANTATION, Improvement.FISHING_BOATS,
})


def _center_base_housing(map: GameMap, c: City) -> tuple[float, str]:
    """City-center housing from water: fresh water 5, coast 3, otherwise 2.

    Fresh water = a river on the center tile's own edge (on_river), or the center is
    adjacent to a Lake/Oasis. (A neighbour merely touching a river elsewhere does NOT
    count — see settle._is_fresh_water_site.)
    """
    t = map.get(c.center)
    nbrs = map.neighbors(c.center)
    own_fresh = t is not None and (t.on_river or t.feature is Feature.OASIS)
    adj_fresh = any(n.terrain is Terrain.LAKE or n.feature is Feature.OASIS for n in nbrs)
    if own_fresh or adj_fresh:
        return 5.0, "пресная вода (5)"
    if t is not None and (t.terrain in (Terrain.COAST, Terrain.LAKE)
                          or any(n.terrain.is_water for n in nbrs)):
        return 3.0, "побережье (3)"
    return 2.0, "без воды (2)"


def _growth_state(surplus: float) -> tuple[str, str]:
    if surplus >= 5:
        return "growing", "свободный рост"
    if surplus >= 2:
        return "slowing", "рост замедлен (−50%)"
    if surplus >= 0:
        return "capped", "рост почти остановлен"
    return "shrinking", "убыль населения (голод)"


@dataclass
class CityHousing:
    city: str
    population: int
    supply: float
    surplus: float
    state: str
    state_label: str
    best_neighborhood: int           # housing a Neighborhood on the best-appeal tile would add
    best_neighborhood_band: str
    advice: list[str] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)


def _governor_appeal(loadout) -> int:
    """Liang (Parks & Recreation) adds appeal to the city's tiles -> better Neighborhoods."""
    from ..rules.modifiers import GOVERNORS

    g = GOVERNORS.get(getattr(loadout, "governor", None) or "") if loadout else None
    return g.appeal if g else 0


def estimate_housing(map: GameMap, cities: list[City], loadout=None) -> list[CityHousing]:
    owner = assign_territory(map, cities)        # Hex -> city index
    gov_appeal = _governor_appeal(loadout)

    imp_by_city: list[float] = [0.0 for _ in cities]
    aqueduct: list[bool] = [False for _ in cities]
    dam: list[bool] = [False for _ in cities]
    neighborhoods: list[int] = [0 for _ in cities]
    best_appeal: list[int] = [-99 for _ in cities]
    holy_river: list[bool] = [False for _ in cities]   # River Goddess: Holy Site touching a river

    for h, ci in owner.items():
        t = map.get(h)
        if t is None:
            continue
        if t.improvement in _HOUSING_IMPROVEMENTS:
            imp_by_city[ci] += 0.5
        if t.district is DistrictType.AQUEDUCT:
            aqueduct[ci] = True
        elif t.district is DistrictType.DAM:
            dam[ci] = True
        elif t.district is DistrictType.NEIGHBORHOOD:
            neighborhoods[ci] += 1
        elif t.district is DistrictType.HOLY_SITE and t.on_river:
            holy_river[ci] = True
        # track the best buildable-appeal tile for a future Neighborhood
        if t.district is None and t.terrain.is_land and t.appeal > best_appeal[ci]:
            best_appeal[ci] = t.appeal

    river_goddess = bool(loadout and getattr(loadout, "pantheon", None) == "river_goddess")

    out: list[CityHousing] = []
    for i, c in enumerate(cities):
        pop = c.population
        base, base_note = _center_base_housing(map, c)
        # Aqueduct/Dam guarantee fresh-water housing and add a bit more.
        util = 0.0
        if aqueduct[i]:
            base = max(base, 6.0)
        if dam[i]:
            util += 1.0
        # River Goddess pantheon: +2 Housing if a Holy Site touches a river.
        if river_goddess and holy_river[i]:
            util += 2.0
        imp = imp_by_city[i]
        nb_housing = float(sum(neighborhood_housing(0) for _ in range(neighborhoods[i])))
        supply = base + util + imp + nb_housing
        surplus = supply - pop if pop > 0 else supply
        state, state_label = _growth_state(surplus)

        ba = (best_appeal[i] if best_appeal[i] > -99 else 0) + gov_appeal  # Liang +appeal
        best_nb = neighborhood_housing(ba)

        advice: list[str] = []
        if pop <= 0:
            advice.append("население неизвестно (ручная карта) — оценка ориентировочная")
        if not aqueduct[i] and base < 6.0:
            advice.append("построй Акведук — поднимет жильё до 6 (если у города нет пресной воды)")
        if pop > 0 and surplus < 5:
            advice.append(
                tr("скоро упрётся в жильё — добавь Квартал на «{band}» клетке "
                   "(+{housing} жилья), фермы/плантации, Канализацию",
                   band=BAND_LABEL_RU[band(ba)], housing=best_nb)
            )
        if dam[i] is False and any(
            map.get(h) and map.get(h).feature.value == "floodplains"
            for h in owner if owner[h] == i
        ):
            advice.append("есть поймы — Дамба добавит жильё и защитит от затоплений")
        if not advice:
            advice.append("жильё в порядке — рост не ограничен")

        out.append(CityHousing(
            city=c.name, population=pop, supply=round(supply, 1),
            surplus=round(surplus, 1), state=state, state_label=state_label,
            best_neighborhood=best_nb, best_neighborhood_band=band(ba),
            advice=advice,
            breakdown={
                "center": base, "utility(dam)": util,
                "improvements": round(imp, 1), "neighborhoods": nb_housing,
            },
        ))
    return out
