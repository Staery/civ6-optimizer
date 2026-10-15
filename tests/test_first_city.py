"""First-city (capital) planner: Settler reachability and turn-penalty trade-off."""

from backend.domain.hexgrid import Hex, within_radius
from backend.domain.models import GameMap, Terrain, Tile
from backend.optimizer.settle import _reachable_turns, suggest_first_city


def _land(center: Hex, radius: int, terrain: Terrain = Terrain.GRASSLAND) -> GameMap:
    gm = GameMap()
    for h in within_radius(center, radius):
        gm.set(Tile(coord=h, terrain=terrain))
    return gm


def test_reachable_turns_settle_in_place_and_distance():
    s = Hex(0, 0)
    gm = _land(s, 5)
    turns = _reachable_turns(gm, s)
    assert turns[s] == 1                 # settle in place = turn 1
    assert turns[Hex(1, 0)] == 2         # 1 move cost -> turn 2
    assert turns[Hex(3, 0)] == 3         # 3 move cost -> turn 3
    assert Hex(5, 0) not in turns        # beyond a Settler's 3-turn reach


def test_hills_and_woods_cost_extra_movement():
    s = Hex(0, 0)
    gm = _land(s, 4)
    gm.get(Hex(1, 0)).hills = True       # entering hills costs 2 -> tile itself turn 2,
    gm.get(Hex(2, 0)).hills = True       # cumulative cost 4 by (2,0) -> turn 3
    turns = _reachable_turns(gm, s)
    assert turns[Hex(2, 0)] == 3


def test_turn_penalty_controls_in_place_vs_move():
    s = Hex(0, 0)
    gm = _land(s, 5, Terrain.DESERT)     # poor start
    gm.get(Hex(2, 0)).terrain = Terrain.GRASSLAND
    gm.get(Hex(3, 0)).terrain = Terrain.LAKE     # makes (2,0) fresh-water + coastal
    cheap = suggest_first_city(gm, s, turn_penalty=0.5)
    expensive = suggest_first_city(gm, s, turn_penalty=50.0)
    assert expensive[0].coord == s       # huge per-turn cost -> settle in place
    assert cheap[0].coord != s           # cheap delay -> move to the better site
    assert cheap[0].turn >= 2
