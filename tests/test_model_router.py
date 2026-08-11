import pytest
import requests

from clauseguard.config import AppConfig
from clauseguard.model_router import (
    ModelResponseError,
    ModelRouter,
    ModelTimeoutError,
    UsageLimitError,
)


def test_generate_json_raises_clear_error_for_malformed_model_output(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))

    monkeypatch.setattr(router, "_groq_chat", lambda *args, **kwargs: "not json")

    with pytest.raises(ModelResponseError, match="non-JSON output"):
        router.generate_json("reasoning", "Return JSON.", "Test prompt.")


def test_unknown_model_role_is_rejected():
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))

    with pytest.raises(ValueError, match="Unknown model role"):
        router.generate_text("unknown-role", "system", "prompt")


def test_local_embedding_is_deterministic_and_lexically_meaningful():
    router = ModelRouter(AppConfig(groq_api_key=None, mock_models=True))
    contract = "termination requires thirty days written notice and a cure period"
    related = "written termination notice must provide a thirty day cure period"
    unrelated = "invoice taxes are payable by electronic bank transfer"

    contract_vector, repeated, related_vector, unrelated_vector = router.embed_texts(
        [contract, contract, related, unrelated]
    )

    assert contract_vector == repeated
    related_similarity = sum(a * b for a, b in zip(contract_vector, related_vector))
    unrelated_similarity = sum(a * b for a, b in zip(contract_vector, unrelated_vector))
    assert related_similarity > unrelated_similarity


class _FakeResponse:
    status_code = 200
    text = "not-json"

    def json(self):
        raise ValueError("invalid JSON")


def test_groq_non_json_http_response_has_clear_error(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))
    monkeypatch.setattr(
        "clauseguard.model_router.requests.post", lambda *args, **kwargs: _FakeResponse()
    )

    with pytest.raises(ModelResponseError, match="non-JSON HTTP response"):
        router.generate_text("reasoning", "system", "prompt")


def test_groq_timeout_has_distinct_error(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))

    def raise_timeout(*_args, **_kwargs):
        raise requests.Timeout("request timed out")

    monkeypatch.setattr("clauseguard.model_router.requests.post", raise_timeout)

    with pytest.raises(ModelTimeoutError, match="timed out"):
        router.generate_text("reasoning", "system", "prompt")


def test_groq_rate_limit_has_usage_limit_error(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))

    class FakeResponse:
        status_code = 429
        text = "rate limited"

    monkeypatch.setattr(
        "clauseguard.model_router.requests.post", lambda *_args, **_kwargs: FakeResponse()
    )

    with pytest.raises(UsageLimitError, match="rate limit"):
        router.generate_text("reasoning", "system", "prompt")
