/**
 * Suite de Paridad Python <-> JavaScript en Node.js (T25 y T26)
 * Verifica:
 * 1. T25: Formateador determinista ROUND_HALF_UP en JS frente a valores esperados independientes y de Python.
 * 2. T26: Paridad numérica (tolerancia mixta |a - b| <= max(1e-9, 1e-12 * max(|a|, |b|))), coincidencia de nulls
 *    e igualdad exacta de cadenas formateadas e IR entre Python y js/actuarial_engine.js para T1–T24.
 */

import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '../..');

const require = createRequire(import.meta.url);
const ActuarialEngine = require(path.join(ROOT_DIR, 'js/actuarial_engine.js'));

const realData = JSON.parse(fs.readFileSync(path.join(ROOT_DIR, 'data.json'), 'utf8'));
const parityVectors = JSON.parse(fs.readFileSync(path.join(ROOT_DIR, 'tests/fixtures/parity_vectors.json'), 'utf8'));
const canonicalStates = realData.estados.map(s => s.entidad);

function mixedNumericEqual(a, b) {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  const diff = Math.abs(a - b);
  const tol = Math.max(1e-9, 1e-12 * Math.max(Math.abs(a), Math.abs(b)));
  return diff <= tol;
}

function assertSummaryParity(caseId, pySum, jsSum) {
  assert.equal(jsSum.target_year, pySum.target_year, `[${caseId}] target_year mismatch`);
  assert.equal(jsSum.all_severidad_missing, pySum.all_severidad_missing, `[${caseId}] all_severidad_missing mismatch`);
  assert.equal(jsSum.all_mdp_missing, pySum.all_mdp_missing, `[${caseId}] all_mdp_missing mismatch`);

  // National reference
  assert.ok(
    mixedNumericEqual(jsSum.national_reference.value, pySum.national_reference.value),
    `[${caseId}] national_reference.value mismatch: JS=${jsSum.national_reference.value} vs PY=${pySum.national_reference.value}`
  );
  assert.equal(jsSum.national_reference.value_fmt, pySum.national_reference.value_fmt, `[${caseId}] national_reference.value_fmt mismatch`);
  assert.equal(jsSum.national_reference.n, pySum.national_reference.n, `[${caseId}] national_reference.n mismatch`);

  // Rows
  assert.equal(jsSum.rows.length, pySum.rows.length, `[${caseId}] rows length mismatch`);
  for (let i = 0; i < pySum.rows.length; i++) {
    const pr = pySum.rows[i];
    const jr = jsSum.rows[i];
    const pfx = `[${caseId} row ${pr.entidad}]`;

    assert.equal(jr.entidad, pr.entidad, `${pfx} entidad`);
    for (const numKey of ['severidad', 'indice', 'indice_2020', 'costo_mdp', 'var_severidad_pct', 'var_mdp_pct', 'delta_indice_pts']) {
      assert.ok(
        mixedNumericEqual(jr[numKey], pr[numKey]),
        `${pfx} ${numKey} numeric mismatch: JS=${jr[numKey]} vs PY=${pr[numKey]}`
      );
    }
    for (const strKey of [
      'severidad_fmt',
      'indice_fmt',
      'indice_2020_fmt',
      'categoria',
      'costo_mdp_fmt',
      'rank_nacional_severidad',
      'n_nacional_severidad',
      'rank_nacional_mdp',
      'n_nacional_mdp',
      'var_severidad_fmt',
      'var_mdp_fmt',
      'delta_indice_fmt'
    ]) {
      assert.equal(jr[strKey], pr[strKey], `${pfx} ${strKey} mismatch: JS=${jr[strKey]} vs PY=${pr[strKey]}`);
    }
  }

  // Selection summary
  if (pySum.selection_summary === null) {
    assert.equal(jsSum.selection_summary, null, `[${caseId}] selection_summary expected null`);
  } else {
    const ps = pySum.selection_summary;
    const js = jsSum.selection_summary;
    assert.deepEqual(js.orden_severidad, ps.orden_severidad, `[${caseId}] orden_severidad`);
    assert.deepEqual(js.orden_mdp, ps.orden_mdp, `[${caseId}] orden_mdp`);
    assert.equal(js.lider_severidad, ps.lider_severidad, `[${caseId}] lider_severidad`);
    assert.equal(js.menor_severidad, ps.menor_severidad, `[${caseId}] menor_severidad`);
    assert.equal(js.lider_mdp, ps.lider_mdp, `[${caseId}] lider_mdp`);
    assert.equal(js.menor_mdp, ps.menor_mdp, `[${caseId}] menor_mdp`);
    assert.equal(js.lideres_difieren, ps.lideres_difieren, `[${caseId}] lideres_difieren`);

    for (const numKey of ['brecha_severidad_abs', 'brecha_severidad_pct', 'brecha_mdp_abs']) {
      assert.ok(
        mixedNumericEqual(js[numKey], ps[numKey]),
        `[${caseId}] selection ${numKey} mismatch: JS=${js[numKey]} vs PY=${ps[numKey]}`
      );
    }
    for (const strKey of ['brecha_severidad_abs_fmt', 'brecha_severidad_pct_fmt', 'brecha_mdp_abs_fmt']) {
      assert.equal(js[strKey], ps[strKey], `[${caseId}] selection ${strKey} mismatch`);
    }
  }
}

