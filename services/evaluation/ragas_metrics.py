"""OpenAI-backed Ragas evaluation for the change-impact workbench.

Ragas is the score authority when an OpenAI key is configured. LangSmith is
enabled through the normal LangChain environment aliases, so the evaluator
LLM and embedding calls appear in the existing trace project without making
LangSmith responsible for the score calculation.
"""

from __future__ import annotations

import math
import os
import asyncio
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from numbers import Real
from statistics import fmean
from typing import Any, Mapping

from agent_platform.contracts import EvaluationRecord

_METRIC_NAMES = ("faithfulness", "answer_relevance", "context_recall", "evidence_relevance")
_RAGAS_RESULT_NAMES = {
    # Ragas uses the library name "answer_relevancy" while the product
    # contract/UI intentionally uses the clearer "answer_relevance" label.
    "answer_relevance": "answer_relevancy",
}
RAGAS_THRESHOLDS = {
    "faithfulness": 0.7,
    "answer_relevance": 0.6,
    "context_recall": 0.8,
    "evidence_relevance": 0.6,
}
_PLACEHOLDER_RESPONSES = {
    "no provider comment was returned.",
    "no review response was returned.",
    "no status comment",
    "no impact summary",
}
_RAGAS_CACHE_MAX_ENTRIES = 64
_RAGAS_SCORE_CACHE: OrderedDict[str, tuple[dict[str, list[float]], list[str]]] = OrderedDict()


def _usable_response(value: Any) -> str:
    response = " ".join(str(value or "").split()).strip()
    if response.casefold() in _PLACEHOLDER_RESPONSES:
        return ""
    return response


