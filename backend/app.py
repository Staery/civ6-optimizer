"""FastAPI app: serves the web editor and the optimization API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .domain.hexgrid import Hex
from .i18n import localize, set_lang, tr
from .domain.models import (
    DistrictType,
    Feature,
    Improvement,
    Terrain,
    YieldType,
)
from .io.map_schema import map_from_dict
from .io.lualog_parser import parse_lua_log
from .optimizer import (
    assign_territory,
    estimate_amenities,
    estimate_housing,
    optimize_city,
    optimize_empire,
    recommend_wonders,
    suggest_first_city,
    suggest_settles,
)
from .optimizer.settle import MAX_SETTLE_DIST, STRATEGICS
from .optimizer.single_city import Placement
from .optimizer.advisor import (
    meta_beliefs, recommend_beliefs, recommend_pantheon, recommend_policies,
)
from .optimizer.empire_plan import plan_empire
from .optimizer.neighbors import assess_neighbors
from .optimizer.specialize import assign_specialization
from .domain.hexgrid import within_radius
from .rules.adjacency import (
    adjacency_yield,
    can_place,
    displayed_adjacency,
    raw_adjacency,
    weighted_score,
)
from .rules.districts import resolve_def
from .rules.appeal import BAND_LABEL_RU, band, neighborhood_housing
from .rules.buildings import building_yields
from .rules.city_limits import counts_toward_cap, district_cap, pop_to_unlock
from .rules.districts import DISTRICTS, OPTIMIZABLE
from .rules.modifiers import (
    BELIEFS,
    CIVS,
    FOCUS_DISTRICTS,
    GOVERNORS,
    LEADERS,
    MODIFIERS,
    PANTHEONS,
    SECRET_SOCIETIES,
    VICTORY_LABEL,
    Loadout,
    focus_weights,
)
from .optimizer.governors import assign_governors
from .rules.natural_wonders import NATURAL_WONDERS
from .rules.wonders import WONDERS

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DATA = ROOT / "data"

# Resource catalogue used by the editor palette. Categories drive colour-coding.
# Sea resources (any category, on water) give Harbor +1 adjacency.
RESOURCES: dict[str, list[str]] = {
    "bonus": ["wheat", "rice", "maize", "cattle", "sheep", "deer", "bananas",
              "stone", "copper", "fish", "crabs", "shellfish"],
    "luxury": ["wine", "incense", "dyes", "silk", "furs", "ivory", "jade",
               "marble", "gypsum", "pearls", "whales", "honey", "tea"],
    "strategic": ["horses", "iron", "niter", "coal", "oil", "aluminum", "uranium"],
}

class UTF8JSONResponse(JSONResponse):
    """JSON responses with an EXPLICIT ``charset=utf-8`` in the Content-Type.

    Starlette already encodes JSON bodies as UTF-8, so Cyrillic city names
    (Ньяни/Аудагост) are transmitted correctly; this just makes the charset
    explicit in the header so no client can second-guess it.
    """

    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return super().render(localize(content))   # RU -> EN when the request asked for it


async def _request_lang(request: Request) -> None:
    """Pick the response language: ``X-Lang`` header, then ``?lang=``, default Russian.

    Async on purpose: it runs in the request task, so the ContextVar it sets is
    seen by the (threadpool) endpoint and by the response/exception rendering.
    """
    set_lang(request.headers.get("x-lang") or request.query_params.get("lang"))


app = FastAPI(title="Civ 6 District Optimizer", default_response_class=UTF8JSONResponse,
              dependencies=[Depends(_request_lang)])


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return UTF8JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Palettes and option lists for the editor UI."""
    return {
        "terrains": [t.value for t in Terrain],
        "features": [f.value for f in Feature],
        "improvements": [i.value for i in Improvement],
        "yields": [y.value for y in YieldType],
        "optimizable_districts": [d.value for d in OPTIMIZABLE],
        "source_districts": [
            d.value for d in DISTRICTS if DISTRICTS[d].primary_yield is None
        ],
        "all_districts": [d.value for d in DistrictType],
        "resources": RESOURCES,
        "modifiers": [
            {"name": m.name, "label": m.label,
             "applies_to": m.applies_to.value if m.applies_to else None,
             "note": m.note}
            for m in MODIFIERS.values()
        ],
        "civs": [
            {
                "key": c.key, "label": c.label, "modifiers": list(c.modifiers), "note": c.note,
                "victory": c.victory, "victory_label": VICTORY_LABEL.get(c.victory, ""),
                "unique": c.unique,
                "focus": {y.value: w for y, w in focus_weights(c.victory).items() if w != 1.0},
                "recommend": list(FOCUS_DISTRICTS.get(c.victory, ())),
            }
            for c in CIVS.values()
        ],
        "leaders": [
            {
                "key": l.key, "label": l.label, "civ": l.civ,
                "modifiers": list(l.modifiers), "note": l.note,
                "victory": l.victory,  # may be "" -> frontend falls back to the civ's victory
            }
            for l in LEADERS.values()
        ],
        "pantheons": [
            {"key": p.key, "label": p.label, "note": p.note,
             "modeled": p.modeled, "modifier": p.modifier}
            for p in PANTHEONS.values()
        ],
        "governors": [
            {"key": g.key, "label": g.label, "note": g.note} for g in GOVERNORS.values()
        ],
        "secret_societies": [
            {"key": s.key, "label": s.label, "note": s.note}
            for s in SECRET_SOCIETIES.values()
        ],
        "beliefs": [
            {"key": b.key, "label": b.label, "category": b.category,
             "note": b.note, "modeled": b.modeled}
            for b in BELIEFS.values()
        ],
        "wonders": [
            {"key": w.key, "name": w.name, "era": w.era,
             "requires": w.requires, "value": w.value}
            for w in WONDERS
        ],
        "natural_wonders": [
            {"key": w.key, "name": w.name, "tiles": w.tiles, "terrain": w.terrain,
             "appeal": w.appeal, "note": w.note}
            for w in NATURAL_WONDERS
        ],
    }


