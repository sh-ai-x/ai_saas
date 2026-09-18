"""Bounded workflow dispatch contracts with no browser-to-worker coupling."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol


class WorkflowDispatcher(Protocol):
    def dispatch(self, request: Mapping[str, str]) -> None:
        ...


class InngestDispatcher:
    """Small adapter around an injected Inngest sender.

    The sender receives only identifiers and limits; the worker reads the
    immutable input from the run store.  This keeps prompts out of events.
    """

    def __init__(
        self,
        send: Callable[[Mapping[str, object]], None],
        *,
        max_steps: int = 8,
        max_model_calls: int = 8,
        max_runtime_seconds: float = 300.0,
    ) -> None:
        if not 0 < max_steps <= 32 or not 0 < max_model_calls <= 32:
            raise ValueError("workflow limits must be between 1 and 32")
        if not 0 < max_runtime_seconds <= 900:
            raise ValueError("workflow runtime must be between 0 and 900 seconds")
        self._send = send
        self.max_steps = max_steps
        self.max_model_calls = max_model_calls
        self.max_runtime_seconds = max_runtime_seconds

    def dispatch(self, request: Mapping[str, str]) -> None:
        required = ("run_id", "tenant_id", "trace_id", "reservation_id", "idempotency_key")
        if any(not isinstance(request.get(key), str) or not request[key] for key in required):
            raise ValueError("run request is missing a dispatch identifier")
        data = {
            "contract_version": "v1",
            "event_id": f"event-run-requested:{request['run_id']}",
            "event_type": "run.requested",
            "tenant_id": request["tenant_id"],
            "run_id": request["run_id"],
            "trace_id": request["trace_id"],
            "idempotency_key": request["idempotency_key"],
            "reservation_id": request["reservation_id"],
        }
        self._send(
            {
                "name": "run.requested",
                "data": data,
                "limits": {
                    "max_steps": self.max_steps,
                    "max_model_calls": self.max_model_calls,
                    "max_runtime_seconds": self.max_runtime_seconds,
                },
            }
        )
