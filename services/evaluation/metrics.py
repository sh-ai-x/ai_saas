"""Exact formula helpers; zero denominators are never passes."""

from __future__ import annotations

import re
from typing import Any, Mapping

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


# --- RAGAS-style metrics (LivingDoc-Ops drift detection) ---------------------
#
# Three deterministic proxies for RAGAS metrics, computed over the bounded shapes
# the proposal-review workbench already produces (review_graph.py:140-149).
# Zero imports from services.proposal_review.* — these functions take plain
# dicts so the change-impact workbench is not coupled to the metric library.

_FAITHFULNESS_JACCARD_THRESHOLD = 0.2
_DEFAULT_THRESHOLDS = {
    "faithfulness": 0.7,
    "answer_relevance": 0.6,
    "context_recall": 0.8,
}


def _claim_tokens(text: str) -> set[str]:
    """Lowercased alphanumeric tokens, ≥2 chars; shared by faithfulness + answer_relevance."""
    return {token.lower() for token in re.findall(r"[a-zA-Z0-9]{2,}", text or "")}


def faithfulness(claims: list[str], evidence: list[str], *, threshold: float = _DEFAULT_THRESHOLDS["faithfulness"]) -> EvaluationRecord:
    """Fraction of claims whose tokens overlap at least one evidence string's tokens with Jaccard ≥ 0.2."""
    evidence_token_sets = [_claim_tokens(item) for item in evidence]
    covered = 0
    for claim in claims:
        claim_tokens = _claim_tokens(claim)
        if not claim_tokens:
            continue
        if any(_jaccard(claim_tokens, ev_tokens) >= _FAITHFULNESS_JACCARD_THRESHOLD for ev_tokens in evidence_token_sets if ev_tokens):
            covered += 1
    return metric_ratio("faithfulness", covered, len(claims), threshold=threshold)


def answer_relevance(requirements: list[Mapping[str, Any]], decisions: list[Mapping[str, Any]], *, threshold: float = _DEFAULT_THRESHOLDS["answer_relevance"]) -> EvaluationRecord:
    """Fraction of decisions with status != 'unknown' AND non-empty rationale."""
    del requirements  # kept in the signature for orchestrator symmetry; this metric is decision-scoped
    if not decisions:
        return metric_ratio("answer_relevance", 0, 0, threshold=threshold)
    relevant = sum(1 for decision in decisions if str(decision.get("status", "")).strip().lower() != "unknown" and str(decision.get("rationale", "")).strip())
    return metric_ratio("answer_relevance", relevant, len(decisions), threshold=threshold)


def context_recall(requirements: list[Mapping[str, Any]], evidence_by_requirement: Mapping[str, list[str]], *, threshold: float = _DEFAULT_THRESHOLDS["context_recall"]) -> EvaluationRecord:
    """Fraction of requirements with at least one evidence range in evidence_by_requirement."""
    covered = sum(1 for requirement in requirements if evidence_by_requirement.get(str(requirement.get("requirement_id", "")), []))
    return metric_ratio("context_recall", covered, len(requirements), threshold=threshold)


def evaluate(decisions: list[Mapping[str, Any]], evidence: list[Mapping[str, Any]], requirements: list[Mapping[str, Any]]) -> dict[str, EvaluationRecord]:
    """Orchestrator: compute all three metrics from the canonical review-artifact dicts."""
    claims = [f"{decision.get('rationale', '')} {decision.get('impact', '')}".strip() for decision in decisions]
    evidence_strings = [str(item.get("excerpt", "")) for item in evidence]
    evidence_by_requirement: dict[str, list[str]] = {}
    for item in evidence:
        requirement_id = str(item.get("requirement_id", ""))
        if requirement_id:
            evidence_by_requirement.setdefault(requirement_id, []).append(str(item.get("excerpt", "")))
    return {
        "faithfulness": faithfulness(claims, evidence_strings),
        "answer_relevance": answer_relevance(requirements, decisions),
        "context_recall": context_recall(requirements, evidence_by_requirement),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0