@app.get("/api/sample")
def sample() -> JSONResponse:
    path = DATA / "sample_map.json"
    if not path.exists():
        raise HTTPException(404, "sample map not found; run scripts/build_sample.py")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


def _build_loadout(payload: dict[str, Any]) -> Loadout:
    lo = payload.get("loadout") or {}
    weights = {YieldType(k): float(v) for k, v in (lo.get("weights") or {}).items()
               if k in YieldType._value2member_map_}
    # Governor weight multipliers (Pingala -> science/culture, Magnus -> production, …).
    full_weights = {**{y: 1.0 for y in YieldType}, **weights}
    gov = GOVERNORS.get(lo.get("governor") or "")
    if gov:
        for y, mult in gov.weight_mult.items():
            full_weights[y] = full_weights.get(y, 1.0) * mult
    return Loadout(
        civ=lo.get("civ"),
        leader=lo.get("leader"),
        victory=str(lo.get("victory") or ""),
        pantheon=lo.get("pantheon"),
        governor=lo.get("governor"),
        secret_society=lo.get("secret_society"),
        religion_beliefs=list(lo.get("beliefs") or lo.get("religion_beliefs") or []),
        active_modifiers=list(lo.get("active_modifiers") or []),
        weights=full_weights,
        oc_weight=float(lo.get("oc_weight", 0.0) or 0.0),
        region_weight=float(lo.get("region_weight", 0.6) or 0.0),
    )


def _foreign_city_centers(payload: dict[str, Any]) -> list[Hex]:
    """Centers of ALL foreign cities (rival civs, city-states, free cities) from the
    payload. Civ 6 forbids founding within MIN_CITY_DIST of any of them, so the settle
    planner uses these for spacing even though city-states don't count as loyalty rivals."""
    return [
        Hex(int(rc["q"]), int(rc["r"]))
        for rc in payload.get("rival_cities", [])
        if "q" in rc and "r" in rc and rc.get("kind", "major") != "barbarian"
    ]


def _placement_dict(p: Placement, city_name: str) -> dict[str, Any]:
    return {
        "city": city_name,
        "district": p.district.value,
        "q": p.coord.q,
        "r": p.coord.r,
        "displayed": p.displayed,
        "score": round(p.score, 3),
        "opportunity": round(p.opportunity, 3),
        "yields": {y.value: round(v, 3) for y, v in p.yields.items()},
        # buildings ≈ the rest of the district's value (flat; planning estimate)
        "building": {y.value: round(v, 3) for y, v in building_yields(p.district).items()},
    }


def _building_summary(placements: list[dict[str, Any]], loadout: Loadout) -> dict[str, Any]:
    """Aggregate building yields across placed districts (display only)."""
    totals: dict[str, float] = {}
    weighted = 0.0
    for p in placements:
        for y, v in building_yields(DistrictType(p["district"])).items():
            totals[y.value] = totals.get(y.value, 0.0) + v
            weighted += loadout.weight(y) * v
    return {"yields": {k: round(v, 3) for k, v in totals.items()}, "weighted": round(weighted, 3)}


