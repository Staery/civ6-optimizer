"""Adjacency rule values for Gathering Storm + New Frontier.

These pin the *unambiguous*, well-established numbers. Special-pair stacking
(e.g. Commercial Hub adjacent to a Harbor) is documented separately as the
current model and flagged ``VALIDATE`` in the rules module.
"""

from backend.domain.hexgrid import Hex
from backend.domain.models import (
    DistrictType,
    Feature,
    GameMap,
    Improvement,
    Terrain,
    Tile,
    YieldType,
)
from backend.rules.adjacency import adjacency_yield, displayed_adjacency, raw_adjacency
from backend.rules.modifiers import Loadout

CENTER = Hex(0, 0)


def build(center_attrs: dict | None = None, neighbors: dict[int, dict] | None = None) -> GameMap:
    """Map with a center tile (attrs) and neighbours keyed by direction 0..5."""
    gm = GameMap()
    c = Tile(coord=CENTER)
    for k, v in (center_attrs or {}).items():
        setattr(c, k, v)
    gm.set(c)
    for direction, attrs in (neighbors or {}).items():
        t = Tile(coord=CENTER.neighbor(direction))
        for k, v in attrs.items():
            setattr(t, k, v)
        gm.set(t)
    return gm


def test_campus_two_mountains_and_a_district():
    gm = build(neighbors={
        0: {"terrain": Terrain.MOUNTAIN},
        1: {"terrain": Terrain.MOUNTAIN},
        2: {"district": DistrictType.THEATER},  # standard district -> +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.CAMPUS) == 2.5


def test_campus_city_center_counts_as_district():
    # In Civ 6 the City Center IS a district and grants the generic +0.5 to neighbours.
    gm = build(neighbors={0: {"district": DistrictType.CITY_CENTER}})
    assert raw_adjacency(gm, CENTER, DistrictType.CAMPUS) == 0.5


def test_campus_rainforest_and_reef_and_geothermal():
    gm = build(neighbors={
        0: {"feature": Feature.RAINFOREST},          # +0.5
        1: {"feature": Feature.REEF},                # +2
        2: {"feature": Feature.GEOTHERMAL_FISSURE},  # +2
    })
    assert raw_adjacency(gm, CENTER, DistrictType.CAMPUS) == 4.5


def test_holy_site_natural_wonder_mountain_woods():
    gm = build(neighbors={
        0: {"feature": Feature.NATURAL_WONDER},  # +2
        1: {"terrain": Terrain.MOUNTAIN},        # +1
        2: {"feature": Feature.WOODS},           # +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.HOLY_SITE) == 3.5


def test_theater_world_wonder():
    gm = build(neighbors={
        0: {"wonder": "Pyramids"},               # +2
        1: {"district": DistrictType.CAMPUS},    # +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.THEATER) == 2.5


def test_theater_entertainment_and_water_park_are_major():
    # August 2020 Update: Entertainment Complex / Water Park give a Theater Square a
    # MAJOR (+2) Culture adjacency — same as a Wonder, NOT the generic +0.5.
    gm = build(neighbors={0: {"district": DistrictType.ENTERTAINMENT}})
    assert raw_adjacency(gm, CENTER, DistrictType.THEATER) == 2.0
    gm = build(neighbors={0: {"district": DistrictType.WATER_PARK}})
    assert raw_adjacency(gm, CENTER, DistrictType.THEATER) == 2.0


def test_theater_butterfly_two_wonders_plus_entertainment():
    # "Butterfly" combo: a Theater wedged next to 2 Wonders (+2 each) and an
    # Entertainment Complex (+2 major) tops out at +6 Culture.
    gm = build(neighbors={
        0: {"wonder": "Pyramids"},                    # +2
        1: {"wonder": "Colosseum"},                   # +2
        2: {"district": DistrictType.ENTERTAINMENT},  # +2 (major)
    })
    assert raw_adjacency(gm, CENTER, DistrictType.THEATER) == 6.0


def test_commercial_hub_on_river_plus_one_district():
    gm = build(center_attrs={"on_river": True}, neighbors={
        0: {"district": DistrictType.THEATER},   # +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.COMMERCIAL_HUB) == 2.5


def test_harbor_city_center_and_sea_resources():
    gm = build(center_attrs={"terrain": Terrain.COAST}, neighbors={
        0: {"district": DistrictType.CITY_CENTER},                 # +2 specific, +0.5 generic
        1: {"terrain": Terrain.COAST, "resource": "crabs"},        # +1
        2: {"terrain": Terrain.OCEAN, "resource": "whales"},       # +1
    })
    assert raw_adjacency(gm, CENTER, DistrictType.HARBOR) == 4.5


def test_industrial_zone_mines_are_minor_in_gs():
    # Gathering Storm re-tiering: a Mine gives the Industrial Zone only +0.5 (minor),
    # not the +1 it gave in the base game.
    gm = build(neighbors={
        0: {"hills": True, "improvement": Improvement.MINE},   # +0.5
        1: {"hills": True, "improvement": Improvement.MINE},   # +0.5
        2: {"district": DistrictType.THEATER},                 # +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.INDUSTRIAL_ZONE) == 1.5


def test_industrial_zone_quarry_strategic_standard_lumbermill_minor():
    # Quarry and Strategic Resource are STANDARD (+1); Lumber Mill is MINOR (+0.5).
    gm = build(neighbors={
        0: {"improvement": Improvement.QUARRY},                                  # +1
        1: {"resource_class": "strategic"},                                      # +1
        2: {"feature": Feature.WOODS, "improvement": Improvement.LUMBER_MILL},   # +0.5
    })
    assert raw_adjacency(gm, CENTER, DistrictType.INDUSTRIAL_ZONE) == 2.5


def test_industrial_zone_mined_strategic_counts_once():
    # A Mine worked on a strategic resource (e.g. Iron) scores +1 (strategic), NOT
    # +1.5 — the mine's +0.5 is suppressed to avoid double-counting.
    gm = build(neighbors={
        0: {"hills": True, "improvement": Improvement.MINE, "resource_class": "strategic"},
    })
    assert raw_adjacency(gm, CENTER, DistrictType.INDUSTRIAL_ZONE) == 1.0


def test_modifier_natural_philosophy_doubles_campus():
    gm = build(neighbors={
        0: {"terrain": Terrain.MOUNTAIN},
        1: {"terrain": Terrain.MOUNTAIN},
        2: {"district": DistrictType.THEATER},
    })
    loadout = Loadout(active_modifiers=["natural_philosophy"])
    y = adjacency_yield(gm, CENTER, DistrictType.CAMPUS, loadout)
    assert y[YieldType.SCIENCE] == 5.0  # 2.5 * 2


def test_netherlands_river_bonus_changes_campus_value():
    gm = build(center_attrs={"on_river": True}, neighbors={0: {"terrain": Terrain.MOUNTAIN}})
    base = raw_adjacency(gm, CENTER, DistrictType.CAMPUS)  # mountain only
    assert base == 1.0
    y = adjacency_yield(gm, CENTER, DistrictType.CAMPUS, Loadout(civ="netherlands"))
    assert y[YieldType.SCIENCE] == 3.0  # +1 mountain, +2 river (civ bonus)


def test_leader_modifiers_merge_with_civ():
    gm = build(center_attrs={"on_river": True})
    # leader 'wilhelmina' implies civ netherlands isn't auto-set, but civ+leader both apply
    y = adjacency_yield(gm, CENTER, DistrictType.CAMPUS,
                        Loadout(civ="netherlands", leader="wilhelmina"))
    assert y[YieldType.SCIENCE] == 2.0  # just the river bonus here


def test_gaul_mine_adjacency_all_districts():
    gm = build(neighbors={
        0: {"hills": True, "improvement": Improvement.MINE},
        1: {"terrain": Terrain.MOUNTAIN},
    })
    y = adjacency_yield(gm, CENTER, DistrictType.CAMPUS, Loadout(civ="gaul"))
    assert y[YieldType.SCIENCE] == 1.5  # +1 mountain, +0.5 from adjacent mine


def test_gaul_forbids_district_adjacent_to_city_center():
    from backend.domain.models import City
    from backend.rules.adjacency import can_place

    gm = GameMap()
    gm.set(Tile(coord=Hex(0, 0), district=DistrictType.CITY_CENTER))
    gm.set(Tile(coord=Hex(1, 0), terrain=Terrain.GRASSLAND))
    city = City("C", Hex(0, 0), work_radius=3, requested=[])
    assert can_place(gm, Hex(1, 0), DistrictType.CAMPUS, city) is True
    assert can_place(gm, Hex(1, 0), DistrictType.CAMPUS, city, Loadout(civ="gaul")) is False


def test_australia_appeal_adjacency():
    breathtaking = build(center_attrs={"appeal": 4})
    y = adjacency_yield(breathtaking, CENTER, DistrictType.CAMPUS, Loadout(civ="australia"))
    assert y[YieldType.SCIENCE] == 2.0  # breathtaking -> +2
    charming = build(center_attrs={"appeal": 2})
    y2 = adjacency_yield(charming, CENTER, DistrictType.CAMPUS, Loadout(civ="australia"))
    assert y2[YieldType.SCIENCE] == 1.0  # charming -> +1


def test_displayed_floors_the_total():
    assert displayed_adjacency(3.5) == 3
    assert displayed_adjacency(2.0) == 2
    assert displayed_adjacency(0.5) == 0
