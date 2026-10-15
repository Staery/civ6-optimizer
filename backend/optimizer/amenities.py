"""Estimate each city's Amenity (довольство) balance and advise how to reach surplus.

Civ 6 (Gathering Storm) model used here:
  * **required** Amenities = floor((population - 1) / 2)  — 1 per 2 pop, from pop 3.
  * **supply** (modelled): distinct luxuries that reach the city + an Entertainment
    Complex / Water Park in the city. Each distinct luxury gives +1 Amenity to your
    **4 highest-population cities** — so a wide empire's 5th+ cities get none from
    luxuries (the classic happiness squeeze). Wonders/policies/religion are noted,
    not auto-counted.
  * **state** by surplus = supply − required (exact thresholds per the in-game
    tooltip; community sources vary slightly):
      ≥ +3  Ecstatic   → +10% non-food yields, +20% growth
      +1/+2 Happy      → +5% non-food yields, +10% growth
        0   Content    → neutral
      −1/−2 Displeased → −15% growth
      −3/−4 Unhappy    → −30% growth, −loyalty
      ≤ −5  Unrest/Revolt → growth stops, rebels appear

Goal (per the user / guides): keep every city **out of deficit** and push the key
cities to **Ecstatic** for the yield/growth bonuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import tr
from ..domain.models import City, DistrictType, GameMap
from .empire import assign_territory
from .settle import LUXURIES

_STATE_RU = {
    "ecstatic": "Восторг (+10% выходов, +20% роста)",
    "happy": "Счастье (+5% выходов, +10% роста)",
    "content": "Доволен (нейтрально)",
    "displeased": "Недоволен (−15% роста)",
    "unhappy": "Несчастен (−30% роста)",
    "unrest": "Волнения (рост остановлен, мятежники)",
    "revolt": "Восстание",
}


def _state(surplus: float) -> str:
    if surplus >= 3:
        return "ecstatic"
    if surplus >= 1:
        return "happy"
    if surplus >= 0:
        return "content"
    if surplus >= -2:
        return "displeased"
    if surplus >= -4:
        return "unhappy"
    if surplus >= -9:
        return "unrest"
    return "revolt"


@dataclass
class CityAmenities:
    city: str
    population: int
    required: int
    supply: float
    surplus: float
    state: str
    state_label: str
    advice: list[str] = field(default_factory=list)


def estimate_amenities(
    map: GameMap, cities: list[City], loadout=None
) -> list[CityAmenities]:
    owner = assign_territory(map, cities)        # Hex -> city index
    lux_by_city: list[set[str]] = [set() for _ in cities]
    ent_by_city: list[int] = [0 for _ in cities]
    holy_river: list[bool] = [False for _ in cities]   # River Goddess: Holy Site touching a river
    empire_lux: set[str] = set()

    for h, ci in owner.items():
        t = map.get(h)
        if t is None:
            continue
        if t.resource and t.resource in LUXURIES:
            lux_by_city[ci].add(t.resource)
            empire_lux.add(t.resource)
        if t.district in (DistrictType.ENTERTAINMENT, DistrictType.WATER_PARK):
            ent_by_city[ci] += 1
        elif t.district is DistrictType.HOLY_SITE and t.on_river:
            holy_river[ci] = True

    # luxuries benefit only the 4 highest-population cities
    order = sorted(range(len(cities)), key=lambda i: cities[i].population, reverse=True)
    top4 = set(order[:4])

    # Liang (Parks & Recreation): +1 Amenity in a city that has an Entertainment/Water Park.
    from ..rules.modifiers import GOVERNORS
    _gov = GOVERNORS.get(getattr(loadout, "governor", None) or "") if loadout else None
    liang_amen = _gov.amenity if _gov else 0
    river_goddess = bool(loadout and getattr(loadout, "pantheon", None) == "river_goddess")

    out: list[CityAmenities] = []
    for i, c in enumerate(cities):
        pop = c.population
        required = max(0, (pop - 1) // 2) if pop > 0 else 0
        lux_amen = len(empire_lux) if i in top4 else 0
        ent_amen = 1 if ent_by_city[i] else 0       # Arena / Ferris Wheel ≈ +1 (buildings add more)
        gov_amen = liang_amen if ent_by_city[i] else 0   # Liang boosts the entertainment district
        rg_amen = 2 if (river_goddess and holy_river[i]) else 0   # River Goddess: Holy Site on a river
        supply = lux_amen + ent_amen + gov_amen + rg_amen
        surplus = supply - required
        st = _state(surplus) if pop > 0 else "content"

        advice: list[str] = []
        if pop <= 0:
            advice.append("население неизвестно (ручная карта) — оценка ориентировочная")
        if i not in top4 and len(cities) > 4:
            advice.append("это не входит в 4 самых населённых города — предметы роскоши его НЕ "
                          "покрывают; нужны Парк развлечений/Аквапарк, заповедники, политики/религия")
        if surplus < 0:
            advice.append(tr("дефицит {n} — построй Парк развлечений (Арена) или Аквапарк, "
                             "добудь новые предметы роскоши, или чудо (Колизей +3 в радиусе 6)",
                             n=abs(surplus)))
        elif surplus < 3 and pop > 0:
            advice.append(tr("до Восторга не хватает {n} довольства "
                             "(+10% нежёлтые выходы, +20% рост) — добавь источник довольства",
                             n=3 - surplus))
        else:
            advice.append("цель достигнута — Восторг даёт +10% выходов и +20% роста")

        out.append(CityAmenities(
            city=c.name, population=pop, required=required, supply=float(supply),
            surplus=float(surplus), state=st, state_label=_STATE_RU[st], advice=advice,
        ))
    return out