def _annotate_build_order(
    placements: list[dict[str, Any]], cities: list
) -> dict[str, Any]:
    """Plan the full layout 'for growth' but tag each district with a build phase.

    Mutates each placement dict, adding ``phase`` = "now" or "later" and
    ``unlock_pop`` (population needed) for capped districts queued behind the limit.
    Returns a per-city build plan summary.
    """
    pop_by_city = {c.name: c.population for c in cities}
    plan: dict[str, Any] = {}
    for c in cities:
        ps = [p for p in placements if p["city"] == c.name]
        capped = sorted(
            (p for p in ps if counts_toward_cap(DistrictType(p["district"]))),
            key=lambda p: p["score"], reverse=True,
        )
        uncapped = [p for p in ps if not counts_toward_cap(DistrictType(p["district"]))]
        pop = pop_by_city.get(c.name, 0)
        cap = district_cap(pop)            # 0 when population unknown
        for p in uncapped:
            p["phase"] = "now"; p["unlock_pop"] = 0   # infrastructure: always buildable
        for i, p in enumerate(capped):
            if cap == 0 or i < cap:        # cap==0 -> unknown population -> show all 'now'
                p["phase"] = "now"; p["unlock_pop"] = 0
            else:
                p["phase"] = "later"; p["unlock_pop"] = pop_to_unlock(i + 1)
        now = sum(1 for p in capped if p["phase"] == "now")
        plan[c.name] = {
            "population": pop, "cap": cap,
            "build_now": now, "queued": len(capped) - now,
            "pop_known": pop > 0,
        }
    return plan


def _best_legal_tile(gm, city, dtype: DistrictType, loadout, prefer=None, exclude=None):
    """Best empty, legal tile in the city for ``dtype`` (maximising ``prefer(tile,hex)``).

    Used to give each recommended infrastructure district a CONCRETE tile so the UI can
    mark it on the map — and to respect placement rules (Aqueduct next to center+water,
    Encampment/Preserve not next to center, Dam on floodplains-river, Canal geography…).
    ``exclude`` are hexes already claimed by other recommendations (avoid collisions).
    """
    best, best_s = None, None
    for hx in within_radius(city.center, city.work_radius):
        if hx == city.center or (exclude and hx in exclude):
            continue
        t = gm.get(hx)
        if t is None or t.district is not None:
            continue
        if not can_place(gm, hx, dtype, city, loadout):
            continue
        s = prefer(t, hx) if prefer else 0.0
        if best is None or s > best_s:
            best, best_s = hx, s
    return best


# Infrastructure that GIVES adjacency to other districts. Co-planning them in the
# optimizer (not just recommending afterwards) lets it place e.g. the Industrial Zone
# next to where an Aqueduct will sit, capturing the +2 Production. Maps the trigger
# district -> infra districts to add when a legal tile exists.
_SYNERGY_INFRA: dict[DistrictType, tuple[DistrictType, ...]] = {
    DistrictType.INDUSTRIAL_ZONE: (
        DistrictType.AQUEDUCT, DistrictType.DAM, DistrictType.CANAL,
    ),
}


def _augment_districts(gm, city, loadout, built: frozenset = frozenset()) -> list[DistrictType]:
    """Add adjacency-providing infrastructure to a city's requested set so the optimizer
    co-plans it (Aqueduct/Dam/Canal +2 to the Industrial Zone). Only adds a district
    when it has a legal tile and isn't already built; returns the new requested list.
    """
    req = list(city.requested)
    rset = set(req) | set(built)
    for trigger, infra in _SYNERGY_INFRA.items():
        if trigger not in set(req) and trigger not in built:
            continue
        for d in infra:
            if d not in rset and _best_legal_tile(gm, city, d, loadout) is not None:
                req.append(d)
                rset.add(d)
    return req


