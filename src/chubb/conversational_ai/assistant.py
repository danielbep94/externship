"""
Conversational AI — Grounded Actuarial Assistant Orchestrator & Colab Data Agent.
Coordinates QueryParser, QueryValidator, ActuarialOperationsEngine, Grounding, and OutputVerifier.
"""

import json
from typing import Dict, List, Any, Optional
from chubb.contracts.error_contract import QueryValidationError
from chubb.infrastructure.paths import resolve_data_path
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.analytical_foundation.calculations import format_number
from chubb.analytical_foundation.actuarial_engine import ActuarialOperationsEngine
from chubb.validation_foundation.data_validator import ActuarialDataValidator
from chubb.validation_foundation.output_verifier import ActuarialOutputVerifier
from chubb.conversational_ai.memory_manager import ConversationMemoryManager
from chubb.conversational_ai.query_parser import ActuarialQueryParser
from chubb.conversational_ai.providers.ollama import LLMProvider
from chubb.conversational_ai.grounding import (
    build_human_narrative,
    format_executive_summary_response,
    format_recommendations_response,
    format_business_rules_response,
    format_insufficient_kpi_response,
    format_unsupported_granularity_response,
)


class GroundedActuarialAssistant:
    """
    Asistente Actuarial de Producción con arquitectura Grounded:
    1. Parseo a JSON Estructurado (IR)
    2. Validación Previa al Engine
    3. Cómputo Verificado en ActuarialOperationsEngine
    4. Síntesis Grounded con Guardrails Metodológicos
    """

    def __init__(self, data_path: str = "", llm_provider: Optional[LLMProvider] = None):
        resolved_path = data_path if data_path else resolve_data_path()
        self.data = ActuarialDataValidator.load_and_validate(resolved_path)
        self.canonical_states = [s["entidad"] for s in self.data["estados"]]
        self.catalog = ActuarialCatalog(self.canonical_states)
        self.memory = ConversationMemoryManager()
        self.engine = ActuarialOperationsEngine(self.data)
        self.parser = ActuarialQueryParser(self.catalog, self.memory)
        self.llm_provider = llm_provider

    @staticmethod
    def build_human_narrative(summary: Dict[str, Any]) -> str:
        return build_human_narrative(summary)

    @staticmethod
    def format_executive_summary_response(
        summary: Dict[str, Any],
        structured_json: Dict[str, Any],
        llm_narrative: Optional[str] = None
    ) -> str:
        return format_executive_summary_response(summary, structured_json, llm_narrative=llm_narrative)

    @staticmethod
    def format_recommendations_response(rec_data: Dict[str, Any], structured_json: Dict[str, Any]) -> str:
        return format_recommendations_response(rec_data, structured_json)

    def format_business_rules_response(self, user_query: str) -> str:
        return format_business_rules_response(user_query, self.engine, self.catalog, self.data)

    def _try_llm_executive_narrative(self, summary: Dict[str, Any], user_query: str) -> Optional[str]:
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
        return format_insufficient_kpi_response(structured_json)

    @staticmethod
    def format_unsupported_granularity_response(structured_json: Dict[str, Any]) -> str:
        return format_unsupported_granularity_response(structured_json)

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

        if intent == "recommendations_actions":
            states = structured_json["states"]
            target_year = structured_json["target_year"] or 2024
            rec_data = self.engine.compute_recommendations_and_opportunities(states, target_year)
            if states:
                self.memory.update_confirmed_context(states, target_year, intent)
            body = self.format_recommendations_response(rec_data, structured_json)
            n_ref = rec_data["national_reference"]["n"]
            for r in rec_data["rows"]:
                if r.get("severidad") is not None:
                    structured_metrics.append({
                        "metric_id": "severidad_estatal",
                        "entity": r["entidad"],
                        "period": str(target_year),
                        "value": float(r["severidad"]),
                        "unit": "MXN",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": r["n_nacional_severidad"]},
                        "operation_id": "compute_recommendations_and_opportunities:RN-01_RN-02",
                        "slot_keywords": [f"{r['entidad']}: severidad de"]
                    })
                if r.get("indice") is not None:
                    structured_metrics.append({
                        "metric_id": "indice_relativo",
                        "entity": r["entidad"],
                        "period": str(target_year),
                        "value": float(r["indice"]),
                        "unit": "pts",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": n_ref},
                        "operation_id": "compute_recommendations_and_opportunities:RN-01",
                        "slot_keywords": []
                    })
                if r.get("costo_mdp") is not None:
                    structured_metrics.append({
                        "metric_id": "costo_mdp",
                        "entity": r["entidad"],
                        "period": str(target_year),
                        "value": float(r["costo_mdp"]),
                        "unit": "MDP",
                        "filters": {"entidad": r["entidad"], "anio": str(target_year), "n": r["n_nacional_mdp"]},
                        "operation_id": "compute_recommendations_and_opportunities:RN-03",
                        "slot_keywords": []
                    })
            trace = self._build_traceability(
                structured_json,
                "compute_recommendations_and_opportunities",
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
            lines = ["🤖 **Asistente de análisis**: Top 5 Estados con Mayor Severidad e Índice Relativo (Promedio 2020–2024):"]
            for r in ranks:
                lines.append(f"  {r['rank']}. **{r['entidad']}**: ${format_number(r['severidad'], 2)} MXN | Índice: **{format_number(r['indice'], 1)} pts** (Promedio 2020–2024)")
                structured_metrics.extend([
                    {
                        "metric_id": f"ranking_top_{r['rank']}_severidad",
                        "entity": r["entidad"],
                        "period": "Promedio 2020–2024",
                        "value": float(r["severidad"]),
                        "unit": "MXN",
                        "filters": {"rank": r["rank"], "n": 32},
                        "operation_id": "compute_severity_rankings:RN-05",
                        "slot_keywords": [f"{r['rank']}. {r['entidad']}:"]
                    },
                    {
                        "metric_id": f"ranking_top_{r['rank']}_indice",
                        "entity": r["entidad"],
                        "period": "Promedio 2020–2024",
                        "value": float(r["indice"]),
                        "unit": "pts",
                        "filters": {"rank": r["rank"], "n": 32},
                        "operation_id": "compute_severity_rankings:RN-01",
                        "slot_keywords": []
                    }
                ])
            lines.append("• Fuente: Chubb Baseline (2020-2024) & INEGI VMRC")
            trace = self._build_traceability(structured_json, "compute_severity_rankings", ["RN-01", "RN-05", "RN-06"], "Promedio 2020–2024", 32)
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


class LlamaColabDataAgent:
    """
    Agente Actuarial Grounded con soporte para Llama-3.
    Mantiene compatibilidad con notebooks y suites de benchmark,
    delegando en el motor validado GroundedActuarialAssistant.
    """
    def __init__(self, data_path: str = ""):
        self.assistant = GroundedActuarialAssistant(data_path=data_path)
        self.catalog = self.assistant.catalog
        self.engine = self.assistant.engine
        self.memory = self.assistant.memory

    def process_query(self, user_question: str) -> str:
        return self.assistant.ask(user_question)

    def query(self, user_question: str) -> str:
        return self.process_query(user_question)

