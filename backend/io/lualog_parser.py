"""Parse the Civ 6 in-game export (Lua.log) produced by ``mod/Civ6MapExporter``.

The mod prints one line per plot. We tag every line with ``CIV6OPT|`` so it is
easy to find amid the rest of Lua.log. Line schema (``|``-separated):

    CIV6OPT|TILE|x|y|terrain|feature|isNW|resource|resClass|river|hills|owner|district|wonder

plus one header line:

    CIV6OPT|META|player|<id>|civ|<CIVILIZATION_*>|width|<w>|height|<h>|wrapX|<0/1>

Civ 6 uses *offset* (x, y) coordinates; we convert to axial and recenter on the
local player's first City Center so the capital sits near (0, 0) in the editor.

NOTE: the offset parity (odd-r vs even-r) and the type-name maps below should be
verified against a real export on first use; unknown types degrade gracefully to
sensible defaults and are counted in ``warnings``.
"""

from __future__ import annotations

from typing import Any

from ..i18n import tr
from ..rules.natural_wonders import NW_BY_KEY

TAG = "CIV6OPT|"


def _match_nw(feature_name: str) -> str | None:
    """Best-effort map a Civ 6 natural-wonder FEATURE_* name to a catalogue key."""
    norm = feature_name.replace("FEATURE_", "").lower()
    if norm in NW_BY_KEY:
        return norm
    for key in NW_BY_KEY:
        if key in norm or norm in key:
            return key
    return None

# --- type maps (Civ 6 GameInfo type names -> our schema) ------------------------

_TERRAIN_BASE = {
    "GRASS": "grassland", "PLAINS": "plains", "DESERT": "desert",
    "TUNDRA": "tundra", "SNOW": "snow", "COAST": "coast", "OCEAN": "ocean",
}

_FEATURE = {
    "FEATURE_FOREST": "woods",
    "FEATURE_JUNGLE": "rainforest",
    "FEATURE_MARSH": "marsh",
    "FEATURE_OASIS": "oasis",
    "FEATURE_REEF": "reef",
    "FEATURE_ICE": "ice",
    "FEATURE_GEOTHERMAL_FISSURE": "geothermal_fissure",
    "FEATURE_VOLCANIC_SOIL": "volcanic_soil",
}

_DISTRICT = {
    "DISTRICT_CITY_CENTER": "city_center",
    "DISTRICT_CAMPUS": "campus",
    "DISTRICT_HOLY_SITE": "holy_site",
    "DISTRICT_THEATER": "theater_square",
    "DISTRICT_ENTERTAINMENT_COMPLEX": "entertainment_complex",
    "DISTRICT_COMMERCIAL_HUB": "commercial_hub",
    "DISTRICT_HARBOR": "harbor",
    "DISTRICT_INDUSTRIAL_ZONE": "industrial_zone",
    "DISTRICT_AQUEDUCT": "aqueduct",
    "DISTRICT_DAM": "dam",
    "DISTRICT_CANAL": "canal",
    "DISTRICT_ENCAMPMENT": "encampment",
    "DISTRICT_GOVERNMENT": "government_plaza",
    "DISTRICT_NEIGHBORHOOD": "neighborhood",
    "DISTRICT_AERODROME": "aerodrome",
    "DISTRICT_SPACEPORT": "spaceport",
    "DISTRICT_WATER_PARK": "water_park",
    "DISTRICT_PRESERVE": "preserve",
    "DISTRICT_DIPLOMATIC_QUARTER": "diplomatic_quarter",
    # civ-unique districts -> their standard equivalent
    "DISTRICT_LAVRA": "holy_site",            # Russia
    "DISTRICT_SEOWON": "campus",              # Korea
    "DISTRICT_OBSERVATORY": "campus",         # Maya
    "DISTRICT_HANSA": "industrial_zone",      # Germany
    "DISTRICT_OPPIDUM": "industrial_zone",    # Gaul
    "DISTRICT_SUGUBA": "commercial_hub",      # Mali
    "DISTRICT_COTHON": "harbor",              # Carthage
    "DISTRICT_ROYAL_NAVY_DOCKYARD": "harbor", # England
    "DISTRICT_ACROPOLIS": "theater_square",   # Greece
    "DISTRICT_BATH": "aqueduct",              # Rome
    "DISTRICT_MBANZA": "neighborhood",        # Kongo
    "DISTRICT_THANH": "encampment",           # Vietnam (Thành)
    "DISTRICT_IKANDA": "encampment",          # Zulu
}

