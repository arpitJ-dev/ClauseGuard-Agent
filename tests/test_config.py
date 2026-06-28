import pytest

from legal_lm.config import AppConfig, ConfigError


def test_free_tier_only_blocks_unapproved_models():
    config = AppConfig(
        groq_api_key="groq-key",
        free_tier_only=True,
        reasoning_model="paid-or-unknown-model",
        mock_models=False,
    )

    with pytest.raises(ConfigError):
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
    assert reasoning_limit["max_input_tokens"] == 10000