def _city_plan(gm, cities: list, loadout: Loadout, placements=None,
               taken: list[str] | None = None) -> dict[str, Any]:
    """Holistic per-city plan: Housing + Amenities balance and which EXTRA districts to
    add, EACH with a concrete tile so the UI marks them on the map. Accounts for
    districts already built (won't re-recommend) and for the optimizer's planned
    districts (applied below so infra placement sees occupancy/adjacency).
    """
    D = DistrictType
    # Reflect the optimizer's chosen placements on the map (occupancy + adjacency) so
    # infra recommendations don't reuse those tiles and Government Plaza sees districts.
    for p in (placements or []):
        t = gm.get(Hex(int(p["q"]), int(p["r"])))
        if t is not None and t.district is None:
            t.district = D(p["district"])

    housing = {h.city: h for h in estimate_housing(gm, cities, loadout)}
    amen = {a.city: a for a in estimate_amenities(gm, cities, loadout)}
    owner = assign_territory(gm, cities)

    existing: dict[str, set] = {c.name: set() for c in cities}
    coastal: dict[str, bool] = {c.name: False for c in cities}
    floodp: dict[str, bool] = {c.name: False for c in cities}
    ndist: dict[str, int] = {c.name: 0 for c in cities}
    trade_routes = 0
    plaza_exists = False
    for h, ci in owner.items():
        t = gm.get(h)
        if t is None:
            continue
        nm = cities[ci].name
        if t.district is not None:
            existing[nm].add(t.district)
            ndist[nm] += 1
            if t.district is D.GOVERNMENT_PLAZA:
                plaza_exists = True
            if t.district in (D.COMMERCIAL_HUB, D.HARBOR):
                trade_routes += 1
        if t.terrain.is_water:
            coastal[nm] = True
        if t.feature.value == "floodplains":
            floodp[nm] = True

    plaza_city = max(cities, key=lambda c: ndist[c.name]).name if cities else None
    n_adj_districts = lambda t, hx: sum(1 for n in gm.neighbors(hx) if n.district is not None)
    # appeal-driven, but among equal-appeal tiles prefer one ADJACENT to a district so the
    # generic +0.5 it grants is actually captured (see the re-evaluation pass below)
    by_appeal = lambda t, hx: t.appeal * 100 + n_adj_districts(t, hx)

    # World Wonders to BUILD, with tiles -> shown on the map like districts. AI can grab
    # them, so each carries a risk + alternative tiles; the user can mark one "taken" to
    # exclude it and re-plan. Already-built wonders are auto-excluded (detect_taken).
    wrecs, _taken = recommend_wonders(gm, cities, taken=taken, top=6)
    wonders = [{
        "key": w.key, "name": w.name, "q": w.q, "r": w.r, "value": w.value,
        "requires": w.requires, "risk": w.risk, "note": w.note,
        "alternatives": w.alternatives,
    } for w in wrecs]
    gov = GOVERNORS.get(loadout.governor or "")
    gov_note = gov.note if (gov and gov.key != "none") else ""
    trade_note = (
        tr("Торговые пути: ~{n} (каждый Ком. хаб/Гавань = +1 путь → рост, "
           "золото и производство; внутренние пути ускоряют новые города)", n=trade_routes)
        if trade_routes else ""
    )

    out = []
    gov_features: list[dict[str, Any]] = []
    for c in cities:
        h = housing.get(c.name)
        a = amen.get(c.name)
        ex = existing[c.name]
        gov_features.append({
            "city": c.name,
            "districts": {d.value for d in ex},   # built + optimizer-planned districts
            "coastal": coastal[c.name],
            "pop": c.population,
            "housing_surplus": None if h is None else h.surplus,
            "amenity_surplus": None if a is None else a.surplus,
        })
        recs: list[dict[str, Any]] = []
        used: set = set()      # tiles already claimed by a recommendation (no collisions)

        def add(dtype: DistrictType, why: str, prefer=None, cond: bool = True, min_appeal=None):
            # a district with nowhere legal to build is not actionable -> require a tile
            if not cond or dtype in ex:
                return
            tile = _best_legal_tile(gm, c, dtype, loadout, prefer, exclude=used)
            if tile is None or (min_appeal is not None and gm.get(tile).appeal < min_appeal):
                return
            used.add(tile)
            rec = {"district": dtype.value, "why": why, "q": tile.q, "r": tile.r}
            if dtype is D.NEIGHBORHOOD:
                ap = gm.get(tile).appeal
                rec["why"] = tr("Квартал на «{band}» клетке (+{housing} жилья)",
                                band=BAND_LABEL_RU[band(ap)], housing=neighborhood_housing(ap))
            recs.append(rec)

        # Amenities deficit -> Entertainment Complex / Water Park (next to districts -> +0.5 each)
        if a is not None and a.surplus < 0:
            if coastal[c.name] and D.WATER_PARK not in ex:
                add(D.WATER_PARK, tr("дефицит довольства {n} → +удобства (побережье)", n=a.surplus),
                    prefer=n_adj_districts)
            else:
                add(D.ENTERTAINMENT, tr("дефицит довольства {n} → +удобства", n=a.surplus),
                    prefer=n_adj_districts)
        # Housing -> Aqueduct + Neighborhood (placed on the best-appeal tile)
        if h is not None and c.population > 0 and h.surplus < 5:
            add(D.AQUEDUCT, "жильё до 6 + соседство Промзоне (+2)", prefer=n_adj_districts)
            add(D.NEIGHBORHOOD, "", prefer=by_appeal)
        # Dam for floodplains
        if floodp[c.name]:
            add(D.DAM, "поймы → жильё + защита от затоплений", prefer=n_adj_districts)
        # Government Plaza recommendation (if it wasn't co-planned into the optimizer)
        if not plaza_exists and c.name == plaza_city:
            add(D.GOVERNMENT_PLAZA, "+1 соседним районам и сильные здания (выбор политик/титулов)",
                prefer=n_adj_districts)
        # Preserve — only where a Charming+ tile exists (appeal -> faith/culture; не вырубай лес)
        add(D.PRESERVE, "Заповедник: вера/культура с привлекательности — не вырубай лес",
            prefer=by_appeal, min_appeal=2)
        # Canal — only if geography allows a legal tile (links water bodies, +Промзоне)
        add(D.CANAL, "Канал: связь морей/озёр + соседство Промзоне", prefer=n_adj_districts)

        out.append({
            "city": c.name,
            "housing": None if h is None else {
                "supply": h.supply, "surplus": h.surplus, "state": h.state,
                "state_label": h.state_label, "best_neighborhood": h.best_neighborhood,
                "best_neighborhood_band": h.best_neighborhood_band,
            },
            "amenities": None if a is None else {
                "required": a.required, "supply": a.supply, "surplus": a.surplus,
                "state": a.state, "state_label": a.state_label,
            },
            "recommend": recs,
        })

    # Recommend WHICH governor to seat in WHICH city (unique 1:1) from each city's
    # character + the player's victory weights, then attach the pick to its city.
    wsimple = {
        "science": loadout.weights.get(YieldType.SCIENCE, 1.0),
        "culture": loadout.weights.get(YieldType.CULTURE, 1.0),
        "gold": loadout.weights.get(YieldType.GOLD, 1.0),
        "faith": loadout.weights.get(YieldType.FAITH, 1.0),
        "production": loadout.weights.get(YieldType.PRODUCTION, 1.0),
    }
    gov_assign = assign_governors(gov_features, wsimple)
    for cp in out:
        cp["governor_rec"] = gov_assign.get(cp["city"])

    # Empire situation -> Pantheon / Policy-card advice. Count what the workable land
    # offers (dedup tiles) and which specialty districts exist, then rank the options.
    seen: set = set()
    counts: dict[str, int] = {}

    def _bump(k: str) -> None:
        counts[k] = counts.get(k, 0) + 1

    for c in cities:
        for hx in within_radius(c.center, c.work_radius):
            if hx in seen:
                continue
            seen.add(hx)
            t = gm.get(hx)
            if t is None:
                continue
            if t.terrain is Terrain.DESERT:
                _bump("desert")
            elif t.terrain is Terrain.TUNDRA:
                _bump("tundra")
            if t.feature is Feature.RAINFOREST:
                _bump("rainforest")
            elif t.feature in (Feature.MARSH, Feature.OASIS, Feature.FLOODPLAINS):
                _bump("reeds")
            if t.on_river:
                _bump("river")
            if t.appeal >= 2:
                _bump("high_appeal")
            if t.resource and t.terrain.is_water:
                _bump("sea_resource")
            if t.resource in STRATEGICS:
                _bump("strategic")
            if t.improvement is Improvement.PASTURE:
                _bump("pasture")
            elif t.improvement is Improvement.PLANTATION:
                _bump("plantation")
            elif (t.improvement is Improvement.MINE and t.resource
                  and t.resource not in STRATEGICS):
                _bump("mine_lux")
    all_districts = {d.value for s in existing.values() for d in s}
    setup_advice = {
        "pantheon": recommend_pantheon(counts, all_districts, loadout.civ,
                                       selected=loadout.pantheon),
        "policies": recommend_policies(all_districts),
        "beliefs": recommend_beliefs(all_districts, wsimple),
        "belief_meta": meta_beliefs(),
    }

    # Count EVERY adjacent district's bonus: apply the recommended districts to the map,
    # then re-evaluate each optimizer placement on the full layout. A Campus next to a
    # recommended Neighborhood/Entertainment/Plaza/Preserve now shows the extra adjacency
    # (+0.5 each, Government Plaza +1, Aqueduct/Dam/Canal +2 to the Industrial Zone).
    for cp in out:
        for rec in cp["recommend"]:
            if "q" in rec:
                rt = gm.get(Hex(int(rec["q"]), int(rec["r"])))
                if rt is not None and rt.district is None:
                    rt.district = D(rec["district"])
    for p in (placements or []):
        dt = D(p["district"])
        y = adjacency_yield(gm, Hex(int(p["q"]), int(p["r"])), dt, loadout)
        if not y:
            continue
        p["yields"] = {yt.value: round(v, 3) for yt, v in y.items()}
        ddef = resolve_def(dt, loadout.civ)
        if ddef is not None and ddef.primary_yield is not None:
            p["displayed"] = displayed_adjacency(y.get(ddef.primary_yield, 0.0))
        p["score"] = round(weighted_score(y, loadout), 3)

    ss = SECRET_SOCIETIES.get(loadout.secret_society or "")
    ss_note = ({"label": ss.label, "note": ss.note}
               if (ss and ss.key != "none") else None)
    return {"cities": out, "wonders": wonders, "governor": gov_note,
            "secret_society": ss_note, "trade": trade_note, "setup_advice": setup_advice}


