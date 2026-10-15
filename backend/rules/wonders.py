"""World Wonder catalogue with placement requirements (Gathering Storm + NFP).

Each wonder has a ``predicate(map, hex) -> bool`` that checks the *terrain/adjacency*
requirement (the recommender separately checks the tile is empty and inside your
territory). ``value`` is a curated relative strength (roughly 1–10) used to rank
suggestions.

Requirements are encoded from community knowledge; the iconic ones are reliable,
but a few are approximate — marked ``VALIDATE`` — and easy to correct here since
this is pure data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..domain.hexgrid import Hex
from ..domain.models import DistrictType, Feature, GameMap, Improvement, Terrain, Tile

Pred = Callable[[GameMap, Hex], bool]


@dataclass(frozen=True)
class Wonder:
    key: str
    name: str          # Russian display name
    era: str
    value: float
    requires: str      # human-readable placement requirement (RU)
    predicate: Pred
    note: str = ""


# --- tile/adjacency helpers -----------------------------------------------------

def _t(map: GameMap, h: Hex) -> Tile | None:
    return map.get(h)


def _flat_land(t: Tile) -> bool:
    return t.terrain.is_land and not t.hills


def _hills_land(t: Tile) -> bool:
    return t.terrain.is_land and t.hills


def _adj_district(map: GameMap, h: Hex, *types: DistrictType) -> bool:
    s = set(types)
    return any(n.district in s for n in map.neighbors(h))


def _adj_resource(map: GameMap, h: Hex, *names: str) -> bool:
    s = set(names)
    return any((n.resource or "").lower() in s for n in map.neighbors(h))


def _adj_mountain(map: GameMap, h: Hex) -> bool:
    return any(n.terrain is Terrain.MOUNTAIN for n in map.neighbors(h))


def _adj_improvement(map: GameMap, h: Hex, *imps: Improvement) -> bool:
    s = set(imps)
    return any(n.improvement in s for n in map.neighbors(h))


# --- catalogue ------------------------------------------------------------------

WONDERS: list[Wonder] = [
    Wonder("pyramids", "Пирамиды", "ancient", 9.0,
           "пустыня или пустынные холмы",
           lambda m, h: _t(m, h).terrain is Terrain.DESERT,
           "Бесплатный строитель + заряды; +2 культуры."),
    Wonder("stonehenge", "Стоунхендж", "ancient", 6.0,
           "ровная земля рядом с ресурсом «Камень»",
           lambda m, h: _flat_land(_t(m, h)) and _adj_resource(m, h, "stone"),
           "Великий пророк; основание религии без Святого места."),
    Wonder("hanging_gardens", "Висячие сады", "ancient", 7.0,
           "земля у реки",
           lambda m, h: _t(m, h).terrain.is_land and _t(m, h).on_river,
           "+15% к росту во всех городах."),
    Wonder("oracle", "Оракул", "classical", 7.0,
           "холмы",
           lambda m, h: _hills_land(_t(m, h)),
           "Дешёвые великие люди; +1 культуры/веры с районов города."),
    Wonder("petra", "Петра", "classical", 8.0,
           "пустыня или пустынные холмы",
           lambda m, h: _t(m, h).terrain is Terrain.DESERT,
           "+2 еды/+2 золота/+1 произв. с пустынных клеток."),
    Wonder("colossus", "Колосс", "classical", 6.0,
           "прибрежная клетка рядом с Гаванью",
           lambda m, h: _t(m, h).terrain is Terrain.COAST and _adj_district(m, h, DistrictType.HARBOR),
           "Требует Гавань. +золото, торг. путь, очки великого торговца."),
    Wonder("great_lighthouse", "Великий маяк", "classical", 6.0,
           "прибрежная клетка рядом с Гаванью",
           lambda m, h: _t(m, h).terrain is Terrain.COAST and _adj_district(m, h, DistrictType.HARBOR),
           "Требует Гавань с Маяком. +движение флоту, очки адмирала."),
    Wonder("mausoleum", "Мавзолей в Галикарнасе", "classical", 5.0,
           "прибрежная клетка рядом с Гаванью",
           lambda m, h: _t(m, h).terrain is Terrain.COAST and _adj_district(m, h, DistrictType.HARBOR),
           "Бонусы великим адмиралам/инженерам."),
    Wonder("temple_artemis", "Храм Артемиды", "classical", 6.0,
           "ровная земля рядом с пастбищем/плантацией",
           lambda m, h: _flat_land(_t(m, h)) and _adj_improvement(m, h, Improvement.PASTURE, Improvement.PLANTATION),
           "+жильё и амулеты; VALIDATE: рядом с лагерем/пастбищем/плантацией."),
    Wonder("machu_picchu", "Мачу-Пикчу", "medieval", 7.0,
           "клетка ГОРЫ",
           lambda m, h: _t(m, h).terrain is Terrain.MOUNTAIN,
           "Единственное чудо на горе; +золото/произв."),
    Wonder("chichen_itza", "Чичен-Ица", "medieval", 6.0,
           "клетка тропического леса",
           lambda m, h: _t(m, h).feature is Feature.RAINFOREST,
           "+произв./культуры с тропиков."),
    Wonder("alhambra", "Альгамбра", "medieval", 6.0,
           "холмы рядом с Лагерем",
           lambda m, h: _hills_land(_t(m, h)) and _adj_district(m, h, DistrictType.ENCAMPMENT),
           "Требует Лагерь. Амулет, очки генерала, +оборона."),
    Wonder("colosseum", "Колизей", "medieval", 6.0,
           "ровная земля рядом с Парком развлечений",
           lambda m, h: _flat_land(_t(m, h)) and _adj_district(m, h, DistrictType.ENTERTAINMENT),
           "Культура и амулеты соседним городам."),
    Wonder("great_zimbabwe", "Великий Зимбабве", "medieval", 8.0,
           "ровная земля рядом с Ком. хабом и ресурсом «Скот»",
           lambda m, h: _flat_land(_t(m, h)) and _adj_district(m, h, DistrictType.COMMERCIAL_HUB) and _adj_resource(m, h, "cattle"),
           "Мощный торговый бонус (+торг. путь, золото)."),
    Wonder("mont_st_michel", "Мон-Сен-Мишель", "medieval", 6.0,
           "пойма или болото",
           lambda m, h: _t(m, h).feature in (Feature.FLOODPLAINS, Feature.MARSH),
           "+вера, апостолы с мученичеством."),
    Wonder("huey_teocalli", "Уэй-Теокалли", "medieval", 6.0,
           "клетка ОЗЕРА (в границах)",
           lambda m, h: _t(m, h).terrain is Terrain.LAKE,
           "+амулеты/произв. за соседние озёрные клетки."),
    Wonder("forbidden_city", "Запретный город", "renaissance", 9.0,
           "ровная земля рядом с Центром города",
           lambda m, h: _flat_land(_t(m, h)) and _adj_district(m, h, DistrictType.CITY_CENTER),
           "+1 ячейка политики (вилдкард). Очень сильное."),
    Wonder("potala_palace", "Дворец Потала", "renaissance", 6.0,
           "холмы рядом с горой",
           lambda m, h: _hills_land(_t(m, h)) and _adj_mountain(m, h),
           "+1 ячейка дипломатии, +наука/культура/вера."),
    Wonder("taj_mahal", "Тадж-Махал", "renaissance", 6.0,
           "земля у реки",
           lambda m, h: _t(m, h).terrain.is_land and _t(m, h).on_river,
           "Бонус очков эпохи при значимых событиях."),
    Wonder("venetian_arsenal", "Венецианский арсенал", "renaissance", 7.0,
           "прибрежная клетка рядом с Промзоной",
           lambda m, h: _t(m, h).terrain is Terrain.COAST and _adj_district(m, h, DistrictType.INDUSTRIAL_ZONE),
           "Требует Промзону. Второй флотский юнит при постройке."),
    Wonder("big_ben", "Биг-Бен", "industrial", 7.0,
           "клетка у реки рядом с Ком. хабом",
           lambda m, h: _t(m, h).terrain.is_land and _t(m, h).on_river and _adj_district(m, h, DistrictType.COMMERCIAL_HUB),
           "Требует Ком. хаб с Банком. +золото, экон. бонусы."),
    Wonder("ruhr_valley", "Рурская долина", "industrial", 9.0,
           "клетка у реки рядом с Промзоной",
           lambda m, h: _t(m, h).terrain.is_land and _t(m, h).on_river and _adj_district(m, h, DistrictType.INDUSTRIAL_ZONE),
           "Требует Промзону с Фабрикой. Огромный бонус к производству."),
    Wonder("oxford_university", "Оксфордский университет", "industrial", 7.0,
           "ровная земля рядом с Кампусом",
           lambda m, h: _flat_land(_t(m, h)) and _adj_district(m, h, DistrictType.CAMPUS),
           "Требует Кампус с Университетом. +наука, бесплатные технологии."),
    Wonder("eiffel_tower", "Эйфелева башня", "industrial", 7.0,
           "ровная земля",
           lambda m, h: _flat_land(_t(m, h)),
           "+2 к привлекательности всех клеток империи."),
    Wonder("statue_liberty", "Статуя Свободы", "modern", 5.0,
           "прибрежная клетка рядом с Центром города",
           lambda m, h: _t(m, h).terrain is Terrain.COAST and _adj_district(m, h, DistrictType.CITY_CENTER),
           "Лояльность и быстрое заселение."),
]


WONDERS_BY_KEY: dict[str, Wonder] = {w.key: w for w in WONDERS}

# Era -> AI-race risk label (earlier wonders are contested harder by the AI).
ERA_RISK: dict[str, str] = {
    "ancient": "высокий", "classical": "высокий", "medieval": "средний",
    "renaissance": "средний", "industrial": "низкий", "modern": "низкий",
    "atomic": "низкий", "information": "низкий",
}
