"""
Contracts Foundation — Query Intermediate Representation (QueryIR).
Defines the structured JSON contract between QueryParser, QueryValidator, and AnalyticalEngine.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class QueryIR:
    """Structured Query Intermediate Representation (IR) contract."""
    intent: str
    states: List[str] = field(default_factory=list)
    states_raw: List[str] = field(default_factory=list)
    duplicate_mentions: List[str] = field(default_factory=list)
    target_year: Optional[int] = None
    year_source: Optional[str] = None
    metrics: List[str] = field(default_factory=list)
    national_reference: Dict[str, str] = field(
        default_factory=lambda: {"method": "simple_mean_entities_with_data"}
    )
    ranking_scope: List[str] = field(default_factory=list)
    interpretation_notes: List[str] = field(default_factory=list)
    insufficient_entities: bool = False
    confidence: float = 0.95
    query_text: str = ""
    error_message: Optional[str] = None
    missing_kpis: List[str] = field(default_factory=list)
    kpi_categories: List[str] = field(default_factory=list)
    unsupported_terms: List[str] = field(default_factory=list)
    granularity_types: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "intent": self.intent,
            "states": list(self.states),
            "states_raw": list(self.states_raw),
            "duplicate_mentions": list(self.duplicate_mentions),
            "target_year": self.target_year,
            "year_source": self.year_source,
            "metrics": list(self.metrics),
            "national_reference": dict(self.national_reference),
            "ranking_scope": list(self.ranking_scope),
            "interpretation_notes": list(self.interpretation_notes),
            "insufficient_entities": self.insufficient_entities,
            "confidence": self.confidence,
            "query_text": self.query_text,
        }
        if self.error_message is not None:
            d["error_message"] = self.error_message
        if self.missing_kpis:
            d["missing_kpis"] = list(self.missing_kpis)
            d["kpi_categories"] = list(self.kpi_categories)
        if self.unsupported_terms:
            d["unsupported_terms"] = list(self.unsupported_terms)
            d["granularity_types"] = list(self.granularity_types)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryIR":
        return cls(
            intent=data["intent"],
            states=data.get("states", []),
            states_raw=data.get("states_raw", []),
            duplicate_mentions=data.get("duplicate_mentions", []),
            target_year=data.get("target_year"),
            year_source=data.get("year_source"),
            metrics=data.get("metrics", []),
            national_reference=data.get("national_reference", {"method": "simple_mean_entities_with_data"}),
            ranking_scope=data.get("ranking_scope", []),
            interpretation_notes=data.get("interpretation_notes", []),
            insufficient_entities=bool(data.get("insufficient_entities", False)),
            confidence=float(data.get("confidence", 0.95)),
            query_text=str(data.get("query_text", "")),
            error_message=data.get("error_message"),
            missing_kpis=data.get("missing_kpis", []),
            kpi_categories=data.get("kpi_categories", []),
            unsupported_terms=data.get("unsupported_terms", []),
            granularity_types=data.get("granularity_types", []),
        )

