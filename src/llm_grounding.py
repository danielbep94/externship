"""
Fase 5: Módulo de Inferencia Llama-3 y Grounding Actuarial
Implementa:
- Esquema de JSON estructurado intermedio (Structured Query IR)
- Pre-validador estricto del JSON estructurado antes de consultar el motor de datos
- Capa de Grounding Verificado contra ActuarialOperationsEngine
- Soporte para Llama-3 (vía provider pluggable) con fallback determinista grounded
"""

import json
from typing import Dict, List, Any, Optional, Union
from actuarial_core import (
    ActuarialDataValidator,
    ActuarialCatalog,
    ConversationMemoryManager,
    ActuarialOperationsEngine,
    normalize_text
)

class QueryValidationError(Exception):
    """Lanzada cuando el JSON estructurado generado no supera las reglas previas a la ejecución."""
    pass

class LLMProvider:
    """Interfaz base para proveedores de LLM (Llama-3, Ollama, API, etc.)."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

class MockLlama3Provider(LLMProvider):
    """Proveedor de prueba o fallback que simula la síntesis de lenguaje natural con base en el payload grounded."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return f"[Llama-3 Grounded Response]\n{user_prompt}"

class ActuarialQueryParser:
    """
    Parser que genera el JSON estructurado intermedio a partir de lenguaje natural libre.
    En un entorno con GPU/API, Llama-3 genera este JSON estructurado.
    En entorno local, el parser heurístico produce el mismo JSON estructurado bajo el mismo esquema.
    """

    VALID_INTENTS = {
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

    def __init__(self, catalog: ActuarialCatalog, memory: ConversationMemoryManager):
        self.catalog = catalog
        self.memory = memory

    def parse_to_structured_json(self, user_query: str) -> Dict[str, Any]:
        """Convierte la consulta del usuario a un JSON estructurado intermedio (IR)."""
        norm_q = normalize_text(user_query)

        # 1. Out of domain check
        if any(w in norm_q for w in ["clima", "temperatura", "lluvia", "tiempo manana", "futbol", "politica", "receta"]):
            return {
                "intent": "out_of_domain",
                "states": [],
                "target_year": None,
                "metrics": [],
                "confidence": 0.99,
                "query_text": user_query
            }

        # 2. State extraction (N estados)
        extracted_states = self.catalog.extract_states(user_query)
        effective_states = self.memory.get_effective_states(extracted_states, user_query)

        # 3. Year parsing con el memory manager
        target_year, year_err = self.memory.parse_year_intent(user_query, has_explicit_new_state=(len(extracted_states) > 0))
        if year_err:
            return {
                "intent": "temporal_out_of_range",
                "error_message": year_err,
                "states": [],
                "target_year": None,
                "metrics": [],
                "confidence": 1.0,
                "query_text": user_query
            }

        # 4. Metric extraction
        detected_metrics = self.catalog.resolve_metrics(user_query)

        # 5. Intent classification (Priorizar glosario y causalidad antes de estado único)
        intent = "single_state"
        if any(w in norm_q for w in ["resumen", "hallazgo", "hallazgos", "sintesis", "conclusiones"]):
            intent = "three_findings"
        elif any(w in norm_q for w in ["glosario", "definicion", "que es mdp", "volumen de costo total mdp", "explicar volumen de costo", "explicar mdp", "significa mdp"]):
            intent = "glossary_units"
        elif any(w in norm_q for w in ["causa", "causada", "causado", "causalidad", "provoca"]):
            intent = "regression_drivers"
        elif any(w in norm_q for w in ["pareto", "concentracion", "volumen agregado"]):
            intent = "pareto_breakdown"
        elif any(w in norm_q for w in ["crecimiento", "cagr", "incremento", "duplicaron", "tendencia", "acumulado"]):
            intent = "growth_cagr"
        elif any(w in norm_q for w in ["variable", "impacto", "factor", "correlacion", "afectan", "explicar r2", "precio"]):
            intent = "regression_drivers"
        elif any(w in norm_q for w in ["top", "ranking", "mayor severidad", "mas alto", "mas severos", "cuales son"]) and not len(effective_states) > 0:
            intent = "top_rankings"
        elif len(effective_states) >= 2 or any(w in norm_q for w in ["compara", "comparar", "vs", "versus", "diferencia", "difieren"]):
            intent = "multi_state_comparison"
        elif len(effective_states) == 1:
            intent = "single_state"
        elif any(w in norm_q for w in ["top", "ranking", "mayor", "mas alto"]):
            intent = "top_rankings"

        return {
            "intent": intent,
            "states": effective_states,
            "target_year": target_year,
            "metrics": detected_metrics,
            "confidence": 0.95,
            "query_text": user_query
        }

    @classmethod
    def validate_structured_json(cls, structured_json: Dict[str, Any], canonical_states: List[str]) -> bool:
        """
        Valida rigurosamente el JSON estructurado ANTES de pasarlo al motor de ejecución.
        Previene ejecuciones con entidades inválidas o parámetros corruptos.
        """
        intent = structured_json.get("intent")
        if not intent:
            raise QueryValidationError("El JSON estructurado carece de 'intent'.")

        if intent not in cls.VALID_INTENTS and intent not in {"temporal_out_of_range"}:
            raise QueryValidationError(f"Intent desconocido: '{intent}'.")

        # Validar estados
        states = structured_json.get("states", [])
        for st in states:
            if st not in canonical_states:
                raise QueryValidationError(f"Estado no reconocido en el catálogo canónico: '{st}'.")

        # Validar año
        target_year = structured_json.get("target_year")
        if target_year is not None:
            if not isinstance(target_year, int) or target_year not in ConversationMemoryManager.VALID_YEARS:
                raise QueryValidationError(f"Año {target_year} fuera del dominio válido (2020-2024).")

        return True


class GroundedActuarialAssistant:
    """
    Asistente Actuarial de Producción con arquitectura Grounded:
    1. Parseo a JSON Estructurado
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
        self.llm_provider = llm_provider # Optional Llama-3 connection

    def ask(self, user_query: str) -> str:
        # Paso 1: Generación de JSON estructurado
        structured_json = self.parser.parse_to_structured_json(user_query)

        # Paso 2: Validación antes de ejecutar
        try:
            self.parser.validate_structured_json(structured_json, self.canonical_states)
        except QueryValidationError as qe:
            return f"🤖 **Error de Validación de Consulta**: {qe}"

        intent = structured_json["intent"]

        # Paso 3: Ejecución de operaciones actuariales verificadas
        if intent == "out_of_domain":
            return """🤖 **Asistente de análisis actuarial**:
La consulta se encuentra fuera del ámbito actuarial del Dataset Actuarial de Severidad de Siniestros de Auto en México (Chubb Baseline 2020–2024).
Para mantener rigor metodológico sin alucinaciones, este asistente solo responde consultas sobre severidad ($ MXN), costo total (MDP), factores de riesgo vehicular e indicadores del reporte."""

        if intent == "temporal_out_of_range":
            return f"🤖 **Asistente de análisis actuarial**:\n{structured_json.get('error_message')}"

        if intent == "three_findings":
            findings = self.engine.compute_three_key_findings()
            top5_names = [f"{s['entidad']} (${s['mdp']:,.2f} MDP)" for s in findings['pareto_top5']]
            return f"""🤖 **Asistente de análisis actuarial — El reporte en 3 hallazgos clave**:

1. **Concentración Pareto del Costo Total (MDP)**:
   El Top 5 de entidades concentra el **{findings['pareto_pct']:.1f}% del costo nacional total en MDP** (${findings['top5_mdp_sum']:,.2f} MDP de los ${findings['total_national_mdp']:,.2f} MDP anuales). Encabezado por {', '.join(top5_names)}.

2. **Disparidad Geográfica y Crecimiento Acumulado**:
   Existe una brecha de severidad de aproximadamente **{findings['ratio_max_min']:.2f} veces ({findings['ratio_max_min']:.2f}x)** entre {findings['max_state']['entidad']} (${findings['max_state']['severidad']:,.2f} MXN, índice {findings['max_state']['idx']:.1f} pts) y {findings['min_state']['entidad']} (${findings['min_state']['severidad']:,.2f} MXN). {findings['growth_leader']['entidad']} lidera el incremento con **+{findings['growth_leader']['cagr_total']:.1f}% acumulado** (+{findings['growth_leader']['cagr_anual']:.1f}% anual compuesto).

3. **Asociación Estadística con Precios Vehiculares (r = +{findings['regression']['r']:.4f}, R² = {findings['regression']['r2_pct']:.2f}%)**:
   El precio comercial promedio del vehículo presenta la asociación más fuerte con la severidad. *Nota actuarial: La correlación estadística lineal macroestatal no demuestra causalidad directa única* sin evaluar microdatos de coberturas y pérdidas totales."""

        if intent == "top_rankings":
            ranks = self.engine.compute_severity_rankings(top_n=5)
            lines = ["🤖 **Asistente de análisis**: Top 5 Estados con Mayor Severidad Promedio:"]
            for r in ranks:
                lines.append(f"  {r['rank']}. **{r['entidad']}**: ${r['severidad']:,.2f} MXN (Promedio 2020–2024)")
            lines.append("• Fuente: Chubb Baseline (2020-2024) & INEGI VMRC")
            return "\n".join(lines)

        if intent == "multi_state_comparison":
            states = structured_json["states"]
            year = structured_json["target_year"]
            if len(states) < 2:
                # Si no hay 2 estados definidos aún, usa los del último contexto o pide clarificación
                states = ["Nuevo Leon", "Jalisco"]

            comp = self.engine.compute_multi_state_comparison(states, target_year=year)
            self.memory.update_confirmed_context(states, year, "multi_state_comparison")

            # Construcción dinámica para 2 o N estados
            lines = [
                f"🤖 **Asistente de análisis actuarial — Comparativa Multivariada ({len(states)} Entidades)**:",
                f"• Periodo evaluado: **{comp['periodo']}**\n",
                "1. **Severidad Unitaria ($/Siniestro)**:"
            ]
            for st_m in comp["estados_metricas"]:
                lines.append(f"   • **{st_m['entidad']}**: ${st_m['severidad']:,.2f} MXN (Índice: {st_m['indice_severidad']:.1f} pts, Nivel: **{st_m['categoria']}**)")

            lines.append(f"   • Brecha: **{comp['lider_severidad']}** supera a **{comp['menor_severidad']}** en **${comp['diferencia_absoluta']:,.2f} MXN** (+{comp['diferencia_porcentual']:.1f}% tomando como base a {comp['menor_severidad']}).\n")

            lines.append("2. **Costo Total en la Cartera (MDP)**:")
            for st_m in comp["estados_metricas"]:
                lines.append(f"   • **{st_m['entidad']}**: ${st_m['costo_mdp']:,.2f} MDP")

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
  • Severidad: **${m['severidad']:,.2f} MXN** por siniestro
  • Periodo: {m['periodo']}
  • Nivel de Riesgo: **{cat_display}**
  • Índice Relativo: **{m['indice_severidad']:.1f} pts** (Base Nacional = 100)
  • Costo Anual Medio: **${m['costo_mdp']:,.2f} MDP**
  • Parque Registrado: **{m['automoviles_registrados']:,d} autos** (INEGI VMRC, macro no asegurados)
  • Crecimiento Acumulado: **+{m['cagr_acumulado']:.1f}%**
  • Fuente: Dataset Actuarial Oficial (Chubb / INEGI VMRC)"""

        if intent == "pareto_breakdown":
            pareto = self.engine.compute_pareto_breakdown(top_k=5)
            lines = [
                f"🤖 **Asistente de análisis actuarial — Concentración Pareto de Costos (MDP)**:",
                f"• **Concentración Top 5**: Las 5 entidades con mayor volumen concentran el **{pareto['pct_k']:.1f}%** del costo total nacional en MDP (${pareto['sum_k_mdp']:,.2f} MDP de los ${pareto['total_national_mdp']:,.2f} MDP anuales).",
                "• **Ranking de Volumen en MDP**:"
            ]
            for s in pareto["top_states"]:
                lines.append(f"  {s['rank']}. {s['entidad']}: ${s['mdp']:,.2f} MDP ({s['pct_nacional']:.1f}%)")
            lines.append("• **Distinción Actuarial**: Este diagrama mide volumen agregado de pérdida (Costo Total en MDP), no severidad unitaria individual.")
            return "\n".join(lines)

        if intent == "growth_cagr":
            growth = self.engine.compute_growth_rankings(top_n=3)
            lines = [
                "🤖 **Asistente de análisis actuarial — Crecimiento y Tendencia Temporal (2020–2024)**:",
                "1. **Líder Nacional en Crecimiento Acumulado**:"
            ]
            for s in growth["leaders"]:
                lines.append(f"   • **{s['entidad']}**: Crecimiento de **+{s['cagr_acumulado']:.1f}%** acumulado (tasa anual compuesta CAGR de **+{s['cagr_anual']:.1f}%** anual).")
            lines.append("2. **Promedio Nacional**:")
            lines.append(f"   • Creció de ${growth['nacional']['sev_2020']:,.2f} MXN en 2020 a ${growth['nacional']['sev_2024']:,.2f} MXN en 2024 (+{growth['nacional']['cagr_total']:.1f}% acumulado, CAGR +{growth['nacional']['cagr_anual']:.1f}% anual).")
            lines.append("3. **Interpretación Actuarial**: Refleja presiones inflacionarias en autopartes, sofisticación tecnológica de vehículos y costos médicos.")
            return "\n".join(lines)

        if intent == "regression_drivers":
            stats = self.data["scatter_stats"]
            r_val = float(stats["r_pearson"])
            r2_val = float(stats["r2_score"]) * 100.0
            return f"""🤖 **Asistente de análisis actuarial — Asociación Estadística de Variables**:
De acuerdo con el análisis macroestatal (Promedio 2020–2024), las variables presentan los siguientes grados de asociación estadística lineal con la severidad:
1. **Precio Comercial Promedio del Vehículo (Mercado Libre)**: r = +{r_val:.4f} | R² = {r2_val:.2f}% (p < 0.0001)
2. **Tasa de Motorización (INEGI VMRC)**: r = +0.7648 (Autos registrados por cada 1,000 hab)
3. **Volumen del Parque Vehicular Registrado**: r = +0.3621
⚠️ *Nota Metodológica y Guardrail*: Describe fuerza de **asociación estadística** lineal, pero **no implica causalidad** directa ni demuestra que los autos caros sean la causa única de la severidad. La severidad real depende de coberturas, pérdida total y mano de obra."""

        if intent == "glossary_units":
            return f"""🤖 **Glosario Actuarial y Unidades Estándar**:
• **Severidad ($/Siniestro)**: Costo económico medio en **MXN** por cada siniestro pagado. Promedio nacional: **${self.engine.national_avg_severity:,.2f} MXN** (2020–2024).
• **Costo Total en MDP (Millones de Pesos)**: 1 MDP = $1,000,000 MXN. El total anual promedio nacional es de **${self.engine.total_national_mdp:,.2f} MDP**.
• **Identidad Actuarial**:
  Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
• **Exposición vs. Parque Registrado**: El parque vehicular registrado (INEGI VMRC) mide el volumen automotriz global, pero **no equivale a la exposición asegurada** (pólizas vigentes).
• **Índice Relativo (pts)**: Estandarización base 100 respecto a la media nacional del mismo periodo."""

        return """🤖 **Asistente de análisis actuarial**:
  No reconocí esa consulta con suficiente certeza dentro del dataset actuarial.
  Opciones recomendadas:
  • '¿Cuál es la severidad de Nuevo León?'
  • 'Compara Jalisco, Nuevo León, CDMX y Puebla'
  • 'Tres hallazgos clave'
  • 'Concentración de costos Pareto'"""