# Tile improvements we care about (housing, Industrial-Zone & Observatory adjacency,
# appeal). Unmapped improvements (camp, fort, …) fall through to "none".
_IMPROVEMENT = {
    "IMPROVEMENT_FARM": "farm",
    "IMPROVEMENT_MINE": "mine",
    "IMPROVEMENT_QUARRY": "quarry",
    "IMPROVEMENT_PASTURE": "pasture",
    "IMPROVEMENT_PLANTATION": "plantation",
    "IMPROVEMENT_LUMBER_MILL": "lumber_mill",
    "IMPROVEMENT_FISHING_BOATS": "fishing_boats",
}

# Features that are NOT natural wonders (everything else FEATURE_* is treated as one).
_KNOWN_FEATURES = {
    "FEATURE_FOREST", "FEATURE_JUNGLE", "FEATURE_MARSH", "FEATURE_OASIS",
    "FEATURE_REEF", "FEATURE_ICE", "FEATURE_GEOTHERMAL_FISSURE",
    "FEATURE_VOLCANIC_SOIL", "FEATURE_VOLCANO",
}

DEFAULT_REQUESTED = [
    "campus", "holy_site", "commercial_hub", "harbor", "industrial_zone", "theater_square",
]


def _parse_terrain(name: str) -> tuple[str, bool, bool]:
    """Return (terrain, hills, is_mountain) from a TERRAIN_* type name."""
    n = name.upper().replace("TERRAIN_", "")
    is_mountain = n.endswith("_MOUNTAIN")
    hills = n.endswith("_HILLS")
    base_key = n.replace("_MOUNTAIN", "").replace("_HILLS", "")
    terrain = _TERRAIN_BASE.get(base_key, "grassland")
    return terrain, hills, is_mountain


def _offset_to_axial(x: int, y: int) -> tuple[int, int]:
    # odd-r offset -> axial (Red Blob Games). Parity may need flipping per game build.
    q = x - (y - (y & 1)) // 2
    r = y
    return q, r


def _short_resource(name: str) -> str | None:
    if not name or name.upper() in ("NONE", "-1", "RESOURCE_NONE"):
        return None
    return name.upper().replace("RESOURCE_", "").lower()


def _res_class(name: str) -> str | None:
    """Civ 6 ResourceClassType -> bonus / luxury / strategic (drives district legality)."""
    n = (name or "").upper()
    if "LUXURY" in n:
        return "luxury"
    if "STRATEGIC" in n:
        return "strategic"
    if "BONUS" in n:
        return "bonus"
    return None


def _belief_key(name: str) -> str | None:
    """Civ 6 BELIEF_* type (pantheon or religion belief) -> our catalogue key."""
    if not name or name.upper() in ("NONE", "BELIEF_NONE", "-1", ""):
        return None
    return name.upper().replace("BELIEF_", "").lower()


def _gov_key(name: str) -> str | None:
    if not name or name.upper() in ("NONE", "GOVERNMENT_NONE", "-1", ""):
        return None
    return name.upper().replace("GOVERNMENT_", "").lower()


