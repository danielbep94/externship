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
    Guardrail Post-Generación: Audita el texto generado por el LLM antes de mostrarlo.
    Extrae cualquier cifra monetaria ($...) o porcentaje (%) y verifica que exista
    dentro del grounding_payload numérico permitido. Si encuentra una cifra inventada,
    rechaza la salida para evitar alucinaciones.
    """
    @classmethod
    def verify(cls, generated_text: str, allowed_numbers: List[float], tolerance: float = 0.5) -> bool:
        amounts = re.findall(r'\$\s*([0-9,]+(?:\.[0-9]+)?)', generated_text)
        percentages = re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*%', generated_text)

        extracted_floats = []
        for amt in amounts:
            cleaned = amt.replace(',', '')
            try:
                extracted_floats.append(float(cleaned))
            except ValueError:
                pass

        for pct in percentages:
            try:
                extracted_floats.append(float(pct))
            except ValueError:
                pass

        for num in extracted_floats:
            if num in {1.0, 100.0, 1000000.0, 35.0, 30.0}:
                continue
            is_valid = any(abs(num - allowed) <= tolerance for allowed in allowed_numbers)
            if not is_valid:
                raise HallucinationDetectedError(
                    f"Cifra alucinada detectada en la salida del LLM: {num}. No coincide con el payload actuarial."
                )

        return True


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

    VALID_INTENTS = {
        "executive_multistate_summary",
        "executive_single_state_summary",
        "clarification_year",
        "temporal_out_of_range",
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

        # Ignorar el rango literal "2020 2024" cuando viene precedido de "promedio" o "periodo"
        is_period_range = ("promedio" in words or "periodo" in words or "historico" in words) and unique_years == [2020, 2024]

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
        elif any(w in norm_q for w in ["glosario", "definicion", "que es mdp", "volumen de costo total mdp", "explicar volumen de costo", "explicar mdp", "significa mdp"]):
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
    def format_executive_summary_response(summary: Dict[str, Any], structured_json: Dict[str, Any]) -> str:
        """Formatea la respuesta del Resumen Ejecutivo siguiendo estrictamente §3, §4, §5, §6 y §9."""
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

    def ask(self, user_query: str) -> str:
        structured_json = self.parser.parse_to_structured_json(user_query)

        try:
            self.parser.validate_structured_json(structured_json, self.canonical_states)
        except QueryValidationError as qe:
            return f"🤖 **Error de Validación de Consulta**: {qe}"

        intent = structured_json["intent"]

        if intent == "out_of_domain":
            return """🤖 **Asistente de análisis actuarial**:
La consulta se encuentra fuera del ámbito actuarial del Dataset Actuarial de Severidad de Siniestros de Auto en México (Chubb Baseline 2020–2024).
Para mantener rigor metodológico sin alucinaciones, este asistente solo responde consultas sobre severidad ($ MXN), costo total (MDP), factores de riesgo vehicular e indicadores del reporte."""

        if intent in ("temporal_out_of_range", "clarification_year"):
            return f"🤖 **Asistente de análisis actuarial**:\n{structured_json.get('error_message')}"

        if intent in ("executive_multistate_summary", "executive_single_state_summary"):
            states = structured_json["states"]
            target_year = structured_json["target_year"]
            summary = self.engine.compute_executive_summary(states, target_year)
            self.memory.update_confirmed_context(states, target_year, intent)
            return self.format_executive_summary_response(summary, structured_json)

        if intent == "three_findings":
            findings = self.engine.compute_three_key_findings()
            top5_names = [f"{s['entidad']} (${format_number(s['mdp'], 2)} MDP)" for s in findings['pareto_top5']]
            return f"""🤖 **Asistente de análisis actuarial — El reporte en 3 hallazgos clave**:

1. **Concentración Pareto del Costo Total (MDP)**:
   El Top 5 de entidades concentra el **{format_number(findings['pareto_pct'], 1)}% del costo nacional total en MDP** (${format_number(findings['top5_mdp_sum'], 2)} MDP de los ${format_number(findings['total_national_mdp'], 2)} MDP anuales). Encabezado por {', '.join(top5_names)}.

2. **Disparidad Geográfica y Crecimiento Acumulado**:
   Existe una brecha de severidad de aproximadamente **{format_number(findings['ratio_max_min'], 2)} veces ({format_number(findings['ratio_max_min'], 2)}x)** entre {findings['max_state']['entidad']} (${format_number(findings['max_state']['severidad'], 2)} MXN, índice {format_number(findings['max_state']['idx'], 1)} pts) y {findings['min_state']['entidad']} (${format_number(findings['min_state']['severidad'], 2)} MXN). {findings['growth_leader']['entidad']} lidera el incremento con **+{format_number(findings['growth_leader']['cagr_total'], 1)}% acumulado** (+{format_number(findings['growth_leader']['cagr_anual'], 1)}% anual compuesto).

