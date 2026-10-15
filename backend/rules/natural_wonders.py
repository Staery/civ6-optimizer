"""Natural Wonder catalogue (Gathering Storm + NFP).

Each natural wonder has an **area** (``tiles`` — how many map tiles it occupies),
a settle value, the Appeal it grants to *adjacent* tiles, the Holy Site adjacency
each of its tiles grants (default +2 major), and optional extra adjacency to other
districts. Multi-tile wonders are painted one tile at a time in the editor; being
adjacent to several tiles of the same wonder stacks the Holy Site bonus.

``tiles`` counts are reliable; precise per-yield bonuses live in ``note`` (and are
approximated by ``settle_value``/``appeal``) — exact yields should be verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NaturalWonder:
    key: str
    name: str               # Russian display name
    tiles: int              # area: number of map tiles it occupies
    terrain: str            # editor hint: land / coast / mountain / wetland / desert
    appeal: int             # Appeal granted to ADJACENT tiles
    settle_value: float     # how valuable it is to settle near (per adjacent tile)
    holy_site_adj: float = 2.0           # Holy Site major adjacency per adjacent tile
    extra_adj: dict[str, float] = field(default_factory=dict)  # district value -> amount
    note: str = ""


NATURAL_WONDERS: list[NaturalWonder] = [
    NaturalWonder("pamukkale", "Памуккале", 1, "land", 2, 6.0,
                  note="Сильное: золото и вера; +вера соседним клеткам."),
    NaturalWonder("uluru", "Улуру", 1, "land", 2, 5.0,
                  note="+вера; высокая привлекательность; отличное Святое место рядом."),
    NaturalWonder("everest", "Эверест", 1, "mountain", 2, 4.0,
                  note="+вера соседям; +движение паломникам; нельзя строить на самой клетке."),
    NaturalWonder("kilimanjaro", "Килиманджаро", 1, "mountain", 1, 4.0,
                  note="+еда соседним клеткам."),
    NaturalWonder("matterhorn", "Маттерхорн", 1, "mountain", 2, 4.0,
                  note="+культура/боевой бонус; высокая привлекательность."),
    NaturalWonder("vesuvius", "Везувий", 1, "mountain", 0, 4.0,
                  note="Вулкан: +произв./вера соседям, но риск извержения."),
    NaturalWonder("crater_lake", "Кратерное озеро", 1, "land", 2, 5.0,
                  note="+вера/наука; пресная вода; отличное Святое место/Кампус рядом."),
    NaturalWonder("zhangye_danxia", "Чжанъе Данься", 1, "land", 2, 4.0,
                  note="NFP: +культура соседям; высокая привлекательность."),
    NaturalWonder("ik_kil", "Ик-Киль", 1, "land", 1, 4.0,
                  note="NFP: +вера/амулеты."),
    NaturalWonder("fountain_of_youth", "Фонтан молодости", 1, "land", 1, 4.0,
                  note="Бонус амулетов/эпохи; редкое."),
    NaturalWonder("cliffs_of_dover", "Скалы Дувра", 2, "coast", 2, 6.0,
                  note="2 клетки: +культура/золото; высокая привлекательность."),
    NaturalWonder("great_barrier_reef", "Большой Барьерный риф", 2, "coast", 2, 6.0,
                  note="2 клетки: +еда/наука; высокая привлекательность; рыба."),
    NaturalWonder("galapagos", "Галапагосы", 2, "coast", 1, 5.0,
                  note="2 клетки: +наука; рядом нельзя строить районы/чудеса."),
    NaturalWonder("yosemite", "Йосемити", 2, "land", 2, 5.0,
                  note="2 клетки: +золото/наука; привлекательность."),
    NaturalWonder("torres_del_paine", "Торрес-дель-Пайне", 2, "land", 1, 5.0,
                  note="2 клетки: +еда/произв. соседним клеткам."),
    NaturalWonder("dead_sea", "Мёртвое море", 2, "coast", 1, 5.0,
                  note="2 клетки: +вера; лечит юниты."),
    NaturalWonder("giants_causeway", "Дорога гигантов", 2, "coast", 1, 5.0,
                  note="NFP: 2 клетки прибрежные; +культура; бонус движению флота."),
    NaturalWonder("ha_long_bay", "Бухта Халонг", 2, "coast", 2, 5.0,
                  note="NFP: 2 клетки; +культура/произв.; привлекательность."),
    NaturalWonder("eye_of_the_sahara", "Око Сахары", 2, "desert", 0, 4.0,
                  note="2 клетки в пустыне (Ришат); наука/произв."),
    NaturalWonder("roraima", "Рорайма", 2, "land", 1, 4.0,
                  note="2 клетки; наука/произв./еда соседям."),
    NaturalWonder("pantanal", "Пантанал", 4, "wetland", 1, 5.0,
                  note="САМОЕ БОЛЬШОЕ: 4 клетки; +еда/культура; влажная низина."),
    NaturalWonder("bermuda_triangle", "Бермудский треугольник", 3, "coast", 0, 4.0,
                  note="3 океанские клетки; наука; телепортация флота."),
]

NW_BY_KEY: dict[str, NaturalWonder] = {w.key: w for w in NATURAL_WONDERS}
