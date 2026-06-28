import pytest

from legal_lm.config import AppConfig
from legal_lm.model_router import ModelResponseError, ModelRouter


def test_generate_json_raises_clear_error_for_malformed_model_output(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))

    monkeypatch.setattr(router, "_groq_chat", lambda *args, **kwargs: "not json")

    with pytest.raises(ModelResponseError, match="non-JSON output"):
        router.generate_json("reasoning", "Return JSON.", "Test prompt.")