def parse_lua_log(text: str) -> dict[str, Any]:
    warnings: list[str] = []
    meta: dict[str, Any] = {}
    raw_tiles: list[dict[str, Any]] = []
    # (player, cityID) -> {"name", "x", "y", "capital", "pop"}; latest dump wins.
    city_records: dict[tuple[int, int], dict[str, Any]] = {}
    settlers_raw: list[tuple[int, int]] = []   # local player's Settler (x, y) positions
    player_kind: dict[int, str] = {}   # player id -> major / city_state / free / barbarian
    player_civ: dict[int, str] = {}    # player id -> CIVILIZATION_* type (rival identity)
    player_leader: dict[int, str] = {} # player id -> LEADER_* (city-states encode category)
    game_modes: set[str] = set()       # detected NFP modes (e.g. Secret Societies via ley lines)
    loadout_data: dict[str, Any] = {}  # local player's pantheon / beliefs / government
    local_player: int | None = None

    for line in text.splitlines():
        idx = line.find(TAG)
        if idx < 0:
            continue
        parts = line[idx:].strip().split("|")
        if len(parts) < 2:
            continue
        kind = parts[1]

        if kind == "META":
            kv = parts[2:]
            for i in range(0, len(kv) - 1, 2):
                meta[kv[i]] = kv[i + 1]
            try:
                local_player = int(meta.get("player", "-1"))
            except ValueError:
                local_player = None
            continue

        if kind == "BEGIN":
            raw_tiles = []        # keep only the latest dump
            city_records = {}
            settlers_raw = []
            player_kind = {}
            player_civ = {}
            player_leader = {}
            loadout_data = {}
            continue
        if kind == "END":
            continue

        if kind == "LOADOUT":
            # LOADOUT|pantheon|<BELIEF_*>|beliefs|<csv>|government|<GOVERNMENT_*>
            kv = parts[2:]
            d = {kv[i]: kv[i + 1] for i in range(0, len(kv) - 1, 2)}
            pantheon = _belief_key(d.get("pantheon", ""))
            beliefs = [k for b in d.get("beliefs", "").split(",")
                       if (k := _belief_key(b)) is not None]
            gov = _gov_key(d.get("government", ""))
            loadout_data = {}
            if pantheon:
                loadout_data["pantheon"] = pantheon
            if beliefs:
                loadout_data["religion_beliefs"] = beliefs
            if gov:
                loadout_data["government"] = gov
            continue

        if kind == "PLAYER":
            # PLAYER|id|kind|civType?|leaderType?
            if len(parts) >= 4:
                try:
                    pid = int(parts[2])
                except ValueError:
                    continue
                player_kind[pid] = parts[3]
                if len(parts) > 4 and parts[4]:
                    player_civ[pid] = parts[4]
                if len(parts) > 5 and parts[5]:
                    player_leader[pid] = parts[5]
            continue

        if kind == "CITY":
            # CITY|x|y|ownerPlayer|cityID|isCapital|population|name  (name may have spaces;
            # population is optional for backward compatibility with older logs)
            if len(parts) < 7:
                continue
            try:
                cx, cy, cpl, cid = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                cap = parts[6] == "1"
            except ValueError:
                continue
            pop = 0
            name_parts = parts[7:]
            if len(parts) >= 8:
                try:
                    pop = int(parts[7]); name_parts = parts[8:]   # new format with population
                except ValueError:
                    pop = 0; name_parts = parts[7:]               # old format: name only
            name = "|".join(name_parts).strip() or f"City {cid}"
            city_records[(cpl, cid)] = {"name": name, "x": cx, "y": cy, "capital": cap, "pop": pop}
            continue

        if kind == "SETTLER":
            if len(parts) >= 4:
                try:
                    settlers_raw.append((int(parts[2]), int(parts[3])))
                except ValueError:
                    pass
            continue

        if kind != "TILE" or len(parts) < 14:
            continue
        try:
            x, y = int(parts[2]), int(parts[3])
        except ValueError:
            continue
        terrain, hills, is_mountain = _parse_terrain(parts[4])
        feature_name = parts[5].upper()
        is_nw = parts[6] == "1"
        if "LEY_LINE" in feature_name or "LEY_LINE" in parts[7].upper():
            game_modes.add("secret_societies")     # Hermetic Order reveals Ley Lines
        resource = _short_resource(parts[7])
        resource_class = _res_class(parts[8]) if len(parts) > 8 else None
        resource_revealed = (parts[18] == "1") if len(parts) > 18 else None
        river = parts[9] == "1"
        hills = hills or parts[10] == "1"
        try:
            owner = int(parts[11])
        except ValueError:
            owner = -1
        try:
            owning_city = int(parts[14]) if len(parts) > 14 else -1
        except ValueError:
            owning_city = -1
        try:
            appeal = int(parts[15]) if len(parts) > 15 else 0   # optional (older logs omit it)
        except ValueError:
            appeal = 0
        improvement = _IMPROVEMENT.get(parts[16].upper(), "none") if len(parts) > 16 else "none"
        try:                                   # river edges crossing this tile (Dam rule)
            river_edges = int(parts[17]) if len(parts) > 17 else None
        except ValueError:
            river_edges = None

        # --- feature / natural wonder (NWs often arrive with isNW=0 -> detect by name) ---
        feature = "none"
        nw_key = None
        is_volcano = False
        fn = feature_name
        if fn in ("NONE", "FEATURE_NONE", ""):
            feature = "none"                 # no feature (must precede the FEATURE_ check)
        elif fn.startswith("FEATURE_FLOODPLAINS"):
            feature = "floodplains"          # FLOODPLAINS, _GRASSLAND, _PLAINS
        elif fn in _FEATURE:
            feature = _FEATURE[fn]
        elif fn == "FEATURE_VOLCANO":
            feature = "none"; is_volcano = True   # impassable volcano (sits on a mountain)
        elif fn in _KNOWN_FEATURES:
            feature = "none"
        elif is_nw or fn.startswith("FEATURE_"):
            feature = "natural_wonder"
            nw_key = _match_nw(fn)           # may be None for NWs not in the catalogue
            if "VOLCANO" in fn:
                is_volcano = True            # named NW volcanoes (Vesuvius, Kilimanjaro…) still erupt
        else:
            warnings.append(f"unknown feature {fn}")

        # --- district / world wonder ---
        dn = parts[12].upper()
        wonder = None
        district = None
        if dn == "DISTRICT_WONDER":
            wonder = "World Wonder"          # a World Wonder occupies this tile
        elif dn not in ("NONE", "DISTRICT_NONE", ""):
            district = _DISTRICT.get(dn)
            if district is None:
                warnings.append(f"unknown district {dn}")
        wonder_name = parts[13].upper() if len(parts) > 13 else "NONE"
        if wonder_name not in ("NONE", "WONDER_NONE", ""):
            wonder = wonder_name.replace("WONDER_", "").title().replace("_", " ")

        q, r = _offset_to_axial(x, y)
        raw_tiles.append({
            "q": q, "r": r,
            "terrain": "mountain" if is_mountain else terrain,
            "feature": feature,
            "hills": hills and not is_mountain,
            "on_river": river,
            "river_edges": river_edges,
            "resource": resource,
            "resource_class": resource_class,
            "resource_revealed": resource_revealed,
            "improvement": improvement,
            "wonder": wonder,
            "natural_wonder": nw_key,
            "district": district,
            "volcano": is_volcano,
            "appeal": appeal,
            "_owner": owner,
            "_city": owning_city,
        })

    if not raw_tiles:
        return {"ruleset": "gathering_storm_nfp", "tiles": [], "cities": [],
                "warnings": warnings, "meta": meta,
                "loadout": loadout_data or None}

    # offset->axial for the city roster, so names line up with recentered tiles
    for rec in city_records.values():
        rec["q"], rec["r"] = _offset_to_axial(rec["x"], rec["y"])

    # local player's cities, capital first (drives the recenter origin)
    local_cities = [
        {"player": pl, "cid": cid, **rec}
        for (pl, cid), rec in city_records.items()
        if local_player is None or pl == local_player
    ]
    local_cities.sort(key=lambda c: (not c["capital"], c["cid"]))

    # fallback for old logs without CITY lines: derive centers from city-center tiles
    center_tiles = [t for t in raw_tiles
                    if t["district"] == "city_center"
                    and (local_player is None or t["_owner"] == local_player)]
    if not local_cities and center_tiles:
        local_cities = [
            {"player": local_player, "cid": -1 - i, "name": "Capital" if i == 0 else tr("Город {n}", n=i + 1),
             "q": t["q"], "r": t["r"], "capital": i == 0}
            for i, t in enumerate(center_tiles)
        ]

    settler_axial = [_offset_to_axial(sx, sy) for (sx, sy) in settlers_raw]

    if local_cities:
        origin = (local_cities[0]["q"], local_cities[0]["r"])
    elif center_tiles:
        origin = (center_tiles[0]["q"], center_tiles[0]["r"])
    elif settler_axial:
        origin = settler_axial[0]            # new game: recenter on the Settler
    else:
        origin = (raw_tiles[0]["q"], raw_tiles[0]["r"])

    # (player, cityID) -> display name, to label each tile by its owning city
    name_by_key = {(pl, cid): rec["name"] for (pl, cid), rec in city_records.items()}

    # Classify each player. Prefer the mod's PLAYER lines; otherwise fall back to a
    # heuristic: a player owning exactly ONE city is almost certainly a city-state
    # (city-states never expand), the rest are treated as major civs.
    cities_per_player: dict[int, int] = {}
    for (pl, _cid) in city_records:
        cities_per_player[pl] = cities_per_player.get(pl, 0) + 1

    def kind_of(pl: int) -> str:
        if pl in player_kind:
            return player_kind[pl]
        return "city_state" if cities_per_player.get(pl, 0) == 1 else "major"

    tiles: list[dict[str, Any]] = []
    for t in raw_tiles:
        owner = t.pop("_owner")
        cid = t.pop("_city")
        if local_player is None or owner == local_player:
            t["owner_city"] = name_by_key.get((owner, cid)) or "Capital"
            t["owner_kind"] = "own"
        elif owner < 0:
            t["owner_city"] = None
            t["owner_kind"] = None
        else:
            t["owner_city"] = f"rival{owner}"  # excluded from placement by optimizer
            t["owner_kind"] = kind_of(owner)   # major / city_state / free / barbarian
        t["q"] -= origin[0]
        t["r"] -= origin[1]
        tiles.append(t)

    # one city per local city center (recentered) -> enables empire mode + real names
    cities = [
        {"name": c["name"], "q": c["q"] - origin[0], "r": c["r"] - origin[1],
         "work_radius": 3, "requested": DEFAULT_REQUESTED,
         "population": c.get("pop", 0)}
        for c in local_cities
    ]

    # Settler positions (recentered) -> shown on the map + future "first city" planner.
    settlers = [
        {"q": q - origin[0], "r": r - origin[1]} for (q, r) in settler_axial
    ]

    # Rival cities (recentered) with population + kind -> loyalty pressure / display.
    # Barbarians don't found cities; exclude them defensively. ``civ`` (rival identity ->
    # meta victory) and ``cs_type`` (city-state category) come from the PLAYER export.
    def _civ_key(pid: int) -> str | None:
        ct = player_civ.get(pid, "")
        return ct[len("CIVILIZATION_"):].lower() if ct.startswith("CIVILIZATION_") else None

    def _cs_type(pid: int) -> str | None:
        lt = player_leader.get(pid, "")
        i = lt.find("MINOR_CIV_")
        return lt[i + len("MINOR_CIV_"):].lower() if i >= 0 else None

    rival_cities = []
    for (pl, cid), rec in city_records.items():
        if local_player is None or pl == local_player or kind_of(pl) == "barbarian":
            continue
        k = kind_of(pl)
        entry = {"q": rec["q"] - origin[0], "r": rec["r"] - origin[1],
                 "name": rec["name"], "population": rec.get("pop", 0), "kind": k}
        if k == "city_state":
            t = _cs_type(pl)
            if t:
                entry["cs_type"] = t
        else:
            c = _civ_key(pl)
            if c:
                entry["civ"] = c
        rival_cities.append(entry)

    # de-duplicate warnings for a compact summary
    seen: dict[str, int] = {}
    for w in warnings:
        seen[w] = seen.get(w, 0) + 1
    warn_summary = [f"{w} (x{n})" if n > 1 else w for w, n in seen.items()]

    return {
        "ruleset": "gathering_storm_nfp",
        "tiles": tiles,
        "cities": cities,
        "settlers": settlers,
        "rival_cities": rival_cities,
        "city_name": cities[0]["name"] if cities else "Capital",
        "warnings": warn_summary,
        "game_modes": sorted(game_modes),
        "loadout": loadout_data or None,
        "meta": meta,
    }
