import json
import os

import requests
from dotenv import load_dotenv


class GroqClient:
    """Small legacy adapter with invoke/query methods used by old agents."""

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        load_dotenv()
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Missing GROQ_API_KEY in environment.")
        self.api_key = api_key
        self.model_name = model_name

    def invoke(self, input_text: str):
        return self.query(prompt=input_text)

    def query(self, system_prompt: str | None = None, prompt: str | None = None):
        user_prompt = prompt if prompt is not None else system_prompt or ""
        system = system_prompt if prompt is not None else "You are a legal document analysis assistant."
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
        }
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Groq call failed ({response.status_code}): {response.text[:500]}")
        data = response.json()
        return data["choices"][0]["message"]["content"]
