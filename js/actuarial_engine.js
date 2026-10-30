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
      weak_summary: ['reporte', 'informe'],
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
      ]
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
  };

  function normalizeText(text) {
    if (text === null || text === undefined) return '';
    return String(text)
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

    const effectiveStates = mem.getEffectiveStates(extractedStates, userQuery);
    const isSummary = isSummaryFamily(normQ, effectiveStates.length > 0);
    const isComparison = isComparisonFamily(normQ);

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
      (words.has('promedio') || words.has('periodo') || words.has('historico')) &&
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

    return html;
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
    formatExecutiveSummaryHtml
  };
});
