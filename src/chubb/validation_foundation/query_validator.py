"""
Validation Foundation — Structured Query IR Pre-Execution Validator.
Validates intent families, canonical state entities, cardinality, temporal bounds,
and ranking scopes before invoking Analytical Foundation.
"""

from typing import Dict, List, Any
from chubb.contracts.error_contract import QueryValidationError
from chubb.semantic_foundation.temporal_registry import TemporalRegistry


class QueryValidator:
    """Validates structured JSON / QueryIR prior to engine execution."""

    VALID_INTENTS = {
        "executive_multistate_summary",
        "executive_single_state_summary",
        "recommendations_actions",
        "clarification_year",
        "temporal_out_of_range",
        "insufficient_data_kpi",
        "unsupported_granularity",
        "three_findings",
        "top_rankings",
        "multi_state_comparison",
        "single_state",
        "pareto_breakdown",
        "growth_cagr",
        "regression_drivers",
        "glossary_units",
        "out_of_domain"
    }

    VALID_YEAR_SOURCES = {"explicit", "memory", "default"}

    @classmethod
    def validate_structured_json(cls, structured_json: Dict[str, Any], canonical_states: List[str]) -> bool:
        """
        Valida rigurosamente el JSON estructurado ANTES de pasarlo al motor de ejecución (§8).
        Previene ejecuciones con entidades inválidas, cardinalidades inconsistentes o parámetros corruptos.
        """
        intent = structured_json.get("intent")
        if not intent:
            raise QueryValidationError("El JSON estructurado carece de 'intent'.")

        if intent not in cls.VALID_INTENTS:
            raise QueryValidationError(f"Intent desconocido: '{intent}'.")

        states = structured_json.get("states", [])
        if not isinstance(states, list):
            raise QueryValidationError("El campo 'states' debe ser una lista.")

        seen = set()
        for st in states:
            if st not in canonical_states:
                raise QueryValidationError(f"Estado no reconocido en el catálogo canónico: '{st}'.")
            if st in seen:
                raise QueryValidationError(f"Estado duplicado no permitido en 'states': '{st}'.")
            seen.add(st)

        target_year = structured_json.get("target_year")
        if target_year is not None:
            if not TemporalRegistry.is_valid_year(target_year):
                raise QueryValidationError(f"Año {target_year} fuera del dominio válido (2020-2024).")

        if intent in ("executive_multistate_summary", "executive_single_state_summary"):
            if not states:
                raise QueryValidationError(f"El intent '{intent}' requiere al menos una entidad en 'states'.")
            if intent == "executive_multistate_summary" and len(states) < 2:
                raise QueryValidationError("executive_multistate_summary requiere al menos 2 entidades únicas.")
            if intent == "executive_single_state_summary" and len(states) != 1:
                raise QueryValidationError("executive_single_state_summary requiere exactamente 1 entidad única.")
            if target_year is None:
                raise QueryValidationError(f"El intent '{intent}' requiere un 'target_year' entero resuelto (2020-2024).")
            year_source = structured_json.get("year_source")
            if year_source not in cls.VALID_YEAR_SOURCES:
                raise QueryValidationError(f"year_source inválido para resumen ejecutivo: '{year_source}'.")

        ranking_scope = structured_json.get("ranking_scope", [])
        if "selection" in ranking_scope and len(states) < 2:
            raise QueryValidationError("ranking_scope no puede incluir 'selection' cuando hay menos de 2 entidades.")

        if structured_json.get("insufficient_entities") is True and intent != "multi_state_comparison":
            raise QueryValidationError("insufficient_entities: true solo se permite con 'multi_state_comparison'.")

        return True

