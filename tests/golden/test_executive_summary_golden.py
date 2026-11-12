"""
Golden Tests — Verifies exact numerical and structural outputs for canonical Executive Summaries and Recommendations.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from chubb.conversational_ai import GroundedActuarialAssistant


class TestExecutiveSummaryGolden(unittest.TestCase):
    def setUp(self):
        self.assistant = GroundedActuarialAssistant()

    def test_golden_multistate_nl_jalisco_2023(self):
        resp = self.assistant.ask("Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023")
        self.assertIn("Resumen ejecutivo — Nuevo Leon, Jalisco (2023)", resp)
        self.assertIn("$16,477.15 MXN", resp)
        self.assertIn("$12,131.95 MXN", resp)
        self.assertIn("$4,345.20 MXN (+35.8 % sobre Jalisco)", resp)

    def test_golden_single_state_chihuahua_2024_and_recommendations(self):
        resp1 = self.assistant.ask("Resumen ejecutivo de CHICHUACA para 2024")
        self.assertIn("Resumen ejecutivo — Chihuahua (2024)", resp1)
        self.assertIn("$11,422.11 MXN", resp1)
        resp2 = self.assistant.ask("¿Qué recomendaciones y acciones preventivas sugieres?")
        self.assertIn("Recomendaciones, Acciones Preventivas y Oportunidades — Chihuahua (2024)", resp2)
        self.assertIn("$275k MXN", resp2)


if __name__ == "__main__":
    unittest.main()
