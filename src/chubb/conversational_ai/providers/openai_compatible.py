"""
Conversational AI — OpenAICompatibleProvider (vLLM, Groq, Colab, Databricks Model Serving).
"""

import json
import urllib.request
from chubb.conversational_ai.providers.ollama import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Conector para endpoints compatibles con OpenAI (vLLM, Groq, Colab, etc.)."""
    def __init__(self, api_url: str, api_key: str = "EMPTY", model: str = "llama-3-8b-instruct", timeout: float = 15.0):
        self.api_url = api_url.rstrip('/') + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0
        }
        data_bytes = json.dumps(payload).encode('utf-8')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        req = urllib.request.Request(self.api_url, data=data_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result["choices"][0]["message"]["content"]

