"""Regression tests for the Tier-1/Tier-2 additions:
Encampment rule, new districts, Government Plaza +1, unique districts, appeal &
housing, governors, settle proximity anchoring, and the integrated city plan.
"""

from __future__ import annotations

from backend.domain.hexgrid import Hex, distance, within_radius
from backend.domain.models import (
    City, DistrictType as D, GameMap, Improvement, Terrain, Tile,
)
from backend.optimizer.housing import estimate_housing
from backend.optimizer.settle import suggest_settles
from backend.rules.adjacency import can_place, raw_adjacency
from backend.rules.appeal import band, neighborhood_housing
from backend.rules.districts import DISTRICTS, resolve_def
from backend.rules.modifiers import GOVERNORS, Loadout


def _board(radius: int = 2, terrain: Terrain = Terrain.GRASSLAND) -> GameMap:
    gm = GameMap()
    for h in within_radius(Hex(0, 0), radius):
        gm.set(Tile(coord=h, terrain=terrain))
    return gm


# --- Encampment rule + new districts -------------------------------------------

def test_encampment_not_adjacent_to_city_center():
    gm = _board()
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    assert not can_place(gm, Hex(1, 0), D.ENCAMPMENT, city)      # adjacent -> illegal
    assert can_place(gm, Hex(2, 0), D.ENCAMPMENT, city)         # 2 away -> ok


def test_new_districts_are_defined():
    for d in (D.CANAL, D.WATER_PARK, D.NEIGHBORHOOD, D.AERODROME,
              D.SPACEPORT, D.PRESERVE, D.DIPLOMATIC_QUARTER):
        assert d in DISTRICTS


def test_preserve_not_adjacent_to_city_center():
    gm = _board()
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    assert not can_place(gm, Hex(1, 0), D.PRESERVE, city)


# --- Government Plaza +1 --------------------------------------------------------

def test_government_plaza_gives_standard_bonus():
    gm = _board()
    gm.get(Hex(1, 0)).district = D.GOVERNMENT_PLAZA
    # Campus on (2,0) is adjacent only to the plaza -> +0.5 generic + 0.5 plaza = 1.0
    assert raw_adjacency(gm, Hex(2, 0), D.CAMPUS) == 1.0


# --- unique districts ----------------------------------------------------------

def test_suguba_mali_holy_site_adjacency():
    gm = _board()
    gm.get(Hex(1, 0)).district = D.HOLY_SITE
    gm.get(Hex(-1, 0)).district = D.HOLY_SITE
    base = raw_adjacency(gm, Hex(0, 0), D.COMMERCIAL_HUB, civ=None)
    mali = raw_adjacency(gm, Hex(0, 0), D.COMMERCIAL_HUB, civ="mali")
    assert base == 1.0                 # 2 districts x +0.5
    assert mali == 5.0                 # +2 per Holy Site (4) + 1 generic


def test_seowon_korea_inherent_and_penalty_and_hills():
    gm = _board()
    gm.get(Hex(0, 0)).hills = True
    assert raw_adjacency(gm, Hex(0, 0), D.CAMPUS, civ="korea") == 4.0
    gm.get(Hex(1, 0)).district = D.CITY_CENTER
    gm.get(Hex(-1, 0)).district = D.HOLY_SITE
    assert raw_adjacency(gm, Hex(0, 0), D.CAMPUS, civ="korea") == 2.0   # 4 - 2 districts
    # hills-only placement
    flat = _board()
    city = City(name="c", center=Hex(5, 5))
    assert not can_place(flat, Hex(0, 0), D.CAMPUS, city, Loadout(civ="korea"))


def test_hansa_germany_commercial_hub_and_resource():
    gm = _board()
    gm.get(Hex(1, 0)).district = D.COMMERCIAL_HUB
    gm.get(Hex(-1, 0)).resource = "iron"
    assert raw_adjacency(gm, Hex(0, 0), D.INDUSTRIAL_ZONE, civ="germany") == 3.5


def test_acropolis_greece_city_center_hills():
    gm = _board()
    gm.get(Hex(0, 0)).hills = True
    gm.get(Hex(1, 0)).district = D.CITY_CENTER
    # +1 per district (city center) + 1 city-center extra = 2.0
    assert raw_adjacency(gm, Hex(0, 0), D.THEATER, civ="greece") == 2.0


