"""Regression coverage for the official Ragas review evaluation boundary."""

from __future__ import annotations

from services.evaluation.ragas_metrics import _cache_key, _cached_scores, _records_from_result, _store_cached_scores, _unavailable_records, build_ragas_rows, evaluate_with_ragas
from services.review_comment_policy import comment_keys_for_status


def test_comment_field_policy_is_shared_by_review_and_ragas() -> None:
    assert comment_keys_for_status("partial") == ("implemented_comment", "not_implemented_comment")
    assert comment_keys_for_status("modified") == ("implemented_comment", "changed_comment")
    assert comment_keys_for_status("unexpected") == ("implemented_comment", "not_implemented_comment", "changed_comment")


def test_ragas_dataset_derives_requirement_reference_and_keeps_evidence_scoped() -> None:
    rows = build_ragas_rows(
        decisions=[{"requirement_id": "REQ-001", "status": "partial", "comment": "Some support", "risk": "Rotation is missing."}],
        evidence=[
            {"requirement_id": "REQ-001", "excerpt": "session code"},
            {"requirement_id": "REQ-002", "excerpt": "must not leak into another sample"},
        ],
        requirements=[{"requirement_id": "REQ-001", "text": "The system must manage sessions."}],
    )
    assert rows == [{
        "requirement_id": "REQ-001",
        "user_input": "The system must manage sessions.",
        "response": "Some support",
        "retrieved_contexts": ["session code"],
        "reference": "The system must manage sessions.",
        "reference_source": "requirement-derived",
    }]


def test_ragas_dataset_includes_context_recall_reference_only_when_explicit() -> None:
    rows = build_ragas_rows(
        decisions=[{"requirement_id": "REQ-001", "status": "implemented", "comment": "Sessions are stored."}],
        evidence=[{"requirement_id": "REQ-001", "excerpt": "sessions are stored"}],
        requirements=[{
            "requirement_id": "REQ-001",
            "text": "The system must manage sessions.",
            "reference_answer": "The system stores user sessions.",
        }],
    )
    assert rows[0]["reference"] == "The system stores user sessions."
    assert rows[0]["reference_source"] == "explicit"


def test_ragas_cache_fingerprint_includes_evidence_source_hash() -> None:
    base = build_ragas_rows(
        decisions=[{"requirement_id": "REQ-001", "status": "implemented", "comment": "Sessions are stored."}],
        evidence=[{"requirement_id": "REQ-001", "content_hash": "hash-a", "excerpt": "sessions are stored"}],
        requirements=[{"requirement_id": "REQ-001", "text": "The system must manage sessions."}],
    )
    changed = build_ragas_rows(
        decisions=[{"requirement_id": "REQ-001", "status": "implemented", "comment": "Sessions are stored."}],
        evidence=[{"requirement_id": "REQ-001", "content_hash": "hash-b", "excerpt": "sessions are stored"}],
        requirements=[{"requirement_id": "REQ-001", "text": "The system must manage sessions."}],
    )
    assert base[0]["evidence_hashes"] == ["hash-a"]
    assert _cache_key(base, evaluator_model="test-mini", embedding_model="test-embed", answer_relevancy_strictness=3) != _cache_key(changed, evaluator_model="test-mini", embedding_model="test-embed", answer_relevancy_strictness=3)


def test_evidence_integrity_is_separate_from_semantic_evidence_relevance() -> None:
    from services.evaluation.ragas_metrics import _evidence_integrity_record

    record = _evidence_integrity_record(
        [
            {"requirement_id": "REQ-001", "path": "auth.py", "start_line": 2, "end_line": 4, "excerpt": "create_session()", "rationale": "The range is connected to session creation."},
            {"requirement_id": "REQ-001", "path": "auth.py", "start_line": 2, "end_line": 4, "excerpt": "create_session()", "rationale": "Duplicate pointer."},
            {"requirement_id": "REQ-404", "path": "missing.py", "start_line": 0, "end_line": 1, "excerpt": "", "rationale": ""},
        ],
        [{"requirement_id": "REQ-001", "text": "The system must create sessions."}],
    )
    assert record.sample_count == 3
    assert record.supported_count == 1
    assert record.value == 1 / 3
    assert record.method.startswith("provenance shape validation")


def test_evidence_integrity_rejects_a_stale_source_hash() -> None:
    from services.evaluation.ragas_metrics import _evidence_integrity_record

    record = _evidence_integrity_record(
        [{
            "requirement_id": "REQ-001",
            "path": "auth.py",
            "start_line": 2,
            "end_line": 4,
            "excerpt": "create_session()",
            "rationale": "The range is connected to session creation.",
            "content_hash": "stale-hash",
        }],
        [{"requirement_id": "REQ-001", "text": "The system must create sessions."}],
        {"file_manifest": [{"path": "auth.py", "sha256": "current-hash"}]},
    )
    assert record.value == 0.0
    assert record.supported_count == 0
    assert "source hash" in record.method


