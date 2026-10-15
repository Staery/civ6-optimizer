"""Recommend the best Pantheon and Policy cards for the CURRENT map situation.

Pantheons and adjacency policy cards are empire-wide choices, so these recommenders
look at what the player's land actually offers (terrain/features/resources within the
workable radius of cities) and which specialty districts they are building, then rank
the options with a short reason. Pure advice — it changes nothing on the map.
"""

from __future__ import annotations

from typing import Any

from ..i18n import tr
from ..rules.modifiers import BELIEFS, PANTHEONS

# Pantheon key -> (feature-count key it keys off, weight, reason template).
# The count keys are produced by the caller (app._city_plan) over workable tiles.
_PANTHEON_RULES: list[tuple[str, str, float, str]] = [
    ("desert_folklore", "desert", 1.0, "пустынных клеток у городов: {n} → Святое место +1 веры за каждую"),
    ("dance_of_the_aurora", "tundra", 1.0, "клеток тундры у городов: {n} → Святое место +1 веры за каждую"),
    ("sacred_path", "rainforest", 1.0, "клеток тропиков у городов: {n} → Святое место +1 веры за каждую"),
    ("river_goddess", "river", 0.9, "речных клеток у городов: {n} → Святое место у реки даёт +2 жилья и +2 довольства"),
    ("god_of_the_sea", "sea_resource", 0.9, "морских ресурсов: {n} → +1 произв. каждому (через Гавань)"),
    ("earth_goddess", "high_appeal", 0.7, "клеток с высокой привлекательностью: {n} → +1 веры с каждой"),
    ("lady_of_the_reeds_and_marshes", "reeds", 0.7, "болот/оазисов/пойм: {n} → +1 произв. с каждой"),
    ("goddess_of_the_hunt", "camp", 0.6, "Лагерей (Camp): {n} → +1 еды/+1 произв. с каждого"),
    ("god_of_the_open_sky", "pasture", 0.6, "Пастбищ: {n} → +1 культуры с каждого"),
    ("oral_tradition", "plantation", 0.6, "плантаций: {n} → +1 культуры с каждой"),
    ("god_of_craftsmen", "strategic", 0.6, "стратегических ресурсов: {n} → +1 произв./+1 веры с улучшенных"),
    ("religious_idols", "mine_lux", 0.6, "шахт на роскоши/бонусах: {n} → +2 веры с каждой"),
]


# Community-"meta" pantheons that don't need specific terrain — strong economic
# openers. Surfaced when the player hasn't locked a pantheon yet ("...по типу поселенца").
_SPECIALTY = {"campus", "holy_site", "theater_square", "commercial_hub",
              "harbor", "industrial_zone"}


def _meta_picks(districts: set[str]) -> list[tuple[str, str]]:
    picks = [("religious_settlements",
              "бесплатный Поселенец + быстрый рост границ — ранний разгон экспансии (мета)")]
    if len(_SPECIALTY & districts) >= 2:
        picks.append(("city_patron_goddess",
                      "+25% к постройке районов в городах без района — быстрее ставить районы (мета)"))
    else:
        picks.append(("fertility_rites",
                      "бесплатный Строитель и +10% к росту города (мета)"))
    return picks


def recommend_pantheon(counts: dict[str, int], districts: set[str],
                       civ: str | None = None,
                       selected: str | None = None) -> dict[str, Any] | None:
    """Rank pantheons by how much the player's land/districts support them.

    `counts` — workable-tile counts (desert/tundra/rainforest/river/…). `districts`
    — district values built or planned across the empire. `selected` — the pantheon
    the player already picked (if any). Returns the top pick plus up to two runner-ups,
    each {"key","label","reason"}, and — when no pantheon is locked yet — a `meta` list
    of strong terrain-independent openers (free Settler/Builder, fast districts).
    """
    has_holy = "holy_site" in districts        # faith pantheons need a Holy Site to pay off
    scored: list[tuple[float, str, str]] = []
    for key, ckey, w, tmpl in _PANTHEON_RULES:
        n = counts.get(ckey, 0)
        if n <= 0:
            continue
        score = n * w
        # faith-from-Holy-Site pantheons are worthless without a Holy Site in the plan
        if key in ("desert_folklore", "dance_of_the_aurora", "sacred_path",
                   "river_goddess") and not has_holy:
            score *= 0.45
        # Mali lives in the desert and leans on Faith/Gold -> nudge desert pantheons
        if civ == "mali" and key == "desert_folklore":
            score *= 1.6
        scored.append((score, key, tr(tmpl, n=n)))

    scored.sort(key=lambda t: t[0], reverse=True)

    def label_of(key: str) -> str:
        p = PANTHEONS.get(key)
        return p.label if p else key

    # meta openers — only when the player hasn't locked a pantheon yet
    not_locked = (selected or "none") == "none"
    meta = ([{"key": k, "label": label_of(k), "reason": why} for k, why in _meta_picks(districts)]
            if not_locked else [])

    if not scored:
        # no terrain-driven pick, but still suggest the meta openers
        return {"meta": meta} if meta else None

    top = {"key": scored[0][1], "label": label_of(scored[0][1]), "reason": scored[0][2]}
    top["alternatives"] = [
        {"key": k, "label": label_of(k), "reason": why} for _, k, why in scored[1:3]
    ]
    if not has_holy and scored[0][1] in ("desert_folklore", "dance_of_the_aurora",
                                         "sacred_path", "river_goddess"):
        top["reason"] += " (но сначала запланируй Святое место — иначе бонус не сработает)"
    top["meta"] = meta
    return top


