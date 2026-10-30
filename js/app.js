/* ==========================================================================
   Chubb Analytics — Executive Actuarial Dashboard Application Logic
   Dynamic Data Binding | MapLibre GL JS (WebGL) + INEGI Marco Geoestadístico
   ========================================================================== */

let rawData = null;
let filteredStates = [];
let selectedStateName = 'ALL';
let chartInstances = {};
let mapInstance = null;
let hoveredStateCve = null;

// Official INEGI State Code Mapping (Marco Geoestadístico 01-32)
const INEGI_CODE_MAP = {
  'Aguascalientes': '01', 'Baja California': '02', 'Baja California Sur': '03',
  'Campeche': '04', 'Coahuila': '05', 'Colima': '06', 'Chiapas': '07',
  'Chihuahua': '08', 'Ciudad de Mexico': '09', 'Durango': '10',
  'Guanajuato': '11', 'Guerrero': '12', 'Hidalgo': '13', 'Jalisco': '14',
  'Estado de Mexico': '15', 'Michoacan': '16', 'Morelos': '17', 'Nayarit': '18',
  'Nuevo Leon': '19', 'Oaxaca': '20', 'Puebla': '21', 'Queretaro': '22',
  'Quintana Roo': '23', 'San Luis Potosi': '24', 'Sinaloa': '25', 'Sonora': '26',
  'Tabasco': '27', 'Tamaulipas': '28', 'Tlaxcala': '29', 'Veracruz': '30',
  'Yucatan': '31', 'Zacatecas': '32'
};

// Alias Dictionary for Fuzzy State Matching in Chatbot
const STATE_ALIASES = {
  'cdmx': 'Ciudad de Mexico',
  'df': 'Ciudad de Mexico',
  'distrito federal': 'Ciudad de Mexico',
  'edomex': 'Estado de Mexico',
  'edo mex': 'Estado de Mexico',
  'estado mex': 'Estado de Mexico',
  'nl': 'Nuevo Leon',
  'nvo leon': 'Nuevo Leon',
  'nevo lion': 'Nuevo Leon',
  'slp': 'San Luis Potosi',
  'san luis': 'San Luis Potosi',
  'bc': 'Baja California',
  'bcs': 'Baja California Sur'
};

function normalizeStr(str) {
  return String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function levenshteinSimilarity(s1, s2) {
  const a = normalizeStr(s1);
  const b = normalizeStr(s2);
  if (a === b) return 1.0;
  if (a.length === 0 || b.length === 0) return 0.0;
  
  const matrix = [];
  for (let i = 0; i <= b.length; i++) matrix[i] = [i];
  for (let j = 0; j <= a.length; j++) matrix[0][j] = j;

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  const dist = matrix[b.length][a.length];
  return 1.0 - dist / Math.max(a.length, b.length);
}

// Traffic Light Severity Scale Mapping with Precise Brackets (Verde, Amarillo, Rojo)
function getSeverityColor(sevVal) {
  if (sevVal === null || sevVal === undefined || isNaN(sevVal)) return '#D1D5DB'; // Sin datos (Gris)
  if (sevVal >= 11000) return '#EF4444'; // Crítica: >= $11,000 MXN (Rojo carmesí)
  if (sevVal >= 7500) return '#F59E0B';  // Media: $7,500 a < $11,000 MXN (Amarillo / Ámbar)
  return '#10B981';                      // Baja: < $7,500 MXN (Verde esmeralda)
}

// 1. Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
  const errorBanner = document.getElementById('dataErrorBanner');
  try {
    const res = await fetch('data.json?t=' + Date.now());
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    rawData = await res.json();
    filteredStates = [...rawData.estados];
    
    if (errorBanner) errorBanner.classList.add('hidden');

    populateStateDropdown();

    // Check URL parameters for deep linking (e.g. ?year=2024&state=Jalisco)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('year')) {
      const y = urlParams.get('year');
      const selY = document.getElementById('selectYear');
      if (selY) selY.value = y;
    }
    if (urlParams.has('state')) {
      const s = urlParams.get('state');
      const selS = document.getElementById('selectState');
      if (selS) {
        selS.value = s;
        selectedStateName = s;
      }
    }

    updateNationalKPIs();
    updateStateFichaKPIs();
    initMapLibreMap();
    try { renderCharts(); } catch(e) { console.warn('Chart.js render warning:', e); }
    renderDataTable();
    setupEventListeners();
    setupScrollNavigationObserver();
  } catch (err) {
    console.error('Error al cargar data.json:', err);
    if (errorBanner) errorBanner.classList.remove('hidden');
  }
});

function populateStateDropdown() {
  const select = document.getElementById('selectState');
  if (!select) return;
  select.innerHTML = '<option value="ALL" selected>Nacional (32 Entidades)</option>';
  const sorted = [...rawData.estados].sort((a, b) => a.entidad.localeCompare(b.entidad));
  sorted.forEach(st => {
    const opt = document.createElement('option');
    opt.value = st.entidad;
    opt.textContent = st.entidad;
    select.appendChild(opt);
  });
}

// Helper: Calculate or retrieve national figures for any period ('ALL', '2020', '2021', '2022', '2023', '2024')
function getNationalMetricsForPeriod(year = 'ALL') {
  if (!rawData) return { natAvg: 6674.08, natMdp: 90373.46, label: 'Promedio 2020–2024' };
  
  if (year === 'ALL') {
    return {
      natAvg: rawData.metadata.promedio_nacional_severidad,
      natMdp: rawData.metadata.total_mdp_nacional_promedio,
      label: 'Promedio 2020–2024'
    };
  }

  const validStates = rawData.estados.filter(st => st.yearly_severidad && st.yearly_severidad[year] !== undefined && st.yearly_severidad[year] !== null && st.yearly_severidad[year] > 0);
  const avgSev = validStates.length > 0 
    ? validStates.reduce((acc, st) => acc + st.yearly_severidad[year], 0) / validStates.length
    : null;
  
  const totMdp = rawData.estados.reduce((acc, st) => {
    return acc + (st.yearly_mdp && st.yearly_mdp[year] ? st.yearly_mdp[year] : 0);
  }, 0);

  return {
    natAvg: avgSev,
    nValid: validStates.length,
    natMdp: totMdp,
    label: `Año ${year}`
  };
}

// Helper: Actuarial Risk Category based on severity value ($ MXN)
function getSeverityCategory(sevVal) {
  if (sevVal >= 11000) return 'Crítica';
  if (sevVal >= 7500) return 'Media';
  return 'Baja';
}

// Helper: Synchronized state metrics for a given period ('ALL' or specific year)
function getStateMetricsForPeriod(st, year = 'ALL') {
  if (!st) return null;
  const nat = getNationalMetricsForPeriod(year);
  
  let sev = st.severidad_promedio;
  let mdp = st.siniestros_ocurridos_mdp_promedio;
  let storedCat = st.categoria_severidad;
  let hasData = true;

  if (year !== 'ALL') {
    if (st.yearly_severidad && st.yearly_severidad[year] !== undefined && st.yearly_severidad[year] !== null) {
      sev = st.yearly_severidad[year];
    } else {
      sev = null;
      hasData = false;
    }
    if (st.yearly_mdp && st.yearly_mdp[year] !== undefined && st.yearly_mdp[year] !== null) {
      mdp = st.yearly_mdp[year];
    } else {
      mdp = null;
    }
    storedCat = st.yearly_categoria ? st.yearly_categoria[year] : null;
  }

  const diffAbs = (sev !== null && nat.natAvg !== null) ? (sev - nat.natAvg) : 0;
  const diffPct = (sev !== null && nat.natAvg) ? ((sev - nat.natAvg) / nat.natAvg) * 100 : 0;
  const relIndex = (sev !== null && nat.natAvg) ? (sev / nat.natAvg) * 100 : 0;
  const categoria = (sev !== null && storedCat) ? (storedCat === 'Critica' ? 'Crítica' : storedCat) : 'sin dato';

  return {
    entidad: st.entidad,
    year,
    periodLabel: nat.label,
    severidad: sev,
    mdp,
    diffAbs,
    diffPct,
    relIndex,
    hasData,
    cagr: st.cagr_2020_2024_pct,
    categoria: categoria,
    autos: st.automoviles_registrados,
    precioAuto: st.precio_promedio_auto_ml_k_mxn,
    costoAuto: st.costo_por_auto_registrado
  };
}

// 2. Update Resumen Nacional KPIs (Left Box)
function updateNationalKPIs() {
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const nat = getNationalMetricsForPeriod(selYear);

  const paretoTop5 = [...rawData.estados].sort((a, b) => {
    const mdpA = (selYear !== 'ALL' && a.yearly_mdp && a.yearly_mdp[selYear]) ? a.yearly_mdp[selYear] : a.siniestros_ocurridos_mdp_promedio;
    const mdpB = (selYear !== 'ALL' && b.yearly_mdp && b.yearly_mdp[selYear]) ? b.yearly_mdp[selYear] : b.siniestros_ocurridos_mdp_promedio;
    return mdpB - mdpA;
  }).slice(0, 5);

  const paretoTop5Sum = paretoTop5.reduce((sum, item) => {
    const mdpVal = (selYear !== 'ALL' && item.yearly_mdp && item.yearly_mdp[selYear]) ? item.yearly_mdp[selYear] : item.siniestros_ocurridos_mdp_promedio;
    return sum + mdpVal;
  }, 0);
  const paretoPct = (paretoTop5Sum / nat.natMdp) * 100;

  document.getElementById('kpiNatAvg').textContent = `$${nat.natAvg.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN`;
  document.getElementById('kpiNatMdp').textContent = `$${nat.natMdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP`;
  document.getElementById('kpiNatDriver').textContent = `r = +${rawData.scatter_stats.r_pearson.toFixed(4)}`;
  document.getElementById('kpiNatDriverSub').textContent = `Precio Auto ML (R² = ${(rawData.scatter_stats.r2_score * 100).toFixed(1)}%)`;
  document.getElementById('kpiNatPareto').textContent = `${paretoPct.toFixed(1)}%`;
}

