"""
Conversational AI — Base LLMProvider, MockLlama3Provider & OllamaProvider.
"""

import json
import urllib.request


class LLMProvider:
    """Interfaz base para proveedores de LLM (Llama-3, Ollama, API, etc.)."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class MockLlama3Provider(LLMProvider):
    """Proveedor simulado para pruebas de integración grounded."""
    def __init__(self, hallucinate: bool = False):
        self.hallucinate = hallucinate

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if self.hallucinate:
            return "[Llama-3 Alucinación]: La severidad en este estado es de $999,999.00 MXN y 99.9% de riesgo."
        return f"[Llama-3 Grounded Response]\n{user_prompt}"


class OllamaProvider(LLMProvider):
    """Conector real con servidor local o remoto Ollama (Llama-3)."""
    def __init__(self, model: str = "llama3:8b", endpoint: str = "http://localhost:11434/api/generate", timeout: float = 15.0):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False
        }
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.endpoint, data=data_bytes, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result.get("response", "")
        except Exception as e:
            raise ConnectionError(f"Error al conectar con servidor Ollama Llama-3: {e}") from e

