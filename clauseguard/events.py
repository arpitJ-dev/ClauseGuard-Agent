from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Literal, TextIO

from pydantic import BaseModel, Field

EVENT_SCHEMA_VERSION: Literal["1.0"] = "1.0"

PipelineStage = Literal[
    "queued",
    "loading",
    "extracting",
    "retrieving",
    "checking",
    "verifying",
    "scoring",
    "rewriting",
    "comparing",
    "reporting",
    "completed",
    "failed",
]
ProgressStatus = Literal["queued", "started", "completed", "failed"]
EventType = Literal["progress", "completed", "error"]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PipelineProgress(BaseModel):
    stage: PipelineStage
    status: ProgressStatus
    progress: int = Field(ge=0, le=100)
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class EventError(BaseModel):
    code: str
    message: str


class ProgressEvent(BaseModel):
    schema_version: Literal["1.0"] = EVENT_SCHEMA_VERSION
    run_id: str
    sequence: int = Field(ge=1)
    type: EventType
    stage: PipelineStage
    status: ProgressStatus
    progress: int = Field(ge=0, le=100)
    message: str
    timestamp: str = Field(default_factory=utc_timestamp)
    details: Dict[str, Any] = Field(default_factory=dict)
    error: EventError | None = None


ProgressCallback = Callable[[PipelineProgress], None]


class JsonLineEventWriter:
    """Writes a versioned, flush-on-write NDJSON event stream."""

    def __init__(self, stream: TextIO, run_id: str):
        self.stream = stream
        self.run_id = run_id
        self.sequence = 0

    def progress(self, update: PipelineProgress) -> None:
        event_type: EventType = "completed" if update.stage == "completed" else "progress"
        self.emit(
            event_type=event_type,
            stage=update.stage,
            status=update.status,
            progress=update.progress,
            message=update.message,
            details=update.details,
        )

    def completed(self, message: str, details: Dict[str, Any] | None = None) -> ProgressEvent:
        return self.emit(
            event_type="completed",
            stage="completed",
            status="completed",
            progress=100,
            message=message,
            details=details,
        )

    def failed(
        self,
        code: str,
        message: str,
        *,
        details: Dict[str, Any] | None = None,
    ) -> ProgressEvent:
        return self.emit(
            event_type="error",
            stage="failed",
            status="failed",
            progress=100,
            message=message,
            details=details,
            error=EventError(code=code, message=message),
        )

    def emit(
        self,
        *,
        event_type: EventType,
        stage: PipelineStage,
        status: ProgressStatus,
        progress: int,
        message: str,
        details: Dict[str, Any] | None = None,
        error: EventError | None = None,
    ) -> ProgressEvent:
        self.sequence += 1
        event = ProgressEvent(
            run_id=self.run_id,
            sequence=self.sequence,
            type=event_type,
            stage=stage,
            status=status,
            progress=progress,
            message=message,
            details=details or {},
            error=error,
        )
        self.stream.write(event.model_dump_json() + "\n")
        self.stream.flush()
        return event


def notify(
    callback: ProgressCallback | None,
    stage: PipelineStage,
    status: ProgressStatus,
    progress: int,
    message: str,
    **details: Any,
) -> None:
    if callback is None:
        return
    callback(
        PipelineProgress(
            stage=stage,
            status=status,
            progress=progress,
            message=message,
            details=details,
        )
    )