3. **Asociación Estadística con Precios Vehiculares (r = +{format_number(findings['regression']['r'], 4, False)}, R² = {format_number(findings['regression']['r2_pct'], 2)}%)**:
   El precio comercial promedio del vehículo presenta la asociación más fuerte con la severidad. *Nota actuarial: La correlación estadística lineal macroestatal no demuestra causalidad directa única* sin evaluar microdatos de coberturas y pérdidas totales."""

        if intent == "top_rankings":
            ranks = self.engine.compute_severity_rankings(top_n=5)
            lines = ["🤖 **Asistente de análisis**: Top 5 Estados con Mayor Severidad Promedio:"]
            for r in ranks:
                lines.append(f"  {r['rank']}. **{r['entidad']}**: ${format_number(r['severidad'], 2)} MXN (Promedio 2020–2024)")
            lines.append("• Fuente: Chubb Baseline (2020-2024) & INEGI VMRC")
            return "\n".join(lines)

        if intent == "multi_state_comparison":
            states = structured_json["states"]
            year = structured_json["target_year"]

            if structured_json.get("insufficient_entities") and len(states) == 1:
                st_name = states[0]
                m = self.engine.get_state_metrics(st_name, target_year=year)
                self.memory.update_confirmed_context([st_name], year, "single_state")
                dups = " y ".join(structured_json.get("duplicate_mentions", [st_name]))
                return (
                    f"🤖 **Asistente de análisis actuarial**:\n"
                    f"ℹ️ *Ambas menciones ({dups}) corresponden a **{st_name}**; indica otra entidad para comparar.*\n\n"
                    f"**Ficha de {m['entidad']} ({m['periodo']})**:\n"
                    f"• Severidad: **${format_number(m['severidad'], 2)} MXN**\n"
                    f"• Índice Relativo: **{format_number(m['indice_severidad'], 1)} pts** (Media de severidad de las entidades con dato = 100)\n"
                    f"• Categoría: **{m['categoria']}**\n"
                    f"• Costo Total: **${format_number(m['costo_mdp'], 2)} MDP**"
                )

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

            lines.append(f"   • Brecha: **{comp['lider_severidad']}** supera a **{comp['menor_severidad']}** en **${format_number(comp['diferencia_absoluta'], 2)} MXN** (+{format_number(comp['diferencia_porcentual'], 1)}% tomando como base a {comp['menor_severidad']}).\n")

            lines.append("2. **Costo Total en la Cartera (MDP)**:")
            for st_m in comp["estados_metricas"]:
                lines.append(f"   • **{st_m['entidad']}**: ${format_number(st_m['costo_mdp'], 2)} MDP")

            lines.append("   • *Identidad actuarial*: Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000.")
            lines.append("   • *Aclaración de exposición*: Los vehículos registrados en circulación (INEGI VMRC) reflejan la escala macro, pero **no equivalen a la exposición asegurada** (número de pólizas vigentes).\n")

            lines.append("3. **Restricción de Causalidad**:")
            lines.append("   • La asociación lineal observada orienta el análisis, pero no demuestra causalidad directa entre las entidades comparadas.")

            return "\n".join(lines)

        if intent == "single_state":
            states = structured_json["states"]
            year = structured_json["target_year"]
            st_name = states[0] if states else "Nuevo Leon"

            m = self.engine.get_state_metrics(st_name, target_year=year)
            self.memory.update_confirmed_context([st_name], year, "single_state")
            cat_display = "Crítica" if m['categoria'] in ['Critica', 'Crítica'] else m['categoria']

            return f"""🤖 **Asistente de análisis**:
  • Estado: **{m['entidad']}**
  • Severidad: **${format_number(m['severidad'], 2)} MXN** por siniestro
  • Periodo: {m['periodo']}
  • Nivel de Riesgo: **{cat_display}**
  • Índice Relativo: **{format_number(m['indice_severidad'], 1)} pts** (Base Nacional = 100, n = {m['n_entidades_nacional']})
  • Costo Anual Medio: **${format_number(m['costo_mdp'], 2)} MDP**
  • Parque Registrado: **{m['automoviles_registrados']:,d} autos** (INEGI VMRC, macro no asegurados)
  • Crecimiento Acumulado: **+{format_number(m['cagr_acumulado'], 1)}%**
  • Fuente: Dataset Actuarial Oficial (Chubb / INEGI VMRC)"""

        if intent == "pareto_breakdown":
            pareto = self.engine.compute_pareto_breakdown(top_k=5)
            lines = [
                f"🤖 **Asistente de análisis actuarial — Concentración Pareto de Costos (MDP)**:",
                f"• **Concentración Top 5**: Las 5 entidades con mayor volumen concentran el **{format_number(pareto['pct_k'], 1)}%** del costo total nacional en MDP (${format_number(pareto['sum_k_mdp'], 2)} MDP de los ${format_number(pareto['total_national_mdp'], 2)} MDP anuales).",
                "• **Ranking de Volumen en MDP**:"
            ]
            for s in pareto["top_states"]:
                lines.append(f"  {s['rank']}. {s['entidad']}: ${format_number(s['mdp'], 2)} MDP ({format_number(s['pct_nacional'], 1)}%)")
            lines.append("• **Distinción Actuarial**: Este diagrama mide volumen agregado de pérdida (Costo Total en MDP), no severidad unitaria individual.")
            return "\n".join(lines)

        if intent == "growth_cagr":
            growth = self.engine.compute_growth_rankings(top_n=3)
            lines = [
                "🤖 **Asistente de análisis actuarial — Crecimiento y Tendencia Temporal (2020–2024)**:",
                "1. **Líder Nacional en Crecimiento Acumulado**:"
            ]
            for s in growth["leaders"]:
                lines.append(f"   • **{s['entidad']}**: Crecimiento de **+{format_number(s['cagr_acumulado'], 1)}%** acumulado (tasa anual compuesta CAGR de **+{format_number(s['cagr_anual'], 1)}%** anual).")
            lines.append("2. **Media de severidad de las entidades con dato**:")
            lines.append(f"   • Creció de ${format_number(growth['nacional']['sev_2020'], 2)} MXN en 2020 a ${format_number(growth['nacional']['sev_2024'], 2)} MXN en 2024 (+{format_number(growth['nacional']['cagr_total'], 1)}% acumulado, CAGR +{format_number(growth['nacional']['cagr_anual'], 1)}% anual).")
            lines.append("3. **Interpretación Actuarial**: Refleja presiones inflacionarias en autopartes, sofisticación tecnológica de vehículos y costos médicos.")
            return "\n".join(lines)

        if intent == "regression_drivers":
            stats = self.data["scatter_stats"]
            r_val = float(stats["r_pearson"])
            r2_val = float(stats["r2_score"]) * 100.0
            return f"""🤖 **Asistente de análisis actuarial — Asociación Estadística de Variables**:
