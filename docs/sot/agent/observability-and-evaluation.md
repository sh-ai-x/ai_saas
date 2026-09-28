---
doc_id: agent-observability-evaluation
domain: agent
purpose: Define LangSmith trace correlation, Ragas evaluation, prompt/model/tool telemetry, and evaluation loops.
read_when:
  - investigating agent quality, latency, cost, tool behavior, or regressions
  - changing prompts, models, trace fields, or evaluation datasets
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - runtime-and-tools.md
  - model-routing-and-cost.md
  - ../verification/release-and-incident.md
source_of_truth: contract
owner: agent-platform
last_reviewed: 2026-09-28
change_impact: high
---

# Agent Observability and Evaluation

## Trace contract

Every agent run should correlate:

- request, user, tenant, session, and `run_id`
- graph/node and tool name/version
- model/provider/policy version
- prompt/version identifier where permitted
- retrieval source/chunk IDs
- input/output token usage, latency, finish reason, retry/fallback reason
- evaluation scores, user feedback, and error category

LangSmith is the configured trace backend for LangChain and Ragas calls. The
Workbench exposes the project and console URL, but never an API key. Tracing
is useful for connecting the single LangChain synthesis call, optional JEV
context filtering, and the official Ragas judge calls to one review.

## Privacy and reliability

- Redact secrets and sensitive payloads before trace export.
- Make trace export asynchronous so telemetry failure does not block the user
  response.
- Record a local telemetry-loss signal when LangSmith is unavailable.
- Apply retention and deletion policies to traces, prompts, and evaluations.
- Use sampled payloads in production when full payload capture is not justified.

## Evaluation loop

1. Capture representative failures and user feedback.
2. Add sanitized cases to a versioned dataset.
3. Run official Ragas evaluators against the same bounded REQ/AC samples.
4. Compare prompt/model/code variants against the same reference and evidence.
5. Release only when quality, safety, latency, and cost gates pass.
6. Use LangSmith traces to inspect judge inputs, failures, latency, and cost.

The Workbench uses Faithfulness, Answer Relevance, Context Recall, Context
Relevance, and deterministic Evidence Integrity. Context Recall prefers an
explicit reference answer and labels requirement-derived references separately.
Metric failures are reported as unavailable rather than converted to zero.

Review submission is asynchronous. The API returns a review ID immediately;
the UI polls the persisted checkpoint until synthesis and Ragas evaluation
complete. This prevents evaluator latency from being mistaken for Foundation
API downtime.

Cost controls are `gpt-4o-mini`, `text-embedding-3-small`, bounded Ragas
strictness, and an exact-input in-process score cache. The cache key includes
the canonical rows, evaluator configuration, and evidence source hashes, so a
changed source cannot reuse an old score.

## Verification evidence

- Trace schema tests for every run, tool, model, and retrieval event.
- Redaction tests for credentials, payment data, and PII.
- Dataset regression results stored with prompt/model versions.
- Production alerts for error rate, latency, cost, loop rate, and evaluator
  score degradation.
- User feedback can be joined to a trace without exposing private content.
