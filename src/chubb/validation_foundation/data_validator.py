"""
Validation Foundation — Dataset Schema, Referential Integrity & Methodological Consistency Validator.
Separates structural schema errors (raising DataIntegrityError) from missing observations (nulls recorded in data_quality).
"""

import json
import math
from typing import Dict, List, Any
from chubb.contracts.error_contract import DataIntegrityError
from chubb.analytical_foundation.calculations import compute_category_from_rule
from chubb.infrastructure.paths import resolve_data_path


class ActuarialDataValidator:
    """
    Valida y carga data.json garantizando integridad referencial y metodológica (SSOT).
    Separa:
    - Errores de esquema (detienen la carga lanzando DataIntegrityError).
    - Observaciones faltantes (permitidas como None/null y registradas en data_quality).
    """

    REQUIRED_METADATA_KEYS = {"titulo", "periodo", "promedio_nacional_severidad", "total_mdp_nacional_promedio", "fechas_corte"}
    REQUIRED_STATE_KEYS = {
        "cve_ent", "entidad", "severidad_promedio", "siniestros_ocurridos_mdp_promedio",
        "poblacion_2020", "automoviles_registrados", "area_km2",
        "precio_promedio_auto_ml_k_mxn", "precio_gasolina_reg_prom",
        "autos_por_1000_hab", "densidad_poblacional", "cagr_2020_2024_pct",
        "yearly_severidad", "yearly_mdp", "yearly_categoria",
        "indice_severidad", "pct_costo_nacional", "categoria_severidad"
    }
    REQUIRED_SCATTER_KEYS = {"r_pearson", "r2_score", "p_value", "slope", "intercept", "formula"}
    VALID_YEARS = {"2020", "2021", "2022", "2023", "2024"}
    VALID_CATEGORIES = {"Baja", "Media", "Critica", "Crítica"}

    @classmethod
    def load_and_validate(cls, file_path: str = "", allow_synthetic: bool = False) -> Dict[str, Any]:
        target_path = file_path if file_path else resolve_data_path()
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            raise DataIntegrityError(f"Error crítico al leer la fuente canónica data.json: {e}") from e

        return cls.validate_data_dict(data, allow_synthetic=allow_synthetic)

    @classmethod
    def validate_data_dict(cls, data: Dict[str, Any], allow_synthetic: bool = False) -> Dict[str, Any]:
        for main_key in ["metadata", "estados", "scatter_stats"]:
            if main_key not in data:
                raise DataIntegrityError(f"Falta sección obligatoria '{main_key}' en data.json")

        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            raise DataIntegrityError("La sección 'metadata' debe ser un objeto JSON.")
        missing_meta = cls.REQUIRED_METADATA_KEYS - set(metadata.keys())
        if missing_meta:
            raise DataIntegrityError(f"Metadata incompleta. Faltan claves: {missing_meta}")
        if metadata["promedio_nacional_severidad"] is not None and metadata["promedio_nacional_severidad"] <= 0:
            raise DataIntegrityError("El promedio_nacional_severidad debe ser un número positivo.")
        if metadata["total_mdp_nacional_promedio"] is not None and metadata["total_mdp_nacional_promedio"] <= 0:
            raise DataIntegrityError("El total_mdp_nacional_promedio debe ser un número positivo.")

        estados = data["estados"]
        if not isinstance(estados, list) or len(estados) == 0:
            raise DataIntegrityError("La sección 'estados' debe ser una lista no vacía.")
        if not allow_synthetic and len(estados) != 32:
            raise DataIntegrityError(f"Se esperaban 32 entidades federativas, pero se encontraron {len(estados)}.")

        tot_mdp_calc = 0.0
        tot_pct_calc = 0.0
        excluded_mdp_count = 0
        excluded_pct_count = 0
        nat_avg = metadata["promedio_nacional_severidad"]
        missing_observations: List[Dict[str, Any]] = []

        entidades_vistas = set()
        for idx, st in enumerate(estados):
            if not isinstance(st, dict):
                raise DataIntegrityError(f"Estado en posición {idx} no es un objeto válido.")
            ent_name = st.get("entidad")
            if not ent_name or not isinstance(ent_name, str):
                raise DataIntegrityError(f"Estado en posición {idx} no tiene un campo 'entidad' válido.")
            if ent_name in entidades_vistas:
                raise DataIntegrityError(f"Entidad duplicada encontrada: '{ent_name}'.")
            entidades_vistas.add(ent_name)

            missing_state_keys = cls.REQUIRED_STATE_KEYS - set(st.keys())
            if missing_state_keys:
                raise DataIntegrityError(f"Entidad '{ent_name}' no contiene claves requeridas de esquema: {missing_state_keys}")

            for dict_key in ("yearly_severidad", "yearly_mdp", "yearly_categoria"):
                if not isinstance(st[dict_key], dict):
                    raise DataIntegrityError(f"El campo '{dict_key}' en '{ent_name}' debe ser un diccionario.")

            yearly_sev = st["yearly_severidad"]
            yearly_mdp = st["yearly_mdp"]
            yearly_cat = st["yearly_categoria"]

            for yr in sorted(cls.VALID_YEARS):
                sev_v = yearly_sev.get(yr)
                mdp_v = yearly_mdp.get(yr)
                cat_v = yearly_cat.get(yr)

                if sev_v is None:
                    missing_observations.append({"entidad": ent_name, "anio": yr, "metrica": "severidad"})
                elif not isinstance(sev_v, (int, float)) or isinstance(sev_v, bool) or not math.isfinite(sev_v):
                    raise DataIntegrityError(f"Severidad inválida para '{ent_name}' en {yr}: {sev_v}")
                elif float(sev_v) <= 0:
                    missing_observations.append({"entidad": ent_name, "anio": yr, "metrica": "severidad"})

                if mdp_v is None:
                    missing_observations.append({"entidad": ent_name, "anio": yr, "metrica": "costo_mdp"})
                elif not isinstance(mdp_v, (int, float)) or isinstance(mdp_v, bool) or not math.isfinite(mdp_v) or float(mdp_v) < 0:
                    raise DataIntegrityError(f"MDP inválido para '{ent_name}' en {yr}: {mdp_v}")

                if cat_v is None:
                    missing_observations.append({"entidad": ent_name, "anio": yr, "metrica": "categoria"})
                else:
                    if cat_v not in cls.VALID_CATEGORIES:
                        raise DataIntegrityError(f"Categoría anual inválida '{cat_v}' en '{ent_name}' ({yr}).")
                    if sev_v is not None and float(sev_v) > 0:
                        expected_cat = compute_category_from_rule(float(sev_v))
                        norm_cat = "Critica" if cat_v == "Crítica" else cat_v
                        if expected_cat != norm_cat:
                            raise DataIntegrityError(
                                f"Categoría anual '{cat_v}' en '{ent_name}' ({yr}) contradice la regla para severidad {sev_v}: esperado '{expected_cat}'."
                            )

            sev_prom = st.get("severidad_promedio")
            if sev_prom is not None and nat_avg is not None and nat_avg > 0:
                expected_idx = (sev_prom / nat_avg) * 100.0
                actual_idx = st.get("indice_severidad")
                if actual_idx is not None and abs(expected_idx - actual_idx) > 0.5:
                    raise DataIntegrityError(f"Inconsistencia en índice relativo para '{ent_name}': esperado {expected_idx:.2f}, reportado {actual_idx:.2f}")

            cat_prom = st.get("categoria_severidad")
            if cat_prom is not None:
                if cat_prom not in cls.VALID_CATEGORIES:
                    raise DataIntegrityError(f"Categoría inválida '{cat_prom}' en '{ent_name}'.")
                if sev_prom is not None and sev_prom > 0:
                    expected_prom_cat = compute_category_from_rule(float(sev_prom))
                    norm_prom_cat = "Critica" if cat_prom == "Crítica" else cat_prom
                    if expected_prom_cat != norm_prom_cat:
                        raise DataIntegrityError(
                            f"Categoría promedio '{cat_prom}' en '{ent_name}' contradice la regla para severidad {sev_prom}: esperado '{expected_prom_cat}'."
                        )

            if st.get("siniestros_ocurridos_mdp_promedio") is not None:
                tot_mdp_calc += st["siniestros_ocurridos_mdp_promedio"]
            else:
                excluded_mdp_count += 1

            if st.get("pct_costo_nacional") is not None:
                tot_pct_calc += st["pct_costo_nacional"]
            else:
                excluded_pct_count += 1

        if not allow_synthetic:
            if excluded_mdp_count == 0 and abs(tot_mdp_calc - metadata["total_mdp_nacional_promedio"]) > 5.0:
                raise DataIntegrityError(f"Inconsistencia en suma total de MDP: suma de estados ({tot_mdp_calc:.2f}) difiere del total en metadata ({metadata['total_mdp_nacional_promedio']:.2f})")
            if excluded_pct_count == 0 and abs(tot_pct_calc - 100.0) > 0.5:
                raise DataIntegrityError(f"Inconsistencia en suma de porcentajes nacionales: suma {tot_pct_calc:.2f}% != 100%")

        scatter = data["scatter_stats"]
        missing_scatter = cls.REQUIRED_SCATTER_KEYS - set(scatter.keys())
        if missing_scatter:
            raise DataIntegrityError(f"Estadísticas de dispersión incompletas. Faltan: {missing_scatter}")
        if not (-1.0 <= scatter["r_pearson"] <= 1.0):
            raise DataIntegrityError(f"Coeficiente r_pearson ({scatter['r_pearson']}) fuera de [-1, 1].")
        if not (0.0 <= scatter["r2_score"] <= 1.0):
            raise DataIntegrityError(f"Coeficiente r2_score ({scatter['r2_score']}) fuera de [0, 1].")

        data["data_quality"] = {
            "missing": missing_observations,
            "missing_observations": missing_observations,
            "missing_count": len(missing_observations),
            "excluded_mdp_count": excluded_mdp_count,
            "excluded_pct_count": excluded_pct_count
        }
        return data

