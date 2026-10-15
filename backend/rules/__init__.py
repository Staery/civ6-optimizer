"""Ruleset layer: district definitions, adjacency evaluation, and modifiers.

Target ruleset: Gathering Storm + New Frontier Pass. See ``districts.py`` for the
data tables and ``VALIDATE:`` markers on values that should be cross-checked
against the community Adjacency Planner.
"""

from .districts import DISTRICTS, DistrictDef, AdjRule, STANDARD_ADJ_DISTRICTS
from .adjacency import adjacency_yield, can_place
from .modifiers import Loadout, MODIFIERS

__all__ = [
    "DISTRICTS",
    "DistrictDef",
    "AdjRule",
    "STANDARD_ADJ_DISTRICTS",
    "adjacency_yield",
    "can_place",
    "Loadout",
    "MODIFIERS",
]
