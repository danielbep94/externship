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

    def test_post_generation_verifier_approves_grounded_numbers(self):
        """Verifica que el verificador aprueba textos con cifras autorizadas."""
        from llm_grounding import ActuarialOutputVerifier
        valid_text = "La severidad de Nuevo León es de $13,970.61 MXN con un índice de 209.3 pts y 47.1% en Pareto."
        allowed = [13970.61, 209.3, 47.1]
        self.assertTrue(ActuarialOutputVerifier.verify(valid_text, allowed))

    def test_post_generation_verifier_intercepts_hallucinations(self):
        """Verifica que el verificador detecta y arroja error ante cifras inventadas por el LLM."""
        from llm_grounding import ActuarialOutputVerifier, HallucinationDetectedError
        hallucinated_text = "La severidad inventada es de $99,999.00 MXN con 85.5% de riesgo."
        allowed = [13970.61, 10824.52] # 99,999 no está permitido
        with self.assertRaises(HallucinationDetectedError):
            ActuarialOutputVerifier.verify(hallucinated_text, allowed)

    def test_ollama_provider_connection_error_handling(self):
        """Verifica que el conector de Ollama maneja fallas de red de forma limpia."""
        from llm_grounding import OllamaProvider
        offline_provider = OllamaProvider(endpoint="http://127.0.0.1:54321/api/generate", timeout=0.1)
        with self.assertRaises(ConnectionError):
            offline_provider.generate("system", "prompt")

if __name__ == '__main__':
    unittest.main()
