---
doc_id: agent-runtime-tools
domain: agent
purpose: Define agent run state, tool contracts, streaming, cancellation, and authorization.
read_when:
  - adding or changing a LangGraph node or tool
  - changing agent streaming, retries, cancellation, or run state
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
  - ../architecture/system-map.md
  - ../auth/google-oauth.md
  - ../security/safety-boundaries.md
source_of_truth: contract
owner: agent-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Agent Runtime and Tools

## Runtime boundary

The baseline runtime is Python/FastAPI plus LangGraph, packaged as a Docker
service. Next.js owns user-facing interaction and streaming presentation;
FastAPI owns authenticated run creation, authorization, and agent execution.
LangGraph is appropriate for stateful, long-running, persistent, streaming,
and human-in-the-loop workflows. **(source:
https://langchain-ai.github.io/langgraph/reference/)**

## Run state

Every run has a durable `run_id`, `user_id`/tenant scope, status, created and
updated times, idempotency key, model policy, budget, cancellation state, and
correlation ID.

```text
created -> queued -> running -> waiting_for_approval -> running
                         |              |
                         +-> succeeded  +-> cancelled
                         +-> failed     +-> timed_out
```

Transitions are server-controlled and append an event. A worker crash must
resume from a checkpoint or expose a recoverable failure; it must not create a
second side effect because a request was retried.

## Tool contract

Each tool declares:

- stable name and version
- typed input/output schema
- allowed caller and tenant scope
- read-only or side-effect level
- required entitlements
- timeout and retry class
- idempotency key construction
- approval requirement
- redaction policy
- trace fields and verification cases

Payment, account deletion, permission changes, external messages, and
production deployment are high-impact tools and require explicit approval or a
separate operator-controlled path. LangGraph supports interrupt-based human
review of tool calls. **(source:
https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/review-tool-calls/)**

## Execution policy

- Validate input before execution and validate output before state mutation.
- Never pass raw provider secrets or unrestricted database credentials to a
  model-generated tool.
- Classify retryable versus non-retryable failures.
- Enforce run step, time, token, concurrency, and cost limits.
- Make cancellation observable and propagate it to downstream calls.
- Stream user-safe progress; do not stream secrets, hidden credentials, or
  unredacted internal trace payloads.

## Verification evidence

- Tool schema, authorization, and tenant-isolation tests.
- Duplicate and retry tests for side-effecting tools.
- Approval tests prove high-impact tools pause before execution.
- Cancellation, timeout, provider failure, and worker restart tests.
- Trace assertions prove every tool call has run and correlation identifiers.

## Sources

- [LangGraph reference](https://langchain-ai.github.io/langgraph/reference/)
- [LangGraph human-in-the-loop](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/review-tool-calls/)
- [Vercel AI SDK streamText](https://ai-sdk.dev/docs/reference/ai-sdk-core/stream-text)
- Baseline: `../mysaas/my-saas/src/proxy.ts:15-63` for protected route
  boundaries and `src/instrumentation.ts:1-16` for request-error hooks.
