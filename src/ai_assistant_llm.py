"""
Asistente de Análisis Actuarial con Arquitectura Grounded (Llama-3 & Python)
Implementa:
- Validación de esquema, integridad y consistencia (Fase 1)
- Catálogo de métricas y alias de entidades N-estatal (Fase 2)
- Separación de contexto confirmado vs interpretaciones pendientes (Fase 3)
- Motor de operaciones actuariales sin cifras hardcodeadas (Fase 4)
- Generación de JSON estructurado y validación previa a la ejecución (Fase 5)
"""

from llm_grounding import GroundedActuarialAssistant, MockLlama3Provider
from actuarial_core import ActuarialCatalog, ActuarialDataValidator

class LlamaColabDataAgent:
    """
    Agente Actuarial Grounded con soporte para Llama-3.
    Mantiene compatibilidad con notebooks y suites de benchmark,
    delegando en el motor validado GroundedActuarialAssistant.
    """
    def __init__(self, data_path: str = '/Users/victordaniel/chubb/data.json'):
        self.assistant = GroundedActuarialAssistant(data_path=data_path)
        self.catalog = self.assistant.catalog
        self.engine = self.assistant.engine
        self.memory = self.assistant.memory

    def process_query(self, user_question: str) -> str:
        return self.assistant.ask(user_question)

    def query(self, user_question: str) -> str:
        return self.process_query(user_question)

if __name__ == "__main__":
    agent = LlamaColabDataAgent()
    print("=== TEST LlamaColabDataAgent (Grounded Architecture) ===")
    print(agent.process_query("Tres hallazgos clave"))
    print("-" * 50)
    print(agent.process_query("Compara Jalisco, Nuevo León, CDMX y Puebla"))
    print("-" * 50)
    print(agent.process_query("¿Y en 2024?"))
