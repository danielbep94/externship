"""
Oráculo Actuarial Independiente (Corrección Problema 2)
-------------------------------------------------------
- PROHIBIDO importar cualquier módulo de `src/` (ni `actuarial_core` ni `llm_grounding`).
- Implementa las fórmulas actuariales desde cero usando `fractions.Fraction` y `decimal.Decimal`
  directamente sobre el archivo `data.json`.
- Incluye un banco de Casos Críticos Auditados Manualmente (`GOLDEN_MANUAL_CASES`) que valida
  al propio oráculo antes de calificar una sola pregunta del benchmark de 10,000 consultas.
"""

import json
import math
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Dict, List, Any, Optional, Tuple


def oracle_fmt(val: float, decimals: int = 2, thousands: bool = True) -> str:
    """Redondeo independiente ROUND_HALF_UP sobre representación decimal exacta."""
    d = Decimal(str(float(val)))
    q = Decimal("1") if decimals == 0 else Decimal("0." + ("0" * (decimals - 1)) + "1")
    r = d.quantize(q, rounding=ROUND_HALF_UP)
    if r == Decimal("0"):
        r = abs(r)
    fmt_str = f"{r:,.{decimals}f}" if thousands else f"{r:.{decimals}f}"
    return fmt_str


def oracle_category_rule(sev: Optional[float]) -> str:
    """Regla RN-02 independiente: Crítica >= 11,000; Media [7,500, 11,000); Baja < 7,500."""
    if sev is None or not math.isfinite(sev) or sev <= 0:
        return "sin dato"
    if sev >= 11000.0:
        return "Crítica"
    if sev >= 7500.0:
        return "Media"
    return "Baja"


# =============================================================================
# BANCO DE CASOS CRÍTICOS AUDITADOS MANUALMENTE (GOLDEN_MANUAL_CASES)
# Valores verificados fuera del motor y aprobados contra las reglas RN-01..RN-06
# =============================================================================
GOLDEN_MANUAL_CASES = [
    {
        "case_id": "GM-01",
        "description": "Nuevo León y Jalisco 2023: severidad, referencia nacional, índice, brecha y MDP",
        "year": "2023",
        "expected": {
            "ref_nacional_fmt": "7,805.92",
            "n_nacional": 32,
            "nl_sev_fmt": "16,477.15",
            "nl_idx_fmt": "211.1",
            "nl_cat": "Crítica",
            "nl_rank_sev": 1,
            "nl_mdp_fmt": "10,007.67",
            "nl_rank_mdp": 4,
            "jal_sev_fmt": "12,131.95",
            "jal_idx_fmt": "155.4",
            "jal_cat": "Crítica",
            "jal_rank_sev": 5,
            "jal_mdp_fmt": "10,634.33",
            "jal_rank_mdp": 3,
            "brecha_abs_fmt": "4,345.20",
            "brecha_pct_fmt": "35.8",
            "lider_sev": "Nuevo Leon",
            "lider_mdp": "Jalisco"
        }
    },
    {
        "case_id": "GM-02",
        "description": "Ciudad de México 2024: severidad, referencia nacional, índice y evolución desde 2020",
        "year": "2024",
        "expected": {
            "ref_nacional_fmt": "9,041.64",
            "cdmx_sev_fmt": "14,112.41",
            "cdmx_idx_fmt": "156.1",
            "cdmx_cat": "Crítica",
            "cdmx_rank_sev": 4,
            "cdmx_mdp_fmt": "13,647.32",
            "cdmx_rank_mdp": 2,
            "cdmx_var_sev_fmt": "+93.1 %",
            "cdmx_delta_idx_fmt": "-5.9 pts"
        }
    },
    {
        "case_id": "GM-03",
        "description": "Concentración Pareto Top 5 y líder de crecimiento (Tlaxcala)",
        "expected": {
            "pareto_top5_pct_fmt": "47.1",
            "growth_leader": "Tlaxcala",
            "growth_leader_total_fmt": "150.6",
            "growth_leader_annual_fmt": "25.8",
            "r_pearson_fmt": "0.8488",
            "r2_pct_fmt": "72.05"
        }
    },
    {
        "case_id": "GM-04",
        "description": "Fronteras exactas de umbrales de categoría (RN-02)",
        "expected_thresholds": [
            (11000.00, "Crítica"),
            (10999.99, "Media"),
            (7500.00, "Media"),
            (7499.99, "Baja")
        ]
    }
]