def test_observatory_maya_plantation():
    gm = _board()
    gm.get(Hex(1, 0)).improvement = Improvement.PLANTATION
    assert raw_adjacency(gm, Hex(0, 0), D.CAMPUS, civ="maya") == 2.0   # +2 plantation


def test_resolve_def_falls_back_to_standard():
    assert resolve_def(D.CAMPUS, None) is DISTRICTS[D.CAMPUS]
    assert resolve_def(D.CAMPUS, "korea") is not DISTRICTS[D.CAMPUS]


# --- appeal & housing ----------------------------------------------------------

def test_appeal_bands_and_neighborhood_housing():
    assert band(5) == "breathtaking" and band(0) == "average" and band(-6) == "disgusting"
    assert neighborhood_housing(5) == 6
    assert neighborhood_housing(0) == 4
    assert neighborhood_housing(-6) == 2


def test_housing_estimate_fresh_water_and_improvements():
    gm = _board(3)
    gm.get(Hex(0, 0)).on_river = True
    gm.get(Hex(1, 0)).improvement = Improvement.FARM
    city = City(name="c", center=Hex(0, 0), population=5)
    rep = estimate_housing(gm, [city])[0]
    assert rep.supply >= 5.0            # fresh water base 5 + farm 0.5
    assert rep.surplus == rep.supply - 5


# --- governors -----------------------------------------------------------------

def test_governor_registry_and_liang_appeal():
    assert set(GOVERNORS) >= {"none", "magnus", "liang", "pingala", "reyna", "moksha"}
    assert GOVERNORS["pingala"].weight_mult                       # has weight multipliers
    # Liang adds +1 appeal -> a charming (3) tile becomes breathtaking for Neighborhoods
    gm = _board(3)
    gm.get(Hex(0, 0)).on_river = True
    gm.get(Hex(1, 0)).appeal = 3
    city = City(name="c", center=Hex(0, 0), population=8)
    plain = estimate_housing(gm, [city])[0]
    liang = estimate_housing(gm, [city], Loadout(governor="liang"))[0]
    assert plain.best_neighborhood_band == "charming"
    assert liang.best_neighborhood_band == "breathtaking"


# --- settle proximity (anti-sprawl) --------------------------------------------

def test_settle_anchors_on_settler_when_no_cities():
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 12):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    for h in within_radius(Hex(40, 0), 5):           # tempting far cluster
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND, on_river=True, resource="wine"))
    sugg = suggest_settles(gm, [], count=5, settlers=[Hex(0, 0)])
    assert sugg
    assert all(distance(s.coord, Hex(0, 0)) <= 9 for s in sugg)   # stayed near the Settler


# --- governor recommendation (per city) ----------------------------------------

def test_governor_recommendation_matches_city_character():
    from backend.optimizer.governors import assign_governors
    feats = [
        {"city": "Science", "districts": {"campus", "theater_square"}, "coastal": False,
         "pop": 8, "housing_surplus": 5, "amenity_surplus": 1},
        {"city": "Trade", "districts": {"harbor", "commercial_hub"}, "coastal": True,
         "pop": 4, "housing_surplus": 5, "amenity_surplus": 1},
        {"city": "Faith", "districts": {"holy_site"}, "coastal": False,
         "pop": 3, "housing_surplus": 5, "amenity_surplus": 1},
    ]
    out = assign_governors(feats, {y: 1.0 for y in ("science", "culture", "gold", "faith", "production")})
    assert out["Science"]["governor"] == "pingala"
    assert out["Trade"]["governor"] == "reyna"
    assert out["Faith"]["governor"] == "moksha"
    # 1:1 — no governor is reused across cities
    seated = [v["governor"] for v in out.values()]
    assert len(seated) == len(set(seated))


# --- pantheon / policy advisor -------------------------------------------------

