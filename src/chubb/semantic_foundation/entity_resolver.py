"""
Semantic Foundation — Entity Resolver.
Governs state entity extraction, alias resolution, non-overlapping span disambiguation,
and duplicate mention tracking across the 32 Mexican federal entities.
"""

import difflib
import re
import unicodedata
from typing import Dict, List, Any, Tuple
from chubb.semantic_foundation.temporal_registry import load_actuarial_rules, normalize_text


class EntityResolver:
    """Resolves entity mentions and aliases into canonical Mexican federal states."""

    _rules = load_actuarial_rules()
    STATE_ALIASES: Dict[str, str] = _rules["state_aliases"]

    STOP_WORDS = {
        "son", "sin", "ver", "clima", "mas", "los", "las", "del", "con", "que",
        "para", "por", "cuanto", "cuales", "cual", "como", "dame", "presumen", "ejecutivo",
        "ejecutiva", "nacional", "reporte", "informe", "resumen", "sintesis",
        "severidad", "severidades", "crecimiento", "crecimoento", "crecimento", "acumulado",
        "indice", "relativo", "promedio", "estado", "estados", "entidad", "entidades",
        "mayor", "menor", "ranking", "rankings", "costo", "costos", "total", "totales",
        "siniestro", "siniestros", "vehiculo", "vehiculos", "autos", "riesgo", "categoria",
        "comparar", "compara", "comparativa", "frecuencia", "exposicion", "correlacion",
        "variables", "tendencia", "evolucion", "historico", "anual", "periodo", "millones",
        "paa", "recomendacion", "recomendaciones", "recomienda", "recomiendas", "recomendar",
        "recomednar", "recomedaciones", "preventiva", "preventivas", "preventivo", "prevencion",
        "oportunidad", "oportunidades", "oputinidades", "oportunidaes", "acciones", "accion",
        "identificar", "identifica", "estrategia", "estrategias", "mitigar", "mitigacion",
        "sugerencia", "sugerencias", "medidas"
    }

    def __init__(self, canonical_states: List[str]):
        self.canonical_states = canonical_states
        self.canonical_set = set(canonical_states)
        self.norm_canonical = {normalize_text(s): s for s in canonical_states}

    @staticmethod
    def _normalize_with_offsets(query: str) -> Tuple[str, List[int]]:
        """Normaliza texto devolviendo (norm_q, orig_indices) para recuperar menciones originales."""
        if not query:
            return ("", [])
        raw_chars: List[Tuple[str, int]] = []
        for idx, ch in enumerate(str(query)):
            if ch == "²":
                raw_chars.append(('2', idx))
                continue
            if ch == "³":
                raw_chars.append(('3', idx))
                continue
            decomp = unicodedata.normalize('NFD', ch)
            base = ''.join(c for c in decomp if unicodedata.category(c) != 'Mn').lower()
            for bc in base:
                if re.match(r'[a-z0-9_]', bc):
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
        Extrae menciones de entidades federativas con límite de palabra (\\b),
        elimina traslapes de spans (prefiriendo la coincidencia más larga, ej. 'Baja California Sur' sobre 'Baja California'),
        y separa estados únicos de menciones repetidas mediante alias.
        """
        norm_q, orig_indices = self._normalize_with_offsets(query)
        candidate_spans: List[Tuple[int, int, str, str]] = []

        def _get_surface(s_idx: int, e_idx: int) -> str:
            if not orig_indices or s_idx >= len(orig_indices) or e_idx <= 0:
                return norm_q[s_idx:e_idx]
            orig_start = orig_indices[s_idx]
            orig_end = orig_indices[e_idx - 1]
            return str(query)[orig_start:orig_end + 1]

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

        candidate_spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
        accepted_spans: List[Tuple[int, int, str, str]] = []
        for start, end, real_name, raw_tok in candidate_spans:
            overlaps = any(not (end <= a_start or start >= a_end) for a_start, a_end, _, _ in accepted_spans)
            if not overlaps:
                accepted_spans.append((start, end, real_name, raw_tok))

        if not accepted_spans:
            for m in re.finditer(r'\b\w+\b', norm_q):
                w = m.group(0)
                if w not in self.STOP_WORDS and len(w) >= 4 and not w.isdigit():
                    close = difflib.get_close_matches(w, list(self.norm_canonical.keys()), n=1, cutoff=0.75)
                    if close:
                        real = self.norm_canonical[close[0]]
                        accepted_spans.append((m.start(), m.end(), real, _get_surface(m.start(), m.end())))

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

