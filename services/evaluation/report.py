"""Machine-readable release report builder."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent_platform.contracts import EvidenceReference, EvaluationRecord, Plan, ReleaseReport, Requirement, UsageRecord

from .metrics import (
    budget_overrun_rate,
    cache_hit_rate,
    evidence_precision,
    invalid_reference_rate,
    metric_ratio,
    requirement_coverage,
    terminal_state_consistency,
    unsupported_claim_rate,
)


def build_release_report(
    *,
    run_id: str,
    status: str,
    requirements: Sequence[Requirement],
    evidence: Sequence[EvidenceReference],
    plan: Plan,
    usage: Sequence[UsageRecord],
    latency_ms: int,
    approval_bypass: int,
    secret_leakage: int,
    prompt_injection: int,
    reason: str | None = None,
    verification_status: str | None = None,
    changed_files: Sequence[str] = (),
    test_results: Sequence[Mapping[str, Any]] = (),
    artifact_ids: Sequence[str] = (),
    trace_id: str | None = None,
) -> ReleaseReport:
    valid_evidence = sum(1 for item in evidence if item.valid and item.authorized)
    metric_map: dict[str, EvaluationRecord] = {
        "requirement_coverage": requirement_coverage(len({item.requirement_id for item in evidence if item.valid}), len(requirements)),
        "evidence_precision": evidence_precision(valid_evidence, len(evidence)),
        "invalid_reference_rate": invalid_reference_rate(len(evidence) - valid_evidence, len(evidence)),
        "unsupported_claim_rate": unsupported_claim_rate(0 if plan.valid_references else 1, len(requirements)),
        "latency_ms": EvaluationRecord("latency_ms", float(latency_ms), latency_ms >= 0, 1, False),
        "token_usage": EvaluationRecord("token_usage", float(sum(item.total_tokens for item in usage)), True, len(usage), len(usage) == 0),
        "cost": EvaluationRecord("cost", 0.0, True, 1, False),
        "cache_hit_rate": cache_hit_rate(sum(1 for item in usage if item.cache_hit), len(usage)),
        "budget_overrun_rate": budget_overrun_rate(sum(1 for item in usage if item.budget_decision not in {"allowed"}), len(usage)),
        "approval_bypass_rate": metric_ratio("approval_bypass_rate", approval_bypass, 1, threshold=0.0, inverse=True),
        "secret_leakage_rate": metric_ratio("secret_leakage_rate", secret_leakage, 1, threshold=0.0, inverse=True),
        "prompt_injection_rate": metric_ratio("prompt_injection_rate", prompt_injection, 1, threshold=0.0, inverse=True),
        "terminal_state_consistency": terminal_state_consistency(1 if status in {"verified", "plan_only", "failed", "rejected", "quota_paused", "budget_exceeded"} else 0, 1),
    }
    if reason:
        metric_map["reason_recorded"] = EvaluationRecord("reason_recorded", 1.0, True, 1, False)
    return ReleaseReport(
        run_id,
        status,
        metric_map,
        metric_map["terminal_state_consistency"].passed,
        verification_status=verification_status or status,
        changed_files=tuple(changed_files),
        test_results=tuple(dict(item) for item in test_results),
        artifact_ids=tuple(artifact_ids),
        trace_id=trace_id,
        reason=reason,
    )
