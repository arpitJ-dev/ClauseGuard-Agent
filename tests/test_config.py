import pytest

from clauseguard.config import AppConfig, ConfigError


def test_free_tier_only_blocks_unapproved_models():
    config = AppConfig(
        groq_api_key="groq-key",
        free_tier_only=True,
        reasoning_model="paid-or-unknown-model",
        mock_models=False,
    )

    with pytest.raises(ConfigError):
        config.validate()


@pytest.mark.parametrize(
    ("field", "model"),
    [
        ("extraction_model", "llama-3.1-8b-instant"),
        ("reasoning_model", "llama-3.3-70b-versatile"),
    ],
)
def test_deprecated_default_models_are_rejected(field: str, model: str):
    config = AppConfig(
        groq_api_key="groq-key",
        free_tier_only=True,
        mock_models=False,
        **{field: model},
    )

    with pytest.raises(ConfigError, match="blocks non-approved model"):
        config.validate()


def test_mock_models_do_not_require_api_keys():
    config = AppConfig(groq_api_key=None, mock_models=True)

    config.validate()


def test_real_models_require_groq_api_key():
    config = AppConfig(groq_api_key=None, mock_models=False)

    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        config.validate()


def test_usage_limits_are_clamped_to_model_ceiling():
    config = AppConfig(
        groq_api_key="groq-key",
        max_reasoning_requests=999,
        max_reasoning_input_tokens=999999,
        mock_models=False,
    )

    reasoning_limit = config.usage_limits()["reasoning"]
    assert reasoning_limit["max_requests"] == 30
    assert reasoning_limit["max_input_tokens"] == 7000