let passedCount = 0;

// 1. Prueba T25: Formateador en JS con valores esperados independientes y de Python
const independentFormatterCases = [
  [0.125, 2, '0.13'],
  [1.005, 2, '1.01'],
  [2.675, 2, '2.68'],
  [9.995, 2, '10.00'],
  [-0.125, 2, '-0.13'],
  [-0.004, 2, '0.00'],
  [1234567.895, 2, '1,234,567.90'],
  [1e-7, 2, '0.00'],
  [1e16, 2, '10,000,000,000,000,000.00'],
  [0.05, 1, '0.1'],
  [0.25, 1, '0.3'],
  [-0.05, 1, '-0.1']
];

for (const [val, dec, exp] of independentFormatterCases) {
  const actual = ActuarialEngine.formatNumber(val, dec);
  assert.equal(actual, exp, `[T25 Independent] formatNumber(${val}, ${dec}) -> ${actual} != ${exp}`);
}
for (const fc of parityVectors.formatter_cases) {
  const actual = ActuarialEngine.formatNumber(fc.val, fc.decimals);
  assert.equal(actual, fc.expected, `[T25 Parity] formatNumber(${fc.val}, ${fc.decimals})`);
}
passedCount++;
console.log('✅ T25 (Formateador determinista JS == Python == Independiente): PASS');

// 2. Prueba Independiente en JS con datos crudos (verifica que la fórmula es correcta sin depender de Python)
const t1JsInd = ActuarialEngine.computeExecutiveSummary(realData, ['Nuevo Leon', 'Jalisco'], 2023);
assert.equal(t1JsInd.national_reference.value_fmt, '7,805.92');
assert.equal(t1JsInd.national_reference.n, 32);
assert.equal(t1JsInd.rows[0].severidad_fmt, '16,477.15');
assert.equal(t1JsInd.rows[0].indice_fmt, '211.1');
assert.equal(t1JsInd.rows[1].severidad_fmt, '12,131.95');
assert.equal(t1JsInd.rows[1].indice_fmt, '155.4');
assert.equal(t1JsInd.selection_summary.brecha_severidad_abs_fmt, '4,345.20');
assert.equal(t1JsInd.selection_summary.brecha_severidad_pct_fmt, '35.8');
passedCount++;
console.log('✅ Verificación independiente JS sobre data.json (T1): PASS');