def test_pantheon_advice_prefers_supported_terrain():
    from backend.optimizer.advisor import recommend_pantheon, recommend_policies
    # desert-heavy land WITH a Holy Site planned -> Desert Folklore on top (Mali boost)
    rec = recommend_pantheon({"desert": 8, "river": 2}, {"holy_site", "campus"}, civ="mali")
    assert rec and rec["key"] == "desert_folklore"
    # no Holy Site -> faith-from-Holy-Site pantheon is discounted; sea wins when present
    rec2 = recommend_pantheon({"desert": 8, "sea_resource": 6}, {"harbor"}, civ=None)
    assert rec2 and rec2["key"] == "god_of_the_sea"
    # policies follow the specialty districts you actually have
    pols = {p["name"] for p in recommend_policies({"campus", "industrial_zone"})}
    assert pols == {"natural_philosophy", "five_year_plan"}


def test_river_goddess_adds_housing_and_amenities():
    from backend.optimizer.amenities import estimate_amenities
    gm = _board(2)
    gm.get(Hex(0, 0)).on_river = True
    gm.get(Hex(1, 0)).on_river = True
    gm.get(Hex(1, 0)).district = D.HOLY_SITE          # Holy Site on a river tile
    city = City(name="c", center=Hex(0, 0), population=6)
    base = estimate_housing(gm, [city])[0].supply
    rg = estimate_housing(gm, [city], Loadout(pantheon="river_goddess"))[0].supply
    assert rg - base == 2.0
    a_base = estimate_amenities(gm, [city])[0].supply
    a_rg = estimate_amenities(gm, [city], Loadout(pantheon="river_goddess"))[0].supply
    assert a_rg - a_base == 2.0


# --- placement-rule fixes (Aqueduct / Dam) -------------------------------------

def test_aqueduct_requires_center_and_fresh_source():
    from backend.rules.adjacency import can_place
    gm = _board(3)
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    # adjacent to center but dry -> illegal
    assert not can_place(gm, Hex(1, 0), D.AQUEDUCT, city)
    # adjacent to center AND on a river -> legal
    gm.get(Hex(1, 0)).on_river = True
    assert can_place(gm, Hex(1, 0), D.AQUEDUCT, city)
    # not adjacent to center -> illegal even next to a mountain
    gm.get(Hex(3, 0)).terrain = Terrain.MOUNTAIN
    assert not can_place(gm, Hex(2, 0), D.AQUEDUCT, city)


def test_dam_requires_floodplains_and_two_river_edges():
    from backend.domain.models import Feature
    from backend.rules.adjacency import can_place
    gm = _board(3)
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    t = gm.get(Hex(1, 0)); t.feature = Feature.FLOODPLAINS; t.on_river = True
    assert not can_place(gm, Hex(1, 0), D.DAM, city)          # <2 river-edge neighbours
    placed = 0
    for n in Hex(1, 0).neighbors():
        if gm.get(n) is not None and placed < 2:
            gm.get(n).on_river = True; placed += 1
    assert can_place(gm, Hex(1, 0), D.DAM, city)


def test_dam_uses_exact_river_edge_count_when_known():
    """When the game export gives the real edge count, the neighbour approximation is
    bypassed: a straight river (1 edge) is rejected even with many river neighbours."""
    from backend.domain.models import Feature
    from backend.rules.adjacency import can_place
    gm = _board(3)
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    t = gm.get(Hex(1, 0)); t.feature = Feature.FLOODPLAINS; t.on_river = True
    for n in Hex(1, 0).neighbors():                  # lots of river neighbours…
        if gm.get(n) is not None:
            gm.get(n).on_river = True
    t.river_edges = 1                                # …but river crosses only ONE edge
    assert not can_place(gm, Hex(1, 0), D.DAM, city)
    t.river_edges = 2                                # a bend -> two edges -> legal
    assert can_place(gm, Hex(1, 0), D.DAM, city)


# --- empire scales to many cities (clustering + budget) ------------------------

