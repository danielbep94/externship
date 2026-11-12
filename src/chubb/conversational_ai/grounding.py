"""
Conversational AI — Grounded Narrative & Response Formatting Module.
Constructs verified human narratives, executive summary tables, data-driven recommendations,
and business rules / glossary explanations from Analytical Foundation payloads.
"""

from typing import Dict, List, Any, Optional
from chubb.semantic_foundation.temporal_registry import normalize_text
from chubb.semantic_foundation.actuarial_catalog import ActuarialCatalog
from chubb.analytical_foundation.calculations import format_number, display_category_label
from chubb.analytical_foundation.actuarial_engine import ActuarialOperationsEngine


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


def format_executive_summary_response(
    summary: Dict[str, Any],
    structured_json: Dict[str, Any],
    llm_narrative: Optional[str] = None
) -> str:
    """Formatea la respuesta del Resumen Ejecutivo combinando narrativa natural verificada y desglose tabular."""
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

    narrative = llm_narrative or build_human_narrative(summary)
    if narrative:
        lines.append(f"\n{narrative}\n")

    if ref["value"] is not None:
        lines.append(f"Referencia: {ref['label'].lower()}, **${ref['value_fmt']} MXN (n = {ref['n']})**.\n")
    else:
        lines.append(f"Referencia: {ref['label'].lower()}, **no calculable (n = 0)**.\n")

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

    lines.append("\n**4. Alcance y limitaciones**")
    lines.append("- Severidad = costo total / siniestros estimados (35 % × 30 % de la población 2020); no son siniestros observados.")
    lines.append("- El parque INEGI VMRC no equivale a la exposición asegurada y no varía por año en este conjunto de datos.")
    lines.append("- Umbrales absolutos en MXN nominales; no se ajustan por inflación.")

    return "\n".join(lines)