// 3. Prueba T26 (Parte A): Paridad de IR y Summary en casos con datos reales (T1–T16)
for (const rc of parityVectors.real_cases) {
  const mem = new ActuarialEngine.MemoryManager();
  const jsIr = ActuarialEngine.parseQueryIR(rc.query, canonicalStates, mem);

  assert.equal(jsIr.intent, rc.ir.intent, `[${rc.id}] intent mismatch: JS=${jsIr.intent} vs PY=${rc.ir.intent}`);
  assert.deepEqual(jsIr.states, rc.ir.states, `[${rc.id}] states mismatch`);
  assert.deepEqual(jsIr.states_raw, rc.ir.states_raw, `[${rc.id}] states_raw mismatch`);
  assert.deepEqual(jsIr.duplicate_mentions, rc.ir.duplicate_mentions, `[${rc.id}] duplicate_mentions mismatch`);
  assert.equal(jsIr.target_year, rc.ir.target_year, `[${rc.id}] target_year mismatch`);
  assert.equal(jsIr.year_source, rc.ir.year_source, `[${rc.id}] year_source mismatch`);
  assert.equal(jsIr.insufficient_entities, rc.ir.insufficient_entities, `[${rc.id}] insufficient_entities mismatch`);
  assert.deepEqual(jsIr.interpretation_notes, rc.ir.interpretation_notes, `[${rc.id}] interpretation_notes mismatch`);

  if (rc.summary !== null) {
    const jsSum = ActuarialEngine.computeExecutiveSummary(realData, jsIr.states, jsIr.target_year);
    assertSummaryParity(rc.id, rc.summary, jsSum);
  }
  passedCount++;
}
console.log(`✅ T26 Parte A (Paridad IR + Cálculos Reales en ${parityVectors.real_cases.length} consultas): PASS`);

// 4. Secuencias conversacionales con memoria en JS (T4, T7, T8)
{
  const mem = new ActuarialEngine.MemoryManager();
  const ir1 = ActuarialEngine.parseQueryIR('Crea un resumen ejecutivo de Nuevo León y Jalisco para el año 2023', canonicalStates, mem);
  mem.updateConfirmedContext(ir1.states, ir1.target_year, ir1.intent);

  // T4: Año 2018 fuera de rango no altera memoria
  const irT4 = ActuarialEngine.parseQueryIR('Resumen de NL y Jalisco para 2018', canonicalStates, mem);
  assert.equal(irT4.intent, 'temporal_out_of_range');
  assert.equal(mem.confirmed_year, 2023);

  // T7: Continuación "¿Y el resumen de Puebla?" hereda 2023
  const irT7 = ActuarialEngine.parseQueryIR('¿Y el resumen de Puebla?', canonicalStates, mem);
  assert.equal(irT7.intent, 'executive_single_state_summary');
  assert.equal(irT7.target_year, 2023);
  assert.equal(irT7.year_source, 'memory');

  // T8: Consulta nueva sin marcador de continuación usa 2024 default
  const irT8 = ActuarialEngine.parseQueryIR('Resumen ejecutivo de Puebla', canonicalStates, mem);
  assert.equal(irT8.intent, 'executive_single_state_summary');
  assert.equal(irT8.target_year, 2024);
  assert.equal(irT8.year_source, 'default');
  passedCount += 3;
  console.log('✅ T26 Secuencias de memoria en JS (T4, T7, T8): PASS');
}

// 5. Prueba T26 (Parte B): Paridad sobre fixtures sintéticos T17–T24
for (const sc of parityVectors.synthetic_cases) {
  const jsSum = ActuarialEngine.computeExecutiveSummary(sc.dataset, sc.states, sc.target_year);
  assertSummaryParity(sc.id, sc.summary, jsSum);
  passedCount++;
}
console.log(`✅ T26 Parte B (Paridad en ${parityVectors.synthetic_cases.length} fixtures sintéticos T17–T24): PASS`);

console.log(`\n🎉 TODAS LAS PRUEBAS DE PARIDAD NODE <-> PYTHON (${passedCount} verificaciones) PASARON AL 100%.`);