def test_empire_optimizes_many_cities_fast():
    import time
    from backend.optimizer.empire import optimize_empire
    from backend.rules.modifiers import Loadout
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 30):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    cities = []
    for i in range(16):
        c = Hex((i % 4) * 5 - 8, (i // 4) * 5 - 8)
        gm.get(c).district = D.CITY_CENTER
        cities.append(City(name=f"C{i}", center=c, population=8,
                           requested=[D.CAMPUS, D.HOLY_SITE, D.THEATER, D.COMMERCIAL_HUB, D.INDUSTRIAL_ZONE]))
    t0 = time.time()
    res = optimize_empire(gm, cities, Loadout())
    assert time.time() - t0 < 30          # was effectively unbounded before clustering/budget
    assert sum(len(v) for v in res.placements_by_city.values()) > 0


# --- religion beliefs ----------------------------------------------------------

def test_work_ethic_adds_production_to_holy_site():
    from backend.domain.models import YieldType as Y
    from backend.rules.adjacency import adjacency_yield
    from backend.rules.modifiers import Loadout
    gm = _board(2)
    for n in gm.neighbors(Hex(0, 0)):
        if n.coord != Hex(0, 0):
            n.terrain = Terrain.MOUNTAIN          # +1 Faith each -> +6
    base = adjacency_yield(gm, Hex(0, 0), D.HOLY_SITE, Loadout())
    we = adjacency_yield(gm, Hex(0, 0), D.HOLY_SITE, Loadout(religion_beliefs=["work_ethic"]))
    assert we[Y.PRODUCTION] == base[Y.FAITH] and base[Y.FAITH] > 0


def test_belief_recommendation_follows_districts():
    from backend.optimizer.advisor import recommend_beliefs
    keys = {b["key"] for b in recommend_beliefs({"holy_site", "campus"}, {y: 1.0 for y in ("culture",)})}
    assert "work_ethic" in keys           # Holy Site present -> Work Ethic headline
    assert "jesuit_education" in keys      # Campus present -> buy buildings with faith
    none = {b["key"] for b in recommend_beliefs(set(), {})}
    assert "work_ethic" not in none       # no Holy Site -> no Work Ethic


# --- joint empire planner (city sites + districts) -----------------------------

def test_plan_empire_picks_spaced_valuable_sites():
    from backend.optimizer.empire_plan import plan_empire
    from backend.rules.modifiers import Loadout
    from backend.domain.hexgrid import distance
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 14):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    for h in within_radius(Hex(0, 0), 14):       # some mountains for Campus value
        if (h.q + h.r) % 5 == 0:
            gm.get(h).terrain = Terrain.MOUNTAIN
    gm.get(Hex(0, 0)).terrain = Terrain.GRASSLAND
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    req = [D.CAMPUS, D.HOLY_SITE, D.COMMERCIAL_HUB, D.INDUSTRIAL_ZONE]
    cities = [City(name="Capital", center=Hex(0, 0), population=8, requested=list(req))]
    sites, full = plan_empire(gm, cities, Loadout(), max_new=3, requested=req)
    assert 1 <= len(sites) <= 3
    centers = [c.center for c in full]
    assert all(distance(a, b) >= 4 for i, a in enumerate(centers) for b in centers[i + 1:])
    assert all(s.coord != Hex(0, 0) for s in sites)   # never re-pick the capital


# --- religion loadout straight from the game log -------------------------------

def test_parse_loadout_pantheon_and_beliefs():
    from backend.io.lualog_parser import parse_lua_log
    log = "\n".join([
        "CIV6OPT|META|player|0|civ|CIVILIZATION_HUNGARY|width|8|height|8|wrapX|1",
        "CIV6OPT|BEGIN",
        "CIV6OPT|LOADOUT|pantheon|BELIEF_GOD_OF_THE_SEA|beliefs|"
        "BELIEF_WORK_ETHIC,BELIEF_MEETING_HOUSE|government|GOVERNMENT_MONARCHY",
        "CIV6OPT|CITY|4|4|0|0|1|6|Buda",
        "CIV6OPT|TILE|4|4|TERRAIN_GRASS|FEATURE_NONE|0|RESOURCE_NONE|NONE|0|0|0|"
        "DISTRICT_CITY_CENTER|NONE|0|1|NONE",
        "CIV6OPT|END",
    ])
    lo = parse_lua_log(log)["loadout"]
    assert lo["pantheon"] == "god_of_the_sea"
    assert lo["religion_beliefs"] == ["work_ethic", "meeting_house"]
    assert lo["government"] == "monarchy"


def test_parse_loadout_absent_is_none():
    from backend.io.lualog_parser import parse_lua_log
    log = "\n".join([
        "CIV6OPT|META|player|0|civ|CIVILIZATION_HUNGARY|width|8|height|8|wrapX|1",
        "CIV6OPT|BEGIN",
        "CIV6OPT|TILE|4|4|TERRAIN_GRASS|FEATURE_NONE|0|RESOURCE_NONE|NONE|0|0|0|"
        "DISTRICT_CITY_CENTER|NONE|0|1|NONE",
        "CIV6OPT|END",
    ])
    assert parse_lua_log(log)["loadout"] is None


def test_no_districts_in_foreign_control_radius():
    """A district can't be built on tiles a foreign city (city-state) controls. The
    foreign-control block marks neutral tiles near its center so the optimizer skips them."""
    from backend.app import _block_foreign_control, FOREIGN_CONTROL_RADIUS
    from backend.optimizer.empire import assign_territory, is_foreign
    from backend.domain.models import GameMap, Terrain, Tile
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 8):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city_state = Hex(4, 0)
    _block_foreign_control(gm, [city_state])
    # every neutral tile within the control radius is now foreign-marked
    for h in within_radius(city_state, FOREIGN_CONTROL_RADIUS):
        t = gm.get(h)
        if t is not None and t.district is None:
            assert is_foreign(t.owner_city)
    # so none of them are assigned to the player's city territory
    city = City(name="Wash", center=Hex(0, 0), population=10, requested=[D.CAMPUS])
    owner_of = assign_territory(gm, [city])
    assert all(distance(h, city_state) > FOREIGN_CONTROL_RADIUS for h in owner_of)


