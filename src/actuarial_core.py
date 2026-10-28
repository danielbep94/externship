"""
Core Actuarial Module
Implementa:
- Fase 1: Validación rigurosa de esquema, integridad y consistencia de data.json (SSOT).
- Fase 2: Catálogo de entidades (con alias) y catálogo formal de métricas actuariales.
- Fase 3: Gestión de contexto conversacional separando contexto confirmado de interpretaciones pendientes.
- Fase 4: Motor de operaciones dinámicas y reglas metodológicas actuariales (sin hardcoding).
"""

import json
import math
import re
import difflib
import unicodedata
from typing import Dict, List, Any, Optional, Tuple

class DataIntegrityError(Exception):
    """Excepción lanzada cuando data.json viola restricciones de esquema, integridad o consistencia."""
    pass

def normalize_text(text: str) -> str:
    """Normaliza texto removiendo acentos, puntuación excedente y convirtiendo a minúsculas."""
    if text is None:
        return ""
    decomposed = unicodedata.normalize('NFD', str(text))
    without_accents = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return without_accents.lower().strip()


# =====================================================================
# FASE 1: VALIDADOR DE ESQUEMA, INTEGRIDAD Y CONSISTENCIA
# =====================================================================
class ActuarialDataValidator:
    """Valida y carga data.json garantizando integridad referencial y metodológica (SSOT)."""

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
    VALID_CATEGORIES = {"Baja", "Media", "Critica"}

    @classmethod
    def load_and_validate(cls, file_path: str = '/Users/victordaniel/chubb/data.json') -> Dict[str, Any]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            raise DataIntegrityError(f"Error crítico al leer la fuente canónica data.json: {e}") from e

        # 1. Validación de claves principales
        for main_key in ["metadata", "estados", "scatter_stats"]:
            if main_key not in data:
                raise DataIntegrityError(f"Falta sección obligatoria '{main_key}' en data.json")

        # 2. Validación de Metadata
        metadata = data["metadata"]
        missing_meta = cls.REQUIRED_METADATA_KEYS - set(metadata.keys())
        if missing_meta:
            raise DataIntegrityError(f"Metadata incompleta. Faltan claves: {missing_meta}")
        if metadata["promedio_nacional_severidad"] <= 0:
            raise DataIntegrityError("El promedio_nacional_severidad debe ser un número positivo.")
        if metadata["total_mdp_nacional_promedio"] <= 0:
            raise DataIntegrityError("El total_mdp_nacional_promedio debe ser un número positivo.")

        # 3. Validación de Estados (32 entidades)
        estados = data["estados"]
        if len(estados) != 32:
            raise DataIntegrityError(f"Se esperaban 32 entidades federativas, pero se encontraron {len(estados)}.")

        tot_mdp_calc = 0.0
        tot_pct_calc = 0.0
        nat_avg = metadata["promedio_nacional_severidad"]

        entidades_vistas = set()
        for idx, st in enumerate(estados):
            ent_name = st.get("entidad")
            if not ent_name:
                raise DataIntegrityError(f"Estado en posición {idx} no tiene el campo 'entidad'.")
            if ent_name in entidades_vistas:
                raise DataIntegrityError(f"Entidad duplicada encontrada: '{ent_name}'.")
            entidades_vistas.add(ent_name)

            missing_state_keys = cls.REQUIRED_STATE_KEYS - set(st.keys())
            if missing_state_keys:
                raise DataIntegrityError(f"Entidad '{ent_name}' no contiene claves requeridas: {missing_state_keys}")

            # Validar consistencia de años
            yearly_sev = st["yearly_severidad"]
            missing_years = cls.VALID_YEARS - set(yearly_sev.keys())
            if missing_years:
                raise DataIntegrityError(f"Entidad '{ent_name}' carece de datos para los años: {missing_years}")

            # Validar índice de severidad vs promedio nacional:
            expected_idx = (st["severidad_promedio"] / nat_avg) * 100.0
            actual_idx = st["indice_severidad"]
            if abs(expected_idx - actual_idx) > 0.5:
                raise DataIntegrityError(f"Inconsistencia en índice relativo para '{ent_name}': esperado {expected_idx:.2f}, reportado {actual_idx:.2f}")

            # Validar categorías
            if st["categoria_severidad"] not in cls.VALID_CATEGORIES:
                raise DataIntegrityError(f"Categoría inválida '{st['categoria_severidad']}' en '{ent_name}'.")

            tot_mdp_calc += st["siniestros_ocurridos_mdp_promedio"]
            tot_pct_calc += st["pct_costo_nacional"]

        # 4. Consistencia macroestatal agregada
        if abs(tot_mdp_calc - metadata["total_mdp_nacional_promedio"]) > 5.0:
            raise DataIntegrityError(f"Inconsistencia en suma total de MDP: suma de estados ({tot_mdp_calc:.2f}) difiere del total en metadata ({metadata['total_mdp_nacional_promedio']:.2f})")
        if abs(tot_pct_calc - 100.0) > 0.5:
            raise DataIntegrityError(f"Inconsistencia en suma de porcentajes nacionales: suma {tot_pct_calc:.2f}% != 100%")

        # 5. Validación de Scatter Stats
        scatter = data["scatter_stats"]
        missing_scatter = cls.REQUIRED_SCATTER_KEYS - set(scatter.keys())
        if missing_scatter:
            raise DataIntegrityError(f"Estadísticas de dispersión incompletas. Faltan: {missing_scatter}")
        if not (-1.0 <= scatter["r_pearson"] <= 1.0):
            raise DataIntegrityError(f"Coeficiente r_pearson ({scatter['r_pearson']}) fuera de [-1, 1].")
        if not (0.0 <= scatter["r2_score"] <= 1.0):
            raise DataIntegrityError(f"Coeficiente r2_score ({scatter['r2_score']}) fuera de [0, 1].")

        return data


