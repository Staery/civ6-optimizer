"""Build a rich sample map, save it to data/sample_map.json, run the optimizer.

Doubles as an end-to-end smoke test of domain + rules + optimizer + IO.
Run:  python scripts/build_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import (
    City,
    DistrictType,
    Feature,
    GameMap,
    Improvement,
    Terrain,
    Tile,
    YieldType,
)
from backend.io.map_schema import save_map
from backend.optimizer import optimize_city
from backend.rules.modifiers import Loadout

CENTER = Hex(0, 0)

# (q, r) -> attribute overrides on top of the default grassland tile.
OVERRIDES: dict[tuple[int, int], dict] = {
    (0, 0): dict(on_river=True, district=DistrictType.CITY_CENTER),
    # mountains (Campus / Holy Site adjacency)
    (2, -1): dict(terrain=Terrain.MOUNTAIN),
    (1, -1): dict(terrain=Terrain.MOUNTAIN),
    # natural wonder (Holy Site +2)
    (0, -2): dict(feature=Feature.NATURAL_WONDER),
    # river tiles (Commercial Hub +2)
    (0, 1): dict(on_river=True),
    (1, 0): dict(on_river=True),
    # coastal inlet with sea resources (Harbor)
    (-1, 0): dict(terrain=Terrain.COAST),
    (-2, 0): dict(terrain=Terrain.COAST, resource="crabs"),
    (-1, -1): dict(terrain=Terrain.COAST, resource="fish"),
    (-2, 1): dict(terrain=Terrain.COAST),
    (-2, -1): dict(terrain=Terrain.COAST),
    # hills + mines (Industrial Zone)
    (2, 0): dict(terrain=Terrain.PLAINS, hills=True, improvement=Improvement.MINE),
    (2, 1): dict(terrain=Terrain.PLAINS, hills=True, improvement=Improvement.MINE),
    # a world wonder (Theater Square +2)
    (1, 2): dict(wonder="Pyramids"),
}


def build_map() -> tuple[GameMap, City]:
    gm = GameMap()
    for h in within_radius(CENTER, 3):
        gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND, owner_city="Capital"))
    for (q, r), attrs in OVERRIDES.items():
        t = gm.get(Hex(q, r))
        for k, v in attrs.items():
            setattr(t, k, v)
    city = City(
        name="Capital",
        center=CENTER,
        work_radius=3,
        requested=[
            DistrictType.CAMPUS,
            DistrictType.HOLY_SITE,
            DistrictType.COMMERCIAL_HUB,
            DistrictType.HARBOR,
            DistrictType.INDUSTRIAL_ZONE,
            DistrictType.THEATER,
        ],
    )
    return gm, city


def main() -> None:
    gm, city = build_map()
    out = Path(__file__).resolve().parents[1] / "data" / "sample_map.json"
    save_map(out, gm, [city])
    print(f"saved sample map -> {out}")

    # Weight science a bit higher just to show weights working.
    loadout = Loadout(weights={**{y: 1.0 for y in YieldType}, YieldType.SCIENCE: 1.2})
    res = optimize_city(gm, city, loadout)

    print(f"\nCity: {res.city}   method={res.method}  optimal={res.optimal}")
    print(f"total weighted score = {res.total_score:.2f}")
    print("total yields = " + ", ".join(f"{y.value}:{v:g}" for y, v in res.total_yields.items()))
    print("\nplacements:")
    for p in res.placements:
        yld = ", ".join(f"{y.value} +{v:g}" for y, v in p.yields.items())
        print(f"  {p.district.value:16s} @ ({p.coord.q:+d},{p.coord.r:+d})  "
              f"shown +{p.displayed}  [{yld}]  score={p.score:.2f}")
    if res.unplaceable:
        print("unplaceable:", [d.value for d in res.unplaceable])


if __name__ == "__main__":
    main()
