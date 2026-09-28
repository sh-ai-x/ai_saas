Status: pending
Name: fixtures-and-adr

## Read first

- `PRD.md` §5 (Acceptance criteria)
- `phases/livingdoc-ragas-metrics/step0.md`
- `services/evaluation/metrics.py` (the three new functions added by Step 0)
- `docs/proposals/code-doc-drift/livingdoc-ops.yaml` §4 (Trade-off analysis)

## Task

Add `tests/test_ragas_metrics.py` with 16 fixtures against synthetic dicts. Add `docs/adr/ragas-metrics-extension.md` (~40 lines) documenting the four design choices.

### Tests

16 fixtures total, no `services/proposal_review` import:

**5 faithfulness fixtures:**
1. all_covered — every claim has an evidence match (Jaccard ≥ 0.2) → value = 1.0
2. one_uncovered — one claim has no evidence match → value = (n-1)/n
3. no_evidence — `evidence=[]` → denominator = 0, EvaluationRecord `insufficient=True`
4. multi_claim_split — one logical claim split into two atomic claims, both covered → value = 1.0
5. empty_synthesis — `claims=[]` → denominator = 0, EvaluationRecord `insufficient=True`

**5 answer_relevance fixtures:**
1. all_non_unknown — every decision has `status` in `{implemented, partial, missing, contradicted}` AND non-empty `rationale` → value = 1.0
2. one_unknown — one decision has `status='unknown'` → value = (n-1)/n
3. one_contradicted — one decision has `status='contradicted'` (still counts as relevant) → value = 1.0
4. partial_coverage — mixed `unknown` + `missing` + empty-rationale → value = (covered)/(total)
5. empty_requirements — `requirements=[]` → denominator = 0, EvaluationRecord `insufficient=True`

**5 context_recall fixtures:**
1. every_requirement_evidenced — `evidence_by_requirement` has at least one entry for each requirement → value = 1.0
2. one_uncovered — one requirement missing from `evidence_by_requirement` → value = (n-1)/n
3. cross_domain — same `evidence_by_requirement` covers requirements from different domain groups → value = 1.0
4. no_evidence — `evidence_by_requirement={}` → denominator = 0, EvaluationRecord `insufficient=True`
5. empty_requirements — `requirements=[]` → denominator = 0, EvaluationRecord `insufficient=True`

**1 `evaluate()` orchestrator fixture:**
- 3 decisions, 2 requirements, 4 evidence strings — assert all three EvaluationRecord values are returned and `passed` is `True` for thresholds `faithfulness >= 0.7`, `answer_relevance >= 0.6`, `context_recall >= 0.8`.

### ADR

`docs/adr/ragas-metrics-extension.md` (~40 lines) covering:

1. **Three-metric subset choice** — why Faithfulness + Answer Relevance + Context Recall and not the full RAGAS suite of six.
2. **Deterministic proxy choice** — why token-set Jaccard ≥ 0.2 instead of LLM-judge Faithfulness.
3. **No-change-impact-coupling choice** — why the metrics live standalone in `services/evaluation` with zero imports from `services/proposal_review/*`.
4. **Extend-existing-file choice** — why the three new functions extend `services/evaluation/metrics.py` rather than living in a new `services/evaluation/ragas.py` file.

## Acceptance Criteria

- `pytest tests/test_ragas_metrics.py -v` runs all 16 fixtures in <1 second; all pass.
- The test file does NOT import any module under `services.proposal_review.*`.
- `docs/adr/ragas-metrics-extension.md` exists, references `PRD.md` §1 Frame, and is committed alongside the code change.
- The ADR's "Status" section follows the project's existing ADR template.

## Verification & Status Update

Run `pytest tests/test_ragas_metrics.py -v` and capture the output in `step1-output.json`. Confirm:
- ` `16 passed in <1s``
- ` `0 failed``
- The test file does NOT reference `services.proposal_review` (verifiable via `grep -r 'services.proposal_review' tests/test_ragas_metrics.py` returns zero matches).

## Don't

- Do not import any module under `services.proposal_review.*` in the test file.
- Do not call an LLM provider from any fixture.
- Do not persist fixtures or test outputs to a database or external service.
- Do not skip a fixture with `pytest.skip` — every fixture must actually run and assert.
- Do not add a new pypi dependency for the test file.