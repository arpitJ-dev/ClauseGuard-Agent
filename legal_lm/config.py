from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Set

from dotenv import load_dotenv

from legal_lm.model_catalog import MODEL_ENDPOINTS


class ConfigError(RuntimeError):
    """Raised when the project is configured in a way that can incur cost or fail."""


GROQ_FREE_PLAN_MODELS: Set[str] = {
    "allam-2-7b",
    "groq/compound",
    "groq/compound-mini",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "qwen/qwen3.6-27b",
}

LOCAL_EMBEDDING_MODELS: Set[str] = {
    "local-hash-lexical",
    "local-hash-embedding",
}

MODEL_USAGE_CEILINGS: dict[str, dict[str, int]] = {
    "allam-2-7b": {"max_requests": 30, "max_input_tokens": 5000},
    "groq/compound": {"max_requests": 30, "max_input_tokens": 60000},
    "groq/compound-mini": {"max_requests": 30, "max_input_tokens": 60000},
    "llama-3.1-8b-instant": {"max_requests": 30, "max_input_tokens": 5000},
    "llama-3.3-70b-versatile": {"max_requests": 30, "max_input_tokens": 10000},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"max_requests": 30, "max_input_tokens": 25000},
    "openai/gpt-oss-20b": {"max_requests": 30, "max_input_tokens": 7000},
    "openai/gpt-oss-120b": {"max_requests": 30, "max_input_tokens": 7000},
    "qwen/qwen3-32b": {"max_requests": 60, "max_input_tokens": 5000},
    "qwen/qwen3.6-27b": {"max_requests": 30, "max_input_tokens": 7000},
    "local-hash-lexical": {"max_requests": 100000, "max_input_tokens": 1000000},
    "local-hash-embedding": {"max_requests": 100000, "max_input_tokens": 1000000},
}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(name: str, value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if parsed < 1:
        raise ConfigError(f"{name} must be at least 1.")
    return parsed


@dataclass(frozen=True)
class AppConfig:
    groq_api_key: str | None
    free_tier_only: bool = True
    extraction_model: str = MODEL_ENDPOINTS["extraction"].default_model
    reasoning_model: str = MODEL_ENDPOINTS["reasoning"].default_model
    embedding_model: str = MODEL_ENDPOINTS["embedding"].default_model
    verifier_model: str = MODEL_ENDPOINTS["verifier"].default_model
    mock_models: bool = False
    max_extraction_requests: int = MODEL_ENDPOINTS["extraction"].default_request_cap
    max_extraction_input_tokens: int = MODEL_ENDPOINTS["extraction"].default_input_token_cap
    max_reasoning_requests: int = MODEL_ENDPOINTS["reasoning"].default_request_cap
    max_reasoning_input_tokens: int = MODEL_ENDPOINTS["reasoning"].default_input_token_cap
    max_embedding_requests: int = MODEL_ENDPOINTS["embedding"].default_request_cap
    max_embedding_input_tokens: int = MODEL_ENDPOINTS["embedding"].default_input_token_cap
    max_verifier_requests: int = MODEL_ENDPOINTS["verifier"].default_request_cap
    max_verifier_input_tokens: int = MODEL_ENDPOINTS["verifier"].default_input_token_cap

    @classmethod
    def from_env(cls, mock_models: bool = False) -> "AppConfig":
        load_dotenv()
        config = cls(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            free_tier_only=_as_bool(os.getenv("FREE_TIER_ONLY"), True),
            extraction_model=os.getenv(
                "LEGAL_LM_EXTRACTION_MODEL",
                MODEL_ENDPOINTS["extraction"].default_model,
            ),
            reasoning_model=os.getenv(
                "LEGAL_LM_REASONING_MODEL",
                MODEL_ENDPOINTS["reasoning"].default_model,
            ),
            embedding_model=os.getenv(
                "LEGAL_LM_EMBEDDING_MODEL",
                MODEL_ENDPOINTS["embedding"].default_model,
            ),
            verifier_model=os.getenv(
                "LEGAL_LM_VERIFIER_MODEL",
                MODEL_ENDPOINTS["verifier"].default_model,
            ),
            mock_models=mock_models or _as_bool(os.getenv("LEGAL_LM_MOCK_MODELS"), False),
            max_extraction_requests=_as_int(
                "LEGAL_LM_MAX_EXTRACTION_REQUESTS",
                os.getenv("LEGAL_LM_MAX_EXTRACTION_REQUESTS"),
                MODEL_ENDPOINTS["extraction"].default_request_cap,
            ),
            max_extraction_input_tokens=_as_int(
                "LEGAL_LM_MAX_EXTRACTION_INPUT_TOKENS",
                os.getenv("LEGAL_LM_MAX_EXTRACTION_INPUT_TOKENS"),
                MODEL_ENDPOINTS["extraction"].default_input_token_cap,
            ),
            max_reasoning_requests=_as_int(
                "LEGAL_LM_MAX_REASONING_REQUESTS",
                os.getenv("LEGAL_LM_MAX_REASONING_REQUESTS"),
                MODEL_ENDPOINTS["reasoning"].default_request_cap,
            ),
            max_reasoning_input_tokens=_as_int(
                "LEGAL_LM_MAX_REASONING_INPUT_TOKENS",
                os.getenv("LEGAL_LM_MAX_REASONING_INPUT_TOKENS"),
                MODEL_ENDPOINTS["reasoning"].default_input_token_cap,
            ),
            max_embedding_requests=_as_int(
                "LEGAL_LM_MAX_EMBEDDING_REQUESTS",
                os.getenv("LEGAL_LM_MAX_EMBEDDING_REQUESTS"),
                MODEL_ENDPOINTS["embedding"].default_request_cap,
            ),
            max_embedding_input_tokens=_as_int(
                "LEGAL_LM_MAX_EMBEDDING_INPUT_TOKENS",
                os.getenv("LEGAL_LM_MAX_EMBEDDING_INPUT_TOKENS"),
                MODEL_ENDPOINTS["embedding"].default_input_token_cap,
            ),
            max_verifier_requests=_as_int(
                "LEGAL_LM_MAX_VERIFIER_REQUESTS",
                os.getenv("LEGAL_LM_MAX_VERIFIER_REQUESTS"),
                MODEL_ENDPOINTS["verifier"].default_request_cap,
            ),
            max_verifier_input_tokens=_as_int(
                "LEGAL_LM_MAX_VERIFIER_INPUT_TOKENS",
                os.getenv("LEGAL_LM_MAX_VERIFIER_INPUT_TOKENS"),
                MODEL_ENDPOINTS["verifier"].default_input_token_cap,
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.free_tier_only:
            disallowed = []
            if self.extraction_model not in GROQ_FREE_PLAN_MODELS:
                disallowed.append(("extraction", self.extraction_model))
            if self.reasoning_model not in GROQ_FREE_PLAN_MODELS:
                disallowed.append(("reasoning", self.reasoning_model))
            if self.embedding_model not in LOCAL_EMBEDDING_MODELS:
                disallowed.append(("embedding", self.embedding_model))
            if self.verifier_model not in GROQ_FREE_PLAN_MODELS:
                disallowed.append(("verifier", self.verifier_model))
            if disallowed:
                rendered = ", ".join(f"{role}={model}" for role, model in disallowed)
                raise ConfigError(
                    "FREE_TIER_ONLY=true blocks non-approved model configuration: "
                    f"{rendered}. Use an approved Groq free-plan model for generation "
                    "roles and a local embedding model, or explicitly set "
                    "FREE_TIER_ONLY=false after reviewing provider billing settings."
                )

        if self.mock_models:
            return

        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if missing:
            raise ConfigError(
                "Missing required model provider API key(s): "
                f"{', '.join(missing)}. Set them in .env, or run tests/demo with --mock-models."
            )

    def usage_limits(self) -> dict[str, dict[str, int | str]]:
        return {
            "extraction": self._capped_limit(
                self.extraction_model,
                self.max_extraction_requests,
                self.max_extraction_input_tokens,
            ),
            "reasoning": self._capped_limit(
                self.reasoning_model,
                self.max_reasoning_requests,
                self.max_reasoning_input_tokens,
            ),
            "embedding": self._capped_limit(
                self.embedding_model,
                self.max_embedding_requests,
                self.max_embedding_input_tokens,
            ),
            "verifier": self._capped_limit(
                self.verifier_model,
                self.max_verifier_requests,
                self.max_verifier_input_tokens,
            ),
        }

    def _capped_limit(self, model: str, requested_requests: int, requested_tokens: int) -> dict[str, int | str]:
        ceiling = MODEL_USAGE_CEILINGS.get(model, {"max_requests": requested_requests, "max_input_tokens": requested_tokens})
        return {
            "model": model,
            "max_requests": min(requested_requests, ceiling["max_requests"]),
            "max_input_tokens": min(requested_tokens, ceiling["max_input_tokens"]),
        }
