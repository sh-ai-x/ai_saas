"""Typed durable run contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Literal

RunState = Literal[
    "queued", "running", "waiting_approval", "quota_paused", "completed", "failed", "cancelled"
]


def _freeze(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class RunCreate:
    tenant_id: str
    account_id: str
    project_id: str
    idempotency_key: str
    trace_id: str
    input: Mapping[str, Any]
    reserve_units: int = 1
    max_steps: int = 8
    max_model_calls: int = 8
    max_runtime_seconds: float = 300.0

    def __post_init__(self) -> None:
        for name in ("tenant_id", "account_id", "project_id", "idempotency_key", "trace_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if len(self.idempotency_key) < 8 or len(self.trace_id) < 8:
            raise ValueError("idempotency_key and trace_id must be at least 8 characters")
        if not isinstance(self.input, Mapping):
            raise ValueError("input must be an object")
        for name in ("reserve_units", "max_steps", "max_model_calls"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_steps > 32 or self.max_model_calls > 32:
            raise ValueError("workflow limits cannot exceed 32")
        if not isinstance(self.max_runtime_seconds, (int, float)) or isinstance(self.max_runtime_seconds, bool) or self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if self.max_runtime_seconds > 900:
            raise ValueError("workflow runtime cannot exceed 900 seconds")
        object.__setattr__(self, "input", _freeze(self.input))

    @property
    def fingerprint(self) -> str:
        value = {
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "project_id": self.project_id,
            "trace_id": self.trace_id,
            "input": self.input,
            "reserve_units": self.reserve_units,
            "max_steps": self.max_steps,
            "max_model_calls": self.max_model_calls,
            "max_runtime_seconds": self.max_runtime_seconds,
        }
        value["input"] = dict(self.input)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Run:
    run_id: str
    tenant_id: str
    account_id: str
    project_id: str
    idempotency_key: str
    trace_id: str
    input: Mapping[str, Any]
    state: RunState
    sequence: int
    reservation_id: str | None
    cancel_requested: bool
    worker_attempt: int
    max_steps: int
    max_model_calls: int
    max_runtime_seconds: float
    result: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "input", _freeze(self.input))
        object.__setattr__(self, "result", _freeze(self.result))


@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    tenant_id: str
    sequence: int
    event: str
    data: Mapping[str, Any]
    created_at: str

    @property
    def data_json(self) -> str:
        return json.dumps(
            {
                "contract_version": "v1",
                "event_id": self.event_id,
                "event": self.event,
                "run_id": self.run_id,
                "sequence": self.sequence,
                "payload": dict(self.data),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    step: int
    state: Mapping[str, Any]
    inflight_key: str | None
    approval_id: str | None
    usage_units: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _freeze(self.state))