// 3. Update Selected State Ficha KPIs (Right Box)
function updateStateFichaKPIs() {
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const boxTitle = document.getElementById('kpiStateBoxTitle');
  const sevEl = document.getElementById('kpiStateSev');
  const diffEl = document.getElementById('kpiStateDiff');
  const growthTitle = document.getElementById('kpiStateGrowthTitle');
  const growthEl = document.getElementById('kpiStateGrowth');
  const growthSubEl = document.getElementById('kpiStateGrowthSub');
  const costAutoEl = document.getElementById('kpiStateCostAuto');
  const badgeEl = document.getElementById('kpiStateBadge');
  const mdpSub = document.getElementById('kpiStateMdpSub');

  if (selectedStateName === 'ALL') {
    boxTitle.textContent = 'Ficha del Estado (Sin Selección)';
    sevEl.innerHTML = '<span style="font-size:1.05rem; color:#64748B; font-weight:600;">Selecciona un estado</span>';
    diffEl.textContent = 'Haz clic en el mapa o selector superior';
    growthTitle.textContent = 'Mayor Crecimiento (2020–2024)';
    const maxGrowth = [...rawData.estados].sort((a, b) => b.cagr_2020_2024_pct - a.cagr_2020_2024_pct)[0];
    const maxCagrAnnual = maxGrowth ? (Math.pow(1 + maxGrowth.cagr_2020_2024_pct / 100, 1/4) - 1) * 100 : 0;
    growthEl.textContent = maxGrowth ? `+${maxGrowth.cagr_2020_2024_pct.toFixed(1)}%` : '-';
    if (growthSubEl) {
      growthSubEl.innerHTML = maxGrowth 
        ? `<strong>${maxGrowth.entidad}</strong> · +${maxCagrAnnual.toFixed(1)}% anual compuesto` 
        : 'incremento acumulado';
    }
    costAutoEl.innerHTML = '<span style="font-size:1.05rem; color:#64748B; font-weight:600;">Selecciona un estado</span>';
    badgeEl.innerHTML = '<span class="badge" style="background:#E2E8F0; color:#475569; border:1px solid #CBD5E1;">Vista Nacional</span>';
    if (mdpSub) mdpSub.textContent = '32 entidades vinculadas';

    // Side Ficha Panel Reset
    const fc = document.getElementById('fichaCategoria');
    if (fc) fc.innerHTML = '<span class="badge" style="background:#E2E8F0; color:#475569; border:1px solid #CBD5E1;">Vista Nacional</span>';
    document.getElementById('fichaStateName').textContent = 'Selecciona un Estado';
    document.getElementById('fichaSev').textContent = 'Selecciona un estado';
    document.getElementById('fichaDiff').textContent = 'Selecciona un estado';
    document.getElementById('fichaIndex').textContent = 'Selecciona un estado';
    document.getElementById('fichaMdp').textContent = 'Selecciona un estado';
    document.getElementById('fichaAutos').textContent = 'Selecciona un estado';
    document.getElementById('fichaPrecioAuto').textContent = 'Selecciona un estado';
    return;
  }

  const st = rawData.estados.find(s => s.entidad === selectedStateName);
  if (!st) return;

  const met = getStateMetricsForPeriod(st, selYear);

  if (!met.hasData || met.severidad === null || met.severidad === undefined || isNaN(met.severidad)) {
    boxTitle.textContent = `Ficha de ${st.entidad}`;
    sevEl.textContent = 'Sin datos disponibles';
    diffEl.textContent = `Sin información para el periodo ${selYear}`;
    growthTitle.textContent = `Crecimiento ${st.entidad}`;
    growthEl.textContent = 'Sin datos';
    if (growthSubEl) growthSubEl.textContent = 'Sin datos disponibles';
    costAutoEl.textContent = 'Sin datos';
    badgeEl.innerHTML = '<span class="badge" style="background:#D1D5DB; color:#374151; border:1px solid #9CA3AF;">Sin datos</span>';

    document.getElementById('fichaStateName').textContent = st.entidad;
    document.getElementById('fichaSev').textContent = 'Sin datos disponibles';
    document.getElementById('fichaDiff').textContent = 'Sin información para este periodo';
    document.getElementById('fichaIndex').textContent = 'Sin datos';
    document.getElementById('fichaMdp').textContent = 'Sin datos';
    document.getElementById('fichaAutos').textContent = `${st.automoviles_registrados ? st.automoviles_registrados.toLocaleString('es-MX') + ' autos' : 'Sin datos'}`;
    document.getElementById('fichaPrecioAuto').textContent = 'Sin datos';
    return;
  }

  const diffStr = met.diffPct >= 0 
    ? `+${met.diffPct.toFixed(1)}% vs Nacional (${met.periodLabel})` 
    : `${met.diffPct.toFixed(1)}% vs Nacional (${met.periodLabel})`;

  boxTitle.textContent = `Ficha de ${st.entidad}`;
  sevEl.textContent = `$${met.severidad.toLocaleString('es-MX', {minimumFractionDigits: 2, maximumFractionDigits: 2})} MXN`;
  diffEl.textContent = diffStr;
  growthTitle.textContent = `Crecimiento ${st.entidad} (2020–2024)`;
  const stCagrAnnual = (Math.pow(1 + st.cagr_2020_2024_pct / 100, 1/4) - 1) * 100;
  growthEl.textContent = `+${st.cagr_2020_2024_pct.toFixed(1)}%`;
  if (growthSubEl) {
    growthSubEl.textContent = `Acumulado · +${stCagrAnnual.toFixed(1)}% anual compuesto`;
  }
  costAutoEl.textContent = `$${st.costo_por_auto_registrado.toLocaleString('es-MX', {maximumFractionDigits: 0})} MXN`;
  badgeEl.innerHTML = `<span class="badge badge-${normalizeStr(met.categoria)}">${met.categoria}</span>`;
  if (mdpSub) mdpSub.textContent = `$${met.mdp.toLocaleString('es-MX', {minimumFractionDigits: 2, maximumFractionDigits: 2})} MDP (${met.periodLabel})`;

  // Update Side Ficha Panel (Totalmente unificado con periodo)
  const fc = document.getElementById('fichaCategoria');
  if (fc) fc.innerHTML = `<span class="badge badge-${normalizeStr(met.categoria)}">${met.categoria} (${met.periodLabel})</span>`;
  document.getElementById('fichaStateName').textContent = st.entidad;
  document.getElementById('fichaSev').textContent = `$${met.severidad.toLocaleString('es-MX', {minimumFractionDigits: 2, maximumFractionDigits: 2})} MXN`;
  document.getElementById('fichaDiff').textContent = diffStr;
  document.getElementById('fichaIndex').textContent = `${met.relIndex.toFixed(1)} pts (Base Nacional ${met.periodLabel}=100)`;
  document.getElementById('fichaMdp').textContent = `$${met.mdp.toLocaleString('es-MX', {minimumFractionDigits: 2, maximumFractionDigits: 2})} MDP (${met.periodLabel})`;
  document.getElementById('fichaAutos').textContent = `${st.automoviles_registrados ? st.automoviles_registrados.toLocaleString('es-MX') + ' autos' : '-'}`;
  document.getElementById('fichaPrecioAuto').textContent = `$${st.precio_promedio_auto_ml_k_mxn.toFixed(0)}k MXN`;
}

// 4. MapLibre GL JS (WebGL Vector Engine) + INEGI Marco Geoestadístico Integration
function initMapLibreMap() {
  const container = document.getElementById('maplibreContainer');
  if (!container) return;

  if (typeof maplibregl === 'undefined') {
    console.warn('MapLibre GL JS not loaded; falling back to tabular and filter interface.');
    container.innerHTML = '<div style="padding:40px; text-align:center; color:#64748B;">Mapa interactivo WebGL en inicialización. Utiliza el selector de estado o la tabla para consultar las entidades.</div>';
    return;
  }

  // Create WebGL Map instance with local clean flat style (no external tile server needed)
  mapInstance = new maplibregl.Map({
    container: 'maplibreContainer',
    style: {
      version: 8,
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      sources: {
        'mexico-states': {
          type: 'geojson',
          data: 'data/mexico_estados.geojson',
          promoteId: 'cve_ent'
        }
      },
      layers: [
        {
          id: 'background',
          type: 'background',
          paint: {
            'background-color': '#F8FAFC'
          }
        },
        {
          id: 'states-fill',
          type: 'fill',
          source: 'mexico-states',
          paint: {
            'fill-color': '#10B981',
            'fill-opacity': 1.0 // Totalmente opaco (sin transparencias)
          }
        },
        {
          id: 'states-borders',
          type: 'line',
          source: 'mexico-states',
          paint: {
            'line-color': '#64748B', // Trazo fino visible de 1px
            'line-width': 1.0
          }
        },
        {
          id: 'states-selected-border',
          type: 'line',
          source: 'mexico-states',
          paint: {
            'line-color': '#0F172A', // Contorno oscuro marcado al seleccionar
            'line-width': [
              'case',
              ['boolean', ['feature-state', 'selected'], false],
              2.8,
              0.0
            ]
          }
        },
        {
          id: 'states-labels',
          type: 'symbol',
          source: 'mexico-states',
          minzoom: 5.5,
          layout: {
            'text-field': ['get', 'name'],
            'text-size': 11.5,
            'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
            'text-anchor': 'center',
            'text-allow-overlap': false
          },
          paint: {
            'text-color': '#0F172A',
            'text-halo-color': '#FFFFFF',
            'text-halo-width': 1.8
          }
        }
      ]
    },
    center: [-102.0, 23.8],
    zoom: 3.85,
    minZoom: 3.2,
    maxZoom: 11,
    dragRotate: false,
    pitchWithRotate: false
  });

  mapInstance.on('load', async () => {
    try {
      const geoRes = await fetch('data/mexico_estados.geojson');
      if (geoRes.ok) {
        const geoData = await geoRes.json();
        computeGeoJsonBounds(geoData);
      }
    } catch (e) {
      console.warn('GeoJSON bounds warning:', e);
    }
    updateMapColors();
    setupMapInteractions();
    fitMapToMexico();
  });
}

let geojsonBounds = [[-118.366, 14.535], [-86.724, 32.718]];

function computeGeoJsonBounds(geoData) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  function scan(coords) {
    if (typeof coords[0] === 'number') {
      const [x, y] = coords;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    } else {
      coords.forEach(scan);
    }
  }
  if (geoData && geoData.features) {
    geoData.features.forEach(f => scan(f.geometry.coordinates));
    geojsonBounds = [[minX, minY], [maxX, maxY]];
  }
}

function fitMapToMexico() {
  if (!mapInstance) return;
  mapInstance.resize();
  const container = document.getElementById('maplibreContainer');
  const w = container ? container.clientWidth : 800;
  const h = container ? container.clientHeight : 480;

  // Responsive padding ensuring Baja California (NW) and Yucatan / Quintana Roo (SE) are completely visible
  // and never clipped or covered by the .map-nav-toolbar at (top: 12px, left: 12px)
  const padTop = Math.max(55, Math.floor(h * 0.12));
  const padBottom = Math.max(25, Math.floor(h * 0.06));
  const padLeft = Math.max(35, Math.floor(w * 0.05));
  const padRight = Math.max(35, Math.floor(w * 0.05));

  const bounds = geojsonBounds || [[-118.5, 14.3], [-86.5, 32.85]];

  try {
    mapInstance.fitBounds(bounds, {
      padding: { top: padTop, bottom: padBottom, left: padLeft, right: padRight },
      duration: 600,
      linear: false
    });
  } catch (e) {
    console.warn('fitBounds warning:', e);
  }
}

function updateMapColors() {
  if (!mapInstance || !mapInstance.isStyleLoaded() || !rawData) return;
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';

  // Build MapLibre match expression based on official INEGI 'cve_ent' codes
  const matchExpr = ['match', ['get', 'cve_ent']];
  const missingStates = [];

  rawData.estados.forEach(st => {
    let val = st.severidad_promedio;
    if (selYear !== 'ALL') {
      if (st.yearly_severidad && st.yearly_severidad[selYear] !== undefined) {
        val = st.yearly_severidad[selYear];
      } else {
        val = null;
      }
    }
    if (val === null || val === undefined || isNaN(val)) {
      missingStates.push(st);
    }
    const color = getSeverityColor(val);
    matchExpr.push(st.cve_ent, color);
  });
  matchExpr.push('#D1D5DB'); // Fallback Sin datos (Gris neutral)

  mapInstance.setPaintProperty('states-fill', 'fill-color', matchExpr);
  updateMapSelectionState();

  // Control dinámico de "Sin datos" en la leyenda (Ocultar si hay cobertura 100% para evitar ruido):
  const legendSinDatos = document.getElementById('legendSinDatos');
  const legendSinDatosText = document.getElementById('legendSinDatosText');
  if (legendSinDatos) {
    if (missingStates.length > 0) {
      legendSinDatos.style.display = 'inline-flex';
      if (legendSinDatosText) {
        legendSinDatosText.textContent = `Sin datos: ${missingStates.length} ${missingStates.length === 1 ? 'estado' : 'estados'}`;
      }
      legendSinDatos.style.cursor = 'pointer';
      legendSinDatos.title = `Clic para consultar entidades sin información: ${missingStates.map(s => s.entidad).join(', ')}`;
      legendSinDatos.onclick = () => {
        alert(`Entidades sin datos para el periodo (${selYear === 'ALL' ? 'Promedio 2020–2024' : 'Año ' + selYear}):\n\n• ` + missingStates.map(s => s.entidad).join('\n• '));
      };
    } else {
      legendSinDatos.style.display = 'none';
      legendSinDatos.onclick = null;
    }
  }
}