def test_new_cities_keep_distance_from_city_states_and_rivals():
    """Civ 6 forbids founding within MIN_CITY_DIST of ANY city center — including foreign
    ones (city-states, free cities). Passing those centers as blocked_centers must keep
    new sites away from them."""
    from backend.optimizer.empire_plan import plan_empire
    from backend.optimizer.settle import MIN_CITY_DIST
    from backend.rules.modifiers import Loadout
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 12):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    cities = [City(name="Cap", center=Hex(0, 0), population=8, requested=[D.CAMPUS])]
    city_state = Hex(6, 0)
    sites, _ = plan_empire(gm, cities, Loadout(), max_new=8, requested=[D.CAMPUS],
                           blocked_centers=[city_state])
    assert all(distance(s.coord, city_state) >= MIN_CITY_DIST for s in sites)
    assert all(distance(s.coord, Hex(0, 0)) >= MIN_CITY_DIST for s in sites)


def test_plan_empire_builds_on_already_built_districts():
    """Next wave of cities must plan AROUND what is already built: an existing city's
    already-built district is not re-planned, stays on the map as an anchor, and new
    cities are added without disturbing it."""
    from backend.optimizer.empire_plan import plan_empire
    from backend.rules.modifiers import Loadout
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 14):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    gm.get(Hex(1, 0)).district = D.CAMPUS            # capital already built its Campus
    req = [D.CAMPUS, D.HOLY_SITE, D.COMMERCIAL_HUB, D.INDUSTRIAL_ZONE]
    cities = [City(name="Capital", center=Hex(0, 0), population=8, requested=list(req))]
    sites, full = plan_empire(gm, cities, Loadout(), max_new=2, requested=req)
    cap = next(c for c in full if c.name == "Capital")
    assert D.CAMPUS not in cap.requested              # not re-planned
    assert gm.get(Hex(1, 0)).district is D.CAMPUS      # stays as a fixed anchor
    assert sites                                       # still expands with new cities


def test_districts_blocked_on_luxury_and_strategic_resources():
    """You can't build a district on a Luxury (can't remove) or revealed Strategic
    resource; a Bonus resource is fine (the district consumes it)."""
    from backend.rules.adjacency import can_place
    gm = _board(2)
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    t = gm.get(Hex(1, 0))
    t.resource, t.resource_class = "wine", "luxury"
    assert not can_place(gm, Hex(1, 0), D.CAMPUS, city)
    t.resource, t.resource_class, t.resource_revealed = "iron", "strategic", True  # revealed
    assert not can_place(gm, Hex(1, 0), D.CAMPUS, city)
    t.resource, t.resource_class, t.resource_revealed = "wheat", "bonus", None
    assert can_place(gm, Hex(1, 0), D.CAMPUS, city)


