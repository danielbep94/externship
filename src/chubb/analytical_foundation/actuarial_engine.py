"""
Analytical Foundation — Actuarial Operations Engine.
Executes all runtime calculations, ratios, rankings, executive summaries, and recommendations
directly from curated dataset with zero hardcoded figures and full Python-JS mathematical parity.
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from chubb.analytical_foundation.calculations import (
    round_half_up_decimal,
    format_number,
    display_category_label,
)
from chubb.analytical_foundation.aggregations import (
    is_valid_severity,
    is_valid_mdp,
    compute_national_reference,
    compute_competition_ranks,
)


class ActuarialOperationsEngine:
    """
    Motor de operaciones actuariales que calcula en tiempo de ejecución todas
    las cifras, ratios, rankings y agregaciones directamente desde data.json.
    Garantiza CERO cifras hardcodeadas y paridad matemática con JS.
    """

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.metadata = data["metadata"]
        self.estados_list = data["estados"]
        self.estados_dict = {s["entidad"]: s for s in self.estados_list}
        self.scatter_stats = data["scatter_stats"]

        self.national_avg_severity = float(self.metadata["promedio_nacional_severidad"])
        self.total_national_mdp = float(self.metadata["total_mdp_nacional_promedio"])

    @staticmethod
    def is_valid_severity(val: Any) -> bool:
        """Severidad válida: número finito y > 0."""
        return is_valid_severity(val)

    @staticmethod
    def is_valid_mdp(val: Any) -> bool:
        """MDP válido en el año consultado: número finito y >= 0."""
        return is_valid_mdp(val)

    def compute_national_reference_for_year(self, year_str: str) -> Tuple[Optional[float], int]:
        """
        Calcula la referencia nacional para un año como la media simple de las entidades con severidad válida.
        Retorna (media_ref, n_entidades_con_dato).
        """
        return compute_national_reference(self.estados_list, year_str)

    def compute_competition_ranks_for_year(self, year_str: str) -> Dict[str, Any]:
        """
        Calcula rankings nacionales de competencia ('1, 1, 3') comparando valores redondeados al centavo (2 decimales).
        El denominador refleja las entidades con dato válido para cada métrica y año.
        """
        return compute_competition_ranks(self.estados_list, year_str)

    def compute_executive_summary(self, state_names: List[str], target_year: int) -> Dict[str, Any]:
        """
        Calcula todos los indicadores del Resumen Ejecutivo (single o multistate) para el año target_year:
        - Referencia nacional (media de severidad de las entidades con dato y conteo n).
        - Severidad, índice relativo, categoría anual (nunca sustituida por la del periodo) y posición nacional.
        - Costo total en MDP y posición nacional.
        - Evolución 2020 -> target_year (severidad %, MDP % y Δ índice en pts).
        - Rankings dentro de la selección (cuando len(state_names) >= 2) y detección de líderes distintos.
        """
        yr_str = str(target_year)
        media_ref_Y, n_ref_Y = self.compute_national_reference_for_year(yr_str)
        media_ref_2020, _ = self.compute_national_reference_for_year("2020")
        nat_ranks = self.compute_competition_ranks_for_year(yr_str)

        rows: List[Dict[str, Any]] = []
        for name in state_names:
            st = self.estados_dict[name]
            raw_sev_Y = st.get("yearly_severidad", {}).get(yr_str)
            raw_mdp_Y = st.get("yearly_mdp", {}).get(yr_str)
            raw_cat_Y = st.get("yearly_categoria", {}).get(yr_str)

            sev_Y = float(raw_sev_Y) if self.is_valid_severity(raw_sev_Y) else None
            mdp_Y = float(raw_mdp_Y) if self.is_valid_mdp(raw_mdp_Y) else None

            if sev_Y is not None and raw_cat_Y in {"Baja", "Media", "Critica", "Crítica"}:
                cat_Y = display_category_label(raw_cat_Y)
            else:
                cat_Y = None

            if sev_Y is not None and media_ref_Y is not None and media_ref_Y > 0:
                indice_Y = (sev_Y / media_ref_Y) * 100.0
            else:
                indice_Y = None

            raw_sev_2020 = st.get("yearly_severidad", {}).get("2020")
            sev_2020 = float(raw_sev_2020) if self.is_valid_severity(raw_sev_2020) else None

            raw_mdp_2020 = st.get("yearly_mdp", {}).get("2020")
            mdp_2020 = float(raw_mdp_2020) if (self.is_valid_mdp(raw_mdp_2020) and float(raw_mdp_2020) > 0.0) else None

            if sev_Y is not None and sev_2020 is not None:
                var_sev_pct = 0.0 if target_year == 2020 else ((sev_Y / sev_2020) - 1.0) * 100.0
            else:
                var_sev_pct = None

            if mdp_Y is not None and mdp_2020 is not None:
                var_mdp_pct = 0.0 if target_year == 2020 else ((mdp_Y / mdp_2020) - 1.0) * 100.0
            else:
                var_mdp_pct = None

            if sev_2020 is not None and media_ref_2020 is not None and media_ref_2020 > 0:
                indice_2020 = (sev_2020 / media_ref_2020) * 100.0
            else:
                indice_2020 = None

            if indice_Y is not None and indice_2020 is not None:
                delta_indice_pts = 0.0 if target_year == 2020 else (indice_Y - indice_2020)
            else:
                delta_indice_pts = None

            rk_sev = nat_ranks["severidad"].get(name)
            rk_mdp = nat_ranks["costo_mdp"].get(name)

            rows.append({
                "entidad": name,
                "severidad": sev_Y,
                "severidad_fmt": format_number(sev_Y, 2) if sev_Y is not None else "sin dato",
                "indice": indice_Y,
                "indice_fmt": format_number(indice_Y, 1) if indice_Y is not None else "no calculable",
                "indice_2020": indice_2020,
                "indice_2020_fmt": format_number(indice_2020, 1) if indice_2020 is not None else "no calculable",
                "categoria": cat_Y if cat_Y is not None else "sin dato",
                "costo_mdp": mdp_Y,
                "costo_mdp_fmt": format_number(mdp_Y, 2) if mdp_Y is not None else "sin dato",
                "rank_nacional_severidad": rk_sev[0] if rk_sev else None,
                "n_nacional_severidad": rk_sev[1] if rk_sev else nat_ranks["n_severidad"],
                "rank_nacional_mdp": rk_mdp[0] if rk_mdp else None,
                "n_nacional_mdp": rk_mdp[1] if rk_mdp else nat_ranks["n_costo_mdp"],
                "var_severidad_pct": var_sev_pct,
                "var_severidad_fmt": (f"{'+' if round_half_up_decimal(var_sev_pct, 1) > 0 else ''}{format_number(var_sev_pct, 1)} %" if var_sev_pct is not None else "no calculable"),
                "var_mdp_pct": var_mdp_pct,
                "var_mdp_fmt": (f"{'+' if round_half_up_decimal(var_mdp_pct, 1) > 0 else ''}{format_number(var_mdp_pct, 1)} %" if var_mdp_pct is not None else "no calculable"),
                "delta_indice_pts": delta_indice_pts,
                "delta_indice_fmt": (f"{'+' if round_half_up_decimal(delta_indice_pts, 1) > 0 else ''}{format_number(delta_indice_pts, 1)} pts" if delta_indice_pts is not None else "no calculable"),
                "automoviles_registrados": st.get("automoviles_registrados"),
                "poblacion_2020": st.get("poblacion_2020")
            })

        selection_summary: Optional[Dict[str, Any]] = None
        if len(state_names) >= 2:
            valid_sev_rows = [r for r in rows if r["severidad"] is not None]
            valid_mdp_rows = [r for r in rows if r["costo_mdp"] is not None]

            valid_sev_rows.sort(key=lambda r: round_half_up_decimal(r["severidad"], 2), reverse=True)
            valid_mdp_rows.sort(key=lambda r: round_half_up_decimal(r["costo_mdp"], 2), reverse=True)

            lider_sev = valid_sev_rows[0]["entidad"] if valid_sev_rows else None
            menor_sev = valid_sev_rows[-1]["entidad"] if len(valid_sev_rows) >= 2 else None
            brecha_sev_abs = (valid_sev_rows[0]["severidad"] - valid_sev_rows[-1]["severidad"]) if len(valid_sev_rows) >= 2 else None
            brecha_sev_pct = ((brecha_sev_abs / valid_sev_rows[-1]["severidad"]) * 100.0) if (brecha_sev_abs is not None and valid_sev_rows[-1]["severidad"] > 0) else None

            lider_mdp = valid_mdp_rows[0]["entidad"] if valid_mdp_rows else None
            menor_mdp = valid_mdp_rows[-1]["entidad"] if len(valid_mdp_rows) >= 2 else None
            brecha_mdp_abs = (valid_mdp_rows[0]["costo_mdp"] - valid_mdp_rows[-1]["costo_mdp"]) if len(valid_mdp_rows) >= 2 else None

            selection_summary = {
                "orden_severidad": [r["entidad"] for r in valid_sev_rows],
                "orden_mdp": [r["entidad"] for r in valid_mdp_rows],
                "lider_severidad": lider_sev,
                "menor_severidad": menor_sev,
                "brecha_severidad_abs": brecha_sev_abs,
                "brecha_severidad_abs_fmt": format_number(brecha_sev_abs, 2) if brecha_sev_abs is not None else "no calculable",
                "brecha_severidad_pct": brecha_sev_pct,
                "brecha_severidad_pct_fmt": format_number(brecha_sev_pct, 1) if brecha_sev_pct is not None else "no calculable",
                "lider_mdp": lider_mdp,
                "menor_mdp": menor_mdp,
                "brecha_mdp_abs": brecha_mdp_abs,
                "brecha_mdp_abs_fmt": format_number(brecha_mdp_abs, 2) if brecha_mdp_abs is not None else "no calculable",
                "lideres_difieren": bool(lider_sev and lider_mdp and lider_sev != lider_mdp)
            }

        all_sev_missing = all(r["severidad"] is None for r in rows)
        all_mdp_missing = all(r["costo_mdp"] is None for r in rows)

        return {
            "target_year": target_year,
            "national_reference": {
                "method": "simple_mean_entities_with_data",
                "label": "Media de severidad de las entidades con dato",
                "value": media_ref_Y,
                "value_fmt": format_number(media_ref_Y, 2) if media_ref_Y is not None else "no calculable",
                "n": n_ref_Y
            },
            "rows": rows,
            "selection_summary": selection_summary,
            "all_severidad_missing": all_sev_missing,
            "all_mdp_missing": all_mdp_missing
        }

    def compute_recommendations_and_opportunities(self, state_names: List[str], target_year: int) -> Dict[str, Any]:
        """
        Calcula métricas diagnósticas, benchmarks nacionales y hallazgos basados en datos reales
        para sustentar recomendaciones técnicas, acciones preventivas e identificación de oportunidades.
        """
        exec_summary = self.compute_executive_summary(state_names, target_year) if state_names else None
        yr_str = str(target_year)

        media_ref_2020, _ = self.compute_national_reference_for_year("2020")
        media_ref_2024, _ = self.compute_national_reference_for_year("2024")
        nat_cagr_acum = ((media_ref_2024 - media_ref_2020) / media_ref_2020) * 100.0 if (media_ref_2020 and media_ref_2024) else 0.0
        nat_cagr_anual = (math.pow(1.0 + nat_cagr_acum / 100.0, 0.25) - 1.0) * 100.0

        n_est = len(self.estados_list) if self.estados_list else 1
        nat_precio_auto_k = sum(float(s["precio_promedio_auto_ml_k_mxn"]) for s in self.estados_list) / n_est
        nat_motorizacion = sum(float(s["autos_por_1000_hab"]) for s in self.estados_list) / n_est

        total_mdp_yr = sum(
            float(s["yearly_mdp"][yr_str])
            for s in self.estados_list
            if self.is_valid_mdp(s.get("yearly_mdp", {}).get(yr_str))
        )

        r_val = float(self.scatter_stats["r_pearson"])
        r2_pct = float(self.scatter_stats["r2_score"]) * 100.0

        enriched_rows = []
        if exec_summary:
            for r in exec_summary["rows"]:
                st = self.estados_dict[r["entidad"]]
                cagr_acum = float(st["cagr_2020_2024_pct"])
                cagr_anual = (math.pow(1.0 + cagr_acum / 100.0, 0.25) - 1.0) * 100.0
                precio_k = float(st["precio_promedio_auto_ml_k_mxn"])
                motor = float(st["autos_por_1000_hab"])
                costo_auto = float(st["costo_por_auto_registrado"])
                sev_prom = float(st["severidad_promedio"])
                cat_per = display_category_label(st["categoria_severidad"])
                pct_mdp_yr = (r["costo_mdp"] / total_mdp_yr) * 100.0 if (r["costo_mdp"] is not None and total_mdp_yr > 0) else None

                row_copy = dict(r)
                row_copy.update({
                    "severidad_promedio": sev_prom,
                    "severidad_promedio_fmt": format_number(sev_prom, 2),
                    "categoria_periodo": cat_per,
                    "cagr_acumulado": cagr_acum,
                    "cagr_acumulado_fmt": f"+{format_number(cagr_acum, 1)} %",
                    "cagr_anual": cagr_anual,
                    "cagr_anual_fmt": f"+{format_number(cagr_anual, 1)} %",
                    "precio_auto_k": precio_k,
                    "precio_auto_k_fmt": format_number(precio_k, 0),
                    "autos_por_1000_hab": motor,
                    "autos_por_1000_hab_fmt": format_number(motor, 1),
                    "costo_por_auto": costo_auto,
                    "costo_por_auto_fmt": format_number(costo_auto, 2),
                    "pct_costo_nacional_yr": pct_mdp_yr,
                    "pct_costo_nacional_yr_fmt": format_number(pct_mdp_yr, 1) if pct_mdp_yr is not None else "no calculable"
                })
                enriched_rows.append(row_copy)

        return {
            "scope": "state" if state_names else "national",
            "target_year": target_year,
            "national_reference": exec_summary["national_reference"] if exec_summary else {
                "method": "simple_mean_entities_with_data",
                "label": "Media de severidad de las entidades con dato",
                "value": media_ref_2024 if target_year == 2024 else self.compute_national_reference_for_year(yr_str)[0],
                "value_fmt": format_number(media_ref_2024 if target_year == 2024 else (self.compute_national_reference_for_year(yr_str)[0] or 0.0), 2),
                "n": len(self.estados_list)
            },
            "rows": enriched_rows,
            "selection_summary": exec_summary["selection_summary"] if exec_summary else None,
            "national_benchmarks": {
                "nat_cagr_acum": nat_cagr_acum,
                "nat_cagr_acum_fmt": f"+{format_number(nat_cagr_acum, 1)} %",
                "nat_cagr_anual": nat_cagr_anual,
                "nat_cagr_anual_fmt": f"+{format_number(nat_cagr_anual, 1)} %",
                "nat_precio_auto_k": nat_precio_auto_k,
                "nat_precio_auto_k_fmt": format_number(nat_precio_auto_k, 1),
                "nat_motorizacion": nat_motorizacion,
                "nat_motorizacion_fmt": format_number(nat_motorizacion, 1),
                "total_mdp_yr": total_mdp_yr,
                "total_mdp_yr_fmt": format_number(total_mdp_yr, 2),
                "r_pearson": r_val,
                "r_pearson_fmt": format_number(r_val, 4, False),
                "r2_pct": r2_pct,
                "r2_pct_fmt": format_number(r2_pct, 2)
            },
            "portfolio_context": None if state_names else {
                "findings": self.compute_three_key_findings(),
                "pareto": self.compute_pareto_breakdown(5),
                "top_sev": self.compute_severity_rankings(5),
                "growth": self.compute_growth_rankings(3)
            }
        }

    def compute_severity_rankings(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Calcula el Top N dinámico de estados con mayor severidad promedio."""
        valid_states = [s for s in self.estados_list if self.is_valid_severity(s.get("severidad_promedio"))]
        sorted_by_sev = sorted(valid_states, key=lambda x: x["severidad_promedio"], reverse=True)
        return [
            {
                "rank": i + 1,
                "entidad": s["entidad"],
                "severidad": float(s["severidad_promedio"]),
                "costo_mdp": float(s["siniestros_ocurridos_mdp_promedio"]),
                "indice": float(s["indice_severidad"])
            }
            for i, s in enumerate(sorted_by_sev[:top_n])
        ]

    def get_state_metrics(self, state_name: str, target_year: Optional[int] = None) -> Dict[str, Any]:
        """Obtiene las métricas precisas de un estado para el periodo indicado."""
        st = self.estados_dict[state_name]
        if target_year is not None:
            yr_str = str(target_year)
            raw_sev = st["yearly_severidad"].get(yr_str)
            raw_mdp = st["yearly_mdp"].get(yr_str)
            raw_cat = st["yearly_categoria"].get(yr_str)

            sev = float(raw_sev) if self.is_valid_severity(raw_sev) else None
            mdp = float(raw_mdp) if self.is_valid_mdp(raw_mdp) else None
            cat = raw_cat if (sev is not None and raw_cat in {"Baja", "Media", "Critica", "Crítica"}) else "sin dato"

            nat_yr_avg, n_yr = self.compute_national_reference_for_year(yr_str)
            idx_rel = (sev / nat_yr_avg) * 100.0 if (sev is not None and nat_yr_avg is not None and nat_yr_avg > 0) else None
            label_period = f"Año {target_year}"
            nat_avg = nat_yr_avg
        else:
            sev = float(st["severidad_promedio"]) if self.is_valid_severity(st.get("severidad_promedio")) else None
            mdp = float(st["siniestros_ocurridos_mdp_promedio"]) if self.is_valid_mdp(st.get("siniestros_ocurridos_mdp_promedio")) else None
            cat = st.get("categoria_severidad") if sev is not None else "sin dato"
            idx_rel = float(st["indice_severidad"]) if st.get("indice_severidad") is not None else None
            label_period = "Promedio 2020–2024"
            nat_avg = self.national_avg_severity
            n_yr = len(self.estados_list)

        return {
            "entidad": state_name,
            "periodo": label_period,
            "target_year": target_year,
            "severidad": sev,
            "costo_mdp": mdp,
            "categoria": cat,
            "indice_severidad": idx_rel,
            "promedio_nacional": nat_avg,
            "n_entidades_nacional": n_yr,
            "cagr_acumulado": float(st["cagr_2020_2024_pct"]),
            "automoviles_registrados": int(st["automoviles_registrados"]),
            "precio_auto_k_mxn": float(st["precio_promedio_auto_ml_k_mxn"])
        }

    def compute_three_key_findings(self) -> Dict[str, Any]:
        """Calcula dinámicamente los 3 hallazgos clave del reporte."""
        sorted_by_mdp = sorted(self.estados_list, key=lambda x: x["siniestros_ocurridos_mdp_promedio"], reverse=True)
        top5 = sorted_by_mdp[:5]
        top5_mdp_sum = sum(s["siniestros_ocurridos_mdp_promedio"] for s in top5)
        pareto_pct = (top5_mdp_sum / self.total_national_mdp) * 100.0

        sorted_by_sev = sorted(self.estados_list, key=lambda x: x["severidad_promedio"], reverse=True)
        max_st = sorted_by_sev[0]
        min_st = sorted_by_sev[-1]
        ratio_max_min = max_st["severidad_promedio"] / min_st["severidad_promedio"]

        sorted_by_cagr = sorted(self.estados_list, key=lambda x: x["cagr_2020_2024_pct"], reverse=True)
        leader_growth = sorted_by_cagr[0]
        cagr_annual = (math.pow(1 + leader_growth["cagr_2020_2024_pct"] / 100.0, 1/4) - 1) * 100.0

        r = float(self.scatter_stats["r_pearson"])
        r2 = float(self.scatter_stats["r2_score"]) * 100.0

        return {
            "pareto_top5": [
                {"entidad": s["entidad"], "mdp": s["siniestros_ocurridos_mdp_promedio"], "pct": s["pct_costo_nacional"]}
                for s in top5
            ],
            "top5_mdp_sum": top5_mdp_sum,
            "total_national_mdp": self.total_national_mdp,
            "pareto_pct": pareto_pct,
            "max_state": {"entidad": max_st["entidad"], "severidad": max_st["severidad_promedio"], "idx": max_st["indice_severidad"]},
            "min_state": {"entidad": min_st["entidad"], "severidad": min_st["severidad_promedio"], "idx": min_st["indice_severidad"]},
            "ratio_max_min": ratio_max_min,
            "growth_leader": {
                "entidad": leader_growth["entidad"],
                "cagr_total": leader_growth["cagr_2020_2024_pct"],
                "cagr_anual": cagr_annual
            },
            "regression": {"r": r, "r2_pct": r2, "p_value": self.scatter_stats["p_value"]}
        }

    def compute_multi_state_comparison(self, state_names: List[str], target_year: Optional[int] = None) -> Dict[str, Any]:
        """Calcula la comparativa multidimensional dinámica para N estados (N >= 2)."""
        metrics = [self.get_state_metrics(name, target_year) for name in state_names]
        valid_metrics = [m for m in metrics if m["severidad"] is not None]
        valid_metrics.sort(key=lambda x: x["severidad"], reverse=True)

        highest = valid_metrics[0] if valid_metrics else metrics[0]
        lowest = valid_metrics[-1] if valid_metrics else metrics[-1]
        abs_diff = (highest["severidad"] - lowest["severidad"]) if (highest["severidad"] is not None and lowest["severidad"] is not None) else 0.0
        pct_diff = (abs_diff / lowest["severidad"]) * 100.0 if (lowest["severidad"] and lowest["severidad"] > 0) else 0.0

        valid_mdp = [m for m in metrics if m["costo_mdp"] is not None]
        sorted_by_mdp = sorted(valid_mdp, key=lambda x: x["costo_mdp"], reverse=True) if valid_mdp else metrics

        return {
            "estados_metricas": valid_metrics if valid_metrics else metrics,
            "periodo": metrics[0]["periodo"],
            "target_year": target_year,
            "lider_severidad": highest["entidad"],
            "menor_severidad": lowest["entidad"],
            "diferencia_absoluta": abs_diff,
            "diferencia_porcentual": pct_diff,
            "lider_volumen_mdp": sorted_by_mdp[0]["entidad"],
            "requiere_distincion_actuarial": (highest["entidad"] != sorted_by_mdp[0]["entidad"])
        }

    def compute_pareto_breakdown(self, top_k: int = 5) -> Dict[str, Any]:
        """Calcula el desglose dinámico de Pareto en MDP."""
        sorted_states = sorted(self.estados_list, key=lambda x: x["siniestros_ocurridos_mdp_promedio"], reverse=True)
        top_slice = sorted_states[:top_k]
        sum_k = sum(s["siniestros_ocurridos_mdp_promedio"] for s in top_slice)
        pct_k = (sum_k / self.total_national_mdp) * 100.0

        return {
            "top_k": top_k,
            "top_states": [
                {
                    "rank": i + 1,
                    "entidad": s["entidad"],
                    "mdp": s["siniestros_ocurridos_mdp_promedio"],
                    "pct_nacional": s["pct_costo_nacional"]
                }
                for i, s in enumerate(top_slice)
            ],
            "sum_k_mdp": sum_k,
            "total_national_mdp": self.total_national_mdp,
            "pct_k": pct_k
        }

    def compute_growth_rankings(self, top_n: int = 3) -> Dict[str, Any]:
        """Calcula el ranking dinámico de crecimiento histórico y CAGR."""
        sorted_cagr = sorted(self.estados_list, key=lambda x: x["cagr_2020_2024_pct"], reverse=True)
        leaders = []
        for s in sorted_cagr[:top_n]:
            cagr_anual = (math.pow(1 + s["cagr_2020_2024_pct"] / 100.0, 1/4) - 1) * 100.0
            leaders.append({
                "entidad": s["entidad"],
                "cagr_acumulado": s["cagr_2020_2024_pct"],
                "cagr_anual": cagr_anual,
                "sev_2020": s["yearly_severidad"]["2020"],
                "sev_2024": s["yearly_severidad"]["2024"]
            })

        nat_2020, _ = self.compute_national_reference_for_year("2020")
        nat_2024, _ = self.compute_national_reference_for_year("2024")
        nat_cagr_total = ((nat_2024 - nat_2020) / nat_2020) * 100.0 if (nat_2020 and nat_2024) else 0.0
        nat_cagr_anual = (math.pow(1 + nat_cagr_total / 100.0, 1/4) - 1) * 100.0

        return {
            "leaders": leaders,
            "nacional": {
                "sev_2020": nat_2020,
                "sev_2024": nat_2024,
                "cagr_total": nat_cagr_total,
                "cagr_anual": nat_cagr_anual
            }
        }

