"""
Analytical Foundation — Deterministic Actuarial Calculations, Aggregations & Operations Engine.
Rule: Operates strictly without LLM or frontend dependencies.
"""

from chubb.analytical_foundation.calculations import (
    _double_to_Shortest_decimal_str,
    round_half_up_decimal,
    format_number,
    compute_category_from_rule,
    display_category_label,
)
from chubb.analytical_foundation.aggregations import (
    is_valid_severity,
    is_valid_mdp,
    compute_national_reference,
    compute_competition_ranks,
)
from chubb.analytical_foundation.data_repository import DataRepository
from chubb.analytical_foundation.actuarial_engine import ActuarialOperationsEngine

__all__ = [
    "_double_to_Shortest_decimal_str",
    "round_half_up_decimal",
    "format_number",
    "compute_category_from_rule",
    "display_category_label",
    "is_valid_severity",
    "is_valid_mdp",
    "compute_national_reference",
    "compute_competition_ranks",
    "DataRepository",
    "ActuarialOperationsEngine",
]

