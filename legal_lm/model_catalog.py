from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ModelEndpoint:
    role: str
    provider: str
    default_model: str
    env_var: str
    purpose: str
    request_cap_env: str
    token_cap_env: str
    default_request_cap: int
    default_input_token_cap: int


MODEL_ENDPOINTS: Dict[str, ModelEndpoint] = {
    "extraction": ModelEndpoint(
        role="extraction",
        provider="Groq",
        default_model="llama-3.1-8b-instant",
        env_var="LEGAL_LM_EXTRACTION_MODEL",
        purpose="Document type detection, clause extraction, and JSON normalization.",
        request_cap_env="LEGAL_LM_MAX_EXTRACTION_REQUESTS",
        token_cap_env="LEGAL_LM_MAX_EXTRACTION_INPUT_TOKENS",
        default_request_cap=5,
        default_input_token_cap=5000,
    ),
    "embedding": ModelEndpoint(
        role="embedding",
        provider="Local",
        default_model="local-hash-lexical",
        env_var="LEGAL_LM_EMBEDDING_MODEL",
        purpose="Local deterministic retrieval over clauses and legal checklist references.",
        request_cap_env="LEGAL_LM_MAX_EMBEDDING_REQUESTS",
        token_cap_env="LEGAL_LM_MAX_EMBEDDING_INPUT_TOKENS",
        default_request_cap=200,
        default_input_token_cap=300000,
    ),
    "reasoning": ModelEndpoint(
        role="reasoning",
        provider="Groq",
        default_model="llama-3.3-70b-versatile",
        env_var="LEGAL_LM_REASONING_MODEL",
        purpose="Compliance reasoning, issue explanation, and clause rewrite drafting.",
        request_cap_env="LEGAL_LM_MAX_REASONING_REQUESTS",
        token_cap_env="LEGAL_LM_MAX_REASONING_INPUT_TOKENS",
        default_request_cap=6,
        default_input_token_cap=10000,
    ),
    "verifier": ModelEndpoint(
        role="verifier",
        provider="Groq",
        default_model="openai/gpt-oss-120b",
        env_var="LEGAL_LM_VERIFIER_MODEL",
        purpose="Independent second-model review of candidate findings.",
        request_cap_env="LEGAL_LM_MAX_VERIFIER_REQUESTS",
        token_cap_env="LEGAL_LM_MAX_VERIFIER_INPUT_TOKENS",
        default_request_cap=5,
        default_input_token_cap=7000,
    ),
}


def configured_model_rows(config) -> List[Dict[str, str | int | bool]]:
    limits = config.usage_limits()
    rows: List[Dict[str, str | int | bool]] = []
    for role, endpoint in MODEL_ENDPOINTS.items():
        limit = limits[role]
        rows.append(
            {
                "role": role,
                "provider": endpoint.provider,
                "model": str(limit["model"]),
                "env_var": endpoint.env_var,
                "purpose": endpoint.purpose,
                "max_requests": int(limit["max_requests"]),
                "max_input_tokens": int(limit["max_input_tokens"]),
                "request_cap_env": endpoint.request_cap_env,
                "token_cap_env": endpoint.token_cap_env,
                "free_tier_only": config.free_tier_only,
            }
        )
    return rows
