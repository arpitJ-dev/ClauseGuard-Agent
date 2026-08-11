from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Iterable, List

import requests

from clauseguard.config import AppConfig
from clauseguard.json_utils import parse_json_object


class ModelCallError(RuntimeError):
    pass


class ModelResponseError(ModelCallError):
    pass


class UsageLimitError(ModelCallError):
    pass


class ModelTimeoutError(ModelCallError):
    pass


class UsageLimiter:
    """Per-run request and estimated input-token guard for cloud model calls."""

    def __init__(self, config: AppConfig):
        self.limits = config.usage_limits()
        self.usage: Dict[str, Dict[str, int]] = {
            endpoint: {"requests": 0, "input_tokens": 0} for endpoint in self.limits
        }

    def reserve(self, endpoint: str, text: str, request_count: int = 1) -> None:
        estimated_tokens = self._estimate_tokens(text)
        limit = self.limits[endpoint]
        current = self.usage[endpoint]
        next_requests = current["requests"] + request_count
        next_tokens = current["input_tokens"] + estimated_tokens

        if next_requests > int(limit["max_requests"]):
            raise UsageLimitError(
                f"Usage cap reached for {endpoint} model {limit['model']}: "
                f"{next_requests}/{limit['max_requests']} requests. Increase the "
                f"CLAUSEGUARD_MAX_{endpoint.upper()}_REQUESTS cap only if you have verified free quota."
            )
        if next_tokens > int(limit["max_input_tokens"]):
            raise UsageLimitError(
                f"Usage cap reached for {endpoint} model {limit['model']}: "
                f"estimated {next_tokens}/{limit['max_input_tokens']} input tokens. Increase the "
                f"CLAUSEGUARD_MAX_{endpoint.upper()}_INPUT_TOKENS cap only if you have verified free quota."
            )

        current["requests"] = next_requests
        current["input_tokens"] = next_tokens

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        return {endpoint: dict(values) for endpoint, values in self.usage.items()}

    def _estimate_tokens(self, text: str) -> int:
        return max(1, math.ceil(len(text) / 4))


class ModelRouter:
    """Routes model calls through Groq generation endpoints and local retrieval."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.usage_limiter = UsageLimiter(config)

    def generate_json(self, role: str, system_prompt: str, prompt: str) -> Dict[str, Any]:
        if self.config.mock_models:
            return self._mock_json(role)

        endpoint = self._endpoint_for_role(role)
        self._reserve_generation(endpoint, system_prompt, prompt)
        raw = self._groq_chat(
            self._model_for_endpoint(endpoint), system_prompt, prompt, json_mode=True
        )

        try:
            return parse_json_object(raw)
        except Exception as exc:
            raise ModelResponseError(f"{role} model returned non-JSON output: {raw[:500]}") from exc

    def generate_text(self, role: str, system_prompt: str, prompt: str) -> str:
        if self.config.mock_models:
            return self._mock_text(role)

        endpoint = self._endpoint_for_role(role)
        self._reserve_generation(endpoint, system_prompt, prompt)
        return self._groq_chat(self._model_for_endpoint(endpoint), system_prompt, prompt)

    def embed_texts(self, texts: Iterable[str]) -> List[List[float]]:
        text_list = list(texts)
        return [self._hash_embedding(text) for text in text_list]

    def _groq_chat(
        self,
        model_name: str,
        system_prompt: str,
        prompt: str,
        json_mode: bool = False,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.config.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
        except requests.Timeout as exc:
            raise ModelTimeoutError(f"Groq call timed out for {model_name}.") from exc
        except requests.RequestException as exc:
            raise ModelCallError(f"Groq call failed for {model_name}: {exc}") from exc

        if response.status_code == 429:
            raise UsageLimitError(
                f"Groq rate limit was reached for {model_name}. Retry later, lower local caps, "
                "or use --mock-models."
            )
        if response.status_code >= 400:
            raise ModelCallError(
                f"Groq call failed for {model_name} ({response.status_code}): "
                f"{response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ModelResponseError(
                f"Groq returned a non-JSON HTTP response for {model_name}."
            ) from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelResponseError(
                f"Groq returned an unexpected response structure for {model_name}."
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelResponseError(f"Groq returned empty content for {model_name}.")
        return content

    def _endpoint_for_role(self, role: str) -> str:
        role_to_endpoint = {
            "extraction": "extraction",
            "reasoning": "reasoning",
            "rewrite": "reasoning",
            "verifier": "verifier",
        }
        try:
            return role_to_endpoint[role]
        except KeyError as exc:
            raise ValueError(f"Unknown model role: {role}") from exc

    def _model_for_endpoint(self, endpoint: str) -> str:
        if endpoint == "extraction":
            return self.config.extraction_model
        if endpoint == "verifier":
            return self.config.verifier_model
        return self.config.reasoning_model

    def _mock_json(self, role: str) -> Dict[str, Any]:
        if role == "extraction":
            return {}
        if role == "verifier":
            return {"verifications": []}
        return {"findings": []}

    def _mock_text(self, role: str) -> str:
        return "{}"

    def _hash_embedding(self, text: str, size: int = 64) -> List[float]:
        """Build a deterministic feature-hashed lexical vector.

        This is deliberately local and dependency-free. Token and bigram counts
        make related contract language comparable while preserving deterministic
        test and benchmark behavior.
        """

        tokens = re.findall(r"[a-z0-9]+", text.lower())
        if not tokens:
            return [0.0] * size

        features = [(token, 1.0) for token in tokens]
        features.extend((f"{left}::{right}", 0.75) for left, right in zip(tokens, tokens[1:]))

        values = [0.0] * size
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, byteorder="big") % size
            values[index] += weight

        norm = math.sqrt(sum(value * value for value in values))
        if not norm:
            return values
        return [value / norm for value in values]

    def _reserve_generation(self, endpoint: str, system_prompt: str, prompt: str) -> None:
        self.usage_limiter.reserve(endpoint, f"{system_prompt}\n{prompt}", request_count=1)