def test_ragas_includes_every_review_status_in_the_sample_set() -> None:
    statuses = ["implemented", "modified", "partial", "missing", "unknown"]
    decisions = [
        {
            "requirement_id": f"REQ-{index}",
            "status": status,
            "implemented_comment": f"{status} implemented evidence",
            "not_implemented_comment": f"{status} remaining gap",
            "changed_comment": f"{status} changed approach",
        }
        for index, status in enumerate(statuses, 1)
    ]
    requirements = [
        {"requirement_id": f"REQ-{index}", "text": f"Requirement {status}"}
        for index, status in enumerate(statuses, 1)
    ]

    rows = build_ragas_rows(decisions, [], requirements)

    assert len(rows) == len(statuses)
    assert all(status in row["response"] for status, row in zip(statuses, rows, strict=True))


def test_ragas_scores_the_canonical_answer_instead_of_concatenating_ui_buckets() -> None:
    rows = build_ragas_rows(
        decisions=[{
            "requirement_id": "REQ-001",
            "status": "partial",
            "comment": "Session creation is implemented, but token rotation is not evidenced.",
            "implemented_comment": "Session creation is implemented.",
            "not_implemented_comment": "Token rotation is not evidenced.",
            "changed_comment": "The storage mechanism differs.",
        }],
        evidence=[{"requirement_id": "REQ-001", "path": "auth.py", "start_line": 10, "end_line": 12, "excerpt": "create_session()"}],
        requirements=[{"requirement_id": "REQ-001", "text": "The system must create sessions and rotate tokens."}],
    )
    assert rows[0]["response"] == "Session creation is implemented, but token rotation is not evidenced."
    assert rows[0]["retrieved_contexts"] == ["auth.py:10-12\ncreate_session()"]


def test_ragas_ignores_placeholder_comment_and_uses_status_explanation() -> None:
    rows = build_ragas_rows(
        decisions=[{
            "requirement_id": "REQ-001",
            "status": "partial",
            "comment": "No provider comment was returned.",
            "implemented_comment": "Session creation is implemented.",
            "not_implemented_comment": "Token rotation is not evidenced.",
        }],
        evidence=[],
        requirements=[{"requirement_id": "REQ-001", "text": "The system must create sessions and rotate tokens."}],
    )
    assert rows[0]["response"] == "Session creation is implemented. Token rotation is not evidenced."


def test_ragas_result_is_averaged_per_requirement_without_binary_approximation() -> None:
    records = _records_from_result({
        "faithfulness": [1.0, 0.5],
        "answer_relevance": [0.25, 0.75],
        "context_recall": [0.5, None, 1.0],
    })
    assert records["faithfulness"].value == 0.75
    assert records["faithfulness"].supported_count == 1
    assert records["answer_relevance"].value == 0.5
    assert records["context_recall"].value == 0.75
    assert records["faithfulness"].method.startswith("Ragas 0.4.3")


def test_ragas_answer_relevancy_result_is_exposed_as_product_answer_relevance() -> None:
    records = _records_from_result({"answer_relevancy": [0.25, 0.75]})
    assert records["answer_relevance"].value == 0.5
    assert records["answer_relevance"].sample_count == 2


def test_ragas_is_opt_in_when_openai_key_is_missing() -> None:
    result = evaluate_with_ragas([], [], [], environment={"OPENAI_API_KEY": ""})
    assert result is not None
    assert result.method == "ragas-unavailable"
    assert all(record.value is None for record in result.records.values())


def test_deterministic_evidence_integrity_remains_available_when_ragas_is_unavailable() -> None:
    result = evaluate_with_ragas(
        [],
        [{
            "requirement_id": "REQ-001",
            "path": "auth.py",
            "start_line": 1,
            "end_line": 2,
            "excerpt": "create_session()",
            "rationale": "The range contains session creation.",
        }],
        [{"requirement_id": "REQ-001", "text": "The system must create sessions."}],
        environment={"OPENAI_API_KEY": ""},
    )
    assert result is not None
    assert result.records["faithfulness"].value is None
    assert result.records["evidence_integrity"].value == 1.0


def test_ragas_score_cache_round_trips_exact_scores_and_errors() -> None:
    rows = [{"requirement_id": "REQ-001", "user_input": "requirement", "response": "answer"}]
    key = _cache_key(rows, evaluator_model="test-mini", embedding_model="test-embed", answer_relevancy_strictness=2)
    _store_cached_scores(key, {"faithfulness": [0.75]}, ["one recoverable sample error"])
    assert _cached_scores(key) == ({"faithfulness": [0.75]}, ["one recoverable sample error"])


def test_ragas_failure_is_unavailable_instead_of_a_misleading_proxy_score() -> None:
    records = _unavailable_records("Ragas evaluation failed: timeout")
    assert all(record.value is None for record in records.values())
    assert all(record.insufficient_sample for record in records.values())
    assert all("timeout" in str(record.reason) for record in records.values())
