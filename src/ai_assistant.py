import pandas as pd
import numpy as np
import unicodedata

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn').lower().strip()

class InsuranceSeverityAIAssistant:
    """
    Asistente de IA de Consulta en Lenguaje Natural para el Dataset de Severidad de Siniestros (Chubb/INEGI).
    """
    def __init__(self, data_path='/Users/victordaniel/chubb/output/df_analisis_completo.csv'):
        self.df = pd.read_csv(data_path)
        self.nacional_avg = self.df['severidad_poblacion'].mean()
        self.df['entidad_norm'] = self.df['entidad'].apply(normalize_text)

    def query(self, question: str) -> str:
        q_norm = normalize_text(question)
        
        # 1. Top estados por severidad
        if any(k in q_norm for k in ["top", "mayor severidad", "mas severos", "mas alto", "mas costosos"]):
            if "2024" in q_norm:
                sub_df = self.df[self.df['anio'] == 2024].sort_values(by='severidad_poblacion', ascending=False).head(3)
                periodo = "en el año 2024"
            else:
                sub_df = self.df.groupby('entidad').agg({'severidad_poblacion': 'mean', 'siniestros_ocurridos_mdp': 'mean'}).reset_index().sort_values(by='severidad_poblacion', ascending=False).head(3)
                periodo = "en el promedio 2020-2024"
                
            res = f"🤖 **Respuesta IA**: Los 3 estados con mayor severidad {periodo} son:\n"
            for idx, r in sub_df.reset_index().iterrows():
                res += f"  {idx+1}. **{r['entidad']}**: Severidad = ${r['severidad_poblacion']:,.2f} MXN (Costo medio: ${r['siniestros_ocurridos_mdp']:,.2f} MDP)\n"
            return res
            
        # 2. Crecimiento de severidad
        elif any(k in q_norm for k in ["crecimiento", "aumento", "tendencia", "duplicaron"]):
            df_2020 = self.df[self.df['anio'] == 2020].set_index('entidad')['severidad_poblacion']
            df_2024 = self.df[self.df['anio'] == 2024].set_index('entidad')['severidad_poblacion']
            df_g = ((df_2024 - df_2020) / df_2020 * 100).sort_values(ascending=False).head(3)
            
            res = "🤖 **Respuesta IA**: Los 3 estados con mayor crecimiento acumulado en severidad (2020 a 2024) son:\n"
            for ent, val in df_g.items():
                res += f"  • **{ent}**: +{val:.1f}% de incremento en severidad\n"
            return res

        # 3. Variables de impacto / Correlación
        elif any(k in q_norm for k in ["variable", "impacto", "factor", "correlacion", "afectan"]):
            corr = self.df.groupby('entidad').agg({
                'severidad_poblacion': 'mean',
                'precio_promedio_auto_ml_k_mxn': 'first',
                'autos_por_1000_hab': 'first',
                'automoviles_registrados': 'first'
            }).corr()['severidad_poblacion'].sort_values(ascending=False)
            
            res = "🤖 **Respuesta IA**: Las 3 variables con mayor impacto en la severidad son:\n"
            res += f"  1. **Precio Promedio del Auto (Mercado Libre)**: Correlación r = {corr['precio_promedio_auto_ml_k_mxn']:+.4f} (Muy Fuerte)\n"
            res += f"  2. **Motorización (Autos por 1,000 hab)**: Correlación r = {corr['autos_por_1000_hab']:+.4f} (Fuerte)\n"
            res += f"  3. **Volumen de Parque Vehicular Registrado**: Correlación r = {corr['automoviles_registrados']:+.4f} (Moderada)\n"
            return res

        # 4. Consulta por Estado Específico
        state_match = None
        for ent in self.df['entidad'].unique():
            if normalize_text(ent) in q_norm:
                state_match = ent
                break
                
        if state_match:
            sub = self.df[self.df['entidad'] == state_match]
            avg_sev = sub['severidad_poblacion'].mean()
            idx_rel = (avg_sev / self.nacional_avg) * 100
            total_mdp = sub['siniestros_ocurridos_mdp'].mean()
            
            res = f"🤖 **Respuesta IA**: Ficha actuarial para **{state_match}**:\n"
            res += f"  • Severidad Promedio (2020-2024): ${avg_sev:,.2f} MXN\n"
            res += f"  • Índice de Severidad Relativa: {idx_rel:.1f} pts (Promedio Nacional = 100)\n"
            res += f"  • Costo Promedio Anual de Siniestros: ${total_mdp:,.2f} MDP\n"
            res += f"  • Severidad en 2024: ${sub[sub['anio']==2024]['severidad_poblacion'].values[0]:,.2f} MXN\n"
            return res
            
        return "🤖 **Respuesta IA**: Puedo responder consultas sobre severidad estatal, crecimiento 2020-2024, variables de impacto y métricas específicas por estado."

if __name__ == "__main__":
    ai = InsuranceSeverityAIAssistant()
    print("=== DEMO ASISTENTE DE IA DE CONSULTA ACTUARIAL ===")
    print(ai.query("¿Cuáles son los estados con mayor severidad?"))
    print(ai.query("¿Qué variables afectan la severidad?"))
    print(ai.query("Dame la información de Nuevo León"))
    print(ai.query("¿Qué estados tienen mayor crecimiento de severidad?"))
