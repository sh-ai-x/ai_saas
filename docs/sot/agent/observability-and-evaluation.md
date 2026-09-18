---
doc_id: agent-observability-evaluation
domain: agent
purpose: Define trace correlation, prompt/model/tool telemetry, and evaluation loops.
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
last_reviewed: 2026-09-17
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

Langfuse is designed to trace LLM calls, tool invocations, retrieval steps,
token usage, latency, prompts, and evaluation scores. **(source:
https://langfuse.com/docs/observability/overview)**

## Privacy and reliability

- Redact secrets and sensitive payloads before trace export.
- Make trace export asynchronous so telemetry failure does not block the user
  response.
- Record a local telemetry-loss signal when Langfuse is unavailable.
- Apply retention and deletion policies to traces, prompts, and evaluations.
- Use sampled payloads in production when full payload capture is not justified.

## Evaluation loop

1. Capture representative failures and user feedback.
2. Add sanitized cases to a versioned dataset.
3. Run deterministic and model-based evaluators offline.
4. Compare prompt/model/code variants against the same dataset.
5. Release only when quality, safety, latency, and cost gates pass.
6. Score production traces and feed novel failures back into the dataset.

Langfuse describes the loop from offline datasets and experiments to online
production evaluation. **(source: https://langfuse.com/docs/evaluation/core-concepts)**

## Verification evidence

- Trace schema tests for every run, tool, model, and retrieval event.
- Redaction tests for credentials, payment data, and PII.
- Dataset regression results stored with prompt/model versions.
- Production alerts for error rate, latency, cost, loop rate, and evaluator
  score degradation.
- User feedback can be joined to a trace without exposing private content.

## Sources

- [Langfuse observability](https://langfuse.com/docs/observability/overview)
- [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts)
- Baseline: `../mysaas/my-saas/src/instrumentation.ts:1-16`,
  `src/instrumentation-client.ts:1-24`.
