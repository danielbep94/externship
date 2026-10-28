#!/usr/bin/env python3
"""
Validación de Salida del Asistente Actuarial
Contrasta cifras, unidades y restricciones contra los resultados autorizados.
"""

import sys
import re
import json
import pandas as pd
from ai_assistant_llm import LlamaColabDataAgent

def load_authorized_sources():
    with open('/Users/victordaniel/chubb/data.json', 'r', encoding='utf-8') as f:
        data_json = json.load(f)
    df_csv = pd.read_csv('/Users/victordaniel/chubb/output/df_analisis_completo.csv')
    return data_json, df_csv

def run_comprehensive_validation():
    data_json, df_csv = load_authorized_sources()
    agent = LlamaColabDataAgent()
    
    print("=" * 78)
    print("📋 EJECUCIÓN DEL PLAN DE VALIDACIÓN DE SALIDA — ASISTENTE ACTUARIAL")
    print("=" * 78)
    
    # Authorized ground truths from data.json
    nat_avg_auth = data_json["metadata"]["promedio_nacional_severidad"] # 6674.075...
    nat_mdp_auth = data_json["metadata"]["total_mdp_nacional_promedio"] # 90373.455...
    
    estados_dict = {e['entidad']: e for e in data_json['estados']}
    nl_data = estados_dict['Nuevo Leon']
    jal_data = estados_dict['Jalisco']
    oax_data = estados_dict['Oaxaca']
    tlax_data = estados_dict['Tlaxcala']
    
    nl_sev_auth = nl_data['severidad_promedio'] # 13970.61
    jal_sev_auth = jal_data['severidad_promedio'] # 10824.52
    jal_2024_auth = jal_data['severidad_2024'] # 13836.27
    oax_sev_auth = oax_data['severidad_promedio'] # 2039.42
    diff_nl_jal_auth = nl_sev_auth - jal_sev_auth # 3146.09
    ratio_auth = nl_sev_auth / oax_sev_auth # 6.85028...
    
    # Test matrix
    test_cases = [
        {
            "id": "VAL-CIF-01",
            "dimension": "Cifras Exactas",
            "query": "Tres hallazgos clave",
            "description": "Ratio de dispersión máxima (NL vs Oaxaca)",
            "expected_numeric": "6.85",
            "required_texts": ["6.85 veces", "13,970.61", "Oaxaca", "47.1%"],
            "forbidden_texts": ["3.8 veces", "3.8x"]
        },
        {
            "id": "VAL-CIF-02",
            "dimension": "Cifras Exactas",
            "query": "Compara Nuevo León y Jalisco",
            "description": "Severidades, diferencia absoluta y porcentual en comparativa biestatal",
            "expected_numeric": "3,146.09",
            "required_texts": ["13,970.61", "10,824.52", "3,146.09", "29.1%"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-03",
            "dimension": "Cifras Exactas & Categoría",
            "query": "Jalisco 2024",
            "description": "Severidad 2024 de Jalisco y categoría de severidad",
            "expected_numeric": "13,836.27",
            "required_texts": ["13,836.27", "Crítica"],
            "forbidden_texts": ["Media"]
        },
        {
            "id": "VAL-CIF-04",
            "dimension": "Cifras Exactas",
            "query": "Concentración de costos Pareto",
            "description": "Concentración del Top 5 en MDP y porcentaje nacional",
            "expected_numeric": "47.1%",
            "required_texts": ["47.1%", "42,562.44", "90,373.46"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-05",
            "dimension": "Cifras Exactas",
            "query": "¿Qué estados tienen mayor crecimiento?",
            "description": "Crecimiento acumulado y CAGR anual de Tlaxcala",
            "expected_numeric": "150.6%",
            "required_texts": ["Tlaxcala", "150.6%", "25.8%"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-06",
            "dimension": "Cifras Exactas",
            "query": "¿Qué variables afectan más la severidad?",
            "description": "Correlación de Pearson y R² del precio vehicular",
            "expected_numeric": "0.8488",
            "required_texts": ["0.8488", "72.05%"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-UNI-01",
            "dimension": "Unidades Estándar",
            "query": "¿Cuál es la severidad de Nuevo León?",
            "description": "Unidades explícitas de severidad (MXN por siniestro) e índice relativo (pts)",
            "expected_numeric": "MXN",
            "required_texts": ["MXN", "pts", "209.3"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-UNI-02",
            "dimension": "Unidades Estándar",
            "query": "Explicar volumen de costo total MDP",
            "description": "Definición y uso riguroso de la unidad MDP (Millones de Pesos)",
            "expected_numeric": "MDP",
            "required_texts": ["MDP", "Millones de Pesos", "90,373.46 MDP"],
            "forbidden_texts": []
        },
        {
            "id": "VAL-RES-01",
            "dimension": "Restricción Metodológica",
            "query": "Compara Nuevo León y Jalisco",
            "description": "Identidad actuarial y distinción: Parque Registrado INEGI != Exposición Asegurada",
            "expected_numeric": "Identidad",
            "required_texts": [
                "Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000",
                "no equivalen a la exposición asegurada",
                "INEGI VMRC"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-RES-02",
            "dimension": "Restricción Metodológica",
            "query": "¿La severidad alta es causada por autos caros?",
            "description": "Guardrail actuarial: Asociación estadística / correlación != Causalidad",
            "expected_numeric": "Causalidad",
            "required_texts": [
                "no implica causalidad",
                "asociación"
            ],
            "forbidden_texts": ["demuestra que los autos caros causan"]
        },
        {
            "id": "VAL-RES-03",
            "dimension": "Restricción Fuera de Ámbito",
            "query": "¿Cuál es el pronóstico del clima en Monterrey mañana?",
            "description": "Rechazo determinista de consultas fuera de ámbito (evitar alucinaciones)",
            "expected_numeric": "Rechazo",
            "required_texts": [
                "fuera del ámbito actuarial",
                "Dataset Actuarial de Severidad"
            ],
            "forbidden_texts": ["lluvia", "temperatura", "grados"]
        }
    ]
    
    passed_total = 0
    results_summary = []
    
    for tc in test_cases:
        response = agent.process_query(tc["query"])
        
        # Check required texts
        missing_reqs = [req for req in tc["required_texts"] if req.lower() not in response.lower()]
        
        # Check forbidden texts
        found_forb = [forb for forb in tc["forbidden_texts"] if forb.lower() in response.lower()]
        
        passed = (len(missing_reqs) == 0) and (len(found_forb) == 0)
        if passed:
            passed_total += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            
        results_summary.append({
            "id": tc["id"],
            "dimension": tc["dimension"],
            "description": tc["description"],
            "status": status,
            "missing": missing_reqs,
            "forbidden": found_forb
        })
        
        print(f"[{status}] {tc['id']} | {tc['dimension']} - {tc['description']}")
        if not passed:
            if missing_reqs:
                print(f"     ⚠️ Faltan cadenas requeridas: {missing_reqs}")
            if found_forb:
                print(f"     ⚠️ Se encontraron cadenas prohibidas: {found_forb}")
            print(f"     Respuesta obtenida: {response[:150]}...")
            
    print("=" * 78)
    print(f"RESULTADO FINAL: {passed_total}/{len(test_cases)} ({passed_total/len(test_cases)*100:.1f}%) APROBADOS")
    print("=" * 78)
    
    return passed_total == len(test_cases)

if __name__ == '__main__':
    success = run_comprehensive_validation()
    sys.exit(0 if success else 1)