function updateMapSelectionState() {
  if (!mapInstance || !mapInstance.isStyleLoaded() || !rawData) return;
  rawData.estados.forEach(st => {
    const isSelected = (st.entidad === selectedStateName);
    mapInstance.setFeatureState(
      { source: 'mexico-states', id: st.cve_ent },
      { selected: isSelected }
    );
  });
}

function setupMapInteractions() {
  const tooltip = document.getElementById('mapTooltip');
  const mapWrapper = document.getElementById('mapWrapper');

  // Mouse Move Tooltip
  mapInstance.on('mousemove', 'states-fill', (e) => {
    if (e.features.length > 0) {
      mapInstance.getCanvas().style.cursor = 'pointer';
      const feat = e.features[0];
      const cve = feat.properties.cve_ent;
      const st = rawData.estados.find(s => s.cve_ent === cve || s.entidad === feat.properties.name);

      if (st && tooltip) {
        const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
        const met = getStateMetricsForPeriod(st, selYear);
        const diffStr = met.diffPct >= 0 ? `+${met.diffPct.toFixed(1)}%` : `${met.diffPct.toFixed(1)}%`;

        tooltip.innerHTML = `<strong>${st.entidad}</strong> · <span class="badge badge-${normalizeStr(met.categoria)}">${met.categoria}</span><br/>
          Severidad: <strong>$${met.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN</strong><br/>
          Diferencia vs Nacional: ${diffStr} (${met.periodLabel})`;
        
        const x = e.point.x + 14;
        const y = e.point.y + 14;
        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
        tooltip.classList.remove('hidden');
      }
    }
  });

  mapInstance.on('mouseleave', 'states-fill', () => {
    mapInstance.getCanvas().style.cursor = '';
    if (tooltip) tooltip.classList.add('hidden');
  });

  // State Click Event
  mapInstance.on('click', 'states-fill', (e) => {
    if (e.features.length > 0) {
      const feat = e.features[0];
      const cve = feat.properties.cve_ent;
      const st = rawData.estados.find(s => s.cve_ent === cve || s.entidad === feat.properties.name);
      if (st) {
        const sel = document.getElementById('selectState');
        if (sel) sel.value = st.entidad;
        selectedStateName = st.entidad;
        triggerGlobalFilter();
      }
    }
  });

  // Toolbar Navigation Controls
  const btnZoomIn = document.getElementById('btnMapZoomIn');
  const btnZoomOut = document.getElementById('btnMapZoomOut');
  const btnReset = document.getElementById('btnMapReset');
  const btnCenter = document.getElementById('btnMapCenter');

  if (btnZoomIn) btnZoomIn.addEventListener('click', () => mapInstance.zoomIn());
  if (btnZoomOut) btnZoomOut.addEventListener('click', () => mapInstance.zoomOut());
  if (btnReset) btnReset.addEventListener('click', fitMapToMexico);

  if (btnCenter) {
    btnCenter.addEventListener('click', () => {
      // Smoothly zoom in to Central Mexico (CDMX, Edomex, Morelos, Tlaxcala, Puebla, Hidalgo, Queretaro)
      mapInstance.flyTo({ center: [-99.1332, 19.4326], zoom: 7.3, essential: true });
    });
  }
}

// 5. Render Charts (Clean Light Theme Styling)
function renderCharts() {
  const textColor = '#0F172A';
  const subtextColor = '#475569';
  const gridColor = 'rgba(15, 23, 42, 0.08)';

  // Chart 1: Diagrama Pareto Real
  const sortedPareto = [...filteredStates].sort((a, b) => b.siniestros_ocurridos_mdp_promedio - a.siniestros_ocurridos_mdp_promedio);
  let cum = 0;
  const totMdp = sortedPareto.reduce((sum, item) => sum + item.siniestros_ocurridos_mdp_promedio, 0);
  const paretoLabels = sortedPareto.slice(0, 10).map(s => s.entidad);
  const paretoMdp = sortedPareto.slice(0, 10).map(s => s.siniestros_ocurridos_mdp_promedio);
  const paretoCum = sortedPareto.slice(0, 10).map(s => {
    cum += s.siniestros_ocurridos_mdp_promedio;
    return (cum / totMdp) * 100;
  });

  const paretoCanvas = document.getElementById('chartPareto');
  if (paretoCanvas) {
    if (chartInstances.pareto) chartInstances.pareto.destroy();
    chartInstances.pareto = new Chart(paretoCanvas, {
      type: 'bar',
      data: {
        labels: paretoLabels,
        datasets: [
          { label: 'Costo Ocurrido (MDP)', data: paretoMdp, backgroundColor: '#1D4ED8', borderRadius: 4, yAxisID: 'y' },
          { label: '% Acumulado Pareto', data: paretoCum, type: 'line', borderColor: '#DC2626', borderWidth: 2.5, pointBackgroundColor: '#DC2626', pointRadius: 4, yAxisID: 'y1' }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { type: 'linear', position: 'left', title: { display: true, text: 'Costo (MDP)', color: subtextColor }, grid: { color: gridColor }, ticks: { color: subtextColor } },
          y1: { type: 'linear', position: 'right', min: 0, max: 100, title: { display: true, text: '% Acumulado', color: subtextColor }, grid: { drawOnChartArea: false }, ticks: { color: subtextColor } },
          x: { ticks: { color: subtextColor }, grid: { color: gridColor } }
        },
        plugins: { legend: { labels: { color: textColor, font: { weight: '600' } } } }
      }
    });
  }

  // Chart 2: Scatter Plot (Precio del vehículo y severidad)
  const scatterCanvas = document.getElementById('chartScatter');
  if (scatterCanvas) {
    const scatterPoints = filteredStates.map(s => ({ x: s.precio_promedio_auto_ml_k_mxn, y: s.severidad_promedio, label: s.entidad }));
    const regLine = [
      { x: 200, y: rawData.scatter_stats.slope * 200 + rawData.scatter_stats.intercept },
      { x: 350, y: rawData.scatter_stats.slope * 350 + rawData.scatter_stats.intercept }
    ];

    if (chartInstances.scatter) chartInstances.scatter.destroy();
    chartInstances.scatter = new Chart(scatterCanvas, {
      type: 'scatter',
      data: {
        datasets: [
          { label: 'Estados (32 Entidades)', data: scatterPoints, backgroundColor: '#2563EB', pointRadius: 6 },
          { label: 'Regresión Lineal (r = +0.8488)', data: regLine, type: 'line', borderColor: '#DC2626', borderWidth: 2, pointRadius: 0 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { title: { display: true, text: 'Precio Promedio Auto ($k MXN)', color: subtextColor }, grid: { color: gridColor }, ticks: { color: subtextColor } },
          y: { title: { display: true, text: 'Severidad ($ MXN)', color: subtextColor }, grid: { color: gridColor }, ticks: { color: subtextColor } }
        },
        plugins: { legend: { labels: { color: textColor, font: { weight: '600' } } } }
      }
    });
  }

  // Chart 3: Time Series Trend Line Chart (2020-2024)
  const trendCanvas = document.getElementById('chartTrend');
  if (trendCanvas) {
    const top5Names = ['Nuevo Leon', 'Sinaloa', 'Queretaro', 'Ciudad de Mexico', 'Jalisco'];
    const years = ['2020', '2021', '2022', '2023', '2024'];
    const colorsList = ['#DC2626', '#D97706', '#1D4ED8', '#059669', '#7C3AED', '#2563EB'];
    
    let trendStates = rawData.estados.filter(s => top5Names.includes(s.entidad));
    if (selectedStateName !== 'ALL' && !top5Names.includes(selectedStateName)) {
      const customSt = rawData.estados.find(s => s.entidad === selectedStateName);
      if (customSt) trendStates.push(customSt);
    }

    const trendDatasets = trendStates.map((st, idx) => ({
      label: st.entidad,
      data: years.map(y => st.yearly_severidad[y]),
      borderColor: colorsList[idx % colorsList.length],
      borderWidth: selectedStateName === st.entidad ? 4 : 2,
      fill: false,
      tension: 0.2
    }));

    const trendTitle = document.getElementById('trendChartTitle');
    if (trendTitle) {
      trendTitle.textContent = selectedStateName !== 'ALL' ? `Tendencia de Severidad de ${selectedStateName} (2020–2024)` : 'Tendencia de Severidad (2020–2024)';
    }

    if (chartInstances.trend) chartInstances.trend.destroy();
    chartInstances.trend = new Chart(trendCanvas, {
      type: 'line',
      data: { labels: years, datasets: trendDatasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: subtextColor }, grid: { color: gridColor } },
          y: { ticks: { color: subtextColor }, grid: { color: gridColor } }
        },
        plugins: { legend: { labels: { color: textColor, font: { weight: '600' } } } }
      }
    });
  }
}

// Global sorting state
let currentSortCol = 'entidad';
let currentSortAsc = true;

