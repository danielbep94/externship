"""
Integration Tests — Full Conversational AI Pipeline & Contracts (QueryIR -> AnalyticalResult).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from chubb.conversational_ai import GroundedActuarialAssistant
from chubb.contracts import QueryIR, AnalyticalResult
from chubb.validation_foundation import ResultValidator, ActuarialOutputVerifier


class TestAssistantPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.assistant = GroundedActuarialAssistant()

    def test_end_to_end_contract_roundtrip_and_verification(self):
        out = self.assistant.ask_with_metadata("Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023")
        ir_contract = QueryIR.from_dict(out["ir"])
        result_contract = AnalyticalResult(
            response=out["response"],
            ir=ir_contract.to_dict(),
            structured_metrics=out["structured_metrics"],
            traceability=out["traceability"],
        )
        self.assertEqual(ir_contract.intent, "executive_multistate_summary")
        self.assertTrue(ResultValidator.validate_structured_metrics(result_contract.structured_metrics))
        audit = ActuarialOutputVerifier.verify_semantic_slots(
            result_contract.response, result_contract.structured_metrics
        )
        self.assertTrue(audit["valid"])


if __name__ == "__main__":
    unittest.main()

