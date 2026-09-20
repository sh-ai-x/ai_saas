"""Redacted trace/evaluator adapter with an optional injected LangSmith client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_platform.redaction import redact


@dataclass(frozen=True)
class TraceRecord:
    name: str
    attributes: Mapping[str, Any]


class RedactedTraceAdapter:
    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client
        self.records: list[TraceRecord] = []

    def record(self, name: str, attributes: Mapping[str, Any]) -> None:
        safe = redact(attributes)
        self.records.append(TraceRecord(name, safe))
        if self._client is not None:
            # The injected client is an optional integration point. Only the
            # redacted record is handed to it; it never decides run state.
            callback = getattr(self._client, "record", None)
            if callable(callback):
                callback(name, safe)

    def evaluator(self, name: str, result: Mapping[str, Any]) -> None:
        self.record(f"evaluator.{name}", result)

