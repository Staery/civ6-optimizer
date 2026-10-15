"""Optimization layer."""

from .single_city import optimize_city, CityResult, Placement
from .empire import optimize_empire, EmpireResult, assign_territory
from .settle import suggest_settles, suggest_first_city, SettleSuggestion
from .wonders import recommend_wonders, WonderRec, detect_taken
from .amenities import estimate_amenities, CityAmenities
from .housing import estimate_housing, CityHousing

__all__ = [
    "optimize_city", "CityResult", "Placement",
    "optimize_empire", "EmpireResult", "assign_territory",
    "suggest_settles", "suggest_first_city", "SettleSuggestion",
    "recommend_wonders", "WonderRec", "detect_taken",
    "estimate_amenities", "CityAmenities",
    "estimate_housing", "CityHousing",
]
