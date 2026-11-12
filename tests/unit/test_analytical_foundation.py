"""
Unit Tests — Analytical Foundation (Calculations, Aggregations, ActuarialOperationsEngine, JsonDataRepository).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from chubb.analytical_foundation import (
    format_number,
    compute_category_from_rule,
    ActuarialOperationsEngine,
)
from chubb.infrastructure.json_repository import JsonDataRepository


class TestAnalyticalFoundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = JsonDataRepository()
        cls.engine = ActuarialOperationsEngine(cls.repo.get_dataset())

    def test_format_number_round_half_up_and_negative_zero(self):
        self.assertEqual(format_number(-0.0001, 2), "0.00")
        self.assertEqual(format_number(11000.005, 2), "11,000.01")

    def test_compute_category_from_rule_boundaries(self):
        self.assertEqual(compute_category_from_rule(11000.0), "Critica")
        self.assertEqual(compute_category_from_rule(10999.99), "Media")
        self.assertEqual(compute_category_from_rule(7500.0), "Media")
        self.assertEqual(compute_category_from_rule(7499.99), "Baja")

    def test_engine_operates_without_llm(self):
        summary = self.engine.compute_executive_summary(["Nuevo Leon", "Jalisco"], 2023)
        self.assertEqual(summary["target_year"], 2023)
        self.assertEqual(len(summary["rows"]), 2)
        self.assertTrue(summary["selection_summary"]["lideres_difieren"])


if __name__ == "__main__":
    unittest.main()
