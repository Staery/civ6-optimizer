"""Parser for the in-game export (Lua.log): names, owning city, robustness."""

from backend.io.lualog_parser import parse_lua_log


def _line(x, y, terr="TERRAIN_GRASS", feat="NONE", dist="NONE", owner=0, oc=0):
    return (f"CIV6OPT|TILE|{x}|{y}|{terr}|{feat}|0|RESOURCE_NONE|NONE|0|0|"
            f"{owner}|{dist}|NONE|{oc}")


def _log(*tile_lines, cities=()):
    head = ["CIV6OPT|META|player|0|civ|CIVILIZATION_AMERICA|width|20|height|20|wrapX|1",
            "CIV6OPT|BEGIN", *cities, *tile_lines, "CIV6OPT|END"]
    return "\n".join(head)


def test_feature_none_is_not_a_natural_wonder():
    # "FEATURE_NONE" starts with "FEATURE_" but must not be read as a wonder
    # (that would make the tile unbuildable).
    log = _log(_line(10, 10, dist="DISTRICT_CITY_CENTER"),
               _line(11, 10, feat="FEATURE_NONE"))
    res = parse_lua_log(log)
    t = next(t for t in res["tiles"] if (t["q"], t["r"]) != (0, 0))
    assert t["feature"] == "none"
    assert t["natural_wonder"] is None
    assert not res["warnings"]


def test_real_city_names_and_owning_city():
    log = _log(
        _line(10, 10, dist="DISTRICT_CITY_CENTER", owner=0, oc=0),
        _line(11, 10, owner=0, oc=0),       # Washington's land
        _line(13, 12, dist="DISTRICT_CITY_CENTER", owner=0, oc=1),
        _line(14, 12, owner=0, oc=1),       # New York's land
        _line(18, 18, owner=2, oc=0),       # rival land
        cities=["CIV6OPT|CITY|10|10|0|0|1|Washington",
                "CIV6OPT|CITY|13|12|0|1|0|New York"],
    )
    res = parse_lua_log(log)
    names = [c["name"] for c in res["cities"]]
    assert names == ["Washington", "New York"]        # capital first
    assert res["city_name"] == "Washington"
    owners = {t["owner_city"] for t in res["tiles"]}
    assert "Washington" in owners and "New York" in owners
    assert any(o and o.startswith("rival") for o in owners)  # rival excluded


def test_old_log_without_city_lines_falls_back():
    log = _log(_line(10, 10, dist="DISTRICT_CITY_CENTER"), _line(11, 10))
    res = parse_lua_log(log)
    assert [c["name"] for c in res["cities"]] == ["Capital"]
