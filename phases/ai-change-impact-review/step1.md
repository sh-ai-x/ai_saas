Status: pending
Name: review-graph-and-evaluation

## Read first

- `PRD.md` §§2–5
- `services/agent_orchestrator/langgraph_runtime.py`
- `services/agent_orchestrator/model_port.py`
- `services/observability/adapter.py`
- `services/evaluation/metrics.py`

## Task

Implement the proposal review graph and evaluation seams. Use LangGraph for parse → manifest → structure → evidence → optional JEV context filter → synthesis → artifact stages with checkpoint/resume/cancel and idempotency. Use one LangChain Structured Runnable synthesis call per review, with a hard budget guard. Implement an optional one-call JEV context filter that returns selected evidence IDs, plus a deterministic byte-budget fallback. Export one redacted LangSmith review trace with requirement/evidence/model/rubric/token/cost metadata. Store immutable review artifacts and human decision records without raw source payloads.

## Acceptance Criteria

- The graph can resume from a persisted stage and does not repeat completed deterministic stages.
- LangChain synthesis is called at most once per review and receives only bounded evidence context.
- JEV is optional and called at most once; it receives compact candidates and can reduce the evidence passed to LangChain. Disabled/JEV-incomplete filtering falls back to the deterministic bounded set.
- LangSmith trace correlation includes review, proposal hash, repository fingerprint, and evidence IDs without secrets/raw snapshots.
- Artifact comparison and `ready/revise/blocked` recommendation are deterministic when provider calls are disabled.

## Verification & Status Update

Run focused graph, budget, redaction, artifact, and provider-mock tests. Record token-call counts, checkpoint/resume behavior, and diff checks.

## Don't

- Do not fan out an LLM/JEV call per file or requirement.
- Do not let JEV or the model mutate graph state into `ready` without evidence and human review.
- Do not make live provider credentials mandatory for local tests.