// 6. Render Data Table with Column Sorting & Tabular Right Aligned Numbers
function renderDataTable() {
  const tbody = document.getElementById('tableBody');
  if (!tbody || !rawData) return;
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const nat = getNationalMetricsForPeriod(selYear);

  // Dynamic header labels to match active filter period and show sort indicators
  const sortHeaders = [
    { id: 'thTableSev', col: 'severidad', base: selYear === 'ALL' ? 'Severidad Promedio (MXN)' : `Severidad ${selYear} (MXN)` },
    { id: 'thTableIndex', col: 'relIndex', base: selYear === 'ALL' ? 'Índice Relativo' : `Índice ${selYear}` },
    { id: 'thTableCagr', col: 'cagr_2020_2024_pct', base: 'Crecimiento Acumulado' },
    { id: 'thTableMdp', col: 'mdp', base: selYear === 'ALL' ? 'Costo Total (MDP)' : `Costo Total ${selYear} (MDP)` }
  ];

  document.querySelectorAll('#statesTable thead th[data-sort]').forEach(th => {
    const col = th.getAttribute('data-sort');
    let label = th.getAttribute('data-base-label');
    if (!label) {
      const match = sortHeaders.find(h => h.col === col);
      label = match ? match.base : th.textContent.replace(/[⇕▲▼]/g, '').trim();
      th.setAttribute('data-base-label', label);
    }
    const match = sortHeaders.find(h => h.col === col);
    if (match) label = match.base;

    if (col === currentSortCol) {
      th.classList.add('sorted-active');
      th.innerHTML = `${label} ${currentSortAsc ? '▲' : '▼'}`;
    } else {
      th.classList.remove('sorted-active');
      th.innerHTML = `${label} ⇕`;
    }
  });

  // Sort filteredStates according to currentSortCol and currentSortAsc
  const sortedRows = [...filteredStates].sort((a, b) => {
    const metA = getStateMetricsForPeriod(a, selYear);
    const metB = getStateMetricsForPeriod(b, selYear);
    let valA, valB;

    if (currentSortCol === 'entidad') {
      valA = a.entidad;
      valB = b.entidad;
      return currentSortAsc ? valA.localeCompare(valB, 'es') : valB.localeCompare(valA, 'es');
    } else if (currentSortCol === 'severidad') {
      valA = metA.severidad;
      valB = metB.severidad;
    } else if (currentSortCol === 'relIndex') {
      valA = metA.relIndex;
      valB = metB.relIndex;
    } else if (currentSortCol === 'cagr_2020_2024_pct') {
      valA = a.cagr_2020_2024_pct;
      valB = b.cagr_2020_2024_pct;
    } else if (currentSortCol === 'costo_por_auto_registrado') {
      valA = a.costo_por_auto_registrado;
      valB = b.costo_por_auto_registrado;
    } else if (currentSortCol === 'mdp') {
      valA = metA.mdp;
      valB = metB.mdp;
    } else if (currentSortCol === 'categoria_severidad') {
      valA = metA.severidad;
      valB = metB.severidad;
    } else {
      valA = a.entidad;
      valB = b.entidad;
      return currentSortAsc ? valA.localeCompare(valB, 'es') : valB.localeCompare(valA, 'es');
    }

    if (valA === valB) return a.entidad.localeCompare(b.entidad, 'es');
    return currentSortAsc ? (valA - valB) : (valB - valA);
  });

  tbody.innerHTML = '';
  
  sortedRows.forEach(st => {
    const met = getStateMetricsForPeriod(st, selYear);
    const cagrAnual = (Math.pow(1 + st.cagr_2020_2024_pct / 100, 1/4) - 1) * 100;
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    tr.title = `Clic para seleccionar ${st.entidad}`;
    tr.onclick = () => window.selectStateInDashboard(st.entidad);

    tr.innerHTML = `
      <td><strong>${st.entidad}</strong></td>
      <td class="text-right">$${met.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
      <td class="text-right">${met.relIndex.toFixed(1)} pts</td>
      <td class="text-right" style="color:${st.cagr_2020_2024_pct > 100 ? '#991B1B' : '#0F172A'};" title="CAGR Anual: +${cagrAnual.toFixed(1)}% anual">+${st.cagr_2020_2024_pct.toFixed(1)}%</td>
      <td class="text-right">$${st.costo_por_auto_registrado.toLocaleString('es-MX', {maximumFractionDigits:0})}</td>
      <td class="text-right">$${met.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP</td>
      <td class="text-right"><span class="badge badge-${normalizeStr(met.categoria)}">${met.categoria}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// 7. Global Filter Event Handler & Reset
function triggerGlobalFilter() {
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  selectedStateName = document.getElementById('selectState') ? document.getElementById('selectState').value : 'ALL';
  const searchText = document.getElementById('tableSearchInput') ? normalizeStr(document.getElementById('tableSearchInput').value) : '';

  // Update Context Badge
  const badge = document.getElementById('activeContextBadge');
  if (badge) {
    const yearText = selYear === 'ALL' ? 'Promedio 2020–2024' : `Año ${selYear}`;
    const stateText = selectedStateName === 'ALL' ? 'Nacional' : selectedStateName;
    badge.textContent = `${stateText} · ${yearText}`;
  }

  filteredStates = rawData.estados.filter(st => {
    const matchState = (selectedStateName === 'ALL' || st.entidad === selectedStateName);
    const matchSearch = (searchText === '' || normalizeStr(st.entidad).includes(searchText));
    return matchState && matchSearch;
  });

  updateNationalKPIs();
  updateStateFichaKPIs();
  updateMapColors();
  try { renderCharts(); } catch(e) { console.warn('Chart render warning:', e); }
  renderDataTable();
}

function resetAllFilters() {
  const selYear = document.getElementById('selectYear');
  const selState = document.getElementById('selectState');
  const searchInput = document.getElementById('tableSearchInput');

  if (selYear) selYear.value = 'ALL';
  if (selState) selState.value = 'ALL';
  if (searchInput) searchInput.value = '';
  
  selectedStateName = 'ALL';
  triggerGlobalFilter();
  updateChatContextPill();

  if (mapInstance) {
    mapInstance.flyTo({ center: [-102.5, 23.6], zoom: 4.4, essential: true });
  }
}

// Scroll Navigation Tab Active State Observer
function setupScrollNavigationObserver() {
  const sections = document.querySelectorAll('section[id], div.dashboard-card[id]');
  const navLinks = document.querySelectorAll('.nav-link');

  window.addEventListener('scroll', () => {
    let currentSectionId = '';
    const scrollPosition = window.scrollY + 120;

    sections.forEach(section => {
      if (scrollPosition >= section.offsetTop) {
        currentSectionId = section.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === `#${currentSectionId}`) {
        link.classList.add('active');
      }
    });
  });
}

// 8. AI Assistant Chatbot Logic with Conversational Context & Grounded Verification
let chatMemory = {
  mode: 'none', // 'single', 'comparison', 'glossary', 'chart', 'summary'
  lastStates: [],
  lastYear: 'ALL',
  lastTopic: 'severidad',
  lastResponseText: ''
};
let engineMemory = (typeof window !== 'undefined' && window.ActuarialEngine)
  ? new window.ActuarialEngine.MemoryManager()
  : null;

function updateChatContextPill() {
  const pill = document.getElementById('chatContextPill');
  if (!pill) return;
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const yearStr = selYear === 'ALL' ? 'Promedio 2020–2024' : `Año ${selYear}`;
  const stateStr = selectedStateName === 'ALL' ? 'Nacional' : selectedStateName;
  pill.textContent = `${stateStr} · ${yearStr}`;
}

function renderWelcomeMessage() {
  const msgContainer = document.getElementById('chatMessages');
  if (!msgContainer) return;
  msgContainer.innerHTML = `
    <div class="chat-msg-bot">
      👋 <strong>¡Hola! Soy tu Asistente de análisis actuarial.</strong><br/><br/>
      Puedo ayudarte a consultar de manera verificable:<br/>
      • <strong>Severidad por estado ($ MXN)</strong> y nivel de riesgo.<br/>
      • <strong>Desglose por año (2020–2024)</strong> e incrementos acumulados.<br/>
      • <strong>Rankings de siniestralidad</strong> y concentración Pareto en MDP.<br/>
      • <strong>Variables de impacto</strong> (Precios Mercado Libre, motorización INEGI).<br/><br/>
      <em>Pregúntame algo como: "¿Cuál es la severidad de Nuevo León?", "Compara Nuevo León y Jalisco en el promedio 2020–2024" o "¿Y en 2024?".</em>
    </div>
  `;
}

// Global Helper functions for chat action buttons (supporting state and target year synchronization)
window.selectStateInDashboard = function(stName, targetYear = null) {
  if (targetYear) {
    const selYear = document.getElementById('selectYear');
    if (selYear) selYear.value = targetYear;
  }
  const sel = document.getElementById('selectState');
  if (sel) sel.value = stName;
  selectedStateName = stName;
  triggerGlobalFilter();
  updateChatContextPill();
  const mapSec = document.getElementById('secMapa');
  if (mapSec) mapSec.scrollIntoView({ behavior: 'smooth' });
};

window.highlightAndScrollToTable = function(stName, targetYear = null) {
  if (targetYear) {
    const selYear = document.getElementById('selectYear');
    if (selYear) selYear.value = targetYear;
  }
  const searchInput = document.getElementById('tableSearchInput');
  if (searchInput) searchInput.value = stName;
  triggerGlobalFilter();
  updateChatContextPill();
  const tableSec = document.getElementById('secDatos');
  if (tableSec) tableSec.scrollIntoView({ behavior: 'smooth' });
};

// Global Helper to trigger chart explanation in Assistant
window.explainChartInChat = function(chartType) {
  const chatBox = document.getElementById('chatWindow');
  if (chatBox) chatBox.classList.remove('hidden');

  let queryText = '';
  if (chartType === 'pareto') queryText = 'Explicar barras, línea y ejes de Pareto';
  else if (chartType === 'scatter') queryText = 'Explicar R² y el 72.05%';
  else if (chartType === 'trend') queryText = 'Explicar tendencia histórica de severidad';
  else if (chartType === 'map') queryText = 'Explicar mapa de severidad por estado';

  const input = document.getElementById('chatInput');
  if (input) input.value = queryText;
  handleUserChatMessage();
};

function handleUserChatMessage() {
  const input = document.getElementById('chatInput');
  const query = input.value.trim();
  if (!query) return;

  addChatMessage(query, 'user');
  input.value = '';

  // Show Loading indicator
  const msgContainer = document.getElementById('chatMessages');
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'chat-loading';
  loadingDiv.id = 'chatLoadingIndicator';
  loadingDiv.innerHTML = `⏳ <span>Consultando datos del reporte...</span>`;
  msgContainer.appendChild(loadingDiv);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  setTimeout(() => {
    const loading = document.getElementById('chatLoadingIndicator');
    if (loading) loading.remove();

    const response = processAIIntent(query);
    chatMemory.lastResponseText = response;
    addChatMessage(response, 'bot');
  }, 350);
}

function addChatMessage(text, sender) {
  const msgContainer = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = sender === 'user' ? 'chat-msg-user' : 'chat-msg-bot';
  div.innerHTML = text.replace(/\n/g, '<br/>');
  msgContainer.appendChild(div);
  msgContainer.scrollTop = msgContainer.scrollHeight;
}

// Helper: Extract N distinct states mentioned in query preserving appearance order
function extractStatesFromQuery(query) {
  if (typeof window !== 'undefined' && window.ActuarialEngine) {
    const canonical = (rawData && rawData.estados) ? rawData.estados.map(s => s.entidad) : null;
    return window.ActuarialEngine.extractStatesDetailed(query, canonical).states;
  }
  const norm = normalizeStr(query);
  const matches = [];
  for (const [alias, realName] of Object.entries(STATE_ALIASES)) {
    const regex = new RegExp(`\\b${alias}\\b`, 'gi');
    let m;
    while ((m = regex.exec(norm)) !== null) {
      matches.push({ name: realName, index: m.index });
    }
  }
  if (rawData && rawData.estados) {
    for (const st of rawData.estados) {
      const normEnt = normalizeStr(st.entidad);
      let idx = norm.indexOf(normEnt);
      if (idx !== -1) {
        matches.push({ name: st.entidad, index: idx });
      }
    }
  }
  matches.sort((a, b) => a.index - b.index);
  const result = [];
  for (const m of matches) {
    if (!result.includes(m.name)) {
      result.push(m.name);
    }
  }
  return result;
}

