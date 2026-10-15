"""Map JSON (de)serialization — the shared format for the editor, Lua import and saves.

Schema (all coordinates are axial q/r):

```json
{
  "ruleset": "gathering_storm_nfp",
  "tiles": [
    {"q": 0, "r": 0, "terrain": "grassland", "feature": "none", "hills": false,
     "on_river": true, "resource": null, "improvement": "none", "appeal": 0,
     "wonder": null, "district": "city_center", "owner_city": "Capital"}
  ],
  "cities": [
    {"name": "Capital", "q": 0, "r": 0, "work_radius": 3,
     "requested": ["campus", "commercial_hub", "holy_site"]}
  ]
}
```
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.hexgrid import Hex
from ..domain.models import (
    City,
    DistrictType,
    Feature,
    GameMap,
    Improvement,
    Terrain,
    Tile,
)


def classify_resource(name: str | None, given: str | None = None) -> str | None:
    """Resource class ("bonus"/"luxury"/"strategic") for a resource name. Uses the value
    from the game export when given; otherwise looks the name up in our catalogues so
    manually-painted maps still block districts on luxuries/strategics correctly."""
    if given in ("bonus", "luxury", "strategic"):
        return given
    if not name:
        return None
    from ..optimizer.settle import LUXURIES, STRATEGICS  # local import avoids a cycle
    if name in STRATEGICS:
        return "strategic"
    if name in LUXURIES:
        return "luxury"
    return "bonus"


def _enum(enum_cls, value, default):
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def tile_from_dict(d: dict[str, Any]) -> Tile:
    return Tile(
        coord=Hex(int(d["q"]), int(d["r"])),
        terrain=_enum(Terrain, d.get("terrain"), Terrain.GRASSLAND),
        feature=_enum(Feature, d.get("feature"), Feature.NONE),
        hills=bool(d.get("hills", False)),
        on_river=bool(d.get("on_river", False)),
        river_edges=(None if d.get("river_edges") is None else int(d["river_edges"])),
        resource=d.get("resource"),
        resource_class=classify_resource(d.get("resource"), d.get("resource_class")),
        resource_revealed=d.get("resource_revealed"),
        improvement=_enum(Improvement, d.get("improvement"), Improvement.NONE),
        appeal=int(d.get("appeal", 0)),
        wonder=d.get("wonder"),
        natural_wonder=d.get("natural_wonder"),
        district=_enum(DistrictType, d.get("district"), None) if d.get("district") else None,
        owner_city=d.get("owner_city"),
        volcano=bool(d.get("volcano", False)),
    )


def tile_to_dict(t: Tile) -> dict[str, Any]:
    return {
        "q": t.coord.q,
        "r": t.coord.r,
        "terrain": t.terrain.value,
        "feature": t.feature.value,
        "hills": t.hills,
        "on_river": t.on_river,
        "river_edges": t.river_edges,
        "resource": t.resource,
        "resource_class": t.resource_class,
        "resource_revealed": t.resource_revealed,
        "improvement": t.improvement.value,
        "appeal": t.appeal,
        "wonder": t.wonder,
        "natural_wonder": t.natural_wonder,
        "district": t.district.value if t.district else None,
        "owner_city": t.owner_city,
    }


def city_from_dict(d: dict[str, Any]) -> City:
    return City(
        name=d["name"],
        center=Hex(int(d["q"]), int(d["r"])),
        work_radius=int(d.get("work_radius", 3)),
        requested=[DistrictType(x) for x in d.get("requested", [])],
        population=int(d.get("population", 0) or 0),
    )


def city_to_dict(c: City) -> dict[str, Any]:
    return {
        "name": c.name,
        "q": c.center.q,
        "r": c.center.r,
        "work_radius": c.work_radius,
        "requested": [d.value for d in c.requested],
    }


def map_from_dict(d: dict[str, Any]) -> tuple[GameMap, list[City]]:
    gm = GameMap(ruleset=d.get("ruleset", "gathering_storm_nfp"))
    for td in d.get("tiles", []):
        gm.set(tile_from_dict(td))
    cities = [city_from_dict(cd) for cd in d.get("cities", [])]
    return gm, cities


def map_to_dict(gm: GameMap, cities: list[City] | None = None) -> dict[str, Any]:
    return {
        "ruleset": gm.ruleset,
        "tiles": [tile_to_dict(t) for t in gm.tiles.values()],
        "cities": [city_to_dict(c) for c in (cities or [])],
    }


def load_map(path: str | Path) -> tuple[GameMap, list[City]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return map_from_dict(data)


def save_map(path: str | Path, gm: GameMap, cities: list[City] | None = None) -> None:
    Path(path).write_text(
        json.dumps(map_to_dict(gm, cities), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
