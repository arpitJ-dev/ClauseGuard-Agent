from legal_lm.config import AppConfig
from legal_lm.model_catalog import MODEL_ENDPOINTS, configured_model_rows


def test_model_catalog_contains_required_roles():
    assert set(MODEL_ENDPOINTS) == {"extraction", "embedding", "reasoning", "verifier"}
    assert MODEL_ENDPOINTS["extraction"].default_model == "llama-3.1-8b-instant"
    assert MODEL_ENDPOINTS["reasoning"].default_model == "llama-3.3-70b-versatile"
    assert MODEL_ENDPOINTS["embedding"].default_model == "local-hash-lexical"
    assert MODEL_ENDPOINTS["verifier"].default_model == "openai/gpt-oss-120b"


def test_configured_model_rows_include_caps():
    rows = configured_model_rows(AppConfig(groq_api_key=None, mock_models=True))

    assert len(rows) == 4
    assert all(row["max_requests"] > 0 for row in rows)
    assert all(row["max_input_tokens"] > 0 for row in rows)
