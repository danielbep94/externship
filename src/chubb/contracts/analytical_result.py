"""
Contracts Foundation — Analytical Result Contract.
Defines the structured output contract produced by Analytical Foundation and verified by Validation Foundation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class StructuredMetricSlot:
    """Represents a single verified metric slot in the analytical result."""
    metric_id: str
    entity: str
    period: str
    value: Optional[float]
    unit: str
    filters: Dict[str, Any] = field(default_factory=dict)
    operation_id: str = ""
    slot_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "entity": self.entity,
            "period": self.period,
            "value": self.value,
            "unit": self.unit,
            "filters": self.filters,
            "operation_id": self.operation_id,
            "slot_keywords": self.slot_keywords,
        }


@dataclass
class AnalyticalResult:
    """Explicit output contract containing response, QueryIR, structured metrics, and traceability."""
    response: str
    ir: Dict[str, Any]
    structured_metrics: List[Dict[str, Any]] = field(default_factory=list)
    traceability: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "ir": self.ir,
            "structured_metrics": self.structured_metrics,
            "traceability": self.traceability,
        }

