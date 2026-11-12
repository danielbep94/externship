"""
Unit Tests — Validation Foundation (ActuarialDataValidator, QueryValidator, ResultValidator, ActuarialOutputVerifier).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from chubb.contracts import (
    DataIntegrityError,
    QueryValidationError,
    HallucinationDetectedError,
    LabelSwapDetectedError,
)
from chubb.validation_foundation import (
    ActuarialDataValidator,
    QueryValidator,
    ResultValidator,
    ActuarialOutputVerifier,
)


class TestValidationFoundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ActuarialDataValidator.load_and_validate()
        cls.states = [s["entidad"] for s in cls.data["estados"]]

    def test_query_validator_rejects_unknown_intent(self):
        with self.assertRaises(QueryValidationError):
            QueryValidator.validate_structured_json({"intent": "unknown_intent", "states": []}, self.states)

    def test_result_validator_checks_structured_metrics(self):
        valid_slot = [{"metric_id": "severidad", "entity": "Jalisco", "period": "2024", "value": 13836.27, "unit": "MXN"}]
        self.assertTrue(ResultValidator.validate_structured_metrics(valid_slot))
        with self.assertRaises(DataIntegrityError):
            ResultValidator.validate_structured_metrics([{"metric_id": "severidad"}])

    def test_output_verifier_detects_hallucinations_and_label_swaps(self):
        with self.assertRaises(HallucinationDetectedError):
            ActuarialOutputVerifier.verify("Severidad: $99,999.00 MXN", [13836.27])

        metrics = [
            {
                "metric_id": "severidad_nl",
                "entity": "Nuevo Leon",
                "period": "2023",
                "value": 12217.56,
                "unit": "MXN",
                "slot_keywords": ["nuevo leon:"]
            },
            {
                "metric_id": "severidad_jal",
                "entity": "Jalisco",
                "period": "2023",
                "value": 9792.42,
                "unit": "MXN",
                "slot_keywords": ["jalisco:"]
            },
        ]
        swapped_text = "Nuevo Leon: $9,792.42 MXN\nJalisco: $12,217.56 MXN"
        with self.assertRaises(LabelSwapDetectedError):
            ActuarialOutputVerifier.verify_semantic_slots(swapped_text, metrics)


if __name__ == "__main__":
    unittest.main()

