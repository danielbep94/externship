"""
Validation Foundation — Analytical Result Validator.
Validates structured metrics and traceability contracts produced by Analytical Foundation.
"""

import math
from typing import Dict, List, Any
from chubb.contracts.error_contract import DataIntegrityError


class ResultValidator:
    """Validates analytical result payloads and structured metric slots."""

    REQUIRED_METRIC_KEYS = {"metric_id", "entity", "period", "value", "unit"}

    @classmethod
    def validate_structured_metrics(cls, structured_metrics: List[Dict[str, Any]]) -> bool:
        for idx, m in enumerate(structured_metrics):
            missing = cls.REQUIRED_METRIC_KEYS - set(m.keys())
            if missing:
                raise DataIntegrityError(f"Structured metric en índice {idx} carece de claves requeridas: {missing}")
            val = m.get("value")
            if val is not None and (not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val)):
                raise DataIntegrityError(f"Valor numérico no finito en métrica '{m.get('metric_id')}': {val}")
        return True

