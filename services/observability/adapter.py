"""Redacted trace/evaluator adapter with an optional injected LangSmith client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Mapping
from uuid import uuid4

from agent_platform.redaction import redact


@dataclass(frozen=True)
class TraceRecord:
    name: str
    attributes: Mapping[str, Any]


class RedactedTraceAdapter:
    def __init__(self, *, client: Any | None = None, console_url: str | None = None) -> None:
        self._client = client
        self.console_url = console_url
        self.records: list[TraceRecord] = []
        self.export_errors: list[str] = []

    def record(self, name: str, attributes: Mapping[str, Any]) -> None:
        safe = redact(attributes)
        self.records.append(TraceRecord(name, safe))
        if self._client is not None:
            # The injected client is an optional integration point. Only the
            # redacted record is handed to it; it never decides run state.
            callback = getattr(self._client, "record", None)
            if callable(callback):
                try:
                    callback(name, safe)
                except Exception as exc:
                    self.export_errors.append(f"{type(exc).__name__}: {exc}")

    def start_run(self, name: str, attributes: Mapping[str, Any]) -> str | None:
        if self._client is None:
            return None
        callback = getattr(self._client, "start_run", None)
        if not callable(callback):
            return None
        try:
            return callback(name, redact(attributes))
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")
            return None

    def finish_run(self, run_id: str, *, outputs: Mapping[str, Any] | None = None, error: str | None = None) -> None:
        if self._client is None or not run_id:
            return
        callback = getattr(self._client, "finish_run", None)
        if not callable(callback):
            return
        try:
            callback(run_id, outputs=redact(outputs or {}), error=redact(error) if error else None)
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")

    def evaluator(self, name: str, result: Mapping[str, Any]) -> None:
        self.record(f"evaluator.{name}", result)

    def langchain_callbacks(self) -> list[Any]:
        """Return callbacks that make LangGraph and nested LangChain runs visible."""
        if self._client is None:
            return []
        factory = getattr(self._client, "langchain_tracer", None)
        if not callable(factory):
            return []
        try:
            return [factory()]
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")
            return []

    def status(self) -> dict[str, Any]:
        if self._client is None:
            return {"enabled": False, "provider": "none", "project": None, "console_url": self.console_url}
        return {
            "enabled": True,
            "provider": "langsmith",
            "project": getattr(self._client, "project", None),
            "console_url": self.console_url,
        }


class LangSmithClientAdapter:
    """Optional trace exporter; it never owns authorization or run state."""

    def __init__(self, client: Any, *, project: str = "proposal-to-verified-change", api_url: str = "https://api.smith.langchain.com", console_url: str = "https://smith.langchain.com") -> None:
        if not callable(getattr(client, "create_run", None)):
            raise TypeError("LangSmith client must expose create_run")
        self.client = client
        self.project = project
        self.api_url = api_url
        self.console_url = console_url
        self.export_errors: list[str] = []
        self.project_ready: bool | None = None
        self._project_ensure_attempted = False

    @classmethod
    def from_env(cls, *, project: str = "proposal-to-verified-change", environment: Mapping[str, str] | None = None) -> "LangSmithClientAdapter | None":
        values = {**os.environ, **(environment or {})}
        tracing_flag = values.get("LANGSMITH_TRACING") or values.get("LANGCHAIN_TRACING_V2") or ""
        tracing_enabled = tracing_flag.lower() in {"1", "true", "yes"}
        api_key = (values.get("LANGSMITH_API_KEY") or values.get("LANGCHAIN_API_KEY") or "").strip()
        if not tracing_enabled or not api_key:
            return None
        try:
            from langsmith import Client
        except ImportError as exc:
            raise RuntimeError("langsmith is required when LANGSMITH_TRACING is enabled") from exc
        api_url = (values.get("LANGSMITH_ENDPOINT") or values.get("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com").strip().rstrip("/")
        console_url = (values.get("LANGSMITH_CONSOLE_URL") or "https://smith.langchain.com").strip().rstrip("/")
        workspace_id = (values.get("LANGSMITH_WORKSPACE_ID") or "").strip() or None
        client = Client(
            api_url=api_url,
            api_key=api_key,
            web_url=console_url,
            anonymizer=redact,
            workspace_id=workspace_id,
        )
        return cls(client, project=project, api_url=api_url, console_url=console_url)

    def langchain_tracer(self) -> Any:
        """Create a LangChain callback rooted in the configured LangSmith project."""
        from langchain_core.tracers.langchain import LangChainTracer

        return LangChainTracer(project_name=self.project, client=self.client, tags=["ai-change-impact-workbench", "langgraph"])

    def _ensure_project(self) -> None:
        if self._project_ensure_attempted:
            return
        self._project_ensure_attempted = True
        has_project = getattr(self.client, "has_project", None)
        create_project = getattr(self.client, "create_project", None)
        if not callable(create_project):
            self.project_ready = True
            return
        try:
            if callable(has_project) and has_project(project_name=self.project):
                self.project_ready = True
                return
            create_project(project_name=self.project, upsert=True)
            self.project_ready = True
        except Exception as exc:
            self.project_ready = False
            self.export_errors.append(f"project:{type(exc).__name__}: {exc}")

    def record(self, name: str, attributes: Mapping[str, Any]) -> None:
        self._ensure_project()
        try:
            self.client.create_run(
                id=uuid4(),
                name=name,
                run_type="chain",
                inputs=redact(attributes),
                outputs={"event": name},
                project_name=self.project,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
            )
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")

    def start_run(self, name: str, attributes: Mapping[str, Any]) -> str | None:
        self._ensure_project()
        run_id = str(uuid4())
        try:
            self.client.create_run(
                id=run_id,
                name=name,
                run_type="chain",
                inputs=redact(attributes),
                project_name=self.project,
                start_time=datetime.now(timezone.utc),
            )
            return run_id
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")
            return None

    def finish_run(self, run_id: str, *, outputs: Mapping[str, Any] | None = None, error: str | None = None) -> None:
        callback = getattr(self.client, "update_run", None)
        if not callable(callback):
            self.export_errors.append("RuntimeError: LangSmith client does not expose update_run")
            return
        try:
            callback(run_id, end_time=datetime.now(timezone.utc), outputs=redact(outputs or {}), error=redact(error) if error else None)
        except Exception as exc:
            self.export_errors.append(f"{type(exc).__name__}: {exc}")

    def evaluator(self, name: str, result: Mapping[str, Any]) -> None:
        self.record(f"evaluator.{name}", result)
