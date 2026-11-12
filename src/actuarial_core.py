"""
Compatibility Facade for actuarial_core.
Re-exports all public symbols from the Four-Foundation chubb package:
- chubb.semantic_foundation
- chubb.analytical_foundation
- chubb.validation_foundation
- chubb.conversational_ai
- chubb.contracts
"""

import os
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from chubb.contracts.error_contract import DataIntegrityError
from chubb.semantic_foundation.temporal_registry import (
    DEFAULT_RULES_PATH,
    load_actuarial_rules,
    normalize_text,
)
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.analytical_foundation.calculations import (
    _double_to_Shortest_decimal_str,
    round_half_up_decimal,
    format_number,
    compute_category_from_rule,
    display_category_label,
)
from chubb.analytical_foundation.actuarial_engine import ActuarialOperationsEngine
from chubb.validation_foundation.data_validator import ActuarialDataValidator
from chubb.conversational_ai.memory_manager import ConversationMemoryManager

# Alias for backward compatibility if any caller uses round_half_up_scaled
round_half_up_scaled = round_half_up_decimal

__all__ = [
    "DataIntegrityError",
    "DEFAULT_RULES_PATH",
    "load_actuarial_rules",
    "normalize_text",
    "_double_to_Shortest_decimal_str",
    "round_half_up_decimal",
    "round_half_up_scaled",
    "format_number",
    "compute_category_from_rule",
    "display_category_label",
    "ActuarialDataValidator",
    "ActuarialCatalog",
    "ConversationMemoryManager",
    "ActuarialOperationsEngine",
]
