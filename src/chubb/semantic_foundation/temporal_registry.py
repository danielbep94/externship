"""
Semantic Foundation — Temporal Registry & Text Normalization Utilities.
Governs valid observation years (2020–2024), base year (2020), default year (2024),
and deterministic NFD text normalization shared across Python and JavaScript.
"""

import json
import os
import re
import unicodedata
from typing import Dict, Any, List
from chubb.infrastructure.paths import resolve_rules_path

DEFAULT_RULES_PATH = resolve_rules_path()


def load_actuarial_rules(rules_path: str = "") -> Dict[str, Any]:
    """Carga la configuración compartida entre Python y JavaScript."""
    target_path = resolve_rules_path(rules_path)
    if os.path.exists(target_path):
        with open(target_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    raise FileNotFoundError(f"No se encontró el archivo de reglas actuariales en {target_path}")


def normalize_text(text: str) -> str:
    """
    Normaliza texto de forma idéntica a JavaScript:
    NFD -> eliminar marcas diacríticas -> superíndices (²->2, ³->3) -> minúsculas -> sustituir puntuación por espacio -> colapsar espacios -> trim.
    """
    if text is None:
        return ""
    s = str(text).replace("²", "2").replace("³", "3")
    decomposed = unicodedata.normalize('NFD', s)
    without_accents = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    lowered = without_accents.lower()
    no_punct = re.sub(r'[^\w\s]', ' ', lowered)
    collapsed = re.sub(r'\s+', ' ', no_punct).strip()
    return collapsed


class TemporalRegistry:
    """Governs supported observation years, base year, and default year rules."""

    _rules = load_actuarial_rules()
    VALID_YEARS: List[int] = _rules.get("valid_years", [2020, 2021, 2022, 2023, 2024])
    DEFAULT_YEAR: int = _rules.get("default_year", 2024)
    BASE_YEAR: int = _rules.get("base_year", 2020)

    @classmethod
    def is_valid_year(cls, year: int) -> bool:
        return isinstance(year, int) and not isinstance(year, bool) and year in cls.VALID_YEARS

