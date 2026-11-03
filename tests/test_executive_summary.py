"""
Suite de Pruebas Unitarias y de Integración para Resumen Ejecutivo (T1–T25)
Valida todas las reglas de Plan v3:
- T1–T16: Enrutamiento, alias, deduplicación, memoria, año por defecto (2024) y cálculos con data.json real.
- T17–T24: Fixtures sintéticos con resultados independientes calculados a mano (faltantes, empate al centavo, umbrales, base 2020 = 0).
- T25: Formateador determinista ROUND_HALF_UP en casos frontera IEEE-754.
"""

import os
import sys
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from actuarial_core import (
    ActuarialDataValidator,
    ActuarialCatalog,
    ConversationMemoryManager,
    ActuarialOperationsEngine,
    format_number,
    normalize_text,
    compute_category_from_rule,
    display_category_label
)
from llm_grounding import (
    ActuarialQueryParser,
    GroundedActuarialAssistant
)


def make_synthetic_dataset(states_overrides):
    """Construye un dataset sintético válido para probar casos borde (T17–T24) sin tocar data.json."""
    estados = []
    for idx, ov in enumerate(states_overrides):
        ent = ov["entidad"]
        sev_prom = ov.get("severidad_promedio", 9000.0)
        cat_prom = ov.get("categoria_severidad", compute_category_from_rule(sev_prom) or "Media")
        y_sev = {
            "2020": 100.0,
            "2021": 120.0,
            "2022": 150.0,
            "2023": 200.0,
            "2024": 250.0
        }
        if "yearly_severidad" in ov:
            y_sev.update(ov["yearly_severidad"])
            for k in list(y_sev.keys()):
                if k in ov["yearly_severidad"] and ov["yearly_severidad"][k] == "__DELETE__":
                    del y_sev[k]

        y_mdp = {
            "2020": 50.0,
            "2021": 60.0,
            "2022": 70.0,
            "2023": 80.0,
            "2024": 100.0
        }
        if "yearly_mdp" in ov:
            y_mdp.update(ov["yearly_mdp"])
            for k in list(y_mdp.keys()):
                if k in ov["yearly_mdp"] and ov["yearly_mdp"][k] == "__DELETE__":
                    del y_mdp[k]

        y_cat = {}
        for yr, sv in y_sev.items():
            c = compute_category_from_rule(sv) if (sv is not None and sv > 0) else None
            y_cat[yr] = c
        if "yearly_categoria" in ov:
            y_cat.update(ov["yearly_categoria"])
            for k in list(y_cat.keys()):
                if k in ov["yearly_categoria"] and ov["yearly_categoria"][k] == "__DELETE__":
                    del y_cat[k]

        estados.append({
            "cve_ent": f"{idx + 1:02d}",
            "entidad": ent,
            "severidad_promedio": sev_prom,
            "siniestros_ocurridos_mdp_promedio": ov.get("mdp_promedio", 100.0),
            "poblacion_2020": 1000000,
            "automoviles_registrados": 300000,
            "area_km2": 10000.0,
            "precio_promedio_auto_ml_k_mxn": 250.0,
            "precio_gasolina_reg_prom": 22.0,
            "autos_por_1000_hab": 300.0,
            "densidad_poblacional": 100.0,
            "cagr_2020_2024_pct": 50.0,
            "yearly_severidad": y_sev,
            "yearly_mdp": y_mdp,
            "yearly_categoria": y_cat,
            "indice_severidad": (sev_prom / 9000.0) * 100.0 if sev_prom else None,
            "pct_costo_nacional": 100.0 / len(states_overrides),
            "categoria_severidad": cat_prom
        })

    raw = {
        "metadata": {
            "titulo": "Dataset Sintético de Prueba",
            "periodo": "2020-2024",
            "promedio_nacional_severidad": 9000.0,
            "total_mdp_nacional_promedio": 100.0 * len(states_overrides),
            "fechas_corte": {"chubb": "2024"}
        },
        "estados": estados,
        "scatter_stats": {
            "r_pearson": 0.8488,
            "r2_score": 0.7205,
            "p_value": 0.0001,
            "slope": 50.0,
            "intercept": -1000.0,
            "formula": "y = 50x - 1000"
        }
    }
    return ActuarialDataValidator.validate_data_dict(raw, allow_synthetic=True)


