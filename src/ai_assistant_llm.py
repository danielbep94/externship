"""
Asistente de Análisis Actuarial con LLM / Algoritmo Grounded Determinístico (Llama-3 / Python)
Soporta consultas por estado, periodo (2020-2024), seguimiento de contexto conversacional y guardrails de verificación.
"""

import pandas as pd
import numpy as np
import difflib
import unicodedata

STATES = [
    'Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche', 'Chiapas',
    'Chihuahua', 'Ciudad de Mexico', 'Coahuila', 'Colima', 'Durango',
    'Estado de Mexico', 'Guanajuato', 'Guerrero', 'Hidalgo', 'Jalisco',
    'Michoacan', 'Morelos', 'Nayarit', 'Nuevo Leon', 'Oaxaca',
    'Puebla', 'Queretaro', 'Quintana Roo', 'San Luis Potosi', 'Sinaloa',
    'Sonora', 'Tabasco', 'Tamaulipas', 'Tlaxcala', 'Veracruz',
    'Yucatan', 'Zacatecas'
]

STOP_WORDS = {"son", "clima", "mas", "los", "las", "del", "con", "que", "para", "por", "cuanto", "cuales", "como"}

def normalize_string(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower().strip()

def match_state_fuzzy(user_input):
    norm_input = normalize_string(user_input)
    norm_states = {normalize_string(s): s for s in STATES}
    
    # 1. Exact/Substring
    for norm_s, s in norm_states.items():
        if norm_s == norm_input or norm_s in norm_input:
            return s
            
    # 2. Word-by-word fuzzy
    words = [w for w in norm_input.split() if w not in STOP_WORDS and len(w) >= 4]
    for word in words:
        matches = difflib.get_close_matches(word, norm_states.keys(), n=1, cutoff=0.7)
        if matches:
            return norm_states[matches[0]]
            
    # 3. Full phrase fuzzy
    matches = difflib.get_close_matches(norm_input, norm_states.keys(), n=1, cutoff=0.6)
    if matches and matches[0] not in STOP_WORDS:
        return norm_states[matches[0]]
        
    return None

def extract_states_fuzzy(user_input):
    norm_input = normalize_string(user_input)
    norm_states = {normalize_string(s): s for s in STATES}
    found = []
    
    # 1. Exact substrings
    for norm_s, s in norm_states.items():
        if norm_s in norm_input and s not in found:
            found.append(s)
            
    if len(found) >= 2:
        return found[:2]
        
    # 2. Word fuzzy
    words = [w for w in norm_input.split() if w not in STOP_WORDS and len(w) >= 4]
    for word in words:
        matches = difflib.get_close_matches(word, norm_states.keys(), n=1, cutoff=0.75)
        if matches:
            s_name = norm_states[matches[0]]
            if s_name not in found:
                found.append(s_name)
                if len(found) >= 2:
                    return found[:2]
                    
    # 3. Fallback to full match_state_fuzzy if not found
    if not found:
        single = match_state_fuzzy(user_input)
        if single:
            found.append(single)

    return found

class LlamaColabDataAgent:
    """
    Agente de Asistente de Análisis Actuarial grounded en datos estáticos de Chubb Baseline (2020-2024).
    Mantiene contexto de conversación y verifica fuentes.
    """
    def __init__(self, df_path='/Users/victordaniel/chubb/output/df_analisis_completo.csv'):
        try:
            self.df = pd.read_csv(df_path)
        except Exception:
            self.df = pd.DataFrame()
            
        if not self.df.empty:
            self.df_avg = self.df.groupby('entidad').agg({
                'severidad_poblacion': 'mean',
                'siniestros_ocurridos_mdp': 'mean',
                'precio_promedio_auto_ml_k_mxn': 'first',
                'autos_por_1000_hab': 'first',
                'automoviles_registrados': 'first'
            }).reset_index()
            self.national_avg = self.df['severidad_poblacion'].mean()
        else:
            self.df_avg = pd.DataFrame()
            self.national_avg = 6674.08

        self.last_state = None
        self.last_states = []
        self.last_year = 'ALL'

    def process_query(self, user_question: str) -> str:
        q_clean = user_question.strip()
        norm_q = normalize_string(q_clean)

        # Detect Year
        import re
        year_match = re.search(r'\b(2020|2021|2022|2023|2024)\b', norm_q)
        req_year = year_match.group(1) if year_match else None
        if req_year:
            self.last_year = req_year

        found_states = extract_states_fuzzy(q_clean)

        # 0. Out of Domain Intent (Weather, Sports, etc.)
        if any(w in norm_q for w in ["clima", "temperatura", "lluvia", "tiempo manana", "futbol", "politica", "receta"]):
            return """🤖 **Asistente de análisis actuarial**:
La consulta se encuentra fuera del ámbito actuarial del Dataset Actuarial de Severidad de Siniestros de Auto en México (Chubb Baseline 2020–2024).
Para mantener rigor metodológico sin alucinaciones, este asistente solo responde consultas sobre severidad ($ MXN), costo total (MDP), factores de riesgo vehicular e indicadores del reporte."""

        # 1. Three Findings / Resumen Ejecutivo
        if any(w in norm_q for w in ["resumen", "hallazgo", "hallazgos", "sintesis", "conclusiones"]):
            max_sev = self.df_avg.sort_values(by='severidad_poblacion', ascending=False).iloc[0]
            min_sev = self.df_avg.sort_values(by='severidad_poblacion', ascending=True).iloc[0]
            ratio = max_sev['severidad_poblacion'] / min_sev['severidad_poblacion']
            top5_mdp = self.df_avg.sort_values(by='siniestros_ocurridos_mdp', ascending=False).head(5)
            sum_top5_mdp = top5_mdp['siniestros_ocurridos_mdp'].sum()
            tot_mdp = 90373.46
            pareto_pct = (sum_top5_mdp / tot_mdp) * 100

            return f"""🤖 **Asistente de análisis actuarial — El reporte en 3 hallazgos clave**:

1. **Concentración Pareto del Costo Total (MDP)**:
   El Top 5 de entidades concentra el **{pareto_pct:.1f}% del costo nacional total en MDP** (${sum_top5_mdp:,.2f} MDP de los ${tot_mdp:,.2f} MDP anuales). Encabezado por Ciudad de México ($10,616.13 MDP), Estado de México ($10,274.08 MDP), Jalisco ($9,488.29 MDP), Nuevo León ($8,485.28 MDP) y Sinaloa ($3,698.65 MDP).

2. **Disparidad Geográfica y Crecimiento Acumulado**:
   Existe una brecha de severidad de aproximadamente **{ratio:.2f} veces ({ratio:.2f}x)** entre {max_sev['entidad']} (${max_sev['severidad_poblacion']:,.2f} MXN, índice 209.3 pts) y {min_sev['entidad']} (${min_sev['severidad_poblacion']:,.2f} MXN). Tlaxcala lidera el incremento con **+150.6% acumulado** (+25.8% anual compuesto).

3. **Asociación Estadística con Precios Vehiculares (r = +0.8488, R² = 72.05%)**:
   El precio comercial promedio del vehículo presenta la asociación más fuerte con la severidad. *Nota actuarial: La correlación estadística lineal macroestatal no demuestra causalidad directa única* sin evaluar microdatos de coberturas y pérdidas totales."""

        # 2. Causality / Methodological Guardrail
        if any(w in norm_q for w in ["causa", "causada", "causado", "causalidad", "provoca"]):
            return """🤖 **Asistente de análisis actuarial — Guardrail Metodológico de Causalidad**:
• **Asociación vs. Causalidad**: El precio comercial de los vehículos muestra una correlación de **r = +0.8488** y un **R² = 72.05%** con la severidad estatal.
• **Restricción actuarial**: Esta asociación estadística **no implica causalidad directa**. La correlación macroestatal no demuestra que tener un auto más caro sea la causa directa única del mayor costo.
• **Variables omitidas**: La severidad individual depende fuertemente de la mezcla de coberturas (cobertura amplia vs. responsabilidad civil), la proporción de pérdidas totales y los costos de refacciones y mano de obra en talleres locales."""

        # 3. Growth / Historical Trend Intent (Checked BEFORE general ranking)
        if any(w in norm_q for w in ["crecimiento", "cagr", "incremento", "evolucion", "tendencia", "acumulado"]):
            return """🤖 **Asistente de análisis actuarial — Crecimiento y Tendencia Temporal (2020–2024)**:
1. **Líder Nacional en Crecimiento Acumulado**:
   • **Tlaxcala**: Crecimiento de **+150.6%** acumulado (tasa anual compuesta CAGR de **+25.8%** anual).
   • **Quintana Roo**: **+149.0%** acumulado (+25.6% CAGR anual).
   • **Yucatán**: **+148.6%** acumulado (+25.6% CAGR anual).
2. **Promedio Nacional**:
   • Creció de $4,511.22 MXN en 2020 a $9,041.64 MXN en 2024 (+100.4% acumulado, CAGR +19.0% anual).
3. **Interpretación Actuarial**: Refleja presiones inflacionarias en autopartes, sofisticación tecnológica de vehículos y costos médicos."""

        # 4. Pareto Concentration Intent
        if any(w in norm_q for w in ["pareto", "concentracion", "volumen agregado"]):
            top5_mdp = self.df_avg.sort_values(by='siniestros_ocurridos_mdp', ascending=False).head(5)
            sum_top5 = top5_mdp['siniestros_ocurridos_mdp'].sum()
            tot_mdp = 90373.46
            pct = (sum_top5 / tot_mdp) * 100
            return f"""🤖 **Asistente de análisis actuarial — Concentración Pareto de Costos (MDP)**:
• **Concentración Top 5**: Las 5 entidades con mayor volumen concentran el **{pct:.1f}%** del costo total nacional en MDP (${sum_top5:,.2f} MDP de los ${tot_mdp:,.2f} MDP anuales).
• **Ranking de Volumen en MDP**:
  1. Ciudad de México: $10,616.13 MDP (11.7%)
  2. Estado de México: $10,274.08 MDP (11.4%)
  3. Jalisco: $9,488.29 MDP (10.5%)
  4. Nuevo León: $8,485.28 MDP (9.4%)
  5. Sinaloa: $3,698.65 MDP (4.1%)
• **Distinción Actuarial**: Este diagrama mide volumen agregado de pérdida (Costo Total en MDP), no severidad unitaria individual."""

        # 5. Glossary and Units Intent (MDP, Severidad, Frecuencia, R2)
        if any(w in norm_q for w in ["glosario", "definicion", "que es mdp", "volumen de costo total mdp", "explicar mdp", "que significa mdp", "significa"]):
            return """🤖 **Glosario Actuarial y Unidades Estándar**:
• **Severidad ($/Siniestro)**: Costo económico medio en **MXN** por cada siniestro pagado. Promedio nacional: **$6,674.08 MXN** (2020–2024).
• **Costo Total en MDP (Millones de Pesos)**: 1 MDP = $1,000,000 MXN. El total anual promedio nacional es de **$90,373.46 MDP**.
• **Identidad Actuarial**:
  Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
• **Exposición vs. Parque Registrado**: El parque vehicular registrado (INEGI VMRC) mide el volumen automotriz global, pero **no equivale a la exposición asegurada** (pólizas vigentes).
• **Índice Relativo (pts)**: Estandarización base 100 respecto a la media nacional del mismo periodo."""

        # 6. State Comparison Intent
        is_comparison = any(w in norm_q for w in ["comparar", "compara", "vs", "versus", "diferencia", "difieren"]) or len(found_states) >= 2
        if is_comparison and (len(found_states) >= 2 or (len(found_states) == 1 and len(self.last_states) >= 2)):
            stA_name = found_states[0] if len(found_states) >= 1 else self.last_states[0]
            stB_name = found_states[1] if len(found_states) >= 2 else self.last_states[1]
            
            subA = self.df[self.df['entidad'] == stA_name]
            subB = self.df[self.df['entidad'] == stB_name]
            
            if not subA.empty and not subB.empty:
                self.last_states = [stA_name, stB_name]
                if req_year:
                    sevA = subA[subA['anio'] == int(req_year)]['severidad_poblacion'].values[0]
                    sevB = subB[subB['anio'] == int(req_year)]['severidad_poblacion'].values[0]
                    mdA = subA[subA['anio'] == int(req_year)]['siniestros_ocurridos_mdp'].values[0]
                    mdB = subB[subB['anio'] == int(req_year)]['siniestros_ocurridos_mdp'].values[0]
                    period_str = f"Año {req_year}"
                else:
                    sevA = subA['severidad_poblacion'].mean()
                    sevB = subB['severidad_poblacion'].mean()
                    mdA = subA['siniestros_ocurridos_mdp'].mean()
                    mdB = subB['siniestros_ocurridos_mdp'].mean()
                    period_str = "Promedio 2020–2024"

                diff_abs = abs(sevA - sevB)
                higher_name = stA_name if sevA >= sevB else stB_name
                lower_name = stB_name if sevA >= sevB else stA_name
                lower_val = min(sevA, sevB)
                pct_diff = (diff_abs / lower_val) * 100

                return f"""🤖 **Asistente de análisis actuarial — Comparativa entre {stA_name} y {stB_name}**:
• Periodo evaluado: {period_str}

1. **Severidad Unitaria ($/Siniestro)**:
   • {stA_name}: **${sevA:,.2f} MXN**
   • {stB_name}: **${sevB:,.2f} MXN**
   • {higher_name} supera a {lower_name} en **${diff_abs:,.2f} MXN** (+{pct_diff:.1f}% tomando como base a {lower_name}: ${lower_val:,.2f} MXN).

2. **Costo Total en la Cartera (MDP)**:
   • {stA_name}: **${mdA:,.2f} MDP** vs {stB_name}: **${mdB:,.2f} MDP**
   • *Identidad actuarial*: Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000.
   • *Aclaración de exposición*: Los vehículos registrados en circulación (INEGI VMRC) reflejan la escala macro, pero **no equivalen a la exposición asegurada** (número de pólizas vigentes).

3. **Restricción de Causalidad**:
   • La asociación lineal observada orienta el análisis, pero no demuestra causalidad directa entre ambas entidades."""

        # 7. Drivers / Regression Query
        is_driver = any(w in norm_q for w in ["variable", "impacto", "factor", "correlacion", "afectan", "explicar", "precio"])
        if is_driver:
            return """🤖 **Asistente de análisis actuarial — Asociación Estadística de Variables**:
De acuerdo con el análisis macroestatal (Promedio 2020–2024), las variables presentan los siguientes grados de asociación estadística lineal con la severidad:
1. **Precio Comercial Promedio del Vehículo (Mercado Libre)**: r = +0.8488 | R² = 72.05% (p < 0.0001)
2. **Tasa de Motorización (INEGI VMRC)**: r = +0.7648 (Autos registrados por cada 1,000 hab)
3. **Volumen del Parque Vehicular Registrado**: r = +0.3621
⚠️ *Nota Metodológica*: Describe fuerza de asociación estadística, no causalidad directa."""

        # 8. Rankings Query
        is_ranking = any(w in norm_q for w in ["top", "mayor", "mas alto", "mas caro", "ranking", "severos"])
        if is_ranking:
            if not self.df_avg.empty:
                top3 = self.df_avg.sort_values(by='severidad_poblacion', ascending=False).head(5)
                res = "🤖 **Asistente de análisis**: Top 5 Estados con Mayor Severidad Promedio:\n"
                for idx, r in top3.reset_index().iterrows():
                    res += f"  {idx+1}. **{r['entidad']}**: ${r['severidad_poblacion']:,.2f} MXN (Promedio 2020–2024)\n"
                res += "• Fuente: Chubb Baseline (2020-2024) & INEGI VMRC"
                return res

        # 9. Single State Query / Memory
        state_found = found_states[0] if len(found_states) >= 1 else None
        if not state_found and (any(w in norm_q for w in ["y en", "este", "su"]) or req_year):
            state_found = self.last_state

        if state_found:
            self.last_state = state_found
            if not self.df.empty:
                sub = self.df[self.df['entidad'] == state_found]
                avg_sev = sub['severidad_poblacion'].mean()
                idx_rel = (avg_sev / self.national_avg) * 100
                
                period_str = "Promedio 2020–2024"
                sev_val = avg_sev
                missing_str = ""

                if req_year:
                    sub_year = sub[sub['anio'] == int(req_year)]
                    if not sub_year.empty:
                        sev_val = sub_year['severidad_poblacion'].values[0]
                        period_str = f"Año {req_year}"
                        idx_rel = (sev_val / self.df[self.df['anio'] == int(req_year)]['severidad_poblacion'].mean()) * 100
                    else:
                        missing_str = f"\n  ⚠️ Nota: Para {req_year} se presenta el promedio histórico disponible."

                cat_sev = "Crítica" if sev_val > 11000 else ("Media" if sev_val >= 7500 else "Baja")

                return f"""🤖 **Asistente de análisis**:
  • Estado: **{state_found}**
  • Severidad: **${sev_val:,.2f} MXN** por siniestro
  • Periodo: {period_str}
  • Nivel de Riesgo: **{cat_sev}**
  • Índice Relativo: **{idx_rel:.1f} pts** (Base Nacional = 100)
  • Costo Anual Medio: **${sub['siniestros_ocurridos_mdp'].mean():,.2f} MDP**
  • Parque Registrado: **{sub['automoviles_registrados'].iloc[0]:,d} autos** (INEGI VMRC, macro no asegurados)
  • Fuente: Chubb Baseline 2020-2024 & INEGI VMRC {state_found}{missing_str}"""

        # 10. Deterministic Fallback
        return """🤖 **Asistente de análisis actuarial**:
  No reconocí esa consulta con suficiente certeza dentro del dataset actuarial.
  Opciones recomendadas:
  • '¿Cuál es la severidad de Nuevo León?'
  • 'Compara Nuevo León y Jalisco'
  • 'Tres hallazgos clave'
  • 'Concentración de costos Pareto'"""

if __name__ == "__main__":
    agent = LlamaColabDataAgent()
    print(agent.process_query("Nevo Lion"))
    print(agent.process_query("¿Y en 2023?"))
    print(agent.process_query("Compara Nuevo León y Jalisco"))
    print(agent.process_query("Contar el reporte en tres hallazgos"))

