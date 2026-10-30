"""
Core Actuarial Module
Implementa:
- Fase 1: Validación de esquema, separación de error de esquema vs observación faltante, y verificación de reglas de categoría.
- Fase 2: Catálogo unificado de entidades (con detección de duplicados y spans sin traslape) y métricas desde config/actuarial_rules.json.
- Fase 3: Gestión de contexto conversacional separando contexto confirmado de interpretaciones pendientes y resolución estricta de año.
- Fase 4: Motor de operaciones dinámicas, formateador determinista ROUND_HALF_UP y Resumen Ejecutivo (single/multistate).
"""

import json
import math
import os
import re
import difflib
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Optional, Tuple

class DataIntegrityError(Exception):
    """Excepción lanzada cuando data.json viola restricciones estructurales de esquema o reglas de integridad."""
    pass

DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "actuarial_rules.json"
)

def load_actuarial_rules(rules_path: str = DEFAULT_RULES_PATH) -> Dict[str, Any]:
    """Carga la configuración compartida entre Python y JavaScript."""
    if os.path.exists(rules_path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    raise FileNotFoundError(f"No se encontró el archivo de reglas actuariales en {rules_path}")

def normalize_text(text: str) -> str:
    """
    Normaliza texto de forma idéntica a JavaScript:
    NFD -> eliminar marcas diacríticas -> minúsculas -> sustituir puntuación por espacio -> colapsar espacios -> trim.
    """
    if text is None:
        return ""
    decomposed = unicodedata.normalize('NFD', str(text))
    without_accents = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    lowered = without_accents.lower()
    no_punct = re.sub(r'[^\w\s]', ' ', lowered)
    collapsed = re.sub(r'\s+', ' ', no_punct).strip()
    return collapsed

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
    if val is None or not isinstance(val, (int, float)) or not math.isfinite(val):
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
        int_part_Groups = []
        while len(int_part) > 3:
            int_part_Groups.append(int_part[-3:])
            int_part = int_part[:-3]
        int_part_Groups.append(int_part)
        int_part = ",".join(reversed(int_part_Groups))

    return f"{sign}{int_part}.{frac_part}" if decimals > 0 else f"{sign}{int_part}"

def compute_category_from_rule(sev_val: Optional[float], critica_min: float = 11000.0, media_min: float = 7500.0) -> Optional[str]:
    """Evalúa la regla documentada de categoría sobre el valor sin redondear."""
    if sev_val is None or not isinstance(sev_val, (int, float)) or not math.isfinite(sev_val) or sev_val <= 0:
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


# =====================================================================
# FASE 1: VALIDADOR DE ESQUEMA, INTEGRIDAD Y CONSISTENCIA
# =====================================================================
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
    def load_and_validate(cls, file_path: str = '/Users/victordaniel/chubb/data.json', allow_synthetic: bool = False) -> Dict[str, Any]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            raise DataIntegrityError(f"Error crítico al leer la fuente canónica data.json: {e}") from e

        return cls.validate_data_dict(data, allow_synthetic=allow_synthetic)

    @classmethod
    def validate_data_dict(cls, data: Dict[str, Any], allow_synthetic: bool = False) -> Dict[str, Any]:
        # 1. Validación de claves principales
        for main_key in ["metadata", "estados", "scatter_stats"]:
            if main_key not in data:
                raise DataIntegrityError(f"Falta sección obligatoria '{main_key}' en data.json")

        # 2. Validación de Metadata
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

        # 3. Validación de Estados
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

            # Validar índice de severidad y categoría del periodo cuando severidad_promedio está presente
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

        # 4. Consistencia macroestatal agregada (cuando no es sintético y no hubo exclusiones)
        if not allow_synthetic:
            if excluded_mdp_count == 0 and abs(tot_mdp_calc - metadata["total_mdp_nacional_promedio"]) > 5.0:
                raise DataIntegrityError(f"Inconsistencia en suma total de MDP: suma de estados ({tot_mdp_calc:.2f}) difiere del total en metadata ({metadata['total_mdp_nacional_promedio']:.2f})")
            if excluded_pct_count == 0 and abs(tot_pct_calc - 100.0) > 0.5:
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

        data["data_quality"] = {
            "missing": missing_observations,
            "missing_observations": missing_observations,
            "missing_count": len(missing_observations),
            "excluded_mdp_count": excluded_mdp_count,
            "excluded_pct_count": excluded_pct_count
        }
        return data


# =====================================================================
# FASE 2: CATÁLOGO DE ENTIDADES (ALIAS) Y CATÁLOGO DE MÉTRICAS
# =====================================================================
class ActuarialCatalog:
    """Catálogo formal de entidades y métricas sincronizado con config/actuarial_rules.json."""

    rules = load_actuarial_rules()
    STATE_ALIASES: Dict[str, str] = rules["state_aliases"]

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

    STOP_WORDS = {
        "son", "sin", "ver", "clima", "mas", "los", "las", "del", "con", "que",
        "para", "por", "cuanto", "cuales", "como", "dame", "presumen", "ejecutivo",
        "ejecutiva", "nacional", "reporte", "informe", "resumen", "sintesis"
    }

    def __init__(self, canonical_states: List[str]):
        self.canonical_states = canonical_states
        self.canonical_set = set(canonical_states)
        self.norm_canonical = {normalize_text(s): s for s in canonical_states}

    def resolve_metrics(self, query: str) -> List[str]:
        """Detecta qué métricas actuariales se están solicitando en la consulta."""
        norm_q = normalize_text(query)
        detected = []
        for metric_id, info in self.METRIC_CATALOG.items():
            if any(re.search(rf'\b{re.escape(normalize_text(kw))}\b', norm_q) for kw in info['keywords']):
                detected.append(metric_id)
        if not detected and any(re.search(rf'\b{w}\b', norm_q) for w in ["cuanto", "diferencia", "compara", "comparar", "resumen", "sintesis"]):
            detected.append('severidad')
        return detected

    @staticmethod
    def _normalize_with_offsets(query: str) -> Tuple[str, List[int]]:
        """Normaliza texto devolviendo (norm_q, orig_indices) para recuperar menciones originales."""
        if not query:
            return ("", [])
        raw_chars: List[Tuple[str, int]] = []
        for idx, ch in enumerate(str(query)):
            decomp = unicodedata.normalize('NFD', ch)
            base = ''.join(c for c in decomp if unicodedata.category(c) != 'Mn').lower()
            for bc in base:
                if re.match(r'\w', bc):
                    raw_chars.append((bc, idx))
                else:
                    raw_chars.append((' ', idx))

        norm_chars: List[str] = []
        orig_indices: List[int] = []
        prev_space = True
        for bc, idx in raw_chars:
            if bc == ' ':
                if not prev_space:
                    norm_chars.append(' ')
                    orig_indices.append(idx)
                    prev_space = True
            else:
                norm_chars.append(bc)
                orig_indices.append(idx)
                prev_space = False

        if norm_chars and norm_chars[-1] == ' ':
            norm_chars.pop()
            orig_indices.pop()

        return ("".join(norm_chars), orig_indices)

    def extract_states_detailed(self, query: str) -> Dict[str, Any]:
        """
        Extrae menciones de entidades federativas con límite de palabra (\b),
        elimina traslapes de spans (prefiriendo la coincidencia más larga, ej. 'Baja California Sur' sobre 'Baja California'),
        y separa estados únicos de menciones repetidas mediante alias.
        """
        norm_q, orig_indices = self._normalize_with_offsets(query)
        candidate_spans: List[Tuple[int, int, str, str]] = [] # (start, end, canonical_name, raw_matched)

        def _get_surface(s_idx: int, e_idx: int) -> str:
            if not orig_indices or s_idx >= len(orig_indices) or e_idx <= 0:
                return norm_q[s_idx:e_idx]
            orig_start = orig_indices[s_idx]
            orig_end = orig_indices[e_idx - 1]
            return str(query)[orig_start:orig_end + 1]

        # Unificar patrones de alias y canónicos (filtrados a los canonical_states activos)
        lookup_map: Dict[str, str] = {}
        for alias, real_name in self.STATE_ALIASES.items():
            if real_name in self.canonical_set:
                lookup_map[normalize_text(alias)] = real_name
        for norm_name, real_name in self.norm_canonical.items():
            lookup_map[norm_name] = real_name

        for pat_str, real_name in lookup_map.items():
            if not pat_str:
                continue
            pattern = rf'\b{re.escape(pat_str)}\b'
            for m in re.finditer(pattern, norm_q):
                candidate_spans.append((m.start(), m.end(), real_name, _get_surface(m.start(), m.end())))

        # Resolver traslapes de intervalos: ordenar por longitud descendente y luego por inicio ascendente
        candidate_spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
        accepted_spans: List[Tuple[int, int, str, str]] = []
        for start, end, real_name, raw_tok in candidate_spans:
            overlaps = any(not (end <= a_start or start >= a_end) for a_start, a_end, _, _ in accepted_spans)
            if not overlaps:
                accepted_spans.append((start, end, real_name, raw_tok))

        # Si no hubo coincidencias exactas por palabra completa, intentar fuzzy matching palabra por palabra
        if not accepted_spans:
            for m in re.finditer(r'\b\w+\b', norm_q):
                w = m.group(0)
                if w not in self.STOP_WORDS and len(w) >= 4:
                    close = difflib.get_close_matches(w, list(self.norm_canonical.keys()), n=1, cutoff=0.78)
                    if close:
                        real = self.norm_canonical[close[0]]
                        accepted_spans.append((m.start(), m.end(), real, _get_surface(m.start(), m.end())))

        # Ordenar por orden de aparición en la consulta
        accepted_spans.sort(key=lambda x: x[0])

        unique_states: List[str] = []
        states_raw: List[str] = []
        duplicate_mentions: List[str] = []
        mentions_by_state: Dict[str, List[str]] = {}

        for _, _, real_name, raw_tok in accepted_spans:
            states_raw.append(raw_tok)
            mentions_by_state.setdefault(real_name, []).append(raw_tok)
            if real_name not in unique_states:
                unique_states.append(real_name)

        for real_name, raw_list in mentions_by_state.items():
            if len(raw_list) > 1:
                duplicate_mentions.extend(raw_list)

        return {
            "states": unique_states,
            "states_raw": states_raw,
            "duplicate_mentions": duplicate_mentions,
            "mentions_by_state": mentions_by_state
        }

    def extract_states(self, query: str) -> List[str]:
        """Extrae N entidades federativas únicas en orden de primera aparición."""
        return self.extract_states_detailed(query)["states"]


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
    DEFAULT_YEAR = 2024

    def __init__(self):
        self.confirmed_states: List[str] = []
        self.confirmed_year: Optional[int] = None
        self.confirmed_metric: str = 'severidad'
        self.pending_interpretation: Optional[Dict[str, Any]] = None

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
        # Deduplicar preservando orden
        unique_years: List[int] = []
        for y in years_found:
            if y not in unique_years:
                unique_years.append(y)

        # Verificar años fuera de rango primero
        out_of_range = [y for y in unique_years if y not in self.VALID_YEARS]
        if out_of_range:
            bad_y = out_of_range[0]
            return {
                "status": "temporal_out_of_range",
                "target_year": None,
                "year_source": None,
                "error_message": f"⚠️ El año {bad_y} está fuera del periodo disponible (2020–2024). Indica un año dentro de ese rango."
            }

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

        # Sin año explícito en la consulta:
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
        
        # Si la consulta busca rankings generales ("cuales", "top", "ranking", "mayor"), no debe heredar estado previo
        if words.intersection({"cuales", "ranking", "rankings", "top", "lista", "general", "nacional"}):
            return []

        # Si usa anáfora estricta con palabras completas ("este", "su", "en", "ambos", "estos", "y")
        if words.intersection({"este", "su", "sus", "en", "ambos", "estos", "y", "mismo", "misma", "tambien"}):
            return self.confirmed_states

        return []


# =====================================================================
# FASE 4: MOTOR DE OPERACIONES Y REGLAS METODOLÓGICAS (ZERO HARDCODED)
# =====================================================================
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
        return val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and float(val) > 0.0

    @staticmethod
    def is_valid_mdp(val: Any) -> bool:
        """MDP válido en el año consultado: número finito y >= 0."""
        return val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and float(val) >= 0.0

    def compute_national_reference_for_year(self, year_str: str) -> Tuple[Optional[float], int]:
        """
        Calcula la referencia nacional para un año como la media simple de las entidades con severidad válida.
        Retorna (media_ref, n_entidades_con_dato).
        """
        valid_vals = [
            float(s["yearly_severidad"].get(year_str))
            for s in self.estados_list
            if self.is_valid_severity(s.get("yearly_severidad", {}).get(year_str))
        ]
        n = len(valid_vals)
        if n == 0:
            return (None, 0)
        return (sum(valid_vals) / n, n)

    def compute_competition_ranks_for_year(self, year_str: str) -> Dict[str, Any]:
        """
        Calcula rankings nacionales de competencia ('1, 1, 3') comparando valores redondeados al centavo (2 decimales).
        El denominador refleja las entidades con dato válido para cada métrica y año.
        """
        sev_entries: List[Tuple[str, Decimal]] = []
        mdp_entries: List[Tuple[str, Decimal]] = []

        for s in self.estados_list:
            ent = s["entidad"]
            sv = s.get("yearly_severidad", {}).get(year_str)
            if self.is_valid_severity(sv):
                sev_entries.append((ent, round_half_up_decimal(float(sv), 2)))

            mv = s.get("yearly_mdp", {}).get(year_str)
            if self.is_valid_mdp(mv):
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
        media_ref_2020, n_ref_2020 = self.compute_national_reference_for_year("2020")
        nat_ranks = self.compute_competition_ranks_for_year(yr_str)

        rows: List[Dict[str, Any]] = []
        for name in state_names:
            st = self.estados_dict[name]
            raw_sev_Y = st.get("yearly_severidad", {}).get(yr_str)
            raw_mdp_Y = st.get("yearly_mdp", {}).get(yr_str)
            raw_cat_Y = st.get("yearly_categoria", {}).get(yr_str)

            sev_Y = float(raw_sev_Y) if self.is_valid_severity(raw_sev_Y) else None
            mdp_Y = float(raw_mdp_Y) if self.is_valid_mdp(raw_mdp_Y) else None

            # Categoría estrictamente de yearly_categoria[yr_str] y solo si la severidad del año es válida
            if sev_Y is not None and raw_cat_Y in {"Baja", "Media", "Critica", "Crítica"}:
                cat_Y = display_category_label(raw_cat_Y)
            else:
                cat_Y = None

            # Índice relativo del año
            if sev_Y is not None and media_ref_Y is not None and media_ref_Y > 0:
                indice_Y = (sev_Y / media_ref_Y) * 100.0
            else:
                indice_Y = None

            # Base 2020 y variaciones
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

        # Alcance de selección (solo si len(state_names) >= 2)
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
