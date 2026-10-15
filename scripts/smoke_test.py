"""In-process smoke test of the API surface (no server, no extra deps).

Imports the REAL endpoint handlers from backend.app and calls them directly,
so it catches runtime / serialization / wiring errors that the unit tests miss
(a 500 in an endpoint, a bad payload shape, a broken registry, a wrong cwd).

Exit 0 = all endpoints healthy. Run this BEFORE restarting the live server.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend import app as A  # noqa: E402

fails: list[str] = []


def check(name: str, fn) -> object | None:
    """Run ``fn``; pass if it returns a truthy result without raising."""
    try:
        out = fn()
        ok = out is not None and out is not False
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")
        if not ok:
            fails.append(name)
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {name}  — {type(exc).__name__}: {str(exc)[:160]}")
        fails.append(name)
        return None


def _json(resp) -> dict:
    """Extract the body of a JSONResponse (sample endpoint) or pass a dict through."""
    if isinstance(resp, dict):
        return resp
    return json.loads(bytes(resp.body).decode("utf-8"))


# 1) metadata registry ---------------------------------------------------------
meta = check("GET /api/meta", A.meta)
if meta:
    america = {l["key"] for l in meta.get("leaders", []) if l.get("civ") == "america"}
    check("America leaders (Lincoln + 2 Teddy)",
          lambda: {"abraham_lincoln", "roosevelt_roughrider", "roosevelt_bullmoose"} <= america)

# 2) sample map ----------------------------------------------------------------
sample = _json(check("GET /api/sample", A.sample) or {})
check("sample has tiles + cities", lambda: bool(sample.get("tiles")) and bool(sample.get("cities")))

# 3) core optimization ---------------------------------------------------------
check("POST /api/optimize", lambda: A.optimize(dict(sample)))
check("POST /api/plan-empire", lambda: A.plan_empire_endpoint(dict(sample, max_new=2)))

# 4) America / Lincoln end-to-end (IZ-in-every-city path must not raise) --------
check("POST /api/optimize (America / Lincoln)",
      lambda: A.optimize(dict(sample,
                              loadout={"civ": "america", "leader": "abraham_lincoln",
                                       "victory": "domination"})))

# 5) advisory endpoints --------------------------------------------------------
check("POST /api/suggest-cities", lambda: A.suggest_cities(dict(sample, max_new=2)))
check("POST /api/amenities", lambda: A.amenities(dict(sample)))
check("POST /api/housing", lambda: A.housing(dict(sample)))
check("POST /api/suggest-wonders", lambda: A.suggest_wonders(dict(sample)))

print()
if fails:
    print(f"SMOKE FAILED: {len(fails)} check(s) -> {', '.join(fails)}")
    sys.exit(1)
print("SMOKE PASSED — all endpoints healthy")
