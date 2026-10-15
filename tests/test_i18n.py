"""English localisation: catalogue coverage and Cyrillic-free API responses."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import app as A
from backend.i18n import CATALOG, localize, set_lang, tr, translate

ROOT = Path(__file__).resolve().parents[1]
CYR = re.compile("[А-Яа-яЁё]")


def _russian_literals() -> dict[str, str]:
    """Every Cyrillic string constant in backend/ (docstrings excluded) -> where it is."""
    found: dict[str, str] = {}
    for path in sorted((ROOT / "backend").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)
        }
        fstring_parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str) and CYR.search(n.value)
                    and id(n) not in docstrings):
                where = f"{path.relative_to(ROOT)}:{n.lineno}"
                assert id(n) not in fstring_parts, f"Russian f-string at {where}: use i18n.tr()"
                found.setdefault(n.value, where)
    return found


@pytest.fixture
def english():
    set_lang("en")
    yield
    set_lang("ru")


def test_every_russian_literal_has_a_translation():
    missing = {s: w for s, w in _russian_literals().items() if s not in CATALOG}
    assert not missing, "add to backend/locales/en.json:\n" + "\n".join(
        f"  {w}: {s!r}" for s, w in missing.items())


def test_catalogue_is_english_and_keeps_placeholders():
    for ru, en in CATALOG.items():
        assert not CYR.search(en), f"untranslated: {ru!r} -> {en!r}"
        assert sorted(re.findall(r"\{\w*\}", ru)) == sorted(re.findall(r"\{\w*\}", en)), ru


def test_russian_is_the_identity():
    set_lang("ru")
    assert translate("Кампус") == "Кампус"
    assert tr("Город {n}", n=3) == "Город 3"


def test_language_parsing():
    assert set_lang("EN") == "en"
    assert set_lang("en-US") == "en"
    assert set_lang("de") == "ru"
    assert set_lang(None) == "ru"


def test_templates_and_fragments(english):
    assert tr("Город {n}", n=3) == "City 3"
    # a sentence glued from catalogue fragments is translated piece by piece
    assert translate("наука/культура — крупнейший город") == "science/culture — largest city"
    assert localize({tr("Город {n}", n=2): ["Кампус"]}) == {"City 2": ["Campus"]}


def _rich_map() -> dict:
    """A varied map with several cities, rivals, city-states and a settler."""
    terrains = ["grassland", "plains", "desert", "tundra", "grassland", "plains", "coast"]
    features = ["none", "woods", "rainforest", "marsh", "floodplains", "none", "none"]
    tiles = []
    for q in range(-9, 10):
        for r in range(-9, 10):
            if abs(q + r) > 9:
                continue
            i = (q * 7 + r * 3) % 7
            t = {"q": q, "r": r, "terrain": terrains[i], "feature": features[(q - r) % 7],
                 "hills": (q + 2 * r) % 4 == 0, "on_river": (q - r) % 5 == 0,
                 "appeal": (q * r) % 5 - 1}
            if (q, r) in {(2, -1), (-3, 2), (5, 3)}:
                t.update(terrain="mountain", feature="none", hills=False)
            if t["terrain"] == "coast":
                t["feature"] = "none"
            if (q + r) % 6 == 0 and t["terrain"] != "coast":
                t["resource"] = "wheat"
            tiles.append(t)
    for t in tiles:
        if (t["q"], t["r"]) in {(0, 0), (5, -3), (-4, 4)}:
            t.update(district="city_center", terrain="plains", feature="none", hills=True)
    cities = [
        {"name": "Capital", "q": 0, "r": 0, "population": 9},
        {"name": "Second", "q": 5, "r": -3, "population": 3},
        {"name": "Third", "q": -4, "r": 4, "population": 1},
    ]
    requested = ["campus", "holy_site", "theater_square", "commercial_hub", "harbor",
                 "industrial_zone", "encampment", "neighborhood", "preserve"]
    for c in cities:
        c.update(work_radius=3, requested=requested)
    rivals = [
        {"q": 8, "r": 0, "name": "Rival A", "population": 12, "kind": "major", "civ": "japan"},
        {"q": -8, "r": 1, "name": "Rival B", "population": 8, "kind": "major", "civ": "korea"},
    ] + [
        {"q": -2 + k, "r": -7, "name": f"CS {k}", "population": 3, "kind": "city_state",
         "cs_type": t}
        for k, t in enumerate(["scientific", "cultural", "trade", "religious"])
    ] + [{"q": 3, "r": 6, "name": "Unknown CS", "kind": "city_state"}]
    return {"ruleset": "gathering_storm_nfp", "tiles": tiles, "cities": cities,
            "rival_cities": rivals, "settlers": [{"q": 1, "r": 2}]}


def _assert_no_cyrillic(label: str, payload) -> None:
    text = json.dumps(localize(payload), ensure_ascii=False)
    hits = sorted({m.group(0) for m in re.finditer(r"[^\"]*[А-Яа-яЁё][^\"]*", text)})
    assert not hits, f"{label}: Russian left in the English response:\n" + "\n".join(hits[:20])


LOADOUTS = [
    {},
    {"civ": "japan", "victory": "science", "pantheon": "dance_of_the_aurora",
     "beliefs": ["work_ethic", "tithe"], "governor": "pingala"},
    {"civ": "america", "leader": "abraham_lincoln", "victory": "domination"},
    {"civ": "korea", "leader": "sejong", "victory": "science", "secret_society": "hermetic_order"},
    {"civ": "byzantium", "leader": "theodora", "victory": "religious"},
]


@pytest.mark.parametrize("loadout", LOADOUTS, ids=lambda lo: lo.get("civ", "generic"))
def test_english_responses_have_no_cyrillic(english, loadout):
    m = _rich_map()
    m["loadout"] = loadout
    _assert_no_cyrillic("plan-empire", A.plan_empire_endpoint(dict(m, max_new=3)))
    _assert_no_cyrillic("optimize", A.optimize(dict(m)))


def test_english_advisory_endpoints(english):
    m = _rich_map()
    _assert_no_cyrillic("meta", A.meta())
    _assert_no_cyrillic("suggest-cities", A.suggest_cities(dict(m, count=6)))
    _assert_no_cyrillic("first-city", A.first_city(dict(m, settler={"q": 1, "r": 2})))
    _assert_no_cyrillic("amenities", A.amenities(dict(m)))
    _assert_no_cyrillic("housing", A.housing(dict(m)))
    _assert_no_cyrillic("suggest-wonders", A.suggest_wonders(dict(m, top=25)))


def test_english_error_messages(english):
    with pytest.raises(HTTPException) as err:
        A.import_latest(path=str(ROOT / "no-such-dir" / "Lua.log"))
    assert "not found" in err.value.detail and not CYR.search(err.value.detail)
