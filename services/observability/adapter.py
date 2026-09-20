"""Redacted trace/evaluator adapter with an optional LangSmith client."""

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


class LangSmithClientAdapter:
    """Small LangSmith SDK adapter that only receives already-redacted data."""

    def __init__(self, client: Any, *, project: str = "proposal-to-verified-change") -> None:
        if not callable(getattr(client, "create_run", None)):
            raise TypeError("LangSmith client must expose create_run")
        self.client = client
        self.project = project

    @classmethod
    def from_env(cls, *, project: str = "proposal-to-verified-change") -> "LangSmithClientAdapter | None":
        import os

        if os.getenv("LANGSMITH_TRACING", "").lower() not in {"1", "true", "yes"} or not os.getenv("LANGSMITH_API_KEY"):
            return None
        try:
            from langsmith import Client
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("langsmith is required when LANGSMITH_TRACING is enabled") from exc
        return cls(Client(), project=project)

    def record(self, name: str, attributes: Mapping[str, Any]) -> None:
        safe = redact(attributes)
        self.client.create_run(name=name, run_type="chain", inputs=safe, outputs={"event": name}, project_name=self.project)

    def evaluator(self, name: str, result: Mapping[str, Any]) -> None:
        self.record(f"evaluator.{name}", result)
