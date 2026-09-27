Status: pending
Name: extend-metrics-py-with-three-ragas-functions

## Read first

- `PRD.md` §§1–3
- `services/evaluation/metrics.py` (existing `metric_ratio` helper at `:8` and six named wrappers `:16-44`)
- `docs/proposals/code-doc-drift/livingdoc-ops.yaml` (Trade-off section §4)
- `agent_platform/contracts.py` (`EvaluationRecord` type)

## Task

Extend `services/evaluation/metrics.py` with three RAGAS-style metric functions plus one `evaluate()` orchestrator that operate on plain dicts matching the shapes the existing proposal-review workbench already produces.

- `faithfulness(claims: list[str], evidence: list[str]) -> EvaluationRecord` — fraction of claims whose tokens overlap at least one evidence string's tokens with Jaccard ≥ 0.2.
- `answer_relevance(requirements: list[Mapping[str, Any]], decisions: list[Mapping[str, Any]]) -> EvaluationRecord` — fraction of decisions with `status != 'unknown'` AND non-empty `rationale`.
- `context_recall(requirements: list[Mapping[str, Any]], evidence_by_requirement: Mapping[str, list[str]]) -> EvaluationRecord` — fraction of requirements with at least one evidence range.
- `evaluate(decisions: list[Mapping[str, Any]], evidence: list[Mapping[str, Any]], requirements: list[Mapping[str, Any]]) -> dict[str, EvaluationRecord]` — orchestrator that builds the three inputs from the same shapes and returns the dict.

Add one private helper `_claim_tokens(text: str) -> set[str]` using `re.findall` (`re` is already imported at the top of `metrics.py`).

Each metric follows the existing `metric_ratio(name, numerator, denominator, *, threshold, inverse)` pattern (`metrics.py:8`). Threshold defaults: `faithfulness >= 0.7`, `answer_relevance >= 0.6`, `context_recall >= 0.8`.

## Acceptance Criteria

- `services/evaluation/metrics.py` exports the four new callables with type stubs; existing imports are unchanged.
- The new code does NOT import any module under `services.proposal_review.*` (verifiable via `grep -r 'services.proposal_review' services/evaluation/metrics.py` returns zero matches).
- The new code does NOT add any pypi dependency (verifiable via `pyproject.toml` diff).
- Each metric returns a well-formed `EvaluationRecord` (verifiable via the existing `metric_ratio` shape).
- Per-call cost is bounded by one `re.findall` + set-Jaccard pass over the bounded text.

## Verification & Status Update

Run `python -c "from services.evaluation.metrics import faithfulness, answer_relevance, context_recall, evaluate; print('imports ok')"` and verify no import errors. Record the output in `step0-output.json`.

## Don't

- Do not import any module under `services.proposal_review.*`.
- Do not modify `services/proposal_review/*` (read-only constraint for this proposal).
- Do not add a new pypi dependency.
- Do not create a new `services/evaluation/ragas.py` file — extend the existing `metrics.py`.
- Do not call an LLM provider from the new metrics.
- Do not persist the eval results anywhere; the metric functions are pure and return values only.