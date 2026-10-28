"""
Unit Tests for Phases 1 to 4: Actuarial Core Module
Valida:
1. Esquema, integridad y consistencia de data.json (Fase 1)
2. Catálogo de alias de entidades y métricas, extracción N-estatal (Fase 2)
3. Gestión de memoria y separación de contexto confirmado vs pendiente (Fase 3)
4. Motor de operaciones y reglas metodológicas sin cifras hardcodeadas (Fase 4)
"""

import unittest
import json
import sys
sys.path.append('src')

from actuarial_core import (
    ActuarialDataValidator,
    ActuarialCatalog,
    ConversationMemoryManager,
    ActuarialOperationsEngine,
    DataIntegrityError
)

class TestActuarialCore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = ActuarialDataValidator.load_and_validate('/Users/victordaniel/chubb/data.json')
        cls.canonical_states = [s['entidad'] for s in cls.data['estados']]
        cls.catalog = ActuarialCatalog(cls.canonical_states)
        cls.engine = ActuarialOperationsEngine(cls.data)

    # -------------------------------------------------------------
    # FASE 1: Esquema, Integridad y Consistencia
    # -------------------------------------------------------------
    def test_fase1_data_loads_and_validates_successfully(self):
        """Verifica que data.json cumple 100% de los requisitos del validador."""
        self.assertEqual(len(self.data['estados']), 32)
        self.assertAlmostEqual(self.data['metadata']['promedio_nacional_severidad'], 6674.08, places=1)
        self.assertAlmostEqual(self.data['metadata']['total_mdp_nacional_promedio'], 90373.46, places=1)

    def test_fase1_validator_fails_fast_on_missing_keys(self):
        """Verifica que el validador rechaza archivos con claves faltantes."""
        corrupted = {"metadata": {"titulo": "Incompleto"}}
        with open('/tmp/corrupted_test.json', 'w') as f:
            json.dump(corrupted, f)
        with self.assertRaises(DataIntegrityError):
            ActuarialDataValidator.load_and_validate('/tmp/corrupted_test.json')

    # -------------------------------------------------------------
    # FASE 2: Catálogo de Alias y Parser N-Estatal
    # -------------------------------------------------------------
    def test_fase2_state_aliases_resolution(self):
        """Verifica que las siglas y acrónimos comunes resuelven al nombre canónico."""
        self.assertEqual(self.catalog.extract_states("Consulta de severidad en cdmx y nl"), ["Ciudad de Mexico", "Nuevo Leon"])
        self.assertEqual(self.catalog.extract_states("Riesgo en edomex y slp"), ["Estado de Mexico", "San Luis Potosi"])
        self.assertEqual(self.catalog.extract_states("Comparar qro vs jal"), ["Queretaro", "Jalisco"])

    def test_fase2_extract_multiple_n_states(self):
        """Verifica que no hay límite artificial de 2 estados (admite 4 o más)."""
        query = "Compara Jalisco, Nuevo León, CDMX y Puebla"
        states = self.catalog.extract_states(query)
        self.assertEqual(len(states), 4)
        self.assertEqual(states, ["Jalisco", "Nuevo Leon", "Ciudad de Mexico", "Puebla"])

    def test_fase2_metric_catalog_resolution(self):
        """Verifica la detección de métricas actuariales solicitadas."""
        self.assertIn("severidad", self.catalog.resolve_metrics("¿Cuál es la severidad promedio?"))
        self.assertIn("costo_mdp", self.catalog.resolve_metrics("¿Cuál es el costo total en mdp?"))
        self.assertIn("crecimiento_cagr", self.catalog.resolve_metrics("¿Qué estados tuvieron mayor incremento y cagr?"))
        self.assertIn("pareto", self.catalog.resolve_metrics("Diagrama de pareto y concentracion"))
        self.assertIn("asociacion_precios", self.catalog.resolve_metrics("Explicar r2 y correlacion con precios"))

    # -------------------------------------------------------------
    # FASE 3: Gestión de Memoria y Periodos
    # -------------------------------------------------------------
    def test_fase3_year_boundaries_validation(self):
        """Verifica que años fuera del rango 2020-2024 generan advertencia sin caerse."""
        memory = ConversationMemoryManager()
        
        # Año válido
        yr, err = memory.parse_year_intent("¿Severidad de Jalisco en 2024?")
        self.assertEqual(yr, 2024)
        self.assertIsNone(err)

        # Año fuera de rango inferior
        yr, err = memory.parse_year_intent("¿Severidad en 2019?")
        self.assertIsNone(yr)
        self.assertIn("fuera del rango", err)

        # Año fuera de rango superior
        yr, err = memory.parse_year_intent("¿Proyección para 2026?")
        self.assertIsNone(yr)
        self.assertIn("fuera del rango", err)

    def test_fase3_context_memory_inheritance(self):
        """Verifica que preguntas sucesivas con anáforas heredan el contexto confirmado."""
        memory = ConversationMemoryManager()
        memory.update_confirmed_context(["Nuevo Leon"], 2023, "severidad")

        # Pregunta posterior sin mencionar el estado: "¿Y en 2024?"
        inherited_states = memory.get_effective_states([], "¿Y en 2024?")
        self.assertEqual(inherited_states, ["Nuevo Leon"])

    # -------------------------------------------------------------
    # FASE 4: Motor de Operaciones Actuariales (Zero Hardcoded)
    # -------------------------------------------------------------
    def test_fase4_dynamic_three_findings(self):
        """Verifica que los tres hallazgos clave se calculan dinámicamente y coinciden con ground truth."""
        findings = self.engine.compute_three_key_findings()
        
        # Pareto Top 5 suma ~47.1%
        self.assertAlmostEqual(findings["pareto_pct"], 47.1, places=1)
        self.assertEqual(len(findings["pareto_top5"]), 5)

        # Ratio Max/Min NL vs Oaxaca ~6.85x
        self.assertAlmostEqual(findings["ratio_max_min"], 6.85, places=2)
        self.assertEqual(findings["max_state"]["entidad"], "Nuevo Leon")
        self.assertEqual(findings["min_state"]["entidad"], "Oaxaca")

        # Crecimiento líder Tlaxcala
        self.assertEqual(findings["growth_leader"]["entidad"], "Tlaxcala")
        self.assertAlmostEqual(findings["growth_leader"]["cagr_total"], 150.6, places=1)

        # Regresión r=0.8488, R2=72.05%
        self.assertAlmostEqual(findings["regression"]["r"], 0.8488, places=3)
        self.assertAlmostEqual(findings["regression"]["r2_pct"], 72.05, places=2)

    def test_fase4_dynamic_multi_state_comparison_4_states(self):
        """Verifica la comparación dinámica de 4 estados ordenados por severidad."""
        comp = self.engine.compute_multi_state_comparison(["Jalisco", "Nuevo Leon", "Ciudad de Mexico", "Puebla"])
        self.assertEqual(len(comp["estados_metricas"]), 4)
        # Orden descendente por severidad: Nuevo León primero, Puebla último
        self.assertEqual(comp["estados_metricas"][0]["entidad"], "Nuevo Leon")
        self.assertEqual(comp["estados_metricas"][-1]["entidad"], "Puebla")
        self.assertTrue(comp["requiere_distincion_actuarial"])

    def test_fase4_jalisco_2024_dynamic_category(self):
        """Verifica que Jalisco en 2024 se evalúa dinámicamente como 'Critica' con $13,836.27 MXN."""
        m2024 = self.engine.get_state_metrics("Jalisco", target_year=2024)
        self.assertAlmostEqual(m2024["severidad"], 13836.27, places=2)
        self.assertEqual(m2024["categoria"], "Critica")

if __name__ == '__main__':
    unittest.main()
