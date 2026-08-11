from clauseguard.config import ConfigError
from clauseguard.document import DocumentLoadError
from clauseguard.exit_codes import ExitCode, classify_exception
from clauseguard.model_router import ModelCallError, ModelTimeoutError, UsageLimitError


def test_operational_errors_have_stable_exit_codes():
    cases = [
        (ConfigError("bad config"), ExitCode.CONFIGURATION, "configuration_error"),
        (DocumentLoadError("bad document"), ExitCode.DOCUMENT, "document_error"),
        (ModelCallError("provider failed"), ExitCode.MODEL, "model_error"),
        (UsageLimitError("cap reached"), ExitCode.USAGE_LIMIT, "usage_limit"),
        (ModelTimeoutError("timed out"), ExitCode.TIMEOUT, "timeout"),
        (RuntimeError("unexpected"), ExitCode.INTERNAL, "internal_error"),
    ]

    for error, expected_exit, expected_code in cases:
        exit_code, error_code = classify_exception(error)
        assert exit_code == expected_exit
        assert error_code == expected_code
