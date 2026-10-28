"""
Unit Tests for Phase 5: Structured JSON Generation & Pre-Validation
"""

import unittest
import sys
sys.path.append('src')

from llm_grounding import (
    ActuarialQueryParser,
    GroundedActuarialAssistant,
    QueryValidationError
)
from actuarial_core import ActuarialDataValidator, ActuarialCatalog, ConversationMemoryManager
from ai_assistant_llm import LlamaColabDataAgent

class TestLLMGrounding(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = ActuarialDataValidator.load_and_validate('/Users/victordaniel/chubb/data.json')
        cls.canonical_states = [s['entidad'] for s in cls.data['estados']]
        cls.catalog = ActuarialCatalog(cls.canonical_states)
        cls.memory = ConversationMemoryManager()
        cls.parser = ActuarialQueryParser(cls.catalog, cls.memory)
        cls.agent = LlamaColabDataAgent()

    def test_structured_json_generation_multistate(self):
        """Verifica que consultas complejas generan el JSON estructurado esperado."""
        query = "Compara Jalisco, Nuevo León, CDMX y Puebla en 2024"
        ir = self.parser.parse_to_structured_json(query)

        self.assertEqual(ir["intent"], "multi_state_comparison")
        self.assertEqual(ir["states"], ["Jalisco", "Nuevo Leon", "Ciudad de Mexico", "Puebla"])
        self.assertEqual(ir["target_year"], 2024)
        self.assertIn("severidad", ir["metrics"])

    def test_pre_validation_rejects_corrupted_intent(self):
        """Verifica que el pre-validador rechaza intents inexistentes antes de tocar el engine."""
        corrupted_ir = {
            "intent": "non_existent_intent",
            "states": ["Nuevo Leon"],
            "target_year": 2024
        }
        with self.assertRaises(QueryValidationError):
            self.parser.validate_structured_json(corrupted_ir, self.canonical_states)

    def test_pre_validation_rejects_invalid_state(self):
        """Verifica que estados no canónicos son interceptados por el pre-validador."""
        corrupted_ir = {
            "intent": "single_state",
            "states": ["Texas"], # No pertenece a México
            "target_year": 2024
        }
        with self.assertRaises(QueryValidationError):
            self.parser.validate_structured_json(corrupted_ir, self.canonical_states)

    def test_pre_validation_rejects_invalid_year(self):
        """Verifica que años fuera de rango (ej. 2030) son rechazados por el pre-validador."""
        corrupted_ir = {
            "intent": "single_state",
            "states": ["Jalisco"],
            "target_year": 2030
        }
        with self.assertRaises(QueryValidationError):
            self.parser.validate_structured_json(corrupted_ir, self.canonical_states)

    def test_end_to_end_agent_multistate_4_states(self):
        """Verifica la respuesta final con 4 estados en LlamaColabDataAgent."""
        response = self.agent.process_query("Compara Jalisco, Nuevo León, CDMX y Puebla")
        self.assertIn("Jalisco", response)
        self.assertIn("Nuevo Leon", response)
        self.assertIn("Ciudad de Mexico", response)
        self.assertIn("Puebla", response)
        self.assertIn("Identidad actuarial", response)
        self.assertIn("no equivalen a la exposición asegurada", response)

if __name__ == '__main__':
    unittest.main()