// 1. Chart Explanation: Pareto
function generateParetoExplanation() {
  const sortedMdp = [...rawData.estados].sort((a, b) => b.siniestros_ocurridos_mdp_promedio - a.siniestros_ocurridos_mdp_promedio);
  const top5 = sortedMdp.slice(0, 5);
  const sumTop5 = top5.reduce((sum, s) => sum + s.siniestros_ocurridos_mdp_promedio, 0);
  const totNatMdp = rawData.metadata.total_mdp_nacional_promedio;
  const top5Pct = (sumTop5 / totNatMdp) * 100;

  return `🤖 <strong>Asistente de análisis actuarial — Diagrama de Pareto</strong><br/><br/>
<strong>1. Qué mide:</strong><br/>
Mide la concentración del volumen total de costo ocurrido por siniestros de auto (en Millones de Pesos, MDP) distribuido entre las 32 entidades federativas.<br/><br/>
<strong>2. Cómo leer sus ejes y colores:</strong><br/>
• <strong>Eje horizontal (X):</strong> Entidades federativas ordenadas de mayor a menor según su costo total acumulado en MDP (volumen agregado).<br/>
• <strong>Eje vertical izquierdo (Barras azules):</strong> Costo total ocurrido en MDP de cada entidad federativa.<br/>
• <strong>Eje vertical derecho (Línea continua):</strong> Porcentaje acumulado respecto al costo nacional total (curva de concentración de 0% a 100%).<br/><br/>
<strong>3. Hallazgo clave con cifras exactas del reporte:</strong><br/>
• <strong>El Top 5 de entidades concentra el ${top5Pct.toFixed(1)}% del costo nacional total en MDP</strong> ($${sumTop5.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP de los $${totNatMdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP anuales).<br/>
• Corresponde estrictamente al <strong>ranking de volumen agregado en MDP</strong> (no al de severidad unitaria): <strong>${top5[0].entidad} ($${top5[0].siniestros_ocurridos_mdp_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP, ${top5[0].pct_costo_nacional.toFixed(1)}%)</strong>, <strong>${top5[1].entidad} ($${top5[1].siniestros_ocurridos_mdp_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP, ${top5[1].pct_costo_nacional.toFixed(1)}%)</strong>, <strong>${top5[2].entidad} ($${top5[2].siniestros_ocurridos_mdp_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP, ${top5[2].pct_costo_nacional.toFixed(1)}%)</strong>, <strong>${top5[3].entidad} ($${top5[3].siniestros_ocurridos_mdp_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP, ${top5[3].pct_costo_nacional.toFixed(1)}%)</strong> y <strong>${top5[4].entidad} ($${top5[4].siniestros_ocurridos_mdp_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP, ${top5[4].pct_costo_nacional.toFixed(1)}%)</strong>.<br/><br/>
<strong>4. Distinción actuarial (Costo Total en MDP vs. Severidad Unitaria $/Siniestro):</strong><br/>
• El gráfico refleja volumen agregado de costos, condicionado por la identidad actuarial:<br/>
<div class="formula-box">
  <strong>Identidad actuarial de costo total:</strong>
  Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
</div><br/>
• <strong>No debe confundirse con la severidad unitaria:</strong> CDMX ($10,977.92 MXN) y Jalisco ($10,824.52 MXN) lideran en costo total por su gran escala vehicular, pero su severidad promedio individual es notablemente menor a la de Nuevo León ($13,970.61 MXN), Sinaloa ($11,637.24 MXN) o Querétaro ($11,476.31 MXN).<br/><br/>
<strong>5. Qué NO permite concluir:</strong><br/>
• No permite concluir que los estados del Top 5 tengan los siniestros individuales más caros.<br/>
• El parque vehicular registrado (INEGI VMRC) es un indicador del tamaño automotriz macroestatal, pero <em>no equivale a la exposición asegurada</em>, ya que la penetración del seguro vehicular difiere por entidad.
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="document.getElementById('secComparativas').scrollIntoView({behavior:'smooth'});">📊 Ver Diagrama Pareto</button>
  <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('')">🔍 Ver datos en tabla</button>
</div>`;
}

// 2. Chart Explanation: Scatter Plot & R² (72.05%)
function generateScatterExplanation() {
  return `🤖 <strong>Asistente de análisis actuarial — Dispersión y Coeficiente R²</strong><br/><br/>
<strong>1. Qué mide:</strong><br/>
Evalúa la relación estadística lineal entre el precio comercial promedio de los vehículos en cada entidad (muestra regional Mercado Libre, en miles de pesos) y la severidad media de siniestros de auto (en MXN).<br/><br/>
<strong>2. Cómo leer sus ejes y colores:</strong><br/>
• <strong>Eje horizontal (X):</strong> Precio promedio del auto en miles de MXN ($200k a $350k MXN).<br/>
• <strong>Eje vertical (Y):</strong> Severidad promedio por siniestro en MXN ($4,000 a $14,000 MXN).<br/>
• <strong>Puntos azules (#2563EB):</strong> Representan las 32 entidades federativas.<br/>
• <strong>Línea roja continua (#DC2626):</strong> Traza la recta de regresión lineal por mínimos cuadrados ordinarios.<br/><br/>
<strong>3. Significado del 72.05% (R²) y Correlación (r = +0.8488, Promedio 2020–2024):</strong><br/>
• <strong>Correlación de Pearson (r = +0.8488):</strong> Fuerte asociación estadística lineal positiva; entidades con parque vehicular de mayor valor comercial tienden a registrar mayor costo medio por siniestro.<br/>
• <strong>Coeficiente de determinación (R² = 0.7205 = 72.05%):</strong> Significa que el <strong>72.05% de la varianza en la severidad promedio entre estados se asocia linealmente con las diferencias en el precio comercial de los autos</strong>.<br/><br/>
<strong>4. Advertencia metodológica fundamental (Asociación vs. Causalidad):</strong><br/>
• <strong>Qué NO permite concluir:</strong> Esta correlación macroestatal <em>no demuestra que tener un vehículo más caro incremente directamente o sea la causa única de la severidad</em>.<br/>
• Factores omitidos a nivel de póliza (mayor proporción de cobertura amplia frente a responsabilidad civil, proporción de pérdidas totales y costo local de mano de obra en talleres) influyen en la relación observada. No deben extraerse conclusiones causales sin microdatos.
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="document.getElementById('secComparativas').scrollIntoView({behavior:'smooth'});">📈 Ver Scatter Plot</button>
</div>`;
}

// 3. Chart Explanation: Tendencia Temporal
function generateTrendExplanation() {
  return `🤖 <strong>Asistente de análisis actuarial — Tendencia Temporal de Severidad</strong><br/><br/>
<strong>1. Qué mide:</strong><br/>
La evolución histórica de la severidad media de siniestros automotrices en México entre 2020 y 2024.<br/><br/>
<strong>2. Cómo leer sus ejes:</strong><br/>
• <strong>Eje X:</strong> Años de observación (2020 a 2024).<br/>
• <strong>Eje Y:</strong> Severidad promedio en MXN por siniestro asegurado.<br/><br/>
<strong>3. Hallazgo clave con cifras:</strong><br/>
• La severidad media nacional creció de <strong>$4,511.22 MXN en 2020</strong> a <strong>$9,041.64 MXN en 2024</strong> (+100.4% acumulado, con una tasa de crecimiento anual compuesto CAGR de +19.0% anual).<br/>
• Este incremento refleja presiones inflacionarias en autopartes, mayor tecnología electrónica vehicular y costos médicos.<br/><br/>
<strong>4. Qué falta saber:</strong><br/>
• Si el incremento responde a inflación de costos unitarios de reparación o a un cambio estructural en la severidad (mayor frecuencia de pérdidas totales).`;
}

// 4. Three Key Findings ("Contar el reporte en tres hallazgos")
function generateThreeFindingsResponse() {
  const sortedCagr = [...rawData.estados].sort((a, b) => b.cagr_2020_2024_pct - a.cagr_2020_2024_pct);
  const topCagr = sortedCagr[0];
  const topCagrAnnual = (Math.pow(1 + topCagr.cagr_2020_2024_pct / 100, 1/4) - 1) * 100;

  // Dynamic calculation of max and min average severity states and ratio:
  const sortedSev = [...rawData.estados].sort((a, b) => b.severidad_promedio - a.severidad_promedio);
  const maxSt = sortedSev[0];
  const minSt = sortedSev[sortedSev.length - 1];
  const ratio = (maxSt.severidad_promedio / minSt.severidad_promedio).toFixed(2);

  const sortedMdp = [...rawData.estados].sort((a, b) => b.siniestros_ocurridos_mdp_promedio - a.siniestros_ocurridos_mdp_promedio);
  const top5 = sortedMdp.slice(0, 5);
  const sumTop5 = top5.reduce((sum, s) => sum + s.siniestros_ocurridos_mdp_promedio, 0);
  const totNatMdp = rawData.metadata.total_mdp_nacional_promedio;
  const top5Pct = (sumTop5 / totNatMdp) * 100;

  return `🤖 <strong>Asistente de análisis actuarial — El reporte en 3 hallazgos clave:</strong><br/><br/>
<strong>1. Alta Concentración del Costo Total (Pareto en MDP):</strong><br/>
El <strong>Top 5 de entidades federativas concentra el ${top5Pct.toFixed(1)}% del costo nacional total en MDP</strong> ($${sumTop5.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP de los $${totNatMdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP anuales). Este volumen está impulsado por estados con gran volumen vehicular: <strong>Ciudad de México ($10,616.13 MDP)</strong>, <strong>Estado de México ($10,274.08 MDP)</strong>, <strong>Jalisco ($9,488.29 MDP)</strong>, <strong>Nuevo León ($8,485.28 MDP)</strong> y <strong>Sinaloa ($3,698.65 MDP)</strong>.<br/><br/>
<strong>2. Disparidad Geográfica y Crecimiento Acumulado:</strong><br/>
Existe una dispersión de severidad unitaria de aproximadamente <strong>${ratio} veces (${ratio}x)</strong> entre <strong>${maxSt.entidad} ($${maxSt.severidad_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN, índice 209.3 pts)</strong> y estados del sur como <strong>Chiapas ($2,041.47 MXN)</strong> u <strong>${minSt.entidad} ($${minSt.severidad_promedio.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN)</strong>. En dinámica temporal, <strong>${topCagr.entidad} lidera el crecimiento acumulado con +${topCagr.cagr_2020_2024_pct.toFixed(1)}%</strong> (tasa compuesta CAGR de +${topCagrAnnual.toFixed(1)}% anual), seguido de Quintana Roo (+149.0% acum.) y Yucatán (+148.6% acum.), mientras Nuevo León creció +96.8% acumulado.<br/><br/>
<strong>3. Fuerte Asociación Lineal con Precios Vehiculares (r = +0.8488, R² = 72.05%) sin Causalidad Probada:</strong><br/>
El precio comercial promedio del vehículo muestra la asociación lineal más fuerte con la severidad estatal (r = +0.8488, R² = 72.05% en el Promedio 2020–2024). Aunque es una variable útil para segmentación, a nivel actuarial se subraya que <em>correlación no implica causalidad</em>: la severidad real depende también de la mezcla de coberturas, porcentaje de pérdidas totales y costos locales de talleres.<br/>
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="document.getElementById('secResumen').scrollIntoView({behavior:'smooth'});">📊 Ver KPIs Nacionales</button>
  <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('')">🔍 Ver tabla completa</button>
</div>`;
}

