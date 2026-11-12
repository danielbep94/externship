"""
Contracts Foundation — Explicit Data & Error Contracts between Foundations.
"""

from chubb.contracts.error_contract import (
    ErrorCode,
    ActuarialErrorContract,
    DataIntegrityError,
    QueryValidationError,
    HallucinationDetectedError,
    LabelSwapDetectedError,
    LLMConnectionError,
)
from chubb.contracts.query_ir import QueryIR
from chubb.contracts.analytical_result import StructuredMetricSlot, AnalyticalResult

__all__ = [
    "ErrorCode",
    "ActuarialErrorContract",
    "DataIntegrityError",
    "QueryValidationError",
    "HallucinationDetectedError",
    "LabelSwapDetectedError",
    "LLMConnectionError",
    "QueryIR",
    "StructuredMetricSlot",
    "AnalyticalResult",
]