def _cache_key(rows: list[dict[str, Any]], *, evaluator_model: str, embedding_model: str, answer_relevancy_strictness: int) -> str:
    payload = {
        "version": "ragas-v3-reference-evidence",
        "rows": rows,
        "evaluator_model": evaluator_model,
        "embedding_model": embedding_model,
        "answer_relevancy_strictness": answer_relevancy_strictness,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cached_scores(key: str) -> tuple[dict[str, list[float]], list[str]] | None:
    cached = _RAGAS_SCORE_CACHE.get(key)
    if cached is None:
        return None
    _RAGAS_SCORE_CACHE.move_to_end(key)
    scores, errors = cached
    return ({name: list(values) for name, values in scores.items()}, list(errors))


def _store_cached_scores(key: str, scores: dict[str, list[float]], errors: list[str]) -> None:
    _RAGAS_SCORE_CACHE[key] = ({name: list(values) for name, values in scores.items()}, list(errors))
    _RAGAS_SCORE_CACHE.move_to_end(key)
    while len(_RAGAS_SCORE_CACHE) > _RAGAS_CACHE_MAX_ENTRIES:
        _RAGAS_SCORE_CACHE.popitem(last=False)


@dataclass(frozen=True)
class RagasEvaluation:
    records: dict[str, EvaluationRecord]
    method: str
    error: str | None = None
    reference_answers: dict[str, str] = field(default_factory=dict)
    reference_sources: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _reference_answer(requirement: Mapping[str, Any]) -> tuple[str, str]:
    """Return an explicit reference or a clearly-labelled requirement proxy.

    A proposal requirement is not an observed ground-truth answer.  When the
    caller has not supplied an annotated answer, however, its normative text
    is the only independent specification available for retrieval evaluation.
    We keep the source label so the UI cannot confuse this coverage signal with
    a human-authored reference answer.
    """
    for key in ("reference_answer", "reference", "ground_truth"):
        value = str(requirement.get(key, "")).strip()
        if value:
            return value[:2_000], "explicit"
    requirement_text = str(requirement.get("text", "")).strip()
    if requirement_text:
        return requirement_text[:2_000], "requirement-derived"
    return "", "missing"


def build_ragas_rows(
    decisions: list[Mapping[str, Any]],
    evidence: list[Mapping[str, Any]],
    requirements: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Map one review requirement to one Ragas single-turn sample.

    Faithfulness and Answer Relevancy do not require a ground-truth answer.
    Context Recall uses an explicit reference when supplied; otherwise it uses
    the requirement text as a separately-labelled expected-claims reference.
    This enables coverage measurement without presenting the requirement as
    an observed production answer.
    """
    decisions_by_id = {str(item.get("requirement_id")): item for item in decisions}
    evidence_by_id: dict[str, list[str]] = {}
    for item in evidence:
        requirement_id = str(item.get("requirement_id", ""))
        excerpt = str(item.get("excerpt", "")).strip()
        if requirement_id and excerpt:
            path = str(item.get("path", "")).strip()
            start_line = str(item.get("start_line", "")).strip()
            end_line = str(item.get("end_line", "")).strip()
            provenance = f"{path}:{start_line}-{end_line}" if path and start_line and end_line else path
            evidence_by_id.setdefault(requirement_id, []).append(
                f"{provenance}\n{excerpt[:4_000]}".strip() if provenance else excerpt[:4_000]
            )

    rows: list[dict[str, Any]] = []
    for requirement in requirements[:40]:
        requirement_id = str(requirement.get("requirement_id", ""))
        question = str(requirement.get("text", "")).strip()[:2_000]
        if not requirement_id or not question:
            continue
        decision = decisions_by_id.get(requirement_id, {})
        # Ragas evaluates one answer, not the UI's three display buckets.
        # Concatenating implemented/not-implemented/changed/risk text creates
        # a contradictory answer with absence claims that the code excerpt
        # cannot prove, which makes Faithfulness and Answer Relevancy measure
        # the presentation format instead of the review answer.
        response = _usable_response(decision.get("comment")) or _usable_response(decision.get("impact"))
        if not response:
            status = str(decision.get("status", "unknown")).strip().lower()
            status_parts = {
                "implemented": ("implemented_comment",),
                "modified": ("implemented_comment", "changed_comment"),
                "partial": ("implemented_comment", "not_implemented_comment"),
                "missing": ("not_implemented_comment",),
                "unknown": ("not_implemented_comment",),
                "contradicted": ("not_implemented_comment", "changed_comment"),
            }.get(status, ("implemented_comment", "not_implemented_comment", "changed_comment"))
            response = " ".join(
                dict.fromkeys(
                    part
                    for key in status_parts
                    if (part := _usable_response(decision.get(key)))
                )
            )
        response = response[:4_000]
        if not response:
            response = str(decision.get("status", "unknown")).strip() or "No review response was returned."
        evidence_hashes = sorted({
            str(item.get("content_hash", "")).strip()
            for item in evidence
            if str(item.get("requirement_id", "")) == requirement_id and str(item.get("content_hash", "")).strip()
        })
        rows.append(
            {
                "requirement_id": requirement_id,
                "user_input": question,
                "response": response,
                "retrieved_contexts": evidence_by_id.get(requirement_id, []),
            }
        )
        if evidence_hashes:
            # This is metadata for cache invalidation, not context presented
            # to the judge. A changed source file must trigger a fresh score
            # even when its bounded excerpt happens to be unchanged.
            rows[-1]["evidence_hashes"] = evidence_hashes
        reference_answer, reference_source = _reference_answer(requirement)
        if reference_answer:
            rows[-1]["reference"] = reference_answer
            rows[-1]["reference_source"] = reference_source
    return rows


def _configure_langsmith_aliases(values: Mapping[str, str]) -> None:
    """Make LANGSMITH_* configuration visible to LangChain/Ragas tracing."""
    aliases = {
        "LANGCHAIN_TRACING_V2": values.get("LANGSMITH_TRACING", ""),
        "LANGCHAIN_API_KEY": values.get("LANGSMITH_API_KEY", ""),
        "LANGCHAIN_ENDPOINT": values.get("LANGSMITH_ENDPOINT", ""),
        "LANGCHAIN_PROJECT": values.get("LANGSMITH_PROJECT", ""),
    }
    for name, value in aliases.items():
        if value and not os.environ.get(name):
            os.environ[name] = value


def _finite_scores(result: Any, name: str) -> list[float]:
    values = None
    for result_name in (name, _RAGAS_RESULT_NAMES.get(name, "")):
        if not result_name:
            continue
        try:
            values = result[result_name]
            break
        except (KeyError, TypeError):
            continue
    if values is None:
        return []
    if not isinstance(values, list):
        values = list(values)
    return [float(value) for value in values if isinstance(value, Real) and math.isfinite(float(value))]


def _records_from_result(result: Any, *, context_recall_available: bool = True) -> dict[str, EvaluationRecord]:
    records: dict[str, EvaluationRecord] = {}
    method = "Ragas 0.4.3 · OpenAI LLM + embeddings"
    for name in _METRIC_NAMES:
        scores = _finite_scores(result, name)
        if not scores:
            reason = "Context Recall requires an explicit reference answer." if name == "context_recall" and not context_recall_available else "Ragas returned no finite sample scores."
            sample_label = (
                "reference answers"
                if name == "context_recall"
                else "REQ/AC evidence packs"
                if name == "evidence_relevance"
                else "REQ/AC samples"
            )
            records[name] = EvaluationRecord(name, None, False, 0, True, 0, sample_label, method, reason)
            continue
        value = max(0.0, min(1.0, fmean(scores)))
        threshold = RAGAS_THRESHOLDS[name]
        supported_count = sum(score >= threshold for score in scores)
        sample_label = (
            "reference answers"
            if name == "context_recall"
            else "REQ/AC evidence packs"
            if name == "evidence_relevance"
            else "REQ/AC samples"
        )
        records[name] = EvaluationRecord(name, value, value >= threshold, len(scores), False, supported_count, sample_label, method)
    return records


def _unavailable_records(reason: str) -> dict[str, EvaluationRecord]:
    """Fail closed when configured Ragas cannot produce an evaluation."""
    return {
        name: EvaluationRecord(
            name,
            None,
            False,
            0,
            True,
            0,
            "reference answers"
            if name == "context_recall"
            else "REQ/AC evidence packs"
            if name == "evidence_relevance"
            else "REQ/AC samples",
            "Ragas 0.4.3 · unavailable",
            reason,
        )
        for name in _METRIC_NAMES
    }


def _unavailable_with_integrity(
    reason: str,
    evidence: list[Mapping[str, Any]],
    requirements: list[Mapping[str, Any]],
    repository: Mapping[str, Any] | None,
) -> dict[str, EvaluationRecord]:
    """Keep the deterministic evidence check available without an LLM key."""
    records = _unavailable_records(reason)
    records["evidence_integrity"] = _evidence_integrity_record(evidence, requirements, repository)
    return records


def _evidence_integrity_record(
    evidence: list[Mapping[str, Any]],
    requirements: list[Mapping[str, Any]],
    repository: Mapping[str, Any] | None = None,
) -> EvaluationRecord:
    """Check whether evidence has a usable, traceable shape.

    This is intentionally not called factual correctness: the evaluator only
    receives bounded excerpts, not the repository filesystem. It catches bad
    requirement IDs, paths, line ranges, empty excerpts/rationales, and
    duplicate pointers before semantic Ragas scoring is interpreted.
    """
    if not evidence:
        return EvaluationRecord(
            "evidence_integrity",
            None,
            False,
            0,
            True,
            0,
            "evidence items",
            "provenance shape validation · deterministic",
            "No evidence items were available to validate.",
        )
    requirement_ids = {str(item.get("requirement_id", "")) for item in requirements}
    manifest = {
        str(item.get("path")): str(item.get("sha256"))
        for item in (repository or {}).get("file_manifest", [])
        if isinstance(item, Mapping) and item.get("path") and item.get("sha256")
    }
    seen: set[tuple[str, str, int, int]] = set()
    valid = 0
    for item in evidence:
        requirement_id = str(item.get("requirement_id", "")).strip()
        path = str(item.get("path", "")).strip()
        excerpt = str(item.get("excerpt", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        try:
            start_line = int(item.get("start_line", 0))
            end_line = int(item.get("end_line", 0))
        except (TypeError, ValueError):
            start_line, end_line = 0, 0
        pointer = (requirement_id, path, start_line, end_line)
        source_hash = str(item.get("content_hash", "")).strip()
        source_matches_manifest = not manifest or (path in manifest and source_hash == manifest[path])
        is_valid = (
            requirement_id in requirement_ids
            and bool(path)
            and bool(excerpt)
            and bool(rationale)
            and start_line >= 1
            and end_line >= start_line
            and end_line - start_line + 1 <= 20
            and pointer not in seen
            and source_matches_manifest
        )
        if is_valid:
            valid += 1
            seen.add(pointer)
    value = valid / len(evidence)
    return EvaluationRecord(
        "evidence_integrity",
        value,
        value >= 1.0,
        len(evidence),
        False,
        valid,
        "evidence items",
        "provenance shape + source hash validation · deterministic" if manifest else "provenance shape validation · deterministic",
    )


def _bounded_int(values: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(str(values.get(name, default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float(values: Mapping[str, str], name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(str(values.get(name, default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _metric_score(result: Any) -> float | None:
    """Extract one finite numeric score from a collections metric result."""
    value = getattr(result, "value", result)
    if isinstance(value, Real) and math.isfinite(float(value)):
        return max(0.0, min(1.0, float(value)))
    return None


async def _evaluate_collection_rows(
    rows: list[dict[str, Any]],
    *,
    faithfulness_metric: Any,
    answer_relevancy_metric: Any,
    context_recall_metric: Any,
    evidence_relevance_metric: Any,
    batch_size: int,
    delay_seconds: float,
) -> tuple[dict[str, list[float]], list[str]]:
    """Evaluate each Ragas sample independently with the collections API.

    ``ragas.evaluate`` is a dataset orchestration layer.  In Ragas 0.4.3 its
    legacy batch path can raise ``IndexError`` when one structured LLM output
    is empty, discarding every score in that batch.  The collections metrics
    are the same official Faithfulness/Answer Relevancy/Context Recall
    implementations, but their ``ascore`` calls let us retain successful
    samples and report only the failed sample as unavailable.
    """
    scores: dict[str, list[float]] = {}
    errors: list[str] = []
    for start in range(0, len(rows), batch_size):
        if start:
            await asyncio.sleep(delay_seconds)
        for offset, row in enumerate(rows[start : start + batch_size]):
            sample_number = start + offset + 1
            contexts = [str(item).strip() for item in row.get("retrieved_contexts", []) if str(item).strip()]
            response = str(row.get("response", "")).strip()
            user_input = str(row.get("user_input", "")).strip()

            if contexts:
                try:
                    score = _metric_score(
                        await faithfulness_metric.ascore(
                            user_input=user_input,
                            response=response,
                            retrieved_contexts=contexts,
                        )
                    )
                    if score is not None:
                        scores.setdefault("faithfulness", []).append(score)
                    else:
                        errors.append(f"faithfulness sample {sample_number}: non-finite score")
                except Exception as exc:  # keep the other metrics/sample measurable
                    errors.append(
                        f"faithfulness sample {sample_number}: {type(exc).__name__}: {str(exc)[:160]}"
                    )

            try:
                score = _metric_score(
                    await answer_relevancy_metric.ascore(
                        user_input=user_input,
                        response=response,
                    )
                )
                if score is not None:
                    scores.setdefault("answer_relevance", []).append(score)
                else:
                    errors.append(f"answer_relevance sample {sample_number}: non-finite score")
            except Exception as exc:  # keep the other metrics/sample measurable
                errors.append(
                    f"answer_relevance sample {sample_number}: {type(exc).__name__}: {str(exc)[:160]}"
                )

            if contexts:
                try:
                    score = _metric_score(
                        await evidence_relevance_metric.ascore(
                            user_input=user_input,
                            retrieved_contexts=contexts,
                        )
                    )
                    if score is not None:
                        scores.setdefault("evidence_relevance", []).append(score)
                    else:
                        errors.append(f"evidence_relevance sample {sample_number}: non-finite score")
                except Exception as exc:  # keep the other metrics/sample measurable
                    errors.append(
                        f"evidence_relevance sample {sample_number}: {type(exc).__name__}: {str(exc)[:160]}"
                    )

            reference = str(row.get("reference", "")).strip()
            if reference and contexts:
                try:
                    score = _metric_score(
                        await context_recall_metric.ascore(
                            user_input=user_input,
                            retrieved_contexts=contexts,
                            reference=reference,
                        )
                    )
                    if score is not None:
                        scores.setdefault("context_recall", []).append(score)
                    else:
                        errors.append(f"context_recall sample {sample_number}: non-finite score")
                except Exception as exc:  # keep the other metrics/sample measurable
                    errors.append(
                        f"context_recall sample {sample_number}: {type(exc).__name__}: {str(exc)[:160]}"
                    )
    return scores, errors


def _run_official_ragas_scores(
    rows: list[dict[str, Any]],
    *,
    values: Mapping[str, str],
    api_key: str,
    evaluator_model: str,
    embedding_model: str,
    answer_relevancy_strictness: int,
) -> tuple[dict[str, list[float]], list[str]]:
    """Run the official judges with bounded retries and one shared client."""
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextRecall, ContextRelevance, Faithfulness

    _configure_langsmith_aliases(values)
    batch_size = _bounded_int(values, "RAGAS_BATCH_SIZE", 2, minimum=1, maximum=8)
    max_retries = _bounded_int(values, "RAGAS_MAX_RETRIES", 4, minimum=1, maximum=10)
    delay_seconds = _bounded_float(values, "RAGAS_BATCH_DELAY_SECONDS", 1.0, minimum=0.0, maximum=30.0)
    evaluator_client = AsyncOpenAI(
        api_key=api_key,
        max_retries=max_retries,
        timeout=180,
    )
    evaluator_llm = llm_factory(evaluator_model, client=evaluator_client)
    evaluator_embeddings = embedding_factory("openai", model=embedding_model, client=evaluator_client)
    return asyncio.run(
        _evaluate_collection_rows(
            rows,
            faithfulness_metric=Faithfulness(llm=evaluator_llm),
            answer_relevancy_metric=AnswerRelevancy(
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
                strictness=answer_relevancy_strictness,
            ),
            context_recall_metric=ContextRecall(llm=evaluator_llm),
            evidence_relevance_metric=ContextRelevance(llm=evaluator_llm),
            batch_size=batch_size,
            delay_seconds=delay_seconds,
        )
    )


def evaluate_with_ragas(
    decisions: list[Mapping[str, Any]],
    evidence: list[Mapping[str, Any]],
    requirements: list[Mapping[str, Any]],
    *,
    repository: Mapping[str, Any] | None = None,
    environment: Mapping[str, str] | None = None,
) -> RagasEvaluation | None:
    """Run the official Ragas metrics when OPENAI_API_KEY is available.

    This function is deliberately fail-closed. Missing credentials or a
    transient evaluator failure returns unavailable records instead of a
    lexical approximation that could be mistaken for an official Ragas score.
    """
    values = {**os.environ, **(environment or {})}
    api_key = str(values.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        reason = "OPENAI_API_KEY is required for official Ragas evaluation."
        return RagasEvaluation(
            _unavailable_with_integrity(reason, evidence, requirements, repository),
            "ragas-unavailable",
            reason,
        )
    rows = build_ragas_rows(decisions, evidence, requirements)
    if not rows:
        reason = "No REQ/AC samples were available for Ragas evaluation."
        return RagasEvaluation(
            _unavailable_with_integrity(reason, evidence, requirements, repository),
            "ragas-unavailable",
            reason,
        )

    evaluator_model = str(values.get("RAGAS_EVALUATOR_MODEL") or "gpt-4o-mini")
    embedding_model = str(values.get("RAGAS_EMBEDDING_MODEL") or "text-embedding-3-small")
    answer_relevancy_strictness = _bounded_int(values, "RAGAS_ANSWER_RELEVANCY_STRICTNESS", 3, minimum=1, maximum=3)
    cache_enabled = str(values.get("RAGAS_CACHE_ENABLED", "true")).strip().lower() not in {"0", "false", "no", "off"}
    cache_key = _cache_key(
        rows,
        evaluator_model=evaluator_model,
        embedding_model=embedding_model,
        answer_relevancy_strictness=answer_relevancy_strictness,
    )
    cached = _cached_scores(cache_key) if cache_enabled else None
    cache_hit = cached is not None
    if cached is not None:
        scores, errors = cached
    else:
        try:
            scores, errors = _run_official_ragas_scores(
                rows,
                values=values,
                api_key=api_key,
                evaluator_model=evaluator_model,
                embedding_model=embedding_model,
                answer_relevancy_strictness=answer_relevancy_strictness,
            )
        except Exception as exc:  # evaluator failure must not discard the review artifact
            error = f"{type(exc).__name__}: {str(exc)[:240]}"
            return RagasEvaluation(
                _unavailable_with_integrity(f"Ragas evaluation failed: {error}", evidence, requirements, repository),
                "ragas-unavailable",
                error,
            )
        if cache_enabled:
            _store_cached_scores(cache_key, scores, errors)
    if not any(scores.values()):
        reason = "Ragas produced no successful metric samples."
        if errors:
            reason += " " + errors[0]
        return RagasEvaluation(
            _unavailable_with_integrity(reason, evidence, requirements, repository),
            "ragas-unavailable",
            reason,
        )
    records = _records_from_result(
        scores,
        context_recall_available=any(bool(row.get("reference")) for row in rows),
    )
    records["evidence_integrity"] = _evidence_integrity_record(evidence, requirements, repository)
    reference_answers = {
        str(row.get("requirement_id")): str(row.get("reference"))
        for row in rows
        if row.get("requirement_id") and row.get("reference")
    }
    reference_sources = {
        str(row.get("requirement_id")): str(row.get("reference_source", "explicit"))
        for row in rows
        if row.get("requirement_id") and row.get("reference")
    }
    error = "; ".join(errors[:3]) if errors else None
    estimated_judge_calls = len(rows) * (1 + answer_relevancy_strictness + 2 + 1)
    metadata = {
        "evaluator_model": evaluator_model,
        "embedding_model": embedding_model,
        "answer_relevancy_strictness": answer_relevancy_strictness,
        "cache_enabled": cache_enabled,
        "cache_hit": cache_hit,
        "estimated_judge_calls": estimated_judge_calls,
    }
    return RagasEvaluation(
        records,
        "ragas-cache" if cache_hit else "ragas-partial" if error else "ragas",
        error,
        reference_answers,
        reference_sources,
        metadata,
    )
