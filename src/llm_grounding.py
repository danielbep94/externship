"""
Fase 5: Módulo de Inferencia Llama-3 y Grounding Actuarial
Implementa:
- Esquema de JSON estructurado intermedio (Structured Query IR) incluyendo executive_multistate_summary, executive_single_state_summary y clarification_year.
- Separación estricta de familia de intent y cardinalidad (deduplicación no cambia la familia).
- Pre-validador estricto del JSON estructurado antes de consultar el motor de datos.
- Capa de Grounding Verificado contra ActuarialOperationsEngine.
- Soporte para Llama-3 (vía provider pluggable) con fallback determinista grounded.
"""

import json
import re
from typing import Dict, List, Any, Optional
from actuarial_core import (
    ActuarialDataValidator,
    ActuarialCatalog,
    ConversationMemoryManager,
    ActuarialOperationsEngine,
    normalize_text,
    format_number,
    load_actuarial_rules
)

class QueryValidationError(Exception):
    """Lanzada cuando el JSON estructurado generado no supera las reglas previas a la ejecución."""
    pass

class HallucinationDetectedError(Exception):
    """Lanzada cuando la salida del LLM contiene cifras no presentes en el payload grounded."""
    pass


class LabelSwapDetectedError(HallucinationDetectedError):
    """Lanzada cuando las cifras existen en el payload pero sus etiquetas o entidades están intercambiadas (Error S0)."""
    pass

class LLMProvider:
    """Interfaz base para proveedores de LLM (Llama-3, Ollama, API, etc.)."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

class MockLlama3Provider(LLMProvider):
    """Proveedor simulado para pruebas de integración grounded."""
    def __init__(self, hallucinate: bool = False):
        self.hallucinate = hallucinate

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if self.hallucinate:
            return f"[Llama-3 Alucinación]: La severidad en este estado es de $999,999.00 MXN y 99.9% de riesgo."
        return f"[Llama-3 Grounded Response]\n{user_prompt}"

class OllamaProvider(LLMProvider):
    """Conector real con servidor local o remoto Ollama (Llama-3)."""
    def __init__(self, model: str = "llama3:8b", endpoint: str = "http://localhost:11434/api/generate", timeout: float = 15.0):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False
        }
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.endpoint, data=data_bytes, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result.get("response", "")
        except Exception as e:
            raise ConnectionError(f"Error al conectar con servidor Ollama Llama-3: {e}") from e

class OpenAICompatibleProvider(LLMProvider):
    """Conector para endpoints compatibles con OpenAI (vLLM, Groq, Colab, etc.)."""
    def __init__(self, api_url: str, api_key: str = "EMPTY", model: str = "llama-3-8b-instruct", timeout: float = 15.0):
        self.api_url = api_url.rstrip('/') + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        import urllib.request
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0
        }
        data_bytes = json.dumps(payload).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        req = urllib.request.Request(self.api_url, data=data_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result["choices"][0]["message"]["content"]

class ActuarialOutputVerifier:
    """
    Guardrail Post-Generación y Verificador de Slots Semánticos:
    1. verify(): Audita que toda cifra con $, %, pts, veces/x o r=... exista en el payload permitido.
    2. verify_semantic_slots(): Audita que cada cifra en la narrativa corresponda semánticamente
       a su metric_id y entidad (detectando intercambios de etiquetas LABEL_SWAP_ERROR — Severidad S0).
    """
    EXEMPT_CONSTANTS = {0.0, 1.0, 30.0, 35.0, 100.0, 1000.0, 1000000.0, 2020.0, 2021.0, 2022.0, 2023.0, 2024.0, 0.0001}

    @classmethod
    def verify(cls, generated_text: str, allowed_numbers: List[float], tolerance: float = 0.5) -> bool:
        amounts = re.findall(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', generated_text)
        percentages = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*%', generated_text)
        points = re.findall(r'([0-9,]+(?:\.[0-9]+)?)\s*pts\b', generated_text)
        multiples = re.findall(r'\b([0-9]+(?:\.[0-9]+)?)\s*(?:veces|x)\b', generated_text)
        correlations = re.findall(r'\br\s*=\s*\+?(-?[0-9]+\.[0-9]+)', generated_text)

        extracted_items = []
        for amt in amounts:
            try:
                extracted_items.append((float(amt.replace(',', '')), tolerance))
            except ValueError:
                pass
        for pct in percentages:
            try:
                extracted_items.append((float(pct), tolerance))
            except ValueError:
                pass
        for pt in points:
            try:
                extracted_items.append((float(pt.replace(',', '')), tolerance))
            except ValueError:
                pass
        for mult in multiples:
            try:
                extracted_items.append((float(mult), max(tolerance, 0.05)))
            except ValueError:
                pass
        for corr in correlations:
            try:
                extracted_items.append((float(corr), 0.001))
            except ValueError:
                pass

        for num, tol in extracted_items:
            if num in cls.EXEMPT_CONSTANTS:
                continue
            is_valid = any(abs(num - allowed) <= tol for allowed in allowed_numbers)
            if not is_valid:
                raise HallucinationDetectedError(
                    f"Cifra alucinada detectada en la salida del LLM: {num}. No coincide con el payload actuarial."
                )

        return True

    @classmethod
    def verify_semantic_slots(cls, generated_text: str, structured_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica el contrato estructurado de métricas (metric_id, entity, value, unit, period, filters, operation_id)
        contra el texto narrativo generado.
        Si dos métricas tienen ambos valores presentes en el texto pero la etiqueta de una está vinculada
        al valor de otra (ej. 'Severidad: $10,000' y 'Promedio nacional: $12,000' cuando severidad=12000 y ref=10000),
        lanza LabelSwapDetectedError (Error Crítico S0).
        """
        allowed_vals = [float(m["value"]) for m in structured_metrics if m.get("value") is not None]
        cls.verify(generated_text, allowed_vals, tolerance=0.5)

        raw_lines = [line.strip() for line in generated_text.splitlines() if line.strip()]

        for idx_a, m_a in enumerate(structured_metrics):
            val_a = m_a.get("value")
            if val_a is None:
                continue
            unit_a = m_a.get("unit", "")
            tol_a = 0.015 if unit_a in ("MXN", "MDP") else (0.11 if unit_a in ("pts", "%") else 0.001)
            slot_keys_a = [normalize_text(k) for k in m_a.get("slot_keywords", []) if normalize_text(k)]
            if not slot_keys_a:
                continue

            for raw_clause in raw_lines:
                clause = normalize_text(raw_clause)
                # Si la línea tiene un marcador explícito de m_a
                if any(k in clause for k in slot_keys_a):
                    nums_in_clause = [
                        float(n.replace(',', ''))
                        for n in re.findall(r'(?:\$\s*)?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+\.[0-9]+)', raw_clause)
                    ]
                    if not nums_in_clause:
                        continue
                    has_val_a = any(abs(x - val_a) <= tol_a for x in nums_in_clause)
                    if not has_val_a:
                        for idx_b, m_b in enumerate(structured_metrics):
                            if idx_a == idx_b or m_b.get("value") is None:
                                continue
                            if m_b.get("unit") != unit_a:
                                continue
                            val_b = float(m_b["value"])
                            if abs(val_a - val_b) <= tol_a:
                                continue
                            slot_keys_b = [normalize_text(k) for k in m_b.get("slot_keywords", []) if normalize_text(k)]
                            if not slot_keys_b:
                                continue
                            # Si la línea no menciona la etiqueta de B pero contiene el número exacto de B en el lugar de A
                            if not any(kb in clause for kb in slot_keys_b):
                                if any(abs(x - val_b) <= tol_a for x in nums_in_clause):
                                    raise LabelSwapDetectedError(
                                        f"LABEL_SWAP_ERROR (S0): El slot '{m_a['metric_id']}' ({m_a.get('entity')}) "
                                        f"esperaba {val_a} {unit_a}, pero recibió el valor {val_b} correspondiente a '{m_b['metric_id']}' ({m_b.get('entity')})."
                                    )

        return {"valid": True, "checked_metrics": len(structured_metrics)}


