"""
Compatibility Facade for llm_grounding.
Re-exports all public symbols from the Four-Foundation chubb package:
- chubb.conversational_ai
- chubb.validation_foundation
- chubb.contracts
"""

import os
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from chubb.contracts.error_contract import (
    QueryValidationError,
    HallucinationDetectedError,
    LabelSwapDetectedError,
    LLMConnectionError,
)
from chubb.validation_foundation.output_verifier import ActuarialOutputVerifier
from chubb.conversational_ai.providers import (
    LLMProvider,
    MockLlama3Provider,
    OllamaProvider,
    OpenAICompatibleProvider,
)
from chubb.conversational_ai.memory_manager import ConversationMemoryManager
from chubb.conversational_ai.query_parser import ActuarialQueryParser
from chubb.conversational_ai.assistant import (
    GroundedActuarialAssistant,
    LlamaColabDataAgent,
)
from chubb.semantic_foundation.temporal_registry import (
    normalize_text,
    load_actuarial_rules,
)
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.analytical_foundation.calculations import (
    format_number,
    display_category_label,
)
from chubb.analytical_foundation.actuarial_engine import ActuarialOperationsEngine
from chubb.validation_foundation.data_validator import ActuarialDataValidator

__all__ = [
    "QueryValidationError",
    "HallucinationDetectedError",
    "LabelSwapDetectedError",
    "LLMConnectionError",
    "LLMProvider",
    "MockLlama3Provider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "ActuarialOutputVerifier",
    "ConversationMemoryManager",
    "ActuarialQueryParser",
    "GroundedActuarialAssistant",
    "LlamaColabDataAgent",
    "ActuarialDataValidator",
    "ActuarialCatalog",
    "ActuarialOperationsEngine",
    "normalize_text",
    "format_number",
    "display_category_label",
    "load_actuarial_rules",
]