# Adjacency policy cards: which one to slot, keyed by the specialty district you have.
_POLICY_FOR_DISTRICT: list[tuple[str, str, str]] = [
    ("campus", "natural_philosophy", "Natural Philosophy: +100% соседство Кампуса"),
    ("theater_square", "grand_opera", "Grand Opera: +100% соседство Театра"),
    ("commercial_hub", "free_market", "Free Market: +100% соседство Ком. хаба"),
    ("industrial_zone", "five_year_plan", "Five-Year Plan: +100% соседство Промзоны"),
]


def recommend_policies(districts: set[str]) -> list[dict[str, str]]:
    """Suggest adjacency policy cards for the specialty districts the player has.

    These cards DOUBLE a district's adjacency, so they reward clustering — slot the
    one matching your strongest specialty district. Returns [{"name","why"}].
    """
    out: list[dict[str, str]] = []
    for dval, name, why in _POLICY_FOR_DISTRICT:
        if dval in districts:
            out.append({"name": name, "why": why})
    return out


# Community-consensus "meta" belief picks — the slots people slot on most maps,
# independent of the current terrain. One strong pick per religion slot (matches the four
# dropdowns) plus a culture-victory swap note. Shown ALONGSIDE the situational rec.
_BELIEF_META: list[tuple[str, str]] = [
    ("work_ethic", "Последователь №1: со Святыми местами даёт ещё и производство = вере соседства"),
    ("cross_cultural_dialogue", "сильный Основатель: +наука за последователей по всей империи"),
    ("meeting_house", "универсальный Молитв. дом: +производство в каждом городе со Святым местом"),
    ("itinerant_preachers", "Усилитель на распространение: проще набрать последователей и обратить города"),
]
_BELIEF_META_NOTE = ("Под культуру/туризм меняют: Последователь → Реликварии, "
                     "Основатель → Вселенская церковь; под доминирование Усилитель → Крестовый поход.")


def meta_beliefs() -> dict[str, Any]:
    """Community-meta belief picks (terrain-independent), one per slot, + a swap note."""
    picks: list[dict[str, str]] = []
    for key, why in _BELIEF_META:
        b = BELIEFS.get(key)
        if b:
            picks.append({"key": key, "label": b.label, "category": b.category, "why": why})
    return {"picks": picks, "note": _BELIEF_META_NOTE}


def recommend_beliefs(districts: set[str], weights: dict[str, float]) -> list[dict[str, str]]:
    """Recommend religion beliefs for the player's situation (founder/follower/worship).

    Driven by the specialty districts the player builds; Work Ethic is the headline pick
    whenever a Holy Site is in the plan (and it's actually modelled in placement).
    Returns up to 4 {"key","label","category","why"}.
    """
    out: list[dict[str, str]] = []

    def add(key: str, why: str) -> None:
        b = BELIEFS.get(key)
        if b and not any(o["key"] == key for o in out):
            out.append({"key": key, "label": b.label, "category": b.category, "why": why})

    if "holy_site" in districts:
        add("work_ethic", "есть Святое место — его соседство даст ещё и производство "
                          "(учитывается в расчёте размещения)")
        if weights.get("culture", 1.0) > 1.0:
            add("choral_music", "культурный уклон — Святые места добавят культуру")
        add("meeting_house", "Молитвенный дом: +производство в городе со Святым местом")
    if "campus" in districts or "theater_square" in districts:
        add("jesuit_education", "покупай здания Кампуса/Театра верой — быстрый разгон науки/культуры")
    # a founder belief for steady empire-wide economy
    add("church_property", "+золото за каждый город с твоей религией — стабильная экономика")
    return out[:4]