def test_classify_resource_fallback_for_manual_maps():
    from backend.io.map_schema import classify_resource
    assert classify_resource("wine") == "luxury"        # catalogue lookup (no class given)
    assert classify_resource("horses") == "strategic"
    assert classify_resource("wheat") == "bonus"
    assert classify_resource("iron", "luxury") == "luxury"   # explicit class wins
    assert classify_resource(None) is None


def test_empire_handles_all_districts_in_dense_cluster_without_crash():
    """Requesting EVERY district across several close cities means more slots than tiles —
    some can't be placed. The local search must handle unassigned slots gracefully (no
    KeyError) and report the leftovers as unplaceable."""
    from backend.domain.models import DistrictType as DT, GameMap, Terrain, Tile
    from backend.optimizer.empire import optimize_empire
    from backend.rules.modifiers import Loadout
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 8):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    centers = [Hex(0, 0), Hex(4, 0), Hex(0, 4), Hex(4, -4)]
    alld = [d for d in DT if d is not DT.CITY_CENTER]
    cities = []
    for i, c in enumerate(centers):
        gm.get(c).district = DT.CITY_CENTER
        cities.append(City(name=f"C{i}", center=c, population=8, requested=list(alld)))
    res = optimize_empire(gm, cities, Loadout())          # must not raise
    placed = sum(len(v) for v in res.placements_by_city.values())
    assert placed > 0
    # every requested slot is accounted for: placed + unplaceable == requested per city
    for c in cities:
        got = {p.district for p in res.placements_by_city[c.name]} | set(res.unplaceable[c.name])
        assert got == set(c.requested)


def test_every_district_type_is_modelled():
    """Catalogue completeness: every DistrictType (except the City Center) has a
    definition with a placement rule, so the optimizer can handle all of them."""
    from backend.domain.models import DistrictType
    from backend.rules.districts import DISTRICTS
    for d in DistrictType:
        if d is DistrictType.CITY_CENTER:
            continue
        assert d in DISTRICTS, f"{d.value} missing from DISTRICTS"
        assert DISTRICTS[d].placement is not None


def test_optimizer_considers_all_requested_district_types():
    """Request EVERY placeable district in one city on a varied map; the optimizer must
    account for each (placed or explicitly unplaceable) — none silently dropped — and the
    land-based ones must actually be placed."""
    from backend.domain.models import DistrictType as DT, Feature, GameMap, Terrain, Tile
    from backend.optimizer.single_city import optimize_city
    from backend.rules.modifiers import Loadout
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 4):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(0, 0)).district = DT.CITY_CENTER
    gm.get(Hex(2, 0)).terrain = Terrain.MOUNTAIN            # Campus/Holy Site adjacency
    gm.get(Hex(1, 0)).on_river = True                       # Aqueduct (center-adjacent water)
    gm.get(Hex(1, -1)).on_river = True                      # Commercial Hub river
    fp = gm.get(Hex(0, 1)); fp.feature = Feature.FLOODPLAINS; fp.on_river = True; fp.river_edges = 2  # Dam
    for c in (Hex(3, -1), Hex(3, 0), Hex(3, 1)):           # Coast strip for Harbor/Water Park
        gm.get(c).terrain = Terrain.COAST
    requested = [d for d in DT if d is not DT.CITY_CENTER]
    city = City(name="All", center=Hex(0, 0), population=10, requested=requested)
    res = optimize_city(gm, city, Loadout())
    placed = {p.district for p in res.placements}
    considered = placed | set(res.unplaceable)
    assert considered == set(requested), f"dropped: {set(requested) - considered}"
    # the land-only districts have legal tiles here -> must actually be placed
    must_place = {DT.CAMPUS, DT.HOLY_SITE, DT.THEATER, DT.COMMERCIAL_HUB,
                  DT.INDUSTRIAL_ZONE, DT.ENCAMPMENT, DT.ENTERTAINMENT, DT.NEIGHBORHOOD,
                  DT.DIPLOMATIC_QUARTER, DT.AERODROME, DT.SPACEPORT, DT.GOVERNMENT_PLAZA,
                  DT.PRESERVE, DT.AQUEDUCT, DT.DAM, DT.HARBOR, DT.WATER_PARK}
    assert must_place <= placed, f"not placed: {must_place - placed}"


