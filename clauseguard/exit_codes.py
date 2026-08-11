from __future__ import annotations

from enum import IntEnum

from clauseguard.config import ConfigError
from clauseguard.dataset_benchmark import DatasetBenchmarkError
from clauseguard.document import DocumentLoadError
from clauseguard.evaluation import EvaluationError
from clauseguard.model_router import ModelCallError, ModelTimeoutError, UsageLimitError


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIGURATION = 10
    DOCUMENT = 11
    MODEL = 12
    USAGE_LIMIT = 13
    TIMEOUT = 14
    DATA = 15
    INTERNAL = 20
    CANCELLED = 130


def classify_exception(exc: BaseException) -> tuple[ExitCode, str]:
    if isinstance(exc, ConfigError):
        return ExitCode.CONFIGURATION, "configuration_error"
    if isinstance(exc, DocumentLoadError):
        return ExitCode.DOCUMENT, "document_error"
    if isinstance(exc, UsageLimitError):
        return ExitCode.USAGE_LIMIT, "usage_limit"
    if isinstance(exc, (ModelTimeoutError, TimeoutError)):
        return ExitCode.TIMEOUT, "timeout"
    if isinstance(exc, ModelCallError):
        return ExitCode.MODEL, "model_error"
    if isinstance(exc, (DatasetBenchmarkError, EvaluationError)):
        return ExitCode.DATA, "data_error"
    if isinstance(exc, KeyboardInterrupt):
        return ExitCode.CANCELLED, "cancelled"
    return ExitCode.INTERNAL, "internal_error"
