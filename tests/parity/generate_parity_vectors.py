"""
Generador de vectores de paridad Python -> Node.js (T1–T25)
Exporta tests/fixtures/parity_vectors.json para ser validado contra js/actuarial_engine.js en Node.
"""

import os
import sys
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'src'))
sys.path.insert(0, os.path.join(ROOT_DIR, 'tests'))

from actuarial_core import (
    ActuarialDataValidator,
    ActuarialOperationsEngine,
    format_number
)
from llm_grounding import GroundedActuarialAssistant
from test_executive_summary import make_synthetic_dataset


def build_vectors():
    data_path = os.path.join(ROOT_DIR, 'data.json')
    assistant = GroundedActuarialAssistant(data_path)
    engine = assistant.engine

    real_queries = [
        {"id": "T1", "query": "Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023"},
        {"id": "T2", "query": "Síntesis de CDMX, Puebla y Edomex en 2024"},
        {"id": "T3", "query": "Resumen ejecutivo de Jalisco para 2024"},
        {"id": "T5a", "query": "Tres hallazgos clave"},
        {"id": "T5b", "query": "Resumen nacional"},
        {"id": "T5c", "query": "Contar el reporte en tres hallazgos"},
        {"id": "T6", "query": "Resumen ejecutivo de Nuevo León y Jalisco"},
        {"id": "T9", "query": "Resumen de CDMX y Ciudad de México 2023"},
        {"id": "T10", "query": "Resumen de NL, Nuevo León y Jalisco 2023"},
        {"id": "T11", "query": "Compara CDMX y Ciudad de México"},
        {"id": "T12", "query": "Resumen nacional de Jalisco 2024"},
        {"id": "T13a", "query": "Ejecutivo de Jalisco 2024"},
        {"id": "T13b", "query": "Ver Jalisco en el reporte"},
        {"id": "T13c", "query": "¿Qué presumen en Jalisco?"},
        {"id": "T14a", "query": "Genera un reporte de Jalisco 2024"},
        {"id": "T14b", "query": "Dame un informe de NL y Jalisco 2023"},
        {"id": "T15", "query": "Resumen de Jalisco 2020 y 2024"},
        {"id": "T16", "query": "Resumen ejecutivo de Jalisco para 2020"}
    ]

    real_cases = []
    for item in real_queries:
        fresh_assistant = GroundedActuarialAssistant(data_path)
        ir = fresh_assistant.parser.parse_to_structured_json(item["query"])
        summary = None
        if ir["intent"] in ("executive_multistate_summary", "executive_single_state_summary"):
            summary = engine.compute_executive_summary(ir["states"], ir["target_year"])
        real_cases.append({
            "id": item["id"],
            "query": item["query"],
            "ir": ir,
            "summary": summary
        })

    # Casos sintéticos T17–T24
    synth_specs = [
        ("T17", ["Estado A", "Estado B", "Estado C"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 300.0}},
        ]),
        ("T18", ["Estado A", "Estado B", "Estado C"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}, "yearly_mdp": {"2023": 10.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}, "yearly_mdp": {"2023": 20.0}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": None}, "yearly_mdp": {"2023": 30.0}},
        ]),
        ("T19", ["Estado A", "Estado B", "Estado C"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}, "yearly_mdp": {"2023": 10.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}, "yearly_mdp": {"2023": "__DELETE__"}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 300.0}, "yearly_mdp": {"2023": 30.0}},
        ]),
        ("T20", ["Estado A", "Estado B"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2020": 0.0, "2023": 150.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2020": 100.0, "2023": 250.0}},
        ]),
        ("T21", ["Estado A", "Estado B"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2023": None}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": None}},
        ]),
        ("T22", ["E1", "E2", "E3", "E4"], 2023, [
            {"entidad": "E1", "severidad_promedio": 11000.00, "yearly_severidad": {"2023": 11000.00}},
            {"entidad": "E2", "severidad_promedio": 10999.99, "yearly_severidad": {"2023": 10999.99}},
            {"entidad": "E3", "severidad_promedio": 7500.00, "yearly_severidad": {"2023": 7500.00}},
            {"entidad": "E4", "severidad_promedio": 7499.99, "yearly_severidad": {"2023": 7499.99}},
        ]),
        ("T23", ["Estado A"], 2023, [
            {
                "entidad": "Estado A",
                "severidad_promedio": 12000.0,
                "categoria_severidad": "Critica",
                "yearly_severidad": {"2023": 12000.0},
                "yearly_categoria": {"2023": "__DELETE__"}
            }
        ]),
        ("T24", ["Estado A", "Estado B", "Estado C"], 2023, [
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.004}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 100.001}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 90.00}},
        ]),
    ]

    synthetic_cases = []
    for cid, states, yr, overrides in synth_specs:
        sdata = make_synthetic_dataset(overrides)
        seng = ActuarialOperationsEngine(sdata)
        ssum = seng.compute_executive_summary(states, yr)
        synthetic_cases.append({
            "id": cid,
            "states": states,
            "target_year": yr,
            "dataset": sdata,
            "summary": ssum
        })

    formatter_cases = [
        {"val": v, "decimals": 2, "expected": format_number(v, 2)}
        for v in [0.125, 1.005, 2.675, 9.995, -0.125, -0.004, 1234567.895, 1e-7, 1e16]
    ] + [
        {"val": v, "decimals": 1, "expected": format_number(v, 1)}
        for v in [0.05, 0.25, -0.05]
    ]

    out_dir = os.path.join(ROOT_DIR, 'tests', 'fixtures')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'parity_vectors.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            "real_cases": real_cases,
            "synthetic_cases": synthetic_cases,
            "formatter_cases": formatter_cases
        }, f, ensure_ascii=False, indent=2)
    print(f"Vectores de paridad generados exitosamente en {out_path}")


if __name__ == '__main__':
    build_vectors()