// 5. Glossary of Terms & Conceptual Definitions
function generateGlossaryResponse(term = '') {
  const norm = normalizeStr(term);
  const found = extractStatesFromQuery(term);
  const selYear = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const nat = getNationalMetricsForPeriod(selYear);

  // If query mentions defining severity with specific states as examples
  if (norm.includes('severidad') && found.length > 0) {
    let examplesText = '';
    found.forEach(stName => {
      const st = rawData.estados.find(s => s.entidad === stName);
      if (st) {
        const met = getStateMetricsForPeriod(st, selYear);
        examplesText += `• <strong>${st.entidad}:</strong> $${met.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN (Índice: ${met.relIndex.toFixed(1)} pts en ${met.periodLabel})<br/>`;
      }
    });

    return `🤖 <strong>Glosario Actuarial — Definición de Severidad con Ejemplos:</strong><br/><br/>
• <strong>Definición:</strong> La severidad es el costo económico promedio incurrido por cada reclamo o siniestro atendido.<br/>
<div class="formula-box">
  <strong>Fórmula actuarial:</strong>
  Severidad (MXN) = Costo Total Ocurrido ($) / Número de Siniestros Pagados
</div><br/>
• <strong>Ejemplos en el reporte (${nat.label}):</strong><br/>
${examplesText}
• <strong>Promedio Nacional:</strong> $${nat.natAvg.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN.<br/><br/>
• <strong>Distinción con Frecuencia:</strong> La severidad cuantifica la cuantía del siniestro cuando ocurre ($/evento), mientras que la frecuencia mide la probabilidad de que un vehículo sufra un siniestro en un año.`;
  }

  // Individual glossary terms:
  if (norm.includes('frecuencia') && !norm.includes('glosario') && !norm.includes('severidad')) {
    return `🤖 <strong>Glosario Actuarial — Frecuencia</strong><br/><br/>
• <strong>Definición:</strong> Es la probabilidad o tasa de ocurrencia de un siniestro por cada vehículo asegurado expuesto en un periodo.<br/>
<div class="formula-box">
  <strong>Fórmula actuarial:</strong>
  Frecuencia = Siniestros Ocurridos / Exposición Asegurada (Años-Vehículo)
</div><br/>
• <strong>Datos en este reporte:</strong> No se dispone del censo de pólizas aseguradas por estado; la frecuencia está implícita en la combinación de severidad unitaria y el volumen total de costo en MDP.`;
  }

  if ((norm.includes('indice') || norm.includes('relativo')) && !norm.includes('glosario')) {
    return `🤖 <strong>Glosario Actuarial — Índice Relativo (Base Nacional = 100)</strong><br/><br/>
• <strong>Definición:</strong> Estandarización de la severidad de un estado frente a la media nacional del mismo periodo.<br/>
<div class="formula-box">
  <strong>Fórmula:</strong>
  Índice Relativo = (Severidad Estatal / Promedio Nacional) × 100
</div><br/>
• <strong>Ejemplo en el reporte:</strong> Nuevo León registra un índice de <strong>209.3 pts</strong> en el Promedio 2020–2024 (severidad de $13,970.61 MXN frente a $6,674.08 MXN nacional), lo que significa que se ubica un <strong>+109.3% sobre la media nacional</strong>. En 2023, su índice es de <strong>211.1 pts</strong> frente a los $7,805.92 MXN de ese año.`;
  }

  if (norm.includes('mdp') && !norm.includes('glosario')) {
    return `🤖 <strong>Glosario Actuarial — Costo Total en MDP</strong><br/><br/>
• <strong>Definición:</strong> Millones de Pesos (1 MDP = $1,000,000 MXN) de siniestralidad acumulada.<br/>
<div class="formula-box">
  <strong>Identidad actuarial:</strong>
  Costo Total (MDP) = [Exposición asegurada × Frecuencia × Severidad en MXN] / 1,000,000
</div><br/>
• <strong>En este reporte:</strong> El costo total nacional anual promedio es de <strong>$90,373.46 MDP</strong>.<br/>
• <strong>Aclaración de Exposición vs. Parque Registrado:</strong> El parque vehicular registrado (INEGI VMRC) es un indicador del volumen automotriz general del estado, pero <strong>no equivale a la exposición asegurada</strong> (vehículos con seguro vigente). No se dispone del conteo de pólizas activas en el tablero.`;
  }

  if ((norm.includes('r2') || norm.includes('r²') || norm.includes('cuadrada')) && !norm.includes('glosario')) {
    return `🤖 <strong>Glosario Actuarial — Coeficiente R² (R Cuadrada)</strong><br/><br/>
• <strong>Definición:</strong> Coeficiente de determinación. Mide la proporción de la varianza en la severidad explicada linealmente por el precio promedio del vehículo.<br/>
• <strong>En este reporte (R² = 72.05% en el promedio 2020–2024):</strong> El 72.05% de la varianza entre estados se asocia linealmente con las diferencias en precio comercial vehicular (r = +0.8488).<br/>
• <strong>Advertencia metodológica:</strong> Describe bondad de ajuste lineal macroestatal, <em>no causalidad directa</em>.`;
  }

  // General Glossary Response
  return `🤖 <strong>Glosario Actuarial y Estadístico del Reporte:</strong><br/><br/>
• <strong>Severidad ($/Siniestro):</strong> Costo económico medio por siniestro asegurado (Costo Total / Número de Siniestros). Promedio nacional: <strong>$6,674.08 MXN</strong> (2020–2024). Rango estatal desde $2,039.42 MXN (Oaxaca) hasta $13,970.61 MXN (Nuevo León).<br/><br/>
• <strong>Frecuencia:</strong> Tasa de reclamos por vehículo asegurado (Siniestros / Exposición Asegurada). Implícita en el volumen total en MDP.<br/><br/>
• <strong>Costo Total (MDP):</strong> Millones de Pesos acumulados (1 MDP = $1,000,000 MXN). Total nacional anual promedio: <strong>$90,373.46 MDP</strong>.<br/>
<div class="formula-box">
  <strong>Identidad actuarial:</strong>
  Costo Total (MDP) = [Exposición asegurada × Frecuencia × Severidad en MXN] / 1,000,000
</div><br/>
• <strong>Exposición Asegurada vs. Parque Registrado:</strong> El dato disponible en el tablero es el <em>Parque Registrado de INEGI VMRC</em>, el cual mide el volumen automotriz total pero <strong>no equivale a los autos asegurados</strong>.<br/><br/>
• <strong>Índice Relativo (Base Nacional = 100):</strong> (Severidad Estatal / Promedio Nacional) × 100. Nuevo León: <strong>209.3 pts</strong> (+109.3% sobre la media).<br/><br/>
• <strong>Crecimiento Acumulado (2020–2024):</strong> Variación porcentual total del periodo. Líder: <strong>Tlaxcala (+150.6%)</strong>.<br/><br/>
• <strong>CAGR Anual (Tasa Compuesta):</strong> Tasa anualizada de crecimiento compuesto. Líder: <strong>Tlaxcala (+25.8% anual)</strong>.<br/><br/>
• <strong>Coeficiente R² (72.05%) y Correlación (r = +0.8488):</strong> Evaluados en el promedio 2020–2024, describen la fuerza de asociación estadística lineal entre precio comercial vehicular y severidad, sin probar causalidad directa.
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('')">🔍 Ver datos en tabla</button>
</div>`;
}

// 6. Variable Interpretation (Non-causal association ranking)
function generateVariableImpactResponse() {
  return `🤖 <strong>Asistente de análisis actuarial — Asociación Estadística de Variables:</strong><br/><br/>
De acuerdo con el análisis de regresión disponible a nivel macroestatal (Promedio 2020–2024), las variables presentan los siguientes grados de **asociación estadística lineal** con la severidad promedio:<br/><br/>
1. <strong>Precio Comercial Promedio del Vehículo (Muestra Mercado Libre):</strong><br/>
   • Correlación: <strong>r = +0.8488</strong> | Coeficiente <strong>R² = 72.05%</strong> (p &lt; 0.0001).<br/>
   • Muestra la asociación estadística más fuerte entre las variables observadas.<br/><br/>
2. <strong>Tasa de Motorización (INEGI VMRC):</strong><br/>
   • Correlación: <strong>r = +0.7648</strong> (Vehículos registrados por cada 1,000 habitantes).<br/>
   • Refleja una asociación positiva moderada-alta con la densidad vehicular urbana.<br/><br/>
3. <strong>Volumen del Parque Vehicular Registrado:</strong><br/>
   • Correlación: <strong>r = +0.3621</strong>.<br/>
   • Presenta una asociación débil con la severidad unitaria, aunque impacta directamente el costo total en MDP.<br/><br/>
⚠️ <strong>Nota Metodológica Importante:</strong><br/>
Este orden describe la fuerza de **asociación estadística en el dataset disponible, no un ranking de causas**. En estadística actuarial, la correlación no implica causalidad directa; no es posible atribuir variaciones en costos a factores no medidos en este análisis (como costos de refacciones o mezcla de coberturas) sin un modelo econométrico de microdatos.`;
}

// 7. Rigorous State Comparison
function generateStateComparisonResponse(stNameA, stNameB, period = 'ALL') {
  const stA = rawData.estados.find(s => s.entidad === stNameA);
  const stB = rawData.estados.find(s => s.entidad === stNameB);
  if (!stA || !stB) return 'No se encontraron ambos estados para comparar.';

  const activeYearFilter = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const activeYearLabel = activeYearFilter === 'ALL' ? 'Promedio 2020–2024' : `Año ${activeYearFilter}`;
  const periodDiffers = (period !== activeYearFilter);

  const metA = getStateMetricsForPeriod(stA, period);
  const metB = getStateMetricsForPeriod(stB, period);
  const nat = getNationalMetricsForPeriod(period);

  const diffSev = metA.severidad - metB.severidad;
  const absDiffSev = Math.abs(diffSev);
  
  const higherState = metA.severidad >= metB.severidad ? metA : metB;
  const lowerState = metA.severidad >= metB.severidad ? metB : metA;
  const higherPctOverLower = ((higherState.severidad - lowerState.severidad) / lowerState.severidad) * 100;

  const higherMdp = metA.mdp >= metB.mdp ? metA : metB;
  const lowerMdp = metA.mdp >= metB.mdp ? metB : metA;

  let res = `🤖 <strong>Asistente de análisis actuarial — Comparativa entre ${metA.entidad} y ${metB.entidad}</strong><br/>`;
  res += `<em>Periodo evaluado: ${metA.periodLabel}${periodDiffers ? ` (el filtro del tablero se encuentra en ${activeYearLabel})` : ' (Cifras unificadas con mapa, ficha y tabla)'}</em><br/><br/>`;

  // 1. Qué ocurre y cuánto difiere
  res += `<strong>1. Qué ocurre y cuánto difiere (Severidad Unitaria):</strong><br/>`;
  res += `• En el ${metA.periodLabel}, <strong>${metA.entidad}</strong> registra <strong>$${metA.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN</strong> por siniestro y <strong>${metB.entidad}</strong> registra <strong>$${metB.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN</strong> (frente al promedio nacional de $${nat.natAvg.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN).<br/>`;
  res += `• <strong>${higherState.entidad}</strong> está <strong>$${absDiffSev.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN</strong>, aproximadamente un <strong>${higherPctOverLower.toFixed(1)}% por encima</strong> de ${lowerState.entidad} (tomando como base a ${lowerState.entidad}: $${lowerState.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN).<br/><br/>`;

  // 2. Distinción crítica entre costo unitario y volumen total
  res += `<strong>2. Distinción entre Severidad Unitaria y Volumen Total (MDP):</strong><br/>`;
  if (higherState.entidad !== higherMdp.entidad) {
    res += `• Sin embargo, <strong>${higherMdp.entidad}</strong> presenta un costo total mayor en la tabla: <strong>$${higherMdp.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP</strong> frente a <strong>$${lowerMdp.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP</strong> de ${lowerMdp.entidad}.<br/>`;
    res += `• <em>Esta distinción responde a la identidad actuarial:</em><br/>`;
    res += `<div class="formula-box">
      <strong>Identidad actuarial de costo total:</strong>
      Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
    </div><br/>`;
    res += `• <strong>Distinción actuarial de datos disponibles:</strong><br/>`;
    res += `  - Las cifras de <strong>${metA.entidad} (${metA.autos.toLocaleString('es-MX')} autos)</strong> y <strong>${metB.entidad} (${metB.autos.toLocaleString('es-MX')} autos)</strong> corresponden al <em>Parque de Vehículos Registrados en Circulación (INEGI VMRC)</em>. Miden la escala general del parque automotriz estatal, pero <strong>no equivalen a la exposición asegurada</strong> (número de vehículos con póliza vigente).<br/>`;
    res += `  - En México, la tasa de aseguramiento vehicular difiere notablemente entre entidades. El tablero no cuenta con el desglose de pólizas expuestas por estado para calcular la frecuencia pura de forma independiente; el costo total en MDP responde al volumen de autos asegurados que sufren siniestros y a su costo medio, no únicamente a la severidad unitaria.<br/><br/>`;
  } else {
    res += `• En volumen total de costos en la tabla, <strong>${higherMdp.entidad}</strong> también acumula una mayor cifra: <strong>$${higherMdp.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP</strong> vs <strong>$${lowerMdp.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP</strong> de ${lowerMdp.entidad}.<br/>`;
    res += `<div class="formula-box">
      <strong>Identidad actuarial de costo total:</strong>
      Costo Total (MDP) = [Exposición asegurada × Frecuencia de reclamos × Severidad en MXN] / 1,000,000
    </div><br/>`;
    res += `• <em>Nota sobre exposición:</em> Los autos reportados (${metA.autos.toLocaleString('es-MX')} vs ${metB.autos.toLocaleString('es-MX')}) reflejan el parque registrado INEGI VMRC, no el volumen de vehículos asegurados bajo póliza.<br/><br/>`;
  }

  // 3. Evidencia disponible para interpretarlo
  res += `<strong>3. Evidencia disponible para interpretarlo:</strong><br/>`;
  res += `• El precio comercial estimado del vehículo es de <strong>$${metA.precioAuto.toFixed(0)}k MXN en ${metA.entidad}</strong> vs <strong>$${metB.precioAuto.toFixed(0)}k MXN en ${metB.entidad}</strong>. A nivel nacional se observa una fuerte asociación lineal (r = +0.8488, R² = 72.05%, evaluados en el promedio 2020–2024) entre el precio del auto y la severidad media.<br/><br/>`;

  // 4. Qué no permite concluir y qué falta saber
  res += `<strong>4. Qué no permite concluir y qué falta saber:</strong><br/>`;
  res += `• La correlación nacional con el precio del vehículo puede orientar el análisis, pero <strong>no demuestra por sí sola la causa</strong> de esta diferencia entre ambos estados.<br/>`;
  res += `• Factores no disponibles en este tablero (mezcla de coberturas amplia vs. responsabilidad civil, proporción de pérdidas totales y costo local de mano de obra en talleres) explican la brecha real.`;

  res += `<div class="chat-action-bar">
    <button class="btn-chat-action" onclick="window.selectStateInDashboard('${metA.entidad}', '${period}')">🗺️ Ver ${metA.entidad}</button>
    <button class="btn-chat-action" onclick="window.selectStateInDashboard('${metB.entidad}', '${period}')">🗺️ Ver ${metB.entidad}</button>
    <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('${metA.entidad}', '${period}')">🔍 Ver en tabla</button>
  </div>`;

  chatMemory.mode = 'comparison';
  chatMemory.lastStates = [metA.entidad, metB.entidad];
  chatMemory.lastYear = period;
  return res;
}

