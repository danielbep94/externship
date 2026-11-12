"""
Semantic Foundation — Actuarial Catalog.
Unified facade combining EntityResolver, MetricRegistry, and TemporalRegistry.
Preserves full compatibility with ActuarialCatalog in actuarial_core.
"""

from typing import Dict, List, Any, Tuple
from chubb.semantic_foundation.temporal_registry import load_actuarial_rules
from chubb.semantic_foundation.metric_registry import MetricRegistry
from chubb.semantic_foundation.entity_resolver import EntityResolver


class ActuarialCatalog:
    """Catálogo formal de entidades y métricas sincronizado con config/actuarial_rules.json."""

    rules = load_actuarial_rules()
    STATE_ALIASES: Dict[str, str] = EntityResolver.STATE_ALIASES
    METRIC_CATALOG: Dict[str, Dict[str, Any]] = MetricRegistry.METRIC_CATALOG
    STOP_WORDS = EntityResolver.STOP_WORDS

    def __init__(self, canonical_states: List[str]):
        self._entity_resolver = EntityResolver(canonical_states)
        self.canonical_states = self._entity_resolver.canonical_states
        self.canonical_set = self._entity_resolver.canonical_set
        self.norm_canonical = self._entity_resolver.norm_canonical

    def resolve_metrics(self, query: str) -> List[str]:
        """Detecta qué métricas actuariales se están solicitando en la consulta."""
        return MetricRegistry.resolve_metrics(query)

    @staticmethod
    def _normalize_with_offsets(query: str) -> Tuple[str, List[int]]:
        """Normaliza texto devolviendo (norm_q, orig_indices) para recuperar menciones originales."""
        return EntityResolver._normalize_with_offsets(query)

    def extract_states_detailed(self, query: str) -> Dict[str, Any]:
        """Extrae menciones de entidades federativas con límite de palabra y sin traslapes."""
        return self._entity_resolver.extract_states_detailed(query)

    def extract_states(self, query: str) -> List[str]:
        """Extrae N entidades federativas únicas en orden de primera aparición."""
        return self._entity_resolver.extract_states(query)

