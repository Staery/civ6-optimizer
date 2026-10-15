"""The web interface has an English translation for every Russian string it shows."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
CYR = re.compile("[А-Яа-яЁё]")
APP = (FRONTEND / "app.js").read_text(encoding="utf-8")
# Russian name tables are translated where they are used, via nm(TABLE, key)
NAME_TABLES = ["TERRAIN_NAME", "DISTRICT_NAME", "FEATURE_NAME", "IMPROVEMENT_NAME",
               "RES_CAT_NAME", "FOREIGN_NAME", "VICTORY_LABEL"]


def _catalogue() -> dict[str, str]:
    src = (FRONTEND / "i18n.js").read_text(encoding="utf-8")
    body = src.split("/*I18N_EN*/", 1)[1].split("/*END_I18N_EN*/", 1)[0]
    return json.loads(body)


I18N_EN = _catalogue()


def _js_string(lit: str) -> str:
    """Value of a JS string literal ("..." or '...')."""
    if lit[0] == "'":
        lit = '"' + lit[1:-1].replace('\\"', '"').replace('"', '\\"').replace("\\'", "'") + '"'
    return json.loads(lit)


def _literals(src: str):
    """(start, literal) for every "..." / '...' / `...` literal outside comments (no nesting needed:
    after the i18n pass no template literal with Russian text is left)."""
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            i = src.find("\n", i)
            i = n if i < 0 else i
            continue
        if src.startswith("/*", i):
            i = src.find("*/", i) + 2
            continue
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while src[j] != c:
                j += 2 if src[j] == "\\" else 1
            yield i, src[i:j + 1]
            i = j + 1
            continue
        i += 1


def _table_spans() -> list[tuple[int, int]]:
    spans = []
    for name in NAME_TABLES + ["RISK_COLOR"]:
        m = re.search(rf"const {name} = \{{.*?\}};", APP, re.S)
        assert m, name
        spans.append(m.span())
    return spans


def test_catalogue_is_english_with_matching_placeholders():
    for ru, en in I18N_EN.items():
        assert not CYR.search(en), en
        assert sorted(re.findall(r"\{\d+\}", ru)) == sorted(re.findall(r"\{\d+\}", en)), ru


def test_every_tr_call_is_translated():
    missing = []
    for m in re.finditer(r"\btr\((\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')", APP):
        key = _js_string(m.group(1))
        if CYR.search(key) and key not in I18N_EN:
            missing.append(key)
    assert not missing, missing


def test_name_tables_are_translated():
    for name in NAME_TABLES:
        body = re.search(rf"const {name} = \{{(.*?)\}};", APP, re.S).group(1)
        for value in re.findall(r'"([^"]*)"', body):
            if CYR.search(value):
                assert value in I18N_EN, f"{name}: {value}"


def test_no_bare_russian_strings_in_app_js():
    """Russian text must go through tr() (or live in a name table read through nm())."""
    spans = _table_spans()
    bare = []
    for start, lit in _literals(APP):
        if not CYR.search(lit) or any(a <= start < b for a, b in spans):
            continue
        if not APP[max(0, start - 3):start].endswith("tr("):
            line = APP.count("\n", 0, start) + 1
            bare.append(f"app.js:{line}: {lit[:80]}")
    assert not bare, "\n".join(bare)


def test_static_html_is_translated():
    found: list[str] = []

    class Collect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            found.extend(v for k, v in attrs if k == "title" and v and CYR.search(v))

        def handle_data(self, data):
            text = " ".join(data.split())
            if CYR.search(text):
                found.append(text)

    Collect().feed((FRONTEND / "index.html").read_text(encoding="utf-8"))
    missing = [s for s in found if s not in I18N_EN and s != "Русский"]
    assert not missing, missing
