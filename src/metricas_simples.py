import pandas as pd
import numpy as np

df = pd.read_csv('/Users/victordaniel/chubb/output/df_analisis_completo.csv')

# 1. Crecimiento Acumulado 2020 a 2024 por Estado
df_2020 = df[df['anio'] == 2020].set_index('entidad')['severidad_poblacion']
df_2024 = df[df['anio'] == 2024].set_index('entidad')['severidad_poblacion']
df_growth = ((df_2024 - df_2020) / df_2020 * 100).rename('crecimiento_severidad_pct').reset_index()

# 2. Resumen por Estado
df_summary = df.groupby('entidad').agg({
    'siniestros_ocurridos_mdp': 'mean',
    'costo_total_pesos': 'mean',
    'severidad_poblacion': 'mean',
    'automoviles_registrados': 'first',
    'poblacion_2020': 'first'
}).reset_index()

df_summary = pd.merge(df_summary, df_growth, on='entidad')

# 3. Costo Promedio por Auto Registrado
df_summary['costo_por_auto_registrado'] = df_summary['costo_total_pesos'] / df_summary['automoviles_registrados']

# 4. Concentración % del Total Nacional
total_mdp = df_summary['siniestros_ocurridos_mdp'].sum()
df_summary['pct_costo_nacional'] = (df_summary['siniestros_ocurridos_mdp'] / total_mdp) * 100

# 5. Índice de Severidad Relativa (Nacional = 100)
promedio_nacional_severidad = df_summary['severidad_poblacion'].mean()
df_summary['indice_severidad'] = (df_summary['severidad_poblacion'] / promedio_nacional_severidad) * 100

df_summary = df_summary.sort_values(by='severidad_poblacion', ascending=False)

print("=== DETALLE DE LAS 4 METRICAS SIMPLES DE ALTO VALOR ===")
for idx, row in df_summary.head(5).iterrows():
    print(f"• {row['entidad']}: Severidad = ${row['severidad_poblacion']:,.2f} | Índice = {row['indice_severidad']:.1f} (Nacional=100) | Crecimiento 20-24 = +{row['crecimiento_severidad_pct']:.1f}% | Costo/Auto = ${row['costo_por_auto_registrado']:,.2f}")

print("\n=== TOP 3 ESTADOS CON MAYOR CRECIMIENTO DE SEVERIDAD (2020 vs 2024) ===")
for idx, row in df_summary.sort_values(by='crecimiento_severidad_pct', ascending=False).head(3).iterrows():
    print(f"• {row['entidad']}: Crecimiento Severidad = +{row['crecimiento_severidad_pct']:.1f}% (de 2020 a 2024)")

print("\n=== TOP 5 ESTADOS QUE CONCENTRAN EL COSTO DE SINIESTROS DE MEXICO ===")
df_top_cost = df_summary.sort_values(by='siniestros_ocurridos_mdp', ascending=False).head(5)
for idx, row in df_top_cost.iterrows():
    print(f"• {row['entidad']}: ${row['siniestros_ocurridos_mdp']:,.2f} MDP anuales ({row['pct_costo_nacional']:.1f}% del total nacional)")

print(f"\nConcentración acumulada Top 5 en costo nacional: {df_top_cost['pct_costo_nacional'].sum():.1f}%")
