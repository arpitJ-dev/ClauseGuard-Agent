import pytest

from legal_lm.config import AppConfig
from legal_lm.model_router import UsageLimitError, UsageLimiter


def test_usage_limiter_blocks_request_over_cap():
    limiter = UsageLimiter(
        AppConfig(
            groq_api_key="groq-key",
            max_reasoning_requests=1,
            mock_models=False,
        )
    )

    limiter.reserve("reasoning", "first prompt")

    with pytest.raises(UsageLimitError):
        limiter.reserve("reasoning", "second prompt")


def test_usage_limiter_blocks_estimated_token_over_cap():
    limiter = UsageLimiter(
        AppConfig(
            groq_api_key="groq-key",
            max_verifier_input_tokens=2,
            mock_models=False,
        )
    )

    with pytest.raises(UsageLimitError):
        limiter.reserve("verifier", "this prompt is longer than eight characters")