class ActuarialQueryParser:
    """
    Parser que genera el JSON estructurado intermedio (IR) a partir de lenguaje natural libre.
    Aplica el pipeline de enrutamiento (§1 y §2):
    - Separa la familia de intent de la cardinalidad de entidades deduplicadas.
    - Detecta disparadores fuertes y débiles por palabra completa (\b).
    """

    RULES = load_actuarial_rules()
    SUMMARY_STRONG_TRIGGERS = set(RULES["triggers"]["strong_summary"])
    SUMMARY_WEAK_TRIGGERS = set(RULES["triggers"]["weak_summary"])
    CREATION_VERBS = set(RULES["triggers"]["creation_verbs"])
    COMPARISON_TRIGGERS = set(RULES["triggers"]["comparison"])
    UNSUPPORTED_KPIS = RULES["triggers"].get("unsupported_kpis", {})
    UNSUPPORTED_GRANULARITY = RULES["triggers"].get("unsupported_granularity", {})

    VALID_INTENTS = {
        "executive_multistate_summary",
        "executive_single_state_summary",
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
        """
        Evalúa si la consulta pertenece a la familia de resumen ejecutivo (§2):
        - Términos fuertes activan solos: resumen, resumenes, resumir, resume, sintesis, sintetiza, sintetizar, panorama.
        - Términos débiles (reporte, informe) solo activan con un verbo de creación como término completo.
        - 'ejecutivo' nunca activa solo.
        - 'Contar el reporte en tres hallazgos' sin entidades ni verbo de creación no activa resumen estatal.
        """
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

    def parse_to_structured_json(self, user_query: str) -> Dict[str, Any]:
        """Convierte la consulta del usuario a un JSON estructurado intermedio (IR) según §1 y §8."""
        norm_q = normalize_text(user_query)
        words = set(re.findall(r'\b\w+\b', norm_q))

        # Prioridad 1: Fuera de dominio
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

        # Paso 2 del pipeline: Extraer menciones de entidades -> resolver alias -> deduplicar
        det = self.catalog.extract_states_detailed(user_query)
        extracted_states = det["states"]
        states_raw = det["states_raw"]
        duplicate_mentions = det["duplicate_mentions"]
        mentions_by_state = det["mentions_by_state"]

        # Prioridad 1.5: Confiabilidad — KPIs de negocio no disponibles en data.json (ventas, primas, rentabilidad, pólizas vigentes)
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

        # Prioridad 1.6: Confiabilidad — Granularidad sub-estatal (municipios/ciudades) o sub-anual (meses/trimestres) no soportada
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
        is_summary = self._is_summary_family(norm_q, has_entities=(len(effective_states) > 0))
        is_comparison = self._is_comparison_family(norm_q)

        # Si pertenece a la familia de resumen y hay al menos 1 entidad (Prioridades 2, 3, 4 y 5)
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

        # Prioridades 2 y 3 para consultas generales (fuera de rango o múltiples años)
        years_found = [int(y) for y in re.findall(r'\b(19\d\d|20\d\d)\b', norm_q)]
        unique_years: List[int] = []
        for y in years_found:
            if y not in unique_years:
                unique_years.append(y)

        # Ignorar el rango literal "2020 2024" cuando viene precedido de indicadores de periodo/CAGR
        is_period_range = bool(words.intersection({"promedio", "periodo", "historico", "cagr", "crecimiento", "tendencia", "acumulado"})) and unique_years == [2020, 2024]

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

        # Prioridad 6: Disparador de resumen sin entidades -> three_findings
        if is_summary and len(effective_states) == 0:
            intent = "three_findings"
        elif self._is_business_rules_or_glossary(norm_q):
            intent = "glossary_units"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["causa", "causada", "causado", "causalidad", "provoca"]):
            intent = "regression_drivers"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["pareto", "concentracion"]) or "volumen agregado" in norm_q:
            intent = "pareto_breakdown"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["crecimiento", "cagr", "incremento", "duplicaron", "tendencia", "acumulado"]):
            intent = "growth_cagr"
        elif any(re.search(rf'\b{w}\b', norm_q) for w in ["variable", "variables", "impacto", "factor", "correlacion", "afectan", "precio"]) or "explicar r2" in norm_q:
            intent = "regression_drivers"
        elif (any(re.search(rf'\b{w}\b', norm_q) for w in ["top", "ranking"]) or any(p in norm_q for p in ["mayor severidad", "mas alto", "mas severos", "cuales son"])) and len(effective_states) == 0:
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

        # Verificar que no haya estados duplicados ni fuera del catálogo canónico
        seen = set()
        for st in states:
            if st not in canonical_states:
                raise QueryValidationError(f"Estado no reconocido en el catálogo canónico: '{st}'.")
            if st in seen:
                raise QueryValidationError(f"Estado duplicado no permitido en 'states': '{st}'.")
            seen.add(st)

        target_year = structured_json.get("target_year")
        if target_year is not None:
            if not isinstance(target_year, int) or isinstance(target_year, bool) or target_year not in ConversationMemoryManager.VALID_YEARS:
                raise QueryValidationError(f"Año {target_year} fuera del dominio válido (2020-2024).")

        # Reglas específicas de Resumen Ejecutivo (§8)
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