def format_recommendations_response(rec_data: Dict[str, Any], structured_json: Dict[str, Any]) -> str:
    """
    Formatea recomendaciones actuariales, acciones preventivas e identificación de oportunidades
    basadas estrictamente en los datos reales de las entidades o de la cartera nacional.
    """
    yr = rec_data["target_year"]
    rows = rec_data["rows"]
    ref = rec_data["national_reference"]
    bench = rec_data["national_benchmarks"]
    notes = structured_json.get("interpretation_notes", [])

    if rec_data["scope"] == "national" or not rows:
        ctx = rec_data["portfolio_context"]
        pareto = ctx["pareto"]
        top_sev = ctx["top_sev"]
        growth = ctx["growth"]
        findings = ctx["findings"]
        lines = [f"🤖 **Recomendaciones, Acciones Preventivas y Oportunidades — Cartera Nacional ({yr})**"]
        for note in notes:
            lines.append(f"ℹ️ *{note}*")
        lines.append("\n**1. Diagnóstico Cuantitativo Base (Evidencia del Reporte)**")
        lines.append(
            f"• **Concentración Financiera (Pareto)**: El Top 5 concentra el **{format_number(pareto['pct_k'], 1)} %** del costo nacional "
            f"(**${format_number(pareto['sum_k_mdp'], 2)} MDP** de **${format_number(pareto['total_national_mdp'], 2)} MDP** anuales), "
            f"liderado por **{pareto['top_states'][0]['entidad']} (${format_number(pareto['top_states'][0]['mdp'], 2)} MDP)** y **{pareto['top_states'][1]['entidad']} (${format_number(pareto['top_states'][1]['mdp'], 2)} MDP)**."
        )
        lines.append(
            f"• **Severidad Crítica y Dinámica 2020–2024**: **{top_sev[0]['entidad']}** encabeza la severidad promedio con **${format_number(top_sev[0]['severidad'], 2)} MXN** "
            f"(índice **{format_number(top_sev[0]['indice'], 1)} pts**), mientras que **{growth['leaders'][0]['entidad']}** registra el mayor crecimiento acumulado con **+{format_number(growth['leaders'][0]['cagr_acumulado'], 1)} %** (CAGR **+{format_number(growth['leaders'][0]['cagr_anual'], 1)} %** anual)."
        )
        lines.append("\n**2. Acciones Preventivas y de Mitigación**")
        lines.append(
            f"• **Control de talleres y valuación en polos de Severidad Crítica (≥ $11,000.00 MXN)**: Establecer convenios de tabuladores cerrados de mano de obra y compra consolidada de autopartes en **{top_sev[0]['entidad']} (${format_number(top_sev[0]['severidad'], 2)} MXN)**, **{top_sev[1]['entidad']} (${format_number(top_sev[1]['severidad'], 2)} MXN)** y **{top_sev[2]['entidad']} (${format_number(top_sev[2]['severidad'], 2)} MXN)**, considerando la asociación con el precio comercial vehicular (**r = +{bench['r_pearson_fmt']}**, **R² = {bench['r2_pct_fmt']} %**)."
        )
        lines.append(
            f"• **Prevención vial focalizada en el Top 5 Pareto ({format_number(pareto['pct_k'], 1)} % del volumen)**: Desplegar telemetría en flotillas y programas de prevención en corredores urbanos de **{', '.join(s['entidad'] for s in pareto['top_states'])}**."
        )
        lines.append(
            f"• **Vigilancia de inflación siniestral (2020–2024)**: Auditar suficiencia de sumas aseguradas en entidades con aceleración superior a la media nacional (**{bench['nat_cagr_acum_fmt']}**), encabezadas por **{growth['leaders'][0]['entidad']} (+{format_number(growth['leaders'][0]['cagr_acumulado'], 1)} %)** y **{growth['leaders'][1]['entidad']} (+{format_number(growth['leaders'][1]['cagr_acumulado'], 1)} %)**."
        )
        lines.append("\n**3. Identificación de Oportunidades Basadas en los Datos**")
        lines.append(
            f"• **Crecimiento selectivo en plazas de Severidad Baja (< $7,500.00 MXN)**: Impulsar penetración comercial en mercados con severidad contenida, como **{findings['min_state']['entidad']} (${format_number(findings['min_state']['severidad'], 2)} MXN, índice {format_number(findings['min_state']['idx'], 1)} pts)**, manteniendo disciplina de suscripción."
        )
        lines.append(
            "• **Productos modulares para el parque en circulación (INEGI VMRC)**: Desarrollar coberturas escalonadas (Responsabilidad Civil ampliada y deducible flexible) para capturar parque registrado no asegurado sin presionar la severidad media."
        )
        lines.append("\n**4. Alcance y Guardrail Metodológico**")
        lines.append("- Recomendaciones derivadas de los indicadores macroestatales de `data.json` (RN-01 a RN-06). La asociación estadística con el precio vehicular no implica causalidad directa única.")
        return "\n".join(lines)

    state_titles = ", ".join(r["entidad"] for r in rows)
    lines = [f"🤖 **Recomendaciones, Acciones Preventivas y Oportunidades — {state_titles} ({yr})**"]
    for note in notes:
        lines.append(f"ℹ️ *{note}*")

    lines.append(f"\n**1. Diagnóstico Cuantitativo Base (`data.json` · {yr})**")
    for r in rows:
        diff_vs_100 = abs(r["indice"] - 100.0) if r["indice"] is not None else 0.0
        dir_str = "por encima" if (r["indice"] is not None and r["indice"] >= 100.0) else "por debajo"
        cat_shift = ""
        if r["categoria"] != r["categoria_periodo"]:
            cat_shift = f" *(escaló de categoría **{r['categoria_periodo']}** en el promedio 2020–2024 [${r['severidad_promedio_fmt']} MXN] a **{r['categoria']}** en {yr})*"
        lines.append(
            f"• **{r['entidad']}**: Severidad de **${r['severidad_fmt']} MXN** por siniestro (**{r['rank_nacional_severidad']}.º lugar nacional de {r['n_nacional_severidad']}**), "
            f"clasificada en nivel **{r['categoria']}**{cat_shift} con un Índice Relativo de **{r['indice_fmt']} pts** "
            f"(**{format_number(diff_vs_100, 1)} % {dir_str}** de la media nacional de **${ref['value_fmt']} MXN**, n = {ref['n']})."
        )
        lines.append(
            f"  - **Volumen y Evolución (2020 → {yr})**: Acumula **${r['costo_mdp_fmt']} MDP** (**{r['rank_nacional_mdp']}.º de {r['n_nacional_mdp']}**, **{r['pct_costo_nacional_yr_fmt']} %** del costo nacional en {yr}). "
            f"Frente a 2020, su severidad varió **{r['var_severidad_fmt']}** (CAGR 2020–2024: **{r['cagr_anual_fmt']}** anual) y su índice relativo cambió en **{r['delta_indice_fmt']}** (de **{r['indice_2020_fmt']}** a **{r['indice_fmt']} pts**)."
        )
        lines.append(
            f"  - **Factores del Parque Vehicular**: Precio comercial medio del vehículo de **${r['precio_auto_k_fmt']}k MXN** (media estatal: **${bench['nat_precio_auto_k_fmt']}k MXN**; asociación nacional **r = +{bench['r_pearson_fmt']}**, **R² = {bench['r2_pct_fmt']} %**) "
            f"y tasa de motorización de **{r['autos_por_1000_hab_fmt']} autos / 1,000 hab.** (**{r['automoviles_registrados']:,d} autos** registrados INEGI VMRC vs. **{bench['nat_motorizacion_fmt']}** de media estatal)."
        )

    lines.append("\n**2. Acciones Preventivas y de Mitigación de Severidad**")
    for r in rows:
        if r["categoria"] == "Crítica" or (r["indice"] is not None and r["indice"] >= 110.0):
            lines.append(
                f"• **Control de costos de reparación y talleres en {r['entidad']} (Severidad {r['categoria']}: ${r['severidad_fmt']} MXN | Índice: {r['indice_fmt']} pts)**: "
                f"Dado que rebasa el umbral crítico de **$11,000.00 MXN** y registra un valor comercial vehicular de **${r['precio_auto_k_fmt']}k MXN**, "
                f"implementar **convenios de tabuladores cerrados de mano de obra, compra consolidada de refacciones y auditoría técnica obligatoria** en reclamos mayores a **$11,000.00 MXN**, además de revisar umbrales de pérdida total."
            )
        elif r["categoria"] == "Media":
            gap_crit = max(0.0, 11000.0 - (r["severidad"] or 0.0))
            lines.append(
                f"• **Contención preventiva de estrato en {r['entidad']} (Severidad Media: ${r['severidad_fmt']} MXN | Brecha a Crítica: ${format_number(gap_crit, 2)} MXN)**: "
                f"Reforzar **direccionamiento a red de talleres preferentes y topes de valuación por orden de reparación** para evitar que la entidad rebase el umbral crítico de **$11,000.00 MXN**."
            )
        else:
            lines.append(
                f"• **Preservación de severidad contenida en {r['entidad']} (Severidad Baja: ${r['severidad_fmt']} MXN | Índice: {r['indice_fmt']} pts)**: "
                f"Mantener acuerdos tarifarios con talleres locales y control de costos médicos/RC para conservar la severidad por debajo del límite de **$7,500.00 MXN**."
            )

        lines.append(
            f"• **Prevención vial focalizada por densidad vehicular ({r['autos_por_1000_hab_fmt']} autos / 1,000 hab.) y volumen (${r['costo_mdp_fmt']} MDP)**: "
            f"Desplegar **alertas preventivas en corredores urbanos, telemetría en flotillas y esquemas de deducible diferenciado** en las zonas que concentran los **${r['costo_mdp_fmt']} MDP** (**{r['rank_nacional_mdp']}.º lugar nacional**)."
        )

        if r["delta_indice_pts"] is not None and r["delta_indice_pts"] > 0:
            lines.append(
                f"• **Ajuste por aceleración inflacionaria en {r['entidad']} ({r['var_severidad_fmt']} desde 2020 | Δ Índice: {r['delta_indice_fmt']})**: "
                f"Su severidad creció por encima de la media nacional (**{bench['nat_cagr_acum_fmt']}**), elevando su índice de **{r['indice_2020_fmt']}** a **{r['indice_fmt']} pts**. Se recomienda **actualización prioritaria de suficiencia tarifaria y sumas aseguradas**."
            )
        else:
            lines.append(
                f"• **Vigilancia de inflación nominal en {r['entidad']} ({r['var_severidad_fmt']} desde 2020 | CAGR: {r['cagr_anual_fmt']} anual)**: "
                f"Aunque su índice relativo se moderó en **{r['delta_indice_fmt']}** (**{r['indice_2020_fmt']} → {r['indice_fmt']} pts**), el alza nominal acumulada llevó la severidad a **${r['severidad_fmt']} MXN**. Se recomienda **indexación preventiva de sumas aseguradas y monitoreo trimestral de autopartes**."
            )

    lines.append("\n**3. Identificación de Oportunidades Basadas en los Datos**")
    for r in rows:
        if r["delta_indice_pts"] is not None and r["delta_indice_pts"] <= 0:
            lines.append(
                f"• **Oportunidad de retención y crecimiento selectivo por estabilización relativa ({r['delta_indice_fmt']} en índice 2020 → {yr})**: "
                f"**{r['entidad']}** creció a un ritmo menor que el promedio nacional (**{r['var_severidad_fmt']}** vs. **{bench['nat_cagr_acum_fmt']}** nacional), reduciendo su índice de **{r['indice_2020_fmt']}** a **{r['indice_fmt']} pts**. "
                f"Esto abre oportunidad para **fidelizar cartera sana y crecer selectivamente** en segmentos de riesgo controlado."
            )
        else:
            lines.append(
                f"• **Oportunidad de re-segmentación técnica en {r['entidad']} ({r['delta_indice_fmt']} en índice 2020 → {yr})**: "
                f"Introducir productos con **deducible calibrado y taller multimarca certificado** para recuperar margen técnico frente al incremento relativo de severidad."
            )

        lines.append(
            f"• **Oportunidad de penetración sobre el parque vehicular registrado ({r['automoviles_registrados']:,d} autos INEGI VMRC)**: "
            f"Con una motorización de **{r['autos_por_1000_hab_fmt']} autos / 1,000 hab.** y un costo anual medio por auto registrado de **${r['costo_por_auto_fmt']} MXN** (promedio 2020–2024), "
            f"diseñar **coberturas modulares (Responsabilidad Civil ampliada, pérdida total o deducible flexible)** para captar parque en circulación no asegurado sin presionar la severidad unitaria (**${r['severidad_fmt']} MXN**)."
        )
        lines.append(
            f"• **Calibración de oferta según valor comercial regional (${r['precio_auto_k_fmt']}k MXN)**: "
            f"Alinear paquetes de cobertura amplia y reparación al valor comercial promedio de **${r['precio_auto_k_fmt']}k MXN** en **{r['entidad']}**, optimizando la relación entre valor del activo y costo medio por reclamo."
        )

    lines.append("\n**4. Alcance y Guardrail Metodológico**")
    lines.append("- Estas recomendaciones se derivan de los indicadores agregados verificados en `data.json` (RN-01 a RN-06).")
    lines.append(f"- La asociación entre precio vehicular y severidad (**r = +{bench['r_pearson_fmt']}**, **R² = {bench['r2_pct_fmt']} %**) es orientativa y **no implica causalidad directa única**; decisiones de suscripción o tarifa a nivel póliza requieren cruzar con exposición asegurada y frecuencia observada.")
    return "\n".join(lines)


