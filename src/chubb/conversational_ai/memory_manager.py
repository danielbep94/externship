"""
Conversational AI — Conversation Memory Manager.
Separates confirmed context (states, year, metric) from pending interpretations,
and resolves temporal intent according to specification §6.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from chubb.semantic_foundation.temporal_registry import normalize_text


class ConversationMemoryManager:
    """
    Gestiona el ciclo de vida de la conversación.
    Separa de manera explícita:
    - Contexto Confirmado: Estados y periodos explícitamente consultados/resueltos.
    - Interpretación Pendiente: Intentos de desambiguación antes de confirmar la mutación del contexto.
    """
    VALID_YEARS = [2020, 2021, 2022, 2023, 2024]
    DEFAULT_YEAR = 2024

    def __init__(self):
        self.confirmed_states: List[str] = []
        self.confirmed_year: Optional[int] = None
        self.confirmed_metric: str = 'severidad'
        self.pending_interpretation: Optional[Dict[str, Any]] = None

    def clear(self) -> None:
        """Reinicia el estado de la memoria conversacional para consultas independientes."""
        self.confirmed_states = []
        self.confirmed_year = None
        self.confirmed_metric = 'severidad'
        self.pending_interpretation = None

    @staticmethod
    def is_continuation_query(query: str) -> bool:
        """
        Determina si la consulta es de continuación según la especificación (§6):
        - El texto normalizado empieza con 'y '
        - O contiene como término completo 'tambien', 'mismo ano' o 'ese ano'
        """
        norm_q = normalize_text(query)
        if norm_q.startswith("y "):
            return True
        for marker in ("tambien", "mismo ano", "ese ano"):
            if re.search(rf'\b{re.escape(marker)}\b', norm_q):
                return True
        return False

    def resolve_year_for_summary(self, query: str, has_explicit_states: bool = False) -> Dict[str, Any]:
        """
        Resuelve el año para un Resumen Ejecutivo según la tabla de decisión §6:
        - Más de un año distinto -> 'clarification_year'
        - Año fuera de 2020-2024 -> 'temporal_out_of_range' (sin modificar confirmed_year)
        - Un año explícito válido -> target_year = año, year_source = 'explicit'
        - Sin año, consulta de continuación y memoria con año -> target_year = confirmed_year, year_source = 'memory'
        - Sin año en cualquier otro caso -> target_year = 2024, year_source = 'default'
        """
        norm_q = normalize_text(query)
        years_found = [int(y) for y in re.findall(r'\b(19\d\d|20\d\d)\b', norm_q)]
        unique_years: List[int] = []
        for y in years_found:
            if y not in unique_years:
                unique_years.append(y)

        out_of_range = [y for y in unique_years if y not in self.VALID_YEARS]
        if out_of_range:
            bad_y = out_of_range[0]
            return {
                "status": "temporal_out_of_range",
                "target_year": None,
                "year_source": None,
                "error_message": f"⚠️ El año {bad_y} está fuera del periodo disponible (2020–2024). Indica un año dentro de ese rango."
            }

        if len(unique_years) == 2 and 2020 in unique_years:
            if re.search(r'\b(?:desde|contra|frente a|vs|respecto a)\s+2020\b', norm_q):
                unique_years = [y for y in unique_years if y != 2020]

        if len(unique_years) > 1:
            yrs_str = ", ".join(str(y) for y in unique_years)
            return {
                "status": "clarification_year",
                "target_year": None,
                "year_source": None,
                "error_message": f"⚠️ Indica un solo año para el resumen (2020–2024). Detecté múltiples años: {yrs_str}."
            }

        if len(unique_years) == 1:
            return {
                "status": "ok",
                "target_year": unique_years[0],
                "year_source": "explicit",
                "error_message": None
            }

        if self.is_continuation_query(query) and self.confirmed_year in self.VALID_YEARS:
            return {
                "status": "ok",
                "target_year": self.confirmed_year,
                "year_source": "memory",
                "error_message": None
            }

        return {
            "status": "ok",
            "target_year": self.DEFAULT_YEAR,
            "year_source": "default",
            "error_message": None
        }

    def parse_year_intent(self, query: str, has_explicit_new_state: bool = False) -> Tuple[Optional[int], Optional[str]]:
        """
        Extrae y valida el año solicitado en consultas generales (no resumen ejecutivo).
        Retorna (año_valido, error_o_advertencia_temporal).
        """
        norm_q = normalize_text(query)
        years_found = [int(y) for y in re.findall(r'\b(19\d\d|20\d\d)\b', norm_q)]
        unique_years: List[int] = []
        for y in years_found:
            if y not in unique_years:
                unique_years.append(y)

        if not unique_years:
            if any(re.search(rf'\b{w}\b', norm_q) for w in ["promedio", "historico", "general", "todos"]):
                return (None, None)
            if has_explicit_new_state and not self.is_continuation_query(query) and not any(re.search(rf'\b{w}\b', norm_q) for w in ["este", "ese", "mismo"]):
                return (None, None)
            return (self.confirmed_year, None)

        if unique_years == [2020, 2024] and any(re.search(rf'\b{w}\b', norm_q) for w in ["promedio", "periodo", "historico", "cagr", "crecimiento", "tendencia", "acumulado"]):
            return (None, None)

        for year in unique_years:
            if year not in self.VALID_YEARS:
                return (None, f"⚠️ El año {year} se encuentra fuera del rango de observación del estudio (2020 a 2024).")

        if len(unique_years) > 1:
            return (None, "⚠️ Indica un solo año para la consulta (2020–2024).")

        return (unique_years[0], None)

    def update_confirmed_context(self, states: List[str], year: Optional[int], metric: Optional[str] = None):
        """Actualiza el contexto confirmado tras una respuesta exitosa."""
        if states:
            self.confirmed_states = states
        if year is not None:
            self.confirmed_year = year
        if metric:
            self.confirmed_metric = metric
        self.pending_interpretation = None

    def get_effective_states(self, extracted_states: List[str], query: str) -> List[str]:
        """Resuelve si se usan los estados extraídos o se hereda la memoria confirmada."""
        if extracted_states:
            return extracted_states

        norm_q = normalize_text(query)
        words = set(re.findall(r'\b\w+\b', norm_q))

        if words.intersection({"cuales", "ranking", "rankings", "top", "lista", "general", "nacional"}):
            return []

        if words.intersection({"este", "su", "sus", "en", "ambos", "estos", "y", "mismo", "misma", "tambien"}):
            return self.confirmed_states

        return []

