"""World Wonder recommender.

For each catalogue wonder not already taken, find the best valid empty tile inside
your territory, rank by curated value, and report an AI-race risk plus alternative
tiles (plan B). Wonders already present on the map (built by anyone) are detected
and excluded automatically; the caller may also pass a manual ``taken`` list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.hexgrid import Hex, within_radius
from ..domain.models import City, Feature, GameMap, Tile
from ..rules.wonders import ERA_RISK, WONDERS
from .empire import is_foreign
from .settle import _tile_value


@dataclass
class WonderRec:
    key: str
    name: str
    era: str
    q: int
    r: int
    value: float
    requires: str
    note: str
    risk: str
    alternatives: list[dict] = field(default_factory=list)


def _empty(t: Tile) -> bool:
    return (
        t.district is None
        and t.wonder is None
        and t.feature is not Feature.NATURAL_WONDER
    )


def _own_tiles(map: GameMap, cities: list[City]) -> set[Hex]:
    # Never offer a wonder ON a city centre — you can't build there. This also covers
    # PLANNED new cities, whose centre tile is still empty on the map (otherwise a wonder
    # would be recommended on the exact tile where the new city will be founded).
    centers = {c.center for c in cities}
    tiles: set[Hex] = set()
    for c in cities:
        for h in within_radius(c.center, c.work_radius):
            if h in centers:
                continue
            t = map.get(h)
            if t is not None and not is_foreign(t.owner_city):
                tiles.add(h)
    return tiles


def detect_taken(map: GameMap) -> set[str]:
    """Wonders already built somewhere on the map -> their keys (best-effort match)."""
    present = [t.wonder.lower() for t in map.tiles.values() if t.wonder]
    taken: set[str] = set()
    for w in WONDERS:
        nm = w.name.lower()
        for p in present:
            if w.key in p or (len(nm) >= 5 and nm[:5] in p):
                taken.add(w.key)
                break
    return taken


def recommend_wonders(
    map: GameMap, cities: list[City], taken: list[str] | None = None, top: int = 12
) -> tuple[list[WonderRec], list[str]]:
    taken_set = set(taken or []) | detect_taken(map)
    own = _own_tiles(map, cities)

    recs: list[WonderRec] = []
    for w in WONDERS:
        if w.key in taken_set:
            continue
        valid: list[tuple[Hex, float]] = []
        for h in own:
            t = map.get(h)
            if not _empty(t):
                continue
            try:
                ok = w.predicate(map, h)
            except Exception:  # noqa: BLE001 - a malformed tile must not crash the run
                ok = False
            if ok:
                valid.append((h, _tile_value(t)))
        if not valid:
            continue
        valid.sort(key=lambda x: x[1], reverse=True)
        best = valid[0][0]
        alts = [{"q": hh.q, "r": hh.r} for hh, _ in valid[1:4]]
        recs.append(WonderRec(
            key=w.key, name=w.name, era=w.era, q=best.q, r=best.r,
            value=w.value, requires=w.requires, note=w.note,
            risk=ERA_RISK.get(w.era, "средний"), alternatives=alts,
        ))

    recs.sort(key=lambda r: r.value, reverse=True)
    return recs[:top], sorted(taken_set)