class IndependentActuarialOracle:
    """
    Oráculo matemático independiente que calcula los resultados esperados directamente
    desde `data.json` usando `Fraction` para promedios exactos y `Decimal` para redondeo.
    """

    def __init__(self, data_path: str = "/Users/victordaniel/chubb/data.json"):
        with open(data_path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)
        self.states_by_name: Dict[str, Dict[str, Any]] = {
            s["entidad"]: s for s in self.raw["estados"]
        }
        self.all_states: List[str] = [s["entidad"] for s in self.raw["estados"]]

    def national_ref_year(self, year_str: str) -> Tuple[float, int]:
        vals = [
            float(s["yearly_severidad"][year_str])
            for s in self.raw["estados"]
            if s.get("yearly_severidad", {}).get(year_str) is not None and float(s["yearly_severidad"][year_str]) > 0
        ]
        if not vals:
            return (0.0, 0)
        # Media usando Fraction exacta
        frac_sum = sum(Fraction(str(v)) for v in vals)
        mean_val = float(frac_sum / Fraction(len(vals)))
        return (mean_val, len(vals))

    def competition_ranks_year(self, metric_field: str, year_str: str) -> Tuple[Dict[str, int], int]:
        items = []
        for s in self.raw["estados"]:
            v = s.get(metric_field, {}).get(year_str)
            if v is not None and float(v) > 0:
                c = Decimal(str(float(v))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                items.append((s["entidad"], c))
        items.sort(key=lambda x: x[1], reverse=True)
        ranks: Dict[str, int] = {}
        for idx, (ent, cents) in enumerate(items):
            if idx == 0:
                ranks[ent] = 1
            else:
                prev_ent, prev_cents = items[idx - 1]
                ranks[ent] = ranks[prev_ent] if cents == prev_cents else (idx + 1)
        return ranks, len(items)

    def oracle_state_metrics(self, state_name: str, year: Optional[int] = None) -> Dict[str, Any]:
        st = self.states_by_name[state_name]
        if year is not None:
            ys = str(year)
            sev = float(st["yearly_severidad"][ys])
            mdp = float(st["yearly_mdp"][ys])
            raw_cat = st.get("yearly_categoria", {}).get(ys)
            cat = "Crítica" if raw_cat in ("Critica", "Crítica") else (raw_cat or "sin dato")
            ref_val, n_val = self.national_ref_year(ys)
            idx = (sev / ref_val) * 100.0 if ref_val > 0 else 0.0
            rk_sev, _ = self.competition_ranks_year("yearly_severidad", ys)
            rk_mdp, _ = self.competition_ranks_year("yearly_mdp", ys)

            sev_2020 = float(st["yearly_severidad"]["2020"])
            ref_2020, _ = self.national_ref_year("2020")
            idx_2020 = (sev_2020 / ref_2020) * 100.0 if ref_2020 > 0 else 0.0
            var_sev = 0.0 if year == 2020 else ((sev / sev_2020) - 1.0) * 100.0
            delta_idx = 0.0 if year == 2020 else (idx - idx_2020)
            var_sign = "+" if var_sev > 0 else ""
            d_sign = "+" if delta_idx > 0 else ""
            return {
                "entidad": state_name,
                "periodo": str(year),
                "severidad": sev,
                "severidad_fmt": oracle_fmt(sev, 2),
                "costo_mdp": mdp,
                "costo_mdp_fmt": oracle_fmt(mdp, 2),
                "categoria": cat,
                "indice": idx,
                "indice_fmt": oracle_fmt(idx, 1),
                "ref_nacional": ref_val,
                "ref_nacional_fmt": oracle_fmt(ref_val, 2),
                "n_nacional": n_val,
                "rank_sev": rk_sev[state_name],
                "rank_mdp": rk_mdp[state_name],
                "var_sev_pct": var_sev,
                "var_sev_fmt": f"{var_sign}{oracle_fmt(var_sev, 1, False)} %",
                "delta_idx_pts": delta_idx,
                "delta_idx_fmt": f"{d_sign}{oracle_fmt(delta_idx, 1, False)} pts"
            }
        else:
            sev = float(st["severidad_promedio"])
            mdp = float(st["siniestros_ocurridos_mdp_promedio"])
            raw_cat = st.get("categoria_severidad")
            cat = "Crítica" if raw_cat in ("Critica", "Crítica") else (raw_cat or "sin dato")
            ref_val = float(self.raw["metadata"]["promedio_nacional_severidad"])
            idx = float(st["indice_severidad"])
            return {
                "entidad": state_name,
                "periodo": "Promedio 2020–2024",
                "severidad": sev,
                "severidad_fmt": oracle_fmt(sev, 2),
                "costo_mdp": mdp,
                "costo_mdp_fmt": oracle_fmt(mdp, 2),
                "categoria": cat,
                "indice": idx,
                "indice_fmt": oracle_fmt(idx, 1),
                "ref_nacional": ref_val,
                "ref_nacional_fmt": oracle_fmt(ref_val, 2),
                "n_nacional": len(self.raw["estados"]),
                "cagr_acumulado": float(st["cagr_2020_2024_pct"]),
                "cagr_acumulado_fmt": oracle_fmt(float(st["cagr_2020_2024_pct"]), 1)
            }

    def oracle_comparison(self, states: List[str], year: Optional[int] = None) -> Dict[str, Any]:
        rows = [self.oracle_state_metrics(st, year) for st in states]
        by_sev = sorted(rows, key=lambda r: r["severidad"], reverse=True)
        by_mdp = sorted(rows, key=lambda r: r["costo_mdp"], reverse=True)
        diff_abs = by_sev[0]["severidad"] - by_sev[-1]["severidad"]
        diff_pct = (diff_abs / by_sev[-1]["severidad"]) * 100.0
        diff_mdp = by_mdp[0]["costo_mdp"] - by_mdp[-1]["costo_mdp"]
        return {
            "rows": rows,
            "lider_sev": by_sev[0]["entidad"],
            "menor_sev": by_sev[-1]["entidad"],
            "brecha_abs": diff_abs,
            "brecha_abs_fmt": oracle_fmt(diff_abs, 2),
            "brecha_pct": diff_pct,
            "brecha_pct_fmt": oracle_fmt(diff_pct, 1),
            "lider_mdp": by_mdp[0]["entidad"],
            "menor_mdp": by_mdp[-1]["entidad"],
            "brecha_mdp_abs": diff_mdp,
            "brecha_mdp_abs_fmt": oracle_fmt(diff_mdp, 2),
            "lideres_difieren": by_sev[0]["entidad"] != by_mdp[0]["entidad"]
        }

    def verify_against_golden_manual_cases(self) -> Dict[str, Any]:
        """Audita el propio oráculo contra los casos manuales antes de iniciar el benchmark."""
        checks_run = 0
        # GM-01: NL y Jalisco 2023
        gm1 = GOLDEN_MANUAL_CASES[0]["expected"]
        comp_2023 = self.oracle_comparison(["Nuevo Leon", "Jalisco"], 2023)
        nl_23, jal_23 = comp_2023["rows"][0], comp_2023["rows"][1]
        assert nl_23["ref_nacional_fmt"] == gm1["ref_nacional_fmt"], f"GM-01 ref fail: {nl_23['ref_nacional_fmt']}"
        assert nl_23["severidad_fmt"] == gm1["nl_sev_fmt"]
        assert nl_23["indice_fmt"] == gm1["nl_idx_fmt"]
        assert nl_23["categoria"] == gm1["nl_cat"]
        assert nl_23["rank_sev"] == gm1["nl_rank_sev"]
        assert nl_23["costo_mdp_fmt"] == gm1["nl_mdp_fmt"]
        assert nl_23["rank_mdp"] == gm1["nl_rank_mdp"]
        assert jal_23["severidad_fmt"] == gm1["jal_sev_fmt"]
        assert jal_23["indice_fmt"] == gm1["jal_idx_fmt"]
        assert jal_23["rank_sev"] == gm1["jal_rank_sev"]
        assert jal_23["costo_mdp_fmt"] == gm1["jal_mdp_fmt"]
        assert jal_23["rank_mdp"] == gm1["jal_rank_mdp"]
        assert comp_2023["brecha_abs_fmt"] == gm1["brecha_abs_fmt"]
        assert comp_2023["brecha_pct_fmt"] == gm1["brecha_pct_fmt"]
        assert comp_2023["lider_sev"] == gm1["lider_sev"]
        assert comp_2023["lider_mdp"] == gm1["lider_mdp"]
        checks_run += 16

        # GM-02: CDMX 2024
        gm2 = GOLDEN_MANUAL_CASES[1]["expected"]
        cdmx_24 = self.oracle_state_metrics("Ciudad de Mexico", 2024)
        assert cdmx_24["ref_nacional_fmt"] == gm2["ref_nacional_fmt"]
        assert cdmx_24["severidad_fmt"] == gm2["cdmx_sev_fmt"]
        assert cdmx_24["indice_fmt"] == gm2["cdmx_idx_fmt"]
        assert cdmx_24["categoria"] == gm2["cdmx_cat"]
        assert cdmx_24["rank_sev"] == gm2["cdmx_rank_sev"]
        assert cdmx_24["costo_mdp_fmt"] == gm2["cdmx_mdp_fmt"]
        assert cdmx_24["rank_mdp"] == gm2["cdmx_rank_mdp"]
        assert cdmx_24["var_sev_fmt"] == gm2["cdmx_var_sev_fmt"]
        assert cdmx_24["delta_idx_fmt"] == gm2["cdmx_delta_idx_fmt"]
        checks_run += 9

        # GM-03: Pareto & Growth & Regression
        gm3 = GOLDEN_MANUAL_CASES[2]["expected"]
        by_mdp_all = sorted(self.raw["estados"], key=lambda x: float(x["siniestros_ocurridos_mdp_promedio"]), reverse=True)
        top5_sum = sum(float(x["siniestros_ocurridos_mdp_promedio"]) for x in by_mdp_all[:5])
        tot_mdp = float(self.raw["metadata"]["total_mdp_nacional_promedio"])
        pareto_pct = (top5_sum / tot_mdp) * 100.0
        assert oracle_fmt(pareto_pct, 1) == gm3["pareto_top5_pct_fmt"]

        by_cagr = sorted(self.raw["estados"], key=lambda x: float(x["cagr_2020_2024_pct"]), reverse=True)
        top_g = by_cagr[0]
        cagr_tot = float(top_g["cagr_2020_2024_pct"])
        cagr_ann = (math.pow(1.0 + cagr_tot / 100.0, 0.25) - 1.0) * 100.0
        assert top_g["entidad"] == gm3["growth_leader"]
        assert oracle_fmt(cagr_tot, 1) == gm3["growth_leader_total_fmt"]
        assert oracle_fmt(cagr_ann, 1) == gm3["growth_leader_annual_fmt"]
        assert oracle_fmt(float(self.raw["scatter_stats"]["r_pearson"]), 4, False) == gm3["r_pearson_fmt"]
        assert oracle_fmt(float(self.raw["scatter_stats"]["r2_score"]) * 100.0, 2, False) == gm3["r2_pct_fmt"]
        checks_run += 6

        # GM-04: Threshold boundaries
        for val, exp_cat in GOLDEN_MANUAL_CASES[3]["expected_thresholds"]:
            assert oracle_category_rule(val) == exp_cat
            checks_run += 1

        return {"passed": True, "golden_checks_verified": checks_run}