def format_business_rules_response(
    user_query: str,
    engine: ActuarialOperationsEngine,
    catalog: ActuarialCatalog,
    data: Dict[str, Any]
) -> str:
    """
    Responde consultas sobre Reglas de Negocio (Business Rules), fórmulas matemáticas,
    umbrales, tratamiento de datos faltantes, redondeo ROUND_HALF_UP y glosario actuarial.
    """
    norm_q = normalize_text(user_query)
    ref_2024, n_2024 = engine.compute_national_reference_for_year("2024")
    cdmx_2024 = engine.estados_dict["Ciudad de Mexico"]["yearly_severidad"]["2024"]
    cdmx_idx_2024 = (cdmx_2024 / ref_2024) * 100.0 if ref_2024 else 0.0

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

    if any(w in norm_q for w in ["ranking", "posicion", "empate", "empates"]) and "glosario" not in norm_q:
        return """🤖 **Regla de Negocio (RN-04) — Rankings Nacionales, de Selección y Empates**:

**1. Alcance Nacional y Denominador Dinámico**:
• La posición de cada métrica (`severidad` o `costo_mdp`) en el año `Y` se calcula únicamente entre las entidades con valor válido en ese año: formato **`k.º de n_métrica(Y)`**.

**2. Regla de Empates (Ranking de Competencia Estándar `1, 1, 3`)**:
• Los valores se comparan **redondeados a la precisión de presentación** (`2 decimales` / centavos mediante `ROUND_HALF_UP`).
• Si dos entidades empatan al centavo (p. ej. `$100.004` y `$100.001` → ambos `$100.00`), comparten la posición `1.º` y la siguiente entidad recibe la posición `3.º`.

**3. Alcance de Selección**:
• Solo se calcula cuando se consultan `>= 2` entidades únicas. Para `1` sola entidad se omite ("1 de 1" no aporta información)."""

    is_full_catalog_req = any(w in norm_q for w in ["glosario", "catalogo", "todas las reglas"])
    if "severidad" in norm_q and not is_full_catalog_req:
        det_states = catalog.extract_states(user_query)
        ex_state_name = det_states[0] if det_states else "Ciudad de Mexico"
        ex_st = engine.estados_dict.get(ex_state_name, engine.estados_dict["Ciudad de Mexico"])
        ex_sev_2024 = float(ex_st["yearly_severidad"]["2024"])
        ex_mdp_2024 = float(ex_st["yearly_mdp"]["2024"])
        ex_pob_2020 = int(ex_st["poblacion_2020"])
        ex_claims = 0.35 * 0.30 * ex_pob_2020
        ex_idx_2024 = (ex_sev_2024 / ref_2024) * 100.0 if ref_2024 else 0.0
        ex_cat_2024 = display_category_label(ex_st["yearly_categoria"]["2024"])

        return f"""🤖 **¿Qué es la Severidad y cómo se calcula? (Reglas RN-02 y RN-03)**:

**1. ¿Qué es la Severidad? (En lenguaje sencillo)**:
• La **severidad** es el **costo económico promedio de cada siniestro**; es decir, cuánto cuesta en promedio reparar o indemnizar **un solo accidente vehicular** (expresado en **`$ MXN por siniestro`**).
• **Diferencia clave frente al Costo Total (`MDP`)**: La severidad mide qué tan caro es *cada choque individual*, mientras que el **Costo Total (`MDP`)** suma el dinero de *todos los siniestros ocurridos en el estado*. Un estado puede tener muchos choques pequeños (costo total alto, pero severidad baja) o pocos choques muy costosos (severidad alta).

**2. ¿Cómo se calcula? (Fórmula Actuarial y del Modelo)**:
• **Fórmula actuarial general**:
  `Severidad ($ MXN) = Costo Total de Siniestros ($) / Número de Siniestros Ocurridos`
• **Fórmula en este conjunto de datos (`RN-03`, supuesto `H4`)**:
  `Severidad_e(Y) = [ Costo_Total_MDP_e(Y) × 1,000,000 ] / Siniestros_Estimados_e`
  donde `Siniestros_Estimados_e = 35 % (exposición) × 30 % (frecuencia) × Población_2020_e`.

**3. Ejemplo paso a paso con datos reales ({ex_state_name}, 2024)**:
• **Paso 1 (Costo Total en 2024)**: **${format_number(ex_mdp_2024, 2)} MDP** (equivalente a **${format_number(ex_mdp_2024 * 1_000_000.0, 0)} MXN**).
• **Paso 2 (Siniestros estimados)**: `35 % × 30 % × {ex_pob_2020:,d} habitantes` = **{format_number(ex_claims, 2)} siniestros**.
• **Paso 3 (División)**: `${format_number(ex_mdp_2024 * 1_000_000.0, 0)} MXN / {format_number(ex_claims, 2)} siniestros` = **${format_number(ex_sev_2024, 2)} MXN por siniestro** (Categoría: **{ex_cat_2024}**, Índice Relativo: **{format_number(ex_idx_2024, 1)} pts** frente a la media nacional 2024 de **${format_number(ref_2024, 2)} MXN**, `n = {n_2024}`).

**4. ¿Cómo se clasifica el nivel de severidad? (Semáforo `RN-02`)**:
• 🔴 **Crítica**: `>= $11,000.00 MXN` por siniestro.
• 🟡 **Media**: `$7,500.00 a < $11,000.00 MXN` por siniestro.
• 🟢 **Baja**: `< $7,500.00 MXN` por siniestro."""

    if any(w in norm_q for w in ["mdp", "costo total", "millones de pesos", "volumen de costo"]) and not is_full_catalog_req:
        edomex_mdp_2024 = float(engine.estados_dict["Estado de Mexico"]["yearly_mdp"]["2024"])
        cdmx_mdp_2024 = float(engine.estados_dict["Ciudad de Mexico"]["yearly_mdp"]["2024"])
        return f"""🤖 **¿Qué es el Costo Total (`MDP`) y cómo se calcula? (Regla RN-03)**:

**1. Definición en lenguaje sencillo**:
• **`MDP`** significa **Millones de Pesos** (`1 MDP = $1,000,000 MXN`).
• El **Costo Total en MDP** mide el **volumen financiero agregado** de todos los siniestros ocurridos en una entidad durante el periodo. A nivel nacional (promedio anual 2020–2024), el costo total es de **${format_number(engine.total_national_mdp, 2)} MDP**.

**2. Identidad Actuarial Oficial**:
• `Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000`
• Mientras la **severidad** mide el costo unitario de *un* siniestro (`$ MXN`), el **Costo Total (`MDP`)** refleja la masa monetaria completa impulsada por el tamaño poblacional y vehicular del estado.

**3. Ejemplo verificable en el reporte (2024)**:
• **Estado de México** ocupa el **1.º lugar nacional en Costo Total** con **${format_number(edomex_mdp_2024, 2)} MDP** (aunque su severidad unitaria es Media: `$8,105.33 MXN`), seguido por **Ciudad de México** con **${format_number(cdmx_mdp_2024, 2)} MDP**.
• **Aclaración metodológica**: El parque vehicular registrado (`INEGI VMRC`) mide la escala automotriz macro del estado, pero **no equivale a la exposición asegurada** (pólizas vigentes)."""

    if any(w in norm_q for w in ["frecuencia", "exposicion", "parque vehicular", "inegi vmrc"]) and not is_full_catalog_req:
        return """🤖 **¿Qué son la Frecuencia y la Exposición Asegurada? (Regla RN-03 y Supuesto H4)**:

**1. Definición Actuarial**:
• **Exposición Asegurada**: Número de vehículos-año cubiertos por una póliza de seguro vigente.
• **Frecuencia de Reclamos**: Proporción o tasa de vehículos asegurados que sufren un siniestro en un año (`Frecuencia = Siniestros Ocurridos / Exposición Asegurada`).

**2. Cómo operan en este conjunto de datos (`H4`)**:
• En este estudio macroestatal, el denominador de siniestros se estima de forma fija por entidad aplicando **35 % de exposición × 30 % de frecuencia** sobre la **población del Censo INEGI 2020** (`0.105 × población_2020`).
• **Distinción crítica**: Las cifras de **Parque Vehicular Registrado (`INEGI VMRC`)** muestran el total de automóviles en circulación en el estado, pero **no equivalen a la exposición asegurada** (en México la penetración del seguro varía por entidad)."""

    if any(w in norm_q for w in ["r2", "r cuadrada", "correlacion", "pearson"]) and not is_full_catalog_req:
        r_val = float(data["scatter_stats"]["r_pearson"])
        r2_pct = float(data["scatter_stats"]["r2_score"]) * 100.0
        return f"""🤖 **¿Qué miden la Correlación (`r`) y el Coeficiente `R²` en este modelo?**:

**1. Definición Estadística**:
• **Correlación de Pearson (`r = +{format_number(r_val, 4, False)}`)**: Mide la fuerza y dirección de la asociación lineal entre el precio comercial promedio del vehículo (`Mercado Libre`) y la severidad estatal (Promedio 2020–2024).
• **Coeficiente de Determinación (`R² = {format_number(r2_pct, 2)} %`)**: Indica que el **{format_number(r2_pct, 2)} %** de la variación interestatal de la severidad se explica linealmente por las diferencias en el valor comercial del parque vehicular (`R² = r²`).

**2. Guardrail Actuarial (Correlación ≠ Causalidad)**:
• Esta relación describe una **asociación estadística agregada**, pero **no implica causalidad directa** ni demuestra que el precio del auto sea la única causa de la severidad (intervienen también mezcla de coberturas, robo total y costos locales de reparación)."""

    return f"""🤖 **Catálogo de Reglas de Negocio (`config/actuarial_rules.json`) y Glosario Actuarial**:

• **RN-01 · Referencia Nacional e Índice Relativo (`pts`)**:
  - `Media_ref(Y) = Σ Severidad_e(Y) / n(Y)` (Media de severidad de las entidades con dato; en el promedio 2020–2024 es **${format_number(engine.national_avg_severity, 2)} MXN**, `n = 32`).
  - `Índice_e(Y) = 100 × Severidad_e(Y) / Media_ref(Y)` (Base 100, redondeado a `1 decimal` con `ROUND_HALF_UP`).

• **RN-02 · Umbrales de Categoría de Severidad (`P3`)**:
  - **Crítica**: `>= $11,000.00 MXN` | **Media**: `$7,500.00 a < $11,000.00 MXN` | **Baja**: `< $7,500.00 MXN`.
  - Evaluados sin redondear; la categoría anual `yearly_categoria[Y]` nunca se sustituye por la del periodo.

• **RN-03 · Severidad (`$/Siniestro`) y Costo Total en `MDP` (Millones de Pesos)**:
  - `1 MDP = $1,000,000 MXN`. El total anual promedio nacional es de **${format_number(engine.total_national_mdp, 2)} MDP**.
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