# =====================================================================
# FASE 2: CATÁLOGO DE ENTIDADES (ALIAS) Y CATÁLOGO DE MÉTRICAS
# =====================================================================
class ActuarialCatalog:
    """Catálogo formal de entidades y métricas con resolución difusa."""

    # Catálogo exhaustivo de alias de entidades
    STATE_ALIASES = {
        'cdmx': 'Ciudad de Mexico',
        'df': 'Ciudad de Mexico',
        'distrito federal': 'Ciudad de Mexico',
        'ciudad de mex': 'Ciudad de Mexico',
        'edomex': 'Estado de Mexico',
        'edo mex': 'Estado de Mexico',
        'estado mex': 'Estado de Mexico',
        'estado de mexico': 'Estado de Mexico',
        'nl': 'Nuevo Leon',
        'nvo leon': 'Nuevo Leon',
        'nevo lion': 'Nuevo Leon',
        'nuevo leon': 'Nuevo Leon',
        'regio': 'Nuevo Leon',
        'slp': 'San Luis Potosi',
        'san luis': 'San Luis Potosi',
        'san luis potosi': 'San Luis Potosi',
        'qro': 'Queretaro',
        'queretaro': 'Queretaro',
        'keretaro': 'Queretaro',
        'bc': 'Baja California',
        'baja cal': 'Baja California',
        'baja california norte': 'Baja California',
        'bcs': 'Baja California Sur',
        'baja sur': 'Baja California Sur',
        'chih': 'Chihuahua',
        'coah': 'Coahuila',
        'jal': 'Jalisco',
        'jalisko': 'Jalisco',
        'pue': 'Puebla',
        'tamps': 'Tamaulipas',
        'yuc': 'Yucatan',
        'mich': 'Michoacan',
        'ags': 'Aguascalientes',
        'gto': 'Guanajuato',
        'gro': 'Guerrero',
        'hgo': 'Hidalgo',
        'mor': 'Morelos',
        'nay': 'Nayarit',
        'oax': 'Oaxaca',
        'qroo': 'Quintana Roo',
        'sinaloa': 'Sinaloa',
        'sonora': 'Sonora',
        'tabasco': 'Tabasco',
        'tlaxcala': 'Tlaxcala',
        'zacatecas': 'Zacatecas',
        'camp': 'Campeche',
        'chis': 'Chiapas',
        'dgo': 'Durango'
    }

    # Catálogo formal de métricas actuariales soportadas
    METRIC_CATALOG = {
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

    STOP_WORDS = {"son", "clima", "mas", "los", "las", "del", "con", "que", "para", "por", "cuanto", "cuales", "como", "dame", "ver"}

    def __init__(self, canonical_states: List[str]):
        self.canonical_states = canonical_states
        self.norm_canonical = {normalize_text(s): s for s in canonical_states}

    def resolve_metrics(self, query: str) -> List[str]:
        """Detecta qué métricas actuariales se están solicitando en la consulta."""
        norm_q = normalize_text(query)
        detected = []
        for metric_id, info in self.METRIC_CATALOG.items():
            if any(re.search(rf'\b{re.escape(normalize_text(kw))}\b', norm_q) for kw in info['keywords']):
                detected.append(metric_id)
        if not detected and any(w in norm_q for w in ["cuanto", "diferencia", "compara"]):
            detected.append('severidad')
        return detected

    def extract_states(self, query: str) -> List[str]:
        """Extrae N entidades federativas en orden de aparición sin límite artificial."""
        norm_q = normalize_text(query)
        found_matches: List[Tuple[int, str]] = []

        # 1. Búsqueda por catálogo de Alias con límite de palabra (\b)
        for alias, real_name in self.STATE_ALIASES.items():
            pattern = rf'\b{re.escape(alias)}\b'
            for match in re.finditer(pattern, norm_q):
                found_matches.append((match.start(), real_name))

        # 2. Búsqueda por nombres canónicos
        for norm_name, real_name in self.norm_canonical.items():
            pattern = rf'\b{re.escape(norm_name)}\b'
            for match in re.finditer(pattern, norm_q):
                found_matches.append((match.start(), real_name))

        # 3. Fuzzy matching para palabras no cubiertas exactamente
        if not found_matches:
            words = [w for w in norm_q.split() if w not in self.STOP_WORDS and len(w) >= 4]
            for w in words:
                close = difflib.get_close_matches(w, list(self.norm_canonical.keys()), n=1, cutoff=0.75)
                if close:
                    real = self.norm_canonical[close[0]]
                    idx = norm_q.find(w)
                    found_matches.append((idx, real))

        # Ordenar por posición original en el texto y deduplicar preservando orden
        found_matches.sort(key=lambda x: x[0])
        result = []
        for _, name in found_matches:
            if name not in result:
                result.append(name)

        return result


# =====================================================================
# FASE 3: GESTOR DE CONTEXTO Y MEMORIA CONVERSACIONAL
# =====================================================================
class ConversationMemoryManager:
    """
    Gestiona el ciclo de vida de la conversación.
    Separa de manera explícita:
    - Contexto Confirmado: Estados y periodos explícitamente consultados/resueltos.
    - Interpretación Pendiente: Intentos de desambiguación antes de confirmar la mutación del contexto.
    """
    VALID_YEARS = [2020, 2021, 2022, 2023, 2024]

    def __init__(self):
        # Contexto Confirmado
        self.confirmed_states: List[str] = []
        self.confirmed_year: Optional[int] = None # None = Promedio 2020-2024
        self.confirmed_metric: str = 'severidad'

        # Interpretación Pendiente
        self.pending_interpretation: Optional[Dict[str, Any]] = None

    def parse_year_intent(self, query: str, has_explicit_new_state: bool = False) -> Tuple[Optional[int], Optional[str]]:
        """
        Extrae y valida el año solicitado en la consulta.
        Retorna (año_valido, error_o_advertencia_temporal)
        """
        norm_q = normalize_text(query)
        match = re.search(r'\b(19\d\d|20\d\d)\b', norm_q)
        if not match:
            # Si pide explícitamente "promedio", "historico", "general", "todos"
            if any(w in norm_q for w in ["promedio", "historico", "general", "todos"]):
                return (None, None)
            # Si es una consulta completamente nueva de un estado ("¿Cuál es la severidad de X?"),
            # no arrastra el año temporal anterior a menos que sea una continuación ("y en...", "este ano")
            if has_explicit_new_state and not any(w in norm_q for w in ["y", "mismo", "este", "ese", "continua"]):
                return (None, None)
            return (self.confirmed_year, None)

        year = int(match.group(1))
        if year not in self.VALID_YEARS:
            return (None, f"⚠️ El año {year} se encuentra fuera del rango de observación del estudio (2020 a 2024).")

        return (year, None)

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
        
        # Si la consulta busca rankings generales ("cuales", "top", "ranking", "mayor"), no debe heredar estado previo
        if words.intersection({"cuales", "ranking", "rankings", "top", "lista", "general"}):
            return []

        # Si usa anáfora estricta con palabras completas ("este", "su", "en", "ambos", "estos", "y")
        if words.intersection({"este", "su", "sus", "en", "ambos", "estos", "y", "mismo", "misma"}):
            return self.confirmed_states

        return []


# =====================================================================
# FASE 4: MOTOR DE OPERACIONES Y REGLAS METODOLÓGICAS (ZERO HARDCODED)
# =====================================================================
class ActuarialOperationsEngine:
    """
    Motor de operaciones actuariales que calcula en tiempo de ejecución todas
    las cifras, ratios, rankings y agregaciones directamente desde data.json.
    Garantiza CERO cifras hardcodeadas.
    """

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.metadata = data["metadata"]
        self.estados_list = data["estados"]
        self.estados_dict = {s["entidad"]: s for s in self.estados_list}
        self.scatter_stats = data["scatter_stats"]

        self.national_avg_severity = float(self.metadata["promedio_nacional_severidad"])
        self.total_national_mdp = float(self.metadata["total_mdp_nacional_promedio"])

    def compute_severity_rankings(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Calcula el Top N dinámico de estados con mayor severidad promedio."""
        sorted_by_sev = sorted(self.estados_list, key=lambda x: x["severidad_promedio"], reverse=True)
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
            sev = float(st["yearly_severidad"][yr_str])
            mdp = float(st["yearly_mdp"][yr_str])
            cat = st["yearly_categoria"][yr_str]
            # Cálculo de promedio nacional del año correspondiente:
            nat_yr_avg = sum(s["yearly_severidad"][yr_str] for s in self.estados_list) / len(self.estados_list)
            idx_rel = (sev / nat_yr_avg) * 100.0
            label_period = f"Año {target_year}"
            nat_avg = nat_yr_avg
        else:
            sev = float(st["severidad_promedio"])
            mdp = float(st["siniestros_ocurridos_mdp_promedio"])
            cat = st["categoria_severidad"]
            idx_rel = float(st["indice_severidad"])
            label_period = "Promedio 2020–2024"
            nat_avg = self.national_avg_severity

        return {
            "entidad": state_name,
            "periodo": label_period,
            "target_year": target_year,
            "severidad": sev,
            "costo_mdp": mdp,
            "categoria": cat,
            "indice_severidad": idx_rel,
            "promedio_nacional": nat_avg,
            "cagr_acumulado": float(st["cagr_2020_2024_pct"]),
            "automoviles_registrados": int(st["automoviles_registrados"]),
            "precio_auto_k_mxn": float(st["precio_promedio_auto_ml_k_mxn"])
        }

    def compute_three_key_findings(self) -> Dict[str, Any]:
        """Calcula dinámicamente los 3 hallazgos clave del reporte."""
        # 1. Pareto Top 5 dinámico
        sorted_by_mdp = sorted(self.estados_list, key=lambda x: x["siniestros_ocurridos_mdp_promedio"], reverse=True)
        top5 = sorted_by_mdp[:5]
        top5_mdp_sum = sum(s["siniestros_ocurridos_mdp_promedio"] for s in top5)
        pareto_pct = (top5_mdp_sum / self.total_national_mdp) * 100.0

        # 2. Ratio Max / Min dinámico
        sorted_by_sev = sorted(self.estados_list, key=lambda x: x["severidad_promedio"], reverse=True)
        max_st = sorted_by_sev[0]
        min_st = sorted_by_sev[-1]
        ratio_max_min = max_st["severidad_promedio"] / min_st["severidad_promedio"]

        # Crecimiento líder dinámico
        sorted_by_cagr = sorted(self.estados_list, key=lambda x: x["cagr_2020_2024_pct"], reverse=True)
        leader_growth = sorted_by_cagr[0]
        cagr_annual = (math.pow(1 + leader_growth["cagr_2020_2024_pct"] / 100.0, 1/4) - 1) * 100.0

        # 3. Regresión dinámica
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
        metrics.sort(key=lambda x: x["severidad"], reverse=True)

        highest = metrics[0]
        lowest = metrics[-1]
        abs_diff = highest["severidad"] - lowest["severidad"]
        pct_diff = (abs_diff / lowest["severidad"]) * 100.0 if lowest["severidad"] > 0 else 0.0

        # Regla metodológica: Comparar severidad vs volumen MDP
        sorted_by_mdp = sorted(metrics, key=lambda x: x["costo_mdp"], reverse=True)

        return {
            "estados_metricas": metrics,
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

        # Promedio nacional de crecimiento
        nat_2020 = sum(s["yearly_severidad"]["2020"] for s in self.estados_list) / len(self.estados_list)
        nat_2024 = sum(s["yearly_severidad"]["2024"] for s in self.estados_list) / len(self.estados_list)
        nat_cagr_total = ((nat_2024 - nat_2020) / nat_2020) * 100.0
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
