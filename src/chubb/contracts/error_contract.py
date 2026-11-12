"""
Contracts Foundation — Error Contract & Exception Hierarchy.
Defines standardized error codes and exception classes across Foundations.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


class ErrorCode:
    """Standardized Error Codes across the Four-Foundation Architecture."""
    INVALID_SCHEMA = "INVALID_SCHEMA"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    UNKNOWN_METRIC = "UNKNOWN_METRIC"
    UNSUPPORTED_PERIOD = "UNSUPPORTED_PERIOD"
    MISSING_DATA = "MISSING_DATA"
    INVALID_QUERY = "INVALID_QUERY"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    GROUNDING_VALIDATION_FAILED = "GROUNDING_VALIDATION_FAILED"
    LLM_PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"


@dataclass
class ActuarialErrorContract:
    """Explicit contract representing a structured error or guardrail abstention."""
    error_code: str
    message: str
    severity: str = "S1"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "severity": self.severity,
            "details": self.details,
        }


class DataIntegrityError(Exception):
    """Excepción lanzada cuando data.json viola restricciones estructurales de esquema o reglas de integridad."""
    error_code = ErrorCode.INVALID_SCHEMA


class QueryValidationError(Exception):
    """Lanzada cuando el JSON estructurado generado no supera las reglas previas a la ejecución."""
    error_code = ErrorCode.INVALID_QUERY


class HallucinationDetectedError(Exception):
    """Lanzada cuando la salida del LLM contiene cifras no presentes en el payload grounded."""
    error_code = ErrorCode.GROUNDING_VALIDATION_FAILED


class LabelSwapDetectedError(HallucinationDetectedError):
    """Lanzada cuando las cifras existen en el payload pero sus etiquetas o entidades están intercambiadas (Error S0)."""
    error_code = ErrorCode.GROUNDING_VALIDATION_FAILED


class LLMConnectionError(ConnectionError):
    """Lanzada cuando un proveedor LLM externo no está disponible."""
    error_code = ErrorCode.LLM_PROVIDER_UNAVAILABLE

