"""
Unit Tests — Semantic Foundation (EntityResolver, MetricRegistry, TemporalRegistry, ActuarialCatalog).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from chubb.semantic_foundation import (
    TemporalRegistry,
    MetricRegistry,
    EntityResolver,
    ActuarialCatalog,
    normalize_text,
)
from chubb.validation_foundation import ActuarialDataValidator


class TestSemanticFoundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ActuarialDataValidator.load_and_validate()
        cls.states = [s["entidad"] for s in cls.data["estados"]]
        cls.catalog = ActuarialCatalog(cls.states)
        cls.resolver = EntityResolver(cls.states)

    def test_normalize_text_diacritics_and_superscripts(self):
        self.assertEqual(normalize_text("Nuevo León R² 2024!"), "nuevo leon r2 2024")

    def test_temporal_registry_valid_years(self):
        self.assertTrue(TemporalRegistry.is_valid_year(2020))
        self.assertTrue(TemporalRegistry.is_valid_year(2024))
        self.assertFalse(TemporalRegistry.is_valid_year(2019))
        self.assertFalse(TemporalRegistry.is_valid_year(True))

    def test_entity_resolver_longest_span_and_aliases(self):
        det = self.resolver.extract_states_detailed("Compara BC, Baja California Sur, NL y CDMX")
        self.assertEqual(
            det["states"],
            ["Baja California", "Baja California Sur", "Nuevo Leon", "Ciudad de Mexico"]
        )

    def test_metric_registry_resolution(self):
        metrics = MetricRegistry.resolve_metrics("¿Cuál es el índice relativo y costo total en MDP?")
        self.assertIn("indice_relativo", metrics)
        self.assertIn("costo_mdp", metrics)


if __name__ == "__main__":
    unittest.main()

