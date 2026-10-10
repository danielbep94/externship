import pandas as pd
import numpy as np
import os

# Create directories
os.makedirs('/Users/victordaniel/chubb/output', exist_ok=True)

# 1. Load Baseline Claims Data
df_claims = pd.read_csv('/Users/victordaniel/chubb/data/baseline_siniestros.csv')

# Clean state names
df_claims['entidad'] = df_claims['entidad'].str.strip()

# Convert MDP to total pesos
df_claims['costo_total_pesos'] = df_claims['siniestros_ocurridos_mdp'] * 1_000_000

# 2. INEGI & Regional Data per State (Census 2020 / INEGI VMRC & Territorial Area)
inegi_data = {
    'entidad': [
        'Aguascalientes', 'Baja California', 'Baja California Sur', 'Campeche', 'Chiapas',
        'Chihuahua', 'Ciudad de Mexico', 'Coahuila', 'Colima', 'Durango',
        'Estado de Mexico', 'Guanajuato', 'Guerrero', 'Hidalgo', 'Jalisco',
        'Michoacan', 'Morelos', 'Nayarit', 'Nuevo Leon', 'Oaxaca',
        'Puebla', 'Queretaro', 'Quintana Roo', 'San Luis Potosi', 'Sinaloa',
        'Sonora', 'Tabasco', 'Tamaulipas', 'Tlaxcala', 'Veracruz',
        'Yucatan', 'Zacatecas'
    ],
    'poblacion_2020': [
        1425607, 3769020, 798447, 928363, 5543828,
        3741869, 9209944, 3146771, 731391, 1832650,
        16992418, 6166934, 3540685, 3082841, 8348151,
        4748846, 1971520, 1235456, 5784442, 4132148,
        6583278, 2368467, 1857985, 2822255, 3026943,
        2944840, 2402598, 3527735, 1342977, 8062579,
        2320898, 1622138
    ],
    'automoviles_registrados': [
        541200, 1385400, 395000, 245000, 680000,
        1450000, 5450000, 1150000, 285000, 490000,
        5850000, 1920000, 620000, 690000, 3420000,
        1250000, 510000, 340000, 2580000, 590000,
        1480000, 890000, 610000, 820000, 1050000,
        1180000, 530000, 1120000, 380000, 1750000,
        840000, 460000
    ],
    'area_km2': [
        5616, 71450, 73909, 57507, 73289,
        247455, 1485, 151563, 5625, 123317,
        22357, 30608, 63621, 20813, 78588,
        58643, 4893, 27815, 64210, 93757,
        34251, 11684, 44707, 60983, 57377,
        179355, 24738, 80249, 3991, 71820,
        39612, 75539
    ],
    'precio_gasolina_reg_prom': [
        22.45, 21.80, 23.50, 23.80, 22.90,
        21.90, 23.10, 22.30, 22.80, 23.40,
        22.20, 22.60, 23.90, 22.10, 23.20,
        22.70, 22.50, 23.10, 23.40, 23.60,
        22.30, 22.70, 23.60, 22.80, 23.30,
        22.10, 22.80, 21.95, 22.05, 22.95,
        23.00, 23.20
    ],
    'precio_promedio_auto_ml_k_mxn': [
        245, 260, 280, 230, 215,
        275, 340, 270, 250, 240,
        290, 265, 220, 235, 310,
        240, 255, 235, 330, 210,
        250, 305, 270, 255, 260,
        265, 240, 255, 225, 245,
        275, 230
    ]
}

df_inegi = pd.DataFrame(inegi_data)

# Merge datasets
df_merged = pd.merge(df_claims, df_inegi, on='entidad', how='left')

# Business Assumptions
# Option A: Population-based Exposure
df_merged['riesgo_expuesto_poblacion'] = df_merged['poblacion_2020'] * 0.35
df_merged['numero_reclamos_poblacion'] = df_merged['riesgo_expuesto_poblacion'] * 0.30
df_merged['severidad_poblacion'] = df_merged['costo_total_pesos'] / df_merged['numero_reclamos_poblacion']
df_merged['frecuencia_poblacion'] = 0.30
df_merged['prima_pura_poblacion'] = df_merged['frecuencia_poblacion'] * df_merged['severidad_poblacion']