// 8. Single State Analysis
function generateSingleStateResponse(stName, period = 'ALL') {
  const st = rawData.estados.find(s => s.entidad === stName);
  if (!st) return `No se encontraron datos para ${stName}.`;

  const activeYearFilter = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';
  const activeYearLabel = activeYearFilter === 'ALL' ? 'Promedio 2020–2024' : `Año ${activeYearFilter}`;
  const periodDiffers = (period !== activeYearFilter);

  const met = getStateMetricsForPeriod(st, period);
  const nat = getNationalMetricsForPeriod(period);
  const diffSign = met.diffPct >= 0 ? '+' : '';
  const cagrAnual = (Math.pow(1 + st.cagr_2020_2024_pct / 100, 1/4) - 1) * 100;

  chatMemory.mode = 'single';
  chatMemory.lastStates = [st.entidad];
  chatMemory.lastYear = period;

  return `🤖 <strong>Asistente de análisis actuarial — Análisis de ${st.entidad}:</strong><br/><br/>
<strong>1. Qué ocurre (Severidad Unitaria):</strong><br/>
• <strong>Severidad registrada:</strong> <strong>$${met.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN</strong> por siniestro asegurado.<br/>
• <strong>Periodo consultado:</strong> ${met.periodLabel}${periodDiffers ? ` (el filtro del tablero se encuentra en ${activeYearLabel})` : ' (Unificado con filtros y tabla)'}.<br/>
• <strong>Clasificación de riesgo (${met.periodLabel}):</strong> <span class="badge badge-${normalizeStr(met.categoria)}">${met.categoria}</span>.<br/><br/>
<strong>2. Cuánto difiere (Base Nacional ${met.periodLabel}):</strong><br/>
• <strong>Diferencia vs Nacional (${met.periodLabel}):</strong> <strong>${diffSign}${met.diffPct.toFixed(1)}%</strong> ($${Math.abs(met.diffAbs).toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN respecto al promedio nacional de $${nat.natAvg.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN).<br/>
• <strong>Índice Relativo:</strong> <strong>${met.relIndex.toFixed(1)} pts</strong> (Base Nacional ${met.periodLabel} = 100).<br/>
• <strong>Crecimiento Acumulado (2020–2024):</strong> +${st.cagr_2020_2024_pct.toFixed(1)}% (tasa compuesta CAGR de +${cagrAnual.toFixed(1)}% anual).<br/><br/>
<strong>3. Evidencia disponible para interpretarlo:</strong><br/>
• <strong>Costo Total en el reporte:</strong> $${met.mdp.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MDP.<br/>
• <strong>Parque vehicular registrado (INEGI VMRC):</strong> ${st.automoviles_registrados.toLocaleString('es-MX')} autos (indicador de volumen macro del estado, no exposición asegurada).<br/>
• <strong>Precio comercial vehicular estimado:</strong> $${st.precio_promedio_auto_ml_k_mxn.toFixed(0)}k MXN.<br/><br/>
<strong>4. Qué falta saber / Advertencia:</strong><br/>
• La correlación estadística nacional con el precio del vehículo orienta la tarificación, pero no demuestra por sí sola la causa directa de este nivel de severidad. No se dispone de la cartera de pólizas aseguradas ni de la mezcla de coberturas de la entidad en este tablero para aislar la frecuencia micro.
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="window.selectStateInDashboard('${st.entidad}', '${period}')">🗺️ Mostrar en mapa</button>
  <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('${st.entidad}', '${period}')">🔍 Ver en tabla</button>
</div>`;
}

// 9. Comparison Factor Explanation ("¿Por qué?")
function generateComparisonWhyResponse(stNameA, stNameB, period = 'ALL') {
  const stA = rawData.estados.find(s => s.entidad === stNameA);
  const stB = rawData.estados.find(s => s.entidad === stNameB);
  if (!stA || !stB) return 'No se encontraron los estados para explicar la diferencia.';

  const metA = getStateMetricsForPeriod(stA, period);
  const metB = getStateMetricsForPeriod(stB, period);
  const higher = metA.severidad >= metB.severidad ? metA : metB;
  const lower = metA.severidad >= metB.severidad ? metB : metA;
  const diffAbs = Math.abs(metA.severidad - metB.severidad);
  const pctDiff = ((higher.severidad - lower.severidad) / lower.severidad) * 100;

  return `🤖 <strong>Asistente de análisis actuarial — Factores y Evidencia (${higher.entidad} vs ${lower.entidad}):</strong><br/><br/>
<strong>1. Qué se observa en los datos:</strong><br/>
• ${higher.entidad} supera a ${lower.entidad} en $${diffAbs.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN (+${pctDiff.toFixed(1)}% tomando como base a ${lower.entidad}).<br/>
• <strong>Precio comercial vehicular estimado:</strong> $${higher.precioAuto.toFixed(0)}k MXN en ${higher.entidad} vs $${lower.precioAuto.toFixed(0)}k MXN en ${lower.entidad}.<br/><br/>
<strong>2. Evidencia estadística disponible:</strong><br/>
• En el análisis macroestatal (Promedio 2020–2024), el valor del vehículo presenta una correlación lineal positiva (r = +0.8488, R² = 72.05%) con la severidad.<br/><br/>
<strong>3. Advertencia actuarial (Correlación no es Causalidad):</strong><br/>
• Esta asociación estadística orienta la tarificación, pero <em>no demuestra por sí sola que el precio del auto sea la causa directa única</em> de la diferencia entre ambos estados.<br/>
• Factores a nivel de póliza no medidos en este reporte (como mayor porcentaje de cobertura amplia frente a daños a terceros, proporción de pérdidas totales y costo local de mano de obra en talleres) explican la brecha real.`;
}