def test_strategic_resource_blocks_only_when_revealed():
    """A revealed strategic blocks districts; an unrevealed one does NOT (you may build
    over it before the tech and keep access)."""
    from backend.rules.adjacency import can_place
    gm = _board(2)
    gm.get(Hex(0, 0)).district = D.CITY_CENTER
    city = City(name="c", center=Hex(0, 0))
    t = gm.get(Hex(1, 0)); t.resource, t.resource_class = "iron", "strategic"
    t.resource_revealed = True
    assert not can_place(gm, Hex(1, 0), D.CAMPUS, city)     # revealed -> blocked
    t.resource_revealed = False
    assert can_place(gm, Hex(1, 0), D.CAMPUS, city)         # not yet revealed -> allowed
    t.resource_revealed = None
    assert can_place(gm, Hex(1, 0), D.CAMPUS, city)         # unknown -> allowed (plan-ahead)


def _specialization_board():
    from backend.domain.models import GameMap, Terrain, Tile
    gm = GameMap()
    for h in within_radius(Hex(0, 0), 12):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))
    gm.get(Hex(5, 1)).terrain = Terrain.MOUNTAIN          # campus/holy-site city
    for h in (Hex(1, 5), Hex(0, 6), Hex(-1, 6)):
        gm.get(h).terrain = Terrain.COAST                 # coastal city -> Harbor
    for h in within_radius(Hex(5, 5), 2):
        gm.get(h).hills = True                            # production city -> IZ
    cities = []
    for i, c in enumerate([Hex(0, 0), Hex(5, 0), Hex(0, 5), Hex(5, 5)]):
        gm.get(c).district = D.CITY_CENTER
        cities.append(City(name=f"C{i}", center=c, population=[12, 10, 8, 9][i], requested=[]))
    return gm, cities


def test_specialization_roles_uniques_and_coverage():
    from backend.optimizer.specialize import assign_specialization
    from backend.rules.modifiers import Loadout
    gm, cities = _specialization_board()
    pool = [d for d in D if d is not D.CITY_CENTER]
    spec = assign_specialization(gm, cities, Loadout(victory="science"), pool)
    # one role per city; cities are focused (not "everything everywhere")
    assert set(spec.cities) == {c.name for c in cities}
    assert all(0 < len(r.districts) <= 7 for r in spec.cities.values())
    # uniques: exactly one Government Plaza and one Diplomatic Quarter empire-wide
    assert spec.coverage["government_plaza"] == 1
    assert spec.coverage["diplomatic_quarter"] == 1
    assert "government_plaza" in spec.uniques and "diplomatic_quarter" in spec.uniques
    # key types are covered across the empire
    for key in ("campus", "commercial_hub", "industrial_zone", "holy_site"):
        assert spec.coverage.get(key, 0) >= 1
    # the capital builds the victory's primary (Campus for science)
    assert D.CAMPUS in spec.cities["C0"].districts


def test_specialization_respects_pool():
    """Unticking a district type removes it from every city AND from coverage guarantees."""
    from backend.optimizer.specialize import assign_specialization
    from backend.rules.modifiers import Loadout
    gm, cities = _specialization_board()
    pool = [d for d in D if d not in (D.CITY_CENTER, D.HOLY_SITE)]   # no Holy Sites allowed
    spec = assign_specialization(gm, cities, Loadout(victory="science"), pool)
    assert all(D.HOLY_SITE not in r.districts for r in spec.cities.values())
    assert spec.coverage.get("holy_site", 0) == 0


def test_america_leaders_present_and_bound():
    """All three America Leader-Pass personas exist and are bound to the civ."""
    from backend.rules.modifiers import CIVS, LEADERS
    assert "america" in CIVS
    for key in ("roosevelt_roughrider", "roosevelt_bullmoose", "abraham_lincoln"):
        assert key in LEADERS and LEADERS[key].civ == "america"
    assert LEADERS["abraham_lincoln"].victory == "domination"
    assert LEADERS["roosevelt_bullmoose"].victory == "culture"


