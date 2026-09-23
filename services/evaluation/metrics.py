"""Exact formula helpers; zero denominators are never passes."""

from __future__ import annotations

from agent_platform.contracts import EvaluationRecord


def metric_ratio(name: str, numerator: int, denominator: int, *, threshold: float = 1.0, inverse: bool = False) -> EvaluationRecord:
    if denominator <= 0:
        return EvaluationRecord(name, None, False, 0, True)
    value = numerator / denominator
    passed = value <= threshold if inverse else value >= threshold
    return EvaluationRecord(name, value, passed, denominator, False)


def requirement_coverage(satisfied: int, total: int) -> EvaluationRecord:
    return metric_ratio("requirement_coverage", satisfied, total)


def evidence_precision(valid: int, total: int) -> EvaluationRecord:
    return metric_ratio("evidence_precision", valid, total)


def invalid_reference_rate(invalid: int, total: int) -> EvaluationRecord:
    return metric_ratio("invalid_reference_rate", invalid, total, threshold=0.0, inverse=True)


def unsupported_claim_rate(unsupported: int, total: int) -> EvaluationRecord:
    return metric_ratio("unsupported_claim_rate", unsupported, total, threshold=0.0, inverse=True)


def cache_hit_rate(hits: int, total: int) -> EvaluationRecord:
    return metric_ratio("cache_hit_rate", hits, total, threshold=0.0)


def budget_overrun_rate(overruns: int, total: int) -> EvaluationRecord:
    return metric_ratio("budget_overrun_rate", overruns, total, threshold=0.0, inverse=True)


def terminal_state_consistency(consistent: int, total: int) -> EvaluationRecord:
    return metric_ratio("terminal_state_consistency", consistent, total)
