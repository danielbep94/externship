"""
Analytical Foundation — Deterministic Actuarial Calculations & Rounding Utilities.
Implements IEEE-754 shortest decimal representation ROUND_HALF_UP rounding and category threshold evaluation.
Rule: Never calls LLM providers or frontend modules.
"""

import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def _double_to_Shortest_decimal_str(val: float) -> str:
    """
    Convierte un float IEEE-754 a su representación decimal más corta (repr en Python 3.8+ / String(x) en JS)
    expandiendo notación científica a cadena decimal pura para redondeo exacto.
    """
    s = repr(float(val))
    if 'e' in s or 'E' in s:
        d = Decimal(s)
        return format(d, 'f')
    return s


def round_half_up_decimal(val: float, decimals: int = 2) -> Decimal:
    """Redondea usando la representación decimal más corta del float con ROUND_HALF_UP."""
    dec_str = _double_to_Shortest_decimal_str(val)
    d = Decimal(dec_str)
    quantizer = Decimal('10') ** (-decimals) if decimals > 0 else Decimal('1')
    q = d.quantize(quantizer, rounding=ROUND_HALF_UP)
    if q == 0:
        q = abs(q)
    return q


def format_number(val: Optional[float], decimals: int = 2, thousands_sep: bool = True) -> str:
    """
    Formateador determinista compartido con JS:
    - Parte de la representación decimal más corta del float.
    - Aplica ROUND_HALF_UP (mitad lejos de cero).
    - Evita '-0.00' mostrándolo como '0.00'.
    - Usa ',' para miles y '.' para decimales.
    """
    if val is None or not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
        return "sin dato"
    q = round_half_up_decimal(float(val), decimals)
    sign = "-" if q < 0 else ""
    q_abs = abs(q)
    fixed_str = format(q_abs, f'.{decimals}f')
    if decimals > 0:
        int_part, frac_part = fixed_str.split('.')
    else:
        int_part, frac_part = fixed_str, ""

    if thousands_sep:
        int_part_groups = []
        while len(int_part) > 3:
            int_part_groups.append(int_part[-3:])
            int_part = int_part[:-3]
        int_part_groups.append(int_part)
        int_part = ",".join(reversed(int_part_groups))

    return f"{sign}{int_part}.{frac_part}" if decimals > 0 else f"{sign}{int_part}"


def compute_category_from_rule(
    sev_val: Optional[float],
    critica_min: float = 11000.0,
    media_min: float = 7500.0
) -> Optional[str]:
    """Evalúa la regla documentada de categoría sobre el valor sin redondear."""
    if sev_val is None or not isinstance(sev_val, (int, float)) or isinstance(sev_val, bool) or not math.isfinite(sev_val) or sev_val <= 0:
        return None
    if sev_val >= critica_min:
        return "Critica"
    if sev_val >= media_min:
        return "Media"
    return "Baja"


def display_category_label(cat: Optional[str]) -> str:
    """Formatea la etiqueta de categoría para presentación al usuario."""
    if not cat or cat == "sin dato":
        return "sin dato"
    if cat in ("Critica", "Crítica"):
        return "Crítica"
    return cat

