"""Small, serializable kernel records.

These records deliberately contain no provider, product, or web-framework types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

RunState = Literal[
    "queued",
    "running",
    "waiting_approval",
    "plan_only",
    "verified",
    "quota_paused",
    "budget_exceeded",
    "failed",
    "rejected",
]
Impact = Literal["low", "high"]


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip()


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    title: str
    description: str
    acceptance: tuple[str, ...] = ()
    source_text: str = ""
    supported: bool = True

    def __post_init__(self) -> None:
        _required(self.requirement_id, "requirement_id")
        _required(self.title, "title")
        _required(self.description, "description")


@dataclass(frozen=True)
class EvidenceReference:
    requirement_id: str
    path: str
    start_line: int
    end_line: int
    content_hash: str
    symbol: str | None = None
    authorized: bool = True
    valid: bool = True

    def __post_init__(self) -> None:
        _required(self.requirement_id, "requirement_id")
        _required(self.path, "path")
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("evidence line range is invalid")
        _required(self.content_hash, "content_hash")


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    title: str
    action: str
    evidence: tuple[EvidenceReference, ...] = ()
    impact: Impact = "high"
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    plan_id: str
    requirements: tuple[Requirement, ...]
    steps: tuple[PlanStep, ...]
    runtime: str
    mode: Literal["plan_only", "verify"]
    supported_runtime: bool = True
    unsupported_reason: str | None = None
    valid_references: bool = True


@dataclass(frozen=True)
class RunLifecycle:
    run_id: str
    tenant_id: str
    idempotency_key: str
    state: RunState
    mode: Literal["plan_only", "verify"]
    sequence: int = 0
    error: str | None = None
    approval_id: str | None = None
    result: Mapping[str, Any] = field(default_factory=dict)
    proposal_id: str | None = None
    repository_id: str | None = None
    branch: str | None = None
    commit: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class ApprovalToken:
    token_id: str
    run_id: str
    tenant_id: str
    scopes: tuple[str, ...]
    issued_at: str
    expires_at: str
    consumed: bool = False
    repository_id: str | None = None
    branch: str | None = None
    commit: str | None = None
    plan_digest: str | None = None
    proposal_id: str | None = None


@dataclass(frozen=True)
class UsageRecord:
    run_id: str
    call_id: str
    phase: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated: bool
    cache_hit: bool
    retrieval_expansion: int
    budget_decision: str
    retry: bool = False

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0 or self.total_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens must equal input_tokens + output_tokens")


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    status: Literal["allowed", "quota_paused", "budget_exceeded"]
    reason: str
    total_used: int
    total_limit: int
    primary_calls: int
    retries: int


@dataclass(frozen=True)
class EvaluationRecord:
    metric: str
    value: float | None
    passed: bool
    sample_count: int
    insufficient_sample: bool = False


@dataclass(frozen=True)
class AdapterDescriptor:
    name: str
    kind: str
    version: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeliveryRequest:
    request_id: str
    run_id: str
    tenant_id: str
    artifact_hash: str
    action: Literal["deliver_patch"]
    approval_token_id: str
    signature: str


@dataclass(frozen=True)
class ReleaseReport:
    run_id: str
    status: str
    metrics: Mapping[str, EvaluationRecord]
    terminal_state_consistent: bool
    persisted: bool = False
    verification_status: str | None = None
    changed_files: tuple[str, ...] = ()
    test_results: tuple[Mapping[str, Any], ...] = ()
    artifact_ids: tuple[str, ...] = ()
    trace_id: str | None = None
    reason: str | None = None