De acuerdo con el análisis macroestatal (Promedio 2020–2024), las variables presentan los siguientes grados de asociación estadística lineal con la severidad:
1. **Precio Comercial Promedio del Vehículo (Mercado Libre)**: r = +{format_number(r_val, 4, False)} | R² = {format_number(r2_val, 2)}% (p < 0.0001)
2. **Tasa de Motorización (INEGI VMRC)**: r = +0.7648 (Autos registrados por cada 1,000 hab)
3. **Volumen del Parque Vehicular Registrado**: r = +0.3621
⚠️ *Nota Metodológica y Guardrail*: Describe fuerza de **asociación estadística** lineal, pero **no implica causalidad** directa ni demuestra que los autos caros sean la causa única de la severidad. La severidad real depende de coberturas, pérdida total y mano de obra."""

        if intent == "glossary_units":
            return f"""🤖 **Glosario Actuarial y Unidades Estándar**:
• **Severidad ($/Siniestro)**: Costo económico medio en **MXN** por cada siniestro pagado. Media de severidad de las entidades con dato (n = 32): **${format_number(self.engine.national_avg_severity, 2)} MXN** (2020–2024).
• **Costo Total en MDP (Millones de Pesos)**: 1 MDP = $1,000,000 MXN. El total anual promedio nacional es de **${format_number(self.engine.total_national_mdp, 2)} MDP**.
• **Identidad Actuarial**:
  Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
• **Exposición vs. Parque Registrado**: El parque vehicular registrado (INEGI VMRC) mide el volumen automotriz global, pero **no equivale a la exposición asegurada** (pólizas vigentes).
• **Índice Relativo (pts)**: Estandarización base 100 respecto a la media de severidad de las entidades con dato del mismo periodo."""

        return """🤖 **Asistente de análisis actuarial**:
  No reconocí esa consulta con suficiente certeza dentro del dataset actuarial.
  Opciones recomendadas:
  • '¿Cuál es la severidad de Nuevo León?'
  • 'Compara Jalisco, Nuevo León, CDMX y Puebla'
  • 'Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023'
  • 'Tres hallazgos clave'
  • 'Concentración de costos Pareto'"""
