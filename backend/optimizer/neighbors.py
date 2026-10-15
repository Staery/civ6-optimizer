"""Neighbour / threat assessment.

Turns the imported foreign cities (rival civs + city-states) into strategic advice:
  * which RIVALS are nearby and — if their civ is known — what victory they lean to
    (so you can compete, block, or pick a different path), plus loyalty pressure;
  * which CITY-STATES are nearby, their type, suzerain bonus and the victory they help
    (so you know where to send Envoys).

Works off whatever the import gives us: positions + names + ``kind`` always; the richer
``civ`` (rival civ key) and ``cs_type`` (city-state category) are filled in by the
export mod + parser when available, and the advice degrades gracefully without them.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from ..i18n import tr
from ..domain.hexgrid import Hex, distance
from ..rules.modifiers import CIVS, VICTORY_LABEL

# city-state category -> (russian label, suzerain bonus, victory it supports)
CS_TYPE_INFO: dict[str, tuple[str, str, str]] = {
    "scientific":   ("научное",      "+наука в Кампусах",              "science"),
    "cultural":     ("культурное",   "+культура в Театрах",            "culture"),
    "militaristic": ("военное",      "+произв. юнитов, сильнее Лагерь", "domination"),
    "industrial":   ("промышленное", "+производство районов/чудес",    "domination"),
    "religious":    ("религиозное",  "+вера в Святых местах",          "religious"),
    "trade":        ("торговое",     "+золото в Ком. хабах/Гаванях",   "diplomatic"),
}

NEAR = 6  # tiles: within this distance a rival is a direct competitor / loyalty threat


def _victory_label(v: str) -> str:
    return VICTORY_LABEL.get(v, v or "")


def assess_neighbors(our_centers: list[Hex], rival_cities: list[dict[str, Any]] | None,
                     loadout=None, radius: int = 12) -> dict[str, Any]:
    """Build the neighbour assessment for cities within ``radius`` of any of our cities."""
    rivals: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    if not our_centers:
        return {"rivals": [], "city_states": [], "advice": []}

    for rc in rival_cities or []:
        if rc.get("kind", "major") == "barbarian" or "q" not in rc or "r" not in rc:
            continue
        h = Hex(int(rc["q"]), int(rc["r"]))
        d = min(distance(h, c) for c in our_centers)
        if d > radius:
            continue
        entry: dict[str, Any] = {
            "name": rc.get("name") or "?", "distance": d,
            "population": int(rc.get("population", 0) or 0),
        }
        if rc.get("kind") == "city_state":
            t = rc.get("cs_type")
            if t in CS_TYPE_INFO:
                label, suzerain, vic = CS_TYPE_INFO[t]
                entry.update(type=t, type_label=label, suzerain=suzerain,
                             victory=vic, victory_label=_victory_label(vic))
            states.append(entry)
        else:  # major civ or free city
            civ = rc.get("civ")
            if civ and civ in CIVS and civ != "generic":
                vic = CIVS[civ].victory
                entry.update(civ=civ, civ_label=CIVS[civ].label,
                             victory=vic, victory_label=_victory_label(vic))
            rivals.append(entry)

    rivals.sort(key=lambda e: e["distance"])
    states.sort(key=lambda e: e["distance"])
    return {"rivals": rivals, "city_states": states,
            "advice": _advice(rivals, states, loadout)}


def _advice(rivals: list[dict], states: list[dict], loadout) -> list[str]:
    out: list[str] = []
    my_victory = getattr(loadout, "victory", "") if loadout else ""

    # 1) nearest rival = main competitor + loyalty pressure
    near = [r for r in rivals if r["distance"] <= NEAR]
    if near:
        r = near[0]
        who = r.get("civ_label") or r["name"]
        if r.get("victory"):
            out.append(
                tr("Ближайший соперник — {who} ({dist} кл.), склонен к победе «{victory}». "
                   "Конкурируй за неё (гонка) или выбери другой путь; жди давления "
                   "лояльностью у границы.", who=who, dist=r["distance"],
                   victory=r["victory_label"])
            )
        else:
            out.append(
                tr("Ближайший соперник — {who} ({dist} кл.). Жди давления лояльностью; "
                   "ставь Кварталы/держи довольство у границы.", who=who, dist=r["distance"])
            )
        # same-victory clash warning
        clash = [r for r in near if r.get("victory") and r["victory"] == my_victory]
        if my_victory and clash:
            names = ", ".join(c.get("civ_label") or c["name"] for c in clash)
            out.append(
                tr("⚠ Сосед(и) {names} метят в ту же победу «{victory}», что и ты — "
                   "будь быстрее или смени фокус.", names=names,
                   victory=_victory_label(my_victory))
            )

    # 2) city-state opportunities by type
    typed = [s for s in states if s.get("type")]
    if typed:
        by_vic = Counter(s["victory"] for s in typed)
        top_vic, cnt = by_vic.most_common(1)[0]
        out.append(
            tr("Рядом {n} город(ов)-государств(а); больше всего поддерживают "
               "«{victory}» ({count}) — шли туда послов.", n=len(typed),
               victory=_victory_label(top_vic), count=cnt)
        )
        if my_victory:
            helpful = [s for s in typed if s["victory"] == my_victory]
            if helpful:
                names = ", ".join(f"{s['name']} ({s['type_label']})" for s in helpful[:3])
                out.append(
                    tr("Под твою «{victory}» победу работают: {names} — приоритет послов сюда.",
                       victory=_victory_label(my_victory), names=names)
                )
    elif states:
        out.append(
            tr("Рядом {n} город(ов)-государств(а). Тип станет известен после импорта "
               "из игры (мод экспортит категорию) — тогда подскажу, куда слать послов.",
               n=len(states))
        )

    return out