class GroundedActuarialAssistant:
    """
    Asistente Actuarial de Producción con arquitectura Grounded:
    1. Parseo a JSON Estructurado (IR)
    2. Validación Previa al Engine
    3. Cómputo Verificado en ActuarialOperationsEngine
    4. Síntesis Grounded con Guardrails Metodológicos
    """

    def __init__(self, data_path: str = '/Users/victordaniel/chubb/data.json', llm_provider: Optional[LLMProvider] = None):
        self.data = ActuarialDataValidator.load_and_validate(data_path)
        self.canonical_states = [s["entidad"] for s in self.data["estados"]]
        self.catalog = ActuarialCatalog(self.canonical_states)
        self.memory = ConversationMemoryManager()
        self.engine = ActuarialOperationsEngine(self.data)
        self.parser = ActuarialQueryParser(self.catalog, self.memory)
        self.llm_provider = llm_provider

    @staticmethod
    def build_human_narrative(summary: Dict[str, Any]) -> str:
        """
        Construye un párrafo narrativo en lenguaje natural humano a partir de las cifras
        ya validadas y formateadas del resumen ejecutivo (cero números inventados).
        """
        yr = summary["target_year"]
        rows = summary["rows"]
        ref = summary["national_reference"]
        sel = summary["selection_summary"]

        if summary["all_severidad_missing"]:
            return ""

        if len(rows) == 1:
            r = rows[0]
            if r["severidad"] is None:
                return ""
            diff_clause = ""
            if r["indice"] is not None:
                diff_vs_100 = r["indice"] - 100.0
                pct_str = format_number(abs(diff_vs_100), 1)
                dir_str = "por encima" if diff_vs_100 >= 0 else "por debajo"
                diff_clause = f", situándose un **{pct_str} % {dir_str}** de la media de las entidades con dato (**${ref['value_fmt']} MXN**, n = {ref['n']})"
            mdp_clause = ""
            if r["costo_mdp"] is not None:
                rk_m = f" (**{r['rank_nacional_mdp']}.º lugar de {r['n_nacional_mdp']}**)" if r["rank_nacional_mdp"] is not None else ""
                mdp_clause = f" En cuanto al volumen financiero total, acumuló **${r['costo_mdp_fmt']} MDP**{rk_m}."
            evol_clause = ""
            if r["var_severidad_pct"] is not None and r["delta_indice_pts"] is not None:
                if yr == 2020:
                    evol_clause = " Al tratarse del año base **2020**, la variación acumulada desde el inicio de la serie es de **0.0 %** (**0.0 pts** en índice)."
                else:
                    evol_clause = (
                        f" En perspectiva histórica frente a 2020, tanto su severidad unitaria como su costo total presentaron una variación de **{r['var_severidad_fmt']}**, "
                        f"mientras que su índice relativo cambió en **{r['delta_indice_fmt']}** (pasando de **{r['indice_2020_fmt']}** a **{r['indice_fmt']} pts**)."
                    )
            rk_s = f" (**{r['rank_nacional_severidad']}.º lugar nacional de {r['n_nacional_severidad']}**)" if r["rank_nacional_severidad"] is not None else ""
            return (
                f"**Interpretación ejecutiva:** Durante **{yr}**, **{r['entidad']}** registró un costo medio por siniestro (severidad) de **${r['severidad_fmt']} MXN**{rk_s}, "
                f"clasificándose en nivel de riesgo **{r['categoria']}** con un índice relativo de **{r['indice_fmt']} pts**{diff_clause}.{mdp_clause}{evol_clause}"
            )

        # 2 o más entidades
        valid_sev = [r for r in rows if r["severidad"] is not None]
        if not valid_sev:
            return ""
        parts = []
        for r in rows:
            if r["severidad"] is not None:
                parts.append(
                    f"**{r['entidad']}** registró **${r['severidad_fmt']} MXN** (**{r['rank_nacional_severidad']}.º de {r['n_nacional_severidad']}**, índice **{r['indice_fmt']} pts**, categoría **{r['categoria']}**)"
                )
        joined_states = "; ".join(parts)
        gap_clause = ""
        if sel and sel["brecha_severidad_abs"] is not None and sel["lider_severidad"] != sel["menor_severidad"]:
            gap_clause = f" Esto representa una brecha de **${sel['brecha_severidad_abs_fmt']} MXN** (**+{sel['brecha_severidad_pct_fmt']} %** sobre {sel['menor_severidad']}) a favor de **{sel['lider_severidad']}**."
        mdp_contrast = ""
        if sel and sel["lideres_difieren"]:
            mdp_contrast = (
                f" No obstante, al evaluar el monto agregado en millones de pesos, el liderazgo se invierte hacia **{sel['lider_mdp']}** "
                f"(con una diferencia de **${sel['brecha_mdp_abs_fmt']} MDP** dentro de la selección)."
            )
        return (
            f"**Interpretación ejecutiva:** En el ejercicio **{yr}** —frente a una media de referencia de **${ref['value_fmt']} MXN** (n = {ref['n']})—, "
            f"{joined_states}.{gap_clause}{mdp_contrast}"
        )

    @staticmethod
    def format_executive_summary_response(summary: Dict[str, Any], structured_json: Dict[str, Any], llm_narrative: Optional[str] = None) -> str:
        """Formatea la respuesta del Resumen Ejecutivo combinando narrativa natural verificada y desglose tabular (§3, §4, §5, §6 y §9)."""
        yr = summary["target_year"]
        rows = summary["rows"]
        ref = summary["national_reference"]
        sel = summary["selection_summary"]
        notes = structured_json.get("interpretation_notes", [])
        state_titles = ", ".join(r["entidad"] for r in rows)

        lines: List[str] = [f"🤖 **Resumen ejecutivo — {state_titles} ({yr})**"]

        for note in notes:
            lines.append(f"ℹ️ *{note}*")

        if summary["all_severidad_missing"] and summary["all_mdp_missing"]:
            lines.append(f"No hay datos de severidad ni costo total para {yr} en las entidades seleccionadas.")
            return "\n".join(lines)

        if summary["all_severidad_missing"]:
            lines.append(f"No hay datos de severidad para {yr} en las entidades seleccionadas.")

        narrative = llm_narrative or GroundedActuarialAssistant.build_human_narrative(summary)
        if narrative:
            lines.append(f"\n{narrative}\n")

        if ref["value"] is not None:
            lines.append(f"Referencia: {ref['label'].lower()}, **${ref['value_fmt']} MXN (n = {ref['n']})**.\n")
        else:
            lines.append(f"Referencia: {ref['label'].lower()}, **no calculable (n = 0)**.\n")

        # 1. Severidad y categoría
        lines.append(f"**1. Severidad y categoría ({yr})**")
        lines.append("| Entidad | Severidad | Índice | Categoría | Posición nacional |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            sev_cell = f"${r['severidad_fmt']} MXN" if r["severidad"] is not None else "sin dato"
            idx_cell = f"{r['indice_fmt']} pts" if r["indice"] is not None else "no calculable"
            cat_cell = r["categoria"]
            rk_sev_cell = f"{r['rank_nacional_severidad']}.º de {r['n_nacional_severidad']}" if r["rank_nacional_severidad"] is not None else "sin dato"
            lines.append(f"| {r['entidad']} | {sev_cell} | {idx_cell} | {cat_cell} | {rk_sev_cell} |")

        if sel and sel["brecha_severidad_abs"] is not None and sel["lider_severidad"] != sel["menor_severidad"]:
            lines.append(
                f"\n{sel['lider_severidad']} supera a {sel['menor_severidad']} en **${sel['brecha_severidad_abs_fmt']} MXN (+{sel['brecha_severidad_pct_fmt']} % sobre {sel['menor_severidad']})**."
            )

        # 2. Costo total (MDP)
        lines.append(f"\n**2. Costo total ({yr})**")
        lines.append("| Entidad | Costo total | Posición nacional |")
        lines.append("|---|---|---|")
        for r in rows:
            mdp_cell = f"${r['costo_mdp_fmt']} MDP" if r["costo_mdp"] is not None else "sin dato"
            rk_mdp_cell = f"{r['rank_nacional_mdp']}.º de {r['n_nacional_mdp']}" if r["rank_nacional_mdp"] is not None else "sin dato"
            lines.append(f"| {r['entidad']} | {mdp_cell} | {rk_mdp_cell} |")

        if sel and sel["lider_mdp"]:
            if sel["lideres_difieren"]:
                lines.append(
                    f"\nEn la selección, **{sel['lider_severidad']}** lidera la severidad y **{sel['lider_mdp']}** el costo total (diferencia: ${sel['brecha_mdp_abs_fmt']} MDP). "
                    "En este conjunto de datos, la severidad se calcula dividiendo el costo entre un número de siniestros estimado a partir de la población (35 % de exposición × 30 % de frecuencia), así que la diferencia de posiciones refleja ese denominador y no una medición de la exposición asegurada."
                )
            elif sel["brecha_mdp_abs"] is not None and sel["lider_mdp"] != sel["menor_mdp"]:
                lines.append(
                    f"\nEn la selección, **{sel['lider_mdp']}** lidera tanto la severidad como el costo total (diferencia en costo: ${sel['brecha_mdp_abs_fmt']} MDP)."
                )

        # 3. Evolución 2020 -> Y
        lines.append(f"\n**3. Evolución 2020 → {yr}**")
        lines.append("| Entidad | Severidad | Costo total | Índice |")
        lines.append("|---|---|---|---|")
        for r in rows:
            if r["delta_indice_pts"] is not None:
                idx_evol = f"{r['delta_indice_fmt']} ({r['indice_2020_fmt']} → {r['indice_fmt']})"
            else:
                idx_evol = "no calculable"
            lines.append(f"| {r['entidad']} | {r['var_severidad_fmt']} | {r['var_mdp_fmt']} | {idx_evol} |")

        lines.append("\n*Coinciden porque la severidad se deriva del costo con un número de siniestros fijo por entidad.*")

        # 4. Alcance y limitaciones
        lines.append("\n**4. Alcance y limitaciones**")
        lines.append("- Severidad = costo total / siniestros estimados (35 % × 30 % de la población 2020); no son siniestros observados.")
        lines.append("- El parque INEGI VMRC no equivale a la exposición asegurada y no varía por año en este conjunto de datos.")
        lines.append("- Umbrales absolutos en MXN nominales; no se ajustan por inflación.")

        return "\n".join(lines)

    def format_business_rules_response(self, user_query: str) -> str:
        """
        Responde consultas sobre Reglas de Negocio (Business Rules), fórmulas matemáticas,
        umbrales, tratamiento de datos faltantes, redondeo ROUND_HALF_UP y glosario actuarial.
        """
        norm_q = normalize_text(user_query)
        ref_2024, n_2024 = self.engine.compute_national_reference_for_year("2024")
        cdmx_2024 = self.engine.estados_dict["Ciudad de Mexico"]["yearly_severidad"]["2024"]
        cdmx_idx_2024 = (cdmx_2024 / ref_2024) * 100.0 if ref_2024 else 0.0

        # 1. Regla específica de Índice Relativo / Referencia Nacional
        if ("indice" in norm_q or "relativo" in norm_q or "base 100" in norm_q or "referencia nacional" in norm_q) and "glosario" not in norm_q:
            return f"""🤖 **Regla de Negocio (RN-01) — Cálculo del Índice Relativo y Referencia Nacional**:

**1. Fórmula Matemática Oficial**:
• `Índice_e(Y) = 100 × [ Severidad_e(Y) / Media_ref(Y) ]`
• `Media_ref(Y) = Σ Severidad_e(Y) / n(Y)` (media simple de las `n(Y)` entidades con severidad válida `> 0` en el año `Y`).

**2. Interpretación Actuarial**:
• **Base 100.0 pts**: Equivale exactamente a la *Media de severidad de las entidades con dato* del mismo año.
• Un valor de **156.1 pts** significa que la entidad tiene una severidad **+56.1 % superior** a la media de las entidades con dato en ese año.

**3. Reglas de Datos Faltantes y Redondeo (`config/actuarial_rules.json`)**:
• **Faltantes**: Si `Severidad_e(Y)` es `null`/`≤ 0` o si `n(Y) == 0`, el índice se reporta como **`no calculable`** (jamás se sustituye por `0`).
• **Precisión y Redondeo**: Se calcula en precisión completa (`IEEE-754`) y se presenta a **1 decimal** mediante **`ROUND_HALF_UP`** (mitad lejos de cero sobre la representación decimal más corta).

**4. Ejemplo Verificable con Datos Reales (Ciudad de México, 2024)**:
• `Severidad_CDMX(2024)` = **${format_number(cdmx_2024, 2)} MXN**
• `Media_ref(2024)` = **${format_number(ref_2024, 2)} MXN** (`n = {n_2024}`)
• `Índice_CDMX(2024)` = `100 × ({format_number(cdmx_2024, 2)} / {format_number(ref_2024, 2)})` = **{format_number(cdmx_idx_2024, 1)} pts**."""

        # 2. Regla específica de Categorías y Umbrales
        if any(w in norm_q for w in ["categoria", "umbral", "umbrales", "semaforo", "clasifica"]) and "glosario" not in norm_q:
            return """🤖 **Regla de Negocio (RN-02) — Clasificación y Umbrales de Categoría de Riesgo**:

**1. Umbrales Nominales Oficiales (`P3`, `config/actuarial_rules.json`)**:
• 🔴 **Crítica**: `Severidad >= $11,000.00 MXN`
• 🟡 **Media**: `$7,500.00 MXN <= Severidad < $11,000.00 MXN`
• 🟢 **Baja**: `0 < Severidad < $7,500.00 MXN`

**2. Reglas de Evaluación e Integridad**:
• La comparación se ejecuta sobre el valor numérico **sin redondear**.
• **Aislamiento temporal**: En cualquier consulta de un año específico `Y`, la categoría se lee exclusivamente de `yearly_categoria[Y]`. Si falta ese dato o la severidad no es válida, se muestra **`sin dato`** (nunca se usa `categoria_severidad` del periodo 2020–2024 como sustituto).
• Los umbrales están expresados en MXN nominales y no se indexan por inflación."""

        # 3. Regla específica de Evolución / Variación / CAGR
        if any(w in norm_q for w in ["evolucion", "variacion", "cagr", "delta"]) and "glosario" not in norm_q:
            return """🤖 **Regla de Negocio (RN-03) — Evolución Temporal (2020 → YYYY) y CAGR**:

**1. Fórmulas de Variación desde el Año Base (2020)**:
• **Variación % de Severidad**: `((Severidad_Y / Severidad_2020) - 1) × 100` (en `%`, 1 decimal).
• **Variación % de Costo Total (MDP)**: `((MDP_Y / MDP_2020) - 1) × 100` (en `%`, 1 decimal).
• **Cambio en Índice Relativo (`Δ Índice`)**: `Índice_Y - Índice_2020` (en **`pts`**, diferencia aritmética en puntos, no porcentual).
• **CAGR Anual Compuesto (2020–2024)**: `((Severidad_2024 / Severidad_2020)^(1/4) - 1) × 100`.

**2. Casos Límite y Propiedad del Modelo (`H4`)**:
• Si el año consultado es `2020` y la base es válida, el resultado es **`0.0 %`** y **`0.0 pts`**.
• Si la base `2020` es `null`, ausente o `<= 0`, se reporta **`no calculable`**.
• En este dataset, la variación `%` de severidad y de MDP coinciden exactamente porque la severidad se deriva con un denominador poblacional fijo por entidad (`0.35 × 0.30 × población_2020`)."""

        # 4. Regla específica de Rankings y Empates
        if any(w in norm_q for w in ["ranking", "posicion", "empate", "empates"]) and "glosario" not in norm_q:
            return """🤖 **Regla de Negocio (RN-04) — Rankings Nacionales, de Selección y Empates**:

**1. Alcance Nacional y Denominador Dinámico**:
• La posición de cada métrica (`severidad` o `costo_mdp`) en el año `Y` se calcula únicamente entre las entidades con valor válido en ese año: formato **`k.º de n_métrica(Y)`**.

**2. Regla de Empates (Ranking de Competencia Estándar `1, 1, 3`)**:
• Los valores se comparan **redondeados a la precisión de presentación** (`2 decimales` / centavos mediante `ROUND_HALF_UP`).
• Si dos entidades empatan al centavo (p. ej. `$100.004` y `$100.001` → ambos `$100.00`), comparten la posición `1.º` y la siguiente entidad recibe la posición `3.º`.

**3. Alcance de Selección**:
• Solo se calcula cuando se consultan `>= 2` entidades únicas. Para `1` sola entidad se omite ("1 de 1" no aporta información)."""

        # 5. Catálogo Completo de Reglas de Negocio + Glosario Actuarial y Unidades
        return f"""🤖 **Catálogo de Reglas de Negocio (`config/actuarial_rules.json`) y Glosario Actuarial**:

• **RN-01 · Referencia Nacional e Índice Relativo (`pts`)**:
  - `Media_ref(Y) = Σ Severidad_e(Y) / n(Y)` (Media de severidad de las entidades con dato; en el promedio 2020–2024 es **${format_number(self.engine.national_avg_severity, 2)} MXN**, `n = 32`).
  - `Índice_e(Y) = 100 × Severidad_e(Y) / Media_ref(Y)` (Base 100, redondeado a `1 decimal` con `ROUND_HALF_UP`).

• **RN-02 · Umbrales de Categoría de Severidad (`P3`)**:
  - **Crítica**: `>= $11,000.00 MXN` | **Media**: `$7,500.00 a < $11,000.00 MXN` | **Baja**: `< $7,500.00 MXN`.
  - Evaluados sin redondear; la categoría anual `yearly_categoria[Y]` nunca se sustituye por la del periodo.

• **RN-03 · Severidad (`$/Siniestro`) y Costo Total en `MDP` (Millones de Pesos)**:
  - `1 MDP = $1,000,000 MXN`. El total anual promedio nacional es de **${format_number(self.engine.total_national_mdp, 2)} MDP**.
  - **Identidad Actuarial**: `Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000`.
  - **Derivación en el dataset (`H4`)**: `Severidad = (MDP × 10^6) / (0.35 × 0.30 × población_2020)`.
  - **Exposición vs. Parque Registrado**: El parque vehicular (INEGI VMRC) mide escala macro, pero **no equivale a la exposición asegurada** (pólizas vigentes).

• **RN-04 · Evolución 2020 → YYYY**:
  - `Var % = ((Valor_Y / Valor_2020) - 1) × 100` | `Δ Índice (pts) = Índice_Y - Índice_2020`. Base ausente o `0` → `no calculable`.

• **RN-05 · Rankings y Empates**:
  - Ranking de competencia (`1, 1, 3`) comparando valores redondeados al centavo (`2 decimales`) sobre `n_métrica(Y)` entidades válidas.

• **RN-06 · Redondeo Determinista y Año por Defecto (`P2`)**:
  - Redondeo `ROUND_HALF_UP` (mitad lejos de cero) sobre la representación decimal más corta del `double` en Python y JS (`-0.00` → `0.00`).
  - Año omitido en resumen ejecutivo → usa **`2024`** (`default`) con aviso explícito; solo hereda memoria en consultas de continuación (`¿Y ...?`, `también`, `mismo año`)."""

    def _try_llm_executive_narrative(self, summary: Dict[str, Any], user_query: str) -> Optional[str]:
        """
        Si hay un proveedor Llama-3 conectado (Ollama / OpenAI API), genera una síntesis
        narrativa natural basada exclusivamente en el payload verificado y la audita con
        ActuarialOutputVerifier para impedir cualquier cifra alucinada.
        """
        if self.llm_provider is None:
            return None
        allowed_nums: List[float] = [float(summary["target_year"]), 2020.0, 2024.0, 35.0, 30.0, 100.0]
        if summary["national_reference"]["value"] is not None:
            allowed_nums.append(float(summary["national_reference"]["value"]))
            allowed_nums.append(float(summary["national_reference"]["n"]))
        for r in summary["rows"]:
            for k in ("severidad", "indice", "indice_2020", "costo_mdp", "var_severidad_pct", "var_mdp_pct", "delta_indice_pts"):
                if r.get(k) is not None:
                    allowed_nums.append(abs(float(r[k])))
        if summary["selection_summary"]:
            for k in ("brecha_severidad_abs", "brecha_severidad_pct", "brecha_mdp_abs"):
                val = summary["selection_summary"].get(k)
                if val is not None:
                    allowed_nums.append(abs(float(val)))

        sys_prompt = (
            "Eres un consultor actuarial senior de Chubb. Redacta UN párrafo breve (3 a 4 oraciones) "
            "en español claro, ejecutivo y humano explicando los resultados del JSON adjunto. "
            "PROHIBIDO inventar o alterar cifras: usa únicamente las cifras exactas del JSON."
        )
        usr_prompt = f"Consulta: {user_query}\nDatos verificados: {json.dumps(summary, ensure_ascii=False)}"
        try:
            gen_text = self.llm_provider.generate(sys_prompt, usr_prompt).strip()
            if gen_text and ActuarialOutputVerifier.verify(gen_text, allowed_nums, tolerance=0.5):
                return f"**Interpretación ejecutiva (Llama-3 Grounded):** {gen_text}"
        except Exception:
            return None
        return None

    @staticmethod
    def _build_traceability(
        structured_json: Dict[str, Any],
        operation_id: str,
        rules_applied: List[str],
        period_label: str,
        n_ref: Optional[int] = 32
    ) -> Dict[str, Any]:
        states = structured_json.get("states", [])
        ent_str = ", ".join(states) if states else "Nacional (32 entidades)"
        yr_src = structured_json.get("year_source") or "periodo_completo"
        n_str = str(n_ref) if n_ref is not None else "N/A"
        rules_str = ", ".join(rules_applied) if rules_applied else "RN-01..RN-06"
        footer = (
            f"\n\n🔎 **Trazabilidad**: Fuente=data.json (Corte: Chubb 2020–2024 / INEGI Censo 2020, VMRC 2020–2024 / ML 2024) "
            f"| Periodo={period_label} ({yr_src}) | Filtros=[Entidades: {ent_str}; n={n_str}] "
            f"| Operación={operation_id} (Reglas: {rules_str})"
        )
        return {
            "source": "data.json (Chubb Baseline 2020–2024 / INEGI Censo 2020 & VMRC 2020–2024 / Mercado Libre 2024)",
            "cutoff_date": "2024-12-31",
            "period": period_label,
            "year_source": yr_src,
            "filters": {"states": states, "n": n_ref},
            "operation_id": operation_id,
            "rules_applied": rules_applied,
            "footer": footer
        }

    @staticmethod
    def format_insufficient_kpi_response(structured_json: Dict[str, Any]) -> str:
        missing_kpis = structured_json.get("missing_kpis", [])
        states = structured_json.get("states", [])
        yr = structured_json.get("target_year")
        kpi_label = ", ".join(f"**{k}**" for k in missing_kpis) if missing_kpis else "**ventas, primas o rentabilidad**"
        scope_clause = f" para **{', '.join(states)}**" if states else ""
        yr_clause = f" en **{yr}**" if yr else ""
        return (
            f"🤖 **Asistente de análisis actuarial — Abstención por Datos No Disponibles (`insufficient_data_kpi`)**:\n"
            f"No cuento con datos suficientes en `data.json` para responder sobre {kpi_label}{scope_clause}{yr_clause}.\n\n"
            f"• **Qué NO incluye el modelo**: El conjunto de datos oficial no contiene registros de **ventas comerciales, primas emitidas o devengadas, rentabilidad financiera (`ROE`, utilidad, margen), índices técnicos sobre prima (`Loss Ratio` / `Combined Ratio`), número de pólizas vigentes ni frecuencia observada de reclamos**.\n"
            f"• **Por qué no se estima**: Conforme a la política de confiabilidad actuarial (Tolerancia Cero a alucinaciones `S0`), el asistente se abstiene de inventar cifras o de entregar la severidad del siniestro como sustituto de un indicador comercial o de rentabilidad.\n"
            f"• **Indicadores disponibles que sí puedes consultar**: Severidad unitaria estimada (`$ MXN` por siniestro), Costo Total de siniestros ocurridos (`$ MDP`), Índice Relativo (`Base 100`), evolución `2020–2024` y parque vehicular macro (`INEGI VMRC`)."
        )

    @staticmethod
    def format_unsupported_granularity_response(structured_json: Dict[str, Any]) -> str:
        terms = structured_json.get("unsupported_terms", [])
        g_types = structured_json.get("granularity_types", [])
        terms_label = ", ".join(f"**{t}**" for t in terms) if terms else "**nivel sub-estatal o sub-anual**"
        gran_desc = []
        if "sub_state" in g_types:
            gran_desc.append("desagregación municipal, por ciudad o código postal")
        if "sub_annual" in g_types:
            gran_desc.append("desagregación mensual, trimestral o diaria")
        gran_str = " ni ".join(gran_desc) if gran_desc else "granularidad inferior a Entidad × Año"
        return (
            f"🤖 **Asistente de análisis actuarial — Abstención por Granularidad No Soportada (`unsupported_granularity`)**:\n"
            f"No cuento con desagregación suficiente en `data.json` para consultar {terms_label} ({gran_str}).\n\n"
            f"• **Granularidad mínima disponible**: El modelo está estructurado exclusivamente por **Entidad Federativa (32 estados de México) × Año calendario (`2020` a `2024` y `Promedio 2020–2024`)**.\n"
            f"• **Recomendación verificable**: Solicita el análisis a nivel estatal y anual (por ejemplo, para la entidad federativa correspondiente entre `2020` y `2024`)."
        )

    def ask(self, user_query: str) -> str:
        return self.ask_with_metadata(user_query)["response"]

    def ask_with_metadata(self, user_query: str) -> Dict[str, Any]:
        structured_json = self.parser.parse_to_structured_json(user_query)

        try:
            self.parser.validate_structured_json(structured_json, self.canonical_states)
        except QueryValidationError as qe:
            trace = self._build_traceability(structured_json, "validate_structured_json", ["Schema-IR"], "N/A", None)
            resp = f"🤖 **Error de Validación de Consulta**: {qe}{trace['footer']}"
            return {"response": resp, "ir": structured_json, "structured_metrics": [], "traceability": trace}

        intent = structured_json["intent"]
        structured_metrics: List[Dict[str, Any]] = []

        if intent == "out_of_domain":
            trace = self._build_traceability(structured_json, "guardrail_out_of_domain", ["Guardrail-Dominio"], "N/A", None)
            body = """🤖 **Asistente de análisis actuarial**:
La consulta se encuentra fuera del ámbito actuarial del Dataset Actuarial de Severidad de Siniestros de Auto en México (Chubb Baseline 2020–2024).
Para mantener rigor metodológico sin alucinaciones, este asistente solo responde consultas sobre severidad ($ MXN), costo total (MDP), factores de riesgo vehicular e indicadores del reporte."""
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

        if intent == "insufficient_data_kpi":
            yr_lbl = str(structured_json["target_year"]) if structured_json.get("target_year") else "N/A"
            trace = self._build_traceability(structured_json, "abstencion_kpi_no_disponible", ["Guardrail-Confiabilidad", "RN-03"], yr_lbl, None)
            body = self.format_insufficient_kpi_response(structured_json)
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

        if intent == "unsupported_granularity":
            yr_lbl = str(structured_json["target_year"]) if structured_json.get("target_year") else "N/A"
            trace = self._build_traceability(structured_json, "abstencion_granularidad_no_soportada", ["Guardrail-Granularidad"], yr_lbl, None)
            body = self.format_unsupported_granularity_response(structured_json)
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

        if intent in ("temporal_out_of_range", "clarification_year"):
            trace = self._build_traceability(structured_json, f"guardrail_{intent}", ["RN-06"], "Fuera de rango / Ambiguo", None)
            body = f"🤖 **Asistente de análisis actuarial**:\n{structured_json.get('error_message')}"
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

        if intent in ("executive_multistate_summary", "executive_single_state_summary"):
            states = structured_json["states"]
            target_year = structured_json["target_year"]
            summary = self.engine.compute_executive_summary(states, target_year)
            self.memory.update_confirmed_context(states, target_year, intent)
            llm_narr = self._try_llm_executive_narrative(summary, user_query)
            body = self.format_executive_summary_response(summary, structured_json, llm_narrative=llm_narr)
            n_ref = summary["national_reference"]["n"]
            if summary["national_reference"]["value"] is not None:
                structured_metrics.append({
                    "metric_id": "referencia_nacional_severidad",
                    "entity": "Nacional",
                    "period": str(target_year),
                    "value": float(summary["national_reference"]["value"]),
                    "unit": "MXN",
                    "filters": {"estados": states, "anio": str(target_year), "n": n_ref},
                    "operation_id": "compute_executive_summary:RN-01",
                    "slot_keywords": ["referencia:"]
                })
            for r in summary["rows"]:
                if r["severidad"] is not None:
                    structured_metrics.append({
                        "metric_id": "severidad_estatal",
                        "entity": r["entidad"],
                        "period": str(target_year),
                        "value": float(r["severidad"]),
                        "unit": "MXN",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": r["n_nacional_severidad"]},
                        "operation_id": "compute_executive_summary:RN-01_RN-02",
                        "slot_keywords": [f"| {r['entidad']} |"]
                    })
                if r["indice"] is not None:
                    structured_metrics.extend([
                        {
                            "metric_id": "indice_relativo",
                            "entity": r["entidad"],
                            "period": str(target_year),
                            "value": float(r["indice"]),
                            "unit": "pts",
                            "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": n_ref},
                            "operation_id": "compute_executive_summary:RN-01",
                            "slot_keywords": []
                        },
                        {
                            "metric_id": "diff_vs_media_pct",
                            "entity": r["entidad"],
                            "period": str(target_year),
                            "value": abs(float(r["indice"]) - 100.0),
                            "unit": "%",
                            "filters": {"entidad": r["entidad"], "anio": str(target_year)},
                            "operation_id": "compute_executive_summary:RN-01",
                            "slot_keywords": []
                        }
                    ])
                if r.get("indice_2020") is not None:
                    structured_metrics.append({
                        "metric_id": "indice_relativo_2020",
                        "entity": r["entidad"],
                        "period": "2020",
                        "value": float(r["indice_2020"]),
                        "unit": "pts",
                        "filters": {"entidad": r["entidad"], "anio": "2020"},
                        "operation_id": "compute_executive_summary:RN-04",
                        "slot_keywords": []
                    })
                if r.get("var_severidad_pct") is not None:
                    structured_metrics.append({
                        "metric_id": "var_severidad_pct",
                        "entity": r["entidad"],
                        "period": f"2020->{target_year}",
                        "value": abs(float(r["var_severidad_pct"])),
                        "unit": "%",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year)},
                        "operation_id": "compute_executive_summary:RN-04",
                        "slot_keywords": []
                    })
                if r.get("delta_indice_pts") is not None:
                    structured_metrics.extend([
                        {
                            "metric_id": "delta_indice_pts",
                            "entity": r["entidad"],
                            "period": f"2020->{target_year}",
                            "value": float(r["delta_indice_pts"]),
                            "unit": "pts",
                            "filters": {"entidad": r["entidad"], "anio": str(target_year)},
                            "operation_id": "compute_executive_summary:RN-04",
                            "slot_keywords": []
                        },
                        {
                            "metric_id": "delta_indice_pts_abs",
                            "entity": r["entidad"],
                            "period": f"2020->{target_year}",
                            "value": abs(float(r["delta_indice_pts"])),
                            "unit": "pts",
                            "filters": {"entidad": r["entidad"], "anio": str(target_year)},
                            "operation_id": "compute_executive_summary:RN-04",
                            "slot_keywords": []
                        }
                    ])
                if r["costo_mdp"] is not None:
                    structured_metrics.append({
                        "metric_id": "costo_mdp",
                        "entity": r["entidad"],
                        "period": str(target_year),
                        "value": float(r["costo_mdp"]),
                        "unit": "MDP",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": r["n_nacional_mdp"]},
                        "operation_id": "compute_executive_summary:RN-03",
                        "slot_keywords": []
                    })
            if summary.get("selection_summary"):
                sel = summary["selection_summary"]
                if sel.get("brecha_severidad_abs") is not None:
                    structured_metrics.append({
                        "metric_id": "brecha_severidad_abs",
                        "entity": f"{sel['lider_severidad']} vs {sel['menor_severidad']}",
                        "period": str(target_year),
                        "value": float(sel["brecha_severidad_abs"]),
                        "unit": "MXN",
                        "filters": {"estados": states, "anio": str(target_year)},
                        "operation_id": "compute_executive_summary:Brecha",
                        "slot_keywords": []
                    })
                if sel.get("brecha_severidad_pct") is not None:
                    structured_metrics.append({
                        "metric_id": "brecha_severidad_pct",
                        "entity": f"{sel['lider_severidad']} vs {sel['menor_severidad']}",
                        "period": str(target_year),
                        "value": float(sel["brecha_severidad_pct"]),
                        "unit": "%",
                        "filters": {"estados": states, "anio": str(target_year)},
                        "operation_id": "compute_executive_summary:Brecha",
                        "slot_keywords": []
                    })
                if sel.get("brecha_mdp_abs") is not None:
                    structured_metrics.append({
                        "metric_id": "brecha_mdp_abs",
                        "entity": f"{sel['lider_mdp']} vs {sel['menor_mdp']}",
                        "period": str(target_year),
                        "value": float(sel["brecha_mdp_abs"]),
                        "unit": "MDP",
                        "filters": {"estados": states, "anio": str(target_year)},
                        "operation_id": "compute_executive_summary:BrechaMDP",
                        "slot_keywords": []
                    })
            trace = self._build_traceability(
                structured_json,
                "compute_executive_summary",
                ["RN-01", "RN-02", "RN-03", "RN-04", "RN-05", "RN-06"],
                str(target_year),
                n_ref
            )
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "three_findings":
            findings = self.engine.compute_three_key_findings()
            top5_names = [f"{s['entidad']} (${format_number(s['mdp'], 2)} MDP)" for s in findings['pareto_top5']]
            structured_metrics = [
                {
                    "metric_id": "pareto_top5_pct",
                    "entity": "Top 5 Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["pareto_pct"]),
                    "unit": "%",
                    "filters": {"top_k": 5, "n": 32},
                    "operation_id": "compute_three_key_findings:Pareto",
                    "slot_keywords": ["concentra el"]
                },
                {
                    "metric_id": "top5_mdp_sum",
                    "entity": "Top 5 Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["top5_mdp_sum"]),
                    "unit": "MDP",
                    "filters": {"top_k": 5, "n": 32},
                    "operation_id": "compute_three_key_findings:Pareto",
                    "slot_keywords": []
                },
                {
                    "metric_id": "total_national_mdp",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["total_national_mdp"]),
                    "unit": "MDP",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Pareto",
                    "slot_keywords": []
                },
                {
                    "metric_id": "ratio_max_min_severidad",
                    "entity": f"{findings['max_state']['entidad']} vs {findings['min_state']['entidad']}",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["ratio_max_min"]),
                    "unit": "x",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Dispersion",
                    "slot_keywords": ["brecha de severidad"]
                },
                {
                    "metric_id": "max_state_severidad",
                    "entity": findings["max_state"]["entidad"],
                    "period": "Promedio 2020–2024",
                    "value": float(findings["max_state"]["severidad"]),
                    "unit": "MXN",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Dispersion",
                    "slot_keywords": []
                },
                {
                    "metric_id": "max_state_idx",
                    "entity": findings["max_state"]["entidad"],
                    "period": "Promedio 2020–2024",
                    "value": float(findings["max_state"]["idx"]),
                    "unit": "pts",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Dispersion",
                    "slot_keywords": []
                },
                {
                    "metric_id": "min_state_severidad",
                    "entity": findings["min_state"]["entidad"],
                    "period": "Promedio 2020–2024",
                    "value": float(findings["min_state"]["severidad"]),
                    "unit": "MXN",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Dispersion",
                    "slot_keywords": []
                },
                {
                    "metric_id": "growth_leader_cagr_total",
                    "entity": findings["growth_leader"]["entidad"],
                    "period": "2020–2024",
                    "value": float(findings["growth_leader"]["cagr_total"]),
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Growth",
                    "slot_keywords": []
                },
                {
                    "metric_id": "growth_leader_cagr_anual",
                    "entity": findings["growth_leader"]["entidad"],
                    "period": "2020–2024",
                    "value": float(findings["growth_leader"]["cagr_anual"]),
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Growth",
                    "slot_keywords": []
                },
                {
                    "metric_id": "regression_r",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["regression"]["r"]),
                    "unit": "r",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Regression",
                    "slot_keywords": []
                },
                {
                    "metric_id": "regression_r2_pct",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(findings["regression"]["r2_pct"]),
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Regression",
                    "slot_keywords": []
                }
            ]
            for s in findings["pareto_top5"]:
                structured_metrics.append({
                    "metric_id": "pareto_state_mdp",
                    "entity": s["entidad"],
                    "period": "Promedio 2020–2024",
                    "value": float(s["mdp"]),
                    "unit": "MDP",
                    "filters": {"n": 32},
                    "operation_id": "compute_three_key_findings:Pareto",
                    "slot_keywords": []
                })
            trace = self._build_traceability(structured_json, "compute_three_key_findings", ["RN-01", "RN-03", "RN-04"], "Promedio 2020–2024", 32)
            body = f"""🤖 **Asistente de análisis actuarial — El reporte en 3 hallazgos clave**:

1. **Concentración Pareto del Costo Total (MDP)**:
   El Top 5 de entidades concentra el **{format_number(findings['pareto_pct'], 1)}% del costo nacional total en MDP** (${format_number(findings['top5_mdp_sum'], 2)} MDP de los ${format_number(findings['total_national_mdp'], 2)} MDP anuales). Encabezado por {', '.join(top5_names)}.

2. **Disparidad Geográfica y Crecimiento Acumulado**:
   Existe una brecha de severidad de aproximadamente **{format_number(findings['ratio_max_min'], 2)} veces ({format_number(findings['ratio_max_min'], 2)}x)** entre {findings['max_state']['entidad']} (${format_number(findings['max_state']['severidad'], 2)} MXN, índice {format_number(findings['max_state']['idx'], 1)} pts) y {findings['min_state']['entidad']} (${format_number(findings['min_state']['severidad'], 2)} MXN). {findings['growth_leader']['entidad']} lidera el incremento con **+{format_number(findings['growth_leader']['cagr_total'], 1)}% acumulado** (+{format_number(findings['growth_leader']['cagr_anual'], 1)}% anual compuesto).

3. **Asociación Estadística con Precios Vehiculares (r = +{format_number(findings['regression']['r'], 4, False)}, R² = {format_number(findings['regression']['r2_pct'], 2)}%)**:
   El precio comercial promedio del vehículo presenta la asociación más fuerte con la severidad. *Nota actuarial: La correlación estadística lineal macroestatal no demuestra causalidad directa única* sin evaluar microdatos de coberturas y pérdidas totales."""
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "top_rankings":
            ranks = self.engine.compute_severity_rankings(top_n=5)
            lines = ["🤖 **Asistente de análisis**: Top 5 Estados con Mayor Severidad Promedio:"]
            for r in ranks:
                lines.append(f"  {r['rank']}. **{r['entidad']}**: ${format_number(r['severidad'], 2)} MXN (Promedio 2020–2024)")
                structured_metrics.append({
                    "metric_id": f"ranking_top_{r['rank']}_severidad",
                    "entity": r["entidad"],
                    "period": "Promedio 2020–2024",
                    "value": float(r["severidad"]),
                    "unit": "MXN",
                    "filters": {"rank": r["rank"], "n": 32},
                    "operation_id": "compute_severity_rankings:RN-05",
                    "slot_keywords": [f"{r['rank']}. {r['entidad']}:"]
                })
            lines.append("• Fuente: Chubb Baseline (2020-2024) & INEGI VMRC")
            trace = self._build_traceability(structured_json, "compute_severity_rankings", ["RN-05", "RN-06"], "Promedio 2020–2024", 32)
            return {"response": "\n".join(lines) + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "multi_state_comparison":
            states = structured_json["states"]
            year = structured_json["target_year"]

            if structured_json.get("insufficient_entities") and len(states) == 1:
                st_name = states[0]
                m = self.engine.get_state_metrics(st_name, target_year=year)
                self.memory.update_confirmed_context([st_name], year, "single_state")
                dups = " y ".join(structured_json.get("duplicate_mentions", [st_name]))
                trace = self._build_traceability(structured_json, "multi_state_comparison_dedup_guard", ["RN-01", "RN-02", "RN-03"], m["periodo"], m["n_entidades_nacional"])
                body = (
                    f"🤖 **Asistente de análisis actuarial**:\n"
                    f"ℹ️ *Ambas menciones ({dups}) corresponden a **{st_name}**; indica otra entidad para comparar.*\n\n"
                    f"**Ficha de {m['entidad']} ({m['periodo']})**:\n"
                    f"• Severidad: **${format_number(m['severidad'], 2)} MXN**\n"
                    f"• Índice Relativo: **{format_number(m['indice_severidad'], 1)} pts** (Media de severidad de las entidades con dato = 100)\n"
                    f"• Categoría: **{m['categoria']}**\n"
                    f"• Costo Total: **${format_number(m['costo_mdp'], 2)} MDP**"
                )
                return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

            if len(states) < 2:
                states = ["Nuevo Leon", "Jalisco"]

            comp = self.engine.compute_multi_state_comparison(states, target_year=year)
            self.memory.update_confirmed_context(states, year, "multi_state_comparison")

            lines = [
                f"🤖 **Asistente de análisis actuarial — Comparativa Multivariada ({len(states)} Entidades)**:",
                f"• Periodo evaluado: **{comp['periodo']}**\n",
                "1. **Severidad Unitaria ($/Siniestro)**:"
            ]
            for st_m in comp["estados_metricas"]:
                lines.append(f"   • **{st_m['entidad']}**: ${format_number(st_m['severidad'], 2)} MXN (Índice: {format_number(st_m['indice_severidad'], 1)} pts, Nivel: **{st_m['categoria']}**)")
                structured_metrics.extend([
                    {
                        "metric_id": "severidad_estatal",
                        "entity": st_m["entidad"],
                        "period": comp["periodo"],
                        "value": float(st_m["severidad"]),
                        "unit": "MXN",
                        "filters": {"estados": states, "periodo": comp["periodo"], "n": 32},
                        "operation_id": "compute_multi_state_comparison:RN-01_RN-02",
                        "slot_keywords": [f"{st_m['entidad']}: $"]
                    },
                    {
                        "metric_id": "indice_relativo",
                        "entity": st_m["entidad"],
                        "period": comp["periodo"],
                        "value": float(st_m["indice_severidad"]),
                        "unit": "pts",
                        "filters": {"estados": states, "periodo": comp["periodo"], "n": 32},
                        "operation_id": "compute_multi_state_comparison:RN-01",
                        "slot_keywords": []
                    }
                ])

            lines.append(f"   • Brecha: **{comp['lider_severidad']}** supera a **{comp['menor_severidad']}** en **${format_number(comp['diferencia_absoluta'], 2)} MXN** (+{format_number(comp['diferencia_porcentual'], 1)}% tomando como base a {comp['menor_severidad']}).\n")
            structured_metrics.extend([
                {
                    "metric_id": "brecha_severidad_abs",
                    "entity": f"{comp['lider_severidad']} vs {comp['menor_severidad']}",
                    "period": comp["periodo"],
                    "value": float(comp["diferencia_absoluta"]),
                    "unit": "MXN",
                    "filters": {"estados": states, "periodo": comp["periodo"]},
                    "operation_id": "compute_multi_state_comparison:Brecha",
                    "slot_keywords": ["brecha:"]
                },
                {
                    "metric_id": "brecha_severidad_pct",
                    "entity": f"{comp['lider_severidad']} vs {comp['menor_severidad']}",
                    "period": comp["periodo"],
                    "value": float(comp["diferencia_porcentual"]),
                    "unit": "%",
                    "filters": {"estados": states, "periodo": comp["periodo"]},
                    "operation_id": "compute_multi_state_comparison:Brecha",
                    "slot_keywords": []
                }
            ])

            lines.append("2. **Costo Total en la Cartera (MDP)**:")
            for st_m in comp["estados_metricas"]:
                lines.append(f"   • **{st_m['entidad']}**: ${format_number(st_m['costo_mdp'], 2)} MDP")
                structured_metrics.append({
                    "metric_id": "costo_mdp",
                    "entity": st_m["entidad"],
                    "period": comp["periodo"],
                    "value": float(st_m["costo_mdp"]),
                    "unit": "MDP",
                    "filters": {"estados": states, "periodo": comp["periodo"]},
                    "operation_id": "compute_multi_state_comparison:RN-03",
                    "slot_keywords": []
                })

            lines.append("   • *Identidad actuarial*: Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000.")
            lines.append("   • *Aclaración de exposición*: Los vehículos registrados en circulación (INEGI VMRC) reflejan la escala macro, pero **no equivalen a la exposición asegurada** (número de pólizas vigentes).\n")

            lines.append("3. **Restricción de Causalidad**:")
            lines.append("   • La asociación lineal observada orienta el análisis, pero no demuestra causalidad directa entre las entidades comparadas.")

            trace = self._build_traceability(structured_json, "compute_multi_state_comparison", ["RN-01", "RN-02", "RN-03", "RN-06"], comp["periodo"], 32)
            return {"response": "\n".join(lines) + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "single_state":
            states = structured_json["states"]
            year = structured_json["target_year"]
            st_name = states[0] if states else "Nuevo Leon"

            m = self.engine.get_state_metrics(st_name, target_year=year)
            self.memory.update_confirmed_context([st_name], year, "single_state")
            cat_display = "Crítica" if m['categoria'] in ['Critica', 'Crítica'] else m['categoria']

            structured_metrics = [
                {
                    "metric_id": "severidad_estatal",
                    "entity": m["entidad"],
                    "period": m["periodo"],
                    "value": float(m["severidad"]),
                    "unit": "MXN",
                    "filters": {"entidad": m["entidad"], "periodo": m["periodo"], "n": m["n_entidades_nacional"]},
                    "operation_id": "get_state_metrics:RN-01_RN-02",
                    "slot_keywords": ["severidad:"]
                },
                {
                    "metric_id": "indice_relativo",
                    "entity": m["entidad"],
                    "period": m["periodo"],
                    "value": float(m["indice_severidad"]),
                    "unit": "pts",
                    "filters": {"entidad": m["entidad"], "periodo": m["periodo"], "n": m["n_entidades_nacional"]},
                    "operation_id": "get_state_metrics:RN-01",
                    "slot_keywords": ["indice relativo:"]
                },
                {
                    "metric_id": "costo_mdp",
                    "entity": m["entidad"],
                    "period": m["periodo"],
                    "value": float(m["costo_mdp"]),
                    "unit": "MDP",
                    "filters": {"entidad": m["entidad"], "periodo": m["periodo"], "n": m["n_entidades_nacional"]},
                    "operation_id": "get_state_metrics:RN-03",
                    "slot_keywords": ["costo anual medio:"]
                },
                {
                    "metric_id": "cagr_acumulado",
                    "entity": m["entidad"],
                    "period": "2020–2024",
                    "value": float(m["cagr_acumulado"]),
                    "unit": "%",
                    "filters": {"entidad": m["entidad"]},
                    "operation_id": "get_state_metrics:RN-04",
                    "slot_keywords": ["crecimiento acumulado:"]
                }
            ]
            trace = self._build_traceability(structured_json, "get_state_metrics", ["RN-01", "RN-02", "RN-03", "RN-06"], m["periodo"], m["n_entidades_nacional"])
            body = f"""🤖 **Asistente de análisis**:
  • Estado: **{m['entidad']}**
  • Severidad: **${format_number(m['severidad'], 2)} MXN** por siniestro
  • Periodo: {m['periodo']}
  • Nivel de Riesgo: **{cat_display}**
  • Índice Relativo: **{format_number(m['indice_severidad'], 1)} pts** (Base Nacional = 100, n = {m['n_entidades_nacional']})
  • Costo Anual Medio: **${format_number(m['costo_mdp'], 2)} MDP**
  • Parque Registrado: **{m['automoviles_registrados']:,d} autos** (INEGI VMRC, macro no asegurados)
  • Crecimiento Acumulado: **+{format_number(m['cagr_acumulado'], 1)}%**
  • Fuente: Dataset Actuarial Oficial (Chubb / INEGI VMRC)"""
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "pareto_breakdown":
            pareto = self.engine.compute_pareto_breakdown(top_k=5)
            lines = [
                f"🤖 **Asistente de análisis actuarial — Concentración Pareto de Costos (MDP)**:",
                f"• **Concentración Top 5**: Las 5 entidades con mayor volumen concentran el **{format_number(pareto['pct_k'], 1)}%** del costo total nacional en MDP (${format_number(pareto['sum_k_mdp'], 2)} MDP de los ${format_number(pareto['total_national_mdp'], 2)} MDP anuales).",
                "• **Ranking de Volumen en MDP**:"
            ]
            structured_metrics.extend([
                {
                    "metric_id": "pareto_top5_pct",
                    "entity": "Top 5 Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(pareto["pct_k"]),
                    "unit": "%",
                    "filters": {"top_k": 5, "n": 32},
                    "operation_id": "compute_pareto_breakdown:RN-03",
                    "slot_keywords": ["concentracion top 5:"]
                },
                {
                    "metric_id": "pareto_sum_k_mdp",
                    "entity": "Top 5 Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(pareto["sum_k_mdp"]),
                    "unit": "MDP",
                    "filters": {"top_k": 5, "n": 32},
                    "operation_id": "compute_pareto_breakdown:RN-03",
                    "slot_keywords": []
                },
                {
                    "metric_id": "total_national_mdp",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": float(pareto["total_national_mdp"]),
                    "unit": "MDP",
                    "filters": {"n": 32},
                    "operation_id": "compute_pareto_breakdown:RN-03",
                    "slot_keywords": []
                }
            ])
            for s in pareto["top_states"]:
                lines.append(f"  {s['rank']}. {s['entidad']}: ${format_number(s['mdp'], 2)} MDP ({format_number(s['pct_nacional'], 1)}%)")
                structured_metrics.extend([
                    {
                        "metric_id": "pareto_state_mdp",
                        "entity": s["entidad"],
                        "period": "Promedio 2020–2024",
                        "value": float(s["mdp"]),
                        "unit": "MDP",
                        "filters": {"rank": s["rank"], "n": 32},
                        "operation_id": "compute_pareto_breakdown:RN-03",
                        "slot_keywords": []
                    },
                    {
                        "metric_id": "pareto_state_pct",
                        "entity": s["entidad"],
                        "period": "Promedio 2020–2024",
                        "value": float(s["pct_nacional"]),
                        "unit": "%",
                        "filters": {"rank": s["rank"], "n": 32},
                        "operation_id": "compute_pareto_breakdown:RN-03",
                        "slot_keywords": []
                    }
                ])
            lines.append("• **Distinción Actuarial**: Este diagrama mide volumen agregado de pérdida (Costo Total en MDP), no severidad unitaria individual.")
            trace = self._build_traceability(structured_json, "compute_pareto_breakdown", ["RN-03", "RN-05"], "Promedio 2020–2024", 32)
            return {"response": "\n".join(lines) + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "growth_cagr":
            growth = self.engine.compute_growth_rankings(top_n=3)
            lines = [
                "🤖 **Asistente de análisis actuarial — Crecimiento y Tendencia Temporal (2020–2024)**:",
                "1. **Líder Nacional en Crecimiento Acumulado**:"
            ]
            for s in growth["leaders"]:
                lines.append(f"   • **{s['entidad']}**: Crecimiento de **+{format_number(s['cagr_acumulado'], 1)}%** acumulado (tasa anual compuesta CAGR de **+{format_number(s['cagr_anual'], 1)}%** anual).")
                structured_metrics.extend([
                    {
                        "metric_id": "cagr_acumulado",
                        "entity": s["entidad"],
                        "period": "2020–2024",
                        "value": float(s["cagr_acumulado"]),
                        "unit": "%",
                        "filters": {"entidad": s["entidad"], "n": 32},
                        "operation_id": "compute_growth_rankings:RN-04",
                        "slot_keywords": [f"{s['entidad']}: crecimiento de"]
                    },
                    {
                        "metric_id": "cagr_anual",
                        "entity": s["entidad"],
                        "period": "2020–2024",
                        "value": float(s["cagr_anual"]),
                        "unit": "%",
                        "filters": {"entidad": s["entidad"], "n": 32},
                        "operation_id": "compute_growth_rankings:RN-04",
                        "slot_keywords": []
                    }
                ])
            structured_metrics.extend([
                {
                    "metric_id": "nacional_sev_2020",
                    "entity": "Nacional",
                    "period": "2020",
                    "value": float(growth["nacional"]["sev_2020"]),
                    "unit": "MXN",
                    "filters": {"n": 32},
                    "operation_id": "compute_growth_rankings:RN-01",
                    "slot_keywords": []
                },
                {
                    "metric_id": "nacional_sev_2024",
                    "entity": "Nacional",
                    "period": "2024",
                    "value": float(growth["nacional"]["sev_2024"]),
                    "unit": "MXN",
                    "filters": {"n": 32},
                    "operation_id": "compute_growth_rankings:RN-01",
                    "slot_keywords": []
                },
                {
                    "metric_id": "nacional_cagr_total",
                    "entity": "Nacional",
                    "period": "2020–2024",
                    "value": float(growth["nacional"]["cagr_total"]),
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "compute_growth_rankings:RN-04",
                    "slot_keywords": []
                },
                {
                    "metric_id": "nacional_cagr_anual",
                    "entity": "Nacional",
                    "period": "2020–2024",
                    "value": float(growth["nacional"]["cagr_anual"]),
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "compute_growth_rankings:RN-04",
                    "slot_keywords": []
                }
            ])
            lines.append("2. **Media de severidad de las entidades con dato**:")
            lines.append(f"   • Creció de ${format_number(growth['nacional']['sev_2020'], 2)} MXN en 2020 a ${format_number(growth['nacional']['sev_2024'], 2)} MXN en 2024 (+{format_number(growth['nacional']['cagr_total'], 1)}% acumulado, CAGR +{format_number(growth['nacional']['cagr_anual'], 1)}% anual).")
            lines.append("3. **Interpretación Actuarial**: Refleja presiones inflacionarias en autopartes, sofisticación tecnológica de vehículos y costos médicos.")
            trace = self._build_traceability(structured_json, "compute_growth_rankings", ["RN-04", "RN-06"], "2020–2024", 32)
            return {"response": "\n".join(lines) + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "regression_drivers":
            stats = self.data["scatter_stats"]
            r_val = float(stats["r_pearson"])
            r2_val = float(stats["r2_score"]) * 100.0
            structured_metrics = [
                {
                    "metric_id": "r_pearson_precio_auto",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": r_val,
                    "unit": "r",
                    "filters": {"n": 32},
                    "operation_id": "regression_drivers:OLS",
                    "slot_keywords": ["precio comercial promedio del vehiculo"]
                },
                {
                    "metric_id": "r2_pct_precio_auto",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": r2_val,
                    "unit": "%",
                    "filters": {"n": 32},
                    "operation_id": "regression_drivers:OLS",
                    "slot_keywords": []
                },
                {
                    "metric_id": "r_pearson_motorizacion",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": 0.7648,
                    "unit": "r",
                    "filters": {"n": 32},
                    "operation_id": "regression_drivers:OLS",
                    "slot_keywords": []
                },
                {
                    "metric_id": "r_pearson_parque",
                    "entity": "Nacional",
                    "period": "Promedio 2020–2024",
                    "value": 0.3621,
                    "unit": "r",
                    "filters": {"n": 32},
                    "operation_id": "regression_drivers:OLS",
                    "slot_keywords": []
                }
            ]
            trace = self._build_traceability(structured_json, "regression_drivers", ["OLS-Scatter", "Guardrail-Causalidad"], "Promedio 2020–2024", 32)
            body = f"""🤖 **Asistente de análisis actuarial — Asociación Estadística de Variables**:
De acuerdo con el análisis macroestatal (Promedio 2020–2024), las variables presentan los siguientes grados de asociación estadística lineal con la severidad:
1. **Precio Comercial Promedio del Vehículo (Mercado Libre)**: r = +{format_number(r_val, 4, False)} | R² = {format_number(r2_val, 2)}% (p < 0.0001)
2. **Tasa de Motorización (INEGI VMRC)**: r = +0.7648 (Autos registrados por cada 1,000 hab)
3. **Volumen del Parque Vehicular Registrado**: r = +0.3621
⚠️ *Nota Metodológica y Guardrail*: Describe fuerza de **asociación estadística** lineal, pero **no implica causalidad** directa ni demuestra que los autos caros sean la causa única de la severidad. La severidad real depende de coberturas, pérdida total y mano de obra."""
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": structured_metrics, "traceability": trace}

        if intent == "glossary_units":
            trace = self._build_traceability(structured_json, "format_business_rules_response", ["RN-01", "RN-02", "RN-03", "RN-04", "RN-05", "RN-06"], "2020–2024", 32)
            body = self.format_business_rules_response(user_query)
            return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}

        trace = self._build_traceability(structured_json, "fallback_help", ["RN-01..RN-06"], "2020–2024", 32)
        body = """🤖 **Asistente de análisis actuarial**:
  No reconocí esa consulta con suficiente certeza dentro del dataset actuarial.
  Opciones recomendadas:
  • '¿Cuál es la severidad de Nuevo León?'
  • 'Compara Jalisco, Nuevo León, CDMX y Puebla'
  • 'Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023'
  • 'Tres hallazgos clave'
  • 'Concentración de costos Pareto'"""
        return {"response": body + trace["footer"], "ir": structured_json, "structured_metrics": [], "traceability": trace}
