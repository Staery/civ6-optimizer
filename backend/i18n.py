"""Russian / English localisation of everything the API returns.

The tool was written Russian-first, so the source strings in the rules, the
optimizer advice and the error messages are Russian. ``locales/en.json`` maps
each of them to English.

* The language of the current request lives in a ContextVar. ``backend.app`` sets
  it from the ``X-Lang`` header (or ``?lang=``) before the endpoint runs.
* Static text (catalogue names, notes, labels) is translated on the way out:
  :func:`localize` walks the response just before it is rendered to JSON.
* Messages composed at runtime use :func:`tr` with a ``str.format`` template, so
  the whole sentence is translated, not just its fragments.

Unknown strings pass through unchanged. Anything not found as a whole string is
translated fragment by fragment (longest match first), so a sentence glued from
catalogue pieces still comes out in English. ``tests/test_i18n.py`` checks that
every Russian literal in ``backend/`` has an entry and that no English response
contains Cyrillic.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any

LANGS = ("ru", "en")
DEFAULT_LANG = "ru"

_lang: ContextVar[str] = ContextVar("lang", default=DEFAULT_LANG)

CATALOG: dict[str, str] = json.loads(
    (Path(__file__).parent / "locales" / "en.json").read_text(encoding="utf-8")
)
_FRAGMENTS = re.compile(
    "|".join(re.escape(k) for k in sorted(CATALOG, key=len, reverse=True))
)


def set_lang(lang: str | None) -> str:
    """Set the language for the current request; unknown values fall back to Russian."""
    value = (lang or "").strip().lower()[:2]
    value = value if value in LANGS else DEFAULT_LANG
    _lang.set(value)
    return value


def get_lang() -> str:
    return _lang.get()


def translate(text: str) -> str:
    """Translate one string into the current language (identity for Russian)."""
    if _lang.get() != "en" or not text:
        return text
    hit = CATALOG.get(text)
    if hit is not None:
        return hit
    return _FRAGMENTS.sub(lambda m: CATALOG[m.group(0)], text)


def tr(template: str, **values: Any) -> str:
    """Translate a ``str.format`` template, then fill it (string values are translated too)."""
    filled = {k: translate(v) if isinstance(v, str) else v for k, v in values.items()}
    return translate(template).format(**filled)


def localize(obj: Any) -> Any:
    """Return a copy of a JSON-like structure with every string translated.

    Dict keys are translated as well: some responses are keyed by city name, and
    the same name also appears in lists, so both must change together.
    """
    if _lang.get() != "en":
        return obj
    if isinstance(obj, str):
        return translate(obj)
    if isinstance(obj, dict):
        return {(translate(k) if isinstance(k, str) else k): localize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [localize(v) for v in obj]
    return obj
