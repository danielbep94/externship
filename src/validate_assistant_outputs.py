#!/usr/bin/env python3
"""
Validación de Salida del Asistente Actuarial (Auditoría Técnica Dinámica)
Contrasta cifras, unidades y restricciones contra fuentes autorizadas (data.json),
garantizando CERO cifras hardcodeadas en la suite de pruebas.
"""

import sys
import re
import json
from ai_assistant_llm import LlamaColabDataAgent
from actuarial_core import ActuarialDataValidator

def load_authorized_sources():
    data_json = ActuarialDataValidator.load_and_validate('/Users/victordaniel/chubb/data.json')
    return data_json

def run_comprehensive_validation():
    data_json = load_authorized_sources()
    agent = LlamaColabDataAgent()
    
    print("=" * 82)
    print("📋 AUDITORÍA TÉCNICA DE VALIDACIÓN DE SALIDA — FUENTE CANÓNICA data.json")
    print("=" * 82)
    
    # 1. Extracción dinámica de la verdad autorizada (SSOT)
    nat_avg_auth = data_json["metadata"]["promedio_nacional_severidad"]
    nat_mdp_auth = data_json["metadata"]["total_mdp_nacional_promedio"]
    
    estados_dict = {e['entidad']: e for e in data_json['estados']}
    nl_data = estados_dict['Nuevo Leon']
    jal_data = estados_dict['Jalisco']
    oax_data = estados_dict['Oaxaca']
    tlax_data = estados_dict['Tlaxcala']
    
    nl_sev_auth = nl_data['severidad_promedio']
    jal_sev_auth = jal_data['severidad_promedio']
    nl_2023_auth = nl_data['yearly_severidad']['2023']
    jal_2023_auth = jal_data['yearly_severidad']['2023']
    nl_2024_auth = nl_data['yearly_severidad']['2024']
    jal_2024_auth = jal_data['yearly_severidad']['2024']
    jal_2024_cat = jal_data['yearly_categoria']['2024']
    jal_2024_cat_display = "Crítica" if jal_2024_cat in ["Critica", "Crítica"] else jal_2024_cat
    ref_2023_auth = sum(s['yearly_severidad']['2023'] for s in data_json['estados']) / len(data_json['estados'])
    ref_2024_auth = sum(s['yearly_severidad']['2024'] for s in data_json['estados']) / len(data_json['estados'])

    oax_sev_auth = oax_data['severidad_promedio']
    diff_nl_jal_auth = abs(nl_sev_auth - jal_sev_auth)
    pct_diff_nl_jal = (diff_nl_jal_auth / min(nl_sev_auth, jal_sev_auth)) * 100.0
    ratio_auth = nl_sev_auth / oax_sev_auth

    # Cálculo dinámico de Pareto Top 5
    sorted_mdp = sorted(data_json['estados'], key=lambda x: x['siniestros_ocurridos_mdp_promedio'], reverse=True)
    top5_mdp_sum = sum(s['siniestros_ocurridos_mdp_promedio'] for s in sorted_mdp[:5])
    pareto_pct_auth = (top5_mdp_sum / nat_mdp_auth) * 100.0

    # Crecimiento dinámico Tlaxcala
    tlax_cagr_total = tlax_data['cagr_2020_2024_pct']
    tlax_cagr_anual = (pow(1 + tlax_cagr_total / 100.0, 1/4) - 1) * 100.0

    # Estadísticas dinámicas de regresión
    r_auth = data_json['scatter_stats']['r_pearson']
    r2_pct_auth = data_json['scatter_stats']['r2_score'] * 100.0

    # 2. Matriz de pruebas 100% dinámica (sin cifras hardcodeadas)
    test_cases = [
        {
            "id": "VAL-CIF-01",
            "dimension": "Cifras Dinámicas",
            "query": "Tres hallazgos clave",
            "description": "Ratio de dispersión máxima y Pareto dinámico desde data.json",
            "required_texts": [
                f"{ratio_auth:.2f}",
                f"{nl_sev_auth:,.2f}",
                "Oaxaca",
                f"{pareto_pct_auth:.1f}%"
            ],
            "forbidden_texts": ["3.8 veces", "3.8x"]
        },
        {
            "id": "VAL-CIF-02",
            "dimension": "Cifras Dinámicas",
            "query": "Compara Nuevo León y Jalisco",
            "description": "Severidades y brecha exacta calculada en tiempo real",
            "required_texts": [
                f"{nl_sev_auth:,.2f}",
                f"{jal_sev_auth:,.2f}",
                f"{diff_nl_jal_auth:,.2f}",
                f"{pct_diff_nl_jal:.1f}%"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-03",
            "dimension": "Cifras & Categoría Dinámica",
            "query": "Jalisco 2024",
            "description": "Severidad 2024 y categoría oficial de Jalisco desde data.json",
            "required_texts": [
                f"{jal_2024_auth:,.2f}",
                jal_2024_cat_display
            ],
            "forbidden_texts": ["Media"]
        },
        {
            "id": "VAL-CIF-04",
            "dimension": "Cifras Dinámicas",
            "query": "Concentración de costos Pareto",
            "description": "Volumen agregado y porcentaje del Top 5 dinámico",
            "required_texts": [
                f"{pareto_pct_auth:.1f}%",
                f"{top5_mdp_sum:,.2f}",
                f"{nat_mdp_auth:,.2f}"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-05",
            "dimension": "Cifras Dinámicas",
            "query": "¿Qué estados tienen mayor crecimiento?",
            "description": "Crecimiento acumulado y CAGR anual del líder dinámico",
            "required_texts": [
                tlax_data['entidad'],
                f"{tlax_cagr_total:.1f}%",
                f"{tlax_cagr_anual:.1f}%"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-CIF-06",
            "dimension": "Cifras Dinámicas",
            "query": "¿Qué variables afectan más la severidad?",
            "description": "Coeficientes de correlación y determinación dinámicos de scatter_stats",
            "required_texts": [
                f"{r_auth:.4f}",
                f"{r2_pct_auth:.2f}%"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-UNI-01",
            "dimension": "Unidades Estándar",
            "query": "¿Cuál es la severidad de Nuevo León?",
            "description": "Unidades de severidad (MXN por siniestro) e índice relativo (pts)",
            "required_texts": [
                "MXN",
                "pts",
                f"{nl_data['indice_severidad']:.1f}"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-UNI-02",
            "dimension": "Unidades Estándar",
            "query": "Explicar volumen de costo total MDP",
            "description": "Uso formal de MDP (Millones de Pesos) y cifra nacional",
            "required_texts": [
                "MDP",
                "Millones de Pesos",
                f"{nat_mdp_auth:,.2f} MDP"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-RES-01",
            "dimension": "Restricción Metodológica",
            "query": "Compara Nuevo León y Jalisco",
            "description": "Identidad actuarial obligatoria y Parque INEGI != Exposición Asegurada",
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
            "description": "Rechazo determinista sin alucinaciones para consultas fuera de dominio",
            "required_texts": [
                "fuera del ámbito actuarial",
                "Dataset Actuarial de Severidad"
            ],
            "forbidden_texts": ["lluvia", "temperatura", "grados", "soleado"]
        },
        {
            "id": "VAL-EXEC-01",
            "dimension": "Resumen Ejecutivo Multistate (2023)",
            "query": "Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023",
            "description": "Resumen ejecutivo 2023 con referencia nacional, rankings, brecha y evolución 2020->2023",
            "required_texts": [
                f"{ref_2023_auth:,.2f} MXN (n = 32)",
                f"{nl_2023_auth:,.2f} MXN",
                f"{jal_2023_auth:,.2f} MXN",
                "35 % de exposición × 30 % de frecuencia"
            ],
            "forbidden_texts": []
        },
        {
            "id": "VAL-EXEC-02",
            "dimension": "Resumen Ejecutivo Año Omitido (Default 2024)",
            "query": "Resumen ejecutivo de Nuevo León y Jalisco",
            "description": "Usa 2024 como año predeterminado con aviso explícito y cifras dinámicas de 2024",
            "required_texts": [
                "No indicaste año; uso 2024, último año disponible.",
                f"{ref_2024_auth:,.2f} MXN (n = 32)",
                f"{nl_2024_auth:,.2f} MXN",
                f"{jal_2024_auth:,.2f} MXN"
            ],
            "forbidden_texts": []
        }
    ]
    
    passed_total = 0
    results_summary = []
    
    for tc in test_cases:
        response = agent.process_query(tc["query"])
        
        # Check required texts (case-insensitive)
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
            
    print("=" * 82)
    print(f"RESULTADO DE AUDITORÍA: {passed_total}/{len(test_cases)} ({passed_total/len(test_cases)*100:.1f}%) APROBADOS CONTRA data.json")
    print("=" * 82)
    
    return passed_total == len(test_cases)

if __name__ == '__main__':
    success = run_comprehensive_validation()
    sys.exit(0 if success else 1)
