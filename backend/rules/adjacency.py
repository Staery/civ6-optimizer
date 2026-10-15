"""Adjacency evaluation: how much yield a district produces on a given tile."""

from __future__ import annotations

import math

from ..domain.hexgrid import Hex
from ..domain.models import City, DistrictType, GameMap, YieldType, Yields
from .districts import DISTRICTS, resolve_def
from .modifiers import Loadout


def can_place(
    map: GameMap, coord: Hex, dtype: DistrictType, city: City, loadout=None
) -> bool:
    """True if ``dtype`` may be physically placed on ``coord`` for ``city``.

    ``loadout`` lets civ abilities add placement constraints (e.g. Gaul forbids
    districts adjacent to the City Center, Korea's Seowon needs Hills).
    """
    ddef = resolve_def(dtype, loadout.civ if loadout else None)
    if ddef is None or not ddef.placement(map, coord, city):
        return False
    if loadout is not None:
        for m in loadout.modifiers_for(dtype):
            if m.forbid_adj_city_center and any(
                n.coord == city.center for n in map.neighbors(coord)
            ):
                return False
    return True


def raw_adjacency(
    map: GameMap, coord: Hex, dtype: DistrictType, civ: str | None = None
) -> float:
    """Base adjacency in the district's primary yield, before modifiers.

    Returns a raw float (e.g. 1.5). The in-game displayed bonus is ``floor`` of this.
    ``civ`` selects a unique-district override (Seowon/Hansa/Suguba/…).
    """
    ddef = resolve_def(dtype, civ)
    if ddef is None or ddef.primary_yield is None:
        return 0.0
    center = map.get(coord)
    if center is None:
        return 0.0
    neighbors = map.neighbors(coord)
    total = 0.0
    for rule in ddef.rules:
        if rule.kind == "per_neighbor":
            total += rule.amount * sum(1 for n in neighbors if rule.predicate(n))
        elif rule.kind == "presence":
            if any(rule.predicate(n) for n in neighbors):
                total += rule.amount
        elif rule.kind == "self":
            if rule.predicate(center):
                total += rule.amount
    # Government Plaza is a STANDARD (+1) adjacency source — +0.5 more than the generic
    # per-district minor bonus already counted above for any adjacent district tile.
    from .districts import GOVERNMENT_PLAZA_EXTRA

    total += GOVERNMENT_PLAZA_EXTRA * sum(
        1 for n in neighbors if n.district is DistrictType.GOVERNMENT_PLAZA
    )
    # natural-wonder-specific extra adjacency (beyond the generic Holy Site +2,
    # which is already counted per adjacent natural-wonder tile by the rules above)
    dval = dtype.value
    for n in neighbors:
        if n.natural_wonder:
            from .natural_wonders import NW_BY_KEY

            nw = NW_BY_KEY.get(n.natural_wonder)
            if nw and nw.extra_adj:
                total += nw.extra_adj.get(dval, 0.0)
    return total


def adjacency_yield(
    map: GameMap,
    coord: Hex,
    dtype: DistrictType,
    loadout: Loadout | None = None,
) -> Yields:
    """Yields produced by placing ``dtype`` at ``coord`` (modifiers applied)."""
    civ = loadout.civ if loadout else None
    ddef = resolve_def(dtype, civ)
    if ddef is None or ddef.primary_yield is None:
        return {}
    value = raw_adjacency(map, coord, dtype, civ)
    if loadout is not None:
        mult = 1.0
        flat = 0.0
        delta = 0.0
        river = 0.0
        mine = 0.0
        appeal = 0.0
        neighbor_terms: list[tuple[str, float]] = []
        for m in loadout.modifiers_for(dtype):
            mult *= m.adjacency_multiplier
            flat += m.adjacency_flat
            delta += m.district_adj_delta
            river += m.river_bonus
            mine += m.mine_adj
            appeal += m.self_appeal_adj
            if m.neighbor_adj[0]:
                neighbor_terms.append(m.neighbor_adj)
        value = value * mult + flat
        for token, amount in neighbor_terms:        # pantheons: +X per matching neighbour
            kind, _, name = token.partition(":")
            for n in map.neighbors(coord):
                if (kind == "terrain" and n.terrain.value == name) or \
                   (kind == "feature" and n.feature.value == name):
                    value += amount
        ct = map.get(coord)
        if river and ct is not None and ct.on_river:
            value += river
        if mine:
            value += mine * sum(
                1 for n in map.neighbors(coord)
                if n.improvement.value in ("mine", "quarry")
            )
        if appeal and ct is not None:
            if ct.appeal >= 4:
                value += appeal * 2  # breathtaking
            elif ct.appeal >= 2:
                value += appeal      # charming
        if delta:
            # extra yield per adjacent (standard) district, e.g. Japan's Meiji Restoration
            from .districts import STANDARD_ADJ_DISTRICTS

            cnt = sum(
                1 for n in map.neighbors(coord) if n.district in STANDARD_ADJ_DISTRICTS
            )
            value += delta * cnt
    result = {ddef.primary_yield: value}
    # Work Ethic (follower belief): a Holy Site also yields PRODUCTION equal to its
    # Faith adjacency — so the optimizer values high-adjacency Holy Sites for production.
    if (loadout is not None and dtype is DistrictType.HOLY_SITE
            and "work_ethic" in (loadout.religion_beliefs or [])):
        result[YieldType.PRODUCTION] = result.get(YieldType.PRODUCTION, 0.0) + value
    # Theodora (Byzantium) "Metanoia": a Holy Site also yields CULTURE equal to its Faith
    # adjacency — so the optimizer values high-adjacency Holy Sites for culture too.
    if (loadout is not None and dtype is DistrictType.HOLY_SITE
            and getattr(loadout, "leader", "") == "theodora"):
        result[YieldType.CULTURE] = result.get(YieldType.CULTURE, 0.0) + value
    return result


def displayed_adjacency(value: float) -> int:
    """In-game shown adjacency value (floor of the accumulated total)."""
    return math.floor(value + 1e-9)


def weighted_score(yields: Yields, loadout: Loadout | None) -> float:
    """Collapse a yield dict to a single objective score using loadout weights."""
    if not yields:
        return 0.0
    if loadout is None:
        return sum(yields.values())
    return sum(loadout.weight(y) * v for y, v in yields.items())
