"""Recommend WHICH governor to assign to WHICH city.

In Civ 6 a governor is established in one city and works only there, so a single
empire-wide pick is unrealistic. Instead we score every (governor, city) pair from
the city's character (its districts, coast, population, housing/amenity pressure) and
the player's victory weights, then greedily hand each unique governor to its best
city. Output is advice shown per city — it does not move districts.

Each governor is unique (you own at most one Pingala), so the assignment is 1:1.
Cities left without a governor are fine — governors unlock gradually via titles.
"""

from __future__ import annotations

from typing import Any

from ..i18n import translate

# short display names (the long flavour notes live in modifiers.GOVERNORS)
GOV_LABEL = {
    "pingala": "Пингала",
    "magnus": "Магнус",
    "liang": "Лян",
    "reyna": "Рейна",
    "moksha": "Мокша",
}

# the order we try to seat governors when scores tie / for the headline pick
GOV_ORDER = ("pingala", "magnus", "liang", "reyna", "moksha")


def _score(gov: str, f: dict[str, Any], w: dict[str, float]) -> tuple[float, str]:
    """Return (score, reason) for seating `gov` in the city described by `f`."""
    d = f["districts"]                       # set[str] of district values (built + planned)
    pop = f.get("pop", 0) or 0
    coastal = f.get("coastal", False)
    house = f.get("housing_surplus")
    amen = f.get("amenity_surplus")
    big = pop >= 6
    main = f.get("is_main", False)           # highest-population city ~ capital

    if gov == "pingala":
        sci = "campus" in d
        cul = "theater_square" in d
        sc = 1.0 + (1.6 if sci else 0) + (1.2 if cul else 0) + pop * 0.12
        sc += (w.get("science", 1) + w.get("culture", 1) - 2) * 0.8
        if main:
            sc += 1.0
        bits = [translate(x) for x, ok in (("Кампус", sci), ("Театр", cul)) if ok]
        why = (translate("наука/культура — ") + ("+".join(bits) if bits else translate("крупнейший город"))
               + (translate(", великие люди и +30% к космопроектам") if big else ""))
        return sc, why

    if gov == "magnus":
        iz = "industrial_zone" in d
        sc = 0.8 + (2.0 if iz else 0) + (w.get("production", 1) - 1) * 1.2
        if main and not iz:
            sc += 0.6
        why = (translate("производство — ") + translate("Промзона, хаб для чудес и юнитов" if iz
               else "город под чудеса/поселенцев (Провизия — поселенцы без потери населения)"))
        return sc, why

    if gov == "liang":
        many = len(d) >= 4
        tight = (house is not None and house < 3) or (amen is not None and amen < 0)
        sc = 0.6 + (1.6 if tight else 0) + (1.0 if many else 0)
        why_bits = []
        if tight:
            why_bits.append("дефицит жилья/довольства")
        if many:
            why_bits.append("много районов (+20% к стройке)")
        why = translate("районы/привлекательность — ") + translate(", ".join(why_bits) or "Парки и отдых: +привлекательность")
        return sc, why

    if gov == "reyna":
        trade = "commercial_hub" in d or "harbor" in d
        sc = 0.5 + (1.4 if coastal else 0) + (1.4 if trade else 0) + (w.get("gold", 1) - 1) * 1.0
        why = (translate("золото — ") + translate("побережье + Гавань/Ком.хаб, покупка районов/клеток" if trade or coastal
               else "торговый город"))
        return sc, why

    if gov == "moksha":
        holy = "holy_site" in d
        sc = 0.4 + (2.0 if holy else 0) + (w.get("faith", 1) - 1) * 1.4
        why = translate("вера — ") + translate("Святое место, покупка верой и распространение религии" if holy
                                           else "религиозный центр")
        return sc, why

    return 0.0, ""


def assign_governors(features: list[dict[str, Any]], weights: dict[str, float],
                     ) -> dict[str, dict[str, Any]]:
    """Greedy 1:1 assignment of governors to cities.

    `features` — one dict per city: {"city","districts":set[str],"coastal":bool,
    "pop":int,"housing_surplus":float|None,"amenity_surplus":float|None,"is_main":bool}.
    Returns city name -> {"governor","label","reason"} (only cities that got one).
    """
    # mark the highest-population city as "main" (capital-like) for tie-breaking
    if features:
        top = max(features, key=lambda f: f.get("pop", 0) or 0)
        for f in features:
            f["is_main"] = f is top

    # all candidate (score, city, gov, reason), strongest first
    cand: list[tuple[float, str, str, str]] = []
    for f in features:
        for gov in GOV_ORDER:
            sc, why = _score(gov, f, weights)
            cand.append((sc, f["city"], gov, why))
    cand.sort(key=lambda t: t[0], reverse=True)

    out: dict[str, dict[str, Any]] = {}
    used_gov: set[str] = set()
    for sc, city, gov, why in cand:
        if city in out or gov in used_gov:
            continue
        if sc <= 0:
            continue
        out[city] = {"governor": gov, "label": GOV_LABEL[gov], "reason": why}
        used_gov.add(gov)
        if len(used_gov) == len(GOV_ORDER):
            break
    return out
