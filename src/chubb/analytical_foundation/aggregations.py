"""
Analytical Foundation — Portfolio Aggregations & Ranking Helpers.
Implements Pareto concentration, CAGR rankings, national references, and competition rankings ('1, 1, 3').
"""

import math
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from chubb.analytical_foundation.calculations import round_half_up_decimal


def is_valid_severity(val: Any) -> bool:
    """Severidad válida: número finito y > 0."""
    return val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and float(val) > 0.0


def is_valid_mdp(val: Any) -> bool:
    """MDP válido en el año consultado: número finito y >= 0."""
    return val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and float(val) >= 0.0


def compute_national_reference(estados_list: List[Dict[str, Any]], year_str: str) -> Tuple[Optional[float], int]:
    """
    Calcula la referencia nacional para un año como la media simple de las entidades con severidad válida.
    Retorna (media_ref, n_entidades_con_dato).
    """
    valid_vals = [
        float(s["yearly_severidad"].get(year_str))
        for s in estados_list
        if is_valid_severity(s.get("yearly_severidad", {}).get(year_str))
    ]
    n = len(valid_vals)
    if n == 0:
        return (None, 0)
    return (sum(valid_vals) / n, n)


def compute_competition_ranks(estados_list: List[Dict[str, Any]], year_str: str) -> Dict[str, Any]:
    """
    Calcula rankings nacionales de competencia ('1, 1, 3') comparando valores redondeados al centavo (2 decimales).
    El denominador refleja las entidades con dato válido para cada métrica y año.
    """
    sev_entries: List[Tuple[str, Decimal]] = []
    mdp_entries: List[Tuple[str, Decimal]] = []

    for s in estados_list:
        ent = s["entidad"]
        sv = s.get("yearly_severidad", {}).get(year_str)
        if is_valid_severity(sv):
            sev_entries.append((ent, round_half_up_decimal(float(sv), 2)))

        mv = s.get("yearly_mdp", {}).get(year_str)
        if is_valid_mdp(mv):
            mdp_entries.append((ent, round_half_up_decimal(float(mv), 2)))

    sev_ranks: Dict[str, Tuple[int, int]] = {}
    n_sev = len(sev_entries)
    for ent, q_val in sev_entries:
        higher = sum(1 for _, other_val in sev_entries if other_val > q_val)
        sev_ranks[ent] = (higher + 1, n_sev)

    mdp_ranks: Dict[str, Tuple[int, int]] = {}
    n_mdp = len(mdp_entries)
    for ent, q_val in mdp_entries:
        higher = sum(1 for _, other_val in mdp_entries if other_val > q_val)
        mdp_ranks[ent] = (higher + 1, n_mdp)

    return {
        "severidad": sev_ranks,
        "n_severidad": n_sev,
        "costo_mdp": mdp_ranks,
        "n_costo_mdp": n_mdp
    }

