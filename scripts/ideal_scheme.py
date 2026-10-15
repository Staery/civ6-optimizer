"""Build a 'perfect capital' terrain and let the optimizer compute the ideal
district packing. Used to validate the corrected adjacency rules end-to-end and
to print a reusable ideal scheme.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import (
    City, DistrictType as D, Feature, GameMap, Improvement, Terrain, Tile, YieldType,
)
from backend.rules.modifiers import Loadout
from backend.rules.adjacency import raw_adjacency, adjacency_yield, displayed_adjacency
from backend.optimizer.single_city import optimize_city

C = Hex(0, 0)
gm = GameMap()

# default: flat grassland, buildable land
for h in within_radius(C, 3):
    gm.set(Tile(coord=h, terrain=Terrain.GRASSLAND))

def sett(q, r, **kw):
    t = gm.get(Hex(q, r))
    for k, v in kw.items():
        setattr(t, k, v)

# --- City center, river corridor (fresh water + Commercial Hub +2) ---
sett(0, 0, district=D.CITY_CENTER, on_river=True)
for q, r in [(0, 1), (0, -1), (1, -1), (-1, 1), (1, 0)]:
    sett(q, r, on_river=True)

# --- West: mountains (Campus/Holy Site +1 each) + a geothermal fissure (Campus +2) ---
sett(-1, 0, terrain=Terrain.MOUNTAIN)
sett(-2, 0, terrain=Terrain.MOUNTAIN)
sett(-1, -1, terrain=Terrain.MOUNTAIN)
sett(-2, 1, terrain=Terrain.MOUNTAIN)
sett(-2, -1, feature=Feature.GEOTHERMAL_FISSURE)      # Campus +2
sett(-1, -2, feature=Feature.NATURAL_WONDER)          # Holy Site +2

# --- East / South-East: coast with sea resources (Harbor) ---
for q, r in [(2, 0), (2, -1), (1, 1), (2, 1)]:
    sett(q, r, terrain=Terrain.COAST)
sett(2, 0, resource="crabs", resource_class="bonus")  # Harbor +1
sett(2, 1, resource="fish", resource_class="bonus")   # Harbor +1

# --- Floodplains on the river (Dam) + strategic resource & quarry (Industrial Zone) ---
sett(0, 1, feature=Feature.FLOODPLAINS, river_edges=2)   # Dam-eligible
sett(-1, 1, feature=Feature.FLOODPLAINS, river_edges=2)  # Dam-eligible
sett(1, 1, resource="iron", resource_class="strategic")  # IZ +1
sett(0, 2, improvement=Improvement.QUARRY)               # IZ +1

# --- A World Wonder + Entertainment fuel for the Theater (+2 each) ---
sett(-1, 2, wonder="Pyramids")     # Theater +2 (occupies tile)
# high-appeal tiles (Preserve / general)
for q, r in [(1, 2), (2, -1)]:
    sett(q, r, appeal=4)

city = City("Capital", C, work_radius=3, requested=[
    D.CAMPUS, D.HOLY_SITE, D.THEATER, D.COMMERCIAL_HUB, D.HARBOR,
    D.INDUSTRIAL_ZONE, D.AQUEDUCT, D.DAM, D.GOVERNMENT_PLAZA, D.ENTERTAINMENT,
])

lo = Loadout(oc_weight=0.0)  # pure adjacency packing
res = optimize_city(gm, city, lo)

# Apply result to a fresh map so we can read each district's neighbours
placed = {p.coord: p.district for p in res.placements}
work = GameMap(tiles={h: __import__("copy").copy(t) for h, t in gm.tiles.items()})
for h, d in placed.items():
    work.get(h).district = d

NAME = {
    D.CAMPUS: "Кампус", D.HOLY_SITE: "Свят.место", D.THEATER: "Театр",
    D.COMMERCIAL_HUB: "Ком.хаб", D.HARBOR: "Гавань", D.INDUSTRIAL_ZONE: "Промзона",
    D.AQUEDUCT: "Акведук", D.DAM: "Дамба", D.GOVERNMENT_PLAZA: "Правит.пл.",
    D.ENTERTAINMENT: "Развл.компл.", D.CITY_CENTER: "Центр",
}

print(f"\nМетод: {res.method}  optimal={res.optimal}")
print(f"Суммарное взвешенное соседство: {res.total_score:.1f}\n")
print(f"{'Район':<14}{'клетка':<10}{'в игре':<8}raw")
print("-" * 44)
for p in sorted(res.placements, key=lambda p: -p.score):
    ddef_yield = adjacency_yield(work, p.coord, p.district, lo)
    yval = list(ddef_yield.values())[0] if ddef_yield else 0.0
    coord = f"({p.coord.q},{p.coord.r})"
    print(f"{NAME[p.district]:<14}{coord:<10}+{p.displayed:<7}{yval:.1f}")
if res.unplaceable:
    print("\nне разместить:", [NAME[d] for d in res.unplaceable])

# neighbour breakdown for the yield districts
print("\n— разбор соседства —")
YIELD = [D.CAMPUS, D.HOLY_SITE, D.THEATER, D.COMMERCIAL_HUB, D.HARBOR, D.INDUSTRIAL_ZONE]
for p in res.placements:
    if p.district not in YIELD:
        continue
    nbrs = []
    for n in work.neighbors(p.coord):
        tag = None
        if n.district is not None:
            tag = NAME.get(n.district, n.district.value)
        elif n.terrain is Terrain.MOUNTAIN:
            tag = "гора"
        elif n.feature is Feature.GEOTHERMAL_FISSURE:
            tag = "гейзер"
        elif n.feature is Feature.NATURAL_WONDER:
            tag = "чудо-прир"
        elif n.wonder:
            tag = "чудо-света"
        elif n.resource_class == "strategic":
            tag = "стратег"
        elif n.improvement is Improvement.QUARRY:
            tag = "каменол."
        elif n.resource and n.terrain.is_water:
            tag = "море-рес"
        if tag:
            nbrs.append(tag)
    on_riv = " +река" if work.get(p.coord).on_river else ""
    print(f"{NAME[p.district]:<12} +{p.displayed}{on_riv}: " + ", ".join(nbrs))
