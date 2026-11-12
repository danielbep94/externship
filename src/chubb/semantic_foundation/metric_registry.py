"""
Semantic Foundation — Metric Registry.
Governs canonical actuarial metric definitions, units, labels, and keyword detection.
Rule: Does not execute calculations or generate LLM narratives.
"""

import re
from typing import Dict, List, Any
from chubb.semantic_foundation.temporal_registry import normalize_text


class MetricRegistry:
    """Registry of canonical actuarial metrics and their semantic metadata."""

    METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
        'severidad': {
            'canonical': 'severidad',
            'label': 'Severidad Unitaria ($/Siniestro)',
            'unit': 'MXN por siniestro',
            'keywords': ['severidad', 'costo unitario', 'costo por siniestro', 'severo', 'costoso', 'severidades', 'cuantia']
        },
        'costo_mdp': {
            'canonical': 'costo_mdp',
            'label': 'Costo Total de Siniestros (MDP)',
            'unit': 'MDP (Millones de Pesos)',
            'keywords': ['costo total', 'mdp', 'volumen', 'perdida agregada', 'monto total', 'costo anual', 'millones']
        },
        'indice_relativo': {
            'canonical': 'indice_relativo',
            'label': 'Índice Relativo de Severidad',
            'unit': 'pts (Base Nacional = 100)',
            'keywords': ['indice', 'relativo', 'base 100', 'pts', 'respecto a la media']
        },
        'crecimiento_cagr': {
            'canonical': 'crecimiento_cagr',
            'label': 'Crecimiento Histórico y CAGR',
            'unit': '% acumulado / % anual compuesto',
            'keywords': ['crecimiento', 'cagr', 'incremento', 'aumento', 'tendencia', 'evolucion', 'duplicaron', 'acumulado']
        },
        'riesgo_categoria': {
            'canonical': 'riesgo_categoria',
            'label': 'Categoría y Nivel de Riesgo',
            'unit': 'Estrato (Baja, Media, Crítica)',
            'keywords': ['categoria', 'nivel', 'riesgo', 'semaforo', 'estrato', 'critica', 'media', 'baja']
        },
        'pareto': {
            'canonical': 'pareto',
            'label': 'Concentración de Pérdida (Pareto)',
            'unit': '% del total nacional',
            'keywords': ['pareto', 'concentracion', 'top 5 volumen', 'curva acumulada', '80 20']
        },
        'asociacion_precios': {
            'canonical': 'asociacion_precios',
            'label': 'Correlación y Regresión (Scatter R²)',
            'unit': 'r de Pearson / R² score',
            'keywords': ['r2', 'r²', 'correlacion', 'precio auto', 'regresion', 'asociacion', 'variables', 'afectan', 'drivers']
        }
    }

    @classmethod
    def resolve_metrics(cls, query: str) -> List[str]:
        """Detecta qué métricas actuariales se están solicitando en la consulta."""
        norm_q = normalize_text(query)
        detected = []
        for metric_id, info in cls.METRIC_CATALOG.items():
            if any(re.search(rf'\b{re.escape(normalize_text(kw))}\b', norm_q) for kw in info['keywords']):
                detected.append(metric_id)
        if not detected and any(re.search(rf'\b{w}\b', norm_q) for w in ["cuanto", "diferencia", "compara", "comparar", "resumen", "sintesis"]):
            detected.append('severidad')
        return detected

