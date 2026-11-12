/**
 * Motor Actuarial Compartido (Browser + Node.js)
 * Garantiza paridad matemática, de alias, enrutamiento, manejo de faltantes y redondeo ROUND_HALF_UP
 * con src/actuarial_core.py y src/llm_grounding.py.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ActuarialEngine = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const ACTUARIAL_RULES = {
    version: '1.0.0',
    valid_years: [2020, 2021, 2022, 2023, 2024],
    default_year: 2024,
    base_year: 2020,
    national_reference: {
      method: 'simple_mean_entities_with_data',
      label: 'Media de severidad de las entidades con dato'
    },
    category_thresholds: {
      critica_min: 11000.0,
      media_min: 7500.0
    },
    triggers: {
      strong_summary: [
        'resumen',
        'resumenes',
        'resumir',
        'resume',
        'sintesis',
        'sintetiza',
        'sintetizar',
        'panorama'
      ],
      weak_summary: ['reporte', 'informe', 'explicacion', 'diagnostico'],
      creation_verbs: [
        'crea',
        'crear',
        'genera',
        'generar',
        'haz',
        'hacer',
        'prepara',
        'preparar',
        'elabora',
        'elaborar',
        'dame',
        'dar'
      ],
      continuation_markers: ['tambien', 'mismo ano', 'ese ano'],
      comparison: [
        'compara',
        'comparar',
        'comparativa',
        'comparacion',
        'vs',
        'versus',
        'diferencia',
        'difieren',
        'contra'
      ],
      unsupported_kpis: {
        ventas_y_primas: [
          'ventas', 'venta', 'prima emitida', 'primas emitidas', 'prima devengada',
          'primas devengadas', 'prima suscrita', 'primas suscritas', 'prima cobrada',
          'primas cobradas', 'primas', 'prima', 'facturacion', 'ingresos comerciales',
          'ingresos por prima', 'colocacion', 'meta comercial', 'comisiones',
          'cuota de mercado', 'market share'
        ],
        rentabilidad_y_finanzas: [
          'rentabilidad', 'utilidad', 'utilidades', 'ganancia', 'ganancias', 'margen',
          'roe', 'roi', 'roa', 'ebitda', 'loss ratio', 'combined ratio',
          'indice combinado', 'siniestralidad sobre prima', 'resultado tecnico',
          'reserva matematica', 'reservas ibnr', 'ibnr', 'solvencia'
        ],
        microdatos_poliza_y_exposicion: [
          'polizas vigentes', 'polizas activas', 'polizas emitidas', 'polizas vendidas',
          'numero de polizas', 'cantidad de polizas', 'total de polizas', 'asegurados directos',
          'vehiculos asegurados', 'autos asegurados', 'parque asegurado',
          'frecuencia observada', 'siniestros observados', 'deducible', 'coaseguro', 'suma asegurada'
        ]
      },
      unsupported_granularity: {
        sub_state: [
          'municipio', 'municipios', 'alcaldia', 'alcaldias', 'codigo postal', 'colonia',
          'monterrey', 'guadalajara', 'zapopan', 'cancun', 'tijuana', 'mexicali', 'merida',
          'acapulco', 'toluca', 'ecatepec', 'naucalpan', 'san pedro garza', 'apodaca',
          'tlalnepantla', 'nezahualcoyotl', 'hermosillo', 'culiacan', 'mazatlan', 'saltillo',
          'torreon', 'reynosa', 'los cabos', 'puerto vallarta', 'ciudad juarez'
        ],
        sub_annual: [
          'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
          'septiembre', 'octubre', 'noviembre', 'diciembre', 'mensual', 'mensuales',
          'trimestre', 'trimestral', 'trimestrales', 'bimestre', 'bimestral', 'semestre',
          'semestral', 'semanal', 'diario', 'q1', 'q2', 'q3', 'q4', '1t', '2t', '3t', '4t'
        ]
      }
    },
    state_aliases: {
      'cdmx': 'Ciudad de Mexico',
      'df': 'Ciudad de Mexico',
      'distrito federal': 'Ciudad de Mexico',
      'ciudad de mex': 'Ciudad de Mexico',
      'ciudad de mexico': 'Ciudad de Mexico',
      'edomex': 'Estado de Mexico',
      'edo mex': 'Estado de Mexico',
      'estado mex': 'Estado de Mexico',
      'estado de mex': 'Estado de Mexico',
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
      'chichuaca': 'Chihuahua',
      'chihuaha': 'Chihuahua',
      'chihuhua': 'Chihuahua',
      'chiuaua': 'Chihuahua',
      'coah': 'Coahuila',
      'coahulia': 'Coahuila',
      'jal': 'Jalisco',
      'jalisko': 'Jalisco',
      'pue': 'Puebla',
      'tamps': 'Tamaulipas',
      'tamaulpas': 'Tamaulipas',
      'yuc': 'Yucatan',
      'mich': 'Michoacan',
      'michocan': 'Michoacan',
      'ags': 'Aguascalientes',
      'aguascalentes': 'Aguascalientes',
      'gto': 'Guanajuato',
      'guanajato': 'Guanajuato',
      'gro': 'Guerrero',
      'hgo': 'Hidalgo',
      'mor': 'Morelos',
      'nay': 'Nayarit',
      'oax': 'Oaxaca',
      'qroo': 'Quintana Roo',
      'quintanaroo': 'Quintana Roo',
      'sinaloa': 'Sinaloa',
      'sonora': 'Sonora',
      'tabasco': 'Tabasco',
      'tlaxcala': 'Tlaxcala',
      'tlaxacala': 'Tlaxcala',
      'veracrus': 'Veracruz',
      'zacatecas': 'Zacatecas',
      'camp': 'Campeche',
      'chis': 'Chiapas',
      'dgo': 'Durango'
    }
  };

  function normalizeText(text) {
    if (text === null || text === undefined) return '';
    return String(text)
      .replace(/²/g, '2')
      .replace(/³/g, '3')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^\w\s]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function normalizeWithOffsets(query) {
    if (!query) return { normQ: '', origIndices: [] };
    const str = String(query);
    const rawChars = [];
    for (let idx = 0; idx < str.length; idx++) {
      const ch = str[idx];
      if (ch === '²') {
        rawChars.push({ bc: '2', idx });
        continue;
      }
      if (ch === '³') {
        rawChars.push({ bc: '3', idx });
        continue;
      }
      const base = ch.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
      for (let j = 0; j < base.length; j++) {
        const bc = base[j];
        if (/\w/.test(bc)) {
          rawChars.push({ bc, idx });
        } else {
          rawChars.push({ bc: ' ', idx });
        }
      }
    }

    const normChars = [];
    const origIndices = [];
    let prevSpace = true;
    for (const item of rawChars) {
      if (item.bc === ' ') {
        if (!prevSpace) {
          normChars.push(' ');
          origIndices.push(item.idx);
          prevSpace = true;
        }
      } else {
        normChars.push(item.bc);
        origIndices.push(item.idx);
        prevSpace = false;
      }
    }

    if (normChars.length > 0 && normChars[normChars.length - 1] === ' ') {
      normChars.pop();
      origIndices.pop();
    }

    return { normQ: normChars.join(''), origIndices };
  }

  function expandShortestDecimalParts(absNumberStr) {
    if (/[eE]/.test(absNumberStr)) {
      const parts = absNumberStr.split(/[eE]/);
      const mantissa = parts[0];
      const exp = parseInt(parts[1], 10);
      const mParts = mantissa.split('.');
      const mInt = mParts[0];
      const mFrac = mParts[1] || '';
      const digits = mInt + mFrac;
      const decPos = mInt.length + exp;
      if (decPos <= 0) {
        return { intPart: '0', fracPart: '0'.repeat(-decPos) + digits };
      } else if (decPos >= digits.length) {
        return { intPart: digits + '0'.repeat(decPos - digits.length), fracPart: '' };
      } else {
        return { intPart: digits.slice(0, decPos), fracPart: digits.slice(decPos) };
      }
    }
    const splitParts = absNumberStr.split('.');
    return { intPart: splitParts[0], fracPart: splitParts[1] || '' };
  }

  /**
   * Redondea usando la representación decimal más corta del float con ROUND_HALF_UP (mitad lejos de cero).
   * Retorna un objeto { isNeg, scaledBig, decimals, floatVal }
   */
  function roundHalfUpScaled(val, decimals = 2) {
    const num = Number(val);
    let s = String(num);
    let isNeg = false;
    if (s.startsWith('-')) {
      isNeg = true;
      s = s.slice(1);
    }
    const { intPart, fracPart } = expandShortestDecimalParts(s);
    const paddedFrac = fracPart.padEnd(decimals + 1, '0');
    const keptFrac = decimals > 0 ? paddedFrac.slice(0, decimals) : '';
    const rawDigits = (intPart + keptFrac).replace(/^0+/, '') || '0';
    let scaledBig = BigInt(rawDigits);
    const nextDigit = paddedFrac.charCodeAt(decimals) - 48;
    if (nextDigit >= 5) {
      scaledBig += 1n;
    }
    if (scaledBig === 0n) {
      isNeg = false;
    }
    const signMult = isNeg ? -1 : 1;
    const floatVal = signMult * (Number(scaledBig) / Math.pow(10, decimals));
    return { isNeg, scaledBig: isNeg ? -scaledBig : scaledBig, absScaledBig: scaledBig, decimals, floatVal };
  }

  function formatNumber(val, decimals = 2, thousandsSep = true) {
    if (val === null || val === undefined || typeof val !== 'number' || !Number.isFinite(val)) {
      return 'sin dato';
    }
    const { isNeg, absScaledBig } = roundHalfUpScaled(val, decimals);
    const rawStr = absScaledBig.toString().padStart(decimals + 1, '0');
    let intPart = decimals > 0 ? rawStr.slice(0, rawStr.length - decimals) : rawStr;
    const fracPart = decimals > 0 ? rawStr.slice(rawStr.length - decimals) : '';
    intPart = intPart.replace(/^0+(?=\d)/, '');

    if (thousandsSep) {
      const groups = [];
      let rem = intPart;
      while (rem.length > 3) {
        groups.push(rem.slice(rem.length - 3));
        rem = rem.slice(0, rem.length - 3);
      }
      groups.push(rem);
      intPart = groups.reverse().join(',');
    }

    const signStr = isNeg ? '-' : '';
    return decimals > 0 ? `${signStr}${intPart}.${fracPart}` : `${signStr}${intPart}`;
  }

  function computeCategoryFromRule(sevVal, criticaMin = 11000.0, mediaMin = 7500.0) {
    if (sevVal === null || sevVal === undefined || typeof sevVal !== 'number' || !Number.isFinite(sevVal) || sevVal <= 0) {
      return null;
    }
    if (sevVal >= criticaMin) return 'Critica';
    if (sevVal >= mediaMin) return 'Media';
    return 'Baja';
  }

  function displayCategoryLabel(cat) {
    if (!cat || cat === 'sin dato') return 'sin dato';
    if (cat === 'Critica' || cat === 'Crítica') return 'Crítica';
    return cat;
  }

  function isValidSeverity(val) {
    return val !== null && val !== undefined && typeof val === 'number' && Number.isFinite(val) && val > 0.0;
  }

  function isValidMdp(val) {
    return val !== null && val !== undefined && typeof val === 'number' && Number.isFinite(val) && val >= 0.0;
  }

  function escapeRegExp(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function extractStatesDetailed(query, canonicalStates = null) {
    const { normQ, origIndices } = normalizeWithOffsets(query);
    const canonicalList = canonicalStates || Array.from(new Set(Object.values(ACTUARIAL_RULES.state_aliases)));
    const canonicalSet = new Set(canonicalList);
    const normCanonical = {};
    for (const st of canonicalList) {
      normCanonical[normalizeText(st)] = st;
    }

    function getSurface(sIdx, eIdx) {
      if (!origIndices.length || sIdx >= origIndices.length || eIdx <= 0) {
        return normQ.slice(sIdx, eIdx);
      }
      const origStart = origIndices[sIdx];
      const origEnd = origIndices[eIdx - 1];
      return String(query).slice(origStart, origEnd + 1);
    }

    const lookupMap = {};
    for (const [alias, realName] of Object.entries(ACTUARIAL_RULES.state_aliases)) {
      if (canonicalSet.has(realName)) {
        lookupMap[normalizeText(alias)] = realName;
      }
    }
    for (const [normName, realName] of Object.entries(normCanonical)) {
      lookupMap[normName] = realName;
    }

    const candidateSpans = [];
    for (const [patStr, realName] of Object.entries(lookupMap)) {
      if (!patStr) continue;
      const regex = new RegExp(`\\b${escapeRegExp(patStr)}\\b`, 'g');
      let m;
      while ((m = regex.exec(normQ)) !== null) {
        const start = m.index;
        const end = start + m[0].length;
        candidateSpans.push({
          start,
          end,
          realName,
          rawTok: getSurface(start, end)
        });
      }
    }

    candidateSpans.sort((a, b) => {
      const lenDiff = (b.end - b.start) - (a.end - a.start);
      if (lenDiff !== 0) return lenDiff;
      return a.start - b.start;
    });

    const acceptedSpans = [];
    for (const cand of candidateSpans) {
      const overlaps = acceptedSpans.some(acc => !(cand.end <= acc.start || cand.start >= acc.end));
      if (!overlaps) {
        acceptedSpans.push(cand);
      }
    }

    // Si no hubo coincidencias exactas por palabra completa, intentar fuzzy matching palabra por palabra (paridad con Python)
    if (acceptedSpans.length === 0) {
      const STOP_WORDS = new Set([
        'son', 'sin', 'ver', 'clima', 'mas', 'los', 'las', 'del', 'con', 'que',
        'para', 'por', 'cuanto', 'cuales', 'cual', 'como', 'dame', 'presumen', 'ejecutivo',
        'ejecutiva', 'nacional', 'reporte', 'informe', 'resumen', 'sintesis',
        'severidad', 'severidades', 'crecimiento', 'crecimoento', 'crecimento', 'acumulado',
        'indice', 'relativo', 'promedio', 'estado', 'estados', 'entidad', 'entidades',
        'mayor', 'menor', 'ranking', 'rankings', 'costo', 'costos', 'total', 'totales',
        'siniestro', 'siniestros', 'vehiculo', 'vehiculos', 'autos', 'riesgo', 'categoria',
        'comparar', 'compara', 'comparativa', 'frecuencia', 'exposicion', 'correlacion',
        'variables', 'tendencia', 'evolucion', 'historico', 'anual', 'periodo', 'millones',
        'paa', 'recomendacion', 'recomendaciones', 'recomienda', 'recomiendas', 'recomendar',
        'recomednar', 'recomedaciones', 'preventiva', 'preventivas', 'preventivo', 'prevencion',
        'oportunidad', 'oportunidades', 'oputinidades', 'oportunidaes', 'acciones', 'accion',
        'identificar', 'identifica', 'estrategia', 'estrategias', 'mitigar', 'mitigacion',
        'sugerencia', 'sugerencias', 'medidas'
      ]);

      function levenshteinSim(a, b) {
        if (a === b) return 1.0;
        if (!a.length || !b.length) return 0.0;
        const m = [];
        for (let i = 0; i <= b.length; i++) m[i] = [i];
        for (let j = 0; j <= a.length; j++) m[0][j] = j;
        for (let i = 1; i <= b.length; i++) {
          for (let j = 1; j <= a.length; j++) {
            m[i][j] = b[i - 1] === a[j - 1]
              ? m[i - 1][j - 1]
              : Math.min(m[i - 1][j - 1] + 1, m[i][j - 1] + 1, m[i - 1][j] + 1);
          }
        }
        return 1.0 - m[b.length][a.length] / Math.max(a.length, b.length);
      }

      const wordRe = /\b\w+\b/g;
      let wm;
      while ((wm = wordRe.exec(normQ)) !== null) {
        const w = wm[0];
        if (!STOP_WORDS.has(w) && w.length >= 4 && !/^\d+$/.test(w)) {
          let bestNorm = null;
          let bestScore = 0.0;
          for (const normCand of Object.keys(normCanonical)) {
            const sc = levenshteinSim(w, normCand);
            if (sc > bestScore) {
              bestScore = sc;
              bestNorm = normCand;
            }
          }
          if (bestNorm && bestScore >= 0.75) {
            const start = wm.index;
            const end = start + w.length;
            acceptedSpans.push({
              start,
              end,
              realName: normCanonical[bestNorm],
              rawTok: getSurface(start, end)
            });
          }
        }
      }
    }

    acceptedSpans.sort((a, b) => a.start - b.start);

    const uniqueStates = [];
    const statesRaw = [];
    const duplicateMentions = [];
    const mentionsByState = {};

    for (const sp of acceptedSpans) {
      statesRaw.push(sp.rawTok);
      if (!mentionsByState[sp.realName]) {
        mentionsByState[sp.realName] = [];
      }
      mentionsByState[sp.realName].push(sp.rawTok);
      if (!uniqueStates.includes(sp.realName)) {
        uniqueStates.push(sp.realName);
      }
    }

    for (const rawList of Object.values(mentionsByState)) {
      if (rawList.length > 1) {
        duplicateMentions.push(...rawList);
      }
    }

    return {
      states: uniqueStates,
      states_raw: statesRaw,
      duplicate_mentions: duplicateMentions,
      mentions_by_state: mentionsByState
    };
  }

  class MemoryManager {
    constructor() {
      this.confirmed_states = [];
      this.confirmed_year = null;
      this.confirmed_metric = 'severidad';
    }

    static isContinuationQuery(query) {
      const normQ = normalizeText(query);
      if (normQ.startsWith('y ')) return true;
      for (const marker of ACTUARIAL_RULES.triggers.continuation_markers) {
        const re = new RegExp(`\\b${escapeRegExp(marker)}\\b`);
        if (re.test(normQ)) return true;
      }
      return false;
    }

    resolveYearForSummary(query) {
      const normQ = normalizeText(query);
      const yearMatches = normQ.match(/\b(19\d\d|20\d\d)\b/g) || [];
      const uniqueYears = [];
      for (const yStr of yearMatches) {
        const y = parseInt(yStr, 10);
        if (!uniqueYears.includes(y)) uniqueYears.push(y);
      }

      const outOfRange = uniqueYears.filter(y => !ACTUARIAL_RULES.valid_years.includes(y));
      if (outOfRange.length > 0) {
        const badY = outOfRange[0];
        return {
          status: 'temporal_out_of_range',
          target_year: null,
          year_source: null,
          error_message: `⚠️ El año ${badY} está fuera del periodo disponible (2020–2024). Indica un año dentro de ese rango.`
        };
      }

      if (uniqueYears.length > 1) {
        return {
          status: 'clarification_year',
          target_year: null,
          year_source: null,
          error_message: `⚠️ Indica un solo año para el resumen (2020–2024). Detecté múltiples años: ${uniqueYears.join(', ')}.`
        };
      }

      if (uniqueYears.length === 1) {
        return {
          status: 'ok',
          target_year: uniqueYears[0],
          year_source: 'explicit',
          error_message: null
        };
      }

      if (MemoryManager.isContinuationQuery(query) && ACTUARIAL_RULES.valid_years.includes(this.confirmed_year)) {
        return {
          status: 'ok',
          target_year: this.confirmed_year,
          year_source: 'memory',
          error_message: null
        };
      }

      return {
        status: 'ok',
        target_year: ACTUARIAL_RULES.default_year,
        year_source: 'default',
        error_message: null
      };
    }

    getEffectiveStates(extractedStates, query) {
      if (extractedStates && extractedStates.length > 0) return extractedStates;
      const normQ = normalizeText(query);
      const words = new Set(normQ.match(/\b\w+\b/g) || []);
      for (const w of ['cuales', 'ranking', 'rankings', 'top', 'lista', 'general', 'nacional']) {
        if (words.has(w)) return [];
      }
      for (const w of ['este', 'su', 'sus', 'en', 'ambos', 'estos', 'y', 'mismo', 'misma', 'tambien']) {
        if (words.has(w)) return this.confirmed_states;
      }
      return [];
    }

    updateConfirmedContext(states, year, metric = null) {
      if (states && states.length > 0) this.confirmed_states = states;
      if (year !== null && year !== undefined) this.confirmed_year = year;
      if (metric) this.confirmed_metric = metric;
    }
  }

  function isSummaryFamily(normQ, hasEntities) {
    const words = new Set(normQ.match(/\b\w+\b/g) || []);
    if (!hasEntities && (words.has('hallazgo') || words.has('hallazgos') || words.has('conclusiones'))) {
      return true;
    }
    const hasStrong = ACTUARIAL_RULES.triggers.strong_summary.some(w => words.has(w));
    const hasWeak =
      ACTUARIAL_RULES.triggers.weak_summary.some(w => words.has(w)) &&
      ACTUARIAL_RULES.triggers.creation_verbs.some(w => words.has(w));
    return hasStrong || hasWeak;
  }

  function isComparisonFamily(normQ) {
    const words = new Set(normQ.match(/\b\w+\b/g) || []);
    if (ACTUARIAL_RULES.triggers.comparison.some(w => words.has(w))) return true;
    if (/\bfrente a\b|\bdiferencia entre\b|\bcuanto difieren\b/.test(normQ)) return true;
    return false;
  }

  function isRecommendationsFamily(normQ) {
    if (/\b(recomend\w*|recomed\w*|sugerenc\w*|sugier\w*|preventiv\w*|prevenci\w*|prevensi\w*|oportunidad\w*|oputinidad\w*|mitig\w*|estrategi\w*)\b/.test(normQ)) {
      return true;
    }
    const phrases = [
      'accion preventiva', 'acciones preventivas', 'medida preventiva', 'medidas preventivas',
      'plan de accion', 'planes de accion', 'areas de oportunidad', 'area de oportunidad',
      'identificar oportunidad', 'identificar oportunidades', 'identifica oportunidades',
      'como reducir', 'como controlar', 'como bajar', 'que acciones', 'que medidas'
    ];
    return phrases.some(p => normQ.includes(p));
  }

  function isBusinessRulesOrGlossary(normQ) {
    const phrases = [
      'glosario', 'definicion', 'que es mdp', 'volumen de costo total mdp',
      'explicar volumen de costo', 'explicar mdp', 'significa mdp', 'que significa',
      'que es la severidad', 'que es severidad', 'que es la frecuencia', 'que es frecuencia',
      'que es el indice', 'que es indice', 'que es el costo total', 'que es costo total',
      'que es r2', 'que es r cuadrada', 'que es cagr',
      'como se calcula', 'como calculan', 'como se obtiene', 'como se clasifica',
      'como se define', 'cual es la formula', 'cual es la regla', 'regla de negocio',
      'reglas de negocio', 'business rule', 'business rules', 'umbrales de', 'umbral de'
    ];
    if (phrases.some(p => normQ.includes(p))) return true;
    const words = new Set(normQ.match(/\b\w+\b/g) || []);
    const hasStrongSummary = ACTUARIAL_RULES.triggers.strong_summary.some(w => words.has(w));
    if (!hasStrongSummary && (words.has('glosario') || words.has('reglas') || words.has('umbrales'))) {
      return true;
    }
    if (words.has('formula') || words.has('formulas')) return true;
    return false;
  }

  function parseQueryIR(userQuery, canonicalStates = null, memory = null) {
    const mem = memory || new MemoryManager();
    const normQ = normalizeText(userQuery);
    const words = new Set(normQ.match(/\b\w+\b/g) || []);

    for (const w of ['clima', 'temperatura', 'lluvia', 'tiempo manana', 'futbol', 'politica', 'receta']) {
      if (new RegExp(`\\b${escapeRegExp(w)}\\b`).test(normQ)) {
        return {
          intent: 'out_of_domain',
          states: [],
          states_raw: [],
          duplicate_mentions: [],
          target_year: null,
          year_source: null,
          metrics: [],
          national_reference: { method: 'simple_mean_entities_with_data' },
          ranking_scope: [],
          interpretation_notes: [],
          insufficient_entities: false,
          query_text: userQuery
        };
      }
    }

    const det = extractStatesDetailed(userQuery, canonicalStates);
    const extractedStates = det.states;
    const statesRaw = det.states_raw;
    const duplicateMentions = det.duplicate_mentions;
    const mentionsByState = det.mentions_by_state;

    // Prioridad 1.5: KPIs inexistentes (ventas, primas, rentabilidad, pólizas vigentes)
    const foundKpis = [];
    for (const [catName, terms] of Object.entries(ACTUARIAL_RULES.triggers.unsupported_kpis)) {
      const sortedTerms = [...terms].sort((a, b) => b.length - a.length);
      for (const term of sortedTerms) {
        if (new RegExp(`\\b${escapeRegExp(term)}\\b`).test(normQ)) {
          foundKpis.push({ term, category: catName });
        }
      }
    }
    if (foundKpis.length > 0) {
      const yrM = normQ.match(/\b(202[0-4])\b/g) || [];
      const yrVal = yrM.length === 1 ? parseInt(yrM[0], 10) : null;
      return {
        intent: 'insufficient_data_kpi',
        missing_kpis: foundKpis.map(k => k.term),
        kpi_categories: Array.from(new Set(foundKpis.map(k => k.category))),
        states: extractedStates,
        states_raw: statesRaw,
        duplicate_mentions: duplicateMentions,
        target_year: yrVal,
        year_source: yrVal !== null ? 'explicit' : null,
        metrics: [],
        national_reference: { method: 'simple_mean_entities_with_data' },
        ranking_scope: [],
        interpretation_notes: [],
        insufficient_entities: false,
        query_text: userQuery
      };
    }

    // Prioridad 1.6: Granularidad sub-estatal o sub-anual no soportada
    const foundGran = [];
    for (const [gType, terms] of Object.entries(ACTUARIAL_RULES.triggers.unsupported_granularity)) {
      const sortedTerms = [...terms].sort((a, b) => b.length - a.length);
      for (const term of sortedTerms) {
        if (new RegExp(`\\b${escapeRegExp(term)}\\b`).test(normQ)) {
          foundGran.push({ term, granularity_type: gType });
        }
      }
    }
    if (foundGran.length > 0) {
      const yrM = normQ.match(/\b(202[0-4])\b/g) || [];
      const yrVal = yrM.length === 1 ? parseInt(yrM[0], 10) : null;
      return {
        intent: 'unsupported_granularity',
        unsupported_terms: foundGran.map(g => g.term),
        granularity_types: Array.from(new Set(foundGran.map(g => g.granularity_type))),
        states: extractedStates,
        states_raw: statesRaw,
        duplicate_mentions: duplicateMentions,
        target_year: yrVal,
        year_source: yrVal !== null ? 'explicit' : null,
        metrics: [],
        national_reference: { method: 'simple_mean_entities_with_data' },
        ranking_scope: [],
        interpretation_notes: [],
        insufficient_entities: false,
        query_text: userQuery
      };
    }

    const effectiveStates = mem.getEffectiveStates(extractedStates, userQuery);
    const isRecommendations = isRecommendationsFamily(normQ);
    const isSummary = isSummaryFamily(normQ, effectiveStates.length > 0);
    const isComparison = isComparisonFamily(normQ);

    if (isRecommendations) {
      let recStates = [...effectiveStates];
      const hasNationalWord = ['nacional', 'general', 'pais', 'todos', 'todas', 'reporte', 'tablero'].some(w => words.has(w));
      if (recStates.length === 0 && !hasNationalWord && mem.confirmed_states && mem.confirmed_states.length > 0) {
        recStates = [...mem.confirmed_states];
      }

      const yrRes = mem.resolveYearForSummary(userQuery);
      if (yrRes.status === 'temporal_out_of_range' || yrRes.status === 'clarification_year') {
        return {
          intent: yrRes.status,
          error_message: yrRes.error_message,
          states: yrRes.status === 'clarification_year' ? recStates : [],
          states_raw: statesRaw,
          duplicate_mentions: duplicateMentions,
          target_year: null,
          year_source: null,
          metrics: [],
          national_reference: { method: 'simple_mean_entities_with_data' },
          ranking_scope: [],
          interpretation_notes: [],
          insufficient_entities: false,
          query_text: userQuery
        };
      }

      let targetYear = yrRes.target_year;
      let yearSource = yrRes.year_source;
      const sameConfirmedStates =
        recStates.length > 0 &&
        mem.confirmed_states &&
        recStates.length === mem.confirmed_states.length &&
        recStates.every((s, idx) => s === mem.confirmed_states[idx]);
      if (yearSource === 'default' && sameConfirmedStates && ACTUARIAL_RULES.valid_years.includes(mem.confirmed_year)) {
        targetYear = mem.confirmed_year;
        yearSource = 'memory';
      }

      const notesRec = [];
      if (yearSource === 'default') {
        notesRec.push('No indicaste año; uso 2024, último año disponible.');
      }
      for (const [stCanon, rawList] of Object.entries(mentionsByState)) {
        if (rawList.length > 1) {
          notesRec.push(`${rawList.join(' y ')} corresponden a la misma entidad (${stCanon}).`);
        }
      }

      return {
        intent: 'recommendations_actions',
        states: recStates,
        states_raw: statesRaw,
        duplicate_mentions: duplicateMentions,
        target_year: targetYear,
        year_source: yearSource,
        metrics: ['severidad', 'costo_mdp', 'indice_relativo', 'categoria', 'variacion_2020', 'ranking'],
        national_reference: { method: 'simple_mean_entities_with_data' },
        ranking_scope: recStates.length >= 2 ? ['national', 'selection'] : recStates.length === 1 ? ['national'] : [],
        interpretation_notes: notesRec,
        insufficient_entities: false,
        query_text: userQuery
      };
    }

    if (isSummary && effectiveStates.length >= 1) {
      const yrRes = mem.resolveYearForSummary(userQuery);
      if (yrRes.status === 'temporal_out_of_range' || yrRes.status === 'clarification_year') {
        return {
          intent: yrRes.status,
          error_message: yrRes.error_message,
          states: yrRes.status === 'clarification_year' ? effectiveStates : [],
          states_raw: statesRaw,
          duplicate_mentions: duplicateMentions,
          target_year: null,
          year_source: null,
          metrics: [],
          national_reference: { method: 'simple_mean_entities_with_data' },
          ranking_scope: [],
          interpretation_notes: [],
          insufficient_entities: false,
          query_text: userQuery
        };
      }

      const targetYear = yrRes.target_year;
      const yearSource = yrRes.year_source;
      const intent = effectiveStates.length >= 2 ? 'executive_multistate_summary' : 'executive_single_state_summary';
      const rankingScope = effectiveStates.length >= 2 ? ['national', 'selection'] : ['national'];
      const notes = [];

      if (yearSource === 'default') {
        notes.push('No indicaste año; uso 2024, último año disponible.');
      }
      if (words.has('nacional')) {
        notes.push(
          `Interpreté la consulta como resumen de ${effectiveStates.join(', ')} comparado con la media de las entidades con dato.`
        );
      }
      for (const [stCanon, rawList] of Object.entries(mentionsByState)) {
        if (rawList.length > 1) {
          notes.push(`${rawList.join(' y ')} corresponden a la misma entidad (${stCanon}).`);
        }
      }

      return {
        intent,
        states: effectiveStates,
        states_raw: statesRaw,
        duplicate_mentions: duplicateMentions,
        target_year: targetYear,
        year_source: yearSource,
        metrics: ['severidad', 'costo_mdp', 'indice_relativo', 'categoria', 'variacion_2020', 'ranking'],
        national_reference: { method: 'simple_mean_entities_with_data' },
        ranking_scope: rankingScope,
        interpretation_notes: notes,
        insufficient_entities: false,
        query_text: userQuery
      };
    }

    const yearMatches = normQ.match(/\b(19\d\d|20\d\d)\b/g) || [];
    const uniqueYears = [];
    for (const yStr of yearMatches) {
      const y = parseInt(yStr, 10);
      if (!uniqueYears.includes(y)) uniqueYears.push(y);
    }

    const isPeriodRange =
      (words.has('promedio') || words.has('periodo') || words.has('historico') || words.has('cagr') || words.has('crecimiento') || words.has('tendencia')) &&
      uniqueYears.length === 2 &&
      uniqueYears[0] === 2020 &&
      uniqueYears[1] === 2024;

    if (!isPeriodRange) {
      const outOfRange = uniqueYears.filter(y => !ACTUARIAL_RULES.valid_years.includes(y));
      if (outOfRange.length > 0) {
        return {
          intent: 'temporal_out_of_range',
          error_message: `⚠️ El año ${outOfRange[0]} se encuentra fuera del rango de observación del estudio (2020 a 2024).`,
          states: [],
          states_raw: statesRaw,
          duplicate_mentions: duplicateMentions,
          target_year: null,
          year_source: null,
          metrics: [],
          national_reference: { method: 'simple_mean_entities_with_data' },
          ranking_scope: [],
          interpretation_notes: [],
          insufficient_entities: false,
          query_text: userQuery
        };
      }
      if (uniqueYears.length > 1) {
        return {
          intent: 'clarification_year',
          error_message: '⚠️ Indica un solo año para el resumen o consulta (2020–2024).',
          states: effectiveStates,
          states_raw: statesRaw,
          duplicate_mentions: duplicateMentions,
          target_year: null,
          year_source: null,
          metrics: [],
          national_reference: { method: 'simple_mean_entities_with_data' },
          ranking_scope: [],
          interpretation_notes: [],
          insufficient_entities: false,
          query_text: userQuery
        };
      }
    }

    let intent = 'single_state';
    if (isSummary && effectiveStates.length === 0) {
      intent = 'three_findings';
    } else if (isBusinessRulesOrGlossary(normQ)) {
      intent = 'glossary_units';
    } else if (isComparison || effectiveStates.length >= 2) {
      intent = 'multi_state_comparison';
    } else if (effectiveStates.length === 1) {
      intent = 'single_state';
    }

    let insufficientEntities = false;
    const notesGeneral = [];
    if (intent === 'multi_state_comparison' && effectiveStates.length === 1 && duplicateMentions.length >= 2) {
      insufficientEntities = true;
      notesGeneral.push(
        `Ambas menciones (${duplicateMentions.join(' y ')}) corresponden a ${effectiveStates[0]}; indica otra entidad para comparar.`
      );
    }

    const targetYear = !isPeriodRange && uniqueYears.length === 1 ? uniqueYears[0] : null;
    return {
      intent,
      states: effectiveStates,
      states_raw: statesRaw,
      duplicate_mentions: duplicateMentions,
      target_year: targetYear,
      year_source: targetYear !== null ? 'explicit' : null,
      metrics: ['severidad'],
      national_reference: { method: 'simple_mean_entities_with_data' },
      ranking_scope: effectiveStates.length >= 2 ? ['national', 'selection'] : effectiveStates.length === 1 ? ['national'] : [],
      interpretation_notes: notesGeneral,
      insufficient_entities: insufficientEntities,
      query_text: userQuery
    };
  }

  function computeNationalReferenceForYear(data, yearStr) {
    const validVals = [];
    for (const s of data.estados) {
      const sv = s.yearly_severidad ? s.yearly_severidad[yearStr] : null;
      if (isValidSeverity(sv)) {
        validVals.push(Number(sv));
      }
    }
    const n = validVals.length;
    if (n === 0) return { mediaRef: null, n: 0 };
    const sum = validVals.reduce((acc, v) => acc + v, 0);
    return { mediaRef: sum / n, n };
  }

  function computeCompetitionRanksForYear(data, yearStr) {
    const sevEntries = [];
    const mdpEntries = [];

    for (const s of data.estados) {
      const ent = s.entidad;
      const sv = s.yearly_severidad ? s.yearly_severidad[yearStr] : null;
      if (isValidSeverity(sv)) {
        sevEntries.push({ ent, qVal: roundHalfUpScaled(Number(sv), 2).scaledBig });
      }
      const mv = s.yearly_mdp ? s.yearly_mdp[yearStr] : null;
      if (isValidMdp(mv)) {
        mdpEntries.push({ ent, qVal: roundHalfUpScaled(Number(mv), 2).scaledBig });
      }
    }

    const sevRanks = {};
    const nSev = sevEntries.length;
    for (const item of sevEntries) {
      const higher = sevEntries.filter(other => other.qVal > item.qVal).length;
      sevRanks[item.ent] = [higher + 1, nSev];
    }

    const mdpRanks = {};
    const nMdp = mdpEntries.length;
    for (const item of mdpEntries) {
      const higher = mdpEntries.filter(other => other.qVal > item.qVal).length;
      mdpRanks[item.ent] = [higher + 1, nMdp];
    }

    return {
      severidad: sevRanks,
      n_severidad: nSev,
      costo_mdp: mdpRanks,
      n_costo_mdp: nMdp
    };
  }

  function computeExecutiveSummary(data, stateNames, targetYear) {
    const yrStr = String(targetYear);
    const { mediaRef: mediaRefY, n: nRefY } = computeNationalReferenceForYear(data, yrStr);
    const { mediaRef: mediaRef2020 } = computeNationalReferenceForYear(data, '2020');
    const natRanks = computeCompetitionRanksForYear(data, yrStr);

    const estadosDict = {};
    for (const s of data.estados) {
      estadosDict[s.entidad] = s;
    }

    const rows = [];
    for (const name of stateNames) {
      const st = estadosDict[name];
      const rawSevY = st.yearly_severidad ? st.yearly_severidad[yrStr] : null;
      const rawMdpY = st.yearly_mdp ? st.yearly_mdp[yrStr] : null;
      const rawCatY = st.yearly_categoria ? st.yearly_categoria[yrStr] : null;

      const sevY = isValidSeverity(rawSevY) ? Number(rawSevY) : null;
      const mdpY = isValidMdp(rawMdpY) ? Number(rawMdpY) : null;

      const validCats = new Set(['Baja', 'Media', 'Critica', 'Crítica']);
      const catY = sevY !== null && validCats.has(rawCatY) ? displayCategoryLabel(rawCatY) : null;

      const indiceY = sevY !== null && mediaRefY !== null && mediaRefY > 0 ? (sevY / mediaRefY) * 100.0 : null;

      const rawSev2020 = st.yearly_severidad ? st.yearly_severidad['2020'] : null;
      const sev2020 = isValidSeverity(rawSev2020) ? Number(rawSev2020) : null;

      const rawMdp2020 = st.yearly_mdp ? st.yearly_mdp['2020'] : null;
      const mdp2020 = isValidMdp(rawMdp2020) && Number(rawMdp2020) > 0.0 ? Number(rawMdp2020) : null;

      const varSevPct =
        sevY !== null && sev2020 !== null ? (Number(targetYear) === 2020 ? 0.0 : (sevY / sev2020 - 1.0) * 100.0) : null;
      const varMdpPct =
        mdpY !== null && mdp2020 !== null ? (Number(targetYear) === 2020 ? 0.0 : (mdpY / mdp2020 - 1.0) * 100.0) : null;

      const indice2020 =
        sev2020 !== null && mediaRef2020 !== null && mediaRef2020 > 0 ? (sev2020 / mediaRef2020) * 100.0 : null;
      const deltaIndicePts =
        indiceY !== null && indice2020 !== null ? (Number(targetYear) === 2020 ? 0.0 : indiceY - indice2020) : null;

      const rkSev = natRanks.severidad[name] || null;
      const rkMdp = natRanks.costo_mdp[name] || null;

      const varSevSign = varSevPct !== null && roundHalfUpScaled(varSevPct, 1).scaledBig > 0n ? '+' : '';
      const varMdpSign = varMdpPct !== null && roundHalfUpScaled(varMdpPct, 1).scaledBig > 0n ? '+' : '';
      const deltaIdxSign = deltaIndicePts !== null && roundHalfUpScaled(deltaIndicePts, 1).scaledBig > 0n ? '+' : '';

      rows.push({
        entidad: name,
        severidad: sevY,
        severidad_fmt: sevY !== null ? formatNumber(sevY, 2) : 'sin dato',
        indice: indiceY,
        indice_fmt: indiceY !== null ? formatNumber(indiceY, 1) : 'no calculable',
        indice_2020: indice2020,
        indice_2020_fmt: indice2020 !== null ? formatNumber(indice2020, 1) : 'no calculable',
        categoria: catY !== null ? catY : 'sin dato',
        costo_mdp: mdpY,
        costo_mdp_fmt: mdpY !== null ? formatNumber(mdpY, 2) : 'sin dato',
        rank_nacional_severidad: rkSev ? rkSev[0] : null,
        n_nacional_severidad: rkSev ? rkSev[1] : natRanks.n_severidad,
        rank_nacional_mdp: rkMdp ? rkMdp[0] : null,
        n_nacional_mdp: rkMdp ? rkMdp[1] : natRanks.n_costo_mdp,
        var_severidad_pct: varSevPct,
        var_severidad_fmt: varSevPct !== null ? `${varSevSign}${formatNumber(varSevPct, 1)} %` : 'no calculable',
        var_mdp_pct: varMdpPct,
        var_mdp_fmt: varMdpPct !== null ? `${varMdpSign}${formatNumber(varMdpPct, 1)} %` : 'no calculable',
        delta_indice_pts: deltaIndicePts,
        delta_indice_fmt: deltaIndicePts !== null ? `${deltaIdxSign}${formatNumber(deltaIndicePts, 1)} pts` : 'no calculable',
        automoviles_registrados: st.automoviles_registrados,
        poblacion_2020: st.poblacion_2020
      });
    }

    let selectionSummary = null;
    if (stateNames.length >= 2) {
      const validSevRows = rows.filter(r => r.severidad !== null);
      const validMdpRows = rows.filter(r => r.costo_mdp !== null);

      validSevRows.sort((a, b) => {
        const bBig = roundHalfUpScaled(b.severidad, 2).scaledBig;
        const aBig = roundHalfUpScaled(a.severidad, 2).scaledBig;
        return bBig > aBig ? 1 : bBig < aBig ? -1 : 0;
      });
      validMdpRows.sort((a, b) => {
        const bBig = roundHalfUpScaled(b.costo_mdp, 2).scaledBig;
        const aBig = roundHalfUpScaled(a.costo_mdp, 2).scaledBig;
        return bBig > aBig ? 1 : bBig < aBig ? -1 : 0;
      });

      const liderSev = validSevRows.length > 0 ? validSevRows[0].entidad : null;
      const menorSev = validSevRows.length >= 2 ? validSevRows[validSevRows.length - 1].entidad : null;
      const brechaSevAbs =
        validSevRows.length >= 2 ? validSevRows[0].severidad - validSevRows[validSevRows.length - 1].severidad : null;
      const brechaSevPct =
        brechaSevAbs !== null && validSevRows[validSevRows.length - 1].severidad > 0
          ? (brechaSevAbs / validSevRows[validSevRows.length - 1].severidad) * 100.0
          : null;

      const liderMdp = validMdpRows.length > 0 ? validMdpRows[0].entidad : null;
      const menorMdp = validMdpRows.length >= 2 ? validMdpRows[validMdpRows.length - 1].entidad : null;
      const brechaMdpAbs =
        validMdpRows.length >= 2 ? validMdpRows[0].costo_mdp - validMdpRows[validMdpRows.length - 1].costo_mdp : null;

      selectionSummary = {
        orden_severidad: validSevRows.map(r => r.entidad),
        orden_mdp: validMdpRows.map(r => r.entidad),
        lider_severidad: liderSev,
        menor_severidad: menorSev,
        brecha_severidad_abs: brechaSevAbs,
        brecha_severidad_abs_fmt: brechaSevAbs !== null ? formatNumber(brechaSevAbs, 2) : 'no calculable',
        brecha_severidad_pct: brechaSevPct,
        brecha_severidad_pct_fmt: brechaSevPct !== null ? formatNumber(brechaSevPct, 1) : 'no calculable',
        lider_mdp: liderMdp,
        menor_mdp: menorMdp,
        brecha_mdp_abs: brechaMdpAbs,
        brecha_mdp_abs_fmt: brechaMdpAbs !== null ? formatNumber(brechaMdpAbs, 2) : 'no calculable',
        lideres_difieren: Boolean(liderSev && liderMdp && liderSev !== liderMdp)
      };
    }

    const allSevMissing = rows.every(r => r.severidad === null);
    const allMdpMissing = rows.every(r => r.costo_mdp === null);

    return {
      target_year: Number(targetYear),
      national_reference: {
        method: 'simple_mean_entities_with_data',
        label: 'Media de severidad de las entidades con dato',
        value: mediaRefY,
        value_fmt: mediaRefY !== null ? formatNumber(mediaRefY, 2) : 'no calculable',
        n: nRefY
      },
      rows,
      selection_summary: selectionSummary,
      all_severidad_missing: allSevMissing,
      all_mdp_missing: allMdpMissing
    };
  }

  function buildHumanNarrativeHtml(summary) {
    const yr = summary.target_year;
    const rows = summary.rows;
    const ref = summary.national_reference;
    const sel = summary.selection_summary;

    if (summary.all_severidad_missing) return '';

    if (rows.length === 1) {
      const r = rows[0];
      if (r.severidad === null) return '';
      let diffClause = '';
      if (r.indice !== null) {
        const diffVs100 = r.indice - 100.0;
        const pctStr = formatNumber(Math.abs(diffVs100), 1);
        const dirStr = diffVs100 >= 0 ? 'por encima' : 'por debajo';
        diffClause = `, situándose un <strong>${pctStr} % ${dirStr}</strong> de la media de las entidades con dato (<strong>$${ref.value_fmt} MXN</strong>, n = ${ref.n})`;
      }
      let mdpClause = '';
      if (r.costo_mdp !== null) {
        const rkM = r.rank_nacional_mdp !== null ? ` (<strong>${r.rank_nacional_mdp}.º lugar de ${r.n_nacional_mdp}</strong>)` : '';
        mdpClause = ` En cuanto al volumen financiero total, acumuló <strong>$${r.costo_mdp_fmt} MDP</strong>${rkM}.`;
      }
      let evolClause = '';
      if (r.var_severidad_pct !== null && r.delta_indice_pts !== null) {
        if (Number(yr) === 2020) {
          evolClause = ` Al tratarse del año base <strong>2020</strong>, la variación acumulada desde el inicio de la serie es de <strong>0.0 %</strong> (<strong>0.0 pts</strong> en índice).`;
        } else {
          evolClause = ` En perspectiva histórica frente a 2020, tanto su severidad unitaria como su costo total presentaron una variación de <strong>${r.var_severidad_fmt}</strong>, mientras que su índice relativo cambió en <strong>${r.delta_indice_fmt}</strong> (pasando de <strong>${r.indice_2020_fmt}</strong> a <strong>${r.indice_fmt} pts</strong>).`;
        }
      }
      const rkS = r.rank_nacional_severidad !== null ? ` (<strong>${r.rank_nacional_severidad}.º lugar nacional de ${r.n_nacional_severidad}</strong>)` : '';
      return `<strong>Interpretación ejecutiva:</strong> Durante <strong>${yr}</strong>, <strong>${r.entidad}</strong> registró un costo medio por siniestro (severidad) de <strong>$${r.severidad_fmt} MXN</strong>${rkS}, clasificándose en nivel de riesgo <strong>${r.categoria}</strong> con un índice relativo de <strong>${r.indice_fmt} pts</strong>${diffClause}.${mdpClause}${evolClause}`;
    }

    const validSev = rows.filter(r => r.severidad !== null);
    if (!validSev.length) return '';
    const parts = rows
      .filter(r => r.severidad !== null)
      .map(
        r =>
          `<strong>${r.entidad}</strong> registró <strong>$${r.severidad_fmt} MXN</strong> (<strong>${r.rank_nacional_severidad}.º de ${r.n_nacional_severidad}</strong>, índice <strong>${r.indice_fmt} pts</strong>, categoría <strong>${r.categoria}</strong>)`
      );
    let gapClause = '';
    if (sel && sel.brecha_severidad_abs !== null && sel.lider_severidad !== sel.menor_severidad) {
      gapClause = ` Esto representa una brecha de <strong>$${sel.brecha_severidad_abs_fmt} MXN</strong> (<strong>+${sel.brecha_severidad_pct_fmt} %</strong> sobre ${sel.menor_severidad}) a favor de <strong>${sel.lider_severidad}</strong>.`;
    }
    let mdpContrast = '';
    if (sel && sel.lideres_difieren) {
      mdpContrast = ` No obstante, al evaluar el monto agregado en millones de pesos, el liderazgo se invierte hacia <strong>${sel.lider_mdp}</strong> (con una diferencia de <strong>$${sel.brecha_mdp_abs_fmt} MDP</strong> dentro de la selección).`;
    }
    return `<strong>Interpretación ejecutiva:</strong> En el ejercicio <strong>${yr}</strong> —frente a una media de referencia de <strong>$${ref.value_fmt} MXN</strong> (n = ${ref.n})—, ${parts.join('; ')}.${gapClause}${mdpContrast}`;
  }

  function formatExecutiveSummaryHtml(summary, structuredJson) {
    const yr = summary.target_year;
    const rows = summary.rows;
    const ref = summary.national_reference;
    const sel = summary.selection_summary;
    const notes = (structuredJson && structuredJson.interpretation_notes) || [];
    const stateTitles = rows.map(r => r.entidad).join(', ');

    let html = `🤖 <strong>Resumen ejecutivo — ${stateTitles} (${yr})</strong><br/>`;
    for (const note of notes) {
      html += `ℹ️ <em>${note}</em><br/>`;
    }

    if (summary.all_severidad_missing && summary.all_mdp_missing) {
      html += `<br/>No hay datos de severidad ni costo total para ${yr} en las entidades seleccionadas.`;
      return html;
    }

    if (summary.all_severidad_missing) {
      html += `<br/>No hay datos de severidad para ${yr} en las entidades seleccionadas.<br/>`;
    }

    const narrative = buildHumanNarrativeHtml(summary);
    if (narrative) {
      html += `<br/>${narrative}<br/><br/>`;
    }

    if (ref.value !== null) {
      html += `Referencia: media de severidad de las entidades con dato, <strong>$${ref.value_fmt} MXN (n = ${ref.n})</strong>.<br/><br/>`;
    } else {
      html += `Referencia: media de severidad de las entidades con dato, <strong>no calculable (n = 0)</strong>.<br/><br/>`;
    }

    html += `<strong>1. Severidad y categoría (${yr})</strong><br/>`;
    for (const r of rows) {
      const sevCell = r.severidad !== null ? `$${r.severidad_fmt} MXN` : 'sin dato';
      const idxCell = r.indice !== null ? `${r.indice_fmt} pts` : 'no calculable';
      const rkCell = r.rank_nacional_severidad !== null ? `${r.rank_nacional_severidad}.º de ${r.n_nacional_severidad}` : 'sin dato';
      html += `• <strong>${r.entidad}</strong>: <strong>${sevCell}</strong> | Índice: <strong>${idxCell}</strong> | Categoría: <strong>${r.categoria}</strong> | Posición nacional: <strong>${rkCell}</strong><br/>`;
    }

    if (sel && sel.brecha_severidad_abs !== null && sel.lider_severidad !== sel.menor_severidad) {
      html += `• Brecha en la selección: <strong>${sel.lider_severidad}</strong> supera a <strong>${sel.menor_severidad}</strong> en <strong>$${sel.brecha_severidad_abs_fmt} MXN (+${sel.brecha_severidad_pct_fmt} % sobre ${sel.menor_severidad})</strong>.<br/>`;
    }

    html += `<br/><strong>2. Costo total (${yr})</strong><br/>`;
    for (const r of rows) {
      const mdpCell = r.costo_mdp !== null ? `$${r.costo_mdp_fmt} MDP` : 'sin dato';
      const rkMdpCell = r.rank_nacional_mdp !== null ? `${r.rank_nacional_mdp}.º de ${r.n_nacional_mdp}` : 'sin dato';
      html += `• <strong>${r.entidad}</strong>: <strong>${mdpCell}</strong> | Posición nacional: <strong>${rkMdpCell}</strong><br/>`;
    }

    if (sel && sel.lider_mdp) {
      if (sel.lideres_difieren) {
        html += `• En la selección, <strong>${sel.lider_severidad}</strong> lidera la severidad y <strong>${sel.lider_mdp}</strong> el costo total (diferencia: $${sel.brecha_mdp_abs_fmt} MDP). En este conjunto de datos, la severidad se calcula dividiendo el costo entre un número de siniestros estimado a partir de la población (35 % de exposición × 30 % de frecuencia), así que la diferencia de posiciones refleja ese denominador y no una medición de la exposición asegurada.<br/>`;
      } else if (sel.brecha_mdp_abs !== null && sel.lider_mdp !== sel.menor_mdp) {
        html += `• En la selección, <strong>${sel.lider_mdp}</strong> lidera tanto la severidad como el costo total (diferencia en costo: $${sel.brecha_mdp_abs_fmt} MDP).<br/>`;
      }
    }

    html += `<br/><strong>3. Evolución 2020 → ${yr}</strong><br/>`;
    for (const r of rows) {
      const idxEvol = r.delta_indice_pts !== null ? `${r.delta_indice_fmt} (${r.indice_2020_fmt} → ${r.indice_fmt})` : 'no calculable';
      html += `• <strong>${r.entidad}</strong>: Severidad <strong>${r.var_severidad_fmt}</strong> | Costo total <strong>${r.var_mdp_fmt}</strong> | Índice <strong>${idxEvol}</strong><br/>`;
    }
    html += `<em>Coinciden porque la severidad se deriva del costo con un número de siniestros fijo por entidad.</em><br/>`;

    html += `<br/><strong>4. Alcance y limitaciones</strong><br/>`;
    html += `• Severidad = costo total / siniestros estimados (35 % × 30 % de la población 2020); no son siniestros observados.<br/>`;
    html += `• El parque INEGI VMRC no equivale a la exposición asegurada y no varía por año en este conjunto de datos.<br/>`;
    html += `• Umbrales absolutos en MXN nominales; no se ajustan por inflación.`;

    if (rows.length > 0) {
      const buttons = rows
        .map(r => `<button class="btn-chat-action" onclick="window.selectStateInDashboard('${r.entidad}', '${yr}')">🗺️ Ver ${r.entidad} (${yr})</button>`)
        .join('');
      const recTarget = rows.map(r => r.entidad).join(' y ');
      const recBtn = `<button class="btn-chat-action" onclick="document.getElementById('chatInput').value='Recomendaciones, acciones preventivas y oportunidades para ${recTarget} en ${yr}'; handleUserChatMessage();">🎯 Recomendaciones y oportunidades</button>`;
      html += `<div class="chat-action-bar">${buttons}${recBtn}<button class="btn-chat-action" onclick="window.highlightAndScrollToTable('${rows[0].entidad}', '${yr}')">🔍 Ver en tabla</button></div>`;
    }

    return html;
  }

  function computeRecommendationsAndOpportunities(data, stateNames, targetYear) {
    const hasStates = Array.isArray(stateNames) && stateNames.length > 0;
    const execSummary = hasStates ? computeExecutiveSummary(data, stateNames, targetYear) : null;
    const yrStr = String(targetYear || 2024);

    const { mediaRef: mediaRef2020 } = computeNationalReferenceForYear(data, '2020');
    const { mediaRef: mediaRef2024 } = computeNationalReferenceForYear(data, '2024');
    const natCagrAcum = mediaRef2020 && mediaRef2024 ? ((mediaRef2024 - mediaRef2020) / mediaRef2020) * 100.0 : 0.0;
    const natCagrAnual = (Math.pow(1.0 + natCagrAcum / 100.0, 0.25) - 1.0) * 100.0;

    const nEst = data.estados.length || 1;
    const natPrecioAutoK = data.estados.reduce((acc, s) => acc + Number(s.precio_promedio_auto_ml_k_mxn || 0), 0) / nEst;
    const natMotorizacion = data.estados.reduce((acc, s) => acc + Number(s.autos_por_1000_hab || 0), 0) / nEst;

    const totalMdpYr = data.estados.reduce((acc, s) => {
      const mv = s.yearly_mdp ? s.yearly_mdp[yrStr] : null;
      return isValidMdp(mv) ? acc + Number(mv) : acc;
    }, 0);

    const rVal = Number(data.scatter_stats ? data.scatter_stats.r_pearson : 0.8488);
    const r2Pct = Number(data.scatter_stats ? data.scatter_stats.r2_score : 0.7205) * 100.0;

    const estadosDict = {};
    for (const s of data.estados) {
      estadosDict[s.entidad] = s;
    }

    const enrichedRows = [];
    if (execSummary) {
      for (const r of execSummary.rows) {
        const st = estadosDict[r.entidad];
        const cagrAcum = Number(st.cagr_2020_2024_pct);
        const cagrAnual = (Math.pow(1.0 + cagrAcum / 100.0, 0.25) - 1.0) * 100.0;
        const precioK = Number(st.precio_promedio_auto_ml_k_mxn);
        const motor = Number(st.autos_por_1000_hab);
        const costoAuto = Number(st.costo_por_auto_registrado);
        const sevProm = Number(st.severidad_promedio);
        const catPer = displayCategoryLabel(st.categoria_severidad);
        const pctMdpYr = r.costo_mdp !== null && totalMdpYr > 0 ? (r.costo_mdp / totalMdpYr) * 100.0 : null;

        enrichedRows.push({
          ...r,
          severidad_promedio: sevProm,
          severidad_promedio_fmt: formatNumber(sevProm, 2),
          categoria_periodo: catPer,
          cagr_acumulado: cagrAcum,
          cagr_acumulado_fmt: `+${formatNumber(cagrAcum, 1)} %`,
          cagr_anual: cagrAnual,
          cagr_anual_fmt: `+${formatNumber(cagrAnual, 1)} %`,
          precio_auto_k: precioK,
          precio_auto_k_fmt: formatNumber(precioK, 0),
          autos_por_1000_hab: motor,
          autos_por_1000_hab_fmt: formatNumber(motor, 1),
          costo_por_auto: costoAuto,
          costo_por_auto_fmt: formatNumber(costoAuto, 2),
          pct_costo_nacional_yr: pctMdpYr,
          pct_costo_nacional_yr_fmt: pctMdpYr !== null ? formatNumber(pctMdpYr, 1) : 'no calculable'
        });
      }
    }

    let portfolioContext = null;
    if (!hasStates) {
      const sortedMdp = [...data.estados].sort((a, b) => b.siniestros_ocurridos_mdp_promedio - a.siniestros_ocurridos_mdp_promedio);
      const top5Mdp = sortedMdp.slice(0, 5);
      const sum5Mdp = top5Mdp.reduce((acc, s) => acc + s.siniestros_ocurridos_mdp_promedio, 0);
      const totNatMdp = Number(data.metadata.total_mdp_nacional_promedio);
      const paretoPct = (sum5Mdp / totNatMdp) * 100.0;

      const sortedSev = [...data.estados].sort((a, b) => b.severidad_promedio - a.severidad_promedio);
      const sortedCagr = [...data.estados].sort((a, b) => b.cagr_2020_2024_pct - a.cagr_2020_2024_pct);

      portfolioContext = {
        pareto: {
          pct_k: paretoPct,
          sum_k_mdp: sum5Mdp,
          total_national_mdp: totNatMdp,
          top_states: top5Mdp.map((s, idx) => ({
            rank: idx + 1,
            entidad: s.entidad,
            mdp: s.siniestros_ocurridos_mdp_promedio,
            pct_nacional: s.pct_costo_nacional
          }))
        },
        top_sev: sortedSev.slice(0, 5).map((s, idx) => ({
          rank: idx + 1,
          entidad: s.entidad,
          severidad: s.severidad_promedio,
          indice: s.indice_severidad
        })),
        min_state: {
          entidad: sortedSev[sortedSev.length - 1].entidad,
          severidad: sortedSev[sortedSev.length - 1].severidad_promedio,
          idx: sortedSev[sortedSev.length - 1].indice_severidad
        },
        growth_leaders: sortedCagr.slice(0, 3).map(s => ({
          entidad: s.entidad,
          cagr_acumulado: s.cagr_2020_2024_pct,
          cagr_anual: (Math.pow(1.0 + s.cagr_2020_2024_pct / 100.0, 0.25) - 1.0) * 100.0
        }))
      };
    }

    const fallbackRef = computeNationalReferenceForYear(data, yrStr);
    return {
      scope: hasStates ? 'state' : 'national',
      target_year: Number(targetYear || 2024),
      national_reference: execSummary
        ? execSummary.national_reference
        : {
            method: 'simple_mean_entities_with_data',
            label: 'Media de severidad de las entidades con dato',
            value: fallbackRef.mediaRef,
            value_fmt: fallbackRef.mediaRef !== null ? formatNumber(fallbackRef.mediaRef, 2) : 'no calculable',
            n: fallbackRef.n
          },
      rows: enrichedRows,
      selection_summary: execSummary ? execSummary.selection_summary : null,
      national_benchmarks: {
        nat_cagr_acum: natCagrAcum,
        nat_cagr_acum_fmt: `+${formatNumber(natCagrAcum, 1)} %`,
        nat_cagr_anual: natCagrAnual,
        nat_cagr_anual_fmt: `+${formatNumber(natCagrAnual, 1)} %`,
        nat_precio_auto_k: natPrecioAutoK,
        nat_precio_auto_k_fmt: formatNumber(natPrecioAutoK, 1),
        nat_motorizacion: natMotorizacion,
        nat_motorizacion_fmt: formatNumber(natMotorizacion, 1),
        total_mdp_yr: totalMdpYr,
        total_mdp_yr_fmt: formatNumber(totalMdpYr, 2),
        r_pearson: rVal,
        r_pearson_fmt: formatNumber(rVal, 4, false),
        r2_pct: r2Pct,
        r2_pct_fmt: formatNumber(r2Pct, 2)
      },
      portfolio_context: portfolioContext
    };
  }

  function formatRecommendationsHtml(recData, structuredJson) {
    const yr = recData.target_year;
    const rows = recData.rows;
    const ref = recData.national_reference;
    const bench = recData.national_benchmarks;
    const notes = (structuredJson && structuredJson.interpretation_notes) || [];

    if (recData.scope === 'national' || !rows.length) {
      const ctx = recData.portfolio_context;
      const pareto = ctx.pareto;
      const topSev = ctx.top_sev;
      const growth = ctx.growth_leaders;
      const minSt = ctx.min_state;

      let html = `🤖 <strong>Recomendaciones, Acciones Preventivas y Oportunidades — Cartera Nacional (${yr})</strong><br/>`;
      for (const note of notes) {
        html += `ℹ️ <em>${note}</em><br/>`;
      }
      html += `<br/><strong>1. Diagnóstico Cuantitativo Base (Evidencia del Reporte):</strong><br/>`;
      html += `• <strong>Concentración Financiera (Pareto):</strong> El Top 5 concentra el <strong>${formatNumber(pareto.pct_k, 1)} %</strong> del costo nacional (<strong>$${formatNumber(pareto.sum_k_mdp, 2)} MDP</strong> de <strong>$${formatNumber(pareto.total_national_mdp, 2)} MDP</strong> anuales), liderado por <strong>${pareto.top_states[0].entidad} ($${formatNumber(pareto.top_states[0].mdp, 2)} MDP)</strong> y <strong>${pareto.top_states[1].entidad} ($${formatNumber(pareto.top_states[1].mdp, 2)} MDP)</strong>.<br/>`;
      html += `• <strong>Severidad Crítica y Dinámica 2020–2024:</strong> <strong>${topSev[0].entidad}</strong> encabeza la severidad promedio con <strong>$${formatNumber(topSev[0].severidad, 2)} MXN</strong> (índice <strong>${formatNumber(topSev[0].indice, 1)} pts</strong>), mientras que <strong>${growth[0].entidad}</strong> registra el mayor crecimiento acumulado con <strong>+${formatNumber(growth[0].cagr_acumulado, 1)} %</strong> (CAGR <strong>+${formatNumber(growth[0].cagr_anual, 1)} %</strong> anual).<br/><br/>`;

      html += `<strong>2. Acciones Preventivas y de Mitigación:</strong><br/>`;
      html += `• <strong>Control de talleres y valuación en polos de Severidad Crítica (&ge; $11,000.00 MXN):</strong> Establecer convenios de tabuladores cerrados de mano de obra y compra consolidada de autopartes en <strong>${topSev[0].entidad} ($${formatNumber(topSev[0].severidad, 2)} MXN)</strong>, <strong>${topSev[1].entidad} ($${formatNumber(topSev[1].severidad, 2)} MXN)</strong> y <strong>${topSev[2].entidad} ($${formatNumber(topSev[2].severidad, 2)} MXN)</strong>, considerando la asociación con el precio comercial vehicular (<strong>r = +${bench.r_pearson_fmt}</strong>, <strong>R² = ${bench.r2_pct_fmt} %</strong>).<br/>`;
      html += `• <strong>Prevención vial focalizada en el Top 5 Pareto (${formatNumber(pareto.pct_k, 1)} % del volumen):</strong> Desplegar telemetría en flotillas y programas de prevención en corredores urbanos de <strong>${pareto.top_states.map(s => s.entidad).join(', ')}</strong>.<br/>`;
      html += `• <strong>Vigilancia de inflación siniestral (2020–2024):</strong> Auditar suficiencia de sumas aseguradas en entidades con aceleración superior a la media nacional (<strong>${bench.nat_cagr_acum_fmt}</strong>), encabezadas por <strong>${growth[0].entidad} (+${formatNumber(growth[0].cagr_acumulado, 1)} %)</strong> y <strong>${growth[1].entidad} (+${formatNumber(growth[1].cagr_acumulado, 1)} %)</strong>.<br/><br/>`;

      html += `<strong>3. Identificación de Oportunidades Basadas en los Datos:</strong><br/>`;
      html += `• <strong>Crecimiento selectivo en plazas de Severidad Baja (&lt; $7,500.00 MXN):</strong> Impulsar penetración comercial en mercados con severidad contenida, como <strong>${minSt.entidad} ($${formatNumber(minSt.severidad, 2)} MXN, índice ${formatNumber(minSt.idx, 1)} pts)</strong>, manteniendo disciplina de suscripción.<br/>`;
      html += `• <strong>Productos modulares para el parque en circulación (INEGI VMRC):</strong> Desarrollar coberturas escalonadas (Responsabilidad Civil ampliada y deducible flexible) para capturar parque registrado no asegurado sin presionar la severidad media.<br/><br/>`;

      html += `<strong>4. Alcance y Guardrail Metodológico:</strong><br/>`;
      html += `• Recomendaciones derivadas de los indicadores macroestatales de <code>data.json</code> (RN-01 a RN-06). La asociación estadística con el precio vehicular no implica causalidad directa única.`;
      html += `<div class="chat-action-bar">
        <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('')">🔍 Ver matriz nacional</button>
      </div>`;
      return html;
    }

    const stateTitles = rows.map(r => r.entidad).join(', ');
    let html = `🤖 <strong>Recomendaciones, Acciones Preventivas y Oportunidades — ${stateTitles} (${yr})</strong><br/>`;
    for (const note of notes) {
      html += `ℹ️ <em>${note}</em><br/>`;
    }

    html += `<br/><strong>1. Diagnóstico Cuantitativo Base (<code>data.json</code> · ${yr}):</strong><br/>`;
    for (const r of rows) {
      const diffVs100 = r.indice !== null ? Math.abs(r.indice - 100.0) : 0.0;
      const dirStr = r.indice !== null && r.indice >= 100.0 ? 'por encima' : 'por debajo';
      let catShift = '';
      if (r.categoria !== r.categoria_periodo) {
        catShift = ` <em>(escaló de categoría <strong>${r.categoria_periodo}</strong> en el promedio 2020–2024 [$${r.severidad_promedio_fmt} MXN] a <strong>${r.categoria}</strong> en ${yr})</em>`;
      }
      html += `• <strong>${r.entidad}</strong>: Severidad de <strong>$${r.severidad_fmt} MXN</strong> por siniestro (<strong>${r.rank_nacional_severidad}.º lugar nacional de ${r.n_nacional_severidad}</strong>), clasificada en nivel <strong>${r.categoria}</strong>${catShift} con un Índice Relativo de <strong>${r.indice_fmt} pts</strong> (<strong>${formatNumber(diffVs100, 1)} % ${dirStr}</strong> de la media nacional de <strong>$${ref.value_fmt} MXN</strong>, n = ${ref.n}).<br/>`;
      html += `&nbsp;&nbsp;- <strong>Volumen y Evolución (2020 → ${yr}):</strong> Acumula <strong>$${r.costo_mdp_fmt} MDP</strong> (<strong>${r.rank_nacional_mdp}.º de ${r.n_nacional_mdp}</strong>, <strong>${r.pct_costo_nacional_yr_fmt} %</strong> del costo nacional en ${yr}). Frente a 2020, su severidad varió <strong>${r.var_severidad_fmt}</strong> (CAGR 2020–2024: <strong>${r.cagr_anual_fmt}</strong> anual) y su índice relativo cambió en <strong>${r.delta_indice_fmt}</strong> (de <strong>${r.indice_2020_fmt}</strong> a <strong>${r.indice_fmt} pts</strong>).<br/>`;
      html += `&nbsp;&nbsp;- <strong>Factores del Parque Vehicular:</strong> Precio comercial medio del vehículo de <strong>$${r.precio_auto_k_fmt}k MXN</strong> (media estatal: <strong>$${bench.nat_precio_auto_k_fmt}k MXN</strong>; asociación nacional <strong>r = +${bench.r_pearson_fmt}</strong>, <strong>R² = ${bench.r2_pct_fmt} %</strong>) y tasa de motorización de <strong>${r.autos_por_1000_hab_fmt} autos / 1,000 hab.</strong> (<strong>${r.automoviles_registrados.toLocaleString('es-MX')} autos</strong> registrados INEGI VMRC vs. <strong>${bench.nat_motorizacion_fmt}</strong> de media estatal).<br/>`;
    }

    html += `<br/><strong>2. Acciones Preventivas y de Mitigación de Severidad:</strong><br/>`;
    for (const r of rows) {
      if (r.categoria === 'Crítica' || (r.indice !== null && r.indice >= 110.0)) {
        html += `• <strong>Control de costos de reparación y talleres en ${r.entidad} (Severidad ${r.categoria}: $${r.severidad_fmt} MXN | Índice: ${r.indice_fmt} pts):</strong> Dado que rebasa el umbral crítico de <strong>$11,000.00 MXN</strong> y registra un valor comercial vehicular de <strong>$${r.precio_auto_k_fmt}k MXN</strong>, implementar <strong>convenios de tabuladores cerrados de mano de obra, compra consolidada de autopartes y auditoría técnica obligatoria</strong> en reclamos mayores a <strong>$11,000.00 MXN</strong>, además de revisar umbrales de pérdida total.<br/>`;
      } else if (r.categoria === 'Media') {
        const gapCrit = Math.max(0.0, 11000.0 - (r.severidad || 0.0));
        html += `• <strong>Contención preventiva de estrato en ${r.entidad} (Severidad Media: $${r.severidad_fmt} MXN | Brecha a Crítica: $${formatNumber(gapCrit, 2)} MXN):</strong> Reforzar <strong>direccionamiento a red de talleres preferentes y topes de valuación por orden de reparación</strong> para evitar que la entidad rebase el umbral crítico de <strong>$11,000.00 MXN</strong>.<br/>`;
      } else {
        html += `• <strong>Preservación de severidad contenida en ${r.entidad} (Severidad Baja: $${r.severidad_fmt} MXN | Índice: ${r.indice_fmt} pts):</strong> Mantener acuerdos tarifarios con talleres locales y control de costos médicos/RC para conservar la severidad por debajo del límite de <strong>$7,500.00 MXN</strong>.<br/>`;
      }

      html += `• <strong>Prevención vial focalizada por densidad vehicular (${r.autos_por_1000_hab_fmt} autos / 1,000 hab.) y volumen ($${r.costo_mdp_fmt} MDP):</strong> Desplegar <strong>alertas preventivas en corredores urbanos, telemetría en flotillas y esquemas de deducible diferenciado</strong> en las zonas que concentran los <strong>$${r.costo_mdp_fmt} MDP</strong> (<strong>${r.rank_nacional_mdp}.º lugar nacional</strong>).<br/>`;

      if (r.delta_indice_pts !== null && r.delta_indice_pts > 0) {
        html += `• <strong>Ajuste por aceleración inflacionaria en ${r.entidad} (${r.var_severidad_fmt} desde 2020 | &Delta; Índice: ${r.delta_indice_fmt}):</strong> Su severidad creció por encima de la media nacional (<strong>${bench.nat_cagr_acum_fmt}</strong>), elevando su índice de <strong>${r.indice_2020_fmt}</strong> a <strong>${r.indice_fmt} pts</strong>. Se recomienda <strong>actualización prioritaria de suficiencia tarifaria y sumas aseguradas</strong>.<br/>`;
      } else {
        html += `• <strong>Vigilancia de inflación nominal en ${r.entidad} (${r.var_severidad_fmt} desde 2020 | CAGR: ${r.cagr_anual_fmt} anual):</strong> Aunque su índice relativo se moderó en <strong>${r.delta_indice_fmt}</strong> (<strong>${r.indice_2020_fmt} &rarr; ${r.indice_fmt} pts</strong>), el alza nominal acumulada llevó la severidad a <strong>$${r.severidad_fmt} MXN</strong>. Se recomienda <strong>indexación preventiva de sumas aseguradas y monitoreo trimestral de autopartes</strong>.<br/>`;
      }
    }

    html += `<br/><strong>3. Identificación de Oportunidades Basadas en los Datos:</strong><br/>`;
    for (const r of rows) {
      if (r.delta_indice_pts !== null && r.delta_indice_pts <= 0) {
        html += `• <strong>Oportunidad de retención y crecimiento selectivo por estabilización relativa (${r.delta_indice_fmt} en índice 2020 → ${yr}):</strong> <strong>${r.entidad}</strong> creció a un ritmo menor que el promedio nacional (<strong>${r.var_severidad_fmt}</strong> vs. <strong>${bench.nat_cagr_acum_fmt}</strong> nacional), reduciendo su índice de <strong>${r.indice_2020_fmt}</strong> a <strong>${r.indice_fmt} pts</strong>. Esto abre oportunidad para <strong>fidelizar cartera sana y crecer selectivamente</strong> en segmentos de riesgo controlado.<br/>`;
      } else {
        html += `• <strong>Oportunidad de re-segmentación técnica en ${r.entidad} (${r.delta_indice_fmt} en índice 2020 → ${yr}):</strong> Introducir productos con <strong>deducible calibrado y taller multimarca certificado</strong> para recuperar margen técnico frente al incremento relativo de severidad.<br/>`;
      }

      html += `• <strong>Oportunidad de penetración sobre el parque vehicular registrado (${r.automoviles_registrados.toLocaleString('es-MX')} autos INEGI VMRC):</strong> Con una motorización de <strong>${r.autos_por_1000_hab_fmt} autos / 1,000 hab.</strong> y un costo anual medio por auto registrado de <strong>$${r.costo_por_auto_fmt} MXN</strong> (promedio 2020–2024), diseñar <strong>coberturas modulares (Responsabilidad Civil ampliada, pérdida total o deducible flexible)</strong> para captar parque en circulación no asegurado sin presionar la severidad unitaria (<strong>$${r.severidad_fmt} MXN</strong>).<br/>`;
      html += `• <strong>Calibración de oferta según valor comercial regional ($${r.precio_auto_k_fmt}k MXN):</strong> Alinear paquetes de cobertura amplia y reparación al valor comercial promedio de <strong>$${r.precio_auto_k_fmt}k MXN</strong> en <strong>${r.entidad}</strong>, optimizando la relación entre valor del activo y costo medio por reclamo.<br/>`;
    }

    html += `<br/><strong>4. Alcance y Guardrail Metodológico:</strong><br/>`;
    html += `• Estas recomendaciones se derivan de los indicadores agregados verificados en <code>data.json</code> (RN-01 a RN-06).<br/>`;
    html += `• La asociación entre precio vehicular y severidad (<strong>r = +${bench.r_pearson_fmt}</strong>, <strong>R² = ${bench.r2_pct_fmt} %</strong>) es orientativa y <strong>no implica causalidad directa única</strong>; decisiones de suscripción o tarifa a nivel póliza requieren cruzar con exposición asegurada y frecuencia observada.`;

    if (rows.length > 0) {
      const buttons = rows
        .map(r => `<button class="btn-chat-action" onclick="window.selectStateInDashboard('${r.entidad}', '${yr}')">🗺️ Ver ${r.entidad} (${yr})</button>`)
        .join('');
      html += `<div class="chat-action-bar">${buttons}<button class="btn-chat-action" onclick="window.highlightAndScrollToTable('${rows[0].entidad}', '${yr}')">🔍 Ver en tabla</button></div>`;
    }

    return html;
  }

  function formatBusinessRulesHtml(userQuery, data) {
    const normQ = normalizeText(userQuery);
    const { mediaRef: ref2024, n: n2024 } = data ? computeNationalReferenceForYear(data, '2024') : { mediaRef: 9041.640571, n: 32 };
    const cdmxObj = data && data.estados ? data.estados.find(s => s.entidad === 'Ciudad de Mexico') : null;
    const cdmx2024 = cdmxObj && cdmxObj.yearly_severidad ? cdmxObj.yearly_severidad['2024'] : 14112.41;
    const cdmxIdx2024 = ref2024 ? (cdmx2024 / ref2024) * 100.0 : 156.1;

    // 1. Regla específica de Índice Relativo / Referencia Nacional
    if ((normQ.includes('indice') || normQ.includes('relativo') || normQ.includes('base 100') || normQ.includes('referencia nacional')) && !normQ.includes('glosario')) {
      return `🤖 <strong>Regla de Negocio (RN-01) — Cálculo del Índice Relativo y Referencia Nacional</strong><br/><br/>
<strong>1. Fórmula Matemática Oficial:</strong>
<div class="formula-box">
  <strong>Índice Relativo (Base = 100):</strong><br/>
  Índice_e(Y) = 100 × [ Severidad_e(Y) / Media_ref(Y) ]<br/>
  Media_ref(Y) = Σ Severidad_e(Y) / n(Y)
</div><br/>
<strong>2. Definición e Interpretación Actuarial:</strong><br/>
• <strong>Media_ref(Y) (Decisión P1):</strong> Es la media simple de las <code>n(Y)</code> entidades federativas con severidad válida (finita y <code>&gt; 0</code>) en el año <code>Y</code>.<br/>
• <strong>Base 100.0 pts:</strong> Representa exactamente la media de severidad de las entidades con dato en ese año. Un índice de <strong>156.1 pts</strong> significa que el estado se ubica un <strong>+56.1 % por encima</strong> de la referencia nacional.<br/><br/>
<strong>3. Reglas de Datos Faltantes y Redondeo (<code>config/actuarial_rules.json</code>):</strong><br/>
• <strong>Faltantes:</strong> Si la severidad del estado es <code>sin dato</code> o si <code>n(Y) = 0</code>, el índice se reporta como <strong><code>no calculable</code></strong> (nunca se convierte en <code>0</code>).<br/>
• <strong>Redondeo determinista:</strong> Se calcula con precisión completa (<code>IEEE-754</code>) y se formatea a <strong>1 decimal</strong> con <strong><code>ROUND_HALF_UP</code></strong> (mitad lejos de cero sobre la representación decimal más corta).<br/><br/>
<strong>4. Ejemplo Real en el Reporte (Ciudad de México, 2024):</strong><br/>
• <code>Severidad_CDMX(2024)</code> = <strong>$${formatNumber(cdmx2024, 2)} MXN</strong><br/>
• <code>Media_ref(2024)</code> = <strong>$${formatNumber(ref2024, 2)} MXN (n = ${n2024})</strong><br/>
• <code>Índice_CDMX(2024)</code> = <code>100 × (${formatNumber(cdmx2024, 2)} / ${formatNumber(ref2024, 2)})</code> = <strong>${formatNumber(cdmxIdx2024, 1)} pts</strong>.`;
    }

    // 2. Regla específica de Categorías y Umbrales
    if ((normQ.includes('categoria') || normQ.includes('umbral') || normQ.includes('semaforo') || normQ.includes('clasifica')) && !normQ.includes('glosario')) {
      return `🤖 <strong>Regla de Negocio (RN-02) — Umbrales de Categoría de Severidad (Decisión P3)</strong><br/><br/>
<strong>1. Regla Oficial de Clasificación Nominal:</strong>
<div class="formula-box">
  • <strong>Crítica (Rojo):</strong> Severidad &ge; $11,000.00 MXN<br/>
  • <strong>Media (Ámbar):</strong> $7,500.00 MXN &le; Severidad &lt; $11,000.00 MXN<br/>
  • <strong>Baja (Verde):</strong> 0 &lt; Severidad &lt; $7,500.00 MXN
</div><br/>
<strong>2. Reglas de Integridad y Aislamiento Temporal:</strong><br/>
• La comparación se realiza sobre el valor numérico <strong>sin redondear</strong>.<br/>
• En consultas de un año específico <code>Y</code>, la categoría proviene exclusivamente de <code>yearly_categoria[Y]</code>. Si falta ese dato o la severidad es inválida, se reporta <strong><code>sin dato</code></strong> (jamás se usa la categoría del promedio 2020–2024 como sustituto silencioso).<br/>
• Los umbrales están fijos en pesos nominales (no ajustados por inflación).`;
    }

    // 3. Regla específica de Evolución / Variación / CAGR
    if ((normQ.includes('evolucion') || normQ.includes('variacion') || normQ.includes('cagr') || normQ.includes('delta')) && !normQ.includes('glosario')) {
      return `🤖 <strong>Regla de Negocio (RN-03) — Evolución desde 2020 y CAGR</strong><br/><br/>
<strong>1. Fórmulas Matemáticas:</strong>
<div class="formula-box">
  • <strong>Variación % (Severidad o MDP):</strong> ((Valor_Y / Valor_2020) − 1) × 100  [%]<br/>
  • <strong>Cambio en Índice (Δ Índice):</strong> Índice_Y − Índice_2020  [pts]<br/>
  • <strong>CAGR Anual (2020–2024):</strong> ((Severidad_2024 / Severidad_2020)^(1/4) − 1) × 100  [% anual]
</div><br/>
<strong>2. Reglas de Casos Límite y Propiedad del Modelo (H4):</strong><br/>
• Si <code>Y = 2020</code> y la base es válida, la variación es <strong><code>0.0 %</code></strong> y <strong><code>0.0 pts</code></strong>.<br/>
• Si la base 2020 es ausente, nula o <code>0</code>, se reporta <strong><code>no calculable</code></strong>.<br/>
• La variación <code>%</code> de severidad y la de costo total (MDP) coinciden exactamente porque la severidad se deriva con un número de siniestros fijo por entidad (<code>0.35 × 0.30 × población_2020</code>).`;
    }

    // 4. Regla específica de Rankings y Empates
    if ((normQ.includes('ranking') || normQ.includes('posicion') || normQ.includes('empate')) && !normQ.includes('glosario')) {
      return `🤖 <strong>Regla de Negocio (RN-04) — Rankings y Desempate al Centavo</strong><br/><br/>
<strong>1. Alcance Nacional y Denominador Dinámico:</strong><br/>
• Se ordenan de mayor a menor las entidades con dato válido en esa métrica y año: formato <strong><code>k.º de n_métrica(Y)</code></strong>.<br/><br/>
<strong>2. Regla de Empates (Ranking de Competencia <code>1, 1, 3</code>):</strong><br/>
• Los valores se comparan redondeados a <strong>2 decimales (centavos)</strong> con <code>ROUND_HALF_UP</code>.<br/>
• Valores idénticos al centavo comparten la misma posición y la siguiente se salta (ej. <code>1.º, 1.º, 3.º</code>).<br/><br/>
<strong>3. Alcance de Selección:</strong><br/>
• Solo se muestra cuando el usuario consulta <code>&ge; 2</code> entidades únicas. Con <code>1</code> entidad se omite.`;
    }

    const isFullCatalogReq =
      normQ.includes('glosario') || normQ.includes('catalogo') || normQ.includes('todas las reglas');
    const natAvgAll = data && data.metadata ? data.metadata.promedio_nacional_severidad : 6674.08;
    const natMdpAll = data && data.metadata ? data.metadata.total_mdp_nacional_promedio : 90373.46;

    // 5. Explicación clara y pedagógica de Severidad (¿Qué es y cómo se calcula?)
    if (normQ.includes('severidad') && !isFullCatalogReq) {
      const detStates = extractStatesDetailed(userQuery, data && data.estados ? data.estados.map(s => s.entidad) : null).states;
      const exStateName = detStates.length > 0 ? detStates[0] : 'Ciudad de Mexico';
      const exSt =
        data && data.estados
          ? data.estados.find(s => s.entidad === exStateName) || cdmxObj
          : null;
      const exSev2024 = exSt && exSt.yearly_severidad ? exSt.yearly_severidad['2024'] : 14112.41;
      const exMdp2024 = exSt && exSt.yearly_mdp ? exSt.yearly_mdp['2024'] : 13647.32;
      const exPob2020 = exSt && exSt.poblacion_2020 ? exSt.poblacion_2020 : 9209944;
      const exClaims = 0.35 * 0.30 * exPob2020;
      const exIdx2024 = ref2024 ? (exSev2024 / ref2024) * 100.0 : 156.1;
      const exCat2024 =
        exSt && exSt.yearly_categoria && exSt.yearly_categoria['2024']
          ? displayCategoryLabel(exSt.yearly_categoria['2024'])
          : 'Crítica';

      return `🤖 <strong>¿Qué es la Severidad y cómo se calcula? (Reglas RN-02 y RN-03)</strong><br/><br/>
<strong>1. ¿Qué es la Severidad? (En lenguaje sencillo):</strong><br/>
• La <strong>severidad</strong> es el <strong>costo económico promedio de cada siniestro</strong>; es decir, cuánto cuesta en promedio reparar o indemnizar <strong>un solo accidente vehicular</strong> (expresado en <strong><code>$ MXN por siniestro</code></strong>).<br/>
• <strong>Diferencia clave frente al Costo Total (<code>MDP</code>):</strong> La severidad mide qué tan caro es <em>cada choque individual</em>, mientras que el <strong>Costo Total (<code>MDP</code>)</strong> suma el dinero de <em>todos los siniestros ocurridos en el estado</em>.<br/><br/>
<strong>2. ¿Cómo se calcula? (Fórmula Actuarial y del Modelo):</strong>
<div class="formula-box">
  <strong>Fórmula general actuarial:</strong><br/>
  Severidad ($ MXN) = Costo Total de Siniestros ($) / Número de Siniestros Ocurridos<br/><br/>
  <strong>Fórmula en este conjunto de datos (RN-03, supuesto H4):</strong><br/>
  Severidad_e(Y) = [ Costo_Total_MDP_e(Y) × 1,000,000 ] / Siniestros_Estimados_e<br/>
  donde Siniestros_Estimados_e = 35 % (exposición) × 30 % (frecuencia) × Población_2020_e
</div><br/>
<strong>3. Ejemplo paso a paso con datos reales (${exStateName}, 2024):</strong><br/>
• <strong>Paso 1 (Costo Total en 2024):</strong> <strong>$${formatNumber(exMdp2024, 2)} MDP</strong> (equivalente a <strong>$${formatNumber(exMdp2024 * 1000000, 0)} MXN</strong>).<br/>
• <strong>Paso 2 (Siniestros estimados):</strong> <code>35 % × 30 % × ${formatNumber(exPob2020, 0)} habitantes</code> = <strong>${formatNumber(exClaims, 2)} siniestros</strong>.<br/>
• <strong>Paso 3 (División):</strong> <code>$${formatNumber(exMdp2024 * 1000000, 0)} MXN / ${formatNumber(exClaims, 2)} siniestros</code> = <strong>$${formatNumber(exSev2024, 2)} MXN por siniestro</strong> (Categoría: <strong>${exCat2024}</strong>, Índice Relativo: <strong>${formatNumber(exIdx2024, 1)} pts</strong> frente a la media nacional 2024 de <strong>$${formatNumber(ref2024, 2)} MXN</strong>, <code>n = ${n2024}</code>).<br/><br/>
<strong>4. ¿Cómo se clasifica el nivel de severidad? (Semáforo RN-02):</strong><br/>
• 🔴 <strong>Crítica:</strong> <code>&ge; $11,000.00 MXN</code> por siniestro.<br/>
• 🟡 <strong>Media:</strong> <code>$7,500.00 a &lt; $11,000.00 MXN</code> por siniestro.<br/>
• 🟢 <strong>Baja:</strong> <code>&lt; $7,500.00 MXN</code> por siniestro.`;
    }

    // 6. Explicación específica de Costo Total (MDP / Millones de Pesos)
    if (
      (normQ.includes('mdp') || normQ.includes('costo total') || normQ.includes('millones de pesos') || normQ.includes('volumen de costo')) &&
      !isFullCatalogReq
    ) {
      const edomexObj = data && data.estados ? data.estados.find(s => s.entidad === 'Estado de Mexico') : null;
      const edomexMdp2024 = edomexObj && edomexObj.yearly_mdp ? edomexObj.yearly_mdp['2024'] : 14461.57;
      const cdmxMdp2024 = cdmxObj && cdmxObj.yearly_mdp ? cdmxObj.yearly_mdp['2024'] : 13647.32;
      return `🤖 <strong>¿Qué es el Costo Total (<code>MDP</code>) y cómo se calcula? (Regla RN-03)</strong><br/><br/>
<strong>1. Definición en lenguaje sencillo:</strong><br/>
• <strong><code>MDP</code></strong> significa <strong>Millones de Pesos</strong> (<code>1 MDP = $1,000,000 MXN</code>).<br/>
• El <strong>Costo Total en MDP</strong> mide el <strong>volumen financiero agregado</strong> de todos los siniestros ocurridos en una entidad. A nivel nacional (promedio anual 2020–2024), el costo total es de <strong>$${formatNumber(natMdpAll, 2)} MDP</strong>.<br/><br/>
<strong>2. Identidad Actuarial Oficial:</strong>
<div class="formula-box">
  Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
</div><br/>
• Mientras la <strong>severidad</strong> mide el costo unitario de <em>un</em> siniestro (<code>$ MXN</code>), el <strong>Costo Total (<code>MDP</code>)</strong> refleja la masa monetaria completa impulsada por el tamaño poblacional y vehicular del estado.<br/><br/>
<strong>3. Ejemplo verificable en el reporte (2024):</strong><br/>
• <strong>Estado de México</strong> ocupa el <strong>1.º lugar nacional en Costo Total</strong> con <strong>$${formatNumber(edomexMdp2024, 2)} MDP</strong> (aunque su severidad unitaria es Media: <code>$8,105.33 MXN</code>), seguido por <strong>Ciudad de México</strong> con <strong>$${formatNumber(cdmxMdp2024, 2)} MDP</strong>.<br/>
• <strong>Aclaración metodológica:</strong> El parque vehicular registrado (<code>INEGI VMRC</code>) mide la escala automotriz macro del estado, pero <strong>no equivale a la exposición asegurada</strong> (pólizas vigentes).`;
    }

    // 7. Explicación específica de Frecuencia y Exposición Asegurada
    if (
      (normQ.includes('frecuencia') || normQ.includes('exposicion') || normQ.includes('parque vehicular') || normQ.includes('inegi vmrc')) &&
      !isFullCatalogReq
    ) {
      return `🤖 <strong>¿Qué son la Frecuencia y la Exposición Asegurada? (Regla RN-03 y Supuesto H4)</strong><br/><br/>
<strong>1. Definición Actuarial:</strong><br/>
• <strong>Exposición Asegurada:</strong> Número de vehículos-año cubiertos por una póliza de seguro vigente.<br/>
• <strong>Frecuencia de Reclamos:</strong> Proporción o tasa de vehículos asegurados que sufren un siniestro en un año:
<div class="formula-box">
  Frecuencia = Siniestros Ocurridos / Exposición Asegurada (Años-Vehículo)
</div><br/>
<strong>2. Cómo operan en este conjunto de datos (H4):</strong><br/>
• En este estudio macroestatal, el denominador de siniestros se estima de forma fija por entidad aplicando <strong>35 % de exposición × 30 % de frecuencia</strong> sobre la <strong>población del Censo INEGI 2020</strong> (<code>0.105 × población_2020</code>).<br/>
• <strong>Distinción crítica:</strong> Las cifras de <strong>Parque Vehicular Registrado (<code>INEGI VMRC</code>)</strong> muestran el total de automóviles en circulación en el estado, pero <strong>no equivalen a la exposición asegurada</strong>.`;
    }

    // 8. Explicación específica de Correlación (r) y Coeficiente de Determinación (R²)
    if (
      (normQ.includes('r2') || normQ.includes('r cuadrada') || normQ.includes('correlacion') || normQ.includes('pearson')) &&
      !isFullCatalogReq
    ) {
      const rVal = data && data.scatter_stats ? data.scatter_stats.r_pearson : 0.8488;
      const r2Pct = data && data.scatter_stats ? data.scatter_stats.r2_score * 100.0 : 72.05;
      return `🤖 <strong>¿Qué miden la Correlación (<code>r</code>) y el Coeficiente <code>R²</code> en este modelo?</strong><br/><br/>
<strong>1. Definición Estadística:</strong><br/>
• <strong>Correlación de Pearson (<code>r = +${formatNumber(rVal, 4, false)}</code>):</strong> Mide la fuerza y dirección de la asociación lineal entre el precio comercial promedio del vehículo (<code>Mercado Libre</code>) y la severidad estatal (Promedio 2020–2024).<br/>
• <strong>Coeficiente de Determinación (<code>R² = ${formatNumber(r2Pct, 2)} %</code>):</strong> Indica que el <strong>${formatNumber(r2Pct, 2)} %</strong> de la variación interestatal de la severidad se explica linealmente por las diferencias en el valor comercial del parque vehicular (<code>R² = r²</code>).<br/><br/>
<strong>2. Guardrail Actuarial (Correlación ≠ Causalidad):</strong><br/>
• Esta relación describe una <strong>asociación estadística agregada</strong>, pero <strong>no implica causalidad directa</strong> ni demuestra que el precio del auto sea la única causa de la severidad.`;
    }

    // 9. Catálogo General de Reglas de Negocio
    return `🤖 <strong>Catálogo de Reglas de Negocio Actuariales (<code>config/actuarial_rules.json</code>)</strong><br/><br/>
<strong>• RN-01 · Referencia Nacional e Índice Relativo (pts):</strong><br/>
<code>Media_ref(Y) = Σ Severidad_e(Y) / n(Y)</code> (Media de severidad de las entidades con dato; promedio 2020–2024: <strong>$${formatNumber(natAvgAll, 2)} MXN</strong>, n = 32).<br/>
<code>Índice_e(Y) = 100 × Severidad_e(Y) / Media_ref(Y)</code> (Base 100, redondeado a 1 decimal con <code>ROUND_HALF_UP</code>).<br/><br/>
<strong>• RN-02 · Umbrales de Categoría de Severidad (P3):</strong><br/>
🔴 <strong>Crítica:</strong> <code>&ge; $11,000.00 MXN</code> · 🟡 <strong>Media:</strong> <code>$7,500.00 a &lt; $11,000.00 MXN</code> · 🟢 <strong>Baja:</strong> <code>&lt; $7,500.00 MXN</code> (evaluados sin redondear sobre <code>yearly_categoria[Y]</code>).<br/><br/>
<strong>• RN-03 · Severidad ($/Siniestro) y Costo Total en MDP:</strong><br/>
<code>1 MDP = $1,000,000 MXN</code> (Total nacional anual promedio: <strong>$${formatNumber(natMdpAll, 2)} MDP</strong>).<br/>
<code>Costo Total (MDP) = [Exposición asegurada × Frecuencia × Severidad en MXN] / 1,000,000</code>.<br/>
En este dataset (H4): <code>Severidad = (MDP × 10⁶) / (0.35 × 0.30 × población_2020)</code>.<br/><br/>
<strong>• RN-04 · Evolución desde 2020:</strong><br/>
<code>Variación % = ((Valor_Y / Valor_2020) − 1) × 100</code> · <code>Δ Índice (pts) = Índice_Y − Índice_2020</code>.<br/><br/>
<strong>• RN-05 · Rankings y Empates:</strong><br/>
Ranking de competencia (<code>1, 1, 3</code>) comparando valores redondeados al centavo (2 decimales) entre las <code>n_métrica(Y)</code> entidades con dato válido.<br/><br/>
<strong>• RN-06 · Redondeo Determinista y Año por Defecto (P2):</strong><br/>
Redondeo <code>ROUND_HALF_UP</code> desde la representación decimal más corta del <code>double</code> (<code>-0.00</code> &rarr; <code>0.00</code>). Si se omite el año en un resumen, se usa <strong><code>2024</code></strong> con aviso explícito.`;
  }

  return {
    ACTUARIAL_RULES,
    normalizeText,
    normalizeWithOffsets,
    roundHalfUpScaled,
    formatNumber,
    computeCategoryFromRule,
    displayCategoryLabel,
    isValidSeverity,
    isValidMdp,
    extractStatesDetailed,
    MemoryManager,
    parseQueryIR,
    computeNationalReferenceForYear,
    computeCompetitionRanksForYear,
    computeExecutiveSummary,
    computeRecommendationsAndOpportunities,
    buildHumanNarrativeHtml,
    formatExecutiveSummaryHtml,
    formatRecommendationsHtml,
    formatBusinessRulesHtml
  };
});

