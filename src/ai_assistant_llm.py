"""
Compatibility Facade for ai_assistant_llm.
Re-exports LlamaColabDataAgent and GroundedActuarialAssistant from chubb.conversational_ai.
"""

import os
import sys

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from chubb.conversational_ai.assistant import (
    GroundedActuarialAssistant,
    LlamaColabDataAgent,
)
from chubb.conversational_ai.providers import MockLlama3Provider
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.validation_foundation.data_validator import ActuarialDataValidator

__all__ = [
    "LlamaColabDataAgent",
    "GroundedActuarialAssistant",
    "MockLlama3Provider",
    "ActuarialCatalog",
    "ActuarialDataValidator",
]

if __name__ == "__main__":
    agent = LlamaColabDataAgent()
    print("=== TEST LlamaColabDataAgent (Grounded Architecture) ===")
    print(agent.process_query("Tres hallazgos clave"))
    print("-" * 50)
    print(agent.process_query("Compara Jalisco, Nuevo León, CDMX y Puebla"))
    print("-" * 50)
    print(agent.process_query("¿Y en 2024?"))