def test_lincoln_puts_industrial_zone_in_every_city():
    """Lincoln's Emancipation Proclamation makes an Industrial Zone the meta everywhere."""
    from backend.optimizer.specialize import assign_specialization
    from backend.rules.modifiers import Loadout
    gm, cities = _specialization_board()
    pool = [d for d in D if d is not D.CITY_CENTER]
    spec = assign_specialization(gm, cities, Loadout(leader="abraham_lincoln", victory="domination"), pool)
    assert all(D.INDUSTRIAL_ZONE in r.districts for r in spec.cities.values())
    # Victoria "Age of Steam" (England) has the same IZ-everywhere effect
    sp_vic = assign_specialization(gm, cities, Loadout(leader="victoria_steam", victory="domination"), pool)
    assert all(D.INDUSTRIAL_ZONE in r.districts for r in sp_vic.cities.values())
    # a non-IZ leader specialises: NOT every city gets an Industrial Zone
    spec2 = assign_specialization(gm, cities, Loadout(victory="culture"), pool)
    assert sum(D.INDUSTRIAL_ZONE in r.districts for r in spec2.cities.values()) < len(cities)


def test_leader_pass_roster_present_and_bound():
    """All Leader-Pass personas are registered and bound to the right civ."""
    from backend.rules.modifiers import CIVS, LEADERS
    expect = {
        "julius_caesar": "rome", "nzinga_mbande": "kongo", "nader_shah": "persia",
        "yongle": "china", "qin_unifier": "china", "wu_zetian": "china",
        "ramses": "egypt", "cleopatra_ptolemaic": "egypt", "sundiata_keita": "mali",
        "theodora": "byzantium", "sejong": "korea", "ludwig": "germany",
        "elizabeth_i": "england", "victoria_steam": "england", "harald_varangian": "norway",
    }
    for key, civ in expect.items():
        assert key in LEADERS and LEADERS[key].civ == civ, key
        assert civ in CIVS


def test_assess_neighbors_classifies_rivals_and_city_states():
    """Neighbour advisor: nearby rival -> its meta victory; city-state -> its type/hint."""
    from backend.optimizer.neighbors import assess_neighbors
    from backend.rules.modifiers import Loadout
    our = [Hex(0, 0)]
    rivals = [
        {"q": 5, "r": 0, "name": "Hanseong", "population": 8, "kind": "major", "civ": "korea"},
        {"q": 3, "r": 0, "name": "Geneva", "population": 4, "kind": "city_state", "cs_type": "scientific"},
        {"q": 30, "r": 0, "name": "FarAway", "population": 5, "kind": "major", "civ": "rome"},  # out of radius
        {"q": 2, "r": 0, "name": "Wolves", "population": 0, "kind": "barbarian"},               # excluded
    ]
    out = assess_neighbors(our, rivals, Loadout(victory="science"), radius=12)
    assert len(out["rivals"]) == 1
    assert out["rivals"][0]["civ"] == "korea" and out["rivals"][0]["victory"] == "science"
    assert len(out["city_states"]) == 1 and out["city_states"][0]["type"] == "scientific"
    assert out["advice"]  # produced at least one strategic note


def test_theodora_holy_site_yields_culture_equal_to_adjacency():
    """Theodora 'Metanoia': a Holy Site also yields Culture equal to its Faith adjacency."""
    from backend.domain.models import YieldType as Y
    from backend.rules.adjacency import adjacency_yield
    from backend.rules.modifiers import Loadout
    gm = _board(2)
    for n in gm.neighbors(Hex(0, 0)):
        if n.coord != Hex(0, 0):
            n.terrain = Terrain.MOUNTAIN          # +1 Faith each -> +6
    base = adjacency_yield(gm, Hex(0, 0), D.HOLY_SITE, Loadout())
    theo = adjacency_yield(gm, Hex(0, 0), D.HOLY_SITE, Loadout(leader="theodora"))
    assert theo[Y.CULTURE] == base[Y.FAITH] and base[Y.FAITH] > 0


def test_meta_beliefs_one_per_slot():
    from backend.optimizer.advisor import meta_beliefs
    mb = meta_beliefs()
    cats = {p["category"] for p in mb["picks"]}
    assert cats == {"founder", "follower", "worship", "enhancer"}
    assert mb["note"]