# Option B: Vehicle Fleet-based Exposure
df_merged['riesgo_expuesto_autos'] = df_merged['automoviles_registrados'] * 0.35
df_merged['numero_reclamos_autos'] = df_merged['riesgo_expuesto_autos'] * 0.30
df_merged['severidad_autos'] = df_merged['costo_total_pesos'] / df_merged['numero_reclamos_autos']
df_merged['frecuencia_autos'] = 0.30
df_merged['prima_pura_autos'] = df_merged['frecuencia_autos'] * df_merged['severidad_autos']

# Complementary Variables
df_merged['densidad_poblacional'] = df_merged['poblacion_2020'] / df_merged['area_km2']
df_merged['autos_por_1000_hab'] = (df_merged['automoviles_registrados'] / df_merged['poblacion_2020']) * 1000
df_merged['densidad_vehicular_km2'] = df_merged['automoviles_registrados'] / df_merged['area_km2']

# Save complete dataframe
df_merged.to_csv('/Users/victordaniel/chubb/output/df_analisis_completo.csv', index=False)

# Aggregated by State
df_avg_state = df_merged.groupby('entidad').agg({
    'siniestros_ocurridos_mdp': 'mean',
    'costo_total_pesos': 'mean',
    'severidad_poblacion': 'mean',
    'severidad_autos': 'mean',
    'prima_pura_poblacion': 'mean',
    'prima_pura_autos': 'mean',
    'poblacion_2020': 'first',
    'automoviles_registrados': 'first',
    'densidad_poblacional': 'first',
    'autos_por_1000_hab': 'first',
    'precio_promedio_auto_ml_k_mxn': 'first',
    'precio_gasolina_reg_prom': 'first'
}).reset_index()

# Sort Top 3
top3_states_avg_pob = df_avg_state.sort_values(by='severidad_poblacion', ascending=False).head(3)
top3_states_avg_autos = df_avg_state.sort_values(by='severidad_autos', ascending=False).head(3)
df_2024 = df_merged[df_merged['anio'] == 2024].sort_values(by='severidad_poblacion', ascending=False)
top3_states_2024 = df_2024.head(3)

# Correlations
corr_pob = df_avg_state[[
    'severidad_poblacion',
    'precio_promedio_auto_ml_k_mxn',
    'autos_por_1000_hab',
    'densidad_poblacional',
    'precio_gasolina_reg_prom',
    'poblacion_2020',
    'automoviles_registrados'
]].corr()['severidad_poblacion'].sort_values(ascending=False)

corr_autos = df_avg_state[[
    'severidad_autos',
    'precio_promedio_auto_ml_k_mxn',
    'autos_por_1000_hab',
    'densidad_poblacional',
    'precio_gasolina_reg_prom',
    'poblacion_2020',
    'automoviles_registrados'
]].corr()['severidad_autos'].sort_values(ascending=False)

# Export Summary Tables for Reports
df_avg_state.sort_values(by='severidad_poblacion', ascending=False).to_csv('/Users/victordaniel/chubb/output/ranking_estados_severidad.csv', index=False)

print("=== TOP 3 ESTADOS CON MAYOR SEVERIDAD (Base Población, Promedio 2020-2024) ===")
for idx, row in top3_states_avg_pob.iterrows():
    print(f"{row['entidad']}: Severidad = ${row['severidad_poblacion']:,.2f} MXN | Prima Pura = ${row['prima_pura_poblacion']:,.2f} MXN | Costo Siniestros = ${row['siniestros_ocurridos_mdp']:,.2f} MDP")

print("\n=== TOP 3 ESTADOS CON MAYOR SEVERIDAD (Año 2024 Reciente, Base Población) ===")
for idx, row in top3_states_2024.head(3).iterrows():
    print(f"{row['entidad']}: Severidad = ${row['severidad_poblacion']:,.2f} MXN | Prima Pura = ${row['prima_pura_poblacion']:,.2f} MXN | Costo Siniestros = ${row['siniestros_ocurridos_mdp']:,.2f} MDP")

print("\n=== TOP 3 ESTADOS CON MAYOR SEVERIDAD (Base Parque Vehicular) ===")
for idx, row in top3_states_avg_autos.iterrows():
    print(f"{row['entidad']}: Severidad = ${row['severidad_autos']:,.2f} MXN | Prima Pura = ${row['prima_pura_autos']:,.2f} MXN | Costo Siniestros = ${row['siniestros_ocurridos_mdp']:,.2f} MDP")

print("\n=== CORRELACION DE VARIABLES COMPLEMENTARIAS CON SEVERIDAD (Población) ===")
print(corr_pob)

print("\n=== CORRELACION DE VARIABLES COMPLEMENTARIAS CON SEVERIDAD (Autos) ===")
print(corr_autos)
