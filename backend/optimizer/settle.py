"""Recommend tiles to found new cities on.

Heuristic scorer over candidate city-center tiles. It rewards: fresh water &
coast (housing), surrounding tile quality, and district-adjacency potential
(mountains for Campus/Holy Site, rivers for Commercial Hub, mines/hills for
Industrial Zone, sea resources for Harbor). It enforces Civ 6-style spacing
between cities and avoids tiles a current city would already own.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ..i18n import tr
from ..domain.hexgrid import Hex, distance, within_radius
from ..domain.models import City, Feature, GameMap, Terrain, Tile
from ..rules.natural_wonders import NW_BY_KEY
from .empire import is_foreign

# Cities must be at least this far apart (Civ 6 won't let you settle closer).
MIN_CITY_DIST = 4

# A new city should sit near your current borders, not on the far side of the map.
# Civ 6 ideal spacing is ~4-6 tiles between centers (work radii almost touch). Past
# IDEAL_SETTLE_DIST the empire sprawls, loyalty weakens and the new city is cut off,
# so we softly penalise the gap; beyond MAX_SETTLE_DIST from EVERY existing city we
# drop the candidate outright. Tunable via suggest_settles(max_dist=...).
# Civ 6 adjacency doesn't care which city owns a neighbouring district, so cities founded
# at the minimum legal spacing (4) overlap territory and let districts of different cities
# pack on the shared border and boost each other (+0.5 each). We therefore treat ~4-5 tiles
# as ideal and penalise spreading out, which the community "district sharing" meta relies on.
IDEAL_SETTLE_DIST = 5      # no sprawl penalty up to here (tight, overlapping territories)
MAX_SETTLE_DIST = 9        # discard sites farther than this from the whole empire
SPRAWL_PENALTY = 0.9       # score lost per tile beyond IDEAL_SETTLE_DIST

# Distinct luxury resources each grant +1 Amenity to the empire (first copy), so a
# site sitting on fresh luxuries is worth more. (Matches app.py RESOURCES["luxury"].)
LUXURIES = frozenset({
    "wine", "incense", "dyes", "silk", "furs", "ivory", "jade", "marble",
    "gypsum", "pearls", "whales", "honey", "tea", "cinnamon", "cloves",
    "cocoa", "coffee", "cotton", "citrus", "diamonds", "mercury", "salt",
    "sugar", "tobacco", "truffles", "amber", "olives", "perfume", "jeans",
    "cosmetics", "toys",
})

# Strategic resources power units/buildings; sites with access to them are worth more
# (and you should avoid burying them under a district).
STRATEGICS = frozenset({"horses", "iron", "niter", "coal", "oil", "aluminum", "uranium"})

# Loyalty pressure falls off with distance up to ~9 tiles in Civ 6.
LOYALTY_RANGE = 9


def _loyalty_balance(
    h: Hex, own: list[tuple[Hex, int]], rivals: list[tuple[Hex, int]]
) -> float:
    """Net loyalty pressure at ``h``: your cities push +, rival cities push −.

    Approximate: pressure from a city of population ``pop`` at distance ``d`` is
    ``pop * (RANGE - d) / RANGE`` for ``d <= RANGE``. A negative balance means a new
    city here would tend to lose loyalty (risk of revolt / flipping).
    """
    def pressure(cities: list[tuple[Hex, int]]) -> float:
        s = 0.0
        for c, pop in cities:
            d = distance(h, c)
            if 0 < d <= LOYALTY_RANGE:
                s += max(1, pop) * (LOYALTY_RANGE - d) / LOYALTY_RANGE
        return s

    return pressure(own) - pressure(rivals)


@dataclass
class SettleSuggestion:
    coord: Hex
    score: float
    fresh_water: bool
    coastal: bool
    breakdown: dict[str, float] = field(default_factory=dict)
    note: str = ""        # risk/советы: vulcan/flood/dam hints for this site
    turn: int = 0         # first-city mode: the turn a Settler could found here (0 = n/a)


def _valid_center(map: GameMap, h: Hex) -> bool:
    t = map.get(h)
    return (
        t is not None
        and t.terrain.is_land
        and t.terrain is not Terrain.MOUNTAIN
        and t.district is None
        and t.wonder is None
        and t.feature is not Feature.NATURAL_WONDER
        and not is_foreign(t.owner_city)
    )


def _tile_value(t: Tile) -> float:
    if t.terrain.is_water:
        v = 1.0 if t.terrain in (Terrain.COAST, Terrain.LAKE) else 0.3
    elif t.terrain is Terrain.MOUNTAIN:
        return 0.0
    else:
        base = {
            Terrain.GRASSLAND: 2.2, Terrain.PLAINS: 2.0, Terrain.DESERT: 0.5,
            Terrain.TUNDRA: 1.0, Terrain.SNOW: 0.2,
        }.get(t.terrain, 1.0)
        v = base + (0.8 if t.hills else 0.0)
    if t.feature is Feature.WOODS:
        v += 0.6
    elif t.feature is Feature.RAINFOREST:
        v += 0.3
    elif t.feature is Feature.FLOODPLAINS:
        v += 1.0                       # fertile (food) — but carries flood risk (see scorer)
    elif t.feature is Feature.OASIS:
        v += 1.5
    elif t.feature is Feature.VOLCANIC_SOIL:
        v += 1.3                       # very fertile post-eruption soil (+1F/+1P)
    if t.resource:
        v += 1.2
    if t.natural_wonder:
        nw = NW_BY_KEY.get(t.natural_wonder)
        if nw:
            v += nw.settle_value     # a natural wonder in range is a strong reason to settle near
    v += 0.3 * t.appeal
    return v


def _is_fresh_water_site(map: GameMap, h: Hex) -> bool:
    """Civ 6 fresh water: a river runs on THIS tile's edge (on_river), or the tile is
    adjacent to a Lake or an Oasis. A neighbour merely *being* on a river does NOT
    give fresh water — the river must touch your own edge (then your own on_river is
    True too). Checking neighbours' on_river caused false 'fresh water' positives.
    """
    t = map.get(h)
    if t is not None and (t.on_river or t.feature is Feature.OASIS):
        return True
    for n in map.neighbors(h):
        if n.terrain is Terrain.LAKE or n.feature is Feature.OASIS:
            return True
    return False


def _civ_bonus(civ: str | None, h: Hex, existing: list[Hex],
              mtn: int, tundra: int, floodp: int, fresh: bool) -> float:
    """Civ-specific settle preferences (Inca/Russia/Khmer/Maya change WHERE to settle)."""
    if civ == "inca":
        return 1.0 * mtn                       # mountains are workable -> great Inca sites
    if civ == "russia":
        return 0.6 * tundra                    # tundra/snow yield faith/production
    if civ == "khmer":
        return 0.6 * floodp + (1.0 if fresh else 0.0)  # rivers/floodplains = food & faith
    if civ == "maya" and existing:
        dcap = distance(h, existing[0])        # compact empire near the capital
        return max(0.0, 6 - dcap) * 0.4
    return 0.0


def _score_center(map: GameMap, h: Hex, existing_centers: list[Hex],
                  civ: str | None = None,
                  own_cities: list[tuple[Hex, int]] | None = None,
                  rival_cities: list[tuple[Hex, int]] | None = None,
                  home: list[Hex] | None = None) -> SettleSuggestion:
    center_t = map.get(h)
    fresh = _is_fresh_water_site(map, h)
    nbrs = map.neighbors(h)
    coastal = any(n.terrain.is_water for n in nbrs)

    yield_score = 0.0
    mtn = rivers = woods = mines = sea_res = tundra = floodp = volcanic = 0
    volc1 = volc2 = 0
    breath_land = breath_coast = 0       # breathtaking tiles -> National Park / Seaside Resort
    floodp_on_river = False
    luxuries: set[str] = set()
    strategics: set[str] = set()
    for w in within_radius(h, 3):
        if w == h:
            continue
        t = map.get(w)
        if t is None or is_foreign(t.owner_city):
            continue
        # only count tiles this city would plausibly own (closest to h)
        if existing_centers and min((distance(w, c) for c in existing_centers), default=99) < distance(w, h):
            continue
        ring = distance(w, h)
        weight = 1.0 if ring == 1 else (0.7 if ring == 2 else 0.45)
        yield_score += weight * _tile_value(t)
        if t.resource and t.resource in LUXURIES:
            luxuries.add(t.resource)             # distinct luxuries -> amenities
        if t.resource and t.resource in STRATEGICS:
            strategics.add(t.resource)           # units/buildings need these
        if t.appeal >= 4:                        # breathtaking -> tourism/housing potential
            if t.terrain is Terrain.COAST:
                breath_coast += 1                # Seaside Resort
            elif t.terrain.is_land:
                breath_land += 1                 # National Park / high-appeal Neighborhood
        if t.volcano:                            # eruptions pillage adjacent districts/tiles
            if ring == 1:
                volc1 += 1
            elif ring == 2:
                volc2 += 1
        if ring <= 2:
            if t.terrain is Terrain.MOUNTAIN:
                mtn += 1
            if t.terrain in (Terrain.TUNDRA, Terrain.SNOW):
                tundra += 1
            if t.feature is Feature.FLOODPLAINS:
                floodp += 1
                if t.on_river:
                    floodp_on_river = True        # a Dam can be built -> flood protection
            if t.feature is Feature.VOLCANIC_SOIL:
                volcanic += 1
            if t.on_river:
                rivers += 1
            if t.feature is Feature.WOODS:
                woods += 1
            if t.terrain.is_water and t.resource:
                sea_res += 1
            if t.hills or t.improvement.value in ("mine", "quarry"):
                mines += 1

    districts = 1.2 * mtn + 0.4 * min(rivers, 3) + 0.25 * woods + 0.5 * sea_res + 0.3 * mines

    # housing: fresh water = 5, coast = 3 (vs 2 dry); plus Aqueduct/Dam housing potential.
    # Fresh water is weighted strongly: a dry capital is stuck at 2 Housing and barely
    # grows until an Aqueduct (which itself needs a river/lake/mountain/oasis), so a
    # site with NO fresh water and NO coast carries an explicit growth penalty.
    fw = 4.0 if fresh else 0.0
    cst = 1.5 if coastal else 0.0
    aqueduct_possible = any(n.terrain is Terrain.MOUNTAIN or n.is_fresh_water for n in nbrs)
    housing_potential = 0.5 if (floodp_on_river or aqueduct_possible) else 0.0
    dry_pen = 0.0
    if not fresh and not coastal:
        dry_pen = -3.0 if not aqueduct_possible else -1.5   # crippled growth until Aqueduct

    # amenities: each distinct luxury in range is +1 Amenity to the empire
    amenities = 0.6 * min(len(luxuries), 4)

    # appeal: breathtaking tiles unlock National Parks / Seaside Resorts (tourism +
    # housing for high-appeal Neighborhoods). A modest reward for a scenic site.
    appeal_bonus = 0.3 * min(breath_land, 4) + 0.3 * min(breath_coast, 3)

    # strategic resources (horses/iron/oil/…) power units & buildings
    strategic = 0.7 * min(len(strategics), 4)

    # city-center tile's own yield: settling on Hills gives the center +1 production
    # (Plains Hills = 2F/2P, the strongest center tile).
    center_bonus = 0.0
    if center_t is not None:
        if center_t.hills:
            center_bonus += 0.8
        if center_t.terrain is Terrain.PLAINS:
            center_bonus += 0.2

    # --- risks the user asked about -------------------------------------------------
    # Floodplains are food-rich but flood (pillage tiles/districts) until a Dam exists.
    flood_pen = -0.3 * min(floodp, 3)
    dam_bonus = 0.0
    if floodp and floodp_on_river:
        flood_pen *= 0.4                 # a Dam removes most flood damage
        dam_bonus = 0.6                  # Dam adds housing/production + Industrial-Zone adjacency
    # Settling right next to a volcano risks losing your districts on eruption.
    volcano_pen = -(0.9 * volc1 + 0.4 * volc2)

    # Loyalty: a site dominated by rival cities risks revolting / flipping.
    loyalty = _loyalty_balance(h, own_cities or [], rival_cities or [])
    loyalty_pen = loyalty * 0.5 if loyalty < 0 else 0.0

    # Anti-sprawl: keep new cities tied to your current borders (or, before you've
    # founded anything, to your Settler). Distance to the NEAREST anchor beyond the
    # ideal spacing costs score, so a great-but-far tile loses to a connected one.
    anchors = home if home is not None else existing_centers
    sprawl_pen = 0.0
    dmin_existing = min((distance(h, c) for c in anchors), default=0)
    if anchors and dmin_existing > IDEAL_SETTLE_DIST:
        sprawl_pen = -SPRAWL_PENALTY * (dmin_existing - IDEAL_SETTLE_DIST)

    civ_b = _civ_bonus(civ, h, existing_centers, mtn, tundra, floodp, fresh)
    score = (yield_score + fw + cst + housing_potential + dry_pen + amenities + appeal_bonus
             + strategic + districts + center_bonus + civ_b + flood_pen + dam_bonus
             + volcano_pen + loyalty_pen + sprawl_pen)

    notes: list[str] = []
    # water / growth status first — it's the #1 thing for a capital's early growth
    if fresh:
        notes.append("🌊 пресная вода — жильё 5, рост ок")
    elif coastal:
        notes.append("побережье — жильё 3 (для роста нужен Акведук/Канализация)")
    elif aqueduct_possible:
        notes.append("⚠️ нет пресной воды (жильё 2) — рост ограничен, пока не построишь Акведук")
    else:
        notes.append("⚠️ сухое место: ни реки/озера, ни горы под Акведук — рост будет тяжёлым")
    if volc1:
        notes.append("⚠️ вулкан вплотную — извержения уничтожат соседние районы/улучшения")
    elif volc2:
        notes.append("вулкан рядом: плодородная почва, но риск извержений")
    if floodp and floodp_on_river:
        notes.append("поймы у реки — построй Дамбу (защита от затопления + жильё/произв.)")
    elif floodp:
        notes.append("⚠️ поймы без реки рядом — Дамбу не построить, есть риск затоплений")
    if loyalty_pen < -0.3:
        notes.append("⚠️ риск лояльности — рядом сильные чужие города (возможен бунт/переход)")
    if sprawl_pen < -0.5:
        notes.append(tr("далеко от твоих границ (~{n} клеток до ближайшего города)", n=dmin_existing))
    if breath_coast:
        notes.append("захватывающее побережье — потенциал Приморских курортов (туризм)")
    elif breath_land >= 2:
        notes.append("красивые клетки рядом — потенциал Нац.парка/Заповедника и жильё Кварталов")
    if strategics:
        notes.append("стратег. ресурсы рядом: " + ", ".join(sorted(strategics)))

    return SettleSuggestion(
        coord=h, score=round(score, 2), fresh_water=fresh, coastal=coastal,
        breakdown={
            "tiles": round(yield_score, 2), "fresh_water": fw, "coastal": cst,
            "housing+": housing_potential, "dry": round(dry_pen, 2),
            "amenities": round(amenities, 2),
            "appeal": round(appeal_bonus, 2), "strategic": round(strategic, 2),
            "districts": round(districts, 2), "center": round(center_bonus, 2),
            "civ": round(civ_b, 2), "flood": round(flood_pen + dam_bonus, 2),
            "volcano": round(volcano_pen, 2), "loyalty": round(loyalty_pen, 2),
            "sprawl": round(sprawl_pen, 2),
        },
        note="; ".join(notes),
    )


def suggest_settles(
    map: GameMap, cities: list[City], count: int = 5, civ: str | None = None,
    rival_cities: list[tuple[Hex, int]] | None = None,
    max_dist: int = MAX_SETTLE_DIST,
    settlers: list[Hex] | None = None,
    blocked_centers: list[Hex] | None = None,
) -> list[SettleSuggestion]:
    existing = [c.center for c in cities]
    own = [(c.center, max(1, c.population)) for c in cities]
    rivals = rival_cities or []
    # Civ 6 forbids founding within MIN_CITY_DIST of ANY city center — yours AND foreign
    # ones, including city-states and free cities. `blocked_centers` carries those foreign
    # centers (any kind) so we never suggest an illegal site near e.g. a city-state.
    spacing = existing + list(blocked_centers or [])

    # Proximity anchor: your cities if you have any, otherwise your Settler(s). Before
    # the capital is founded this keeps the FIRST cities near the Settler instead of
    # scattering across the whole revealed map.
    anchors = existing or list(settlers or [])

    candidates: list[SettleSuggestion] = []
    for h in list(map.tiles):
        if not _valid_center(map, h):
            continue
        if any(distance(h, c) < MIN_CITY_DIST for c in spacing):
            continue
        # keep expansion near the empire / Settler: drop sites too far from every anchor
        if anchors and not any(distance(h, c) <= max_dist for c in anchors):
            continue
        candidates.append(_score_center(map, h, existing, civ, own, rivals, home=anchors))

    candidates.sort(key=lambda s: s.score, reverse=True)

    # greedily pick, keeping suggestions spaced apart too
    chosen: list[SettleSuggestion] = []
    for s in candidates:
        if all(distance(s.coord, c.coord) >= MIN_CITY_DIST for c in chosen):
            chosen.append(s)
        if len(chosen) >= count:
            break
    return chosen


# --- first city (capital) planner ----------------------------------------------
# A Settler moves 2 MP/turn. Entering a tile costs 1 (+1 over hills, +1 through
# woods/rainforest/marsh). We ignore embarking for the early turns. You found the
# city on the turn you arrive, so turn = 1 + ceil(move_cost / 2): settle in place
# = turn 1; 1-2 move cost = turn 2; 3-4 = turn 3.
SETTLER_MP = 2
FIRST_CITY_MAX_TURN = 3


def _enter_cost(t: Tile | None) -> int | None:
    if t is None or not t.terrain.is_land or t.terrain is Terrain.MOUNTAIN:
        return None        # impassable for a settling unit in turns 1-3
    c = 1
    if t.hills:
        c += 1
    if t.feature in (Feature.WOODS, Feature.RAINFOREST, Feature.MARSH):
        c += 1
    return c


def _reachable_turns(map: GameMap, start: Hex,
                     max_turn: int = FIRST_CITY_MAX_TURN) -> dict[Hex, int]:
    """Turn on which a Settler starting at ``start`` could found a city on each tile."""
    budget = SETTLER_MP * (max_turn - 1)          # max movement cost for turn <= max_turn
    best: dict[Hex, int] = {start: 0}
    pq: list[tuple[int, Hex]] = [(0, start)]
    while pq:
        d, h = heapq.heappop(pq)
        if d > best.get(h, 1 << 30):
            continue
        for n in h.neighbors():
            ec = _enter_cost(map.get(n))
            if ec is None:
                continue
            nd = d + ec
            if nd <= budget and nd < best.get(n, 1 << 30):
                best[n] = nd
                heapq.heappush(pq, (nd, n))
    return {h: 1 + math.ceil(c / SETTLER_MP) for h, c in best.items()}


def suggest_first_city(
    map: GameMap, settler: Hex, civ: str | None = None, turn_penalty: float = 2.0,
    rival_cities: list[tuple[Hex, int]] | None = None, count: int = 6,
) -> list[SettleSuggestion]:
    """Rank capital sites a Settler can reach in turns 1-3, penalising each lost turn.

    Settle-in-place (turn 1) is the baseline; moving is only recommended when the
    better site outweighs ``turn_penalty`` per turn of delay.
    """
    turns = _reachable_turns(map, settler)
    rivals = rival_cities or []
    scored: list[SettleSuggestion] = []
    for h, turn in turns.items():
        if not _valid_center(map, h):
            continue
        s = _score_center(map, h, [], civ, [], rivals)
        delay = turn_penalty * (turn - 1)
        s.turn = turn
        s.breakdown = {**s.breakdown, "delay": -round(delay, 2)}
        s.score = round(s.score - delay, 2)
        if turn > 1:
            s.note = (tr("основать на {n}-й ход", n=turn) + ("; " + s.note if s.note else ""))
        else:
            s.note = ("основать на месте (1-й ход)" + ("; " + s.note if s.note else ""))
        scored.append(s)
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:count]
