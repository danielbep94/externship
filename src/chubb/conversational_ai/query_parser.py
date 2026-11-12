"""
Conversational AI — Actuarial Query Parser.
Parses free-form natural language queries into Structured Query IR (JSON).
"""

import re
from typing import Dict, List, Any
from chubb.semantic_foundation.temporal_registry import load_actuarial_rules, normalize_text
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.conversational_ai.memory_manager import ConversationMemoryManager
from chubb.validation_foundation.query_validator import QueryValidator


class ActuarialQueryParser:
    """
    Parser que genera el JSON estructurado intermedio (IR) a partir de lenguaje natural libre.
    Aplica el pipeline de enrutamiento (§1 y §2):
    - Separa la familia de intent de la cardinalidad de entidades deduplicadas.
    - Detecta disparadores fuertes y débiles por palabra completa (\\b).
    """

    RULES = load_actuarial_rules()
    SUMMARY_STRONG_TRIGGERS = set(RULES["triggers"]["strong_summary"])
    SUMMARY_WEAK_TRIGGERS = set(RULES["triggers"]["weak_summary"])
    CREATION_VERBS = set(RULES["triggers"]["creation_verbs"])
    COMPARISON_TRIGGERS = set(RULES["triggers"]["comparison"])
    UNSUPPORTED_KPIS = RULES["triggers"].get("unsupported_kpis", {})
    UNSUPPORTED_GRANULARITY = RULES["triggers"].get("unsupported_granularity", {})

    VALID_INTENTS = QueryValidator.VALID_INTENTS
    VALID_YEAR_SOURCES = QueryValidator.VALID_YEAR_SOURCES

    def __init__(self, catalog: ActuarialCatalog, memory: ConversationMemoryManager):
        self.catalog = catalog
        self.memory = memory

    @classmethod
    def _detect_unsupported_kpis(cls, norm_q: str) -> List[Dict[str, str]]:
        """Detecta si la consulta solicita KPIs no existentes en data.json (ventas, primas, rentabilidad, pólizas vigentes)."""
        found = []
        for cat_name, terms in cls.UNSUPPORTED_KPIS.items():
            for term in sorted(terms, key=len, reverse=True):
                if re.search(rf'\b{re.escape(term)}\b', norm_q):
                    found.append({"term": term, "category": cat_name})
        return found

    @classmethod
    def _detect_unsupported_granularity(cls, norm_q: str) -> List[Dict[str, str]]:
        """Detecta si la consulta pide desagregación municipal/ciudad o mensual/trimestral no soportada."""
        found = []
        for g_type, terms in cls.UNSUPPORTED_GRANULARITY.items():
            for term in sorted(terms, key=len, reverse=True):
                if re.search(rf'\b{re.escape(term)}\b', norm_q):
                    found.append({"term": term, "granularity_type": g_type})
        return found

    @classmethod
    def _is_summary_family(cls, norm_q: str, has_entities: bool) -> bool:
        words = set(re.findall(r'\b\w+\b', norm_q))
        if not has_entities and words.intersection({"hallazgo", "hallazgos", "conclusiones"}):
            return True
        has_strong = bool(words.intersection(cls.SUMMARY_STRONG_TRIGGERS))
        has_weak = bool(words.intersection(cls.SUMMARY_WEAK_TRIGGERS)) and bool(words.intersection(cls.CREATION_VERBS))
        return has_strong or has_weak

    @classmethod
    def _is_business_rules_or_glossary(cls, norm_q: str) -> bool:
        phrases = [
            "glosario", "definicion", "que es mdp", "volumen de costo total mdp",
            "explicar volumen de costo", "explicar mdp", "significa mdp", "que significa",
            "que es la severidad", "que es severidad", "que es la frecuencia", "que es frecuencia",
            "que es el indice", "que es indice", "que es el costo total", "que es costo total",
            "que es r2", "que es r cuadrada", "que es cagr",
            "como se calcula", "como calculan", "como se obtiene", "como se clasifica",
            "como se define", "cual es la formula", "cual es la regla", "regla de negocio",
            "reglas de negocio", "business rule", "business rules", "umbrales de", "umbral de"
        ]
        if any(p in norm_q for p in phrases):
            return True
        words = set(re.findall(r'\b\w+\b', norm_q))
        if words.intersection({"glosario", "reglas", "umbrales"}) and not words.intersection(cls.SUMMARY_STRONG_TRIGGERS):
            return True
        if "formula" in words or "formulas" in words:
            return True
        return False

    @classmethod
    def _is_comparison_family(cls, norm_q: str) -> bool:
        words = set(re.findall(r'\b\w+\b', norm_q))
        if words.intersection(cls.COMPARISON_TRIGGERS):
            return True
        if re.search(r'\bfrente a\b|\bdiferencia entre\b|\bcuanto difieren\b', norm_q):
            return True
        return False

    @classmethod
    def _is_recommendations_family(cls, norm_q: str) -> bool:
        if re.search(r'\b(recomend\w*|recomed\w*|sugerenc\w*|sugier\w*|preventiv\w*|prevenci\w*|prevensi\w*|oportunidad\w*|oputinidad\w*|mitig\w*|estrategi\w*)\b', norm_q):
            return True
        phrases = [
            "accion preventiva", "acciones preventivas", "medida preventiva", "medidas preventivas",
            "plan de accion", "planes de accion", "areas de oportunidad", "area de oportunidad",
            "identificar oportunidad", "identificar oportunidades", "identifica oportunidades",
            "como reducir", "como controlar", "como bajar", "que acciones", "que medidas"
        ]
        return any(p in norm_q for p in phrases)

    def parse_to_structured_json(self, user_query: str) -> Dict[str, Any]:
        """Convierte la consulta del usuario a un JSON estructurado intermedio (IR) según §1 y §8."""
        norm_q = normalize_text(user_query)
        words = set(re.findall(r'\b\w+\b', norm_q))

        if any(re.search(rf'\b{re.escape(w)}\b', norm_q) for w in ["clima", "temperatura", "lluvia", "tiempo manana", "futbol", "politica", "receta"]):
            return {
                "intent": "out_of_domain",
                "states": [],
                "states_raw": [],
                "duplicate_mentions": [],
                "target_year": None,
                "year_source": None,
                "metrics": [],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": [],
                "interpretation_notes": [],
                "insufficient_entities": False,
                "confidence": 0.99,
                "query_text": user_query
            }

        det = self.catalog.extract_states_detailed(user_query)
        extracted_states = det["states"]
        states_raw = det["states_raw"]
        duplicate_mentions = det["duplicate_mentions"]
        mentions_by_state = det["mentions_by_state"]

        unsupported_kpis = self._detect_unsupported_kpis(norm_q)
        if unsupported_kpis:
            years_in_q = [int(y) for y in re.findall(r'\b(202[0-4])\b', norm_q)]
            yr_val = years_in_q[0] if len(years_in_q) == 1 else None
            return {
                "intent": "insufficient_data_kpi",
                "missing_kpis": [k["term"] for k in unsupported_kpis],
                "kpi_categories": list(dict.fromkeys(k["category"] for k in unsupported_kpis)),
                "states": extracted_states,
                "states_raw": states_raw,
                "duplicate_mentions": duplicate_mentions,
                "target_year": yr_val,
                "year_source": "explicit" if yr_val is not None else None,
                "metrics": [],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": [],
                "interpretation_notes": [],
                "insufficient_entities": False,
                "confidence": 0.99,
                "query_text": user_query
            }

        unsupported_gran = self._detect_unsupported_granularity(norm_q)
        if unsupported_gran:
            years_in_q = [int(y) for y in re.findall(r'\b(202[0-4])\b', norm_q)]
            yr_val = years_in_q[0] if len(years_in_q) == 1 else None
            return {
                "intent": "unsupported_granularity",
                "unsupported_terms": [g["term"] for g in unsupported_gran],
                "granularity_types": list(dict.fromkeys(g["granularity_type"] for g in unsupported_gran)),
                "states": extracted_states,
                "states_raw": states_raw,
                "duplicate_mentions": duplicate_mentions,
                "target_year": yr_val,
                "year_source": "explicit" if yr_val is not None else None,
                "metrics": [],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": [],
                "interpretation_notes": [],
                "insufficient_entities": False,
                "confidence": 0.99,
                "query_text": user_query
            }

        effective_states = self.memory.get_effective_states(extracted_states, user_query)
        is_recommendations = self._is_recommendations_family(norm_q)
        is_summary = self._is_summary_family(norm_q, has_entities=(len(effective_states) > 0))
        is_comparison = self._is_comparison_family(norm_q)

        if is_recommendations:
            rec_states = list(effective_states)
            if not rec_states and not words.intersection({"nacional", "general", "pais", "todos", "todas", "reporte", "tablero"}) and self.memory.confirmed_states:
                rec_states = list(self.memory.confirmed_states)

            yr_res = self.memory.resolve_year_for_summary(user_query, has_explicit_states=(len(extracted_states) > 0))
            if yr_res["status"] == "temporal_out_of_range":
                return {
                    "intent": "temporal_out_of_range",
                    "error_message": yr_res["error_message"],
                    "states": [],
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }
            if yr_res["status"] == "clarification_year":
                return {
                    "intent": "clarification_year",
                    "error_message": yr_res["error_message"],
                    "states": rec_states,
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }

            target_year = yr_res["target_year"]
            year_source = yr_res["year_source"]
            if year_source == "default" and rec_states and rec_states == self.memory.confirmed_states and self.memory.confirmed_year in ConversationMemoryManager.VALID_YEARS:
                target_year = self.memory.confirmed_year
                year_source = "memory"

            notes_rec: List[str] = []
            if year_source == "default":
                notes_rec.append("No indicaste año; uso 2024, último año disponible.")
            for st_canon, raw_list in mentions_by_state.items():
                if len(raw_list) > 1:
                    notes_rec.append(f"{' y '.join(raw_list)} corresponden a la misma entidad ({st_canon}).")

            return {
                "intent": "recommendations_actions",
                "states": rec_states,
                "states_raw": states_raw,
                "duplicate_mentions": duplicate_mentions,
                "target_year": target_year,
                "year_source": year_source,
                "metrics": ["severidad", "costo_mdp", "indice_relativo", "categoria", "variacion_2020", "ranking"],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": ["national", "selection"] if len(rec_states) >= 2 else (["national"] if len(rec_states) == 1 else []),
                "interpretation_notes": notes_rec,
                "insufficient_entities": False,
                "confidence": 0.98,
                "query_text": user_query
            }

        if is_summary and len(effective_states) >= 1:
            yr_res = self.memory.resolve_year_for_summary(user_query, has_explicit_states=(len(extracted_states) > 0))
            if yr_res["status"] == "temporal_out_of_range":
                return {
                    "intent": "temporal_out_of_range",
                    "error_message": yr_res["error_message"],
                    "states": [],
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }
            if yr_res["status"] == "clarification_year":
                return {
                    "intent": "clarification_year",
                    "error_message": yr_res["error_message"],
                    "states": effective_states,
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }

            target_year = yr_res["target_year"]
            year_source = yr_res["year_source"]
            intent = "executive_multistate_summary" if len(effective_states) >= 2 else "executive_single_state_summary"
            ranking_scope = ["national", "selection"] if len(effective_states) >= 2 else ["national"]

            notes: List[str] = []
            if year_source == "default":
                notes.append("No indicaste año; uso 2024, último año disponible.")
            if "nacional" in words:
                notes.append(
                    f"Interpreté la consulta como resumen de {', '.join(effective_states)} comparado con la media de las entidades con dato."
                )
            for st_canon, raw_list in mentions_by_state.items():
                if len(raw_list) > 1:
                    notes.append(f"{' y '.join(raw_list)} corresponden a la misma entidad ({st_canon}).")

            return {
                "intent": intent,
                "states": effective_states,
                "states_raw": states_raw,
                "duplicate_mentions": duplicate_mentions,
                "target_year": target_year,
                "year_source": year_source,
                "metrics": ["severidad", "costo_mdp", "indice_relativo", "categoria", "variacion_2020", "ranking"],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": ranking_scope,
                "interpretation_notes": notes,
                "insufficient_entities": False,
                "confidence": 0.98,
                "query_text": user_query
            }

        years_found = [int(y) for y in re.findall(r'\b(19\d\d|20\d\d)\b', norm_q)]
        unique_years: List[int] = []
        for y in years_found:
            if y not in unique_years:
                unique_years.append(y)

        is_period_range = bool(words.intersection({"promedio", "periodo", "historico", "cagr", "crecimiento", "tendencia"})) and unique_years == [2020, 2024]

        if not is_period_range:
            out_of_range = [y for y in unique_years if y not in ConversationMemoryManager.VALID_YEARS]
            if out_of_range:
                bad_y = out_of_range[0]
                return {
                    "intent": "temporal_out_of_range",
                    "error_message": f"⚠️ El año {bad_y} se encuentra fuera del rango de observación del estudio (2020 a 2024).",
                    "states": [],
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }
            if len(unique_years) > 1:
                return {
                    "intent": "clarification_year",
                    "error_message": "⚠️ Indica un solo año para el resumen o consulta (2020–2024).",
                    "states": effective_states,
                    "states_raw": states_raw,
                    "duplicate_mentions": duplicate_mentions,
                    "target_year": None,
                    "year_source": None,
                    "metrics": [],
                    "national_reference": {"method": "simple_mean_entities_with_data"},
                    "ranking_scope": [],
                    "interpretation_notes": [],
                    "insufficient_entities": False,
                    "confidence": 1.0,
                    "query_text": user_query
                }

        target_year, year_err = self.memory.parse_year_intent(user_query, has_explicit_new_state=(len(extracted_states) > 0))
        if year_err:
            return {
                "intent": "temporal_out_of_range",
                "error_message": year_err,
                "states": [],
                "states_raw": states_raw,
                "duplicate_mentions": duplicate_mentions,
                "target_year": None,
                "year_source": None,
                "metrics": [],
                "national_reference": {"method": "simple_mean_entities_with_data"},
                "ranking_scope": [],
                "interpretation_notes": [],
                "insufficient_entities": False,
                "confidence": 1.0,
                "query_text": user_query
            }

        detected_metrics = self.catalog.resolve_metrics(user_query)

        if is_summary and len(effective_states) == 0:
            intent = "three_findings"
        elif self._is_business_rules_or_glossary(norm_q):
            intent = "glossary_units"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["causa", "causada", "causado", "causalidad", "provoca"]):
            intent = "regression_drivers"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["pareto", "concentracion"]) or "volumen agregado" in norm_q:
            intent = "pareto_breakdown"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["crecimiento", "cagr", "incremento", "duplicaron", "tendencia", "acumulado"]) or re.search(r'\bcrecim\w*\b', norm_q):
            intent = "growth_cagr"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["variable", "variables", "impacto", "factor", "correlacion", "afectan", "precio", "scatter", "dispersion"]) or "explicar r2" in norm_q or "72 05" in norm_q or "0 7205" in norm_q:
            intent = "regression_drivers"
        elif (any(re.search(rf'\b{w}\b', norm_q) for w in ["top", "ranking", "mayor", "menor", "lider"]) or any(p in norm_q for p in ["mayor severidad", "mayor indice", "mas alto", "mas bajo", "mas caro", "mas severos", "cuales son", "primer lugar"])) and len(effective_states) == 0:
            intent = "top_rankings"
        elif is_comparison or len(effective_states) >= 2:
            intent = "multi_state_comparison"
        elif len(effective_states) == 1:
            intent = "single_state"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["top", "ranking", "mayor"]) or "mas alto" in norm_q:
            intent = "top_rankings"
        else:
            intent = "single_state"

        insufficient_entities = False
        notes_general: List[str] = []
        if intent == "multi_state_comparison" and len(effective_states) == 1 and len(duplicate_mentions) >= 2:
            insufficient_entities = True
            notes_general.append(
                f"Ambas menciones ({' y '.join(duplicate_mentions)}) corresponden a {effective_states[0]}; indica otra entidad para comparar."
            )

        return {
            "intent": intent,
            "states": effective_states,
            "states_raw": states_raw,
            "duplicate_mentions": duplicate_mentions,
            "target_year": target_year,
            "year_source": "explicit" if (target_year is not None and len(unique_years) == 1) else ("memory" if target_year is not None else None),
            "metrics": detected_metrics,
            "national_reference": {"method": "simple_mean_entities_with_data"},
            "ranking_scope": ["national", "selection"] if len(effective_states) >= 2 else (["national"] if len(effective_states) == 1 else []),
            "interpretation_notes": notes_general,
            "insufficient_entities": insufficient_entities,
            "confidence": 0.95,
            "query_text": user_query
        }

    @classmethod
    def validate_structured_json(cls, structured_json: Dict[str, Any], canonical_states: List[str]) -> bool:
        """Delegates validation to Validation Foundation QueryValidator."""
        return QueryValidator.validate_structured_json(structured_json, canonical_states)