@app.post("/api/optimize")
def optimize(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {ruleset?, tiles, cities, loadout?, city_name?}.

    One city -> single-city optimum. Multiple cities -> joint empire optimization
    (cross-city adjacency exploited). Placements are tagged with their city.
    """
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001 - surface a clean 400
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    if not cities:
        raise HTTPException(400, "no city defined (need a city center)")

    loadout = _build_loadout(payload)
    resp = _optimize_response(gm, cities, loadout,
                              taken=payload.get("taken"), city_name=payload.get("city_name"),
                              foreign_centers=_foreign_city_centers(payload))
    resp["neighbors"] = assess_neighbors([c.center for c in cities],
                                         payload.get("rival_cities"), loadout)
    return resp


# districts that, when planned, justify adding a Government Plaza (one per empire)
_SPECIALTY = {
    DistrictType.CAMPUS, DistrictType.HOLY_SITE, DistrictType.THEATER,
    DistrictType.COMMERCIAL_HUB, DistrictType.HARBOR, DistrictType.INDUSTRIAL_ZONE,
}

# A foreign city (rival civ or city-state) controls the tiles around it; you can't build a
# district on them. We block EMPTY NEUTRAL tiles within this radius of a foreign center so
# the optimizer never recommends a district hugging e.g. a city-state. Tiles you already own
# (owner_city set) or have a district on are left untouched.
FOREIGN_CONTROL_RADIUS = 3


def _block_foreign_control(gm, foreign_centers) -> None:
    for fc in foreign_centers or []:
        for h in within_radius(fc, FOREIGN_CONTROL_RADIUS):
            t = gm.get(h)
            if t is not None and t.owner_city is None and t.district is None:
                t.owner_city = "rival_cs"   # foreign control zone -> excluded from placement


def _optimize_response(gm, cities, loadout, taken=None, city_name=None,
                       pool=None, foreign_centers=None) -> dict[str, Any]:
    """Full optimize pipeline shared by /api/optimize and /api/plan-empire: specialize the
    cities, lock already-built districts, co-plan synergy infra, run the single/empire
    optimizer, and assemble the response (placements + build plan + city health).

    ``pool`` = the allowed district types (UI checkboxes). When None it's taken from the
    cities' requested lists (the /api/optimize path); /api/plan-empire passes it explicitly
    because its planted cities carry only a compact ranking set."""
    # Block tiles a foreign city (rival / city-state) controls so we never recommend a
    # district hugging it (you can't build on tiles you don't own).
    _block_foreign_control(gm, foreign_centers)
    # City SPECIALIZATION: assign each city a role + focused district set from the allowed
    # pool (the UI checkboxes) instead of building everything everywhere; this also places
    # the one-per-empire Government Plaza + Diplomatic Quarter in the best-suited city.
    if pool is None:
        pool = set().union(*(set(c.requested) for c in cities)) if cities else set()
    spec = assign_specialization(gm, cities, loadout, pool)
    for c in cities:
        cr = spec.cities.get(c.name)
        if cr is not None:
            c.requested = list(cr.districts)

    # Lock already-built districts: each specialty district is one-per-city in Civ 6, so
    # a type the player has ALREADY built must not be re-planned on a different tile.
    owner_of = assign_territory(gm, cities)
    built_types: dict[str, set] = {c.name: set() for c in cities}
    for h, ci in owner_of.items():
        t = gm.get(h)
        if t is not None and t.district not in (None, DistrictType.CITY_CENTER):
            built_types[cities[ci].name].add(t.district)

    auto_infra: set[str] = set()
    for c in cities:
        c.requested = [d for d in c.requested if d not in built_types[c.name]]
        before = set(c.requested)
        req = _augment_districts(gm, c, loadout, built=frozenset(built_types[c.name]))
        c.requested = req
        auto_infra |= {d.value for d in req if d not in before}

    spec_payload = {
        "cities": {name: {"role": cr.role, "label": cr.role_label, "reason": cr.reason,
                          "districts": [d.value for d in cr.districts]}
                   for name, cr in spec.cities.items()},
        "uniques": spec.uniques,
        "coverage": {k: v for k, v in spec.coverage.items() if v > 0},
    }

    if len(cities) > 1:
        res = optimize_empire(gm, cities, loadout)
        placements = [_placement_dict(p, name)
                      for name, ps in res.placements_by_city.items() for p in ps]
        build_plan = _annotate_build_order(placements, cities)
        buildings = _building_summary(placements, loadout)
        placements.sort(key=lambda d: d["score"], reverse=True)
        unplaceable = [f"{name}: {d.value}"
                       for name, ds in res.unplaceable.items() for d in ds]
        return {
            "multi": True,
            "method": res.method,
            "optimal": res.optimal,
            "total_score": round(res.total_score, 3),
            "total_yields": {y.value: round(v, 3) for y, v in res.total_yields.items()},
            "total_opportunity": round(res.total_opportunity, 3),
            "total_regional": round(res.total_regional, 3),
            "total_buildings": buildings["weighted"],
            "building_yields": buildings["yields"],
            "unplaceable": unplaceable,
            "territory": res.territory,
            "build_plan": build_plan,
            "city_health": _city_plan(gm, cities, loadout, placements, taken=taken),
            "auto_infra": sorted(auto_infra),
            "specialization": spec_payload,
            "cities": [c.name for c in cities],
            "placements": placements,
        }

    city = next((c for c in cities if c.name == city_name), cities[0])
    res = optimize_city(gm, city, loadout)
    placements = [_placement_dict(p, city.name) for p in res.placements]
    build_plan = _annotate_build_order(placements, [city])
    buildings = _building_summary(placements, loadout)
    return {
        "multi": False,
        "city": res.city,
        "method": res.method,
        "optimal": res.optimal,
        "total_score": round(res.total_score, 3),
        "total_yields": {y.value: round(v, 3) for y, v in res.total_yields.items()},
        "total_opportunity": round(res.total_opportunity, 3),
        "total_buildings": buildings["weighted"],
        "building_yields": buildings["yields"],
        "unplaceable": [d.value for d in res.unplaceable],
        "build_plan": build_plan,
        "city_health": _city_plan(gm, [city], loadout, placements, taken=taken),
        "auto_infra": sorted(auto_infra),
        "specialization": spec_payload,
        "placements": placements,
    }


@app.post("/api/plan-empire")
def plan_empire_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, cities?, settlers?, rival_cities?, loadout?, max_new?, max_dist?}.

    Jointly chooses WHERE to found up to ``max_new`` new cities so the resulting district
    layout is strongest (best combinations + cross-city packing), then returns the full
    optimize response for existing+new cities plus the chosen sites in ``new_sites``.
    """
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    loadout = _build_loadout(payload)
    settlers = [Hex(int(s["q"]), int(s["r"]))
                for s in payload.get("settlers", []) if "q" in s and "r" in s]
    if not cities and not settlers:
        raise HTTPException(400, "need at least one city or a settler to plan around")
    rivals = [
        (Hex(int(rc["q"]), int(rc["r"])), int(rc.get("population", 0) or 0))
        for rc in payload.get("rival_cities", [])
        if "q" in rc and "r" in rc and rc.get("kind", "major") in ("major", "free")
    ]
    max_new = max(0, min(int(payload.get("max_new", 5)), 25))
    max_dist = int(payload.get("max_dist", MAX_SETTLE_DIST))
    # Rank candidate sites by a COMPACT, victory-focused district set (not all districts):
    # it's accurate for a site's value and fast. Full per-city specialization is applied
    # later in _optimize_response on the whole empire.
    trial_focus = [DistrictType(d) for d in FOCUS_DISTRICTS.get(loadout.victory, ())]
    requested = trial_focus or list(OPTIMIZABLE)
    # the allowed pool for specialization = the user's checkboxes (existing cities carry it);
    # fall back to OPTIMIZABLE for a settler-only new empire.
    pool = set(cities[0].requested) if cities else set(OPTIMIZABLE)

    sites, full_cities = plan_empire(
        gm, cities, loadout, settlers=settlers, rival_cities=rivals,
        blocked_centers=_foreign_city_centers(payload),
        max_new=max_new, max_dist=max_dist, requested=requested,
    )
    resp = _optimize_response(gm, full_cities, loadout, taken=payload.get("taken"), pool=pool,
                              foreign_centers=_foreign_city_centers(payload))
    resp["new_sites"] = [
        {"q": s.coord.q, "r": s.coord.r, "site_score": s.site_score,
         "district_gain": s.district_gain, "total_gain": s.total_gain, "note": s.note}
        for s in sites
    ]
    resp["existing_cities"] = [c.name for c in cities]
    resp["neighbors"] = assess_neighbors([c.center for c in full_cities],
                                         payload.get("rival_cities"), loadout)
    return resp


@app.post("/api/suggest-cities")
def suggest_cities(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, cities?, count?}. Returns candidate city-center tiles."""
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    count = int(payload.get("count", 5))
    civ = (payload.get("loadout") or {}).get("civ")
    rivals = [
        (Hex(int(rc["q"]), int(rc["r"])), int(rc.get("population", 0) or 0))
        for rc in payload.get("rival_cities", [])
        if "q" in rc and "r" in rc
        # only major civs & free cities apply real settle/loyalty pressure
        and rc.get("kind", "major") in ("major", "free")
    ]
    max_dist = int(payload.get("max_dist", MAX_SETTLE_DIST))
    settlers = [
        Hex(int(s["q"]), int(s["r"]))
        for s in payload.get("settlers", []) if "q" in s and "r" in s
    ]
    sugg = suggest_settles(gm, cities, count=count, civ=civ, rival_cities=rivals,
                           max_dist=max_dist, settlers=settlers,
                           blocked_centers=_foreign_city_centers(payload))
    return {
        "suggestions": [
            {
                "q": s.coord.q, "r": s.coord.r, "score": s.score,
                "fresh_water": s.fresh_water, "coastal": s.coastal,
                "breakdown": s.breakdown, "note": s.note,
            }
            for s in sugg
        ]
    }


@app.post("/api/first-city")
def first_city(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, settler:{q,r}, loadout?, turn_penalty?, rival_cities?}.

    Recommends where to found the CAPITAL: tiles a Settler can reach in turns 1-3,
    penalising each lost turn (settle-in-place is the baseline).
    """
    try:
        gm, _ = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    s = payload.get("settler") or {}
    if "q" not in s or "r" not in s:
        raise HTTPException(400, "no settler position (need {settler:{q,r}})")
    settler = Hex(int(s["q"]), int(s["r"]))
    civ = (payload.get("loadout") or {}).get("civ")
    turn_penalty = float(payload.get("turn_penalty", 2.0) or 0.0)
    rivals = [
        (Hex(int(rc["q"]), int(rc["r"])), int(rc.get("population", 0) or 0))
        for rc in payload.get("rival_cities", [])
        if "q" in rc and "r" in rc
        # only major civs & free cities apply real settle/loyalty pressure
        and rc.get("kind", "major") in ("major", "free")
    ]
    sugg = suggest_first_city(gm, settler, civ=civ, turn_penalty=turn_penalty,
                              rival_cities=rivals, count=int(payload.get("count", 6)))
    return {
        "settler": {"q": settler.q, "r": settler.r},
        "suggestions": [
            {
                "q": s.coord.q, "r": s.coord.r, "score": s.score, "turn": s.turn,
                "fresh_water": s.fresh_water, "coastal": s.coastal,
                "breakdown": s.breakdown, "note": s.note,
            }
            for s in sugg
        ],
    }


@app.post("/api/amenities")
def amenities(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, cities}. Estimates each city's Amenity balance + advice."""
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    if not cities:
        raise HTTPException(400, "no city defined (need a city center)")
    loadout = _build_loadout(payload)
    reports = estimate_amenities(gm, cities, loadout)
    return {
        "cities": [
            {
                "city": r.city, "population": r.population, "required": r.required,
                "supply": r.supply, "surplus": r.surplus, "state": r.state,
                "state_label": r.state_label, "advice": r.advice,
            }
            for r in reports
        ]
    }


@app.post("/api/housing")
def housing(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, cities}. Estimates each city's Housing budget + growth advice."""
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    if not cities:
        raise HTTPException(400, "no city defined (need a city center)")
    loadout = _build_loadout(payload)
    reports = estimate_housing(gm, cities, loadout)
    return {
        "cities": [
            {
                "city": r.city, "population": r.population, "supply": r.supply,
                "surplus": r.surplus, "state": r.state, "state_label": r.state_label,
                "best_neighborhood": r.best_neighborhood,
                "best_neighborhood_band": r.best_neighborhood_band,
                "advice": r.advice, "breakdown": r.breakdown,
            }
            for r in reports
        ]
    }


@app.post("/api/suggest-wonders")
def suggest_wonders(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {tiles, cities?, taken?}. Recommends World Wonders and best tiles."""
    try:
        gm, cities = map_from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"bad map payload: {exc}") from exc
    taken = list(payload.get("taken") or [])
    recs, taken_all = recommend_wonders(gm, cities, taken=taken,
                                        top=int(payload.get("top", 12)))
    return {
        "taken": taken_all,
        "recommendations": [
            {
                "key": r.key, "name": r.name, "era": r.era, "risk": r.risk,
                "q": r.q, "r": r.r, "value": r.value,
                "requires": r.requires, "note": r.note, "alternatives": r.alternatives,
            }
            for r in recs
        ],
    }


def _default_lua_log() -> Path:
    # Civ 6 writes logs to %LOCALAPPDATA%\Firaxis Games\... (NOT Documents).
    base = Path(os.environ.get("LOCALAPPDATA")
                or Path(os.environ.get("USERPROFILE", str(Path.home()))) / "AppData" / "Local")
    return base / "Firaxis Games" / "Sid Meier's Civilization VI" / "Logs" / "Lua.log"


@app.get("/api/import-latest")
def import_latest(path: str | None = None) -> dict[str, Any]:
    """Read the live Lua.log directly from disk (server is local). Optional ?path=."""
    p = Path(path) if path else _default_lua_log()
    if not p.exists():
        raise HTTPException(
            404,
            tr("Lua.log не найден: {path}. Включи мод и EnableLuaDebugLibrary "
               "(см. mod/INSTALL_RU.md) и начни ход.", path=str(p)),
        )
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise HTTPException(500, tr("не удалось прочитать {path}: {error}", path=str(p), error=str(exc))) from exc
    result = parse_lua_log(text)
    result["source_path"] = str(p)
    try:
        result["mtime"] = p.stat().st_mtime
    except OSError:
        result["mtime"] = None
    if not result.get("tiles"):
        raise HTTPException(
            422, "В Lua.log нет строк CIV6OPT — мод не включён или ход ещё не начинался."
        )
    return result


@app.post("/api/import-lualog")
async def import_lualog(payload: dict[str, Any]) -> dict[str, Any]:
    """Body: {text: <contents of Lua.log produced by the export mod>}.

    Returns a map dict (tiles + the detected city) ready for the editor.
    """
    text = payload.get("text") or ""
    if not text.strip():
        raise HTTPException(400, "empty Lua.log text")
    try:
        result = parse_lua_log(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"parse error: {exc}") from exc
    if not result.get("tiles"):
        raise HTTPException(
            422,
            "no CIV6OPT tile lines found — did you enable the mod and press 'Export map'?",
        )
    return result


# Static assets (app.js, style.css) under /static.
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