// 10. Main AI Intent Router
function processAIIntent(userQuery) {
  const normQ = (typeof window !== 'undefined' && window.ActuarialEngine)
    ? window.ActuarialEngine.normalizeText(userQuery)
    : normalizeStr(userQuery);
  const activeYearFilter = document.getElementById('selectYear') ? document.getElementById('selectYear').value : 'ALL';

  // Prioridades 1 a 6 vía ActuarialEngine compartido (paridad con Python)
  if (typeof window !== 'undefined' && window.ActuarialEngine && rawData) {
    if (!engineMemory) engineMemory = new window.ActuarialEngine.MemoryManager();
    const canonicalStates = rawData.estados.map(s => s.entidad);
    const ir = window.ActuarialEngine.parseQueryIR(userQuery, canonicalStates, engineMemory);

    if (ir.intent === 'out_of_domain') {
      return `🤖 <strong>Asistente de análisis actuarial:</strong><br/>
La consulta se encuentra fuera del ámbito actuarial del Dataset Actuarial de Severidad de Siniestros de Auto en México (Chubb Baseline 2020–2024).<br/>
Este asistente solo responde consultas sobre severidad ($ MXN), costo total (MDP), factores de riesgo vehicular e indicadores del reporte.`;
    }

    if (ir.intent === 'temporal_out_of_range' || ir.intent === 'clarification_year') {
      return `🤖 <strong>Asistente de análisis actuarial:</strong><br/>${ir.error_message}`;
    }

    if (ir.intent === 'executive_multistate_summary' || ir.intent === 'executive_single_state_summary') {
      const summary = window.ActuarialEngine.computeExecutiveSummary(rawData, ir.states, ir.target_year);
      engineMemory.updateConfirmedContext(ir.states, ir.target_year, ir.intent);
      chatMemory.mode = 'summary';
      chatMemory.lastStates = ir.states;
      chatMemory.lastYear = String(ir.target_year);
      return window.ActuarialEngine.formatExecutiveSummaryHtml(summary, ir);
    }

    if (ir.intent === 'three_findings') {
      chatMemory.mode = 'chart';
      return generateThreeFindingsResponse();
    }

    if (ir.intent === 'multi_state_comparison' && ir.insufficient_entities && ir.states.length === 1) {
      const stName = ir.states[0];
      const yrUse = ir.target_year ? String(ir.target_year) : activeYearFilter;
      engineMemory.updateConfirmedContext([stName], ir.target_year, 'single_state');
      const noteMsg = ir.interpretation_notes[0] || `Ambas menciones corresponden a ${stName}; indica otra entidad para comparar.`;
      return `ℹ️ <em>${noteMsg}</em><br/><br/>` + generateSingleStateResponse(stName, yrUse);
    }
  }

  // Determine requested period following the hierarchy:
  // (a) Explicit in query -> (b) Follow-up in memory -> (c) UI Filter
  let requestedPeriod = null;
  if (normQ.includes('promedio') || normQ.includes('2020 2024') || normQ.includes('2020-2024') || normQ.includes('historico')) {
    requestedPeriod = 'ALL';
  } else {
    const yearMatch = normQ.match(/\b(2020|2021|2022|2023|2024)\b/);
    if (yearMatch) requestedPeriod = yearMatch[1];
  }

  const periodToUse = requestedPeriod || (chatMemory.lastYear && (normQ.includes('y en') || normQ.includes('mismo')) ? chatMemory.lastYear : activeYearFilter);
  const foundStates = extractStatesFromQuery(userQuery);

  // 1. Three Findings Intent (without states)
  if ((normQ.includes('hallazgo') || normQ.includes('contar el reporte') || normQ.includes('conclusiones')) && foundStates.length === 0) {
    chatMemory.mode = 'chart';
    return generateThreeFindingsResponse();
  }

  // 2. Pareto Chart Intent
  if (normQ.includes('pareto') || (normQ.includes('barra') && normQ.includes('linea')) || (normQ.includes('ejes') && normQ.includes('grafica'))) {
    chatMemory.mode = 'chart';
    return generateParetoExplanation();
  }

  // 3. Scatter Plot / R² Intent
  if (normQ.includes('r2') || normQ.includes('r²') || normQ.includes('r cuadrada') || normQ.includes('72.05') || normQ.includes('scatter')) {
    chatMemory.mode = 'chart';
    return generateScatterExplanation();
  }

  // 4. Trend Chart Intent
  if (normQ.includes('tendencia') || normQ.includes('historico') || normQ.includes('evolucion') || normQ.includes('trend')) {
    chatMemory.mode = 'chart';
    return generateTrendExplanation();
  }

  // 5. Variables Impact / Drivers Intent
  if (normQ.includes('variable') && (normQ.includes('afecta') || normQ.includes('impacto') || normQ.includes('mas') || normQ.includes('driver') || normQ.includes('mayor'))) {
    chatMemory.mode = 'chart';
    return generateVariableImpactResponse();
  }

  // 6. Glossary & Conceptual Definition Intent (PRIORITY OVER STATE COMPARISON)
  if (normQ.includes('glosario') || normQ.includes('que significa') || normQ.includes('define') || normQ.includes('definir') || normQ.includes('definicion') || normQ.includes('concepto de') || normQ.includes('explicar la severidad') || normQ.includes('explica la severidad')) {
    chatMemory.mode = 'glossary';
    return generateGlossaryResponse(normQ);
  }

  // 7. Comparison Intent
  const isComparisonQuery = normQ.includes('comparar') || normQ.includes('compara') || normQ.includes('comparativa') ||
    normQ.includes('diferencia entre') || normQ.includes('cuanto difieren') || normQ.includes('vs') ||
    normQ.includes('frente a') || normQ.includes('versus') || normQ.includes('contrastar') ||
    (foundStates.length >= 2);

  if (isComparisonQuery) {
    if (foundStates.length >= 2) {
      return generateStateComparisonResponse(foundStates[0], foundStates[1], periodToUse);
    }
    if (foundStates.length === 1 && chatMemory.mode === 'comparison' && chatMemory.lastStates.length >= 2) {
      const otherState = chatMemory.lastStates.find(s => s !== foundStates[0]) || chatMemory.lastStates[0];
      return generateStateComparisonResponse(foundStates[0], otherState, periodToUse);
    }
    // "Comparar estados" clicked without states
    return `🤖 <strong>Asistente de análisis actuarial — Comparación de Estados:</strong><br/><br/>
¿Qué dos estados deseas comparar?<br/>
Escribe por ejemplo:<br/>
• <em>"Compara Nuevo León y Jalisco en el promedio 2020–2024. ¿Cuánto difieren?"</em><br/>
• <em>"Compara Querétaro y Puebla en 2023"</em><br/>
• <em>"Compara CDMX y Estado de México"</em><br/><br/>
O pulsa una de estas opciones rápidas:
<div class="chat-action-bar">
  <button class="btn-chat-action" onclick="document.getElementById('chatInput').value='Compara Nuevo León y Jalisco en el promedio 2020–2024. ¿Cuánto difieren?'; handleUserChatMessage();">⚖️ NL vs Jalisco</button>
  <button class="btn-chat-action" onclick="document.getElementById('chatInput').value='Compara Ciudad de Mexico y Estado de Mexico'; handleUserChatMessage();">⚖️ CDMX vs Edomex</button>
  <button class="btn-chat-action" onclick="document.getElementById('chatInput').value='Compara Queretaro y Puebla'; handleUserChatMessage();">⚖️ Querétaro vs Puebla</button>
</div>`;
  }

  // 8. Follow-up Query: "¿Y en 2024?", "¿Y en 2023?", "¿Por qué?"
  if (requestedPeriod && (normQ.includes('y en') || normQ.includes('mismo') || normQ.length <= 15)) {
    if (chatMemory.mode === 'comparison' && chatMemory.lastStates.length >= 2) {
      return generateStateComparisonResponse(chatMemory.lastStates[0], chatMemory.lastStates[1], requestedPeriod);
    }
    if (chatMemory.lastStates.length >= 1) {
      return generateSingleStateResponse(chatMemory.lastStates[0], requestedPeriod);
    }
  }

  if (normQ.includes('por que') || normQ.includes('porque') || normQ.includes('razon')) {
    if (chatMemory.mode === 'comparison' && chatMemory.lastStates.length >= 2) {
      return generateComparisonWhyResponse(chatMemory.lastStates[0], chatMemory.lastStates[1], chatMemory.lastYear);
    }
  }

  // 9. Single State Query / Explicit Change ("ahora analiza Oaxaca")
  let targetState = foundStates.length > 0 ? foundStates[0] : null;
  if (!targetState && chatMemory.lastStates.length >= 1 && (normQ.includes('este estado') || normQ.includes('su severidad'))) {
    targetState = chatMemory.lastStates[0];
  }

  if (targetState && rawData) {
    return generateSingleStateResponse(targetState, periodToUse);
  }

  // 10. Rankings / Top States
  if (normQ.includes('top') || normQ.includes('ranking') || normQ.includes('mas caro') || normQ.includes('mas alto') || normQ.includes('severo')) {
    const sorted = [...rawData.estados].sort((a, b) => {
      const mA = getStateMetricsForPeriod(a, periodToUse).severidad;
      const mB = getStateMetricsForPeriod(b, periodToUse).severidad;
      return mB - mA;
    }).slice(0, 5);

    let res = `🤖 <strong>Asistente de análisis — Top 5 Estados con Mayor Severidad (${getNationalMetricsForPeriod(periodToUse).label}):</strong><br/><br/>`;
    sorted.forEach((s, idx) => {
      const m = getStateMetricsForPeriod(s, periodToUse);
      res += `${idx + 1}. <strong>${s.entidad}</strong>: $${m.severidad.toLocaleString('es-MX', {minimumFractionDigits:2, maximumFractionDigits:2})} MXN (Índice: ${m.relIndex.toFixed(1)} pts)<br/>`;
    });
    res += `<br/>• <strong>Concentración Pareto Top 5:</strong> 47.1% del costo nacional total en MDP.<br/>
    • <strong>Fuente:</strong> Chubb Baseline & Marco Geoestadístico INEGI.
    <div class="chat-action-bar">
      <button class="btn-chat-action" onclick="window.highlightAndScrollToTable('')">🔍 Ver matriz completa</button>
    </div>`;
    return res;
  }

  // 11. Fallback with Clear Specific Suggestions
  return `🤖 <strong>Asistente de análisis actuarial:</strong><br/>
No reconocí con precisión esa consulta. Puedo ayudarte con cualquiera de estas opciones verificables:<br/><br/>
• <strong>Análisis estatal:</strong> <em>"Analizar Nuevo León"</em> o <em>"¿Y en 2024?"</em><br/>
• <strong>Comparación de dos estados:</strong> <em>"Compara Nuevo León y Jalisco en el promedio 2020–2024"</em><br/>
• <strong>Explicación de gráficas:</strong> <em>"Explicar barras, línea y ejes de Pareto"</em> o <em>"Explicar R² y el 72.05%"</em><br/>
• <strong>Resumen ejecutivo:</strong> <em>"Contar el reporte en tres hallazgos"</em><br/>
• <strong>Glosario actuarial:</strong> <em>"Glosario de severidad, frecuencia, índice relativo y MDP"</em>`;
}

function setupEventListeners() {
  const selYear = document.getElementById('selectYear');
  const selState = document.getElementById('selectState');
  const searchInput = document.getElementById('tableSearchInput');
  const btnReset = document.getElementById('btnResetFilters');
  const btnExport = document.getElementById('btnExport');
  const btnRetry = document.getElementById('btnRetryLoad');

  if (selYear) selYear.addEventListener('change', () => { triggerGlobalFilter(); updateChatContextPill(); });
  if (selState) selState.addEventListener('change', () => { triggerGlobalFilter(); updateChatContextPill(); });
  if (searchInput) searchInput.addEventListener('input', triggerGlobalFilter);
  if (btnReset) btnReset.addEventListener('click', resetAllFilters);
  if (btnExport) btnExport.addEventListener('click', () => window.print());
  if (btnRetry) btnRetry.addEventListener('click', () => location.reload());

  // Table Column Header Click Listener for Sorting
  document.querySelectorAll('#statesTable thead th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.getAttribute('data-sort');
      if (currentSortCol === col) {
        currentSortAsc = !currentSortAsc;
      } else {
        currentSortCol = col;
        currentSortAsc = (col === 'entidad'); // Text defaults asc, numbers desc
      }
      renderDataTable();
    });
  });

  // Map Navigation Toolbar Listeners
  const btnZoomIn = document.getElementById('btnMapZoomIn');
  const btnZoomOut = document.getElementById('btnMapZoomOut');
  const btnMapReset = document.getElementById('btnMapReset');
  const btnMapCenter = document.getElementById('btnMapCenter');

  if (btnZoomIn && mapInstance) btnZoomIn.addEventListener('click', () => mapInstance.zoomIn());
  if (btnZoomOut && mapInstance) btnZoomOut.addEventListener('click', () => mapInstance.zoomOut());
  if (btnMapReset && mapInstance) btnMapReset.addEventListener('click', fitMapToMexico);
  if (btnMapCenter && mapInstance) btnMapCenter.addEventListener('click', () => {
    mapInstance.flyTo({ center: [-99.1332, 19.4326], zoom: 6.8, essential: true });
  });

  window.addEventListener('resize', () => {
    if (mapInstance) mapInstance.resize();
  });

  // Chat Widget Listeners
  const btnToggle = document.getElementById('btnToggleChat');
  const chatBox = document.getElementById('chatWindow');
  const btnClose = document.getElementById('btnCloseChat');
  const btnSend = document.getElementById('btnSendChat');
  const chatInput = document.getElementById('chatInput');
  const btnNewChat = document.getElementById('btnNewChat');
  const btnCopyChat = document.getElementById('btnCopyChat');
  const btnExpandChat = document.getElementById('btnExpandChat');

  renderWelcomeMessage();
  updateChatContextPill();

  if (btnToggle && chatBox) {
    btnToggle.addEventListener('click', () => chatBox.classList.toggle('hidden'));
  }
  if (btnClose && chatBox) {
    btnClose.addEventListener('click', () => chatBox.classList.add('hidden'));
  }

  if (btnExpandChat && chatBox) {
    btnExpandChat.addEventListener('click', () => {
      chatBox.classList.toggle('expanded');
    });
  }

  if (btnNewChat) {
    btnNewChat.addEventListener('click', () => {
      chatMemory = { mode: 'none', lastStates: [], lastYear: 'ALL', lastTopic: 'severidad', lastResponseText: '' };
      if (typeof window !== 'undefined' && window.ActuarialEngine) {
        engineMemory = new window.ActuarialEngine.MemoryManager();
      }
      renderWelcomeMessage();
    });
  }

  if (btnCopyChat) {
    btnCopyChat.addEventListener('click', () => {
      if (chatMemory.lastResponseText) {
        const cleanText = chatMemory.lastResponseText.replace(/<[^>]*>/g, '');
        navigator.clipboard.writeText(cleanText);
        alert('Respuesta copiada al portapapeles');
      }
    });
  }

  if (btnSend) btnSend.addEventListener('click', handleUserChatMessage);
  if (chatInput) chatInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleUserChatMessage(); });

  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      if (chatInput) chatInput.value = e.target.getAttribute('data-query');
      handleUserChatMessage();
    });
  });
}