class TestExecutiveSummary(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data_path = '/Users/victordaniel/chubb/data.json'
        with open(cls.data_path, 'r', encoding='utf-8') as f:
            cls.raw_json = json.load(f)
        cls.raw_states_by_name = {s["entidad"]: s for s in cls.raw_json["estados"]}

    def setUp(self):
        self.assistant = GroundedActuarialAssistant(self.data_path)
        self.parser = self.assistant.parser
        self.engine = self.assistant.engine

    # =========================================================================
    # DATOS REALES (T1–T16)
    # =========================================================================
    def test_T1_multistate_nl_jalisco_2023(self):
        """T1: 'Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023'"""
        q = "Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_multistate_summary")
        self.assertEqual(ir["states"], ["Nuevo Leon", "Jalisco"])
        self.assertEqual(ir["states_raw"], ["Nuevo León", "Jalisco"])
        self.assertEqual(ir["target_year"], 2023)
        self.assertEqual(ir["year_source"], "explicit")
        self.assertEqual(ir["ranking_scope"], ["national", "selection"])

        summary = self.engine.compute_executive_summary(ir["states"], ir["target_year"])
        self.assertEqual(summary["national_reference"]["value_fmt"], "7,805.92")
        self.assertEqual(summary["national_reference"]["n"], 32)

        nl, jal = summary["rows"][0], summary["rows"][1]
        self.assertEqual(nl["severidad_fmt"], "16,477.15")
        self.assertEqual(nl["indice_fmt"], "211.1")
        self.assertEqual(nl["categoria"], "Crítica")
        self.assertEqual((nl["rank_nacional_severidad"], nl["n_nacional_severidad"]), (1, 32))
        self.assertEqual(nl["costo_mdp_fmt"], "10,007.67")
        self.assertEqual((nl["rank_nacional_mdp"], nl["n_nacional_mdp"]), (4, 32))
        self.assertEqual(nl["var_severidad_fmt"], "+72.5 %")
        self.assertEqual(nl["var_mdp_fmt"], "+72.5 %")
        self.assertEqual(nl["delta_indice_fmt"], "-0.7 pts")

        self.assertEqual(jal["severidad_fmt"], "12,131.95")
        self.assertEqual(jal["indice_fmt"], "155.4")
        self.assertEqual(jal["categoria"], "Crítica")
        self.assertEqual((jal["rank_nacional_severidad"], jal["n_nacional_severidad"]), (5, 32))
        self.assertEqual(jal["costo_mdp_fmt"], "10,634.33")
        self.assertEqual((jal["rank_nacional_mdp"], jal["n_nacional_mdp"]), (3, 32))
        self.assertEqual(jal["var_severidad_fmt"], "+53.0 %")
        self.assertEqual(jal["var_mdp_fmt"], "+53.0 %")
        self.assertEqual(jal["delta_indice_fmt"], "-20.4 pts")

        sel = summary["selection_summary"]
        self.assertEqual(sel["brecha_severidad_abs_fmt"], "4,345.20")
        self.assertEqual(sel["brecha_severidad_pct_fmt"], "35.8")
        self.assertEqual(sel["brecha_mdp_abs_fmt"], "626.67")
        self.assertTrue(sel["lideres_difieren"])

        resp = self.assistant.ask(q)
        self.assertIn("16,477.15", resp)
        self.assertIn("12,131.95", resp)
        self.assertIn("7,805.92 MXN (n = 32)", resp)
        self.assertIn("35 % de exposición × 30 % de frecuencia", resp)

    def test_T2_sintesis_cdmx_puebla_edomex_2024(self):
        """T2: 'Síntesis de CDMX, Puebla y Edomex en 2024'"""
        q = "Síntesis de CDMX, Puebla y Edomex en 2024"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_multistate_summary")
        self.assertEqual(ir["states"], ["Ciudad de Mexico", "Puebla", "Estado de Mexico"])
        self.assertEqual(ir["target_year"], 2024)

        summary = self.engine.compute_executive_summary(ir["states"], 2024)
        cdmx, pue, edomex = summary["rows"]

        self.assertEqual(cdmx["severidad_fmt"], "14,112.41")
        self.assertEqual(cdmx["indice_fmt"], "156.1")
        self.assertEqual(cdmx["categoria"], "Crítica")
        self.assertEqual(cdmx["rank_nacional_severidad"], 4)
        self.assertEqual(cdmx["costo_mdp_fmt"], "13,647.32")
        self.assertEqual(cdmx["rank_nacional_mdp"], 2)

        self.assertEqual(pue["severidad_fmt"], "7,268.42")
        self.assertEqual(pue["indice_fmt"], "80.4")
        self.assertEqual(pue["categoria"], "Baja")
        self.assertEqual(pue["rank_nacional_severidad"], 21)
        self.assertEqual(pue["costo_mdp_fmt"], "5,024.25")
        self.assertEqual(pue["rank_nacional_mdp"], 5)

        self.assertEqual(edomex["severidad_fmt"], "8,105.33")
        self.assertEqual(edomex["indice_fmt"], "89.6")
        self.assertEqual(edomex["categoria"], "Media")
        self.assertEqual(edomex["rank_nacional_severidad"], 16)
        self.assertEqual(edomex["costo_mdp_fmt"], "14,461.57")
        self.assertEqual(edomex["rank_nacional_mdp"], 1)

        sel = summary["selection_summary"]
        self.assertEqual(sel["lider_severidad"], "Ciudad de Mexico")
        self.assertEqual(sel["lider_mdp"], "Estado de Mexico")

    def test_T3_single_state_jalisco_2024(self):
        """T3: 'Resumen ejecutivo de Jalisco para 2024'"""
        q = "Resumen ejecutivo de Jalisco para 2024"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_single_state_summary")
        self.assertEqual(ir["states"], ["Jalisco"])
        self.assertEqual(ir["ranking_scope"], ["national"])

        summary = self.engine.compute_executive_summary(["Jalisco"], 2024)
        self.assertIsNone(summary["selection_summary"])
        jal = summary["rows"][0]
        self.assertEqual(jal["severidad_fmt"], "13,836.27")
        self.assertEqual(jal["indice_fmt"], "153.0")
        self.assertEqual(jal["categoria"], "Crítica")
        self.assertEqual(jal["rank_nacional_severidad"], 5)
        self.assertEqual(jal["costo_mdp_fmt"], "12,128.27")
        self.assertEqual(jal["rank_nacional_mdp"], 3)
        self.assertEqual(jal["var_severidad_fmt"], "+74.5 %")
        self.assertEqual(jal["delta_indice_fmt"], "-22.8 pts")

    def test_T4_out_of_range_2018_preserves_memory(self):
        """T4: Después de T1: 'Resumen de NL y Jalisco para 2018'"""
        self.assistant.ask("Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023")
        self.assertEqual(self.assistant.memory.confirmed_year, 2023)

        q2 = "Resumen de NL y Jalisco para 2018"
        ir2 = self.parser.parse_to_structured_json(q2)
        self.assertEqual(ir2["intent"], "temporal_out_of_range")
        resp2 = self.assistant.ask(q2)
        self.assertIn("2018", resp2)
        self.assertIn("2020–2024", resp2)
        self.assertNotIn("16,477.15", resp2)
        self.assertEqual(self.assistant.memory.confirmed_year, 2023)

    def test_T5_three_findings_routing(self):
        """T5: 'Tres hallazgos clave' · 'Resumen nacional' · 'Contar el reporte en tres hallazgos'"""
        for q in ["Tres hallazgos clave", "Resumen nacional", "Contar el reporte en tres hallazgos"]:
            ir = self.parser.parse_to_structured_json(q)
            self.assertEqual(ir["intent"], "three_findings", f"Falló para: {q}")

    def test_T6_omitted_year_defaults_to_2024(self):
        """T6: 'Resumen ejecutivo de Nuevo León y Jalisco' (sesión nueva)"""
        q = "Resumen ejecutivo de Nuevo León y Jalisco"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_multistate_summary")
        self.assertEqual(ir["target_year"], 2024)
        self.assertEqual(ir["year_source"], "default")
        self.assertIn("No indicaste año; uso 2024, último año disponible.", ir["interpretation_notes"])

        summary = self.engine.compute_executive_summary(ir["states"], 2024)
        self.assertEqual(summary["national_reference"]["value_fmt"], "9,041.64")
        self.assertEqual(summary["rows"][0]["severidad_fmt"], "18,804.45")
        self.assertEqual(summary["rows"][0]["indice_fmt"], "208.0")
        self.assertEqual(summary["rows"][1]["severidad_fmt"], "13,836.27")
        self.assertEqual(summary["rows"][1]["indice_fmt"], "153.0")

    def test_T7_continuation_query_inherits_memory_year(self):
        """T7: Después de T1: '¿Y el resumen de Puebla?'"""
        self.assistant.ask("Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023")
        q2 = "¿Y el resumen de Puebla?"
        ir2 = self.parser.parse_to_structured_json(q2)
        self.assertEqual(ir2["intent"], "executive_single_state_summary")
        self.assertEqual(ir2["states"], ["Puebla"])
        self.assertEqual(ir2["target_year"], 2023)
        self.assertEqual(ir2["year_source"], "memory")

        summary = self.engine.compute_executive_summary(["Puebla"], 2023)
        raw_pue_2023 = self.raw_states_by_name["Puebla"]["yearly_severidad"]["2023"]
        self.assertAlmostEqual(summary["rows"][0]["severidad"], raw_pue_2023, places=9)
        self.assertEqual(summary["rows"][0]["severidad_fmt"], format_number(raw_pue_2023, 2))

    def test_T8_non_continuation_query_uses_default_2024(self):
        """T8: Después de T1: 'Resumen ejecutivo de Puebla'"""
        self.assistant.ask("Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023")
        q2 = "Resumen ejecutivo de Puebla"
        ir2 = self.parser.parse_to_structured_json(q2)
        self.assertEqual(ir2["intent"], "executive_single_state_summary")
        self.assertEqual(ir2["target_year"], 2024)
        self.assertEqual(ir2["year_source"], "default")

    def test_T9_duplicate_entity_mentions_single_summary(self):
        """T9: 'Resumen de CDMX y Ciudad de México 2023'"""
        q = "Resumen de CDMX y Ciudad de México 2023"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_single_state_summary")
        self.assertEqual(ir["states"], ["Ciudad de Mexico"])
        self.assertEqual(ir["duplicate_mentions"], ["CDMX", "Ciudad de México"])
        self.assertTrue(any("corresponden a la misma entidad" in n for n in ir["interpretation_notes"]))

    def test_T10_duplicate_plus_other_entity_multistate(self):
        """T10: 'Resumen de NL, Nuevo León y Jalisco 2023'"""
        q = "Resumen de NL, Nuevo León y Jalisco 2023"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_multistate_summary")
        self.assertEqual(ir["states"], ["Nuevo Leon", "Jalisco"])
        summary = self.engine.compute_executive_summary(ir["states"], 2023)
        self.assertEqual(summary["rows"][0]["severidad_fmt"], "16,477.15")
        self.assertEqual(summary["rows"][1]["severidad_fmt"], "12,131.95")

    def test_T11_comparison_duplicate_does_not_become_summary(self):
        """T11: 'Compara CDMX y Ciudad de México'"""
        q = "Compara CDMX y Ciudad de México"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "multi_state_comparison")
        self.assertTrue(ir["insufficient_entities"])
        resp = self.assistant.ask(q)
        self.assertIn("indica otra entidad para comparar", resp)
        self.assertNotIn("Resumen ejecutivo", resp)

    def test_T12_resumen_nacional_de_jalisco_2024(self):
        """T12: 'Resumen nacional de Jalisco 2024'"""
        q = "Resumen nacional de Jalisco 2024"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_single_state_summary")
        self.assertEqual(ir["states"], ["Jalisco"])
        self.assertTrue(any("comparado con la media de las entidades con dato" in n for n in ir["interpretation_notes"]))
        summary = self.engine.compute_executive_summary(["Jalisco"], 2024)
        self.assertEqual(summary["rows"][0]["severidad_fmt"], "13,836.27")

    def test_T13_non_triggers_do_not_activate_summary(self):
        """T13: 'Ejecutivo de Jalisco 2024' · 'Ver Jalisco en el reporte' · '¿Qué presumen en Jalisco?'"""
        for q in ["Ejecutivo de Jalisco 2024", "Ver Jalisco en el reporte", "¿Qué presumen en Jalisco?"]:
            ir = self.parser.parse_to_structured_json(q)
            self.assertNotIn(ir["intent"], ("executive_single_state_summary", "executive_multistate_summary"), f"Activó resumen indebidamente: {q}")

    def test_T14_weak_triggers_with_creation_verbs(self):
        """T14: 'Genera un reporte de Jalisco 2024' · 'Dame un informe de NL y Jalisco 2023'"""
        ir1 = self.parser.parse_to_structured_json("Genera un reporte de Jalisco 2024")
        self.assertEqual(ir1["intent"], "executive_single_state_summary")
        self.assertEqual(ir1["states"], ["Jalisco"])
        self.assertEqual(ir1["target_year"], 2024)

        ir2 = self.parser.parse_to_structured_json("Dame un informe de NL y Jalisco 2023")
        self.assertEqual(ir2["intent"], "executive_multistate_summary")
        self.assertEqual(ir2["states"], ["Nuevo Leon", "Jalisco"])
        self.assertEqual(ir2["target_year"], 2023)

        # Consultas exactas reportadas por el usuario en navegador:
        ir3 = self.parser.parse_to_structured_json("resume ejectivo de ciudad de mexico para 2020")
        self.assertEqual(ir3["intent"], "executive_single_state_summary")
        self.assertEqual(ir3["states"], ["Ciudad de Mexico"])
        self.assertEqual(ir3["target_year"], 2020)

        ir4 = self.parser.parse_to_structured_json("crea una explicación de los datos de Ciudad de México severidad para el año 2024")
        self.assertEqual(ir4["intent"], "executive_single_state_summary")
        self.assertEqual(ir4["states"], ["Ciudad de Mexico"])
        self.assertEqual(ir4["target_year"], 2024)

    def test_T15_multiple_years_clarification(self):
        """T15: 'Resumen de Jalisco 2020 y 2024'"""
        q = "Resumen de Jalisco 2020 y 2024"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "clarification_year")
        resp = self.assistant.ask(q)
        self.assertIn("un solo año", resp)
        self.assertNotIn("13,836.27", resp)

    def test_T16_jalisco_base_year_2020(self):
        """T16: 'Resumen ejecutivo de Jalisco para 2020'"""
        q = "Resumen ejecutivo de Jalisco para 2020"
        ir = self.parser.parse_to_structured_json(q)
        self.assertEqual(ir["intent"], "executive_single_state_summary")
        self.assertEqual(ir["target_year"], 2020)

        summary = self.engine.compute_executive_summary(["Jalisco"], 2020)
        jal = summary["rows"][0]
        self.assertEqual(jal["var_severidad_fmt"], "0.0 %")
        self.assertEqual(jal["var_mdp_fmt"], "0.0 %")
        self.assertEqual(jal["delta_indice_fmt"], "0.0 pts")
        self.assertEqual(jal["indice_fmt"], "175.8")
        self.assertEqual(jal["categoria"], "Media")

    # =========================================================================
    # FIXTURES SINTÉTICOS (T17–T24)
    # =========================================================================
    def test_T17_synthetic_exact_hand_calculated_indices(self):
        """T17: A, B, C con severidad 2023 = 100, 200, 300 -> ref 200.00 (n=3), índices 50.0 / 100.0 / 150.0"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 300.0}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B", "Estado C"], 2023)
        self.assertEqual(res["national_reference"]["value_fmt"], "200.00")
        self.assertEqual(res["national_reference"]["n"], 3)
        self.assertEqual([r["indice_fmt"] for r in res["rows"]], ["50.0", "100.0", "150.0"])

    def test_T18_synthetic_missing_severity_preserves_mdp(self):
        """T18: Igual que T17, pero C con null en severidad 2023"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}, "yearly_mdp": {"2023": 10.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}, "yearly_mdp": {"2023": 20.0}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": None}, "yearly_mdp": {"2023": 30.0}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B", "Estado C"], 2023)
        self.assertEqual(res["national_reference"]["value_fmt"], "150.00")
        self.assertEqual(res["national_reference"]["n"], 2)

        rA, rB, rC = res["rows"]
        self.assertEqual(rA["indice_fmt"], "66.7")
        self.assertEqual(rB["indice_fmt"], "133.3")
        self.assertEqual((rB["rank_nacional_severidad"], rB["n_nacional_severidad"]), (1, 2))
        self.assertEqual((rA["rank_nacional_severidad"], rA["n_nacional_severidad"]), (2, 2))

        self.assertIsNone(rC["severidad"])
        self.assertEqual(rC["severidad_fmt"], "sin dato")
        self.assertEqual(rC["indice_fmt"], "no calculable")
        self.assertEqual(rC["categoria"], "sin dato")
        self.assertIsNone(rC["rank_nacional_severidad"])
        # Su MDP sí se muestra y lidera el ranking de MDP (1 de 3)
        self.assertEqual(rC["costo_mdp_fmt"], "30.00")
        self.assertEqual((rC["rank_nacional_mdp"], rC["n_nacional_mdp"]), (1, 3))

    def test_T19_synthetic_missing_mdp_preserves_severity(self):
        """T19: B sin yearly_mdp['2023']"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.0}, "yearly_mdp": {"2023": 10.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 200.0}, "yearly_mdp": {"2023": "__DELETE__"}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 300.0}, "yearly_mdp": {"2023": 30.0}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B", "Estado C"], 2023)
        rB = res["rows"][1]
        self.assertEqual(rB["costo_mdp_fmt"], "sin dato")
        self.assertEqual(rB["var_mdp_fmt"], "no calculable")
        self.assertIsNone(rB["rank_nacional_mdp"])
        self.assertEqual(rB["n_nacional_mdp"], 2)
        # Severidad, índice y categoría de B normales
        self.assertEqual(rB["severidad_fmt"], "200.00")
        self.assertEqual(rB["indice_fmt"], "100.0")
        self.assertEqual(rB["categoria"], "Baja")

    def test_T20_synthetic_zero_base_2020(self):
        """T20: A con severidad 2020 = 0 -> Variación de severidad y Δíndice de A 'no calculable'; índice 2023 válido"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2020": 0.0, "2023": 150.0}},
            {"entidad": "Estado B", "yearly_severidad": {"2020": 100.0, "2023": 250.0}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B"], 2023)
        rA = res["rows"][0]
        self.assertEqual(rA["var_severidad_fmt"], "no calculable")
        self.assertEqual(rA["delta_indice_fmt"], "no calculable")
        self.assertEqual(rA["indice_fmt"], "75.0")

    def test_T21_synthetic_all_severities_null_in_year(self):
        """T21: Todas las severidades 2023 en null"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2023": None}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": None}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B"], 2023)
        self.assertIsNone(res["national_reference"]["value"])
        self.assertEqual(res["national_reference"]["value_fmt"], "no calculable")
        self.assertTrue(res["all_severidad_missing"])
        for r in res["rows"]:
            self.assertEqual(r["indice_fmt"], "no calculable")
            self.assertEqual(r["severidad_fmt"], "sin dato")

        msg = GroundedActuarialAssistant.format_executive_summary_response(res, {"interpretation_notes": []})
        self.assertIn("No hay datos de severidad para 2023", msg)

    def test_T22_category_threshold_boundaries(self):
        """T22: Severidades 11,000.00 · 10,999.99 · 7,500.00 · 7,499.99 (anual y periodo)"""
        cases = [
            (11000.00, "Crítica"),
            (10999.99, "Media"),
            (7500.00, "Media"),
            (7499.99, "Baja"),
        ]
        for val, expected_label in cases:
            raw_cat = compute_category_from_rule(val)
            self.assertEqual(display_category_label(raw_cat), expected_label, f"Falló umbral para {val}")

        data = make_synthetic_dataset([
            {"entidad": "E1", "severidad_promedio": 11000.00, "yearly_severidad": {"2023": 11000.00}},
            {"entidad": "E2", "severidad_promedio": 10999.99, "yearly_severidad": {"2023": 10999.99}},
            {"entidad": "E3", "severidad_promedio": 7500.00, "yearly_severidad": {"2023": 7500.00}},
            {"entidad": "E4", "severidad_promedio": 7499.99, "yearly_severidad": {"2023": 7499.99}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["E1", "E2", "E3", "E4"], 2023)
        self.assertEqual([r["categoria"] for r in res["rows"]], ["Crítica", "Media", "Media", "Baja"])

    def test_T23_missing_yearly_category_does_not_fallback_to_period(self):
        """T23: Falta yearly_categoria['2023'], existe categoria_severidad -> Categoría 2023 'sin dato'"""
        data = make_synthetic_dataset([
            {
                "entidad": "Estado A",
                "severidad_promedio": 12000.0,
                "categoria_severidad": "Critica",
                "yearly_severidad": {"2023": 12000.0},
                "yearly_categoria": {"2023": "__DELETE__"}
            }
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A"], 2023)
        self.assertEqual(res["rows"][0]["categoria"], "sin dato")

    def test_T24_competition_ranking_tie_at_centavo(self):
        """T24: Severidades 100.004 · 100.001 · 90.00 -> Posiciones 1 · 1 · 3 (empate al centavo)"""
        data = make_synthetic_dataset([
            {"entidad": "Estado A", "yearly_severidad": {"2023": 100.004}},
            {"entidad": "Estado B", "yearly_severidad": {"2023": 100.001}},
            {"entidad": "Estado C", "yearly_severidad": {"2023": 90.00}},
        ])
        eng = ActuarialOperationsEngine(data)
        res = eng.compute_executive_summary(["Estado A", "Estado B", "Estado C"], 2023)
        self.assertEqual([r["rank_nacional_severidad"] for r in res["rows"]], [1, 1, 3])

    # =========================================================================
    # FORMATEADOR DETERMINISTA (T25)
    # =========================================================================
    def test_T25_formatter_boundary_values(self):
        """T25: Formateador en Python con límites de redondeo de punto flotante."""
        cases_2dec = [
            (0.125, "0.13"),
            (1.005, "1.01"),
            (2.675, "2.68"),
            (9.995, "10.00"),
            (-0.125, "-0.13"),
            (-0.004, "0.00"),
            (1234567.895, "1,234,567.90"),
            (1e-7, "0.00"),
            (1e16, "10,000,000,000,000,000.00"),
        ]
        for val, expected in cases_2dec:
            self.assertEqual(format_number(val, 2), expected, f"Falló 2 dec para {val}")

        cases_1dec = [
            (0.05, "0.1"),
            (0.25, "0.3"),
            (-0.05, "-0.1"),
        ]
        for val, expected in cases_1dec:
            self.assertEqual(format_number(val, 1), expected, f"Falló 1 dec para {val}")

    def test_T27_business_rules_and_human_narrative(self):
        """Verifica consultas de Reglas de Negocio ('como se calcula indice relativo') y síntesis narrativa humana."""
        for q_rule in ["como se calcula indice relativo", "mostrar todas las reglas de negocio", "umbrales de categoria"]:
            ir = self.parser.parse_to_structured_json(q_rule)
            self.assertEqual(ir["intent"], "glossary_units", f"No enrutó a glossary_units: {q_rule}")
            resp = self.assistant.ask(q_rule)
            self.assertTrue("Regla de Negocio" in resp or "Reglas de Negocio" in resp)

        resp_idx = self.assistant.ask("como se calcula indice relativo")
        self.assertIn("100 × [ Severidad_e(Y) / Media_ref(Y) ]", resp_idx)
        self.assertIn("ROUND_HALF_UP", resp_idx)
        self.assertIn("156.1 pts", resp_idx)

        resp_cdmx = self.assistant.ask("crea una explicación de los datos de Ciudad de México severidad para el año 2024")
        self.assertIn("Interpretación ejecutiva:", resp_cdmx)
        self.assertIn("56.1 % por encima", resp_cdmx)

    def test_T28_severity_and_single_concept_clarity(self):
        """Verifica que 'que es la severidad ? y como se calcula' responda directamente sobre severidad sin volcar RN-01 primero."""
        for q_sev in [
            "que es la severidad ? y como se calcula",
            "¿Qué es la severidad?",
            "como se calcula la severidad",
            "definicion de severidad"
        ]:
            ir = self.parser.parse_to_structured_json(q_sev)
            self.assertEqual(ir["intent"], "glossary_units", f"No enrutó a glossary_units: {q_sev}")
            resp = self.assistant.ask(q_sev)
            self.assertIn("¿Qué es la Severidad y cómo se calcula?", resp, f"Encabezado incorrecto para: {q_sev}")
            self.assertNotIn("Catálogo de Reglas de Negocio", resp, f"Volcó catálogo genérico para: {q_sev}")
            self.assertIn("costo económico promedio de cada siniestro", resp)
            self.assertIn("13,647.32 MDP", resp)
            self.assertIn("967,044.12 siniestros", resp)
            self.assertIn("14,112.41 MXN", resp)

        # Verificar conceptos individuales adicionales (MDP, Frecuencia)
        resp_mdp = self.assistant.ask("que es mdp y como se calcula")
        self.assertIn("¿Qué es el Costo Total (`MDP`) y cómo se calcula?", resp_mdp)
        self.assertIn("90,373.46 MDP", resp_mdp)
        self.assertIn("Millones de Pesos", resp_mdp)

        resp_freq = self.assistant.ask("que es la frecuencia y como se calcula")
        self.assertIn("¿Qué son la Frecuencia y la Exposición Asegurada?", resp_freq)
        self.assertIn("35 % de exposición × 30 % de frecuencia", resp_freq)

    def test_T29_chart_explanation_triggers_and_superscript_r2(self):
        """Verifica que 'Explicar R² y el 72.05%' y las demás consultas de gráficas normalicen '²'->'2' y enruten sin caer en fallback."""
        self.assertEqual(normalize_text("Explicar R² y el 72.05%"), "explicar r2 y el 72 05")

        chart_queries = [
            ("Explicar barras, línea y ejes de Pareto", "pareto_breakdown", "47.1%"),
            ("Explicar R² y el 72.05%", "regression_drivers", "72.05%"),
            ("Explicar tendencia histórica de severidad", "growth_cagr", "Tlaxcala"),
        ]
        for q, expected_intent, expected_text in chart_queries:
            ir = self.parser.parse_to_structured_json(q)
            self.assertEqual(ir["intent"], expected_intent, f"Intent incorrecto para '{q}': {ir['intent']}")
            resp = self.assistant.ask(q)
            self.assertIn(expected_text, resp, f"Falta '{expected_text}' en respuesta a '{q}'")
            self.assertNotIn("No reconocí", resp)

    def test_T30_growth_typos_and_relative_index_rankings(self):
        """Verifica los 3 casos reportados: crecimiento acumulado con typo, typo estatal 'CHICHUACA' 2024 y mayor índice relativo."""
        # Caso 1: "CUALES EL ESTADO CON MAYOR CRECIMOENTO ACUMULADO ?"
        q1 = "CUALES EL ESTADO CON MAYOR CRECIMOENTO ACUMULADO ?"
        ir1 = self.parser.parse_to_structured_json(q1)
        self.assertEqual(ir1["intent"], "growth_cagr")
        self.assertEqual(ir1["states"], [])
        resp1 = self.assistant.ask(q1)
        self.assertIn("Tlaxcala", resp1)
        self.assertIn("150.6%", resp1)
        self.assertNotIn("No reconocí", resp1)

        # Caso 2: "SEVERIDAD CHICHUACA 2024?"
        q2 = "SEVERIDAD CHICHUACA 2024?"
        ir2 = self.parser.parse_to_structured_json(q2)
        self.assertEqual(ir2["intent"], "single_state")
        self.assertEqual(ir2["states"], ["Chihuahua"])
        self.assertEqual(ir2["target_year"], 2024)
        resp2 = self.assistant.ask(q2)
        self.assertIn("Chihuahua", resp2)
        self.assertIn("11,422.11", resp2)
        self.assertIn("126.3 pts", resp2)
        self.assertNotIn("No reconocí", resp2)

        # Caso 3: "CUALES ES EL ESTADO CON MAYOR INDICE RELATIVO ?"
        q3 = "CUALES ES EL ESTADO CON MAYOR INDICE RELATIVO ?"
        ir3 = self.parser.parse_to_structured_json(q3)
        self.assertEqual(ir3["intent"], "top_rankings")
        self.assertEqual(ir3["states"], [])
        resp3 = self.assistant.ask(q3)
        self.assertIn("Nuevo Leon", resp3)
        self.assertIn("209.3 pts", resp3)
        self.assertNotIn("No reconocí", resp3)

    def test_T31_recommendations_preventive_actions_and_opportunities(self):
        """Verifica que tras pedir resumen de Chihuahua 2024, consultas de recomendaciones, acciones preventivas y oportunidades respondan con datos reales."""
        # Turno 1: Resumen ejecutivo de Chihuahua 2024 (con typo 'paa')
        resp_sum = self.assistant.ask("crea un resumen de la severidad de chihuahua paa el año 2024")
        self.assertIn("Resumen ejecutivo — Chihuahua (2024)", resp_sum)
        self.assertIn("11,422.11", resp_sum)

        # Turno 2: Recomendaciones explícitas para Chihuahua
        q_rec = "que recomendaciones me puedes dar para chihuahua ?"
        ir_rec = self.parser.parse_to_structured_json(q_rec)
        self.assertEqual(ir_rec["intent"], "recommendations_actions")
        self.assertEqual(ir_rec["states"], ["Chihuahua"])
        self.assertEqual(ir_rec["target_year"], 2024)
        resp_rec = self.assistant.ask(q_rec)
        self.assertIn("Recomendaciones, Acciones Preventivas y Oportunidades — Chihuahua (2024)", resp_rec)
        self.assertIn("11,422.11", resp_rec)
        self.assertIn("126.3 pts", resp_rec)
        self.assertIn("4,487.71 MDP", resp_rec)
        self.assertIn("275k MXN", resp_rec)
        self.assertIn("387.5 autos / 1,000 hab.", resp_rec)
        self.assertIn("Acciones Preventivas y de Mitigación", resp_rec)
        self.assertIn("Identificación de Oportunidades Basadas en los Datos", resp_rec)

        # Turno 3: Continuación sin mencionar estado ("identificar oputinidades y acciones preventivas")
        q_opp = "identificar oputinidades y acciones preventivas"
        ir_opp = self.parser.parse_to_structured_json(q_opp)
        self.assertEqual(ir_opp["intent"], "recommendations_actions")
        self.assertEqual(ir_opp["states"], ["Chihuahua"])
        self.assertEqual(ir_opp["target_year"], 2024)
        resp_opp = self.assistant.ask(q_opp)
        self.assertIn("Recomendaciones, Acciones Preventivas y Oportunidades — Chihuahua (2024)", resp_opp)
        self.assertIn("Oportunidad de retención y crecimiento selectivo", resp_opp)


if __name__ == '__main__':
    unittest.main()

