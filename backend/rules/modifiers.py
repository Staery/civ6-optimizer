"""Modifiers from civilization, religion/beliefs, policies and government.

A :class:`Modifier` adjusts a district's *primary-yield adjacency* by:
  * ``adjacency_multiplier`` — scales the whole adjacency (e.g. policy cards that
    give "+100% Campus adjacency"),
  * ``adjacency_flat`` — a flat add,
  * ``district_adj_delta`` — extra yield per *adjacent district* (e.g. Japan's
    Meiji Restoration: districts gain +0.5 more from neighbouring districts).

:class:`Loadout` bundles the player's chosen civ/beliefs/policies plus the yield
weights that form the optimizer's objective.

Extensible by design: add entries to ``MODIFIERS`` / ``CIVS``. Policy cards
added by mods (e.g. *Extended Policy Cards*) would slot in here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.models import DistrictType, YieldType


@dataclass(frozen=True)
class Modifier:
    name: str
    label: str
    applies_to: DistrictType | None  # None -> applies to every district
    adjacency_multiplier: float = 1.0
    adjacency_flat: float = 0.0
    district_adj_delta: float = 0.0   # extra yield per adjacent district
    river_bonus: float = 0.0          # extra yield if the district tile is on a river
    mine_adj: float = 0.0             # extra yield per adjacent Mine/Quarry (Gaul)
    self_appeal_adj: float = 0.0      # bonus if the tile is Charming/Breathtaking (Australia)
    forbid_adj_city_center: bool = False  # district may NOT be adjacent to City Center (Gaul)
    # Extra adjacency per neighbour matching a token: "terrain:<t>" or "feature:<f>"
    # (e.g. pantheons: Dance of the Aurora -> Holy Site +1 per adjacent tundra).
    neighbor_adj: tuple[str, float] = ("", 0.0)
    note: str = ""


# Registry of selectable modifiers (policies / beliefs / civ abilities). Extend freely.
MODIFIERS: dict[str, Modifier] = {
    m.name: m
    for m in (
        # --- policy cards (generic "+100% adjacency") ---
        Modifier("natural_philosophy", "Natural Philosophy (политика)", DistrictType.CAMPUS,
                 adjacency_multiplier=2.0, note="+100% к соседству Кампуса"),
        Modifier("grand_opera", "Grand Opera (политика)", DistrictType.THEATER,
                 adjacency_multiplier=2.0, note="+100% к соседству Театра"),
        Modifier("free_market", "Free Market (политика)", DistrictType.COMMERCIAL_HUB,
                 adjacency_multiplier=2.0, note="+100% к соседству Ком. хаба"),
        Modifier("five_year_plan", "Five-Year Plan (политика)", DistrictType.INDUSTRIAL_ZONE,
                 adjacency_multiplier=2.0, note="+100% к соседству Промзоны (и Кампуса)"),
        Modifier("god_of_the_sea", "God of the Sea (пантеон)", DistrictType.HARBOR,
                 adjacency_flat=1.0, note="прибл.: +1 к Гавани (на самом деле +1 произв. с морских клеток)"),
        # --- civ abilities (exposed via CIVS) ---
        Modifier("japan_meiji", "Япония · Реставрация Мэйдзи", None,
                 district_adj_delta=0.5,
                 note="районы получают +0.5 доп. за каждый соседний район (итого +1)"),
        # Seowon/Hansa/Suguba/Acropolis/Observatory now modelled exactly as unique
        # districts (rules.districts.UNIQUE_DISTRICTS) — no approximate modifier needed.
        # Netherlands: major adjacency from rivers for several districts (changes placement).
        Modifier("nl_river_campus", "Нидерланды · реки→Кампус", DistrictType.CAMPUS,
                 river_bonus=2.0, note="≈ +2 науки Кампусу у реки (уточни список районов)"),
        Modifier("nl_river_theater", "Нидерланды · реки→Театр", DistrictType.THEATER,
                 river_bonus=2.0, note="≈ +2 культуры Театру у реки"),
        Modifier("nl_river_iz", "Нидерланды · реки→Промзона", DistrictType.INDUSTRIAL_ZONE,
                 river_bonus=2.0, note="≈ +2 произв. Промзоне у реки"),
        # Gaul: Mines give minor adjacency to every district; districts can't touch City Center.
        Modifier("gaul_hallstatt", "Галлия · Гальштат", None,
                 mine_adj=0.5, forbid_adj_city_center=True,
                 note="Шахты дают +0.5 любому соседнему району; район НЕЛЬЗЯ ставить вплотную к Центру города."),
        # Australia: districts on high-appeal tiles gain adjacency.
        Modifier("australia_outback", "Австралия · Land Down Under", None,
                 self_appeal_adj=1.0,
                 note="Район на «очаровательной» клетке +1, на «потрясающей» +2 к соседству (по привлекательности)."),
        # --- pantheons that change Holy Site adjacency (selected via PANTHEONS) ---
        Modifier("dance_of_the_aurora", "Танец Авроры (пантеон)", DistrictType.HOLY_SITE,
                 neighbor_adj=("terrain:tundra", 1.0),
                 note="Святое место +1 веры за каждую соседнюю клетку тундры."),
        Modifier("desert_folklore", "Пустынный фольклор (пантеон)", DistrictType.HOLY_SITE,
                 neighbor_adj=("terrain:desert", 1.0),
                 note="Святое место +1 веры за каждую соседнюю клетку пустыни."),
        Modifier("sacred_path", "Священный путь (пантеон)", DistrictType.HOLY_SITE,
                 neighbor_adj=("feature:rainforest", 1.0),
                 note="Святое место +1 веры за каждую соседнюю клетку тропиков."),
    )
}


# All Gathering Storm + NFP pantheons, selectable in the UI. ``modifier`` is the
# adjacency Modifier a pantheon activates (only some change *placement*); ``modeled``
# = the optimizer actually accounts for it (adjacency, or housing/amenities for River
# Goddess). The rest are advisory — they tweak tile yields/growth, not where a district
# goes — and feed the pantheon recommender (optimizer.advisor).
@dataclass(frozen=True)
class Pantheon:
    key: str
    label: str
    modifier: str
    note: str = ""
    modeled: bool = False


PANTHEONS: dict[str, Pantheon] = {
    p.key: p
    for p in (
        Pantheon("none", "— без пантеона —", ""),
        # --- change district placement / city supply (modeled) ---
        Pantheon("dance_of_the_aurora", "Танец Авроры", "dance_of_the_aurora",
                 "Святое место +1 веры за каждую соседнюю тундру — селись у тундры/гор.",
                 modeled=True),
        Pantheon("desert_folklore", "Пустынный фольклор", "desert_folklore",
                 "Святое место +1 веры за каждую соседнюю пустыню — пустынные города (Мали!).",
                 modeled=True),
        Pantheon("sacred_path", "Священный путь", "sacred_path",
                 "Святое место +1 веры за каждые соседние тропики — НЕ вырубай тропики у него.",
                 modeled=True),
        Pantheon("river_goddess", "Речная богиня", "",
                 "+2 жилья и +2 довольства, если в городе есть Святое место у реки — "
                 "ставь Святое место на речную клетку.",
                 modeled=True),
        Pantheon("god_of_the_sea", "Бог моря", "god_of_the_sea",
                 "+1 произв. с морских ресурсов (Рыбацкие лодки) — учтено как +1 Гавани.",
                 modeled=True),
        # --- advisory: tweak tile yields / growth, not placement ---
        Pantheon("earth_goddess", "Богиня Земли", "",
                 "+1 веры с возделанных клеток с привлекательностью (Очаровательная+) — "
                 "цени привлекательность и Заповедники."),
        Pantheon("lady_of_the_reeds_and_marshes", "Владычица камышей и болот", "",
                 "+1 произв. с болот, оазисов и пойм."),
        Pantheon("god_of_the_open_sky", "Бог открытого неба", "",
                 "+1 культуры с Пастбищ — селись у скота/коней."),
        Pantheon("goddess_of_the_hunt", "Богиня охоты", "",
                 "+1 еды и +1 произв. с Лагерей (Camp)."),
        Pantheon("god_of_craftsmen", "Бог ремесленников", "",
                 "+1 произв. и +1 веры с улучшенных стратегических ресурсов."),
        Pantheon("religious_idols", "Религиозные идолы", "",
                 "+2 веры с Шахт на ресурсах роскоши/бонусных."),
        Pantheon("stone_circles", "Каменные круги", "",
                 "+2 веры с Карьеров (Quarry)."),
        Pantheon("oral_tradition", "Устная традиция", "",
                 "+1 культуры с плантаций (бананы, специи, вино, шёлк и т.п.)."),
        Pantheon("divine_spark", "Божественная искра", "",
                 "+1 очко великого человека от Кампуса/Святого места/Театра."),
        Pantheon("monument_to_the_gods", "Памятник богам", "",
                 "+15% произв. к чудесам Древней/Классической эпохи."),
        Pantheon("god_of_the_forge", "Бог кузницы", "",
                 "+25% произв. к древним/классическим военным юнитам."),
        Pantheon("god_of_war", "Бог войны", "",
                 "+веры за победы у Святых мест; бонус к первому удару."),
        Pantheon("goddess_of_festivals", "Богиня празднеств", "",
                 "культура с возделанных плантаций/посевов."),
        Pantheon("goddess_of_the_harvest", "Богиня жатвы", "",
                 "разовая вера при сборе урожая/вырубке особенностей."),
        Pantheon("initiation_rites", "Обряды посвящения", "",
                 "+50 веры за каждый зачищенный лагерь варваров."),
        Pantheon("fertility_rites", "Обряды плодородия", "",
                 "+10% к росту города; бесплатный Строитель."),
        Pantheon("religious_settlements", "Религиозные поселения", "",
                 "ускоренный рост границ; бесплатный Поселенец — для экспансии."),
        Pantheon("city_patron_goddess", "Богиня-покровительница", "",
                 "+25% произв. к районам в городах, где района ещё нет."),
    )
}


# --- governors ------------------------------------------------------------------
# Governors mostly change WHICH districts you prioritise and a couple of scalar
# bonuses (Liang's appeal/amenity), not WHERE a district goes — so they are modelled
# as objective-weight multipliers plus Liang's appeal/amenity effect.
@dataclass(frozen=True)
class Governor:
    key: str
    label: str
    weight_mult: dict[YieldType, float] = field(default_factory=dict)
    appeal: int = 0        # Liang (Parks & Recreation): +appeal to this city's tiles
    amenity: int = 0       # Liang: +1 Amenity when an Entertainment/Water Park exists
    note: str = ""


GOVERNORS: dict[str, Governor] = {
    g.key: g
    for g in (
        Governor("none", "— без губернатора —"),
        Governor("magnus", "Магнус (производство/поселенцы)",
                 {YieldType.PRODUCTION: 1.2},
                 note="Поселенцы без потери населения (Provision); Вертикальная интеграция → "
                      "региональные Промзоны. Делай этот город производственным хабом."),
        Governor("liang", "Лян (районы/привлекательность)",
                 {}, appeal=1, amenity=1,
                 note="+20% к стройке районов; «Парки и отдых»: +привлекательность и +довольство "
                      "→ усиливает Кварталы (жильё) и Заповедник."),
        Governor("pingala", "Пингала (наука/культура)",
                 {YieldType.SCIENCE: 1.3, YieldType.CULTURE: 1.3},
                 note="+науки/культуры в городе, великие люди; +30% к космическим проектам."),
        Governor("reyna", "Рейна (золото)",
                 {YieldType.GOLD: 1.25},
                 note="+золото, покупка районов/клеток — прибрежный/торговый город."),
        Governor("moksha", "Мокша (вера)",
                 {YieldType.FAITH: 1.3},
                 note="+вера, покупка верой — религиозный город, усиливает Святые места."),
    )
}


# --- secret societies (NFP mode) ------------------------------------------------
# Joined via Governor Titles; one society per game, applies empire-wide. Modelled as
# advice + a couple of district hints — the player enables this mode next game.
@dataclass(frozen=True)
class SecretSociety:
    key: str
    label: str
    note: str = ""
    favors: tuple[DistrictType, ...] = ()   # districts this society makes stronger (advice)


SECRET_SOCIETIES: dict[str, SecretSociety] = {
    s.key: s
    for s in (
        SecretSociety("none", "— без тайного общества —"),
        SecretSociety(
            "voidsingers", "Голоса Бездны (Voidsingers)",
            note="Каждый район даёт +1 веру (Культисты); чудеса дают культуру и реликвии. "
                 "Усиливает любую веру/культуру — ставь больше районов и строй чудеса.",
            favors=(DistrictType.HOLY_SITE,)),
        SecretSociety(
            "hermetic_order", "Герметический орден (Hermetic Order)",
            note="Лей-линии дают соседство Кампусу/Святому месту/Театру; +наука/вера/культура от "
                 "чудес природы. Ставь эти районы у лей-линий и природных чудес.",
            favors=(DistrictType.CAMPUS, DistrictType.HOLY_SITE, DistrictType.THEATER)),
        SecretSociety(
            "owls_minerva", "Совы Минервы (Owls of Minerva)",
            note="Доп. ячейки послов и здания Площади правительства; бонусы Военному лагерю и "
                 "Коммерческому хабу. Экономика/дипломатия.",
            favors=(DistrictType.COMMERCIAL_HUB, DistrictType.ENCAMPMENT, DistrictType.GOVERNMENT_PLAZA)),
        SecretSociety(
            "sanguine_pact", "Кровавый пакт (Sanguine Pact)",
            note="Вампиры (мощные юниты) и замки вампиров. Военное общество — на размещение "
                 "районов почти не влияет.",
            favors=(DistrictType.ENCAMPMENT,)),
    )
}


# --- religion beliefs -----------------------------------------------------------
# Founder / Follower / Worship / Enhancer beliefs. Most change yields/economy, but a
# few change a district's value enough to matter for placement; ``modeled`` marks those
# the optimizer actually accounts for (currently Work Ethic -> Holy Site Production).
@dataclass(frozen=True)
class Belief:
    key: str
    label: str
    category: str          # founder | follower | worship | enhancer
    note: str = ""
    modeled: bool = False


BELIEFS: dict[str, Belief] = {
    b.key: b
    for b in (
        # --- follower ---
        Belief("work_ethic", "Трудовая дисциплина (Work Ethic)", "follower",
               "Святое место даёт ПРОИЗВОДСТВО, равное его соседству — мощные Святые места "
               "становятся ещё и производственными. Учитывается в расчёте размещения.",
               modeled=True),
        Belief("choral_music", "Хоровая музыка (Choral Music)", "follower",
               "Святилище/Храм дают культуру — религиозно-культурная игра."),
        Belief("jesuit_education", "Иезуитское образование", "follower",
               "Можно покупать здания Кампуса и Театра за веру — быстрый разгон науки/культуры."),
        Belief("religious_community", "Религиозная община", "follower",
               "+жильё от святилищ/храмов."),
        Belief("feed_the_world", "Накормить мир", "follower",
               "+еда и +жильё от святилищ/храмов — рост."),
        Belief("divine_inspiration", "Божественное вдохновение", "follower",
               "+вера от чудес света."),
        Belief("reliquaries", "Реликварии", "follower",
               "утроенная вера и туризм от реликвий/мощей."),
        Belief("zen_meditation", "Дзен-медитация", "follower",
               "+довольство в городах с несколькими последователями."),
        Belief("warrior_monks", "Воины-монахи", "follower",
               "открывает религиозный боевой юнит."),
        # --- founder ---
        Belief("tithe", "Десятина (Tithe)", "founder",
               "+золото за каждые 4 последователя по всей империи."),
        Belief("church_property", "Церковная собственность", "founder",
               "+золото за каждый город с этой религией — стабильная экономика."),
        Belief("cross_cultural_dialogue", "Межкультурный диалог", "founder",
               "+наука за число последователей — научная религия."),
        Belief("world_church", "Вселенская церковь", "founder",
               "+культура за число городов с религией."),
        Belief("pilgrimage", "Паломничество", "founder",
               "+вера за каждый чужой город, принявший твою религию."),
        Belief("papal_primacy", "Папское первенство", "founder",
               "бонусы к отношениям с городами-государствами твоей религии."),
        Belief("stewardship", "Управление", "founder",
               "+наука и +золото в городах с губернатором."),
        # --- worship (a building you construct in the Holy Site) ---
        Belief("meeting_house", "Молитвенный дом (Meeting House)", "worship",
               "+производство в городе со Святым местом."),
        Belief("pagoda", "Пагода", "worship", "+жильё в городе со Святым местом."),
        Belief("stupa", "Ступа", "worship", "+довольство в городе со Святым местом."),
        Belief("wat", "Ват (Wat)", "worship", "+наука и +культура в городе со Святым местом."),
        Belief("cathedral", "Собор (Cathedral)", "worship", "+вера и слот великого произведения (реликвия)."),
        Belief("gurdwara", "Гурдвара", "worship", "+еда и +довольство."),
        Belief("mosque", "Мечеть", "worship", "миссионеры и апостолы получают +1 распространение."),
        Belief("synagogue", "Синагога", "worship", "+вера (молитвенное здание)."),
        Belief("dar_e_mehr", "Дар-э Мехр", "worship", "+вера (молитвенное здание)."),
        # --- enhancer ---
        Belief("scripture", "Священное писание", "enhancer", "сильнее распространение религии."),
        Belief("defender_of_faith", "Защитник веры", "enhancer", "+боевая мощь у своих городов с религией."),
        Belief("holy_order", "Священный орден", "enhancer", "дешевле миссионеры и апостолы."),
        Belief("itinerant_preachers", "Странствующие проповедники", "enhancer", "+дальность распространения."),
        Belief("crusade", "Крестовый поход (Crusade)", "enhancer",
               "+10 боевой мощи юнитам у чужих городов, исповедующих твою религию."),
        Belief("just_war", "Справедливая война", "enhancer",
               "+боевая мощь у городов, принявших твою религию."),
        Belief("religious_colonization", "Религиозная колонизация", "enhancer",
               "новые города сразу получают последователей твоей религии."),
        Belief("religious_unity", "Религиозное единство", "enhancer",
               "усиливает религиозное давление и союзы."),
    )
}


# --- victory orientation -> objective weight presets ----------------------------
# Each civ/leader leans toward a victory type. Selecting "apply focus" in the UI
# loads these yield weights (so the optimizer prioritises the matching districts)
# and pre-checks the recommended districts. Numbers are deliberate nudges, not
# hard rules — the player can still override every weight.
FOCUS_WEIGHTS: dict[str, dict[YieldType, float]] = {
    "science":    {YieldType.SCIENCE: 1.7, YieldType.PRODUCTION: 1.15},
    "culture":    {YieldType.CULTURE: 1.7, YieldType.PRODUCTION: 1.15},
    "domination": {YieldType.PRODUCTION: 1.6, YieldType.SCIENCE: 1.15},
    "religious":  {YieldType.FAITH: 1.7, YieldType.PRODUCTION: 1.1},
    "diplomatic": {YieldType.GOLD: 1.4, YieldType.FAITH: 1.25, YieldType.PRODUCTION: 1.2},
    "gold":       {YieldType.GOLD: 1.6, YieldType.PRODUCTION: 1.1},
}
FOCUS_DISTRICTS: dict[str, tuple[str, ...]] = {
    "science":    ("campus", "industrial_zone", "commercial_hub"),
    "culture":    ("theater_square", "holy_site", "commercial_hub"),
    "domination": ("encampment", "industrial_zone", "commercial_hub"),
    "religious":  ("holy_site", "theater_square", "campus"),
    "diplomatic": ("commercial_hub", "harbor", "industrial_zone"),
    "gold":       ("commercial_hub", "harbor", "campus"),
}
VICTORY_LABEL: dict[str, str] = {
    "science": "научная", "culture": "культурная", "domination": "военная (доминирование)",
    "religious": "религиозная", "diplomatic": "дипломатическая", "gold": "экономическая",
}


def focus_weights(victory: str | None) -> dict[YieldType, float]:
    """Full yield-weight preset for a victory type (1.0 for anything unspecified)."""
    base = {y: 1.0 for y in YieldType}
    base.update(FOCUS_WEIGHTS.get(victory or "", {}))
    return base


@dataclass(frozen=True)
class CivAbility:
    key: str
    label: str
    modifiers: tuple[str, ...] = ()
    note: str = ""
    victory: str = ""        # preferred victory type (drives the focus preset)
    unique: str = ""         # unique district / improvement note (placement hint)


# Civilizations the UI can offer. Selecting a civ activates its modifiers.
#
# PRINCIPLE for the `victory` field (meta-based, not flavour):
#   * Civ 6 has exactly FIVE victories — science / culture / domination / religious /
#     diplomatic. We tag each civ with the ONE it is strongest at by community
#     consensus (tier lists / Zigzagzigal / HGG), derived from its unique district,
#     unit and ability. Confirmed anchors: Korea/Maya=science, Sweden/Maori/Greece/
#     France/China=culture, Macedon/Hungary/Rome/Germany/Mongolia=domination,
#     Ethiopia/Russia/Arabia=religious, Canada/Australia=diplomatic.
#   * `gold` is NOT a victory — it is an economic focus (Mali/Portugal/Phoenician
#     trade) that normally FEEDS diplomatic (patronage/favour) or buys a domination
#     army. We keep it as a weight preset but treat it as the gold-economy path.
#   * A LEADER may OVERRIDE the civ's victory when its kit clearly redirects it
#     (Gorgo→domination, Lincoln→domination, Bull Moose Teddy→culture, Hojo→naval
#     domination). Generalist civs (Japan/Inca/Australia) keep their most-played tag.
CIVS: dict[str, CivAbility] = {
    c.key: c
    for c in (
        CivAbility("generic", "— без бонусов цивы —", (), ""),
        CivAbility("japan", "Япония", ("japan_meiji",),
                   "Точно: соседние районы дают +1 (а не +0.5). Пакуй районы вплотную.",
                   victory="culture",
                   unique="Электронная фабрика (Промзона): тот же радиус 6, но даёт больше; пакуй районы."),
        CivAbility("korea", "Корея", (),
                   "Совон (Кампус) моделируется ТОЧНО: +4 фикс, −1 за каждый соседний район, только холмы.",
                   victory="science",
                   unique="Совон = Кампус, +4 науки и −1 за каждый соседний район (вкл. центр) → ставь ИЗОЛИРОВАННО на холме, рядом с фермами/шахтами."),
        CivAbility("germany", "Германия", (),
                   "Ханза (Промзона) моделируется ТОЧНО: +2 за Ком. хаб, +1 за ресурс, +2 за акведук/дамбу.",
                   victory="domination",
                   unique="Ханза (Промзона): +2 за соседний Ком. хаб, +1 за ресурс, +2 за акведук/дамбу/канал → пакуй рядом с Ком. хабом и акведуком."),
        CivAbility("netherlands", "Нидерланды", ("nl_river_campus", "nl_river_theater", "nl_river_iz"),
                   "Реки дают БОЛЬШОЕ соседство (+2) Кампусу/Театру/Промзоне.",
                   victory="culture",
                   unique="Польдер (улучшение у воды): еда/произв./золото; реки усиливают районы — ставь районы у рек."),
        CivAbility("china", "Китай", (), "Бонусы к чудесам (стройка зарядами строителей).",
                   victory="culture",
                   unique="Великая стена (улучшение): культура/золото на границе; делай ставку на чудеса света."),
        CivAbility("gaul", "Галлия", ("gaul_hallstatt",),
                   "Шахты усиливают соседние районы; районы нельзя ставить вплотную к Центру города.",
                   victory="domination",
                   unique="Оппидум (Промзона) даёт науку и строится рано; шахты дают +0.5 соседним районам — окружай районы шахтами."),
        CivAbility("australia", "Австралия", ("australia_outback",),
                   "Районы на привлекательных клетках получают доп. соседство.",
                   victory="diplomatic",
                   unique="Аванпост (Outback Station): еда/произв., радиус-бонус от пастбищ; районы — на привлекательных клетках (у побережья/чудес)."),
        CivAbility("inca", "Инки", (),
                   "Горы дают еду (рабочие клетки) — учитывается при выборе МЕСТА города.",
                   victory="science",
                   unique="Терраса-ферма (улучшение на холмах у гор): еда/произв. Горы рабочие — БЕРЕГИ горные холмы под фермы, районы ставь на обычные клетки."),
        CivAbility("russia", "Россия", (),
                   "Тундра/снег ценнее (+вера/произв.), Лавра — при выборе МЕСТА города.",
                   victory="religious",
                   unique="Лавра (Святое место): даёт великих людей и произв. работ; соседство как у Святого места — ставь у гор/чудес природы."),
        CivAbility("khmer", "Кхмеры", (),
                   "Реки/поймы ценнее (еда, вера) — при выборе МЕСТА города.",
                   victory="religious",
                   unique="Прасат (Святое место) + акведук дают еду/веру; ставь Святые места у рек/пойм."),
        CivAbility("maya", "Майя", (),
                   "Города выгоднее рядом со столицей — при выборе МЕСТА города.",
                   victory="science",
                   unique="Обсерватория (Кампус): получает соседство от плантаций — ставь в центре плантаций, а не у гор."),
        # --- остальные цивы (Gathering Storm + New Frontier Pass). Бонусы в основном
        #     плоские (на adjacency не влияют) → показаны как подсказки; уникальные
        #     районы заменяют стандартные с тем же соседством. ---
        CivAbility("america", "Америка", (),
                   "«Отцы-основатели»: дипл. ячейки → джокеры (+дипл. очки), быстрее наследие правительств. "
                   "У Америки НЕТ уникального района; уникальное ЗДАНИЕ — Кинокомпания (в Театре, +туризм). "
                   "Конкретный стиль задаёт выбранный лидер.",
                   victory="culture",
                   unique="Нет уник. района. Кинокомпания (здание Театре) → туризм (культурная); нац.парки и "
                          "привлекательность ценны. Линкольн → Промзоны в каждом городе; «Лось» → красивые "
                          "клетки/парки; «Грубый всадник» → война на своём континенте."),
        CivAbility("arabia", "Аравия", (), "", victory="religious",
                   unique="Медресе (Кампус) даёт веру; +наука от мировой религии. Делай ставку на Святые места."),
        CivAbility("aztec", "Ацтеки", (), "", victory="domination",
                   unique="Тлачтли (Парк развлечений) +удобства/вера; строители ускоряют районы — застраивай массово."),
        CivAbility("babylon", "Вавилон", (), "", victory="science",
                   unique="Эврики дают сразу всю технологию; производство — по эпохе. Район Кампуса полезен, но наука и так быстрая."),
        CivAbility("brazil", "Бразилия", (), "", victory="culture",
                   unique="Уличный карнавал (Парк развлечений)/Копакабана (Аквапарк); тропики дают привлекательность — НЕ вырубай лес у Театров/Святых мест."),
        CivAbility("byzantium", "Византия", (), "", victory="religious",
                   unique="Ипподром (Парк развлечений) даёт тяж. кавалерию; сила = религия + армия. Святые места важны."),
        CivAbility("canada", "Канада", (), "", victory="diplomatic",
                   unique="Хоккейная коробка (улучшение тундры/снега), нац.парки; ценны тундра и привлекательность."),
        CivAbility("cree", "Кри", (), "", victory="diplomatic",
                   unique="Мекевап (улучшение на ресурсах/болоте) +еда/произв./золото; ранние торговые пути и союзы."),
        CivAbility("egypt", "Египет", (), "", victory="culture",
                   unique="Сфинкс (улучшение, вера/культура, больше у чудес); районы/чудеса быстрее у рек/пойм — селись у воды."),
        CivAbility("england", "Англия", (), "", victory="domination",
                   unique="Королевская верфь (Гавань) даёт произв.; военный флот. Прибрежные империи — Гавани важны."),
        CivAbility("ethiopia", "Эфиопия", (), "", victory="religious",
                   unique="Вера от гор/холмов/леса; наука/культура из веры. Святые места у гор; селись на возвышенностях."),
        CivAbility("france", "Франция", (), "", victory="culture",
                   unique="Шато (улучшение у рек/чудес → культура); шпионаж и чудеса. Шато (не районы) ставь на ценные клетки у рек."),
        CivAbility("georgia", "Грузия", (), "", victory="religious",
                   unique="Цихе (стены) +культура; вера в золотые/тёмные века. Святые места и города-крепости."),
        CivAbility("gran_colombia", "Великая Колумбия", (), "", victory="domination",
                   unique="Асьенда (улучшение) +еда/золото/произв. соседям; доп. движение и генералы — военная экспансия."),
        CivAbility("greece", "Греция", (), "", victory="culture",
                   unique="Акрополь (Театр) ставится на ХОЛМЕ и получает +1 от Центра города и соседних районов — ставь на холм у центра."),
        CivAbility("hungary", "Венгрия", (), "", victory="domination",
                   unique="Термы (Акведук); найм юнитов городов-государств. Союзы с ГГ + армия."),
        CivAbility("india", "Индия", (), "", victory="religious",
                   unique="Колодец-ступенька (улучшение) +жильё/вера; ставка на религию. Святые места."),
        CivAbility("indonesia", "Индонезия", (), "", victory="religious",
                   unique="Кампунг (улучшение на побережье/рифе) +еда/произв.; вера от прибрежных чудес/Парков. Прибрежные Святые места."),
        CivAbility("kongo", "Конго", (), "", victory="culture",
                   unique="Мбанза (заменяет Квартал: еда/золото без требований жилья) — ставь на лес/тропики; +реликвии/великие люди, нет религии."),
        CivAbility("macedon", "Македония", (), "", victory="domination",
                   unique="Базиликои Пайдес (Лагерь) даёт науку при захвате; войны без усталости. Лагеря важны."),
        CivAbility("mali", "Мали", (), "", victory="gold",
                   unique="Сугуба (Ком. хаб) дешевле и усиливается рекой; меньше произв., больше золото/вера от пустыни — города в пустыне у рек."),
        CivAbility("maori", "Маори", (), "", victory="culture",
                   unique="Марае (Театр) даёт культуру/веру от особенностей; лес/тропики дают привлекательность — НЕ вырубай. Великие писатели."),
        CivAbility("mapuche", "Мапуче", (), "", victory="domination",
                   unique="Чемамуль (улучшение) +культура; бонус против цив в золотом веке. Армия и давление лояльностью."),
        CivAbility("mongolia", "Монголия", (), "", victory="domination",
                   unique="Орду (Лагерь) усиливает кавалерию; торг. пути дают видимость/бонусы. Лагеря + конница."),
        CivAbility("norway", "Норвегия", (), "", victory="domination",
                   unique="Ставкирка (Святое место) +вера; прибрежные рейды и флот — прибрежная военная игра."),
        CivAbility("nubia", "Нубия", (), "", victory="domination",
                   unique="Нубийская пирамида (улучшение рядом с районом — даёт его выход); +произв. районов; Питати-лучники. Окружай районы пирамидами."),
        CivAbility("ottoman", "Османы", (), "", victory="domination",
                   unique="Большой базар (Ком. хаб); осадные Янычары, губернатор Ибрагим. Захват городов."),
        CivAbility("persia", "Персия", (), "", victory="domination",
                   unique="Пайридаэза (улучшение, культура/золото, больше у районов/Святых мест); внезапные войны и торговля — сады ставь у районов."),
        CivAbility("phoenicia", "Финикия", (), "", victory="domination",
                   unique="Котон (Гавань) +произв./опыт флота; перенос столицы, прибрежная экспансия — морская держава."),
        CivAbility("poland", "Польша", (), "", victory="religious",
                   unique="Сукеннице (Ком. хаб); форты захватывают территорию; покупка зданий за веру. Реликвии и культура из веры."),
        CivAbility("portugal", "Португалия", (), "", victory="gold",
                   unique="Фейтория (улучшение на побережье у ресурсов) +золото/наука; Нау и торговые флоты; Навиг. школа (Кампус)."),
        CivAbility("rome", "Рим", (), "", victory="domination",
                   unique="Термы (Акведук) +жильё/удобства; бесплатный памятник и дороги; Легионы — быстрое расширение и война."),
        CivAbility("scotland", "Шотландия", (), "", victory="science",
                   unique="Гольф-поле (улучшение, привлекательность/выходы); довольные/восторженные города дают +наука/произв. — держи города счастливыми."),
        CivAbility("scythia", "Скифия", (), "", victory="domination",
                   unique="Курган (улучшение у пастбищ: вера/золото); конные лучники, удвоение всадников, лечение — ранняя конная агрессия."),
        CivAbility("spain", "Испания", (), "", victory="religious",
                   unique="Миссия (улучшение, наука/вера, больше на др. континентах у Кампуса/Святого места); флоты и Инквизиция — религия + колонии."),
        CivAbility("sumeria", "Шумер", (), "", victory="domination",
                   unique="Зиккурат (улучшение у рек, не на холмах: наука/культура); боевые повозки, общие цели с союзниками — зиккураты вдоль рек."),
        CivAbility("sweden", "Швеция", (), "", victory="culture",
                   unique="Музей под открытым небом (улучшение) +культура/туризм; великие инженеры/учёные и премии — ставка на великих людей."),
        CivAbility("vietnam", "Вьетнам", (), "", victory="culture",
                   unique="ВАЖНО: специализированные районы можно строить ТОЛЬКО на лесу/тропиках/болоте, и они дают культуру — планируй районы на этих клетках."),
        CivAbility("zulu", "Зулусы", (), "", victory="domination",
                   unique="Иканда (Лагерь) — дешёвые корпуса/армии раньше; лояльность от военной мощи — армия из Лагерей."),
    )
}


@dataclass(frozen=True)
class LeaderAbility:
    key: str
    label: str
    civ: str               # associated civilization key (or "generic")
    modifiers: tuple[str, ...] = ()
    note: str = ""
    victory: str = ""      # overrides the civ's preferred victory when set


# Leaders the UI can offer. Selecting a leader applies its civ ability PLUS the
# leader's own modifiers. Most leader bonuses are flat yields that do NOT change
# *where* a district is best placed — those are shown as notes only. Leaders whose
# ability changes adjacency carry real modifiers.
LEADERS: dict[str, LeaderAbility] = {
    l.key: l
    for l in (
        LeaderAbility("none", "— без лидера —", "generic", (), ""),
        LeaderAbility("hojo", "Ходзё Токимунэ (Япония)", "japan", (),
                      "Камикадзе: +мощь в прибрежных/сухопутных боях, быстрые Лагерь/Святое место/Театр. "
                      "Меняет фокус Японии на военно-морской. Соседство районов — способность цивы (учтена).",
                      victory="domination"),
        LeaderAbility("tokugawa", "Токугава (Япония)", "japan", (),
                      "≈ Изоляция: +выходы зданий в домашних городах; на ВЫБОР клетки не влияет."),
        LeaderAbility("seondeok", "Сондок (Корея)", "korea", (),
                      "Губернаторы Хваран: +% науки/культуры; на выбор клетки не влияет."),
        LeaderAbility("barbarossa", "Барбаросса (Германия)", "germany", (),
                      "+ячейка военной политики, бонус против городов-государств; не adjacency."),
        LeaderAbility("wilhelmina", "Вильгельмина (Нидерланды)", "netherlands", (),
                      "Видит соседства заранее; +лояльность. Речные бонусы — у способности цивы."),
        LeaderAbility("qin", "Цинь Шихуанди (Китай)", "china", (),
                      "Строит чудеса зарядами строителей быстрее — учитывай при гонке за чудо."),
        LeaderAbility("ambiorix", "Амбиориг (Галлия)", "gaul", (),
                      "Соседство от шахт и запрет у Центра города — у способности цивы (учтено)."),
        LeaderAbility("john_curtin", "Джон Кёртин (Австралия)", "australia", (),
                      "Бонус производства после объявления войны вам; размещение — у способности цивы.",
                      victory="domination"),
        LeaderAbility("pachacuti", "Пачакутек (Инки)", "inca", (),
                      "Терраса-фермы у гор; влияет на выбор места города."),
        LeaderAbility("peter", "Пётр (Россия)", "russia", (),
                      "Обмен наукой/культурой по торговым путям; место города — у способности цивы."),
        LeaderAbility("jayavarman", "Джайяварман VII (Кхмеры)", "khmer", (),
                      "Святые места дают еду/жильё; реки ценнее при выборе места города."),
        LeaderAbility("lady_six_sky", "Леди Шесть Небо (Майя)", "maya", (),
                      "Сильнее у столицы; компактная империя при выборе мест городов."),
        # --- остальные лидеры (GS + NFP). Способности в основном плоские (не меняют,
        #     КУДА ставить район) → подсказки; victory переопределяет фокус цивы. ---
        # America — три персоны из Leader Pass (последние обновления):
        LeaderAbility("roosevelt_roughrider", "Теодор Рузвельт «Грубый всадник» (Америка)", "america", (),
                      "«Поправка Рузвельта»: +5 боевой мощи на родном континенте (+10 против цив на стартовом), "
                      "посол×2 при торговом пути. Военно-дипломатический стиль; на размещение районов не влияет.",
                      victory="domination"),
        LeaderAbility("roosevelt_bullmoose", "Теодор Рузвельт «Лось» (Америка)", "america", (),
                      "«Древности и парки»: клетки с привлекательностью ≥4 у гор/чудес природы → +2 науки, "
                      "у леса/чудес света → +2 культуры; нац.парк → +1 привлекательности всем клеткам города. "
                      "БЕРЕГИ красивые клетки и Заповедники — не закапывай их районами (подними «Беречь клетки»).",
                      victory="culture"),
        LeaderAbility("abraham_lincoln", "Авраам Линкольн (Америка)", "america", (),
                      "«Прокламация об освобождении»: Промзоны дают +3 лояльности/ход (плантации −2), а за каждую "
                      "построенную Промзону/её здание — бесплатный воин (+5 мощи, без ресурсов). Строй Промзону в "
                      "КАЖДОМ городе — оптимизатор это уже учитывает. На соседство не влияет.",
                      victory="domination"),
        LeaderAbility("saladin", "Саладин (Аравия)", "arabia", (),
                      "Дешёвые культовые здания/вера; ставка на Святые места."),
        LeaderAbility("montezuma", "Монтесума (Ацтеки)", "aztec", (),
                      "Бонусы от роскоши и строителей; быстрая застройка районов."),
        LeaderAbility("hammurabi", "Хаммурапи (Вавилон)", "babylon", (),
                      "Эврики дают всю технологию; производство по эпохе — на adjacency не влияет."),
        LeaderAbility("pedro", "Педру II (Бразилия)", "brazil", (),
                      "Великие люди дешевле; тропики — привлекательность, не вырубай у Театров."),
        LeaderAbility("basil", "Василий II (Византия)", "byzantium", (),
                      "Религия + тяжёлая кавалерия; сильные Святые места.", victory="domination"),
        LeaderAbility("laurier", "Уилфрид Лорье (Канада)", "canada", (),
                      "Чрезвычайные ситуации/тундра; нет внезапных войн — ценны тундра и привлекательность."),
        LeaderAbility("kublai_china", "Хубилай (Китай)", "china", (),
                      "Бонус торговли и +зарядов великих купцов; экономика.", victory="gold"),
        LeaderAbility("poundmaker", "Паундмейкер (Кри)", "cree", (),
                      "Торговые пути дают еду/золото и территорию; союзы."),
        LeaderAbility("cleopatra", "Клеопатра (Египет)", "egypt", (),
                      "Бонусы торговых путей; районы/чудеса быстрее у рек/пойм."),
        LeaderAbility("victoria", "Виктория (Англия)", "england", (),
                      "Бонусы на чужих континентах, военный флот; Гавани важны."),
        LeaderAbility("eleanor_england", "Алиенора Аквитанская (Англия)", "england", (),
                      "Великие произведения снижают лояльность врагов; ставка на культуру.", victory="culture"),
        LeaderAbility("menelik", "Менелик II (Эфиопия)", "ethiopia", (),
                      "Вера от высоты; наука/культура из веры — Святые места у гор."),
        LeaderAbility("catherine", "Екатерина Медичи (Франция)", "france", (),
                      "Шпионаж и чудеса; Шато у рек/чудес даёт культуру."),
        LeaderAbility("eleanor_france", "Алиенора Аквитанская (Франция)", "france", (),
                      "Великие произведения снижают лояльность врагов; культура и чудеса."),
        LeaderAbility("tamar", "Тамара (Грузия)", "georgia", (),
                      "Вера в золотые/тёмные века; города-крепости. Святые места."),
        LeaderAbility("bolivar", "Симон Боливар (Вел. Колумбия)", "gran_colombia", (),
                      "Доп. движение и генералы; быстрая военная экспансия."),
        LeaderAbility("pericles", "Перикл (Греция)", "greece", (),
                      "+культура за каждый сюзеренитет ГГ; Акрополь — на холме у центра."),
        LeaderAbility("gorgo", "Горго (Греция)", "greece", (),
                      "Культура за победы в бою; Акрополь — на холме у центра.", victory="domination"),
        LeaderAbility("matthias", "Матьяш Корвин (Венгрия)", "hungary", (),
                      "Найм/усиление юнитов городов-государств; союзы с ГГ + армия."),
        LeaderAbility("gandhi", "Ганди (Индия)", "india", (),
                      "Бонусы от мировых религий, без войн-агрессий; Святые места."),
        LeaderAbility("chandragupta", "Чандрагупта (Индия)", "india", (),
                      "Военная экспансия Арта-шастры; +движение/сила.", victory="domination"),
        LeaderAbility("gitarja", "Гитарджа (Индонезия)", "indonesia", (),
                      "Прибрежные города/вера; Кампунг и Святые места у воды."),
        LeaderAbility("mvemba", "Мвемба а Нзинга (Конго)", "kongo", (),
                      "Великие люди/реликвии, нет религии; Мбанза на лесу/тропиках."),
        LeaderAbility("alexander", "Александр (Македония)", "macedon", (),
                      "Войны без усталости, лечение при захвате; Лагеря важны."),
        LeaderAbility("mansa_musa", "Манса Муса (Мали)", "mali", (),
                      "Золото/вера от пустыни и торговли; Сугуба у рек, города в пустыне."),
        LeaderAbility("kupe", "Купе (Маори)", "maori", (),
                      "Старт в океане, бонусы леса/привлекательности; Марае, не вырубай лес."),
        LeaderAbility("lautaro", "Лаутаро (Мапуче)", "mapuche", (),
                      "Сильнее против цив в золотом веке; давление лояльностью и армия."),
        LeaderAbility("genghis", "Чингисхан (Монголия)", "mongolia", (),
                      "Кавалерия и захваты; Орду усиливает конницу."),
        LeaderAbility("kublai_mongolia", "Хубилай (Монголия)", "mongolia", (),
                      "Бонус торговли + великие купцы; экономика поверх кавалерии.", victory="gold"),
        LeaderAbility("harald", "Харальд Суровый (Норвегия)", "norway", (),
                      "Прибрежные рейды, флот; Ставкирка даёт веру."),
        LeaderAbility("amanitore", "Аманиторе (Нубия)", "nubia", (),
                      "+произв. районов и пирамиды у районов; быстрые районы, ставь пирамиды вокруг."),
        LeaderAbility("suleiman", "Сулейман (Османы)", "ottoman", (),
                      "Осадные Янычары, губернатор Ибрагим; захват городов."),
        LeaderAbility("cyrus", "Кир (Персия)", "persia", (),
                      "Внезапные войны и движение; сады (Пайридаэза) у районов."),
        LeaderAbility("dido", "Дидона (Финикия)", "phoenicia", (),
                      "Перенос столицы, прибрежная экспансия; Котон (Гавань)."),
        LeaderAbility("jadwiga", "Ядвига (Польша)", "poland", (),
                      "Реликвии и культура из веры; форты захватывают территорию."),
        LeaderAbility("joao", "Жуан III (Португалия)", "portugal", (),
                      "Морская торговля, Фейтория у ресурсов; Навиг. школа (Кампус)."),
        LeaderAbility("trajan", "Траян (Рим)", "rome", (),
                      "Бесплатный памятник и дороги; Термы (Акведук) — быстрое расширение."),
        LeaderAbility("robert_bruce", "Роберт Брюс (Шотландия)", "scotland", (),
                      "Счастливые города дают +наука/произв.; держи города довольными."),
        LeaderAbility("tomyris", "Томирис (Скифия)", "scythia", (),
                      "Конные лучники, лечение, удвоение всадников; ранняя агрессия."),
        LeaderAbility("philip", "Филипп II (Испания)", "spain", (),
                      "Флоты, Инквизиция, бонусы между континентами; Миссии у Кампуса/Святого места."),
        LeaderAbility("gilgamesh", "Гильгамеш (Шумер)", "sumeria", (),
                      "Боевые повозки и общие цели союзников; Зиккураты вдоль рек."),
        LeaderAbility("kristina", "Кристина (Швеция)", "sweden", (),
                      "Великие произведения/музеи и премии; ставка на великих людей."),
        LeaderAbility("ba_trieu", "Ба Чьеу (Вьетнам)", "vietnam", (),
                      "Районы только на лесу/тропиках/болоте → +культура; планируй по этим клеткам."),
        LeaderAbility("shaka", "Шака (Зулусы)", "zulu", (),
                      "Ранние дешёвые корпуса/армии; Иканда (Лагерь) и лояльность от армии."),
        # --- Leader Pass (последние обновления): новые лидеры и альт-персоны ---
        LeaderAbility("julius_caesar", "Юлий Цезарь (Рим)", "rome", (),
                      "+200 золота за первый захват города, бонусы от зачистки варваров; Термы (Акведук) — "
                      "у цивы. Ранняя война + экономика.",
                      victory="domination"),
        LeaderAbility("nzinga_mbande", "Нзинга Мбанде (Конго)", "kongo", (),
                      "Может основать религию (в отличие от Мвембы); +мощь у дальних столиц, бонусы "
                      "внутренних торг. путей. Конго с религией и культурой; Мбанза на лесу/тропиках.",
                      victory="culture"),
        LeaderAbility("nader_shah", "Надир-шах (Персия)", "persia", (),
                      "+5 боевой мощи против юнитов с полным здоровьем; завоевания. Военная Персия; "
                      "Пайридаэза (сады) у районов — у цивы.",
                      victory="domination"),
        LeaderAbility("yongle", "Юнлэ (Китай)", "china", (),
                      "Большие города (≥10 населения) дают +золото/науку/культуру за население; проекты "
                      "Лицзя конвертируют произв. в еду/веру/золото. Расти КРУПНЫЕ города.",
                      victory="gold"),
        LeaderAbility("qin_unifier", "Цинь Шихуанди «Объединитель» (Китай)", "china", (),
                      "Строителями можно достраивать районы/чудеса; +мощь против соседей. Ранняя "
                      "застройка районов зарядами строителей.",
                      victory="domination"),
        LeaderAbility("wu_zetian", "У Цзэтянь (Китай)", "china", (),
                      "Шпионаж: успешная операция даёт 100% науки/веры/культуры города за ход; бесплатный "
                      "шпион. Шпионско-научный Китай.",
                      victory="science"),
        LeaderAbility("ramses", "Рамзес II (Египет)", "egypt", (),
                      "«Абу-Симбел»: +культура за стройку зданий (15%) и чудес (30% стоимости). Ставка на "
                      "чудеса; районы/чудеса быстрее у рек/пойм.",
                      victory="culture"),
        LeaderAbility("cleopatra_ptolemaic", "Клеопатра «Птолемеи» (Египет)", "egypt", (),
                      "Ресурсы на поймах дают +еду/культуру, поймы дают +1 привлекательности соседям "
                      "(вместо −1). Селись у ПОЙМ; красивые речные города (Театры/Заповедники).",
                      victory="culture"),
        LeaderAbility("sundiata_keita", "Сундиата Кейта (Мали)", "mali", (),
                      "«Соголон»: Рынки получают слоты великих писателей, великие произв. письма дают "
                      "золото/произв.; дешевле патронаж. Ком. хабы (Сугуба) у рек + культура.",
                      victory="gold"),
        LeaderAbility("theodora", "Феодора (Византия)", "byzantium", (),
                      "«Метанойя»: Святое место даёт КУЛЬТУРУ, равную его соседству (учтено в расчёте) — "
                      "сильные Святые места становятся и культурными. Религиозно-культурная игра.",
                      victory="culture"),
        LeaderAbility("sejong", "Седжон (Корея)", "korea", (),
                      "«Хангыль»: за первую технологию новой эпохи — культура = 2× текущей науки/ход. "
                      "Совон (Кампус) ставь ИЗОЛИРОВАННО на холме — у цивы.",
                      victory="science"),
        LeaderAbility("ludwig", "Людвиг II (Германия)", "germany", (),
                      "Строящееся ЧУДО сразу даёт +2 культуры за каждый соседний район; культура соседства "
                      "даёт и туризм (после замков). Ставь чудеса в гуще районов; Ханза — у цивы.",
                      victory="culture"),
        LeaderAbility("elizabeth_i", "Елизавета I (Англия)", "england", (),
                      "Торговля и шпионаж: +ёмкость торг. путей с великим адмиралом, +золото за районы при "
                      "путях в города-государства. Морская экономика; Королевская верфь — у цивы.",
                      victory="gold"),
        LeaderAbility("victoria_steam", "Виктория «Эпоха пара» (Англия)", "england", (),
                      "+10% произв. за каждое здание Промзоны в городе; стратег. ресурсы (даже не добытые) "
                      "дают +2 произв. Строй ПРОМЗОНУ в каждом городе — оптимизатор это учитывает.",
                      victory="domination"),
        LeaderAbility("harald_varangian", "Харальд «Варяг» (Норвегия)", "norway", (),
                      "Морские набеги и грабёж прибрежных городов; флот. Прибрежная военная игра; "
                      "Ставкирка (Святое место) — у цивы.",
                      victory="domination"),
    )
}


def _default_weights() -> dict[YieldType, float]:
    return {y: 1.0 for y in YieldType}


@dataclass
class Loadout:
    """Player choices + objective weights for a single optimization run."""

    civ: str | None = None
    leader: str | None = None
    victory: str = ""        # chosen victory path (science/culture/domination/religious/
    #                          diplomatic/gold) — drives city specialization
    pantheon: str | None = None
    governor: str | None = None
    secret_society: str | None = None
    religion_beliefs: list[str] = field(default_factory=list)
    policies: list[str] = field(default_factory=list)
    government: str | None = None
    active_modifiers: list[str] = field(default_factory=list)
    weights: dict[YieldType, float] = field(default_factory=_default_weights)
    oc_weight: float = 0.0   # opportunity-cost weight: 0 = ignore base tile yields
    region_weight: float = 0.6  # value of regional-building overlap (Factory/Zoo within 6 tiles)

    def all_modifier_names(self) -> list[str]:
        names = list(self.active_modifiers)
        civ = CIVS.get(self.civ or "")
        if civ:
            names.extend(civ.modifiers)
        leader = LEADERS.get(self.leader or "")
        if leader:
            names.extend(leader.modifiers)
        pantheon = PANTHEONS.get(self.pantheon or "")
        if pantheon and pantheon.modifier:
            names.append(pantheon.modifier)
        return list(dict.fromkeys(names))  # de-dup, preserve order (avoid double-apply)

    def modifiers_for(self, dtype: DistrictType) -> list[Modifier]:
        out: list[Modifier] = []
        for name in self.all_modifier_names():
            m = MODIFIERS.get(name)
            if m and (m.applies_to is None or m.applies_to == dtype):
                out.append(m)
        return out

    def weight(self, y: YieldType) -> float:
        return self.weights.get(y, 1.0)
